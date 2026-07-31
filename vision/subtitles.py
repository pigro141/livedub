"""Da letture per-frame a battute con un inizio e una fine.

Fra l'OCR e il resto della pipeline manca un pezzo di ragionamento. L'OCR
risponde alla domanda "cosa c'e' scritto adesso"; il doppiaggio ha bisogno di
sapere "quando e' comparsa una battuta nuova" e "quanto e' rimasta a schermo".
Sono domande diverse, e le insidie stanno tutte qui:

- un sottotitolo appare in **dissolvenza**, e la prima lettura cade su lettere
  mezze trasparenti: e' la lettura piu' probabile da sbagliare, e sarebbe anche
  quella che va in onda. Per questo una battuta si conferma solo dopo
  `stable_reads` letture concordi;
- confermare costa tempo, ma la battuta e' **comparsa prima**. Il `t_on` che
  finisce nell'evento e' quello della *prima* lettura, non della conferma: cosi'
  il conto della latenza resta onesto invece di regalarsi un frame;
- l'OCR sbaglia un carattere ogni tanto senza che il sottotitolo sia cambiato.
  Il confronto e' quindi per **somiglianza**, non per uguaglianza, altrimenti
  ogni sfarfallio verrebbe letto come una battuta nuova e il doppiatore
  ricomincerebbe la frase da capo;
- una riga puo' sparire per un solo frame e tornare. `hold_frames` evita di
  chiudere una battuta ancora in corso;

- **una battuta non ha un posto fisso.** La prima versione teneva lo stato in un
  dizionario indicizzato per classe e posizione (`white#0`, `white#1`), il che
  sembra ovvio finche' a schermo c'e' solo il dialogo. Sulla registrazione vera
  una banda di texture — un cordolo, una striscia bianca — viene classificata
  bianca, si infila *sopra* la riga vera e le sposta l'indice: la stessa frase
  diventa `white#1` e il tracker la legge come una battuta nuova. Misurato: 55
  aperture in 50 secondi dove ne servivano una ventina. L'identita' di una
  battuta e' il suo **testo**, non la sua riga, quindi l'abbinamento e' per
  somiglianza fra tutte le attive della stessa classe.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher

from core.config import VisionConfig
from core.types import LineClass, SubtitleEvent


def normalize(text: str) -> str:
    """Forma di confronto: **solo lettere e cifre**, minuscole, senza accenti.

    Serve solo a decidere se due letture sono *la stessa battuta*. Il testo che
    va in sintesi resta quello originale.

    Perche' cosi' aggressiva: la prima versione appiattiva maiuscole e spazi, e
    lasciava passare tutto il resto. Ma cio' che l'OCR non riproduce due volte
    uguale e' esattamente *il resto*. Misurato sulla registrazione:

    - `'Ma domani...'` contro `'Madomani.'` — 0,857, appena sotto la soglia di
      0,88, e sono la stessa identica battuta letta a due frame di distanza;
    - `'Saremo insieme!'` contro `'Saremoinsieme！！'` — il riconoscitore emette
      punteggiatura a **larghezza intera** (`！`, `，`, `：`) quando il glifo e'
      sfocato, e per il confronto quello e' un carattere diverso;
    - `'. Toc toc, negri!'`, `'——octoc，negri！'`, `'"1 Fanculo al...'`, `'→Dalle
      palle'` — un frammento di scena in testa alla riga si legge come un glifo
      spurio, e sposta il rapporto quanto una lettera vera.

    Su una battuta corta ognuno di questi vale diversi punti percentuali, e la
    battuta viene riaperta. Togliere tutto cio' che non e' lettera o cifra
    elimina la classe intera di questi casi invece di inseguirli uno per uno.

    `NFKD` fa due lavori in un colpo: riporta i caratteri a larghezza intera
    alla loro forma normale e scompone le accentate in lettera + segno, e il
    segno cade con la punteggiatura. Cosi' `perche'` e `perche` — che l'OCR
    scambia di continuo — diventano la stessa cosa.
    """
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in folded if ch.isalnum())


def similarity(a: str, b: str) -> float:
    """Somiglianza fra due letture, 0..1."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def contenimento(a: str, b: str, min_blocco: int = 3) -> float:
    """Quanto del piu' corto e' gia' dentro il piu' lungo, 0..1.

    **E' una domanda diversa da `similarity`, e la differenza e' tutto il
    capitolo dei doppioni.** Il rapporto tratta i due testi da pari: un
    frammento contro la battuta intera fa un rapporto basso, perche' meta' della
    seconda non ha corrispondenza — eppure sono la stessa battuta, letta due
    volte. Misurato sulle riletture di una sessione dal vivo (13 coppie marcate
    a mano contro 217 battute distinte):

        confronto                prende      ne sbaglia
        rapporto >= 0,90          0 / 13          0
        rapporto >= 0,80          2 / 13          1
        contenimento >= 0,80      8 / 13          0

    Il cancello che c'era non ne prendeva **nessuna**.

    **I blocchi sotto tre caratteri non contano, e quella riga e' la differenza
    fra una misura e un rumore.** Sommandoli tutti, `'rapporto diventa
    complicato'` risultava contenuto al 100% dentro `'E cosi' che funziona, non
    lo sai?'` — due frasi tenute insieme da una dozzina di lettere sparse. Con
    il minimo a tre quella coppia fa 0,00 e le riletture vere restano a 0,90 e
    1,00. (Poi si e' scoperto che quelle due erano davvero la stessa battuta, la
    seconda essendone la coda; ma la controprova valeva lo stesso, ed e' l'unico
    motivo per cui il numero e' credibile.)

    Le cinque riletture che sfuggono sono tutte OCR cosi' storpiato da non avere
    piu' tre lettere di fila in comune (`'4hoot di Zapho:'` contro `'n Aoenh di
    Zapho!'`). Quelle non le prende nessun confronto fra testi.
    """
    if not a or not b:
        return 0.0
    corto, lungo = (a, b) if len(a) <= len(b) else (b, a)
    m = SequenceMatcher(None, corto, lungo)
    combacia = sum(bl.size for bl in m.get_matching_blocks() if bl.size >= min_blocco)
    return combacia / len(corto)


def wrong_chars(a: str, b: str) -> float:
    """Quanti caratteri separano due letture normalizzate.

    Il rapporto di `similarity` e' comodo ma ha la forma sbagliata per la
    domanda "e' la stessa battuta?": una soglia in percentuale tollera un numero
    di errori proporzionale alla lunghezza, mentre l'OCR sbaglia **una lettera
    ogni tanto** e non una quota del testo. Misurato sulla registrazione:
    `piantaladawwero` contro `piantaladavvero` — due lettere su quindici — fa
    0,867, sotto una soglia di 0,88 che le stesse due lettere su una frase di
    quarantacinque caratteri non avrebbero mai sfiorato. La battuta corta
    veniva riaperta e quella lunga no, per un motivo che non ha niente a che
    vedere con quanto sono diverse.

    Qui si torna ai caratteri: dal rapporto si ricava quanti ne combaciano, e si
    restituisce quanti restano fuori nella piu' lunga delle due.
    """
    if not a or not b:
        return float(max(len(a), len(b)))
    matched = SequenceMatcher(None, a, b).ratio() * (len(a) + len(b)) / 2.0
    return max(0.0, max(len(a), len(b)) - matched)


@dataclass(slots=True)
class _Pending:
    """Candidata in attesa di conferma."""

    norm: str
    text: str
    count: int
    first_t: float
    cls: LineClass
    lines: tuple = ()
    last_seen: float = 0.0
    missing: int = 0


@dataclass(slots=True)
class _Tracked:
    """Battuta confermata e ancora a schermo."""

    event: SubtitleEvent
    last_seen: float = 0.0
    missing: int = 0


@dataclass(slots=True)
class TrackerOutput:
    """Cosa e' cambiato in questa passata."""

    opened: list[SubtitleEvent] = field(default_factory=list)
    closed: list[SubtitleEvent] = field(default_factory=list)
    # **Le battute il cui testo e' migliorato mentre erano a schermo**, come
    # coppie (com'era, com'e'). Servono a chi tiene in mano l'evento di prima:
    # `SubtitleEvent` e' congelato, quindi migliorare il testo crea un oggetto
    # nuovo e quello vecchio resta buono solo per chi non lo sa. La pipeline lo
    # tiene in coda per mezzo secondo prima di parlare — tempo in cui la lettura
    # migliora quasi sempre — e senza questa lista direbbe il frammento.
    updated: list[tuple[SubtitleEvent, SubtitleEvent]] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return bool(self.opened or self.closed or self.updated)


class SubtitleTracker:
    """Tiene lo stato dei sottotitoli a schermo.

    Funziona sia se alimentato a ogni frame sia se alimentato solo quando il
    rilevatore di cambiamento sveglia l'OCR: il conteggio delle assenze e'
    sulle *passate*, non sui frame.
    """

    def __init__(self, cfg: VisionConfig) -> None:
        self.cfg = cfg
        self._active: dict[int, _Tracked] = {}
        self._pending: dict[int, _Pending] = {}
        self._next_id = 0

    # -- stato -------------------------------------------------------------

    @property
    def active(self) -> list[SubtitleEvent]:
        return [tr.event for tr in self._active.values()]

    def reset(self) -> None:
        self._active.clear()
        self._pending.clear()
        self._next_id = 0

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    # -- alimentazione -----------------------------------------------------

    def feed(
        self, candidates: list[SubtitleEvent], t: float, certain: bool = False
    ) -> TrackerOutput:
        """Passa le battute lette in questo istante. Restituisce cosa e' nato e
        cosa e' morto.

        `certain=True` significa "so per certo che quello che manca non c'e'
        piu'": chi chiama ha una prova indipendente dall'OCR, tipicamente il
        rilevatore di cambiamento che ha visto sparire l'inchiostro. In quel
        caso l'assenza si applica subito.

        La distinzione non e' pedanteria, e' l'asse portante della chiusura.
        **Che l'OCR non legga una battuta non e' una prova che sia sparita**: e'
        molto piu' spesso una prova che il frame era difficile. Chi ha la prova
        vera e' il diff, e la porta con `certain`. Quindi la scadenza per
        silenzio puo' essere generosa: sbagliarla per eccesso allunga una durata
        di qualche decimo, sbagliarla per difetto spezza la battuta in due e
        avvelena la calibrazione del tempo con due durate false.
        """
        out = TrackerOutput()
        matched_active: set[int] = set()
        matched_pending: set[int] = set()
        unmatched: list[tuple[SubtitleEvent, str]] = []

        # 1. Le candidate che continuano una battuta gia' a schermo. E' il caso
        #    di gran lunga piu' frequente: un sottotitolo resta per decine di
        #    frame e a ogni passata si ritrova identico a se stesso.
        for cand in candidates:
            norm = normalize(cand.text)
            if not norm:
                continue
            aid = self._best(self._active, cand.cls, norm, matched_active, lambda tr: normalize(tr.event.text))
            if aid is not None:
                matched_active.add(aid)
                self._active[aid].last_seen = t
                self._active[aid].missing = 0
            else:
                unmatched.append((cand, norm))

        # 2. Le altre: o confermano una candidata in attesa, o ne aprono una.
        for cand, norm in unmatched:
            pid = self._best(self._pending, cand.cls, norm, matched_pending, lambda p: p.norm)
            if pid is None:
                pid = self._new_id()
                self._pending[pid] = _Pending(
                    norm=norm,
                    text=cand.text,
                    count=1,
                    first_t=cand.t_on,
                    cls=cand.cls,
                    lines=cand.lines,
                    last_seen=t,
                )
            else:
                pending = self._pending[pid]
                pending.count += 1
                pending.last_seen = t
                pending.missing = 0
                # Fra due letture concordi si tiene la piu' ricca: la dissolvenza
                # toglie caratteri, non ne aggiunge.
                if len(cand.text) > len(pending.text):
                    pending.text = cand.text
                    pending.lines = cand.lines
            matched_pending.add(pid)

            pending = self._pending[pid]
            if pending.count < max(1, self.cfg.stable_reads):
                continue

            # Conferma. Se a schermo c'era **una sola** battuta della stessa
            # classe e non e' stata ritrovata, questa la sostituisce e quella si
            # chiude adesso: una battuta che lascia il posto alla successiva
            # senza passare per lo schermo vuoto finirebbe altrimenti a durare
            # un `hold_seconds` di troppo. Con piu' di una candidata a
            # sostituirla non si sa quale sia, e si lascia decidere alla scadenza.
            orphans = [
                a
                for a, tr in self._active.items()
                if a not in matched_active and tr.event.cls is pending.cls
            ]
            if len(orphans) == 1:
                # Ma prima: la sostituzione e' anche la strada per cui una
                # battuta si spezza. Misurato sui 27 minuti, 752 chiusure su
                # 1177 passano di qui, e l'80% di quelle e' seguita subito da
                # una riapertura di testo somigliante — cioe' erano la stessa
                # battuta, letta abbastanza male da non rientrare nel budget di
                # caratteri ma non abbastanza da essere un'altra frase.
                #
                # Allargare il budget generale le recupererebbe, al prezzo di
                # fondere battute davvero diverse (`Sali sulla moto` e `Sali
                # sulla macchina` distano sei caratteri). Qui invece il confronto
                # e' fra due sole candidate — la nuova e l'unica orfana — e la
                # domanda e' piu' facile: si somigliano tanto da essere la
                # stessa? In quel caso non si sostituisce, si **continua**:
                # l'orfana resta aperta col suo `t_on`, e prende la lettura piu'
                # ricca fra le due.
                keeper = self._active[orphans[0]]
                if self._continua(normalize(keeper.event.text), pending.norm):
                    if len(pending.text) > len(keeper.event.text):
                        vecchio = keeper.event
                        keeper.event = replace(keeper.event, text=pending.text, lines=pending.lines)
                        out.updated.append((vecchio, keeper.event))
                    keeper.last_seen = t
                    keeper.missing = 0
                    matched_active.add(orphans[0])
                    del self._pending[pid]
                    continue
                old = self._active.pop(orphans[0])
                out.closed.append(old.event.closed(t))

            event = SubtitleEvent(
                text=pending.text, cls=pending.cls, t_on=pending.first_t, lines=pending.lines
            )
            self._active[pid] = _Tracked(event, last_seen=t)
            matched_active.add(pid)
            out.opened.append(event)
            del self._pending[pid]

        self._expire(matched_active, matched_pending, t, out, force=certain)
        return out

    def _continua(self, vecchia: str, nuova: str) -> bool:
        """La lettura nuova e' la stessa battuta di quella orfana, o un'altra?

        Due domande, non una, perche' le riletture arrivano in due forme.

        *Si somigliano* — l'OCR ha sbagliato qualche lettera qua e la'. E' il
        caso che `continue_similarity` gia' copriva.

        *Una e' dentro l'altra* — l'OCR ha letto la battuta mentre compariva e
        ne ha preso un pezzo, oppure ne ha ripreso solo la coda. Qui il rapporto
        crolla (0,63 su una coppia che e' la stessa frase) perche' meta' del
        testo lungo non ha corrispondenza, e la battuta veniva **riaperta**: un
        secondo evento, una seconda sintesi, e la stessa frase detta due volte.
        Misurato dal vivo, una battuta di Lamar letta **tre volte** ha messo in
        coda 6,6 secondi di parlato in piu' e ci sono voluti 22 secondi per
        smaltirli.

        La lunghezza minima serve a non far sparire le battute vere corte:
        `'Segui.'` e `'Se qui'` sono sei caratteri, e su testi cosi' brevi
        qualunque misura di contenimento dice quello che le si chiede.
        """
        if similarity(vecchia, nuova) >= self.cfg.continue_similarity:
            return True
        if min(len(vecchia), len(nuova)) < self.cfg.continue_min_chars:
            return False
        return contenimento(vecchia, nuova) >= self.cfg.continue_containment

    def _budget(self, a: str, b: str) -> float:
        """Quanti caratteri di scarto si accettano fra due letture.

        Un minimo fisso, perche' l'OCR sbaglia qualche lettera su qualunque
        lunghezza, piu' una quota della lunghezza, perche' su una frase lunga di
        occasioni di sbagliare ce ne sono di piu'.
        """
        longest = max(len(a), len(b))
        return max(float(self.cfg.max_wrong_chars), self.cfg.max_wrong_frac * longest)

    def _best(self, pool: dict, cls: LineClass, norm: str, taken: set, text_of) -> int | None:
        """L'elemento del gruppo piu' somigliante, entro lo scarto. `None` se nessuno.

        Si sceglie il **migliore** e non il primo accettabile: con due battute
        della stessa classe a schermo — che e' il caso di una frase andata a capo
        letta come due righe — il primo accettabile puo' essere l'altra.
        """
        best_id, best_score = None, -1.0
        for key, item in pool.items():
            if key in taken:
                continue
            item_cls = item.cls if isinstance(item, _Pending) else item.event.cls
            if item_cls is not cls:
                continue
            other = text_of(item)
            if wrong_chars(other, norm) > self._budget(other, norm):
                continue
            score = similarity(other, norm)
            if score >= best_score:
                best_id, best_score = key, score
        return best_id

    def close_all(self, t: float) -> list[SubtitleEvent]:
        """Chiude tutto. Da chiamare a fine sessione o a fine replay, altrimenti
        l'ultima battuta resterebbe senza durata."""
        closed = [tr.event.closed(t) for tr in self._active.values()]
        self._active.clear()
        self._pending.clear()
        return closed

    # -- interni -----------------------------------------------------------

    def _expire(
        self,
        matched_active: set[int],
        matched_pending: set[int],
        t: float,
        out: TrackerOutput,
        force: bool = False,
    ) -> None:
        """Chiude le battute che non si vedono piu' da abbastanza **tempo**.

        Il conteggio era sulle passate, e le passate non sono tempo: il diff le
        apre a raffiche, quindi tre passate valgono un decimo di secondo in una
        scena ferma e diversi secondi in una immobile. Misurato sui 27 minuti,
        539 raffiche di passate a vuoto, mediana 2 ma novantesimo percentile 17
        e massimo 230: con `hold_frames = 3` ognuna delle 177 raffiche piu'
        lunghe chiudeva una battuta ancora a schermo, che si riapriva subito
        dopo come nuova. Il 94% dei frammenti sotto i 0,6 s aveva una gemella a
        meno di quattro secondi — cioe' erano battute spezzate, non battute
        corte.

        Ma sostituire le passate col tempo, e basta, **peggiora**: misurato,
        1105 aperture col conteggio a passate contro 1129 col migliore dei tempi
        provati, e la curva sale da li' in poi. Il motivo e' che una passata non
        e' un intervallo arbitrario: avviene quando la scena cambia, e un
        sottotitolo che sparisce *e'* un cambiamento di scena. Contare le
        passate era una regola adattiva che non dichiarava di esserlo.

        Quindi servono entrambe, ed entrambe devono essere soddisfatte: si
        chiude quando la battuta e' assente da abbastanza passate **e** da
        abbastanza tempo. Il conteggio conserva l'adattivita', il tempo mette il
        pavimento che mancava nelle scene mosse, dove tre passate erano un
        decimo di secondo.
        """
        hold_n = max(0, self.cfg.hold_frames)
        hold_t = max(0.0, self.cfg.hold_seconds)

        def scaduta(missing: int, last_seen: float) -> bool:
            return missing > hold_n and (t - last_seen) > hold_t

        for key in list(self._active):
            if key in matched_active:
                continue
            tracked = self._active[key]
            tracked.missing += 1
            if force or scaduta(tracked.missing, tracked.last_seen):
                out.closed.append(self._active.pop(key).event.closed(t))
        for key in list(self._pending):
            if key in matched_pending:
                continue
            # Una candidata mai confermata che sparisce era uno sfarfallio.
            pending = self._pending[key]
            pending.missing += 1
            if force or scaduta(pending.missing, pending.last_seen):
                del self._pending[key]
