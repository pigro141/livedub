"""Il mixer: dove l'audio del gioco e la voce italiana diventano una cosa sola.

Lavora a blocchi, con un tempo assoluto che scorre. Ogni battuta sintetizzata
viene *programmata* per un certo istante, e il mixer la versa nei blocchi giusti
man mano che quel tempo arriva. La programmazione conta: la voce italiana esce
qualche centinaio di millisecondi dopo l'originale, e senza un istante di
partenza esplicito non ci sarebbe modo di agganciarla al punto voluto.

Il duck non e' un dettaglio ma il motivo per cui il risultato si capisce. Si
abbassa il **solo canale centrale** dell'audio di gioco, che e' dove sta il
parlato: musica, motori e spari restano al loro volume. Vedi `mix/center.py`.

Il clipping si tratta con un limitatore morbido e non con un taglio netto: due
voci che si sommano possono superare il fondo scala, e un taglio netto produce
distorsione udibile proprio sui picchi, cioe' sulle grida.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import numpy as np

from core.metrics import MetricsRegistry
from mix.center import DuckEnvelope, db_to_gain, duck_center


@dataclass
class Scheduled:
    """Una battuta in attesa del proprio turno."""

    audio: np.ndarray  # mono, alla frequenza del mixer
    t_start: float
    gain: float = 1.0
    speaker_id: str = "?"
    text: str = ""
    consumed: int = 0  # campioni gia' versati
    # Quanto e' gia' stata accelerata prima di arrivare qui. Serve a `hurry`:
    # il tetto e' una proprieta' della **voce**, non di uno stadio, e due
    # compressioni ciascuna dentro il limite lo sfondano insieme.
    rate: float = 1.0

    @property
    def remaining(self) -> int:
        return max(0, len(self.audio) - self.consumed)

    @property
    def done(self) -> bool:
        return self.consumed >= len(self.audio)


class Mixer:
    """Somma la voce italiana all'audio di gioco, abbassandone il centro."""

    def __init__(
        self,
        samplerate: int = 48000,
        *,
        duck_db: float = -14.0,
        attack_ms: float = 40.0,
        release_ms: float = 220.0,
        dub_gain_db: float = 0.0,
        passthrough: bool = True,
        hold_ms: float = 500.0,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.samplerate = samplerate
        self.passthrough = passthrough
        self.hold_seconds = max(0.0, hold_ms / 1000.0)
        self.dub_gain = db_to_gain(dub_gain_db)
        self.envelope = DuckEnvelope(samplerate, duck_db, attack_ms, release_ms)
        self.metrics = metrics or MetricsRegistry()
        self._queue: list[Scheduled] = []
        self._t = 0.0
        # Solo la coda e' condivisa: si veda `schedule`. Il lucchetto e'
        # rientrante perche' `clear` puo' essere chiamata da dentro `process`.
        self._lock = threading.RLock()
        self._n_played = self.metrics.counter("mix.utterances")
        self._n_dropped = self.metrics.counter("mix.dropped")
        self._n_clipped = self.metrics.counter("mix.limited")
        self._n_late = self.metrics.counter("mix.late")
        self._n_hurried = self.metrics.counter("mix.hurried")

    # -- programmazione ----------------------------------------------------

    @property
    def now(self) -> float:
        return self._t

    @property
    def pending(self) -> int:
        return len(self._queue)

    @property
    def finisce_a(self) -> float:
        """Quando l'ultima battuta in coda smette di suonare.

        Si ricava da cio' che c'e' **adesso** nella coda, e non da un contatore
        tenuto a parte: dopo `hurry` la durata residua e' cambiata, e un
        contatore aggiornato altrove direbbe la lunghezza di prima. E' la stessa
        forma dei due orologi con origini diverse, un travestimento piu' in la'.
        """
        with self._lock:
            if not self._queue:
                return self._t
            return max(
                max(s.t_start, self._t) + s.remaining / self.samplerate
                for s in self._queue
            )

    @property
    def speaking(self) -> bool:
        """C'e' una battuta gia' iniziata e non ancora finita."""
        return any(s.consumed > 0 and not s.done for s in self._queue)

    def schedule(
        self,
        audio: np.ndarray,
        t_start: float,
        gain_db: float = 0.0,
        speaker_id: str = "?",
        text: str = "",
        rate: float = 1.0,
    ) -> Scheduled:
        """Mette una battuta in coda per l'istante indicato.

        Un istante gia' passato non e' un errore: la battuta parte al primo
        blocco utile. Perdere una battuta perche' e' arrivata tardi sarebbe il
        contrario di quello che il progetto si e' ripromesso — si sfora, non si
        scarta — ma il ritardo va contato, perche' e' un sintomo.

        **La coda e' l'unica cosa condivisa fra i due thread**, quindi il
        lucchetto sta qui e non attorno a chi chiama. Dal vivo il thread video
        sintetizza (misurato: fino a 1,9 s su una battuta lunga) e il thread
        audio deve scrivere un blocco ogni dieci millisecondi: un lucchetto piu'
        largo di questo trasforma il costo della sintesi in un buco nel suono.
        Il primo tentativo lo aveva messo attorno all'intero passo video, e il
        thread audio e' rimasto fermo 1,9 secondi — cioe' esattamente il tempo
        della sintesi.
        """
        item = Scheduled(
            audio=np.asarray(audio, dtype=np.float32),
            t_start=t_start,
            gain=db_to_gain(gain_db),
            speaker_id=speaker_id,
            text=text,
            rate=rate,
        )
        with self._lock:
            if item.t_start < self._t:
                self._n_late.inc()
                item.t_start = self._t
            self._queue.append(item)
        self._n_played.inc()
        return item

    def hurry(
        self,
        t_finish: float,
        limits: tuple[float, float] = (1.0, 1.35),
        min_residue: float = 0.6,
    ) -> float:
        """Stringe il **residuo non ancora suonato** perche' finisca entro `t_finish`.

        Serve quando arriva un sottotitolo nuovo mentre la voce italiana sta
        ancora dicendo il precedente. Sul banco quel caso e' il **34,9%** delle
        battute, ed e' l'unico sforamento che fa danno: una voce che continua
        mentre a schermo non c'e' piu' niente non disturba nessuno, mentre due
        battute accavallate fanno perdere una riga.

        **Perche' qui non serve prevedere.** La durata del sottotitolo si prevede
        da `D = a + b*n`, e misurata sulla registrazione quella retta ha R2 0,15:
        la lunghezza del testo spiega il quindici per cento della durata, cioe' il
        modello e' appena meglio di una costante. L'arrivo della battuta dopo,
        invece, non si stima — **accade**, e accade esattamente nell'istante in
        cui la decisione va presa.

        **E cio' che e' gia' uscito dalle cuffie non si tocca.** Si ristira solo
        da `consumed` in poi, quindi non c'e' niente da rimediare a posteriori e
        il punto di giunzione cade dove l'orecchio non e' ancora arrivato. Se il
        rate necessario esce dai limiti si applica il limite e si sfora lo
        stesso: si sfora, non si scarta.

        Restituisce il rate applicato (1.0 se non c'era niente da fare).
        """
        from mix.stretch import time_stretch

        with self._lock:
            corrente = next(
                (s for s in self._queue if s.consumed > 0 and not s.done), None
            )
            if corrente is None:
                return 1.0
            residuo = corrente.audio[corrente.consumed :]
            # **Sotto un certo residuo si sfora invece di stringere.** Tutta la
            # compressione di `hurry` cade sulla coda, cioe' esattamente
            # sull'ultima parola — quella che chiude il senso della frase. Con la
            # guardia a 150 ms si stringeva ancora quella, e all'ascolto la
            # battuta sembrava interrompersi a meta' parola. Mezzo secondo
            # scarso e' una parola o due: guadagnare due decimi accelerandole
            # costa piu' di quanto renda, perche' uno sforamento di due decimi
            # non lo nota nessuno mentre una parola finale impastata si sente
            # sempre.
            if len(residuo) < int(max(0.0, min_residue) * self.samplerate):
                return 1.0
            # **Il tetto vale sul totale, non su questo stadio.** Questa battuta
            # e' gia' arrivata accelerata: comprimerla di nuovo fino al limite
            # moltiplica le due accelerazioni. Misurato dal vivo, una battuta a
            # 1,550 riceveva la fretta a 1,550 e la coda usciva a **2,40x** —
            # ciascuno stadio dentro il limite, insieme molto fuori, e
            # all'ascolto la frase non finiva: veniva inghiottita. Se il budget
            # e' gia' speso non si stringe, e si sfora: si sfora, non si scarta.
            resto = limits[1] / max(1e-6, corrente.rate)
            if resto <= 1.001:
                return 1.0
            disponibile = t_finish - self._t
            if disponibile <= 0:
                rate = limits[1]
            else:
                rate = (len(residuo) / self.samplerate) / disponibile
            if rate <= 1.001:
                return 1.0
            rate = float(np.clip(rate, max(1.0, limits[0]), resto))
            stretto = time_stretch(residuo, rate, samplerate=self.samplerate)
            corrente.audio = np.concatenate(
                [corrente.audio[: corrente.consumed], stretto]
            ).astype(np.float32)
            corrente.rate *= rate  # il totale speso, per la prossima volta
            self._n_hurried.inc()
            return rate

    def clear(self) -> int:
        with self._lock:
            n = len(self._queue)
            self._queue.clear()
        self._n_dropped.inc(n)
        return n

    # -- elaborazione ------------------------------------------------------

    def process(self, game: np.ndarray | None, n: int | None = None) -> np.ndarray:
        """Elabora un blocco e restituisce lo stereo da mandare in uscita.

        `game` puo' essere None (nessun passthrough): in quel caso esce la sola
        voce italiana, e serve a `n` per sapere quanto lungo dev'essere il blocco.
        """
        if game is not None:
            game = np.asarray(game, dtype=np.float32)
            if game.ndim == 1:
                game = np.stack([game, game], axis=1)
            if game.ndim != 2 or game.shape[1] != 2:
                raise ValueError(f"attesa forma (n, 2), ricevuta {game.shape}")
            n = game.shape[0]
        elif n is None:
            raise ValueError("senza audio di gioco serve la lunghezza del blocco")

        t0 = self._t
        t1 = t0 + n / self.samplerate

        dub = np.zeros(n, dtype=np.float32)
        active = False
        with self._lock:
            for item in self._queue:
                if item.t_start >= t1 or item.done:
                    continue
                # Dove cade, dentro questo blocco, l'inizio della parte da versare.
                offset = max(0, int(round((item.t_start - t0) * self.samplerate)))
                if item.consumed > 0:
                    offset = 0
                take = min(n - offset, item.remaining)
                if take <= 0:
                    continue
                dub[offset : offset + take] += (
                    item.audio[item.consumed : item.consumed + take] * item.gain
                )
                item.consumed += take
                active = True
            self._queue = [s for s in self._queue if not s.done]
            imminente = self._starts_soon(t1)

        envelope = self.envelope.block(n, active or imminente)
        if game is not None and self.passthrough:
            out = duck_center(game, envelope)
        else:
            out = np.zeros((n, 2), dtype=np.float32)

        voice = dub * self.dub_gain
        out[:, 0] += voice
        out[:, 1] += voice

        self._t = t1
        return self._limit(out)

    def _starts_soon(self, t1: float) -> bool:
        """Sta per iniziare una battuta, abbastanza presto da non rialzare?

        Due motivi diversi, e il secondo e' costato una sessione d'ascolto.

        **Non rialzare troppo tardi.** Abbassare il gioco *mentre* la voce parte
        la lascerebbe coperta per i primi quaranta millisecondi, che sono quelli
        in cui l'orecchio decide se ha capito o no. Da qui l'anticipo pari al
        tempo di attacco.

        **E non rialzare affatto, se sta per riabbassarsi.** Nel dialogo fitto
        le battute si incatenano a 120 ms l'una dall'altra: il rilascio da 220 ms
        fa risalire il gioco a meta' strada, e quaranta millisecondi dopo lo
        rischiaccia. Sono otto decibel su e giu' ogni centosessanta
        millisecondi, sull'audio del gioco e non sulla voce — all'ascolto si
        taglia tutto. Il duck resta quindi giu' per `hold_seconds` se un'altra
        battuta arriva entro quel tempo: una risalita che deve subito tornare
        indietro non e' un rilascio, e' un difetto.
        """
        lookahead = max(self.envelope.attack_seconds, self.hold_seconds)
        return any(t1 <= s.t_start <= t1 + lookahead for s in self._queue)

    def _limit(self, x: np.ndarray) -> np.ndarray:
        """Limitatore morbido: comprime i picchi invece di tagliarli."""
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        if peak <= 1.0:
            return x
        self._n_clipped.inc()
        return np.tanh(x * 0.9).astype(np.float32)

    def reset(self, t: float = 0.0) -> None:
        self._queue.clear()
        self.envelope.reset()
        self._t = t
