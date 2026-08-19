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
    """Una battuta in attesa del proprio turno.

    **Puo' essere ancora aperta**, cioe' il sintetizzatore la sta ancora
    producendo. E' l'unica cosa che lo streaming aggiunge al mixer, e cambia il
    significato di una sola parola: `done` non e' piu' "i campioni sono finiti" ma
    "i campioni sono finiti **e** non ne arrivano altri". Un array che finisce non
    e' una battuta che finisce, finche' qualcuno sta ancora scrivendo in coda.
    """

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
    # -- streaming ---------------------------------------------------------
    # Arriveranno altri campioni? Finche' e' vera la battuta non e' finita
    # nemmeno quando l'array e' esaurito.
    aperta: bool = False
    # Quanto ci si aspetta che duri **in tutto**, in secondi, mentre e' aperta.
    # Serve a `finisce_a`, che senza sotto-stimerebbe: la battuta dopo verrebbe
    # messa in fila sopra questa e le due voci si sovrapporrebbero, che e' il
    # difetto peggiore di tutti.
    durata_attesa: float = 0.0
    # La compressione da applicare a cio' che **deve ancora arrivare**. `hurry`
    # stringe il residuo gia' presente; senza questa, i blocchi successivi
    # tornerebbero a velocita' naturale e la battuta cambierebbe passo a meta'.
    rate_futuro: float = 1.0
    # Il mixer l'ha buttata via mentre il produttore ci scriveva ancora: chi
    # produce lo legge e smette.
    annullata: bool = False

    @property
    def remaining(self) -> int:
        return max(0, len(self.audio) - self.consumed)

    @property
    def done(self) -> bool:
        return self.consumed >= len(self.audio) and not self.aperta

    @property
    def a_secco(self) -> bool:
        """Aperta ma senza campioni pronti: il sintetizzatore non sta stando dietro."""
        return self.aperta and self.consumed >= len(self.audio)


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
        prebuffer_ms: float = 350.0,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.samplerate = samplerate
        self.passthrough = passthrough
        # Quanti campioni devono esserci prima che una battuta **aperta** cominci
        # a suonare. Si veda `_da_riempire`.
        self._cuscino = int(max(0.0, prebuffer_ms) / 1000.0 * samplerate)
        self.hold_seconds = max(0.0, hold_ms / 1000.0)
        self.dub_gain = db_to_gain(dub_gain_db)
        self.envelope = DuckEnvelope(samplerate, duck_db, attack_ms, release_ms)
        # La fotografia dei sei numeri con cui si e' costruito: serve a `ritara`
        # per non rifare l'inviluppo cento volte al secondo. Si veda li'.
        self._tarature = (duck_db, attack_ms, release_ms, dub_gain_db,
                          bool(passthrough), hold_ms)
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
        # **Quante volte una battuta in streaming e' rimasta a secco**, cioe' era
        # il suo turno di suonare e i campioni non c'erano ancora. E' il numero
        # che dice se lo streaming regge: il modello sta avanti al tempo reale
        # (0,74x misurato), ma se la catena gli chiede anche di comprimere, il
        # margine si mangia. Senza questo contatore un difetto del genere si
        # sente e non si misura, che e' il modo in cui questo progetto ha gia'
        # perso due sessioni.
        self._n_secco = self.metrics.counter("mix.underrun")
        # **Blocchi passati ad aspettare che una battuta si riempisse.** Diverso
        # dall'underrun: qui la battuta non e' ancora partita, quindi non si sente
        # niente di rotto — si sente solo un po' piu' tardi. Tenerli separati e'
        # cio' che permette di dire "e' lenta" invece di "e' rotta".
        self._n_attesa = self.metrics.counter("mix.prebuffer")
        # **Di quanto il muro e' avanti al contatore dei campioni**, a ogni
        # blocco. Se resta a zero i due vanno insieme; se cresce, il mixer stava
        # suonando in una linea temporale sua — e questa e' la misura che
        # mancava, quella che rendeva invisibile un ritardo che si sentiva.
        self._t_deriva = self.metrics.timer("mix.deriva")

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

        **Una battuta aperta e' l'unica eccezione, e deve esserlo.** Li' i campioni
        che ci sono non sono tutti quelli che ci saranno, quindi si usa la durata
        attesa — che e' una stima, ma sbagliarla per difetto vorrebbe dire mettere
        in fila la battuta dopo *sopra* questa, e due voci italiane sovrapposte
        sono il difetto che tutto lo scheduler esiste per evitare. Fra sbagliare
        lungo e sbagliare corto, qui si sbaglia lungo.
        """
        with self._lock:
            if not self._queue:
                return self._t
            return max(self._fine(s) for s in self._queue)

    def _fine(self, s: Scheduled) -> float:
        base = max(s.t_start, self._t)
        pronta = base + s.remaining / self.samplerate
        if not s.aperta:
            return pronta
        attesa = s.t_start + max(0.0, s.durata_attesa) / max(1e-6, s.rate_futuro)
        return max(pronta, attesa)

    @property
    def speaking(self) -> bool:
        """C'e' una battuta gia' iniziata e non ancora finita."""
        return any(s.consumed > 0 and not s.done for s in self._queue)

    def ritara(self, mix) -> bool:
        """Rilegge i volumi da `cfg.mix` **a sessione accesa**, e dice se e' cambiato qualcosa.

        Esiste perche' senza di lei i sei campi dei volumi erano **dichiarati
        caldi e non lo erano**: `DubPipeline` li versa qui dentro nel proprio
        costruttore e poi non li rilegge mai piu'. Il pannello scriveva
        `mix.duck_db = -20` e non succedeva niente, con la riga verde nel
        registro — ed e' la nona volta della forma «dichiarato e mai letto» in
        questo progetto. Un volume che chiede di ripremere Avvia non e' un
        volume: e' un valore di partenza.

        **Si confronta prima di ricostruire**, perche' chi la chiama la chiama a
        ogni blocco da 10 ms: rifare l'inviluppo a ogni giro azzererebbe il
        guadagno corrente cento volte al secondo, cioe' il duck non scenderebbe
        mai. Cosi' invece l'oggetto nuovo nasce solo quando un numero e'
        cambiato davvero, e **si porta dietro il guadagno di adesso**: cambiare
        il volume mentre un personaggio parla non deve far risalire il gioco di
        scatto in mezzo a una battuta.
        """
        nuovo = (mix.duck_db, mix.duck_attack_ms, mix.duck_release_ms,
                 mix.dub_gain_db, bool(mix.passthrough), mix.duck_hold_ms)
        if nuovo == getattr(self, "_tarature", None):
            return False
        self._tarature = nuovo
        self.passthrough = bool(mix.passthrough)
        self.hold_seconds = max(0.0, mix.duck_hold_ms / 1000.0)
        self.dub_gain = db_to_gain(mix.dub_gain_db)
        dov_era = self.envelope.gain
        self.envelope = DuckEnvelope(
            self.samplerate, mix.duck_db, mix.duck_attack_ms, mix.duck_release_ms)
        self.envelope.gain = dov_era
        return True

    def schedule(
        self,
        audio: np.ndarray,
        t_start: float,
        gain_db: float = 0.0,
        speaker_id: str = "?",
        text: str = "",
        rate: float = 1.0,
        aperta: bool = False,
        durata_attesa: float = 0.0,
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
            aperta=aperta,
            durata_attesa=durata_attesa,
            rate_futuro=rate,
        )
        with self._lock:
            if item.t_start < self._t:
                self._n_late.inc()
                item.t_start = self._t
            self._queue.append(item)
        self._n_played.inc()
        return item

    def append(self, item: Scheduled, audio: np.ndarray, *, chiudi: bool = False) -> None:
        """Aggiunge campioni a una battuta ancora aperta.

        La chiama il produttore — il thread che sta sintetizzando — mentre il
        thread audio sta gia' suonando i campioni di prima. **Il lucchetto e' lo
        stesso della coda e non uno nuovo**: `process` legge `item.audio` mentre
        questa lo riscrive, e due lucchetti diversi sullo stesso dato sono un
        lucchetto solo scritto male.

        `rate_futuro` si applica **qui**, all'arrivo. Se `hurry` ha stretto il
        residuo perche' e' arrivato un altro sottotitolo, i blocchi che seguono
        devono arrivare stretti uguale: altrimenti la battuta accelera e poi
        rallenta a meta', che all'ascolto e' peggio che restare lenta.
        """
        a = np.asarray(audio, dtype=np.float32).reshape(-1)
        with self._lock:
            if item.annullata:
                return
            if a.size and item.rate_futuro > 1.001:
                from mix.stretch import time_stretch

                a = time_stretch(a, item.rate_futuro, samplerate=self.samplerate)
            if a.size:
                item.audio = np.concatenate([item.audio, a]).astype(np.float32)
            if chiudi:
                item.aperta = False

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
            # **Su una battuta aperta il residuo presente non e' il residuo.** Cio'
            # che c'e' nell'array e' solo quanto il sintetizzatore ha fatto in
            # tempo a consegnare: guardare quello vorrebbe dire misurare la
            # velocita' del produttore invece della lunghezza della battuta, e
            # concludere ogni volta "manca pochissimo, non stringo" — cioe'
            # spegnere `hurry` proprio dove serve. Si guarda quanto **durera'**.
            resta_s = max(
                len(residuo) / self.samplerate,
                self._fine(corrente) - self._t if corrente.aperta else 0.0,
            )
            # **Sotto un certo residuo si sfora invece di stringere.** Tutta la
            # compressione di `hurry` cade sulla coda, cioe' esattamente
            # sull'ultima parola — quella che chiude il senso della frase. Con la
            # guardia a 150 ms si stringeva ancora quella, e all'ascolto la
            # battuta sembrava interrompersi a meta' parola. Mezzo secondo
            # scarso e' una parola o due: guadagnare due decimi accelerandole
            # costa piu' di quanto renda, perche' uno sforamento di due decimi
            # non lo nota nessuno mentre una parola finale impastata si sente
            # sempre.
            if resta_s < max(0.0, min_residue):
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
                rate = resta_s / disponibile
            if rate <= 1.001:
                return 1.0
            rate = float(np.clip(rate, max(1.0, limits[0]), resto))
            if residuo.size:
                stretto = time_stretch(residuo, rate, samplerate=self.samplerate)
                corrente.audio = np.concatenate(
                    [corrente.audio[: corrente.consumed], stretto]
                ).astype(np.float32)
            corrente.rate *= rate  # il totale speso, per la prossima volta
            if corrente.aperta:
                # Cio' che deve ancora arrivare va stretto uguale: `append` lo fa
                # all'ingresso. Senza, la battuta si comprime fino a dove il
                # sintetizzatore era arrivato e poi torna lenta.
                corrente.rate_futuro *= rate
            self._n_hurried.inc()
            return rate

    def clear(self) -> int:
        """Svuota la coda. Le battute aperte vengono **annullate**, non dimenticate.

        Un produttore che sta ancora sintetizzando tiene un riferimento al proprio
        `Scheduled`: senza il contrassegno continuerebbe a versare campioni in un
        oggetto che non sta piu' in coda, cioe' a lavorare per un'uscita che
        nessuno ascoltera' — e a farlo finche' non finisce la battuta, occupando
        la GPU mentre la battuta nuova aspetta il suo turno.
        """
        with self._lock:
            n = len(self._queue)
            for s in self._queue:
                s.annullata = True
                s.aperta = False
            self._queue.clear()
        self._n_dropped.inc(n)
        return n

    # -- elaborazione ------------------------------------------------------

    def process(
        self, game: np.ndarray | None, n: int | None = None, t: float | None = None
    ) -> np.ndarray:
        """Elabora un blocco e restituisce lo stereo da mandare in uscita.

        `game` puo' essere None (nessun passthrough): in quel caso esce la sola
        voce italiana, e serve a `n` per sapere quanto lungo dev'essere il blocco.

        **`t` e' che ora e' davvero**, e senza di lei questo mixer non ha un
        orologio: ha un contatore di campioni. `self._t` avanzava di `n /
        samplerate` a ogni blocco, cioe' misurava *quanto audio e' passato*, non
        *quanto tempo e' passato*. Sono la stessa cosa solo se i campioni
        arrivano tutti.

        Dal vivo non arrivano. Misurato su una sessione di diciannove minuti:
        l'orologio della sessione arriva a 1155,7 s mentre l'audio processato e'
        1150,4 — **cinque secondi e tre che il mixer non ha mai contato**, e il
        divario cresce.

        Le conseguenze sono due, e la seconda e' peggiore della prima. Una
        battuta viene programmata a `t_start`, che si calcola dall'orologio della
        sessione; il mixer la suona quando il *contatore* arriva a quel numero,
        cioe' D secondi di tempo vero piu' tardi. **E nel registro non si vede**:
        il log scrive `t_start`, che e' l'istante in cui la battuta era pronta —
        il riconoscimento e la scelta della voce — non l'istante in cui si e'
        sentita. E' esattamente il difetto dell'anello di ieri, in un altro
        posto: una quantita' che si comporta da orologio senza esserlo.

        `max` e non assegnazione secca: il tempo non torna indietro. Se il
        dispositivo consegna audio piu' in fretta del muro il contatore resta
        avanti, ed e' il verso innocuo — le battute partono appena possono. Nel
        verso opposto si recupera il divario in una volta, e cio' che era
        programmato nell'intervallo saltato parte subito, che e' cio' che si
        vuole.
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
        if t is not None and t > t0:
            # Il muro e' avanti al contatore: si recupera, e si conta di quanto.
            self._t_deriva.add((t - t0) * 1000.0)
            t0 = t
        t1 = t0 + n / self.samplerate

        dub = np.zeros(n, dtype=np.float32)
        active = False
        with self._lock:
            for item in self._queue:
                if item.t_start >= t1 or item.done:
                    continue
                # **Una battuta aperta non parte finche' non ha un cuscino.**
                #
                # E' il difetto che una prova dal vivo ha trovato e che il banco
                # non poteva vedere: li' il produttore genera tutto e *poi*
                # ritorna, quindi i campioni ci sono sempre. Dal vivo il
                # produttore lavora un turno alla volta, e `t_start` veniva
                # calcolato dalla fine **prevista** della battuta precedente —
                # cioe' la successiva cominciava a suonare nell'istante esatto in
                # cui la sua generazione cominciava. Il mixer apriva la bocca, non
                # trovava niente, versava silenzio, e le parole arrivavano a
                # goccia: all'ascolto **parole sminuzzate**, con il contenuto
                # sempre piu' indietro del video.
                #
                # Aspettare un cuscino costa un ritardo pari al cuscino, una volta
                # per battuta. Non aspettarlo costa la battuta intera.
                if self._da_riempire(item):
                    # Non e' partita: si sposta l'inizio invece di accumulare
                    # ritardo. E **non e' un underrun** — quello e' restare a
                    # secco *dopo* aver cominciato, che si sente e va contato a
                    # parte. Confonderli renderebbe illeggibile il contatore che
                    # serve proprio a decidere se questo motore regge.
                    item.t_start = max(item.t_start, t1)
                    self._n_attesa.inc()
                    active = True  # il duck resta giu': la battuta sta arrivando
                    continue
                # Dove cade, dentro questo blocco, l'inizio della parte da versare.
                offset = max(0, int(round((item.t_start - t0) * self.samplerate)))
                if item.consumed > 0:
                    offset = 0
                take = min(n - offset, item.remaining)
                if take <= 0:
                    # **Una battuta aperta senza campioni pronti e' un buco, e va
                    # contato qui.** Non si puo' concluderne che sia finita — lo
                    # dice `done`, che su una battuta aperta e' falso — quindi il
                    # blocco esce muto e si riprende appena il produttore
                    # consegna. Il duck resta giu' perche' `active` non e' l'unica
                    # cosa che lo tiene giu': la battuta e' ancora in coda.
                    if item.a_secco and item.t_start <= t0:
                        self._n_secco.inc()
                        active = True  # non rialzare il gioco dentro una battuta
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

    def _da_riempire(self, s: Scheduled) -> bool:
        """La battuta e' aperta, non e' ancora partita, e ha troppo poco dentro.

        Solo prima di cominciare: una volta partita non si aspetta piu' niente,
        perche' fermarsi a meta' per aspettare sarebbe un buco in mezzo a una
        parola — peggio di andare avanti.
        """
        if not s.aperta or s.consumed > 0:
            return False
        return len(s.audio) < self._cuscino

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
        with self._lock:
            for s in self._queue:
                s.annullata = True
                s.aperta = False
            self._queue.clear()
        self.envelope.reset()
        self._t = t
