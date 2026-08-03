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

import glob
import os
import sys
import tempfile
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
# **E' il piu' incerto dei quattro, e va detto.** Misurato su tre battute:
# 9,0 - 7,9 - 14,8 car/s, media 10,6. Gli altri motori hanno uno scarto di
# qualche punto percentuale; qui il rapporto fra la piu' lenta e la piu' veloce
# e' quasi due. Il motivo e' strutturale: questo modello **campiona** (con
# `temperature` e `top_k`), quindi la durata non e' una funzione del testo — e'
# una variabile casuale. Chi lo usa deve aspettarsi che la previsione dei tempi
# sbagli piu' spesso che con Piper o Kokoro, e che a raccogliere il residuo sia
# WSOLA. Prima di fidarsi di questo numero, rimisurarlo su una scena intera.
PASSO = 10.6

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
        seed: int | None = None,
        download: bool = True,
    ) -> None:
        self.samplerate = samplerate
        self.variante = variante
        self.device = device
        self.temperature = temperature
        self.top_k = top_k
        self.seed = seed
        self.download = download
        self._G = None
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

        La stessa cura di `speak/backends/kokoro.py`: senza `preload_dlls()` le
        DLL CUDA dei pacchetti pip `nvidia-*` non si trovano e ORT ripiega sulla
        CPU **senza dirlo**. Ci sono gia' cascato misurando questo stesso
        modello: 4-7 s a battuta riportati come se fossero il numero della GPU.
        """
        import onnxruntime as rt

        if hasattr(rt, "preload_dlls"):
            rt.preload_dlls()
        disponibili = rt.get_available_providers()
        if (self.device or "auto").lower() == "cpu":
            return ["CPUExecutionProvider"]
        if "CUDAExecutionProvider" in disponibili:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if (self.device or "").lower() == "cuda":
            raise RuntimeError(
                "tts.device=cuda ma CUDAExecutionProvider non e' disponibile"
            )
        print(
            "qwen: CUDA non disponibile, si ripiega sulla CPU — questo motore li'"
            " costa secondi a battuta e non e' utilizzabile dal vivo.",
            file=sys.stderr,
        )
        return ["CPUExecutionProvider"]

    def _motore(self):
        """Carica lo script di riferimento, con le sessioni tenute in cache.

        **La cache e' il punto.** Senza, `generate_onnx` ricostruisce quattro
        sessioni ONNX (4,2 GB) a ogni battuta: cinque secondi che non c'entrano
        niente con la sintesi e che nasconderebbero il costo vero.
        """
        if self._G is not None:
            return self._G

        import onnxruntime as ort

        providers = self._provider()
        radice = _radice_modello()

        if "transformers" not in sys.modules:
            finto = types.ModuleType("transformers")
            finto.AutoTokenizer = type(
                "AutoTokenizer", (), {"from_pretrained": staticmethod(lambda p, *a, **k: _Tok(p))}
            )
            sys.modules["transformers"] = finto

        originale = ort.InferenceSession
        cache, prov = self._sessioni, self._providers

        def sessione(path, *a, **k):
            chiave = str(path)
            if chiave not in cache:
                k.pop("providers", None)
                o = ort.SessionOptions()
                o.log_severity_level = 3
                o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                s = originale(chiave, sess_options=o, providers=providers)
                cache[chiave] = s
                prov[os.path.basename(chiave)] = s.get_providers()
            return cache[chiave]

        ort.InferenceSession = sessione
        if radice not in sys.path:
            sys.path.insert(0, radice)
        import generate_onnx as G  # noqa: E402

        self._G = G
        self._radice = radice
        return G

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

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        """La battuta **intera**: qui non c'e' streaming, e va detto.

        `first_sample_ms` e' dichiarato pari al totale, perche' il primo campione
        esiste quando esiste tutto. Riportare qui il numero dello streaming
        (~320 ms) sarebbe una promessa che questo codice non mantiene, e la
        catena lo userebbe per pianificare una finestra che non ha.
        """
        text = text.strip()
        if not text:
            return Speech(np.zeros(0, np.float32), self.samplerate, voice.voice_id, text=text)

        G = self._motore()
        descrizione = VOICES.get(voice.base_voice, (None, "?"))[0]
        if descrizione is None:
            raise ValueError(
                f"voce Qwen sconosciuta: {voice.base_voice!r} (note: {sorted(VOICES)})"
            )

        import soundfile as sf

        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "out.wav")
            G.generate_onnx(
                model_dir=self._radice,
                variant=self.variante,
                text=text,
                instruct=descrizione,
                language="italian",
                output_path=dest,
                max_new_tokens=2048,
                temperature=self.temperature,
                top_k=self.top_k,
                repetition_penalty=1.05,
                seed=self.seed,
            )
            audio, sr = sf.read(dest, dtype="float32", always_2d=False)
        total_ms = (time.perf_counter() - t0) * 1000.0

        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        audio = taglia_silenzio(audio, sr or NATIVE_RATE)
        if audio.size and voice.semitones:
            audio = pitch_shift(audio, voice.semitones, samplerate=sr or NATIVE_RATE)
        if (sr or NATIVE_RATE) != self.samplerate:
            audio = resample(audio, sr or NATIVE_RATE, self.samplerate)

        return Speech(
            audio=audio,
            samplerate=self.samplerate,
            voice_id=voice.voice_id,
            first_sample_ms=total_ms,
            total_ms=total_ms,
            text=text,
        )
