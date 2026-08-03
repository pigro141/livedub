"""Backend Qwen3-TTS ONNX: la voce si descrive a parole, e sono illimitate.

Piper e Kokoro hanno **due** voci italiane; oltre il secondo personaggio si
spostano i semitoni, cioe' si trucca la stessa voce. Questo modello e'
*VoiceDesign*: la voce non si sceglie da un elenco, si **descrive** — «un uomo
sulla quarantina, voce roca e stanca» — e il pool smette di essere un vincolo.
L'italiano e' una lingua di prima classe (`codec_language_id['italian'] = 2070`),
non un ripiego.

## Perche' e' vivibile, e perche' non lo e' ancora

Il modello e' autoregressivo a 12 Hz: genera un frame per passo, e ogni frame
vale 83 ms di audio. Misurato su questa macchina (4060, int4, CUDA verificato):

    prefill                      200 ms   una volta per battuta
    passo (decode + 15x cp)     55,3 ms   per frame
    vocoder                      11 ms    su 4 frame (85 su 64)

**55,3 ms di calcolo per 83,3 ms di audio: 0,66x tempo reale.** Il modello sta
avanti da solo, quindi in streaming la latenza al primo campione sarebbe

    2 frame (0,17 s di audio):  200 + 111 + 10  =  320 ms
    4 frame (0,33 s di audio):  200 + 221 + 11  =  432 ms

contro i 174 ms di Kokoro — pagabili, dentro un bilancio dal vivo che sta fra
1150 e 1400 ms.

**Ma questo backend non fa streaming, e quindi dal vivo non e' utilizzabile.**
Restituisce la battuta intera: ~3,5 s. Lo streaming non si aggiunge qui — la
catena a monte sintetizza, *poi* misura la durata, *poi* calcola la fretta WSOLA,
*poi* programma, e il mixer tiene un array fisso. Con lo streaming la durata non
esiste ancora quando la voce deve partire, quindi tocca `mix/mixer.py` e
`fuse/timing.py`. E' il lavoro grosso, ed e' quello che porta i 3,5 s a 320 ms.

Quello che questo backend serve a fare **adesso** e' l'ascolto: con
`tools/dub.py --mp4` si giudica l'italiano, la resa delle voci descritte e la
prosodia. Rifare il mixer prima di quel giudizio sarebbe costruire su una
supposizione.

## Il modello si avvolge, non si riscrive

Il repo del modello porta `generate_onnx.py`, che e' la sola implementazione di
riferimento del ciclo autoregressivo. Riscriverla sarebbe rifare a mano un
campionamento con penalita' di ripetizione e sedici gruppi di codici: una
trasformata sbagliata li' produce spazzatura **plausibile**, non un errore. Si
avvolge quindi quella, sistemando l'unica cosa che la rende inservibile — che
**ricarica 4,2 GB di modelli a ogni chiamata**, cioe' cinque secondi per battuta.

Due innesti, dichiarati:

- `ort.InferenceSession` restituisce sessioni **in cache** per percorso;
- `transformers.AutoTokenizer` diventa un guscio su `tokenizers`, che legge lo
  stesso `tokenizer.json`. Cosi' il venv non prende `transformers` (che non
  serve: di quel pacchetto si usa solo `.encode()`).
"""

from __future__ import annotations

import contextlib
import glob
import os
import sys
import time
import types

import numpy as np

from core.types import VoiceSpec
from mix.stretch import pitch_shift, resample
from speak.base import Speech, taglia_silenzio

# Frequenza nativa del vocoder, dal `config.json` del modello.
NATIVE_RATE = 24000

# **Il passo, misurato, in unita' di `spoken_length()`.** Come per gli altri
# backend: un numero solo per tutti i motori e' gia' costato due sessioni.
#
# **E' il piu' incerto dei quattro, e va detto.** Questo modello **campiona** (con
# `temperature` e `top_k`), quindi la durata non e' una funzione del testo: e' una
# variabile casuale. Chi lo usa deve aspettarsi che la previsione dei tempi sbagli
# piu' spesso che con Piper o Kokoro, e che a raccogliere il residuo sia WSOLA.
#
# **Il numero e' 8,6 e prima diceva 10,6.** Il vecchio veniva da tre battute
# (9,0 - 7,9 - 14,8 car/s, media 10,6); questo dalle venticinque battute di una
# scena intera passata dalla catena vera, che e' cio' che il commento di allora
# chiedeva di fare prima di fidarsi. Tre campioni su una quantita' che varia da 7
# a 15 non sono una misura, sono un sorteggio.
#
# **E il confronto che conta e' con gli altri motori**, sulla stessa scena e sullo
# stesso testo: Piper fa 18,3 car/s dove questo ne fa 8,6. Non e' un dettaglio di
# taratura — vuol dire che Qwen produce **il doppio** dell'audio per la stessa
# battuta, e che su una scena fitta non ci sta nemmeno comprimendo al tetto. Si
# veda la tabella in `stream()`.
PASSO = 8.6

# Le voci, che qui sono **descrizioni**. Non c'e' un elenco di timbri da
# rispettare: si scrivono, e il modello prova a costruirle. Sono in italiano
# perche' il modello riceve l'istruzione come un messaggio d'utente qualunque.
VOICES: dict[str, tuple[str, str]] = {
    "qwen-uomo1": ("Un uomo adulto, voce calda e sicura, tono colloquiale.", "m"),
    "qwen-uomo2": ("Un uomo giovane, voce chiara e svelta, un po' nervosa.", "m"),
    "qwen-uomo3": ("Un uomo maturo, voce profonda e roca, parla lentamente.", "m"),
    "qwen-donna1": ("Una donna adulta, voce limpida e cordiale, tono colloquiale.", "f"),
    "qwen-donna2": ("Una donna giovane, voce brillante e svelta.", "f"),
    "qwen-donna3": ("Una donna matura, voce bassa e pacata.", "f"),
    # **Sono otto e non sei di proposito**, come per Kokoro: con `pool_size = 6`
    # ne restano due libere, quindi `voce_neutra` prende la settima e non cade
    # nel ramo di ripiego — quello in cui la voce d'attesa somiglia a quella di
    # un personaggio. La verifica `pool` lo controlla, e l'ha gia' preso.
    "qwen-uomo4": ("Un uomo anziano, voce sottile e un po' tremante.", "m"),
    "qwen-donna4": ("Una donna giovane, voce calda e leggermente roca.", "f"),
}


def _offset_testa(
    audio: np.ndarray, samplerate: int, soglia: float = 0.02, margine: float = 0.03
) -> int | None:
    """Da quale campione comincia il parlato, o `None` se non e' ancora chiaro.

    In streaming il silenzio si toglie solo in **testa**: la coda di un prefisso
    non e' la coda della battuta, e' il punto in cui il modello e' arrivato.

    **E il taglio si decide una volta sola.** La soglia e' relativa al picco, e il
    picco di un prefisso cresce: alla vocale forte del terzo blocco la soglia si
    alza e il primo campione "sopra soglia" si sposta **in avanti**, cioe' oltre
    roba gia' consegnata. Un contatore di campioni che torna indietro e' un pezzo
    di parola perso a ogni giuntura. Quindi si aspetta di avere un picco degno di
    quel nome — se non c'e', si risponde `None` e si consegna comunque nulla,
    perche' quello che c'e' e' silenzio.
    """
    a = np.asarray(audio, dtype=np.float32).reshape(-1)
    if a.size == 0:
        return None
    picco = float(np.abs(a).max())
    if picco < 0.05:  # ancora solo respiro: il taglio non e' deciso
        return None
    forte = np.flatnonzero(np.abs(a) > soglia * picco)
    if forte.size == 0:
        return None
    return max(0, int(forte[0]) - int(margine * samplerate))


def _radice_modello() -> str:
    """Dove sta il modello scaricato. Solleva invece di cercare altrove."""
    trovati = glob.glob(os.path.expanduser(
        "~/.cache/huggingface/hub/models--wavekat--Qwen3-TTS-1.7B-VoiceDesign-ONNX/snapshots/*/"
    ))
    if not trovati:
        raise RuntimeError(
            "modello Qwen3-TTS ONNX non trovato in cache. Scaricarlo con "
            "`huggingface-cli download wavekat/Qwen3-TTS-1.7B-VoiceDesign-ONNX`"
        )
    return trovati[0]


class _Tok:
    """Il minimo di `AutoTokenizer` che lo script usa: `.encode()`."""

    def __init__(self, path: str) -> None:
        from tokenizers import Tokenizer

        self._t = Tokenizer.from_file(os.path.join(path, "tokenizer.json"))

    def encode(self, text: str, add_special_tokens: bool = False):
        return self._t.encode(text, add_special_tokens=add_special_tokens).ids


class QwenTts:
    """Qwen3-TTS ONNX. Le voci sono descrizioni, l'italiano e' nativo."""

    def __init__(
        self,
        samplerate: int = 22050,
        *,
        variante: str = "int4",
        device: str = "auto",
        temperature: float = 0.9,
        top_k: int = 50,
        repetition_penalty: float = 1.05,
        seed: int | None = None,
        blocco_iniziale: int = 2,
        blocco_massimo: int = 32,
        download: bool = True,
    ) -> None:
        self.samplerate = samplerate
        self.variante = variante
        self.device = device
        self.temperature = temperature
        self.top_k = top_k
        self.repetition_penalty = repetition_penalty
        self.seed = seed
        # Il primo blocco e' l'unico che si paga in latenza (2 frame = 160 ms di
        # audio, ~270 ms al primo campione); da li' i blocchi raddoppiano fino a
        # questo tetto, perche' rivocodare il prefisso costa in proporzione alla
        # sua lunghezza. Si veda `stream()`.
        self.blocco_iniziale = blocco_iniziale
        self.blocco_massimo = blocco_massimo
        # Questo backend sa consegnare a pezzi: la catena lo guarda per decidere
        # se puo' programmare una battuta prima di averla tutta.
        self.streaming = True
        self.download = download
        self._G = None
        self._radice = ""
        self._tok: _Tok | None = None
        self._cfg: dict | None = None
        self._emb: dict | None = None
        self._sessioni: dict[str, object] = {}
        self._providers: dict[str, list[str]] = {}

    @property
    def chars_per_second(self) -> float:
        """Il passo di questo motore, nell'unita' di `spoken_length()`.

        Lo dichiara il backend e non la config, perche' ogni motore ha il suo e
        un numero solo per tutti li fa sbagliare tutti. Si veda `PASSO`.
        """
        return PASSO

    # -- caricamento -------------------------------------------------------

    def _provider(self) -> list[str]:
        """Quali provider chiedere. Su CPU questo modello **non e' utilizzabile**.

        La scelta e il precaricamento delle DLL stanno in `core/onnx.py`: qui
        c'era una copia, ed e' esattamente il modo in cui ci sono gia' cascato
        misurando questo stesso modello (4-7 s a battuta riportati come se
        fossero il numero della GPU).
        """
        from core.onnx import provider_voluti

        return provider_voluti(
            self.device,
            chi="qwen",
            costo="secondi a battuta: dal vivo non e' utilizzabile",
        )

    def _motore(self):
        """Carica lo script di riferimento e le sue funzioni d'appoggio.

        Del modulo servono i pezzi *puri* — proiezione del testo, embedding,
        config, campionamento — che sono la parte delicata e che qui non si
        riscrive. Il ciclo autoregressivo invece viene srotolato in `_stato` e
        `_codici`, perche' lo streaming ha bisogno dei frame **mentre** escono e
        una funzione che scrive un WAV non li puo' dare.
        """
        if self._G is not None:
            return self._G

        radice = _radice_modello()

        if "transformers" not in sys.modules:
            finto = types.ModuleType("transformers")
            finto.AutoTokenizer = type(
                "AutoTokenizer", (), {"from_pretrained": staticmethod(lambda p, *a, **k: _Tok(p))}
            )
            sys.modules["transformers"] = finto

        if radice not in sys.path:
            sys.path.insert(0, radice)
        import generate_onnx as G  # noqa: E402

        self._G = G
        self._radice = radice
        return G

    def _sessione(self, nome: str):
        """La sessione ONNX per `<variante>/<nome>.onnx`, costruita una volta sola.

        **La cache e' il punto.** Senza, si ricostruiscono quattro sessioni
        (4,2 GB) a ogni battuta: cinque secondi che non c'entrano niente con la
        sintesi e che nasconderebbero il costo vero.
        """
        import onnxruntime as ort

        radice = _radice_modello()
        percorso = os.path.join(radice, self.variante, f"{nome}.onnx")
        if percorso in self._sessioni:
            return self._sessioni[percorso]

        from core.onnx import verifica_provider

        providers = self._provider()
        o = ort.SessionOptions()
        o.log_severity_level = 3
        o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        s = ort.InferenceSession(percorso, sess_options=o, providers=providers)
        verifica_provider(s, f"qwen/{nome}", providers)
        self._sessioni[percorso] = s
        self._providers[f"{nome}.onnx"] = s.get_providers()
        return s

    @contextlib.contextmanager
    def _presta_sessioni(self):
        """Presta le sessioni gia' caricate a `generate_onnx`, e **solo a lui**.

        Serve alla verifica (`tools/bench_qwen.py --riferimento`), che confronta
        il ciclo srotolato con l'originale. La toppa su `ort.InferenceSession`
        prima era **permanente**: da quel momento in poi *qualunque* sessione del
        processo perdeva i propri `providers` e prendeva quelli di Qwen — cioe'
        ECAPA, che gira su CPU per scelta, sarebbe finita su CUDA senza che
        nessuno l'avesse chiesto. Una toppa globale per un uso locale e' un
        effetto collaterale in attesa di succedere: qui dura il tempo del `with`.
        """
        import onnxruntime as ort

        originale = ort.InferenceSession
        cache = self._sessioni
        providers = self._provider()

        def sessione(path, *a, **k):
            chiave = str(path)
            if chiave not in cache:
                k.pop("providers", None)
                o = ort.SessionOptions()
                o.log_severity_level = 3
                o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                s = originale(chiave, sess_options=o, providers=providers)
                cache[chiave] = s
                self._providers[os.path.basename(chiave)] = s.get_providers()
            return cache[chiave]

        ort.InferenceSession = sessione
        try:
            yield
        finally:
            ort.InferenceSession = originale

    # -- il ciclo autoregressivo, srotolato --------------------------------
    #
    # Questi tre metodi sono la trascrizione fedele di `generate_onnx.py`, spezzata
    # nei suoi tre tempi: il costo fisso (`_stato`), il passo (`_codici`), la resa
    # in onda (`_onda`). **Non e' una riscrittura**, ed e' importante che non lo
    # sia: un campionamento con penalita' di ripetizione e sedici gruppi di codici
    # riscritto a mano produce spazzatura *plausibile*, non un errore.
    #
    # Che sia davvero fedele non e' un'opinione: `tools/bench_qwen.py --riferimento`
    # gira la funzione originale e questa con lo **stesso seme** e confronta i
    # campioni. E' la stessa regola della trasformata contro la propria inversa —
    # si verifica il pezzo nuovo contro qualcosa che si sa gia' giusto, prima di
    # costruirci sopra.

    def _stato(self, text: str, descrizione: str | None, language: str = "italian") -> dict:
        """Il costo fisso: tokenizzazione, embedding del prefill, prefill.

        E' quello che nella misura vale ~200 ms e si paga **una volta** per
        battuta, prima che esca un solo campione.
        """
        G = self._motore()
        radice = self._radice
        # **Config, embedding e tokenizer si caricano una volta.** Erano dentro il
        # corpo, come nell'originale — che li rileggeva da disco a ogni battuta
        # perche' e' uno script da riga di comando e le battute le fa una alla
        # volta. Qui costava: il prefill misurava 525 ms, di cui la maggior parte
        # era `text_embedding.npy` riletto. E' lo stesso difetto delle sessioni
        # ONNX ricostruite a ogni chiamata, un piano piu' in giu'.
        if self._cfg is None:
            self._cfg = G.load_config(radice)
            self._emb = G.load_embeddings(radice)
            self._tok = _Tok(os.path.join(radice, "tokenizer"))
        config, emb, tokenizer = self._cfg, self._emb, self._tok

        text_emb = emb["text_embedding"]
        fc1_w, fc1_b = emb["text_projection_fc1_weight"], emb["text_projection_fc1_bias"]
        fc2_w, fc2_b = emb["text_projection_fc2_weight"], emb["text_projection_fc2_bias"]
        codec_emb = emb["talker_codec_embedding"]
        cp_codec_embs = emb["cp_codec_embeddings"]

        def text_proj(token_ids):
            return G.text_project_numpy(token_ids, text_emb, fc1_w, fc1_b, fc2_w, fc2_b)

        num_layers = config["talker_num_layers"]

        chat_text = f"<|im_start|>assistant\n{text}<|im_end|>\n<|im_start|>assistant\n"
        input_ids = tokenizer.encode(chat_text, add_special_tokens=False)
        instruct_tokens = None
        if descrizione:
            instruct_tokens = tokenizer.encode(
                f"<|im_start|>user\n{descrizione}<|im_end|>\n", add_special_tokens=False
            )

        language_id = config["codec_language_id"].get(language.lower())
        if language_id is not None:
            codec_prefix_ids = [
                config["codec_think_id"], config["codec_think_bos_id"],
                language_id, config["codec_think_eos_id"],
            ]
        else:
            codec_prefix_ids = [
                config["codec_nothink_id"], config["codec_think_bos_id"],
                config["codec_think_eos_id"],
            ]

        tts_pad_embed = text_proj([config["tts_pad_token_id"]])[0]
        tts_bos_embed = text_proj([config["tts_bos_token_id"]])[0]
        tts_eos_embed = text_proj([config["tts_eos_token_id"]])[0]
        codec_pad_embed = codec_emb[config["codec_pad_id"]]
        codec_bos_embed = codec_emb[config["codec_bos_id"]]

        embeds_list = []
        if instruct_tokens is not None:
            embeds_list.append(text_proj(instruct_tokens))
        embeds_list.append(text_proj(input_ids[:3]))
        for cid in codec_prefix_ids:
            embeds_list.append((tts_pad_embed + codec_emb[cid]).reshape(1, -1))
        embeds_list.append((tts_bos_embed + codec_pad_embed).reshape(1, -1))
        for tid in input_ids[3:-5]:
            embeds_list.append((text_proj([tid])[0] + codec_pad_embed).reshape(1, -1))
        embeds_list.append((tts_eos_embed + codec_pad_embed).reshape(1, -1))
        embeds_list.append((tts_pad_embed + codec_bos_embed).reshape(1, -1))

        prefill_embeds = np.concatenate(embeds_list, axis=0)[np.newaxis, :, :].astype(np.float32)
        T = prefill_embeds.shape[1]

        out = self._sessione("talker_prefill").run(None, {
            "inputs_embeds": prefill_embeds,
            "attention_mask": np.ones((1, T), dtype=np.int64),
            "position_ids": np.arange(T).reshape(1, 1, T).repeat(3, axis=0),
        })
        kv = out[2:]
        return {
            "config": config,
            "codec_emb": codec_emb,
            "cp_codec_embs": cp_codec_embs,
            "logits": out[0],
            "hidden_states": out[1],
            "past_keys": np.stack([kv[i * 2] for i in range(num_layers)]),
            "past_values": np.stack([kv[i * 2 + 1] for i in range(num_layers)]),
            "trailing_hidden": tts_pad_embed.reshape(1, -1),
            "pos": T,
        }

    def _codici(self, st: dict, max_new_tokens: int = 2048):
        """Un frame di sedici codici alla volta, finche' il modello non chiude.

        Generatore e non lista: e' l'unica differenza che conta rispetto
        all'originale, e l'unica che rende possibile lo streaming — chi ascolta
        puo' cominciare a vocodare mentre il modello e' ancora al frame otto.
        """
        G = self._G
        config = st["config"]
        codec_emb, cp_codec_embs = st["codec_emb"], st["cp_codec_embs"]
        num_code_groups = config["talker_num_code_groups"]
        cp_num_layers = config["cp_num_layers"]
        cp_num_kv_heads = config["cp_num_kv_heads"]
        cp_head_dim = config["cp_head_dim"]
        vocab_size = config["talker_vocab_size"]
        codec_eos = config["codec_eos_token_id"]

        decode_sess = self._sessione("talker_decode")
        cp_sess = self._sessione("code_predictor")

        suppress_mask = np.zeros(vocab_size, dtype=bool)
        suppress_mask[vocab_size - 1024:vocab_size] = True
        suppress_mask[codec_eos] = False

        logits = st["logits"]
        hidden_states = st["hidden_states"]
        past_keys, past_values = st["past_keys"], st["past_values"]
        trailing_hidden = st["trailing_hidden"]
        current_pos = st["pos"]
        generated_tokens: list[int] = []

        for step in range(max_new_tokens):
            last_logits = logits[0, -1, :].copy()
            last_logits[suppress_mask] = -np.inf
            if step < 2:  # min_new_tokens = 2
                last_logits[codec_eos] = -np.inf

            if self.repetition_penalty != 1.0 and generated_tokens:
                seen = np.array(generated_tokens)
                scores = last_logits[seen]
                last_logits[seen] = np.where(
                    scores > 0, scores / self.repetition_penalty,
                    scores * self.repetition_penalty,
                )

            group0_token = G.sample_top_k(last_logits, self.top_k, self.temperature)
            if group0_token == codec_eos:
                break
            generated_tokens.append(group0_token)

            frame_codes = [group0_token]
            cp_input = np.concatenate(
                [hidden_states[0, -1:, :], codec_emb[group0_token].reshape(1, -1)], axis=0
            )[np.newaxis, :, :].astype(np.float32)
            cp_past_keys = np.zeros(
                (cp_num_layers, 1, cp_num_kv_heads, 0, cp_head_dim), dtype=np.float32
            )
            cp_past_values = np.zeros_like(cp_past_keys)

            for g in range(num_code_groups - 1):
                cp_out = cp_sess.run(None, {
                    "inputs_embeds": cp_input,
                    "generation_steps": np.array([g], dtype=np.int64),
                    "past_keys": cp_past_keys,
                    "past_values": cp_past_values,
                })
                cp_past_keys, cp_past_values = cp_out[1], cp_out[2]
                token = G.sample_top_k(cp_out[0][0, -1, :], self.top_k, self.temperature)
                frame_codes.append(token)
                cp_input = cp_codec_embs[g][token].reshape(1, 1, -1).astype(np.float32)

            yield frame_codes

            next_embed = codec_emb[group0_token].copy()
            for g in range(num_code_groups - 1):
                next_embed = next_embed + cp_codec_embs[g][frame_codes[g + 1]]
            next_embed = (next_embed + trailing_hidden[0]).reshape(1, 1, -1).astype(np.float32)

            decode_out = decode_sess.run(None, {
                "inputs_embeds": next_embed,
                "attention_mask": np.ones((1, current_pos + 1), dtype=np.int64),
                "position_ids": np.array([[[current_pos]]]).repeat(3, axis=0),
                "past_keys": past_keys,
                "past_values": past_values,
            })
            logits, hidden_states = decode_out[0], decode_out[1]
            past_keys, past_values = decode_out[2], decode_out[3]
            current_pos += 1

    def _onda(self, frames: list) -> np.ndarray:
        """Da una sequenza di frame all'onda a 24 kHz."""
        if not frames:
            return np.zeros(0, np.float32)
        codes = np.array(frames, dtype=np.int64).T[np.newaxis, :, :]  # (1, 16, T)
        wav = self._sessione("vocoder").run(None, {"codes": codes})[0].flatten()
        return np.asarray(wav, dtype=np.float32)

    def preload(self, names: list[str]) -> None:
        """Carica i modelli e **verifica di aver ottenuto l'acceleratore**.

        Non basta che la chiamata non sollevi: ORT ripiega in silenzio, ed e' il
        difetto che questo progetto ha gia' pagato due volte."""
        try:
            self.synthesize("Prova.", VoiceSpec(
                voice_id="preload", backend="qwen",
                base_voice=next(iter(VOICES)), semitones=0.0, rate=1.0, gender="?",
            ))
        except Exception as e:  # pragma: no cover - dipende dall'ambiente
            print(f"qwen: precaricamento fallito: {e!r}", file=sys.stderr)
            return
        su_cpu = [n for n, p in self._providers.items() if "CUDAExecutionProvider" not in p]
        if su_cpu:
            print(
                f"qwen: {len(su_cpu)} sessioni su CPU ({', '.join(su_cpu)}): "
                "la latenza sara' di secondi, non di millisecondi.",
                file=sys.stderr,
            )

    # -- sintesi -----------------------------------------------------------

    def _descrizione(self, voice: VoiceSpec) -> str:
        d = VOICES.get(voice.base_voice, (None, "?"))[0]
        if d is None:
            raise ValueError(
                f"voce Qwen sconosciuta: {voice.base_voice!r} (note: {sorted(VOICES)})"
            )
        return d

    def _rifinisci(self, audio: np.ndarray, voice: VoiceSpec, *, taglia=True) -> np.ndarray:
        """Silenzio, semitoni, frequenza: cio' che va fatto **fuori** dal modello.

        `taglia` vale `True` (testa e coda), `"testa"` o `False`. In streaming solo
        la testa: la coda di un prefisso e' il **centro** della battuta, e
        tagliarla li' vorrebbe dire mangiarsi una parola ogni blocco. Il silenzio
        finale vero lo toglie chi chiude, o resta — e un respiro di troppo in
        fondo costa molto meno di una sillaba in meno in mezzo.
        """
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if taglia == "testa":
            audio = _taglia_testa(audio, NATIVE_RATE)
        elif taglia:
            audio = taglia_silenzio(audio, NATIVE_RATE)
        if audio.size and voice.semitones:
            audio = pitch_shift(audio, voice.semitones, samplerate=NATIVE_RATE)
        if NATIVE_RATE != self.samplerate:
            audio = resample(audio, NATIVE_RATE, self.samplerate)
        return audio

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        """La battuta intera. `first_sample_ms` e' il totale, e non e' un refuso:
        senza streaming il primo campione esiste quando esiste tutto.

        Chi vuole il primo campione prima usa `stream()`, che e' l'unico posto in
        cui quel numero significa qualcosa.
        """
        text = text.strip()
        if not text:
            return Speech(np.zeros(0, np.float32), self.samplerate, voice.voice_id, text=text)

        if self.seed is not None:
            np.random.seed(self.seed)
        t0 = time.perf_counter()
        st = self._stato(text, self._descrizione(voice))
        audio = self._rifinisci(self._onda(list(self._codici(st))), voice)
        total_ms = (time.perf_counter() - t0) * 1000.0

        return Speech(
            audio=audio,
            samplerate=self.samplerate,
            voice_id=voice.voice_id,
            first_sample_ms=total_ms,
            total_ms=total_ms,
            text=text,
        )

    def stream(self, text: str, voice: VoiceSpec, rate: float = 1.0, max_seconds: float = 0.0):
        """La battuta a pezzi, mentre esce. **E' il motivo per cui questo motore
        esiste dal vivo.**

        Genera `(audio, finita)` a blocchi. Il primo arriva dopo ~270 ms invece
        che dopo ~4,9 s, ed e' tutta la differenza fra un motore da banco e un
        motore da gioco.

        ## Si vocoda il prefisso, non il blocco, e questo e' misurato

        `tools/bench_qwen.py --vocoder` ha chiesto al vocoder le due cose che si
        potevano volere, e ha risposto in modo netto:

            vocoder(codici[:k])   contro l'intero   corr 1,0000   err rms 0,0003
            vocoder(codici[a:b])  contro l'intero   corr 0,95     err rms 0,33

        Il **prefisso** e' trasparente: i primi k frame vocodati da soli danno
        esattamente i campioni che darebbe la battuta intera, anche senza guardia
        ai bordi. Il **blocco interno** no — quel vocoder ha bisogno del suo
        contesto a sinistra, e senza si inventa i primi millisecondi.

        Quindi ogni volta si rivocoda tutto dall'inizio e si tiene solo la coda
        nuova. Costa, e il costo e' quello che decide il ritmo dei blocchi.

        ## I blocchi raddoppiano, e non e' un'ottimizzazione prematura

        Rivocodare il prefisso costa `35 ms + 0,9 ms per frame` (misurato). Un
        blocco di `b` frame consegna `b * 80 ms` di audio: perche' lo streaming
        stia dietro serve `21 ms * b > 35 + 0,9 * k`, cioe' **il blocco deve
        crescere insieme alla battuta**. A blocchi fissi da 2 frame una battuta di
        79 frame paga 40 rivocodifiche — 2,4 s in piu' — e lo streaming non regge.
        Raddoppiando (2, 4, 8, 16, 32...) le rivocodifiche diventano sei e il
        costo totale 384 ms, cioe' 0,79x tempo reale: sta avanti.

        Il primo blocco resta piccolo perche' e' l'unico che si paga in latenza;
        gli altri si pagano in margine, e di margine ce n'e'.

        ## `max_seconds`, che non e' una rifinitura

        Questo modello **si incanta**. Misurato su una scena di venticinque
        battute: `'Toc toc, negri!'` — quindici caratteri, poco piu' di un secondo
        di parlato — ha prodotto **9,12 secondi** di audio. Non e' lentezza, e'
        il ciclo autoregressivo che entra in un giro e ci resta; `max_new_tokens`
        vale 2048, cioe' due minuti e mezzo, che come rete di sicurezza dal vivo
        non e' una rete.

        Il taglio e' un difetto — una battuta mozzata — ma e' un difetto piccolo
        accanto a quello che sostituisce: nove secondi di voce su una battuta da
        uno tengono occupata l'unica voce disponibile per tutto quel tempo, e le
        battute vere che arrivano intanto o si accavallano o slittano. Chi chiama
        passa un tetto **largo** (tre volte la previsione), cosi' scatta solo sul
        giro incantato e mai su una frase lunga.
        """
        text = text.strip()
        if not text:
            yield np.zeros(0, np.float32), True
            return

        if self.seed is not None:
            np.random.seed(self.seed)
        st = self._stato(text, self._descrizione(voice))

        frames: list = []
        emessi = 0  # campioni gia' consegnati, **dopo** la rifinitura
        taglio: int | None = None
        prossimo = max(1, self.blocco_iniziale)

        def fin_qui():
            """Tutta la battuta fin qui, rifinita, e il taglio in testa deciso.

            **Si rifinisce il prefisso intero e si affetta**, invece di rifinire
            il blocco. Sembra spreco e non lo e': ricampionare da 24000 a 22050
            un blocco alla volta lascia a ogni giuntura una frazione di campione
            in piu' o in meno, e spostare i semitoni a pezzi impasta i bordi.
            Rifinendo il prefisso, cio' che si consegna e' **per costruzione**
            identico a cio' che la battuta intera avrebbe avuto in quel punto —
            la stessa proprieta' che la prova del vocoder ha verificato un piano
            piu' sotto. Costa un `interp` su qualche decina di migliaia di
            campioni: rumore, accanto ai 59 ms di un frame.
            """
            nonlocal taglio
            grezza = self._onda(frames)
            if taglio is None:
                taglio = _offset_testa(grezza, NATIVE_RATE)
            if taglio is None:
                return np.zeros(0, np.float32)
            return self._rifinisci(grezza[taglio:], voice, taglia=False)

        def parlato(onda: np.ndarray) -> int:
            """Fin dove arriva il **parlato** in questo prefisso.

            **Il silenzio in coda non si consegna, e questa non e' cosmetica.**
            `synthesize` lo toglie con `taglia_silenzio` da sempre, e il ramo in
            streaming non lo ereditava: misurato su una scena di venticinque
            battute, Qwen consegnava **100 secondi di parlato per 49 di scena**,
            passo apparente 6,5 caratteri al secondo contro gli 11-15 che lo
            stesso motore fa da solo. Meta' dell'uscita era imbottitura, e la
            catena non la sa distinguere dal parlato: misura una durata, la trova
            piu' lunga della finestra, e chiede fretta. Si accelerava del
            silenzio, pagandolo in parole — lo stesso difetto che SuperTonic ha
            gia' fatto pagare una notte.

            In streaming non si puo' tagliare dopo: quello che e' uscito e'
            uscito. Si **trattiene** invece — il silenzio in fondo al prefisso
            resta indietro, e se poi il modello riprende a parlare esce insieme al
            resto (era una pausa); se invece il modello chiude, non esce affatto
            (era imbottitura). La differenza fra le due si conosce solo dopo, ed
            e' esattamente per questo che la decisione va rimandata.
            """
            if onda.size == 0:
                return 0
            picco = float(np.abs(onda).max())
            if picco <= 0.0:
                return 0
            forte = np.flatnonzero(np.abs(onda) > 0.02 * picco)
            if forte.size == 0:
                return 0
            return min(len(onda), int(forte[-1]) + 1 + int(0.03 * self.samplerate))

        # Il tetto in frame. Un frame vale 80 ms, e `0` vuol dire nessun tetto —
        # che e' giusto sul banco, dove una battuta lunga non fa danno a nessuno.
        tetto = int(max_seconds * NATIVE_RATE / 1920) if max_seconds > 0 else 0

        for f in self._codici(st):
            frames.append(f)
            if tetto and len(frames) >= tetto:
                print(
                    f"qwen: battuta troncata a {max_seconds:.1f}s, il modello non "
                    f"chiudeva ({text[:40]!r})",
                    file=sys.stderr,
                )
                break
            if len(frames) < prossimo:
                continue
            onda = fin_qui()
            fin_dove = parlato(onda)
            if fin_dove > emessi:
                blocco, emessi = onda[emessi:fin_dove], fin_dove
                yield blocco, False
            prossimo = min(len(frames) * 2, len(frames) + self.blocco_massimo)

        onda = fin_qui()
        # In chiusura il silenzio trattenuto era imbottitura: non esce.
        yield onda[emessi : max(emessi, parlato(onda))], True

    def synthesize_riferimento(self, text: str, voice: VoiceSpec) -> Speech:
        """La stessa battuta, fatta girare dalla funzione **originale** del modello.

        Non serve alla catena: serve a `tools/bench_qwen.py --riferimento`, che
        confronta i campioni per stabilire se il ciclo srotolato qui sopra e'
        fedele. Un ciclo autoregressivo trascritto a mano che *quasi* coincide
        produce parlato plausibile e sbagliato, e nessun contatore lo direbbe.
        """
        import soundfile as sf
        import tempfile

        G = self._motore()
        if self.seed is not None:
            np.random.seed(self.seed)
        t0 = time.perf_counter()
        with self._presta_sessioni(), tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "out.wav")
            G.generate_onnx(
                model_dir=self._radice,
                variant=self.variante,
                text=text.strip(),
                instruct=self._descrizione(voice),
                language="italian",
                output_path=dest,
                max_new_tokens=2048,
                temperature=self.temperature,
                top_k=self.top_k,
                repetition_penalty=self.repetition_penalty,
                seed=None,  # il seme lo mettiamo noi, per partire dallo stesso stato
            )
            audio, sr = sf.read(dest, dtype="float32", always_2d=False)
        total_ms = (time.perf_counter() - t0) * 1000.0
        return Speech(
            audio=self._rifinisci(audio, voice),
            samplerate=self.samplerate,
            voice_id=voice.voice_id,
            first_sample_ms=total_ms,
            total_ms=total_ms,
            text=text,
        )
