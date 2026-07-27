"""Buffer circolare audio.

Il produttore e' la callback di cattura, che non puo' bloccarsi per nessun
motivo: se si ferma li', l'audio del gioco fa un buco. I consumatori (VAD,
embedding, emozione) leggono con comodo, ognuno al proprio ritmo.

Il buffer indicizza per **frame assoluto** dall'inizio della sessione, non per
posizione nell'array. Costa un intero in piu' e regala due cose: un consumatore
puo' tenere il proprio cursore senza coordinarsi con gli altri, e soprattutto
puo' *accorgersi* di essere rimasto indietro oltre la capacita' invece di
leggere silenziosamente dati sbagliati. Un sorpasso non segnalato e' il genere
di bug che si manifesta come "il riconoscimento speaker ogni tanto sbaglia".
"""

from __future__ import annotations

import threading

import numpy as np


class Overrun(Exception):
    """Il consumatore e' stato sorpassato: i dati richiesti sono gia' stati
    sovrascritti dal produttore."""


class RingBuffer:
    """Buffer circolare float32, mono o multicanale."""

    def __init__(self, capacity: int, channels: int = 1, samplerate: int = 48000) -> None:
        if capacity <= 0:
            raise ValueError(f"capacita' non valida: {capacity}")
        if channels <= 0:
            raise ValueError(f"canali non validi: {channels}")
        self.capacity = int(capacity)
        self.channels = int(channels)
        self.samplerate = int(samplerate)
        shape = (self.capacity,) if channels == 1 else (self.capacity, channels)
        self._buf = np.zeros(shape, dtype=np.float32)
        self._written = 0  # frame totali scritti dall'inizio
        self._lock = threading.Lock()
        self.overruns = 0

    # -- scrittura ---------------------------------------------------------

    def write(self, samples: np.ndarray) -> int:
        """Accoda un blocco. Restituisce l'indice assoluto del suo primo frame."""
        data = np.asarray(samples, dtype=np.float32)
        if self.channels == 1 and data.ndim == 2 and data.shape[1] == 1:
            data = data[:, 0]
        expected = 1 if self.channels == 1 else 2
        if data.ndim != expected:
            raise ValueError(f"attesi {expected} assi, ricevuto shape={data.shape}")
        if self.channels > 1 and data.shape[1] != self.channels:
            raise ValueError(f"attesi {self.channels} canali, ricevuti {data.shape[1]}")

        n = data.shape[0]
        if n == 0:
            return self._written
        if n > self.capacity:
            # Blocco piu' grande del buffer: si tiene solo la coda, ed e' un
            # errore di dimensionamento che va visto.
            data = data[-self.capacity :]
            n = self.capacity
            self.overruns += 1

        with self._lock:
            start = self._written
            pos = start % self.capacity
            end = pos + n
            if end <= self.capacity:
                self._buf[pos:end] = data
            else:
                split = self.capacity - pos
                self._buf[pos:] = data[:split]
                self._buf[: end - self.capacity] = data[split:]
            self._written += n
            return start

    # -- lettura -----------------------------------------------------------

    @property
    def written(self) -> int:
        """Frame totali passati dal buffer dall'inizio della sessione."""
        return self._written

    @property
    def available(self) -> int:
        """Frame ancora leggibili (i piu' recenti)."""
        return min(self._written, self.capacity)

    def read_last(self, n: int, pad: bool = True) -> np.ndarray:
        """Copia degli ultimi `n` frame.

        Se non ce ne sono abbastanza e `pad` e' vero, la copia e' allineata a
        destra e riempita di zeri a sinistra: comodo per i modelli che vogliono
        una finestra di lunghezza fissa fin dal primo istante.
        """
        if n <= 0:
            return self._empty(0)
        with self._lock:
            have = min(self._written, self.capacity)
            take = min(n, have)
            out = self._slice(self._written - take, take)
        if take == n or not pad:
            return out
        padded = self._empty(n)
        if take:
            padded[n - take :] = out
        return padded

    def read_from(self, index: int, n: int) -> np.ndarray:
        """Legge `n` frame a partire dal frame assoluto `index`.

        Solleva `Overrun` se quei dati sono gia' stati sovrascritti. Se il
        produttore non e' ancora arrivato a `index + n`, restituisce quello che
        c'e' (anche vuoto): sta al chiamante richiamare piu' tardi.
        """
        if n < 0:
            raise ValueError(f"n negativo: {n}")
        with self._lock:
            oldest = max(0, self._written - self.capacity)
            if index < oldest:
                self.overruns += 1
                raise Overrun(
                    f"frame {index} gia' sovrascritto (il piu' vecchio disponibile e' {oldest})"
                )
            if index > self._written:
                raise ValueError(f"frame {index} non ancora scritto (written={self._written})")
            take = min(n, self._written - index)
            return self._slice(index, take)

    # -- tempo -------------------------------------------------------------

    def frame_to_time(self, index: int, t0: float = 0.0) -> float:
        """Tempo del frame assoluto `index`, dato l'istante `t0` del frame 0."""
        return t0 + index / float(self.samplerate)

    def time_to_frame(self, t: float, t0: float = 0.0) -> int:
        return int(round((t - t0) * self.samplerate))

    # -- interni -----------------------------------------------------------

    def _empty(self, n: int) -> np.ndarray:
        shape = (n,) if self.channels == 1 else (n, self.channels)
        return np.zeros(shape, dtype=np.float32)

    def _slice(self, index: int, n: int) -> np.ndarray:
        """Copia di `n` frame dal frame assoluto `index`. Chiamare sotto lock."""
        if n <= 0:
            return self._empty(0)
        pos = index % self.capacity
        end = pos + n
        if end <= self.capacity:
            return self._buf[pos:end].copy()
        split = self.capacity - pos
        out = self._empty(n)
        out[:split] = self._buf[pos:]
        out[split:] = self._buf[: end - self.capacity]
        return out

    def __repr__(self) -> str:
        return (
            f"<RingBuffer {self.capacity}fr x{self.channels}ch @{self.samplerate}Hz "
            f"written={self._written} overruns={self.overruns}>"
        )
