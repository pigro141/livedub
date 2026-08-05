"""Interfaccia della sintesi.

Un backend riceve un testo e una voce e restituisce audio. Tutto quello che
riguarda *quanto in fretta* parlare, *con che intonazione* e *quanto forte* e'
gia' stato deciso a monte e arriva dentro la `VoiceSpec` e il parametro `rate`:
il backend non prende decisioni artistiche, esegue.

La separazione serve a poter cambiare motore senza toccare nient'altro. Il tier
A (Piper, CPU, latenza garantita) e il tier B (un modello espressivo su GPU)
devono essere intercambiabili da configurazione, perche' quale dei due convenga
si decide sul banco e non a priori.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from core.types import VoiceSpec


@dataclass(slots=True)
class Speech:
    """Audio sintetizzato, con il conto di quanto e' costato produrlo."""

    audio: np.ndarray  # float32 mono in [-1, 1]
    samplerate: int
    voice_id: str = "?"
    first_sample_ms: float = 0.0  # tempo al primo campione: e' la latenza che si sente
    total_ms: float = 0.0
    text: str = ""

    @property
    def duration(self) -> float:
        return len(self.audio) / float(self.samplerate) if self.samplerate else 0.0

    @property
    def rtf(self) -> float:
        """Real-time factor: sotto 1 vuol dire che si sintetizza piu' in fretta
        di quanto si ascolta."""
        d = self.duration
        return (self.total_ms / 1000.0) / d if d > 0 else 0.0


def taglia_silenzio(
    audio: "np.ndarray", samplerate: int, soglia: float = 0.02, margine: float = 0.03
) -> "np.ndarray":
    """Toglie il silenzio in testa e in coda a quello che il sintetizzatore da'.

    **Non e' cosmetica, ed e' costata mezza notte di conclusioni sbagliate.**
    SuperTonic imbottisce: su dodici battute vere, 6,0 secondi di silenzio in
    testa e 7,6 in coda su 35,2 totali, cioe' il **39% dell'uscita**. La catena
    quella roba non la sa distinguere dal parlato — misura una durata e la
    confronta con la finestra del sottotitolo — quindi concludeva che la battuta
    non ci stava e chiedeva al modello di andare piu' svelto. Il modello, per
    andare piu' svelto, saltava sillabe. Si accelerava del silenzio, pagandolo
    in parole.

    Al netto dell'imbottitura i due motori vanno quasi uguale: 14,8 caratteri al
    secondo SuperTonic contro 15,6 di Piper. Tutto il divario di ritmo che
    sembrava esserci era questo.

    Il margine lasciato e' piccolo apposta: lo stacco fra una battuta e l'altra
    lo mette gia' `tts.gap_seconds`, che esiste proprio per quello e sa anche
    togliersi di mezzo quando si e' in ritardo. Due respiri sovrapposti sono un
    respiro che non finisce piu'.
    """
    import numpy as np

    a = np.asarray(audio, dtype=np.float32).reshape(-1)
    if a.size == 0:
        return a
    picco = float(np.abs(a).max())
    if picco <= 0.0:
        return a[:0]
    forte = np.flatnonzero(np.abs(a) > soglia * picco)
    if forte.size == 0:
        return a[:0]
    m = int(margine * samplerate)
    return a[max(0, int(forte[0]) - m) : min(a.size, int(forte[-1]) + m + 1)]


class TtsBackend(Protocol):
    name: str
    samplerate: int
    # **Quanto parla in fretta questo motore, nella stessa unita' di
    # `spoken_length()`** — lettere e cifre al secondo, non caratteri qualunque.
    # Il passo e' una proprieta' del motore e non della sessione: dichiararlo qui
    # evita che la catena stimi le durate di un backend con il ritmo di un altro,
    # che e' esattamente cio' che faceva (17,4 di Piper applicati a SuperTonic, e
    # per giunta contati in un'altra unita').
    chars_per_second: float

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        ...


# **Sa consegnare a pezzi?** Un backend che espone `streaming = True` offre anche
#
#     stream(text, voice, rate=1.0, max_seconds=0.0) -> Iterator[(blocco, finita)]
#
# Serve ai motori autoregressivi, dove aspettare la battuta intera costa secondi
# mentre il primo blocco costa centinaia di millisecondi.
#
# `max_seconds` non e' facoltativo e non e' una rifinitura: un modello
# autoregressivo **si incanta** — misurato, quindici caratteri diventati 9,12
# secondi di audio — e senza un tetto quella battuta tiene occupata l'unica voce
# disponibile mentre le altre slittano. `0` vuol dire nessun tetto, che e' giusto
# sul banco e sbagliato dal vivo.
#
# E' un attributo e non un `hasattr(tts, "stream")` di proposito: cosi' si puo'
# **spegnere** (`tts.stream = false`) su un backend che pure lo saprebbe fare, e
# rimisurare il divario invece di ricordarselo. La catena guarda questo, non la
# presenza del metodo.
def sa_streaming(tts) -> bool:
    return bool(getattr(tts, "streaming", False)) and hasattr(tts, "stream")


@dataclass
class ToneTts:
    """Backend finto: produce un bip modulato invece di parlare.

    Non e' un segnaposto inutile. Serve a misurare **tutto il resto** della
    catena — tempi, scheduler, mixer, duck — senza che i tempi del sintetizzatore
    vero si mescolino ai loro, e senza scaricare un modello. Se una battuta arriva
    tardi con questo backend, il colpevole non e' il TTS.

    La durata imita quella del parlato (circa 14 caratteri al secondo) e
    l'intonazione segue la voce, cosi' anche l'assegnazione delle voci si sente.
    """

    name: str = "tone"
    samplerate: int = 22050
    chars_per_second: float = 14.0

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        import time

        t0 = time.perf_counter()
        rate = max(0.1, rate * voice.rate)
        seconds = max(0.15, len(text) / self.chars_per_second / rate)
        n = int(seconds * self.samplerate)
        t = np.arange(n, dtype=np.float32) / self.samplerate

        base_f0 = 190.0 if voice.gender == "f" else 115.0
        f0 = base_f0 * (2.0 ** (voice.semitones / 12.0))
        # Poche armoniche e un inviluppo a sillabe: basta a distinguere le voci
        # a orecchio senza fingere di essere parlato.
        wave = sum(
            (0.6 / k) * np.sin(2 * np.pi * f0 * k * t) for k in (1, 2, 3)
        ).astype(np.float32)
        syllables = 0.55 + 0.45 * np.sin(2 * np.pi * 4.0 * rate * t)
        fade = np.minimum(1.0, np.minimum(t, seconds - t) * 40.0).clip(0.0)
        audio = (wave * syllables * fade * 0.25).astype(np.float32)

        ms = (time.perf_counter() - t0) * 1000.0
        return Speech(
            audio=audio,
            samplerate=self.samplerate,
            voice_id=voice.voice_id,
            first_sample_ms=ms,
            total_ms=ms,
            text=text,
        )


@dataclass
class SilentTts:
    """Non produce nulla. Per i test che vogliono la catena senza audio."""

    name: str = "silent"
    samplerate: int = 22050

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        return Speech(
            audio=np.zeros(0, np.float32),
            samplerate=self.samplerate,
            voice_id=voice.voice_id,
            text=text,
        )


# I nomi che `tts.backend` accetta. Dichiarati qui perche' li usano sia la
# factory sia gli `argparse` degli strumenti: due elenchi diverghevano gia'
# (`tools/say.py` vietava SuperTonic con un `choices` rimasto indietro).
BACKEND_NOTI = ("piper", "supertonic", "kokoro", "tone", "silent")


def make_tts(cfg, *, download: bool = True, preload: bool = True):
    """Il backend di sintesi richiesto, costruito con **tutti** i suoi parametri.

    Prende la sezione `tts` intera e non i singoli campi, ed e' il punto. Finche'
    la costruzione era ripetuta in sei posti, `tools/dub.py` non passava `steps`
    e `speed`: il banco misurava una configurazione diversa da quella che diceva
    di misurare, mentre `tools/live.py` li passava da sempre — banco e vivo
    giravano con due velocita' diverse. Con un solo punto di costruzione non e'
    una cosa da ricordarsi, e' una cosa che non puo' succedere.

    **Un nome sconosciuto e' un errore.** Prima si ripiegava in silenzio su
    Piper, quindi `--set tts.backend=<refuso>` produceva un doppiaggio del tutto
    plausibile con il motore sbagliato, e nessun numero lo diceva. E' la stessa
    forma del «trattamento non applicato» che ha gia' fatto leggere due volte un
    risultato pulito e falso. `make_ocr` e `make_embedder` sollevano da sempre.

    `preload` scalda le voci della famiglia: il primo `synthesize` costruisce le
    sessioni e paga tutto il caricamento — 1,7 s per Piper, quasi altrettanto
    per Kokoro su CUDA dove vanno compilati i kernel — e non deve capitare sulla
    prima battuta di una partita.
    """
    nome = (cfg.backend or "").lower()

    if nome == "tone":
        return ToneTts(samplerate=cfg.samplerate)
    if nome == "silent":
        return SilentTts(samplerate=cfg.samplerate)

    if nome == "piper":
        from speak.backends.piper import PiperTts

        tts = PiperTts(samplerate=cfg.samplerate, download=download)
    elif nome == "supertonic":
        from speak.backends.supertonic import SupertonicTts

        tts = SupertonicTts(
            samplerate=cfg.samplerate,
            steps=cfg.steps,
            speed=cfg.speed,
            download=download,
        )
    elif nome == "kokoro":
        from speak.backends.kokoro import KokoroTts

        tts = KokoroTts(
            samplerate=cfg.samplerate,
            speed=cfg.kokoro_speed,
            pesi=cfg.kokoro_weights,
            device=cfg.device,
            download=download,
        )
    else:
        raise ValueError(
            f"backend TTS sconosciuto: {cfg.backend!r} (noti: {', '.join(BACKEND_NOTI)})"
        )

    if preload:
        # Le voci dichiarate se ci sono, altrimenti quelle della famiglia. Prima
        # si passava `cfg.voices`, che e' **vuoto** per default: il precaricamento
        # non precaricava niente e la prima battuta pagava lo stesso.
        from speak.pool import FAMIGLIE

        voci = list(cfg.voices) or list(FAMIGLIE.get(nome, ()))
        tts.preload(voci)
    return tts
