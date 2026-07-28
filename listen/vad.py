"""Quando qualcuno comincia a parlare, nell'audio del gioco.

Serve a una cosa sola in F2, e vale la pena dirla prima dell'interfaccia: il
sottotitolo compare quando il gioco decide di mostrarlo, la **voce** comincia
quando il personaggio apre la bocca, e i due istanti non coincidono. L'onset del
parlato e' l'ancoraggio piu' preciso dei due, ed e' l'unico modo per attaccare
la voce italiana dove attacca quella originale invece che dove appare il testo.

Piu' avanti lo stesso stadio serve a F3 (ritagliare la clip su cui calcolare
l'embedding) e a F4 (misurare il livello della battuta originale). Per questo
l'uscita sono **segmenti**, non un booleano per frame: chi arriva dopo ha
bisogno di sapere dove comincia e dove finisce una presa di parola.

## Due cose che si sbagliano facilmente qui

**L'istante dell'onset non e' l'istante in cui si e' deciso.** Per non chiamare
parlato ogni colpo di clacson servono `min_speech_ms` di suono continuo, ma quel
tempo va speso *guardando indietro*: l'onset dichiarato e' quello del primo
frame sopra soglia, non quello della conferma. E' la stessa regola del `t_on`
dello stabilizzatore dei sottotitoli, e per la stessa ragione — un ancoraggio
che si sposta di centocinquanta millisecondi a seconda di quanto ci si mette a
confermarlo non e' un ancoraggio.

**La soglia non puo' essere assoluta.** L'audio di un gioco passa da una stanza
silenziosa a un inseguimento in tre secondi, e una soglia fissa direbbe "parla
sempre" nel secondo caso e "non parla mai" nel primo. Qui si misura il rumore di
fondo su una finestra scorrevole e si chiede al parlato di **staccare** da
quello, che e' la stessa forma di ragionamento del contrasto locale usato per
trovare i glifi: non quanto e' forte, ma quanto e' piu' forte di cio' che ha
intorno.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from core.config import VadConfig

_EPS = 1e-10


@dataclass(frozen=True, slots=True)
class Speech:
    """Una presa di parola: da quando a quando."""

    t0: float
    t1: float | None = None  # None finche' e' ancora in corso
    peak_dbfs: float = -120.0

    @property
    def duration(self) -> float | None:
        return None if self.t1 is None else self.t1 - self.t0

    def ended(self, t1: float, peak_dbfs: float | None = None) -> "Speech":
        return Speech(self.t0, t1, self.peak_dbfs if peak_dbfs is None else peak_dbfs)


def dbfs(block: np.ndarray) -> float:
    """Livello RMS in dBFS. Il silenzio digitale vale -120, non -inf."""
    if block.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(block, dtype=np.float64))))
    return max(-120.0, 20.0 * np.log10(rms + _EPS))


class EnergyVad:
    """Rilevatore di parlato per stacco dal rumore di fondo.

    Non e' un modello: e' un livello contro un fondo, con isteresi. Esiste per
    due motivi diversi e ugualmente necessari — perche' la suite deve poter
    girare senza scaricare niente, e perche' quando un modello dara' un
    risultato strano servira' qualcosa di stupido con cui confrontarlo. Un
    rilevatore che si puo' leggere per intero e' il modo di distinguere "il
    modello sbaglia" da "il segnale non contiene la risposta".
    """

    def __init__(self, cfg: VadConfig, samplerate: int) -> None:
        self.cfg = cfg
        self.samplerate = samplerate
        self.frame = max(1, int(samplerate * cfg.frame_ms / 1000.0))
        self._floor_window = deque(
            maxlen=max(4, int(cfg.floor_window_ms / max(1, cfg.frame_ms)))
        )
        self._tail = np.zeros(0, dtype=np.float32)
        self._t_next = 0.0  # istante del primo campione non ancora consumato
        self._started = False  # siamo dentro una presa di parola?
        self._run_on = 0  # frame consecutivi sopra soglia
        self._run_off = 0  # e sotto
        self._cand_t0 = 0.0  # inizio del tratto sopra soglia in corso
        self._cand_peak = -120.0
        self._open: Speech | None = None
        self._last_off_t = 0.0

    # -- stato -------------------------------------------------------------

    @property
    def speaking(self) -> bool:
        return self._open is not None

    @property
    def noise_floor(self) -> float:
        """Il fondo stimato, in dBFS. Utile nei log per capire una decisione."""
        if not self._floor_window:
            return -120.0
        return float(np.percentile(np.asarray(self._floor_window), self.cfg.floor_percentile))

    def reset(self) -> None:
        self._floor_window.clear()
        self._tail = np.zeros(0, dtype=np.float32)
        self._started = False
        self._run_on = self._run_off = 0
        self._open = None

    # -- alimentazione -----------------------------------------------------

    def push(self, mono: np.ndarray, t: float | None = None) -> list[Speech]:
        """Consuma audio mono e restituisce le prese di parola **concluse**.

        Quella eventualmente in corso si legge da `current`: chiuderla in
        anticipo per farla comparire nell'uscita significherebbe dichiarare una
        fine che non e' ancora avvenuta.
        """
        if mono.ndim != 1:
            raise ValueError(f"il VAD vuole audio mono, ricevuto shape={mono.shape}")
        if t is not None and self._tail.size == 0:
            self._t_next = t
        buf = np.concatenate([self._tail, mono.astype(np.float32)]) if self._tail.size else mono.astype(np.float32)

        done: list[Speech] = []
        n_frames = len(buf) // self.frame
        need_on = max(1, int(round(self.cfg.min_speech_ms / max(1, self.cfg.frame_ms))))
        need_off = max(1, int(round(self.cfg.min_silence_ms / max(1, self.cfg.frame_ms))))
        dt = self.frame / self.samplerate

        for i in range(n_frames):
            block = buf[i * self.frame : (i + 1) * self.frame]
            t0 = self._t_next + i * dt
            level = dbfs(block)
            floor = self.noise_floor
            # Il fondo si aggiorna solo quando NON si sta parlando: altrimenti
            # una battuta lunga alza il fondo fino a coprirsi da sola.
            attivo = level > floor + self.cfg.energy_margin_db and level > self.cfg.floor_db
            if not attivo or not self._floor_window:
                self._floor_window.append(level)

            if attivo:
                if self._run_on == 0:
                    self._cand_t0 = t0
                    self._cand_peak = level
                else:
                    self._cand_peak = max(self._cand_peak, level)
                self._run_on += 1
                self._run_off = 0
                if self._open is None and self._run_on >= need_on:
                    # L'onset e' quello del PRIMO frame sopra soglia.
                    self._open = Speech(self._cand_t0, None, self._cand_peak)
            else:
                self._run_off += 1
                self._run_on = 0
                if self._open is not None and self._run_off >= need_off:
                    # La fine e' l'inizio del silenzio, non la sua conferma.
                    fine = t0 - (need_off - 1) * dt
                    done.append(self._open.ended(fine, self._cand_peak))
                    self._open = None

        consumed = n_frames * self.frame
        self._t_next += n_frames * dt
        self._tail = buf[consumed:].copy()
        return done

    @property
    def current(self) -> Speech | None:
        """La presa di parola in corso, se ce n'e' una."""
        return self._open

    def flush(self, t: float | None = None) -> list[Speech]:
        """Chiude cio' che e' rimasto aperto. A fine sessione o fine replay."""
        if self._open is None:
            return []
        fine = self._t_next if t is None else t
        out = [self._open.ended(fine, self._cand_peak)]
        self._open = None
        return out


def make_vad(cfg: VadConfig, samplerate: int):
    """Costruisce il rilevatore chiesto dalla configurazione.

    `silero` non c'e' ancora: finche' non c'e', chiederlo restituisce quello a
    energia **dichiarandolo**. Un ripiego silenzioso qui sarebbe il difetto
    peggiore possibile — si misurerebbe il backend leggero credendo di misurare
    il modello, e la conclusione sbagliata sarebbe indistinguibile da quella
    giusta.
    """
    backend = (cfg.backend or "energy").lower()
    if backend in ("energy", "silero"):
        return EnergyVad(cfg, samplerate)
    raise ValueError(f"backend VAD sconosciuto: {cfg.backend}")
