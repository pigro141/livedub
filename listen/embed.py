"""La voce ridotta a un punto: l'impronta di chi sta parlando.

Serve a F3. Il sottotitolo dice *cosa* si dice e il colore della riga dice
*che e' cambiato qualcuno*, ma nessuno dei due dice **quale** personaggio: quello
lo sa solo l'audio. Un embedding di speaker e' un vettore per cui due ritagli
della stessa voce stanno vicini e due voci diverse stanno lontane, e la distanza
e' il coseno perche' i vettori si normalizzano a norma uno.

## Due backend, e il piu' stupido non e' un ripiego

`ecapa-onnx` e' il modello vero: ECAPA-TDNN addestrato su VoxCeleb, 192
dimensioni, 25 MB, gira su CPU in qualche decina di millisecondi. `mfcc` sono
media e deviazione dei cepstri, quaranta righe di numpy che chiunque puo'
leggere per intero.

Il secondo esiste per la stessa ragione per cui esiste `EnergyVad`, ed e' una
ragione che qui pesa piu' che altrove: **le statistiche dei cepstri descrivono
soprattutto il canale**, cioe' la stanza, la musica di fondo, il rumore del
motore. Se su una misura i due backend danno lo stesso risultato, quella misura
non sta separando le voci — sta separando le scene, e la conclusione "il modello
funziona" sarebbe indistinguibile da "il modello e' inutile qui". Il backend
stupido non e' il piano B: e' il caso nullo del backend serio.

## La trasformata e' il punto in cui si sbaglia in silenzio

Il modello non vuole audio, vuole un banco di filtri mel in scala Kaldi: 80
bande, finestre da 25 ms ogni 10 ms, finestra di Povey, preenfasi 0,97, ampiezza
in scala intera a 16 bit. Ogni dettaglio sbagliato produce numeri plausibili —
non un errore — e un embedding che sembra funzionare perche' separa comunque
*qualcosa*. Per questo `fbank` sta qui fuori come funzione a se', verificabile
contro risposte note (un tono puro deve accendere la banda che lo contiene), e
per questo il banco di prova confronta sempre le voci vere del gioco con voci
sintetiche di identita' nota: se la trasformata fosse sbagliata, le voci note
non si separerebbero, e si saprebbe subito che il colpevole e' il codice e non
l'audio del gioco.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from core import percorsi
from core.config import SpeakerConfig
from mix.stretch import resample

# Il modello vuole 16 kHz. Non e' negoziabile: e' la frequenza a cui e' stato
# addestrato, e dargli 48 kHz sposterebbe tutte le bande mel.
MODEL_RATE = 16000

# Repo e file del modello ECAPA. Sono quelli ufficiali di WeSpeaker: l'ONNX
# esportato dallo stesso progetto che ha addestrato i pesi, non una ri-esportazione.
ECAPA_REPO = "Wespeaker/wespeaker-voxceleb-ecapa-tdnn512"
ECAPA_FILE = "voxceleb_ECAPA512.onnx"
ECAPA_DIR = percorsi.modelli("ecapa")

_EPS = 1.1920928955078125e-07  # eps di float32, come nella fbank di riferimento


# -- la trasformata --------------------------------------------------------


def _mel(f: np.ndarray | float) -> np.ndarray | float:
    """Frequenza in scala mel, formula di Kaldi."""
    return 1127.0 * np.log(1.0 + np.asarray(f, dtype=np.float64) / 700.0)


def mel_bank(
    n_mels: int, n_fft: int, samplerate: int, low_freq: float = 20.0, high_freq: float = 0.0
) -> np.ndarray:
    """Banco triangolare in scala mel, `(n_mels, n_fft // 2)`.

    Le colonne sono `n_fft // 2` e non `n_fft // 2 + 1` perche' Kaldi scarta la
    banda di Nyquist. Un banco largo un bin di piu' non darebbe errore: darebbe
    uno scorrimento silenzioso di tutte le bande.
    """
    nyquist = samplerate / 2.0
    high = nyquist + high_freq if high_freq <= 0.0 else high_freq
    if not (0.0 <= low_freq < high <= nyquist):
        raise ValueError(f"banda mel assurda: [{low_freq}, {high}] su {samplerate} Hz")

    n_bins = n_fft // 2
    centers = _mel(np.arange(n_bins) * (samplerate / n_fft))
    m_low, m_high = float(_mel(low_freq)), float(_mel(high))
    delta = (m_high - m_low) / (n_mels + 1)

    bank = np.zeros((n_mels, n_bins), dtype=np.float32)
    for i in range(n_mels):
        left = m_low + i * delta
        right = left + 2.0 * delta
        rise = (centers - left) / delta
        fall = (right - centers) / delta
        w = np.minimum(rise, fall)
        bank[i] = np.where((centers > left) & (centers < right), np.maximum(w, 0.0), 0.0)
    return bank


def _povey_window(n: int) -> np.ndarray:
    """La finestra di Kaldi: una Hann elevata a 0,85."""
    k = np.arange(n, dtype=np.float64)
    hann = 0.5 - 0.5 * np.cos(2.0 * np.pi * k / (n - 1))
    return np.power(hann, 0.85).astype(np.float32)


def fbank(
    mono: np.ndarray,
    samplerate: int = MODEL_RATE,
    *,
    n_mels: int = 80,
    frame_ms: float = 25.0,
    shift_ms: float = 10.0,
) -> np.ndarray:
    """Log-mel in scala Kaldi, `(n_frames, n_mels)`.

    Riproduce `torchaudio.compliance.kaldi.fbank` con i parametri di WeSpeaker
    (`dither=0`, 80 bande, 25/10 ms). L'ordine delle operazioni dentro il frame
    conta e non e' quello che verrebbe naturale: prima si toglie la componente
    continua, **poi** si preenfatizza, **poi** si finestra. Invertire preenfasi
    e finestra cambia le bande basse di qualche dB — abbastanza per peggiorare
    un embedding, troppo poco per accorgersene guardando i numeri.
    """
    x = np.asarray(mono, dtype=np.float32).reshape(-1)
    frame_len = int(round(samplerate * frame_ms / 1000.0))
    frame_shift = int(round(samplerate * shift_ms / 1000.0))
    if x.size < frame_len:
        return np.zeros((0, n_mels), dtype=np.float32)

    # Convenzione Kaldi: l'ampiezza e' in scala intera a 16 bit, non in [-1, 1].
    x = x * 32768.0

    win = np.lib.stride_tricks.sliding_window_view(x, frame_len)[::frame_shift].astype(
        np.float32, copy=True
    )
    win -= win.mean(axis=1, keepdims=True)  # componente continua
    pre = np.empty_like(win)
    pre[:, 1:] = win[:, 1:] - 0.97 * win[:, :-1]
    pre[:, 0] = win[:, 0] - 0.97 * win[:, 0]  # il primo campione predice se stesso
    pre *= _povey_window(frame_len)

    n_fft = 1
    while n_fft < frame_len:
        n_fft *= 2
    power = np.abs(np.fft.rfft(pre, n=n_fft, axis=1)) ** 2
    energies = power[:, : n_fft // 2] @ mel_bank(n_mels, n_fft, samplerate).T
    return np.log(np.maximum(energies, _EPS)).astype(np.float32)


def cmn(feats: np.ndarray) -> np.ndarray:
    """Media sottratta lungo il tempo.

    Toglie cio' che e' costante per tutta la clip, che e' in buona parte il
    canale. E' il minimo di igiene prima di confrontare due ritagli registrati
    in momenti diversi — senza, la differenza fra due scene supera quella fra
    due persone.
    """
    return feats - feats.mean(axis=0, keepdims=True) if feats.size else feats


def dct2(x: np.ndarray, n_out: int) -> np.ndarray:
    """DCT-II ortonormale sulle colonne, tenendo i primi `n_out` coefficienti."""
    n = x.shape[1]
    k = np.arange(n_out)[:, None]
    m = np.arange(n)[None, :]
    basis = np.cos(np.pi * k * (2 * m + 1) / (2 * n)) * np.sqrt(2.0 / n)
    basis[0] *= np.sqrt(0.5)
    return (x @ basis.T).astype(np.float32)


def to_model_rate(mono: np.ndarray, samplerate: int) -> np.ndarray:
    """Porta l'audio a 16 kHz riusando il ricampionatore del mixer."""
    if samplerate == MODEL_RATE:
        return np.asarray(mono, dtype=np.float32).reshape(-1)
    return resample(np.asarray(mono, dtype=np.float32).reshape(-1), samplerate, MODEL_RATE)


# -- i backend -------------------------------------------------------------


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, mono: np.ndarray, samplerate: int) -> np.ndarray:
        ...


def _l2(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return (v / n).astype(np.float32) if n > 1e-9 else np.zeros_like(v, dtype=np.float32)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Coseno fra due impronte gia' normalizzate."""
    return float(np.dot(a, b))


@dataclass
class MfccEmbedder:
    """Media e deviazione dei cepstri. Il caso nullo, non il piano B.

    Si scartano i coefficienti `c0` (che e' il volume) e si tiene il resto,
    media e deviazione lungo il tempo. Separa le voci solo quando sono molto
    diverse, e separa **benissimo** le registrazioni fatte in condizioni
    diverse: e' esattamente questa seconda proprieta' a renderlo utile come
    termine di paragone.
    """

    n_mfcc: int = 20
    name: str = "mfcc"

    @property
    def dim(self) -> int:
        return 2 * (self.n_mfcc - 1)

    def embed(self, mono: np.ndarray, samplerate: int) -> np.ndarray:
        x = to_model_rate(mono, samplerate)
        fb = fbank(x, MODEL_RATE)
        if fb.shape[0] < 2:
            return np.zeros(self.dim, dtype=np.float32)
        ceps = dct2(cmn(fb), self.n_mfcc)[:, 1:]
        return _l2(np.concatenate([ceps.mean(axis=0), ceps.std(axis=0)]))


class EcapaOnnxEmbedder:
    """ECAPA-TDNN di WeSpeaker in ONNX, 192 dimensioni, su CPU.

    Il modello si scarica alla prima chiamata in `models/ecapa/`. Il costruttore
    fa scaricare e caricare **subito**: un caricamento pigro alla prima clip
    farebbe pagare venticinque megabyte di rete dentro una misura di latenza.
    """

    name = "ecapa-onnx"
    dim = 192

    def __init__(self, *, download: bool = True, threads: int = 1) -> None:
        import onnxruntime as ort

        from core.onnx import provider_voluti

        self.path = self._fetch(download)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, int(threads))
        opts.inter_op_num_threads = 1
        # CPU per scelta: il modello e' piccolo e la GPU serve alla sintesi. Ma si
        # passa comunque dalla porta di `core/onnx.py`, perche' e' li' che vive il
        # precaricamento delle DLL — averne una sola vale piu' della scorciatoia.
        self._sess = ort.InferenceSession(
            str(self.path),
            sess_options=opts,
            providers=provider_voluti("cpu", chi="ecapa"),
        )
        self._input = self._sess.get_inputs()[0].name
        self._output = self._sess.get_outputs()[0].name

    @staticmethod
    def _fetch(download: bool) -> Path:
        local = ECAPA_DIR / ECAPA_FILE
        if local.exists():
            return local
        if not download:
            raise FileNotFoundError(f"modello ECAPA assente: {local}")
        from huggingface_hub import hf_hub_download

        return Path(hf_hub_download(ECAPA_REPO, ECAPA_FILE, local_dir=str(ECAPA_DIR)))

    def embed(self, mono: np.ndarray, samplerate: int) -> np.ndarray:
        x = to_model_rate(mono, samplerate)
        feats = cmn(fbank(x, MODEL_RATE))
        if feats.shape[0] < 10:
            # Meno di 100 ms di audio: il pooling statistico del modello non ha
            # niente su cui mediare. Un vettore nullo si riconosce a valle
            # (coseno zero con tutto), un vettore casuale no.
            return np.zeros(self.dim, dtype=np.float32)
        out = self._sess.run([self._output], {self._input: feats[None, :, :]})[0]
        return _l2(np.asarray(out, dtype=np.float32).reshape(-1))


def make_embedder(
    cfg: SpeakerConfig, *, download: bool = True, quiet: bool = False
) -> Embedder:
    """Costruisce l'impronta chiesta dalla configurazione.

    Se il modello non c'e' e non si riesce a scaricarlo si ripiega su `mfcc`,
    ma **dichiarandolo su stderr**. Un ripiego silenzioso qui e' il difetto
    peggiore possibile: si misurerebbe il backend stupido credendo di misurare
    il modello, e la curva sbagliata sarebbe indistinguibile da quella giusta.
    Chi non vuole ripieghi guarda `.name`, che dice sempre cosa sta girando.
    """
    backend = (cfg.backend or "ecapa-onnx").lower()
    if backend == "none":
        raise ValueError("backend speaker 'none': nessuna impronta da calcolare")
    if backend == "mfcc":
        return MfccEmbedder()
    if backend != "ecapa-onnx":
        raise ValueError(f"backend speaker sconosciuto: {cfg.backend}")
    try:
        return EcapaOnnxEmbedder(download=download)
    except Exception as exc:  # rete assente, modello mancante, onnxruntime rotto
        if not quiet:
            print(
                f"ATTENZIONE: ECAPA non disponibile ({type(exc).__name__}: {exc}); "
                f"si ripiega su 'mfcc', che misura il canale piu' della voce.",
                file=sys.stderr,
            )
        return MfccEmbedder()
