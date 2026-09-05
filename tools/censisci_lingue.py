"""Il censimento delle **combinazioni**: ogni lingua per ogni motore, e cosa
succede davvero.

    python -m tools.censisci_lingue                 # la matrice, senza rete e senza modelli
    python -m tools.censisci_lingue --guai          # solo le righe che non tornano
    python -m tools.censisci_lingue --fonemi        # fonemizza e conta cosa viene buttato
    python -m tools.censisci_lingue --sintesi       # sintetizza e misura car/s e picco

Il programma dichiara 53 lingue parlate, 133 tradotte e 3 motori. Ogni
combinazione che si puo' scegliere dalla finestra e' una promessa, e il difetto
tipico di questo repo non e' un errore: e' una combinazione che **funziona a
meta' e non lo dice**.

## Le tre domande, e sono diverse

**1. Esiste una voce?** Si risponde leggendo i cataloghi (`speak/pool.py`), che
e' quello che fa gia' `tools/censisci_voci.py`. Qui si aggiunge il passaggio che
manca: la lingua non arriva dal catalogo, arriva **dal menu**, in codici Google
(`translate/lingue.py`). `iw` e `he` sono la stessa lingua e i due elenchi ne
conoscono uno per uno, quindi una lingua puo' avere una voce e non essere
raggiungibile — o essere raggiungibile solo scrivendola a mano.

**2. Il g2p e' quello giusto?** E' la domanda che ha tolto il giapponese a
espeak. Il metro non e' «quanti fonemi per carattere»: con quello il cinese
sembrava sano mentre perdeva i toni. Il metro e' **quanti simboli lo stadio
successivo butta via in silenzio**, e ognuno dei tre motori ha il suo:

| motore | chi butta | come |
|---|---|---|
| kokoro | `Tokenizer.phonemize` | `filter(lambda p: p in self.vocab, …)` |
| piper | `phoneme_ids.phonemes_to_ids` | `if phoneme not in id_map: continue` (piu' un `logging.warning`) |
| supertonic | `UnicodeProcessor.__call__` | `self.indexer[ord(c)]`, che vale **-1** per i caratteri non supportati — cioe' l'ultima riga dell'embedding, non un errore |

Sono tre meccanismi diversi che fanno la stessa cosa: consegnano audio
plausibile fatto con i simboli sbagliati, senza sollevare e senza contatori.

**3. Il passo e' misurato o e' un ripiego?** `PASSO_LINGUA` di ogni backend dice
quanto parla in fretta in quella lingua; le lingue che non ci sono ricadono sul
numero **italiano**, e questo progetto ha gia' pagato sei volte la stessa unita'
applicata a un'altra distribuzione. Qui «ripiego» e' scritto, non dedotto.

## Cosa questo strumento non fa

Non giudica la **pronuncia**: nessuno ha ascoltato cinquantatre lingue, e dirlo
sarebbe una promessa che nessuna misura regge. Dichiara che una voce esiste, che
il suo g2p e' quello dichiarato e che nulla viene buttato per strada — tre cose
meccaniche. Una fonemizzazione fatta con le regole giuste puo' ancora suonare
male, e questo censimento non lo vedrebbe.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MOTORI: tuple[str, ...] = ("piper", "supertonic", "kokoro")

# I codici dei guai. Codici e non frasi, per la stessa ragione di
# `core.motore.INVARIATO`: la verifica non deve dipendere da come e' scritta una
# riga italiana, che cambia.
FUORI_MENU = "fuori_menu"            # il catalogo la parla, il menu non la sa chiedere
G2P_IGNOTO = "g2p_ignoto"            # il tipo di fonemi non e' fra quelli installati
PASSO_RIPIEGO = "passo_ripiego"      # nessun numero misurato: si usa l'italiano
PASSO_SOTTO = "passo_sotto_minimo"   # il passo dichiarato e' sotto la soglia del banco
SENZA_FRASE = "senza_frase"          # non c'e' una frase di prova: non misurabile
DUE_ACCENTI = "due_accenti"          # voci di due accenti, un fonemizzatore solo
SCARTI = "scarti"                    # lo stadio dopo butta simboli in silenzio


@dataclass(frozen=True, slots=True)
class Cella:
    """Una combinazione lingua x motore, come la descrive il **codice**."""

    lingua: str
    motore: str
    voci: int
    g2p: str
    passo: float
    misurato: bool
    guai: tuple[str, ...] = ()


@dataclass
class Riga:
    """Una lingua, con le sue tre celle e quello che il menu ne sa."""

    codice: str            # il codice del catalogo (due lettere)
    menu: tuple[str, ...]  # i codici del menu che ci arrivano (puo' essere vuoto)
    celle: dict[str, Cella] = field(default_factory=dict)

    @property
    def guai(self) -> tuple[str, ...]:
        fuori = [] if self.menu else [FUORI_MENU]
        for c in self.celle.values():
            fuori.extend(c.guai)
        return tuple(dict.fromkeys(fuori))


# ------------------------------------------------------------ la matrice --


def _g2p_piper(lingua: str) -> tuple[str, tuple[str, ...]]:
    """Che fonemizzatore userebbero le voci Piper di quella lingua.

    Il tipo sta nel `.onnx.json` di ogni voce e il catalogo lo ricorda in
    `SPECIALI`; qui si confronta con quelli che il `piper-tts` **installato** sa
    davvero costruire. E' un confronto e non una lettura: `FONEMI_OK` dichiara
    `hebrew` fra i tipi validi, e `piper-tts 1.3.0` non ce l'ha.
    """
    from speak.backends.piper_voci import SPECIALI, voci_per

    voci = voci_per(lingua, 6)
    if not voci:
        return "", ()
    tipi = tuple(dict.fromkeys(SPECIALI.get(v.split("#")[0], "espeak") for v in voci))
    try:
        from piper.config import PhonemeType

        noti = {e.value for e in PhonemeType}
    except Exception:  # pragma: no cover - dipende dall'ambiente
        noti = {"espeak", "text"}
    ignoti = tuple(t for t in tipi if t not in noti)
    return "+".join(tipi), ignoti


def _g2p_kokoro(lingua: str) -> tuple[str, tuple[str, ...]]:
    """Il g2p di Kokoro per quella lingua, e gli accenti che gli passano sotto.

    `FONEMI_LINGUA` ha **una** riga per lingua e le voci ne dichiarano due:
    `_PREFISSI` dice `a -> en-us` e `b -> en-gb`, ma la tabella si costruisce con
    una comprensione in cui l'ultima vince, quindi l'inglese e' `en-us` per tutte
    e ventotto le voci — otto delle quali sono britanniche, e due di quelle otto
    stanno fra le sei `PREFERITE`.
    """
    from speak.backends.kokoro import (
        FONEMI_LINGUA, G2P_ESTERNO, PER_LINGUA, VOICES, _PREFISSI,
    )

    if lingua in G2P_ESTERNO:
        return G2P_ESTERNO[lingua].rsplit(".", 1)[-1], ()
    codice = FONEMI_LINGUA.get(lingua, "")
    voluti = {_PREFISSI[VOICES[c][0][0]][1] for c in PER_LINGUA.get(lingua, ())}
    scartati = tuple(sorted(v for v in voluti if v != codice))
    return codice, scartati


def matrice(solo: tuple[str, ...] = ()) -> list[Riga]:
    """La matrice completa, **ricavata dal codice**. Niente rete, niente modelli.

    Il perno e' il codice del catalogo (due lettere) e non quello del menu,
    perche' due codici del menu possono finire sulla stessa lingua (`zh-CN` e
    `zh-TW`) e un codice del catalogo puo' non averne nessuno (`he`, che nel menu
    e' `iw`). Contarle dal menu darebbe 53 in tutti e due i casi e nasconderebbe
    esattamente la riga che conta.
    """
    from core.banco import PASSO_MINIMO
    from speak.frasi import frase
    from speak.pool import basi_per, famiglia_lingua, lingue_con_voce
    from translate.lingue import PER_CODICE

    da_menu: dict[str, list[str]] = {}
    for codice in sorted(PER_CODICE):
        da_menu.setdefault(famiglia_lingua(codice), []).append(codice)

    lingue = sorted(set().union(*(set(lingue_con_voce(m)) for m in MOTORI)))
    if solo:
        lingue = [x for x in lingue if x in solo]

    fuori: list[Riga] = []
    for lingua in lingue:
        riga = Riga(codice=lingua, menu=tuple(da_menu.get(lingua, ())))
        for motore in MOTORI:
            voci = basi_per(motore, lingua)
            if not voci:
                continue
            guai: list[str] = []
            if motore == "piper":
                from speak.backends.piper import PASSO_LINGUA as TAB
                g2p, ignoti = _g2p_piper(lingua)
                if ignoti:
                    guai.append(G2P_IGNOTO)
            elif motore == "kokoro":
                from speak.backends.kokoro import PASSO_LINGUA as TAB
                g2p, scartati = _g2p_kokoro(lingua)
                if scartati:
                    guai.append(DUE_ACCENTI)
            else:
                from speak.backends.supertonic import LINGUE, PASSO_LINGUA as TAB
                g2p = "unicode" if lingua in LINGUE else ""
            passo = _passo(motore, lingua)
            if lingua not in TAB:
                guai.append(PASSO_RIPIEGO)
            if passo < PASSO_MINIMO:
                guai.append(PASSO_SOTTO)
            if not frase(lingua):
                guai.append(SENZA_FRASE)
            riga.celle[motore] = Cella(lingua, motore, len(voci), g2p, passo,
                                       lingua in TAB, tuple(guai))
        fuori.append(riga)
    return fuori


def _passo(motore: str, lingua: str) -> float:
    """Il passo che la catena userebbe davvero per quella coppia.

    Si chiede al backend invece di leggere la tabella: Kokoro e SuperTonic lo
    dichiarano come **prodotto** con `speed`, e leggere solo `PASSO_LINGUA`
    darebbe un numero che nessuno usa.
    """
    from core.config import Config

    cfg = Config().tts
    if motore == "piper":
        from speak.backends.piper import PiperTts

        return PiperTts(download=False, lingua=lingua).chars_per_second
    if motore == "kokoro":
        from speak.backends.kokoro import KokoroTts

        return KokoroTts(download=False, lingua=lingua,
                         speed=cfg.kokoro_speed).chars_per_second
    from speak.backends.supertonic import SupertonicTts

    return SupertonicTts(download=False, lingua=lingua, speed=cfg.speed).chars_per_second


# ------------------------------------------------- quanto viene buttato --


def scarti_kokoro(lingua: str, testo: str) -> tuple[int, int, str]:
    """Quanti simboli il vocabolario di Kokoro butta via, e quali.

    E' il metro che ha preso il giapponese e poi il cinese, dove il rapporto
    fonemi/carattere diceva «sano». Torna `(crudi, persi, quali)`.
    """
    from kokoro_onnx.config import DEFAULT_VOCAB
    from speak.backends.kokoro import FONEMI_LINGUA, G2P_ESTERNO

    if lingua in G2P_ESTERNO:
        from importlib import import_module

        modulo = import_module(G2P_ESTERNO[lingua])
        crudi, _ = modulo._motore()(testo)
    else:
        import phonemizer

        _espeak_di_kokoro()  # senza, `phonemize` risponde «espeak not installed»
        crudi = phonemizer.phonemize(testo, FONEMI_LINGUA.get(lingua, lingua),
                                     preserve_punctuation=True, with_stress=True)
    persi = [c for c in crudi if c not in DEFAULT_VOCAB]
    return len(crudi), len(persi), "".join(sorted(set(persi)))


def scarti_piper(lingua: str, testo: str, scarica: bool = False
                 ) -> tuple[int, int, str]:
    """Lo stesso per Piper, **senza scaricare i pesi**.

    Del modello serve solo il `.onnx.json` (7 KB): dentro ci sono il tipo di
    fonemi, la voce espeak e la `phoneme_id_map`, cioe' tutto quello che decide
    cosa viene buttato. Scaricare cinquanta modelli da 28-114 MB per rispondere a
    questa domanda sarebbe pagare tre giga per leggere tre campi.
    """
    from piper.phonemize_espeak import ESPEAK_DATA_DIR, EspeakPhonemizer
    from speak.backends.piper import MODELS_DIR, REPO
    from speak.backends.piper_voci import sottopercorso, voci_per

    voci = voci_per(lingua, 1)
    if not voci:
        raise RuntimeError(f"piper non ha voci per «{lingua}»")
    chiave = voci[0].split("#")[0]
    sub = sottopercorso(chiave)
    locale = MODELS_DIR / sub / f"{chiave}.onnx.json"
    if not locale.exists():
        if not scarica:
            raise FileNotFoundError(f"manca {locale} (si prende con --scarica)")
        from huggingface_hub import hf_hub_download

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        hf_hub_download(REPO, f"{sub}/{chiave}.onnx.json", local_dir=MODELS_DIR)
    dati = json.loads(locale.read_text(encoding="utf-8"))
    tipo = dati.get("phoneme_type", "espeak")
    if tipo != "espeak":
        # `text` fonemizza in codepoint e gli altri due tipi non esistono nel
        # pacchetto installato: in tutti e tre i casi questo conto non e' quello
        # che gira, e dirlo e' meglio che dare un numero.
        raise RuntimeError(f"phoneme_type «{tipo}»: non si fonemizza con espeak")
    voce = dati.get("espeak", {}).get("voice", lingua)
    mappa = dati["phoneme_id_map"]
    fonemi = [p for frase in EspeakPhonemizer(ESPEAK_DATA_DIR).phonemize(voce, testo)
              for p in frase]
    persi = [p for p in fonemi if p not in mappa]
    return len(fonemi), len(persi), "".join(sorted(set(persi)))


def scarti_supertonic(lingua: str, testo: str) -> tuple[int, int, str]:
    """E per SuperTonic, dove non si butta: si **sbaglia riga**.

    `UnicodeProcessor.__call__` fa `self.indexer[ord(c)]`, e l'indice vale `-1`
    per i caratteri che il modello non conosce: in numpy `-1` e' l'**ultima**
    riga dell'embedding, quindi un carattere non supportato diventa un altro
    token invece di sparire. E oltre `len(indexer)` (65536) l'accesso solleva a
    meta' sessione.
    """
    tp = _processore_supertonic()
    pre = tp._preprocess_text(testo, lingua if lingua in _lingue_supertonic() else "na")
    persi = [c for c in pre if c not in tp.supported_character_set]
    oltre = [c for c in pre if ord(c) >= len(tp.indexer)]
    return len(pre), len(persi) + len(oltre), "".join(sorted(set(persi + oltre)))


def _lingue_supertonic() -> tuple[str, ...]:
    from speak.backends.supertonic import LINGUE

    return LINGUE


@lru_cache(maxsize=1)
def _processore_supertonic():
    """Il processore di testo di SuperTonic, aperto una volta sola.

    Costruire la `TTS` apre quattro sessioni ONNX: farlo per ognuna delle
    trentuno lingue vorrebbe dire misurare l'apertura invece della
    fonemizzazione.
    """
    import supertonic

    return supertonic.TTS(auto_download=True).model.text_processor


@lru_cache(maxsize=1)
def _espeak_di_kokoro() -> None:
    """Il `Tokenizer` di kokoro esiste per il suo effetto collaterale: imposta le
    vie di espeak-ng. Senza, `phonemizer.phonemize` risponde «espeak not
    installed» anche con i binari nel venv."""
    from kokoro_onnx.tokenizer import Tokenizer

    Tokenizer()


SCARTI_PER_MOTORE = {
    "kokoro": scarti_kokoro,
    "piper": scarti_piper,
    "supertonic": scarti_supertonic,
}


# ------------------------------------------------------------- la sintesi --


def misura(motore: str, lingue: tuple[str, ...], tutte_le_voci: bool = False
           ) -> list[tuple]:
    """Sintetizza davvero e misura car/s e picco, una lingua alla volta.

    **Un motore per lingua**, come `tools/censisci_voci.py`: la lingua non e' un
    argomento di `synthesize`, e' una cosa che il motore sa di se stesso.

    ## Perche' si misurano **tutte** le voci del pool, e non la prima

    La prima versione ne prendeva una — la prima che `build_pool` restituisce —
    e da li' e' uscita una tabella di passi che sembrava una misura per lingua.
    Non lo era: su Piper la stessa frase greca fa **8,56 car/s con `joy` e 15,59
    con `rapunzelina`**, e il russo va da 7,98 (`irina`) a 14,77 (`dmitri`).
    Cioe' fra due voci della **stessa** lingua ci sono l'ottanta per cento di
    differenza, tanto quanto fra due lingue diverse — e quale voce sia la prima
    dipende dall'ordine del catalogo, non da niente di misurato.

    `chars_per_second` invece e' **uno per lingua** e vale per tutto il pool: la
    quantita' che descrive e' quindi la mediana delle voci, non una di esse. E
    l'escursione va stampata, se no una mediana su voci che non sono d'accordo
    si legge come una taratura — che e' la forma «il numero non e' tarato, e'
    vinto» gia' scritta in questo repo per le soglie.

    Costa piu' tempo e piu' disco (su Piper ogni voce e' un modello suo), ma e'
    la differenza fra un numero e un numero con un intervallo. Con `--prima` si
    torna a una voce sola, per una passata veloce.
    """
    import numpy as np

    from core.config import Config
    from fuse.timing import spoken_length
    from speak.base import make_tts, taglia_silenzio
    from speak.frasi import frase
    from speak.pool import build_pool

    fuori = []
    for lingua in lingue:
        testo = frase(lingua)
        if not testo:
            fuori.append((motore, lingua, None, None, None, 0, 0.0,
                          "nessuna frase di prova"))
            _stampa(fuori[-1])
            continue
        cfg = Config()
        cfg.tts.backend = motore
        try:
            tts = make_tts(cfg.tts, lingua=lingua, preload=False)
            quante = 6 if tutte_le_voci else 1
            voci = build_pool(None, quante, backend=motore, lingua=lingua)
            # Il pool ripete le voci quando sono meno di `quante` (cambiando i
            # semitoni): qui interessano le **basi**, che sono i modelli veri.
            viste: set[str] = set()
            passi: list[float] = []
            picchi: list[float] = []
            tempi: list[float] = []
            for v in voci:
                if v.base_voice in viste or v.semitones or v.rate != 1.0:
                    continue
                viste.add(v.base_voice)
                t0 = time.perf_counter()
                s = tts.synthesize(testo, v)
                tempi.append((time.perf_counter() - t0) * 1000.0)
                audio = taglia_silenzio(np.asarray(s.audio), s.samplerate)
                secondi = len(audio) / float(s.samplerate)
                passi.append(spoken_length(testo) / secondi if secondi else 0.0)
                picchi.append(float(np.abs(audio).max()) if audio.size else 0.0)
            passo = statistics.median(passi)
            picco = max(picchi)
            # L'escursione fra le voci, in percentuale della mediana. Sotto c'e'
            # una lingua; sopra c'e' una lingua **e** delle voci che non sono
            # d'accordo, e il numero solo non lo direbbe.
            spread = 100.0 * (max(passi) - min(passi)) / passo if passo else 0.0
            nota = "" if 4.0 <= passo <= 20.0 else "PASSO FUORI FASCIA"
            if picco <= 0.001:
                nota = (nota + " MUTO").strip()
            if spread > 25.0:
                nota = (nota + " VOCI IN DISACCORDO").strip()
            fuori.append((motore, lingua, passo, picco,
                          statistics.median(tempi), len(passi), spread, nota))
        except Exception as e:  # noqa: BLE001 - qui si censisce, non si corregge
            fuori.append((motore, lingua, None, None, None, 0, 0.0,
                          f"{type(e).__name__}: {str(e).splitlines()[0][:70]}"))
        _stampa(fuori[-1])
    return fuori


def _stampa(r) -> None:
    passo = f"{r[2]:.2f} car/s" if r[2] else "—"
    picco = f"picco {r[3]:.3f}" if r[3] else ""
    ms = f"{r[4]:.0f} ms" if r[4] else ""
    voci = f"{r[5]}v ±{r[6]:4.1f}%" if r[5] else ""
    print(f"  {r[1]:4} {passo:>12}  {voci:>11}  {picco:>11}  {ms:>8}  {r[7]}",
          flush=True)


# ------------------------------------------------------------------ CLI --


def _stampa_matrice(righe: list[Riga], solo_guai: bool) -> None:
    print(f"{'ling':4} {'menu':10} "
          + "  ".join(f"{m[:4]:>22}" for m in MOTORI) + "   guai")
    for r in righe:
        if solo_guai and not r.guai:
            continue
        celle = []
        for m in MOTORI:
            c = r.celle.get(m)
            if c is None:
                celle.append(f"{'—':>22}")
            else:
                marchio = "" if c.misurato else "~"
                celle.append(f"{c.voci:2}v {c.g2p[:9]:<9} {marchio}{c.passo:5.1f}")
        menu = ",".join(r.menu) or "(nessuno)"
        print(f"{r.codice:4} {menu[:10]:10} " + "  ".join(celle)
              + "   " + " ".join(r.guai))
    print("\n`~` davanti al passo = ripiego sull'italiano, non misurato.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--guai", action="store_true",
                    help="mostra solo le righe che hanno qualcosa da dichiarare")
    ap.add_argument("--fonemi", action="store_true",
                    help="fonemizza e conta i simboli buttati dallo stadio dopo")
    ap.add_argument("--sintesi", action="store_true",
                    help="sintetizza davvero e misura car/s e picco")
    ap.add_argument("--motore", default="", help=f"uno di {', '.join(MOTORI)}")
    ap.add_argument("--lingue", default="", help="separate da virgola")
    ap.add_argument("--scarica", action="store_true",
                    help="prende i .onnx.json di Piper che mancano (7 KB l'uno)")
    ap.add_argument("--prima", action="store_true",
                    help="con --sintesi, misura la sola prima voce del pool "
                         "invece di tutte (veloce, ma il passo che ne esce e' "
                         "di quella voce e non della lingua)")
    a = ap.parse_args(argv)

    solo = tuple(x.strip() for x in a.lingue.split(",") if x.strip())
    motori = (a.motore,) if a.motore else MOTORI

    if a.fonemi:
        from speak.frasi import frase
        from speak.pool import lingue_con_voce

        for motore in motori:
            lingue = tuple(x for x in lingue_con_voce(motore)
                           if not solo or x in solo)
            print(f"\n{motore}: {len(lingue)} lingue")
            for lingua in lingue:
                testo = frase(lingua)
                if not testo:
                    print(f"  {lingua:4} nessuna frase di prova")
                    continue
                try:
                    if motore == "piper":
                        crudi, persi, quali = scarti_piper(lingua, testo, a.scarica)
                    else:
                        crudi, persi, quali = SCARTI_PER_MOTORE[motore](lingua, testo)
                except Exception as e:  # noqa: BLE001
                    print(f"  {lingua:4} ! {type(e).__name__}: "
                          f"{str(e).splitlines()[0][:70]}", flush=True)
                    continue
                quota = 100.0 * persi / crudi if crudi else 0.0
                segno = "  <<<" if quota > 0.5 else ""
                print(f"  {lingua:4} crudi {crudi:4}  persi {persi:3} "
                      f"({quota:4.1f}%) {quali!r}{segno}", flush=True)
        return 0

    if a.sintesi:
        from speak.pool import lingue_con_voce

        for motore in motori:
            lingue = tuple(x for x in lingue_con_voce(motore)
                           if not solo or x in solo)
            print(f"\n{motore}: {len(lingue)} lingue")
            misura(motore, lingue, tutte_le_voci=not a.prima)
        return 0

    righe = matrice(solo)
    _stampa_matrice(righe, a.guai)
    conta: dict[str, int] = {}
    for r in righe:
        for g in r.guai:
            conta[g] = conta.get(g, 0) + 1
    print(f"\n{len(righe)} lingue nei cataloghi, "
          f"{sum(1 for r in righe if r.guai)} con qualcosa da dichiarare")
    for g, n in sorted(conta.items(), key=lambda x: -x[1]):
        print(f"  {g:20} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
