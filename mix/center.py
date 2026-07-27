"""Il canale centrale: dove sta il parlato.

Nei giochi il dialogo e' pannato al centro, mentre musica, motori e ambiente
sono larghi. La decomposizione mid/side sfrutta esattamente questo:

    mid  = (L + R) / 2      cio' che i due canali hanno in comune -> il parlato
    side = (L - R) / 2      cio' in cui differiscono -> tutto il resto

Abbassare il solo `mid` e ricomporre attenua le voci originali lasciando intatto
il resto. E' quello che rende ascoltabile il doppiaggio: senza, la voce italiana
si sovrappone a quella inglese e non si capisce nessuna delle due; abbassando
tutto, il gioco ammutolisce ogni volta che qualcuno parla.

Non e' una separazione vera — un'esplosione centrata viene attenuata anche lei —
ma costa quattro operazioni per campione e non ha latenza. Una separazione
neurale costerebbe piu' dell'intera pipeline e aggiungerebbe il ritardo del suo
buffer, proprio dove il ritardo e' la valuta scarsa.

**La verifica**: con guadagno 1 la ricomposizione deve restituire l'ingresso
campione per campione. Se non lo fa, ogni frame del gioco passa attraverso una
trasformazione che lo altera anche quando nessuno sta parlando.
"""

from __future__ import annotations

import numpy as np


def split(stereo: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Scompone in (mid, side)."""
    if stereo.ndim != 2 or stereo.shape[1] != 2:
        raise ValueError(f"attesa forma (n, 2), ricevuta {stereo.shape}")
    left = stereo[:, 0].astype(np.float32)
    right = stereo[:, 1].astype(np.float32)
    return (left + right) * 0.5, (left - right) * 0.5


def join(mid: np.ndarray, side: np.ndarray) -> np.ndarray:
    """Ricompone (mid, side) in stereo."""
    return np.stack([mid + side, mid - side], axis=1).astype(np.float32)


def duck_center(stereo: np.ndarray, gain: np.ndarray | float) -> np.ndarray:
    """Attenua il centro del fattore `gain`, lasciando i lati.

    `gain` puo' essere uno scalare o un array per-campione: la seconda forma
    serve all'inviluppo di attacco e rilascio, perche' un guadagno che salta di
    colpo si sente come un clic.
    """
    mid, side = split(stereo)
    return join(mid * gain, side)


def center_energy(stereo: np.ndarray) -> float:
    """Quanta energia c'e' al centro rispetto al totale, 0..1.

    Serve come indizio grezzo di "c'e' qualcuno che parla": il dialogo alza
    questo rapporto, la musica no.
    """
    mid, side = split(stereo)
    m = float(np.mean(mid * mid))
    s = float(np.mean(side * side))
    return m / (m + s) if (m + s) > 1e-12 else 0.0


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def gain_to_db(gain: float) -> float:
    return float(20.0 * np.log10(max(gain, 1e-9)))


class DuckEnvelope:
    """Inviluppo di attenuazione con attacco e rilascio.

    Asimmetrico di proposito: l'attacco e' rapido (bisogna fare spazio alla voce
    italiana prima che parta) e il rilascio lento (rialzare il volume del gioco
    a scatti fra una battuta e l'altra e' fastidioso quanto non abbassarlo).
    """

    def __init__(
        self,
        samplerate: int,
        duck_db: float = -14.0,
        attack_ms: float = 40.0,
        release_ms: float = 220.0,
    ) -> None:
        self.samplerate = samplerate
        self.duck_gain = db_to_gain(duck_db)
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.attack = self._coefficient(attack_ms)
        self.release = self._coefficient(release_ms)
        self.gain = 1.0

    @property
    def attack_seconds(self) -> float:
        return self.attack_ms / 1000.0

    def _coefficient(self, ms: float) -> float:
        """Costante di un filtro a un polo: quanto resta del valore precedente
        a ogni campione."""
        n = max(1.0, ms * self.samplerate / 1000.0)
        return float(np.exp(-1.0 / n))

    def block(self, n: int, active: bool) -> np.ndarray:
        """Inviluppo per `n` campioni, con il duck acceso o spento.

        Il filtro a un polo si applicherebbe campione per campione; qui la
        formula chiusa fa lo stesso lavoro in forma vettoriale, che a 48 kHz e'
        la differenza fra un ciclo Python e niente.
        """
        target = self.duck_gain if active else 1.0
        coeff = self.attack if target < self.gain else self.release
        steps = np.arange(1, n + 1, dtype=np.float32)
        decay = coeff**steps
        env = target + (self.gain - target) * decay
        self.gain = float(env[-1]) if n else self.gain
        return env.astype(np.float32)

    def reset(self) -> None:
        self.gain = 1.0
