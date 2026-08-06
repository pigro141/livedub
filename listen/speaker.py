"""Chi parla: da un'impronta a un personaggio, e da un personaggio a una voce.

Non serve sapere che quello e' Franklin. Serve che, dentro una partita, ogni
personaggio riceva una voce **subito** e la tenga: un personaggio con la voce
sbagliata e' una scelta discutibile, un personaggio che cambia voce a meta'
scena e' un errore evidente. I nomi non li da' nessuno — i sottotitoli non li
contengono — quindi le identita' sono progressive (`S0`, `S1`, ...) e vere solo
dentro la sessione.

## La forma di questo modulo viene da una misura, e la misura ha sorpreso

La prima domanda posta era: due ritagli brevi della stessa voce si somigliano
piu' di due ritagli brevi di voci diverse? Risposta sull'audio di GTA V: quasi
per niente. Sembrava la fine della strada.

Era la domanda sbagliata. **Il tracker non confronta mai due ritagli brevi fra
loro.** Confronta il poco che ha raccolto prima di dover parlare con il
*centroide* di un personaggio, costruito su tutte le sue battute intere: un
indizio debole contro una conoscenza solida, non due indizi deboli. Misurato su
82 battute di GTA V etichettate all'ascolto, tre personaggi, a esclusione:

    parlato disponibile     sceglie il personaggio giusto
        0,30 s                       86,6%
        0,50 s                       93,9%
        0,75 s                      100,0%
        1,00 s                      100,0%

Da qui **due regole che non sono opzioni**:

1. **un ritaglio breve sceglie, non dichiara.** A 0,30 s la somiglianza col
   proprio centroide sta sotto 0,40 tre volte su quattro: non perche' sia un
   altro personaggio, ma perche' e' corta. Chi creasse un personaggio nuovo su
   quel numero ne inventerebbe uno a ogni battuta, e sarebbe un difetto che
   all'ascolto sembra "cambia voce in continuazione" — cioe' esattamente il
   guasto peggiore, ottenuto per eccesso di zelo;

2. **si impara dalle battute intere.** Quando la battuta finisce il suo audio
   c'e' tutto: quello e' il momento di aggiornare il centroide e, se davvero non
   somiglia a nessuno, di aprire un personaggio nuovo. La decisione veloce paga
   il prezzo della fretta, la conoscenza no.

## Cosa questo modulo non fa

Non usa il colore della riga. Il piano assumeva che una riga grigia fosse un
secondo personaggio: misurato su 675 battute bianche in 17 sessioni, le grigie
sono 15 e **nessuna e' dialogo** — sono code del rumore dell'OCR. Un vincolo
costruito su quel segnale vincolerebbe rumore.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.config import SpeakerConfig

# Il pavimento della scelta veloce, **spostato in config e misurato**: si veda
# `SpeakerConfig.name_min_score`, dove sta la tabella dell'accordo fra la porta
# veloce e la porta lenta per fascia di somiglianza. Questo valore resta come
# riferimento storico di cosa significhi "qui non c'e' proprio voce" — un
# ritaglio di silenzio o di motore da' somiglianze intorno a zero con tutti — ma
# la decisione non lo usa piu'.
PLAUSIBILE_SOPRA = 0.15

# **Le soglie del genere, e la misura che le ha spostate.** Erano 165 e 185, e
# venivano dalla fisiologia della voce parlata. Sul mix del gioco non
# funzionavano: dei tre uomini della scena del concessionario — risposta nota,
# confermata all'ascolto — uno riceveva `paola` e un altro finiva nella fascia
# morta.
#
# **La prima spiegazione era sbagliata, ed e' istruttivo dire quale.** Nei
# ritagli di quel personaggio le finestre sonore stanno per meta' sopra i 190 Hz,
# e le piu' *sicure* sono proprio quelle: sembrava fondo che si sovrapponeva alla
# voce. Il rimedio "prendi la parte bassa della distribuzione" funzionava, quindi
# la spiegazione e' rimasta in piedi senza essere verificata.
#
# Poi e' stata verificata, e dice un'altra cosa. Se i 230 Hz fossero fondo,
# starebbero anche — anzi soprattutto — nelle finestre **deboli**, dove il
# parlato non li copre. Misurato sulle 1517 finestre sonore di quel personaggio,
# divise per energia:
#
#     quarto piu' debole   intonazione mediana 151 Hz   sopra 190 Hz  34%
#     secondo quarto                           180 Hz                 46%
#     terzo quarto                              198 Hz                 53%
#     quarto piu' forte                        217 Hz                 69%
#
# La correlazione fra energia della finestra e intonazione e' **+0,40**, e la
# confidenza dell'autocorrelazione sale insieme (da 0,58 a 0,80). E' il contrario
# di cio' che farebbe una musica di fondo: e' un uomo che **alza la voce**, e
# alzandola sale di intonazione. In quella scena il personaggio urla.
#
# Quindi il percentile basso non toglie una contaminazione: prende il **fondo
# tonale del parlatore**, cioe' come suona quando non sta gridando — che e' un
# tratto molto piu' stabile della media, per chiunque abbia una scena concitata.
# Il rimedio resta lo stesso; la ragione per cui funziona e' un'altra, e sapere
# quale cambia cosa ha senso provare dopo (non serve pulire il segnale per
# questo).
#
# Non la mediana delle finestre ma il loro quindicesimo percentile — si veda
# `stima_f0` — e le soglie ricalibrate su quella statistica:
#
#     misura (p15 per ritaglio, mediana sui ritagli)   attuale   prima
#     S0   Simeon, uomo                                   124     153
#     S9   uomo                                           118     134
#     S10  uomo                                           140     181
#     S11  Lamar, uomo, 15 battute                        174     218   <- prendeva `paola`
#     riccardo, voce Piper pulita                         142     160
#     paola, voce Piper pulita                            185     210
#
# 175 e 195 tengono i quattro uomini a maschile e `paola` a femminile. Il
# margine sul lato femminile e' di dieci hertz su un solo riferimento pulito:
# **questa taratura sa dire "uomo" molto meglio di quanto sappia dire "donna"**,
# e su una registrazione con una voce femminile va rifatta.
F0_MASCHILE_SOTTO = 175.0
F0_FEMMINILE_SOPRA = 195.0
# **Quante misure servono prima di dichiarare un sesso.** Con due, Lamar veniva
# dichiarato femmina sui suoi primi due ritagli — 242 e 193 Hz — e riceveva
# `paola` alla prima battuta detta, tenendosela per tutta la scena: la stima si
# raddrizza (a fine sessione la sua mediana e' 166 Hz, maschile), ma la voce era
# gia' data e non si tocca piu'. Con quattro non capita: la sua mediana resta
# dentro la fascia morta fino in fondo, quindi "non si sa" — che e' la risposta
# giusta — mentre gli altri due uomini sono maschili gia' alla quarta misura.
MISURE_MINIME = 4


@dataclass
class Personaggio:
    """Un personaggio conosciuto: la somma delle sue impronte, e da quando."""

    speaker_id: str
    somma: np.ndarray
    battute: int = 0
    prima_volta: float = 0.0
    ultima_volta: float = 0.0
    # **Le misure, non la loro media.** Prima c'era una media mobile 0,8/0,2, che
    # ha due difetti in uno: un ritaglio in cui l'intonazione e' stata presa dal
    # fondo la sposta e non torna piu' indietro, e quanto valga la stima non si
    # puo' piu' sapere — un valore solo non ha dispersione. Tenendo i valori si
    # risponde a tutte e due le domande con la stessa lista.
    f0_valori: list[float] = field(default_factory=list)
    # Se questo personaggio si e' rivelato un frammento di un altro, l'identita'
    # che lo ha assorbito. Non si cancella dalla banca: le battute gia' dette
    # portano il suo id, e senza di lui non si saprebbe piu' di chi erano.
    merged_into: str | None = None

    @property
    def centroide(self) -> np.ndarray:
        n = float(np.linalg.norm(self.somma))
        return self.somma / n if n > 1e-9 else self.somma

    @property
    def confermato(self) -> bool:
        """Sentito almeno due volte, quindi degno di una voce.

        Misurato su cento secondi di GTA V: il tracker apriva 16 personaggi, ma
        **tredici parlavano una volta sola** e non tornavano mai. Erano battute
        sporche, sovrapposizioni, o semplicemente un ritaglio infelice; e
        ognuna si portava via una voce del pool, che ne ha sei. Il risultato
        all'ascolto e' il difetto peggiore possibile — la voce che cambia a ogni
        riga — ottenuto non sbagliando a riconoscere, ma **credendo troppo in
        fretta** a una somiglianza bassa.

        Un personaggio che parla una volta e sparisce non ha bisogno di una voce
        propria: nessuno potra' accorgersi che non ce l'ha. Uno che torna si'.
        """
        return self.battute >= 2

    @property
    def f0(self) -> float:
        """Intonazione del personaggio: la mediana delle misure. Zero se non ce ne sono."""
        return float(np.median(self.f0_valori)) if self.f0_valori else 0.0

    @property
    def gender(self) -> str:
        """Maschile, femminile, o non si sa — e "non si sa" e' una risposta.

        La fascia morta fra le due soglie e' voluta: li' dentro un uomo con la
        voce chiara e una donna con la voce scura non si distinguono. Dirlo
        lascia decidere a chi assegna la voce, che puo' aspettare; rispondere a
        caso no.
        """
        if len(self.f0_valori) < MISURE_MINIME or self.f0 <= 0:
            return "?"
        if self.f0 < F0_MASCHILE_SOTTO:
            return "m"
        return "f" if self.f0 > F0_FEMMINILE_SOPRA else "?"

    @property
    def f0_dispersione(self) -> float:
        """Quanto le misure sono d'accordo fra loro (MAD, in Hz)."""
        if len(self.f0_valori) < 2:
            return 0.0
        v = np.asarray(self.f0_valori, dtype=np.float64)
        return float(np.median(np.abs(v - np.median(v))))


@dataclass
class Decisione:
    """Cosa il tracker ha deciso, e con quanta fiducia."""

    speaker_id: str
    confidence: float
    is_new: bool = False
    provisional: bool = False  # deciso con poco parlato: si potra' solo imparare, non disdire
    merged: tuple[str, str] | None = None  # (assorbito, vincitore), se questa battuta li ha uniti
    # Nessuno somiglia abbastanza da meritare un nome. Non e' un fallimento: e'
    # la risposta giusta nei primi secondi, quando la banca e' vuota o ha dentro
    # un solo personaggio e chiunque parli riceverebbe il suo nome.
    anonima: bool = False


class SpeakerTracker:
    """Banca di centroidi, coseno, e due porte di ingresso invece di una.

    `scegli` e' la porta veloce: la usa chi deve parlare adesso e ha in mano
    quel poco che il personaggio ha detto finora. Non crea mai nessuno.

    `impara` e' la porta lenta: la usa chi ha in mano la battuta intera, a cose
    fatte. Aggiorna il centroide e, se serve, apre un personaggio nuovo.

    Tenerle separate e' l'intero contenuto di questo modulo. Una sola porta
    dovrebbe scegliere una soglia buona per entrambe, e non esiste: quella che
    non inventa personaggi a 0,3 s non ne riconosce di nuovi a 2 s.
    """

    def __init__(self, cfg: SpeakerConfig | None = None) -> None:
        self.cfg = cfg or SpeakerConfig()
        self.people: list[Personaggio] = []
        self._ultimo: str | None = None
        # Gli id si contano a parte e non si riusano mai. Erano `f"S{len(people)}"`,
        # e con i fusi che restano in lista quel conto continuerebbe a tornare —
        # ma legare l'identita' di un personaggio alla lunghezza di una lista che
        # ha cambiato significato e' il genere di dettaglio che si rompe piu'
        # tardi, quando due battute distanti portano lo stesso nome.
        self._creati = 0
        self._alias: dict[str, str] = {}  # assorbito -> vincitore
        self.fusioni: list[tuple[str, str, float]] = []  # (assorbito, vincitore, somiglianza)

    def __len__(self) -> int:
        """Quanti personaggi **attivi**: i fusi non contano piu' come persone."""
        return len(self.attivi)

    @property
    def attivi(self) -> list[Personaggio]:
        return [p for p in self.people if p.merged_into is None]

    def risolvi(self, speaker_id: str | None) -> str | None:
        """L'identita' viva dietro un id, seguendo le fusioni fino in fondo."""
        visti = set()
        while speaker_id in self._alias and speaker_id not in visti:
            visti.add(speaker_id)
            speaker_id = self._alias[speaker_id]
        return speaker_id

    def get(self, speaker_id: str) -> Personaggio | None:
        vivo = self.risolvi(speaker_id)
        return next((p for p in self.people if p.speaker_id == vivo), None)

    def reset(self) -> None:
        self.people.clear()
        self._ultimo = None
        self._creati = 0
        self._alias.clear()
        self.fusioni.clear()

    # -- la porta veloce ---------------------------------------------------

    def scegli(self, embedding: np.ndarray | None, t: float = 0.0) -> Decisione:
        """Chi e', fra quelli che conosco? Non ne inventa di nuovi, e sa tacere.

        **Prima rispondeva sempre qualcuno**: il migliore fra i confermati, o in
        mancanza di meglio l'ultimo che aveva parlato. Il ragionamento era che
        inventare un personaggio e' sbagliato sempre mentre tirare a indovinare
        lo e' una volta su due, ed era giusto finche' le opzioni erano due. Con
        la voce neutra ce n'e' una terza, che non inventa e non mente — e la
        misura dice quando usarla: sotto `name_min_score` la porta veloce prende
        due battute su tredici, sopra venticinque su ventinove.

        Quelle tredici sono i primi trenta secondi di una scena, quando un solo
        personaggio e' confermato e chiunque parli riceve il suo nome e la sua
        voce. Il riconoscimento parte da vuoto e si costruisce ascoltando: e'
        giusto che nei primi secondi dichiari di non sapere, invece di dare a
        tutti la voce del primo che ha parlato.
        """
        # Solo i confermati danno una voce. Gli altri restano in banca — servono
        # a `impara`, che li puo' confermare — ma non entrano in una decisione
        # che si sente: un personaggio nato dalla battuta precedente non ha
        # ancora dimostrato di esistere.
        noti = [p for p in self.attivi if p.confermato]
        anonima = Decisione(
            self.risolvi(self._ultimo) or "S?", 0.0, provisional=True, anonima=True
        )
        if embedding is None or not noti or float(np.linalg.norm(embedding)) < 1e-9:
            # Senza impronta, o senza nessuno fra cui scegliere, non c'e' niente
            # da riconoscere. **Non si apre un posto in banca**: iscrivere qui un
            # personaggio significherebbe dargli un centroide vuoto, che non
            # somigliera' mai piu' a niente — quel personaggio non si
            # ritroverebbe e la sua voce resterebbe bruciata.
            return anonima

        punteggi = np.array([float(np.dot(embedding, p.centroide)) for p in noti])
        k = int(np.argmax(punteggi))
        migliore = float(punteggi[k])
        if migliore < self.cfg.name_min_score:
            # Nessuno somiglia abbastanza. Puo' voler dire che il ritaglio non
            # contiene voce, o che a parlare e' qualcuno che la banca non ha
            # ancora imparato: da qui non si distinguono, e per fortuna la
            # risposta e' la stessa. `_ultimo` non si tocca — non si e' sentito
            # nessuno di cui tenere memoria.
            return Decisione(anonima.speaker_id, migliore, provisional=True, anonima=True)
        self._ultimo = noti[k].speaker_id
        return Decisione(noti[k].speaker_id, migliore, provisional=True)

    # -- la porta lenta ----------------------------------------------------

    def impara(
        self, embedding: np.ndarray | None, t: float = 0.0, f0: float = 0.0
    ) -> Decisione:
        """La battuta e' finita e c'e' tutto il suo audio: adesso si conclude.

        E' l'unico punto in cui nasce un personaggio, ed e' voluto: qui il
        ritaglio e' lungo abbastanza perche' una somiglianza bassa voglia dire
        davvero "non l'ho mai sentito" e non "non ho sentito abbastanza".
        """
        if embedding is None or float(np.linalg.norm(embedding)) < 1e-9:
            return Decisione(self.risolvi(self._ultimo) or "S?", 0.0)
        attivi = self.attivi
        if attivi:
            punteggi = np.array([float(np.dot(embedding, p.centroide)) for p in attivi])
            k = int(np.argmax(punteggi))
            if float(punteggi[k]) >= self.cfg.similarity:
                p = attivi[k]
                p.somma = p.somma + embedding
                p.battute += 1
                p.ultima_volta = t
                # `_ultimo` non si tocca qui. E' l'ultimo a cui e' stata **data
                # una voce**, non l'ultimo di cui si e' imparato qualcosa:
                # confonderli faceva risuscitare dal ripiego i personaggi appena
                # nati e non ancora confermati, che e' esattamente cio' che la
                # conferma doveva impedire. Il difetto non dava errore — dava
                # tredici voci in cento secondi.
                if f0 > 0:
                    p.f0_valori.append(f0)
                # Il centroide di `p` e' appena cambiato: e' l'unico istante in
                # cui puo' essersi avvicinato abbastanza a un altro da rivelarsi
                # lo stesso personaggio.
                fusione = self._fondi(p)
                vivo = self.risolvi(p.speaker_id)
                return Decisione(vivo, float(punteggi[k]), merged=fusione)
        if attivi and len(attivi) >= self.cfg.max_speakers:
            # Il pool e' pieno. Si attacca al migliore invece di rifiutare: due
            # personaggi con la stessa voce sono brutti, un personaggio muto no.
            #
            # **E «attaccare» vuol dire contarla, non solo nominarla.** Prima di
            # qui si restituiva l'id del migliore senza toccarlo: niente
            # battuta, niente centroide, niente f0, nessun tentativo di fusione.
            # Il pool si riempie con le prime `max_speakers` battute, e da li' in
            # poi **ogni riga passava di qua**: nessuna identita' arrivava mai a
            # due battute, quindi nessuna diventava `confermato`, quindi `noti`
            # restava vuoto per sempre e la porta veloce restituiva zero. Voce
            # neutra su tutto, per il resto della sessione.
            #
            # Misurato sulla scena dell'utente (115 battute, 130 imparate): 16
            # identita' tutte con **una** battuta, zero confermate, punteggio
            # esattamente 0,000 su 114 chiamate su 114. E lo spazzamento di
            # `merge_similarity` da 0,35 a 0,90 non muoveva **un solo numero** —
            # il segno che la soglia non era la variabile e che il difetto stava
            # a monte.
            k = int(np.argmax(punteggi))
            p = attivi[k]
            p.somma = p.somma + embedding
            p.battute += 1
            p.ultima_volta = t
            if f0 > 0:
                p.f0_valori.append(f0)
            # La fusione si tenta anche qui, ed e' l'unica via d'uscita: a pool
            # pieno non si aprono piu' personaggi, quindi l'unico modo di fare
            # posto e' accorgersi che due erano lo stesso.
            fusione = self._fondi(p)
            return Decisione(self.risolvi(p.speaker_id), float(punteggi[k]),
                             merged=fusione)
        return self._apri(embedding, t, f0=f0)

    # -- interno -----------------------------------------------------------

    def _apri(self, embedding: np.ndarray, t: float, *, f0: float = 0.0) -> Decisione:
        """Iscrive un personaggio. Solo dalla porta lenta, e solo con un'impronta
        vera: un centroide vuoto non somiglierebbe mai piu' a niente."""
        sid = f"S{self._creati}"
        self._creati += 1
        self.people.append(
            Personaggio(
                speaker_id=sid,
                somma=embedding.copy(),
                battute=1,
                prima_volta=t,
                ultima_volta=t,
                f0_valori=[f0] if f0 > 0 else [],
            )
        )
        return Decisione(sid, 0.0, is_new=True)

    # -- la fusione --------------------------------------------------------

    def _fondi(self, p: Personaggio) -> tuple[str, str] | None:
        """Se `p` si e' rivelato lo stesso personaggio di un altro, li unisce.

        **Il difetto che cura.** Il tracker apre un personaggio quando un
        ritaglio intero non somiglia a nessuno; ma un ritaglio intero puo' essere
        sporco, sovrapposto, o preso mezzo secondo troppo tardi, e allora la
        stessa persona si spezza in due identita' che restano due per sempre.
        Misurato dal vivo: **sedici identita' per tre personaggi reali**, con
        Simeon sparso fra S3, S6 e S8 e undici identita' con una battuta sola.

        Il rimedio esiste perche' i centroidi non sono fermi: ogni battuta ne
        aggiunge una, e due frammenti della stessa persona si somigliano sempre
        di piu'. Prima o poi si somigliano abbastanza da poterlo dire, ed e'
        allora — non prima — che si possono unire.

        **La soglia dipende da chi si sta confrontando, e non e' un
        raffinamento: senza, questa funzione non serviva a niente.** Fra due
        centroidi maturi vale `merge_similarity`, misurata proprio li'. Ma un
        personaggio con **una battuta sola** non ha un centroide: ha un
        ritaglio, e un ritaglio contro un centroide e' l'altra distribuzione —
        quella con mediana 0,489, per cui la soglia giusta e' `similarity`.
        Applicare 0,70 anche a quel confronto significa non fondere mai
        un'identita' solitaria, cioe' esattamente quelle per cui la fusione e'
        stata scritta: misurato su tre passate della stessa scena, **zero
        fusioni e sedici identita' per tre personaggi reali**. Con la soglia
        scelta per maturita' le fusioni diventano 2, 2 e 3.

        E' la stessa forma dell'errore dei caratteri al secondo: un numero
        misurato in un'unita' e speso in un'altra.

        **Chi vince tiene la voce: quello con piu' battute**, a parita' il piu'
        vecchio di comparsa. Non il primo comparso, che era la formulazione
        istintiva: un frammento da una battuta nato a inizio scena che
        assorbisse un personaggio da venti farebbe cambiare voce a venti
        battute gia' sentite, cioe' esattamente il difetto — la voce che cambia
        a meta' scena — che la fusione dovrebbe togliere di mezzo.
        """
        if not self.cfg.merge:
            return None
        altri = [q for q in self.attivi if q is not p]
        if not altri:
            return None
        centro = p.centroide
        punteggi = np.array([float(np.dot(centro, q.centroide)) for q in altri])
        k = int(np.argmax(punteggi))
        somiglianza = float(punteggi[k])
        if somiglianza < self._soglia_fusione(p, altri[k]):
            return None
        q = altri[k]
        vincitore, perdente = (p, q) if self._anziano(p, q) else (q, p)

        vincitore.somma = vincitore.somma + perdente.somma
        vincitore.battute += perdente.battute
        vincitore.prima_volta = min(vincitore.prima_volta, perdente.prima_volta)
        vincitore.ultima_volta = max(vincitore.ultima_volta, perdente.ultima_volta)
        vincitore.f0_valori.extend(perdente.f0_valori)
        perdente.merged_into = vincitore.speaker_id
        self._alias[perdente.speaker_id] = vincitore.speaker_id
        self.fusioni.append((perdente.speaker_id, vincitore.speaker_id, somiglianza))
        if self._ultimo == perdente.speaker_id:
            self._ultimo = vincitore.speaker_id
        return (perdente.speaker_id, vincitore.speaker_id)

    def _soglia_fusione(self, a: Personaggio, b: Personaggio) -> float:
        """Quale delle due soglie vale per **questa** coppia.

        La domanda non e' "quanto devono somigliarsi", e' "che cosa sto
        confrontando": due medie, o una media e un campione.
        """
        if min(a.battute, b.battute) < self.cfg.merge_maturo:
            return self.cfg.similarity
        return self.cfg.merge_similarity

    @staticmethod
    def _anziano(a: Personaggio, b: Personaggio) -> bool:
        """`a` e' quello che l'orecchio ha sentito di piu'? A parita', il piu' vecchio."""
        if a.battute != b.battute:
            return a.battute > b.battute
        return a.prima_volta <= b.prima_volta

    # -- lettura -----------------------------------------------------------

    def report(self) -> str:
        if not self.people:
            return "(nessun personaggio ancora sentito)"
        righe = [
            f"  {p.speaker_id:>4}  {p.battute:>3} battute  "
            f"da {p.prima_volta:7.1f}s a {p.ultima_volta:7.1f}s  "
            f"f0 {p.f0:5.0f} Hz -> {p.gender}"
            for p in self.attivi
        ]
        # Le fusioni si stampano: senza, un id sparito dal report sembrerebbe un
        # personaggio dimenticato invece di uno riconosciuto.
        for perdente, vincitore, s in self.fusioni:
            righe.append(f"  {perdente:>4}  fuso in {vincitore} (somiglianza {s:.2f})")
        return "\n".join(righe)


# -- l'intonazione, che serve solo a scegliere maschile o femminile ---------


def stima_f0(
    x: np.ndarray, samplerate: int, lo: float = 60.0, hi: float = 300.0, quantile: float = 15.0
) -> float:
    """Intonazione delle finestre sonore, in Hz. Zero se non si sa.

    Autocorrelazione su finestre di 40 ms. Non e' un estrattore raffinato e non
    deve esserlo: l'unica domanda a cui risponde e' "voce maschile o femminile",
    cioe' quale meta' del pool guardare.

    **Non la mediana delle finestre ma il loro quindicesimo percentile, e il
    motivo e' una misura.** Nei ritagli del gioco le finestre sonore di un uomo
    si distribuiscono su tutta la banda: sui quindici ritagli di Lamar, 64
    finestre fra 90 e 130 Hz e 673 sopra i 190. La mediana cade in mezzo alle
    seconde e risponde 221 Hz per un uomo.

    Quelle finestre alte **sono la sua voce**, non fondo che ci si sovrappone:
    l'intonazione sale insieme all'energia della finestra (correlazione +0,40, e
    la tabella per quartili sta in cima a questo modulo), che e' la firma di
    qualcuno che alza la voce, non di una musica sotto. Un percentile basso
    quindi non ripulisce niente: prende il **fondo tonale del parlatore**, come
    suona quando non sta gridando. Ed e' proprio per questo che identifica meglio
    la persona — quanto uno gridi dipende dalla scena, la sua voce di base no.

    Sui quattro personaggi maschili di riferimento la risposta passa da
    153/134/181/218 Hz a 124/118/140/174, e su `paola` pulita resta 185.

    Il prezzo, dichiarato: la stima **scende anche sulle voci femminili**, e il
    margine sul lato femminile e' di dieci hertz. Questa misura sa dire "uomo"
    molto meglio di quanto sappia dire "donna".
    """
    # Nota per chi tocchera' `quantile`: un valore piu' basso rende la stima piu'
    # robusta a chi grida e piu' fragile al primo colpo di tosse, perche' guarda
    # sempre meno finestre. Quindici e' un compromesso misurato, non un default
    # ereditato.
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    n = int(0.04 * samplerate)
    hop = max(1, n // 2)
    if x.size < n:
        return 0.0
    a, b = int(samplerate / hi), int(samplerate / lo)
    if b <= a or b >= n:
        return 0.0
    valori = []
    for i in range(0, x.size - n, hop):
        w = x[i : i + n] - x[i : i + n].mean()
        if float(np.sqrt(np.mean(w**2))) < 0.005:
            continue
        r = np.correlate(w, w, "full")[n - 1 :]
        r = r / (r[0] + 1e-12)
        k = int(np.argmax(r[a:b])) + a
        if r[k] > 0.35:
            valori.append(samplerate / k)
    return float(np.percentile(valori, quantile)) if len(valori) >= 3 else 0.0
