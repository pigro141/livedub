"""I due cicli dal vivo, **fuori da qualunque finestra**.

    motore = Motore(cfg, Opzioni(loopback="voicemeeter"), manda=coda.put)
    motore.avvia()   # apre device, catena e sessione, poi due thread
    motore.ferma()   # ferma, chiude la sessione, scrive il rapporto

**Perche' esiste questo file.** Il ciclo audio (blocchi da 10 ms) e il ciclo
video (30 Hz) stavano dentro `tools/ui.py`, cioe' dentro Tkinter. Portarli in
una seconda finestra voleva dire copiarli, e questo progetto ha gia' pagato due
volte il prezzo di una strada parallela che non eredita le cure dell'altra: il
ricampionamento e il taglio del silenzio in coda, scritti nel ramo normale e
mancanti in quello in streaming. Qui i cicli sono **uno solo**: la finestra Tk e
quella Qt li chiamano tutte e due, quindi una correzione arriva a entrambe per
costruzione invece che per memoria.

**Il motore non tocca nessuna interfaccia.** Comunica in un verso solo, con
`manda(tipo, dato)`, che dal vivo e' `queue.put` — disegnare dal thread video
vorrebbe dire toccare Tk o Qt da fuori del loro thread, che e' il modo piu'
rapido di far cadere la finestra. I messaggi sono sei:

| tipo | dato | chi lo guarda |
|---|---|---|
| `nota` | una riga di testo | il registro |
| `stato` | una riga di stato | testata e pallino |
| `riga` | `(sid, voce, testo, latenza, t)` | il log di chi parla |
| `overlay` | la battuta tradotta e la sua geometria | la finestra sopra il gioco |
| `aggiorna` | `(ritaglio, quando)` | la sfocatura, a ogni fotogramma |
| `spegni` | `None` | l'overlay si nasconde |
| `guasto` | il dettaglio | chi deve chiudere la sessione |

**L'overlay lo costruisce la finestra, non il motore**, e glielo passa: e' un
oggetto grafico, e quale sia dipende dal front-end. Da qui si leggono solo tre
cose che hanno tutte e due (`_visibile`, `rett`, `t_on`), dichiarate in
`ui.overlay.OverlayBase`.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from capture.audio import (
    Loopback,
    Player,
    find_loopback,
    find_output,
    list_devices,
    nome_scheda,
    stesso_dispositivo,
)
from capture.screen import apri_cattura
from core.clock import RealClock, set_clock
from core.metrics import MetricsRegistry
from core.pipeline import DubPipeline
from tools.session import Session
from ui.overlay import inchiostro, inchiostro_da_box, ritaglia

# **La frequenza dell'anello audio non e' una scelta di questo file.** 48 kHz e'
# quello che chiedono cattura e uscita: cambiarlo qui vorrebbe dire ricampionare
# ovunque, ed e' scritto in chiaro perche' non lo si tocchi per sbaglio.
SR = 48000

# **Dal vivo si tengono le ultime battute, non tutte.** Una sessione di tre ore
# lascia vive 3600 battute per +10,4 MB (misurato con `tools/bench_memoria.py`) e
# cresce senza limite. Chi le rilegge e' il cancello anti-doppioni, che guarda
# indietro di secondi: 400 sono venti minuti di conversazione, cioe' cento volte
# quello che serve.
MAX_SPOKEN = 400

# Le parole del guasto audio stanno qui, non in una finestra: sono due front-end
# a doverle dire, e due copie diventano due messaggi diversi al primo ritocco.
STATO_GUASTO = "! audio interrotto"

# **Gli stati di una sessione sono quattro, e per anni ne sono stati dichiarati
# due.** L'unica domanda che il motore sapeva rispondere era `acceso`, cioe'
# `bool(threads)`: vera quando i due cicli girano, falsa in tutti gli altri casi
# — **compresi i secondi in cui i device si aprono e il TTS si carica**, che con
# Kokoro sono parecchi. In quella finestra il motore diceva «fermo» mentre stava
# partendo, e da li' sono usciti due difetti che sembravano scollegati:
#
#   - `avvia()` non era idempotente: un secondo Avvia in quei secondi — o un
#     Ferma seguito da un Avvia, che `applica_in_attesa` e `_riprova` fanno da
#     soli — metteva in piedi **una seconda catena** sullo stesso processo, con
#     i suoi due thread e la sua pipeline. E' cosi' che qualcosa si accumula fra
#     un Avvia e l'altro;
#   - un `finito` mandato da una partenza fallita rimetteva i bottoni di una
#     sessione **viva**: Ferma spento, Avvia acceso, la scheda Sessione che dice
#     «avviato» e Avvia che non fa niente perche' `acceso` e' vero. E' lo stato
#     esatto in cui l'utente si e' trovato bloccato, ed e' l'immagine rovesciata
#     del guasto audio gia' curato — *una cura e' quasi sempre piu' stretta del
#     difetto*.
#
# Quattro stati e una regola sola (`bottoni`) rispondono a tutte e due, e la
# regola sta qui e non nella finestra perche' e' una **regola**: si verifica
# senza aprire niente, ed e' una sola per due front-end.
FERMO = "fermo"
IN_PARTENZA = "in partenza"
ACCESA = "accesa"
IN_ARRESTO = "in arresto"
STATI = (FERMO, IN_PARTENZA, ACCESA, IN_ARRESTO)


@dataclass(frozen=True)
class Bottoni:
    """Cosa si puo' premere, e cosa dice la finestra, dato lo stato.

    `avviato` non e' un bottone: e' la spunta del terzo passo, cioe' **cio' che
    la scheda Sessione dichiara**. Sta qui insieme ai due bottoni apposta —
    erano dedotti in punti diversi della finestra, e due deduzioni sulla stessa
    domanda sono due risposte al primo caso di bordo.
    """

    avvia: bool
    ferma: bool
    preparazione: bool
    avviato: bool


def bottoni(stato: str) -> Bottoni:
    """Da uno stato di sessione, i comandi che ne conseguono.

    Gli invarianti che questa tabella tiene — e che la suite verifica a uno a
    uno, partendo dallo **stato** e non ricopiando la logica della finestra:

    - Avvia e Ferma non sono mai premibili insieme, ne' mai spenti tutti e due
      salvo mentre si sta chiudendo, che e' l'unico momento in cui non c'e'
      davvero niente da chiedere;
    - **`avviato` implica Avvia spento**: «la sessione e' avviata» e «Avvia si
      puo' premere» non possono convivere. E' letteralmente lo stato in cui il
      programma si e' piantato, quindi e' la riga che questa regola esiste per
      far fallire;
    - Avvia e' premibile **solo** da fermo: durante la partenza non lo e', ed e'
      la meta' che mancava — un secondo Avvia li' dentro raddoppiava la catena.

    La scheda Preparazione segue Avvia: cosa si cattura, da dove arriva l'audio
    e dove sono i sottotitoli si leggono alla partenza, quindi restano toccabili
    solo quando toccarli ha un effetto.
    """
    if stato == FERMO:
        return Bottoni(avvia=True, ferma=False, preparazione=True, avviato=False)
    if stato == IN_PARTENZA:
        return Bottoni(avvia=False, ferma=True, preparazione=False, avviato=False)
    if stato == ACCESA:
        return Bottoni(avvia=False, ferma=True, preparazione=False, avviato=True)
    if stato == IN_ARRESTO:
        return Bottoni(avvia=False, ferma=False, preparazione=False, avviato=False)
    # **Uno stato che non esiste non si dipinge lo stesso.** Ripiegare su una
    # riga plausibile qui vorrebbe dire una finestra coerente che descrive una
    # sessione che non c'e': il silenzio e' proprio il difetto che questo pezzo
    # e' stato scritto per togliere.
    raise ValueError(f"stato di sessione sconosciuto: {stato!r}")


def in_coda(coda):
    """Il `manda` che le finestre passano al motore: impacchetta e infila.

    **Non e' zucchero.** `coda.put` prende `(oggetto, bloccante, timeout)`:
    chiamarlo come `coda.put(tipo, dato)` non solleva — infila il **solo tipo**
    e usa il dato come flag di blocco. Dall'altra parte `tipo, dato = ...`
    prova a spacchettare una stringa di quattro lettere, e il guasto arriva
    lontanissimo da dove sta lo sbaglio. E' successo: due front-end, due
    adattatori scritti a mano, e la verifica ne usava un terzo — cioe' provava
    una catena che nessuno faceva girare.
    """
    return lambda tipo, dato=None: coda.put((tipo, dato))


def colore_stato(testo: str, tema) -> str:
    """Di che colore va il pallino, dato quello che c'e' scritto accanto.

    **Sta fuori dalle finestre perche' e' una regola, non un disegno**, e una
    regola si verifica senza aprire niente. E' servito: «audio interrotto»
    veniva **verde** — il colore del «va tutto bene» sopra una catena morta —
    perche' non contiene ne' `!` ne' «guasto», e nessuno poteva accorgersene
    senza staccare le cuffie a meta' sessione. Adesso le finestre sono due, e
    una regola scritta due volte diventa due regole al primo ritocco.

    `tema` e' qualunque cosa abbia `ROSSO`, `VERDE` e `TESTO_FIOCO`: il modulo
    del tema Tk, o un adattatore di tre righe sulla tavolozza Qt.
    """
    basso = testo.lower()
    if "!" in testo or "error" in basso or "guast" in basso or "interrott" in basso:
        return tema.ROSSO
    if "ferm" in basso or "pront" in basso:
        return tema.TESTO_FIOCO
    return tema.VERDE


# **Le parole che dicono «la sessione e' chiusa».** Non un elenco di stati
# scritto in testata: un elenco scritto la' si separerebbe da questa regola al
# primo stato nuovo, e si separerebbe **in silenzio**, con la suite verde.
PAROLE_GUASTO = ("guast", "error", "interrott", "avvio fallito", "si e' fermato")


def gravita(riga: str) -> str:
    """Che marca va nel margine sinistro di una riga di log: `""`, `avviso`, `guasto`.

    **Avviso e guasto non possono vedersi uguali**, e oggi si vedevano: ogni riga
    andava nel log dello stesso colore, `!` compresi. Quindi
    `! l'area e' alta 0,180 dello schermo` (un consiglio) e
    `! l'audio si e' fermato` (la fine della sessione) uscivano identici, in
    mezzo a righe che scorrono.

    E la cura ovvia — colorarli di rosso — e' sbagliata due volte: brucia il
    canale del colore del testo, che appartiene alle **voci**, e addestra
    l'occhio a ignorare il rosso, perche' gli `!` di questo programma sono quasi
    tutti avvisi che non fermano niente. Quindi il segno e' una marca da 3 px nel
    margine, ambra o rossa, e il testo resta del colore del testo.

    Sta qui e non nella finestra perche' e' **una regola e non un disegno**: si
    verifica senza aprire niente, ed e' una sola per due front-end.
    """
    basso = riga.lower()
    if any(p in basso for p in PAROLE_GUASTO):
        return "guasto"
    if riga.lstrip().startswith("!"):
        return "avviso"
    return ""


@dataclass(frozen=True)
class Misura:
    """Un valore della barra in fondo: come si chiama, quanto vale, se e' storto.

    `stato` vale `""`, `"avviso"` (ambra) o `"guasto"` (rosso), e lo decide
    `barra_misura` guardando **soglie dichiarate**, non l'aspetto del numero.
    """

    nome: str
    testo: str
    stato: str = ""


# Le soglie della barra della misura, tutte gia' misurate o dichiarate altrove in
# questo progetto — nessuna scelta guardando la barra:
#
# | soglia | da dove viene |
# |---|---|
# | OCR < 15 Hz | schermo intero 14,7 Hz contro fascia 19,9: **cinque sottotitoli in meno**. Sono **letture** (`vision.read`), non chiamate all'OCR: vedi `misure()` |
# | latenza p50 > 2500 ms | la soglia scritta **prima** della prova di Qwen dal vivo |
# | compressione > 1,30 | oltre 1,3 le consonanti spariscono (WSOLA) |
# | underrun > 0 | zero e' l'unico valore accettabile: un buco nell'audio si sente |
OCR_MINIMO_HZ = 15.0
LATENZA_MASSIMA_MS = 2500.0
COMPRESSIONE_MASSIMA = 1.30


def barra_misura(d: dict) -> list[Misura]:
    """I valori da mettere in fondo alla finestra, gia' formattati e giudicati.

    Esiste perche' questo progetto misura tutto e poi **non lo guarda finche' non
    finisce la sessione**. Le stesse quantita' sono gia' nel rapporto scritto in
    `runs/`: metterle sotto gli occhi durante la partita e' la differenza fra
    accorgersi che l'OCR e' sceso a 12 Hz e scoprirlo mezz'ora dopo leggendo un
    file.

    **C'erano sei valori e una finestra bassa ne mostrava tre**, come dice §6 del
    disegno. Provato a schermo, era un difetto: rimpicciolendo la finestra i
    numeri **sparivano uno dopo l'altro** senza che niente dicesse perche', e
    quelli che se ne andavano per primi — OCR, compressione, underrun — sono
    esattamente quelli che si guardano quando qualcosa non va. La riga sta in una
    finestra larga 960 e ci sta tutta; se un giorno non ci stesse, la cosa da
    fare e' accorciare le etichette, non nascondere le misure.
    """
    fuori: list[Misura] = [Misura("", str(d.get("stato", "fermo")))]
    ocr = float(d.get("ocr_hz") or 0.0)
    battute = int(d.get("battute") or 0)
    lat = float(d.get("latenza_ms") or 0.0)
    compr = float(d.get("compressione") or 0.0)
    secchi = int(d.get("underrun") or 0)
    viva = bool(d.get("viva"))

    fuori.append(Misura(
        "OCR", f"{ocr:.1f} Hz" if ocr else "—",
        "avviso" if viva and 0 < ocr < OCR_MINIMO_HZ else ""))
    fuori.append(Misura("battute", str(battute)))
    fuori.append(Misura(
        "latenza p50", f"{lat:.0f} ms" if lat else "—",
        "avviso" if lat > LATENZA_MASSIMA_MS else ""))
    fuori.append(Misura(
        "compress.", f"{compr:.2f}" if compr else "—",
        "avviso" if compr > COMPRESSIONE_MASSIMA else ""))
    # **L'unico che passa in rosso.** Un underrun e' un buco nell'audio: non e'
    # un valore fuori norma, e' una battuta che non si e' sentita.
    fuori.append(Misura("underrun", str(secchi), "guasto" if secchi > 0 else ""))
    roi = d.get("roi")
    if roi:
        x, y, w, h = roi
        fuori.append(Misura("ROI", f"x{x:.3f} y{y:.3f} w{w:.3f} h{h:.3f}"))
    return fuori


# Le quattro parole con cui la catena dice cosa sta facendo. Sono quattro e non
# cinque **perche' quattro sono quelle che si misurano**: «sta sintetizzando»
# sarebbe la quinta e non c'e' modo di vederla da qui, perche' la sintesi accade
# dentro `on_frame`, cioe' dentro il thread video, e il thread della finestra
# quella finestra di tempo non la vede mai. Una parola in piu' che indovina e'
# peggio di una in meno che misura.
#
# **E sono frasi e non parole, che e' una scelta pagata subito.** La prima
# stesura diceva `legge` e `parla`, cioe' due verbi alla terza persona senza
# soggetto: il catalogo tedesco li ha resi `Gesetz` («la legge», il sostantivo) e
# `sprechen` (l'infinito). Una parola sola fuori contesto e' ambigua per un
# traduttore automatico esattamente come lo e' per un lettore, ed e' la stessa
# forma dei tre errori gia' trovati nei cataloghi — «solo a caldo» diventato il
# tempo atmosferico. Con `sta leggendo` non c'e' piu' niente da indovinare.
FASI = ("fermo", "sta leggendo", "sta parlando", "in ritardo")


def fase_catena(d: dict) -> Misura:
    """In che punto della catena siamo, in una parola sola.

    E' la domanda che ci si fa guardando la finestra mentre si gioca — «sta
    ancora funzionando?» — e a cui i sei numeri della barra in fondo rispondono
    solo se li si legge tutti. Non li ripete: **quelli dicono quanto, questa dice
    cosa**, e la faccia del logo dice se e' rotto. Tre domande diverse, una
    risposta per ciascuna.

    L'ordine dei rami e' l'ordine di importanza: che stia parlando batte tutto,
    perche' e' l'unico momento in cui il programma sta facendo il suo mestiere;
    il ritardo batte la lettura, perche' e' la cosa che si vuole sapere.

    Sta qui e non nella finestra per la ragione di sempre: e' una regola, si
    verifica senza aprire Qt, ed e' **una sola** per due front-end.
    """
    if not d.get("viva"):
        return Misura("", "fermo")
    if d.get("parla"):
        return Misura("", "sta parlando")
    lat = float(d.get("latenza_ms") or 0.0)
    if lat > LATENZA_MASSIMA_MS:
        return Misura("", "in ritardo", "avviso")
    return Misura("", "sta leggendo")


def righe_guasto_audio(dettaglio: str) -> list[str]:
    """Cosa si scrive quando il ciclo audio muore.

    Il guasto piu' probabile di tutti — le cuffie staccate a meta' partita — e'
    anche quello da cui si deve poter tornare: si dice **cosa** e' successo e
    **cosa fare**, perche' senza il messaggio l'unico sintomo e' un doppiaggio
    che ammutolisce mentre la finestra continua a dire «in corso».
    """
    return [
        f"! l'audio si e' fermato: {dettaglio}",
        "! probabile: cuffie o altoparlanti staccati, oppure il device e' "
        "cambiato. Ricollega e premi Avvia.",
    ]


@dataclass
class Opzioni:
    """Quello che si sceglie dalla riga di comando, non dalla config.

    Sono i **dispositivi** e il modo di catturare: non stanno in `Config` perche'
    non sono del gioco ne' del setup di cattura salvato in un profilo, sono di
    questa macchina e di questa volta.
    """

    loopback: str = "voicemeeter"
    output: str | None = None
    block: int = 480
    backend: str = "auto"
    monitor: int = 1
    no_save: bool = False

    @classmethod
    def da_args(cls, args) -> "Opzioni":
        """Gli argomenti dell'argparse, quelli che ci sono."""
        return cls(**{
            campo: getattr(args, campo)
            for campo in ("loopback", "output", "block", "backend", "monitor", "no_save")
            if getattr(args, campo, None) is not None
        })


class Motore:
    """Apre i device, costruisce la catena e tiene i due thread.

    Non ha finestre, non ha timer, non disegna: si accende con `avvia()` e si
    spegne con `ferma()`. Chi lo usa gli passa `manda` e — se traduce — un
    overlay gia' costruito.
    """

    def __init__(self, cfg, opzioni: Opzioni, manda, *, overlay=None) -> None:
        self.cfg = cfg
        self.opz = opzioni
        self.manda = manda
        self.overlay = overlay
        # La finestra del gioco scelta dall'utente. `None` = tutto lo schermo,
        # che e' il vecchio modo e resta possibile: su un gioco in fullscreen
        # esclusivo e' l'unico.
        self.finestra = None
        self.pipeline: DubPipeline | None = None
        self.sessione: Session | None = None
        self.threads: list[threading.Thread] = []
        self.stop = threading.Event()
        # Lo stato **dichiarato**, che e' l'unica fonte per «cosa si puo'
        # premere». Il lucchetto copre le sole transizioni — tre righe — e mai
        # una chiusura: tenerlo durante `_chiudi` vorrebbe dire il thread della
        # finestra fermo su un `join`, cioe' la finestra congelata, che e' il
        # sintomo da cui e' partita tutta questa storia.
        self._stato = FERMO
        self._lucchetto = threading.Lock()
        self._registro = None
        # Fino a quando il tradotto resta a schermo. Lo scrivono in due — il
        # ciclo video quando il sottotitolo del gioco c'e' ancora, la finestra
        # quando una battuta arriva tardi — quindi vive qui, dove tutti e due lo
        # vedono.
        self.overlay_fino_a = 0.0
        # **Le metriche della finestra muoiono con lei, e non devono.**
        # `overlay.ritardo` veniva misurato a ogni giro e buttato, perche' il
        # rapporto scritto in `runs/` era solo quello della catena. Stando qui
        # finisce nel rapporto di tutte e due le finestre.
        self.metriche = MetricsRegistry()
        self._t_ritardo = self.metriche.timer("overlay.ritardo")
        # Quando sono partiti i due cicli: serve a dire l'OCR **in hertz** e non
        # in letture. Il conteggio da solo cresce sempre, quindi non risponde mai
        # alla domanda «sta leggendo abbastanza in fretta adesso?».
        self.t_avvio = 0.0

    def misure(self) -> dict:
        """I numeri che la barra in fondo mostra durante la partita.

        Si leggono dal registro della catena, che li raccoglie gia' tutti: qui
        non si misura niente di nuovo, si **guarda** cio' che finora veniva
        scritto in `runs/` e letto mezz'ora dopo. Con la catena spenta si
        risponde con zeri invece che con l'ultimo valore vivo, perche' un numero
        fermo accanto a uno stato «fermo» si legge come un numero vero.
        """
        dati: dict = {"roi": tuple(self.cfg.vision.roi), "viva": self.pipeline is not None}
        p = self.pipeline
        if p is None:
            return dati
        m = p.metrics
        trascorso = max(1e-6, time.perf_counter() - self.t_avvio) if self.t_avvio else 0.0
        # **`vision.read` e non `vision.ocr`**, e la differenza e' un fattore 2,7.
        # `vision.read` conta i fotogrammi **guardati**; `vision.ocr` solo quelli
        # che passano il cancello del diff, cioe' quelli in cui qualcosa e'
        # cambiato. La soglia qui sotto e' misurata sulle **letture** (la tabella
        # di `OCR_MINIMO_HZ` dice 14,7 contro 19,9, e quei numeri sono letture),
        # quindi applicarla alle chiamate all'OCR e' la settima volta in questo
        # progetto della forma «una quantita' misurata e un'altra applicata».
        #
        # Misurato su `runs/2026-08-20_00-01-56`: `vision.read` 10724 e
        # `vision.ocr` 3883 su 674,9 s, cioe' **15,9 Hz contro 5,8**. Quella
        # sessione ha tenuto l'OCR **in ambra per undici minuti** con
        # `mix.underrun` 0, compressione 1,00 e 146 battute doppiate — un valore
        # fuori norma che fuori norma non era. Un ambra bruciato dove non e'
        # successo niente e' cio' che insegna a non guardare piu' l'ambra la
        # volta che conta: lo stesso difetto del `!` speso su `auto` quando
        # funzionava.
        #
        # Il tasso **con il cancello acceso** sarebbe un'altra misura, con una
        # sua soglia: oggi quella soglia non esiste, e inventarla qui vorrebbe
        # dire scrivere un numero non misurato.
        letture = m.timer("vision.read").count
        dati.update(
            ocr_hz=(letture / trascorso) if trascorso else 0.0,
            battute=p.dette,
            latenza_ms=m.timer("dub.latency_live").p50,
            compressione=m.timer("dub.rate_x1000").p50 / 1000.0,
            underrun=m.counter("mix.underrun").value,
            # **Due valori che rispondono ad «adesso» e non a «finora».** La
            # barra in fondo vuole i percentili, la scheda Sessione vuole
            # l'ultima battuta: sono la stessa misura letta con due domande
            # diverse, e prenderla una volta sola qui evita che le due viste
            # finiscano a leggere due registri.
            parla=self.sta_parlando,
            fretta=m.timer("dub.rate_x1000").ultimo / 1000.0,
        )
        return dati

    @property
    def sta_parlando(self) -> bool:
        """Sta uscendo una battuta doppiata adesso? (l'alone sulla spia)

        E' l'unica cosa a cui serve il bagliore menta, in tutta la finestra.
        """
        p = self.pipeline
        if p is None:
            return False
        try:
            return p.mixer.finisce_a > p.mixer.now
        except Exception:
            return False

    # -- quello che la finestra chiede a lui -------------------------------

    @property
    def stato(self) -> str:
        """In che stato e' la sessione: **la fonte unica**, e non si deduce.

        Prima si deduceva da `bool(self.threads)`, in cinque punti di due
        finestre. Una quantita' dedotta in cinque punti e' una quantita' che al
        primo caso di bordo ha cinque valori — e infatti la finestra e' arrivata
        a dire «avviato» sopra un bottone Avvia premibile.
        """
        return self._stato

    @property
    def acceso(self) -> bool:
        """C'e' una sessione in piedi **o che sta salendo**.

        Il `bool(self.threads)` di prima escludeva la partenza: chi chiedeva
        «c'e' qualcosa da fermare?» durante il caricamento del TTS si sentiva
        rispondere di no, e ne apriva un'altra.
        """
        return self._stato in (IN_PARTENZA, ACCESA)

    def ritardo(self, ms: float) -> None:
        """Quanto e' vecchio il ritaglio quando arriva a schermo.

        Lo misura la finestra, perche' e' l'unica che sa quando ha disegnato;
        lo tiene il motore, perche' e' l'unico che scriva un rapporto.
        """
        self._t_ritardo.add(ms)

    def segui_finestra(self) -> None:
        """Il gioco si sposta, e il sottotitolo deve seguirlo.

        Una finestra spostata senza che l'overlay la segua e' un sottotitolo
        tradotto in mezzo al desktop. Costa una chiamata a Windows, e si fa
        insieme allo svuotamento della coda invece che a ogni fotogramma.
        """
        if self.finestra is None or self.overlay is None:
            return
        from capture.finestre import rettangolo_client, viva

        if not viva(self.finestra.hwnd):
            return
        r = rettangolo_client(self.finestra.hwnd)
        if r and r != self.overlay.ancora:
            self.overlay.aggancia(r)

    def prepara_overlay(self, costruisci) -> None:
        """L'overlay si decide **quando parte la catena**, non alla nascita della
        finestra.

        Era costruito nel costruttore, leggendo `translate.enabled` com'era
        all'avvio del programma. Accendendo la traduzione dalle impostazioni —
        cioe' il modo dichiarato di accenderla — la catena traduceva e **nessuno
        disegnava**: nel log dell'utente 26 battute su 27 tradotte e zero
        sottotitoli a schermo, senza un errore da nessuna parte. E' la forma di
        difetto peggiore di questo progetto: non un guasto, un silenzio.

        Si rifa' a ogni partenza invece di aggiornarlo: taglia, colore, modo e
        raggio si leggono alla costruzione, quindi un overlay tenuto in vita
        mostrerebbe la configurazione di prima — un altro «dichiarato e mai
        riletto», stavolta dentro la cura.
        """
        if self.overlay is not None:
            self.overlay.distruggi()
            self.overlay = None
        if not (self.cfg.translate.enabled and self.cfg.translate.overlay):
            return
        # **Chi disegna il tradotto ha bisogno di opencv, e lo si guarda
        # adesso.** Sfocatura e cancellatura lo importano *dentro* la funzione
        # che dipinge, cioe' dentro il ciclo video: bloccato, il difetto uscirebbe
        # come un ImportError su un fotogramma qualunque, dove nessuno lo collega
        # alla riga che l'ha acceso. Qui non si rinuncia a niente — il tradotto
        # si disegna lo stesso, con il riquadro pieno che non usa opencv — ma si
        # dice cosa non si potra' fare.
        from core import bloccati

        occhi = bloccati.pezzo("opencv")
        if not occhi.ok:
            self.manda("nota", "! " + bloccati.spiega("opencv")
                       + ". Il tradotto si disegna lo stesso: metti "
                         "translate.background_mode=riquadro")
        self.overlay = costruisci()
        self.overlay.riposiziona(self.cfg.vision.roi)
        if self.finestra is None:
            # Catturando lo schermo l'overlay ci rientra: va nascosto alla
            # cattura, e il prezzo e' che non lo vede nemmeno chi registra.
            self.overlay.aggancia(None)
            self.overlay.esclusione(True)
        else:
            from capture.finestre import rettangolo_client

            # Catturando la sola finestra del gioco non ci rientra affatto
            # (misurato: zero righe lette che fossero nostre su quattro), e
            # allora nasconderlo a tutte le catture e' un prezzo per niente.
            self.overlay.aggancia(rettangolo_client(self.finestra.hwnd))
            self.overlay.esclusione(False)

    # -- avvio -------------------------------------------------------------

    def avvia(self) -> bool:
        """Parte in un thread suo: aprire i device e caricare il TTS costa secondi.

        **Risponde `False` se non era fermo**, e non e' un dettaglio: il guardiano
        di prima (`if self.threads: return`) era cieco proprio nei secondi della
        partenza, cioe' esattamente quando qualcuno preme di nuovo perche' non
        vede succedere niente. Da li' due catene sullo stesso processo, ognuna
        con i suoi due thread e la sua pipeline.
        """
        with self._lucchetto:
            if self._stato != FERMO:
                return False
            self._stato = IN_PARTENZA
        self.stop.clear()
        threading.Thread(target=self._prepara, daemon=True).start()
        return True

    def _prepara(self) -> None:
        """Monta la catena e poi **dichiara come e' andata**, che sono due cose.

        Il montaggio (`_monta`) apre device, carica il TTS e fa partire i due
        cicli: costa secondi ed e' l'unica parte che tocchi l'hardware. Quello
        che sta qui e' la macchina degli stati — chi vince fra una partenza e un
        Ferma arrivato nel frattempo — ed e' la parte in cui i difetti non danno
        errore. Sono separate apposta: cosi' la suite prova **questo codice** con
        un montaggio finto, invece di provare una copia di questo codice.
        """
        try:
            if not self._monta():
                return
            # **Un Ferma arrivato mentre si apriva non si puo' ignorare.** In
            # quei secondi non c'era ancora niente da fermare, quindi `ferma()`
            # ha solo dichiarato l'intenzione: la chiusura tocca a chi ha
            # costruito, cioe' a qui. Senza questo ramo i due cicli restavano
            # vivi con la finestra che diceva «fermo» — due catene che suonano
            # insieme, e nessun contatore che lo dica.
            with self._lucchetto:
                fermare = self._stato == IN_ARRESTO
                if not fermare:
                    self._stato = ACCESA
            if fermare:
                self._chiudi()
                return
            self.manda("stato", "in corso")
        except Exception as exc:  # un errore di device non deve chiudere la finestra
            self.manda("nota", f"! avvio fallito: {type(exc).__name__}: {exc}")
            # **Un avvio fallito lasciava in piedi quello che aveva gia'
            # costruito**: catena, sessione e file delle impronte nascono prima
            # dei device, e dire «finito» e basta li lasciava vivi nel processo.
            # Un Avvia dopo l'altro ne accumulava una copia per volta. Si chiude
            # quello che c'e', come farebbe un Ferma.
            self._chiudi()

    def _monta(self) -> bool:
        """Device, catena, sessione e i due cicli. `False` = non se ne fa niente.

        Solleva se qualcosa non si apre: chi chiama sa cosa farne, e in un posto
        solo.
        """
        set_clock(RealClock())
        _loops, default = list_devices()
        entrata = find_loopback(self.opz.loopback)
        uscita = default
        if self.opz.output:
            # **Fra le uscite, non fra i loopback**: quelli hanno zero canali
            # di uscita, quindi il nome giusto dava `OSError -9998` e il nome
            # sbagliato dava la predefinita **in silenzio**, cioe' il
            # doppiaggio che suona da un'altra parte senza dirlo.
            uscita = find_output(self.opz.output)
        if stesso_dispositivo(entrata, uscita):
            self.manda("nota", f"! catturi e suoni sulla stessa scheda "
                               f"({nome_scheda(entrata)}): il doppiaggio rientrerebbe "
                               f"nella cattura e verrebbe ri-doppiato. Scegli un'altra "
                               f"uscita, oppure usa Voicemeeter.")
            # **Anche il rifiuto passa dalla chiusura**, che qui non ha
            # niente da chiudere ma rimette lo stato a `fermo`. Mandare solo
            # «finito» e lasciare lo stato com'era e' il modo in cui i bottoni
            # e la sessione hanno finito per dire due cose diverse.
            self._chiudi()
            return False
        self.manda("nota", f"carico {self.cfg.tts.backend}...")
        from tools.live import costruisci_tts

        tts = costruisci_tts(self.cfg.tts.backend, self.cfg)
        self.pipeline = DubPipeline(
            self.cfg, tts, samplerate=SR,
            dillo=lambda riga: self.manda("nota", riga),
        )
        self.pipeline.max_spoken = MAX_SPOKEN
        # **Se la traduzione fallisce, lo deve sapere chi guarda.** Il
        # ripiego «si tiene l'originale» e' giusto, ma da solo e' muto:
        # l'errore finiva su `stderr`, che dietro una finestra non lo legge
        # nessuno. Misurato nella sessione dell'utente: quattro sessioni,
        # zero traduzioni su diciannove battute, nessuna riga a schermo e
        # nessuna spiegazione.
        if getattr(self.pipeline, "traduci", None) is not None:
            self.pipeline.traduci.dillo = lambda riga: self.manda("nota", riga)
        # **`ui.save_mix` era dichiarato e non lo leggeva nessuno**: il
        # quinto campo di questa forma, dopo `max_ocr_hz`, `tts.device`,
        # `background_mode` e `overlay.ritardo`. Chi lo metteva a `false` si
        # ritrovava lo stesso 660 MB di RAM e 340 MB di WAV per mezz'ora.
        self.sessione = None if self.opz.no_save else Session(
            samplerate=SR, salva_mix=bool(self.cfg.ui.save_mix)
        )
        if self.sessione is not None and self.cfg.ui.save_mix:
            self.manda("nota", "registro l'audio: ~11 MB al minuto su disco, "
                               "fino a 660 MB di RAM (ui.save_mix=false lo spegne)")
        # **Il registro delle impronte anche dal vivo.** Senza, di una
        # sessione dal vivo si sa cosa e' stato detto ma non cosa il
        # riconoscitore ha visto — e quando dal vivo va peggio che sul banco
        # non c'e' modo di sapere se cambia il segnale, il ritaglio o il
        # modello. Costa due decimi di megabyte e si rigioca con
        # `tools.recluster`.
        if self.sessione is not None:
            self._registro = (self.sessione.dir / "speaker.jsonl").open(
                "w", encoding="utf-8"
            )
            self.pipeline.speaker_log = self._registro
        self.manda("nota", f"catturo: {entrata}")
        self.manda("nota", f"suono su: {uscita}")
        x, y, w, h = self.cfg.vision.roi
        self.manda("nota", f"ROI  x{x:.3f}  y{y:.3f}  w{w:.3f}  h{h:.3f}   "
                           f"attesa voce {self.cfg.speaker.decide_after_ms} ms")

        pronto = threading.Event()
        t_avvio = self.t_avvio = time.perf_counter()
        for f in (self._ciclo_audio, self._ciclo_video):
            t = threading.Thread(target=f, args=(entrata, uscita, pronto, t_avvio),
                                 daemon=True)
            t.start()
            self.threads.append(t)
        return True

    # -- il ciclo audio ----------------------------------------------------

    def _ciclo_audio(self, entrata, uscita, pronto, _t_avvio) -> None:
        # **Il guasto piu' probabile di tutti: le cuffie staccate a meta'
        # partita.** WASAPI non aspetta: il device sparisce e la lettura solleva.
        # Senza questo, il thread moriva **in silenzio** — il doppiaggio
        # ammutoliva, la finestra continuava a dire «in corso», e non c'era
        # niente da leggere. E' esattamente la forma dei difetti che questo
        # progetto ha imparato a temere: non un errore, un silenzio.
        #
        # Non si prova a riaprire il device da soli: il flusso audio ha una linea
        # temporale (`_marche`) che riparte da zero, e riprendere a meta' vorrebbe
        # dire programmare battute su un orologio che non esiste piu'. Si ferma
        # tutto e **si dice cosa e' successo**.
        try:
            with Loopback(entrata, block=self.opz.block, samplerate=SR) as ing, Player(
                uscita, block=self.opz.block, samplerate=SR
            ) as alt:
                self.pipeline.start_live()
                pronto.set()
                while not self.stop.is_set():
                    gioco = ing.read()
                    quando = self.pipeline.mixer.now
                    fuori = self.pipeline.on_audio(gioco, n=len(gioco))
                    alt.write(fuori)
                    if self.sessione is not None:
                        self.sessione.audio(fuori, quando)
        except Exception as guasto:
            pronto.set()  # se no il ciclo video aspetta dieci secondi per niente
            self.stop.set()  # il video senza audio non serve a niente
            # **Fermare i cicli non e' fermare la sessione.** Il riordino lo deve
            # fare il thread dell'interfaccia — da qui non si tocca ne' Tk ne'
            # Qt — quindi si manda un messaggio e ci pensa lei.
            self.manda("guasto", f"{type(guasto).__name__}: {guasto}")

    # -- il ciclo video ----------------------------------------------------

    def _apri_cattura(self):
        hwnd = self.finestra.hwnd if self.finestra is not None else None
        rois = (tuple(self.cfg.vision.roi),) if self.cfg.capture.solo_roi else ()
        return rois, apri_cattura(
            self.opz.backend, monitor=self.opz.monitor, hwnd=hwnd,
            rois=rois, margine=self.cfg.capture.roi_margin,
            dillo=lambda riga: self.manda("nota", riga),
        )

    def _ciclo_video(self, _entrata, _uscita, pronto, t_avvio) -> None:
        # La sorgente si apre **nel thread che la usa**: dxcam sta su COM, e
        # creata altrove non solleva — restituisce `None` a ogni grab.
        rois_aperte, schermo = self._apri_cattura()
        self.manda("nota", f"cattura: {schermo.name}")
        try:
            pronto.wait(timeout=10.0)
            periodo = 1.0 / max(1e-6, self.cfg.capture.fps)
            prossimo = time.perf_counter()
            n = vuoti = 0
            detto_nero = False
            while not self.stop.is_set():
                ora = time.perf_counter()
                if ora < prossimo:
                    time.sleep(min(0.002, prossimo - ora))
                    continue
                prossimo += periodo
                # **Se si e' rimasti indietro, si riparte da adesso.** Sommando il
                # periodo e basta, un giro lento lascia `prossimo` nel passato: il
                # ciclo smette di dormire e gira a tutta velocita' per rimettersi in
                # pari, prendendosi la CPU che serve al thread audio. Misurato nella
                # sessione dell'utente: `speaker.ring_lag` a 4674 ms, cioe' quasi
                # cinque secondi di campioni mai arrivati. Saltare i giri arretrati
                # costa qualche fotogramma; non saltarli costa l'audio.
                if prossimo < ora:
                    prossimo = ora + periodo
                # **L'area si sposta col mouse a sessione accesa, e la fascia
                # catturata deve seguirla.** Senza, spostare il rettangolo con la
                # cattura ridotta darebbe il difetto peggiore possibile: si legge il
                # **nero** fuori dalla vecchia fascia, e a schermo non succede piu'
                # niente.
                if rois_aperte and (tuple(self.cfg.vision.roi),) != rois_aperte:
                    schermo.close()
                    rois_aperte, schermo = self._apri_cattura()
                    self.manda("nota", "area cambiata: rifaccio la cattura")
                    continue
                g = schermo.grab()
                if not g.ok:
                    # **`None` vuol dire due cose diverse, e si distinguono solo dal
                    # tempo.** Desktop Duplication risponde `None` quando lo schermo
                    # non e' cambiato — normale — e risponde `None` anche quando non
                    # funziona affatto, che su questa macchina e' il caso: 1071 grab,
                    # zero fotogrammi, con un video a tutto schermo. La seconda non
                    # finisce mai, e senza questo ripiego la finestra resta li' a non
                    # fare niente **senza dire perche'**.
                    vuoti += 1
                    # `startswith` e non `==`: con la fascia sola il nome diventa
                    # `dxcam+roi`, e un confronto esatto avrebbe spento il ripiego
                    # proprio nella configurazione nuova.
                    if (n == 0 and vuoti > 2 * self.cfg.capture.fps
                            and schermo.name.startswith("dxcam")):
                        schermo.close()
                        rois_aperte = (tuple(self.cfg.vision.roi),) if self.cfg.capture.solo_roi else ()
                        schermo = apri_cattura(
                            "mss", monitor=self.opz.monitor,
                            rois=rois_aperte, margine=self.cfg.capture.roi_margin,
                        )
                        self.manda("nota",
                                   "! la cattura veloce non restituisce fotogrammi: passo a mss")
                        vuoti = 0
                    continue
                n += 1
                # **Un fotogramma nero non e' un errore, ed e' il difetto
                # peggiore che questa cattura possa avere.** `PrintWindow`
                # riesce anche su una finestra Direct3D che non ha una
                # superficie da consegnare: torna `1`, e dentro c'e' il buio.
                # La sessione resta accesa, i contatori restano verdi, l'OCR non
                # legge mai niente e sembra rotto lui. Si dichiara **una volta**,
                # appena la sorgente ha guardato abbastanza fotogrammi per
                # poterlo dire (`PrintWindowSource.nero`).
                if getattr(schermo, "nero", False) and not detto_nero:
                    detto_nero = True
                    self.manda("nota",
                               "! questo gioco non si lascia catturare per finestra: "
                               "i fotogrammi arrivano neri. Nella Preparazione scegli "
                               "lo schermo intero invece della finestra.")
                # **Il ritaglio per la sfocatura parte subito, prima dell'OCR.**
                # Stava in fondo al giro, dopo `on_frame`, e quindi pagava tutto il
                # costo del riconoscimento prima di essere spedito: misurato nella
                # sessione dell'utente, `vision.ocr` sta a **84 ms al p50 e 137 al
                # massimo** — cioe' la macchia arrivava a schermo con quattro
                # fotogrammi di ritardo sulla scena. Per sfocare non serve sapere cosa
                # c'e' scritto.
                if self.overlay is not None and self.overlay._visibile:
                    pezzo = ritaglia(g.frame, self.overlay.rett)
                    if pezzo is not None:
                        self.manda("aggiorna", (pezzo, time.perf_counter()))
                for riga in self.pipeline.on_frame(g.frame):
                    if self.sessione is not None:
                        self.sessione.line(riga)
                    self.manda("riga", (riga.speaker_id or "—",
                                        riga.voice_id or "(solo scritta)", riga.text,
                                        riga.live_latency_ms, time.perf_counter() - t_avvio))
                    # **La sostituzione grafica dal vivo.** Si passa dalla coda come
                    # tutto il resto: disegnare da qui vorrebbe dire toccare la
                    # finestra dal thread video. Si manda solo se c'e' stata una
                    # traduzione — se no si coprirebbe il sottotitolo con se' stesso.
                    if self.overlay is not None and riga.text_original:
                        # **Quanto resta a schermo il tradotto: quanto il sottotitolo
                        # del gioco, non quanto la nostra voce.** La durata dell'audio
                        # doppiato e' quasi sempre piu' corta della permanenza del
                        # sottotitolo: usando quella, la finestra spariva mentre
                        # l'originale era ancora li'.
                        resta = self.pipeline.timing.predict(riga.text)
                        fine = time.perf_counter() + max(riga.duration, resta)
                        # **La geometria viene dal fotogramma in cui il sottotitolo
                        # c'era, non da questo.** Fra la lettura e adesso sono passati
                        # piu' di due secondi: `inchiostro()` cercava l'inchiostro su
                        # una scena gia' cambiata, e cio' che trovava era scenario.
                        # `riga.boxes` sono le bande accettate allora.
                        # `riga.roi` dice **di quale area** sono quei rettangoli:
                        # con due aree dichiarate, prendere sempre `vision.roi`
                        # disegnerebbe la traduzione del cartello dentro la fascia
                        # del dialogo. Vuoto = la ROI, che e' il caso di sempre.
                        trovato = inchiostro_da_box(
                            g.frame, self.cfg, riga.boxes, riga.ink, riga.roi or None)
                        if trovato[0] is None:
                            trovato = inchiostro(g.frame, self.cfg)
                        self.manda("overlay", (riga.text, riga.text_original, fine,
                                               riga.t_subtitle, *trovato))
                # **Chi decide se il tradotto resta a schermo e' il lettore**, non un
                # orologio e nemmeno i pixel: prima si prolungava il timer finche' la
                # finestra era visibile — un anello chiuso su se' stesso — e la
                # finestra non spariva piu'.
                #
                # **Si contano i giri vuoti.** L'OCR perde una riga per qualche
                # fotogramma e la ritrova subito: spegnere al primo giro vuoto fa
                # lampeggiare il tradotto.
                if self.overlay is not None and self.overlay._visibile:
                    if self.pipeline.a_schermo(self.overlay.t_on):
                        self.overlay._vuoti = 0
                        self.overlay_fino_a = time.perf_counter() + 0.4
                    else:
                        self.overlay._vuoti += 1
                        if (self.overlay._vuoti >= self.cfg.translate.overlay_hold_frames
                                and time.perf_counter() >= self.overlay_fino_a):
                            self.manda("spegni", None)
                if n % 30 == 0:
                    p = len(self.pipeline.tracker) if self.pipeline.tracker else 0
                    riga = (f"in corso  |  {n} frame  |  {self.pipeline.dette} battute"
                            f"  |  {p} personaggi  |  {len(self.pipeline.pool)} voci")
                    # Le traduzioni fallite stanno **nella testata** e non solo nel
                    # log: il log scorre, e questa e' la differenza fra «sta
                    # doppiando» e «sta ripetendo l'originale».
                    tradu = getattr(self.pipeline, "traduci", None)
                    if tradu is not None and tradu.n_falliti:
                        riga += f"  |  ! {tradu.n_falliti} traduzioni fallite"
                    self.manda("stato", riga)
        finally:
            # **La cattura si chiude qui, e non e' un dettaglio di pulizia.**
            # I callback di WGC sono chiusure su se stessi: senza questa riga la
            # sorgente resta viva per tutto il processo e continua a copiare la
            # finestra del gioco a ogni fotogramma. Misurato, cinque Avvia nello
            # stesso processo lasciavano **cinque catture accese** — 285 copie al
            # secondo invece di 57 — e il costo si vedeva a valle: la sintesi da
            # 162,9 a 180,4 ms, `classify_lines` da 30 a 47. Non e' una perdita
            # di memoria che si nota: e' una sessione che va sempre peggio.
            schermo.close()

    # -- arresto -----------------------------------------------------------

    def ferma(self) -> None:
        """Chiude la sessione — e se sta ancora partendo, **dichiara di volerlo**.

        Fermare durante la partenza non e' fermare: aprire i device e caricare il
        TTS costa secondi, e in quei secondi non c'e' ancora niente da chiudere.
        Aspettarli qui vorrebbe dire il thread della finestra bloccato, cioe' la
        finestra congelata; non aspettarli affatto vorrebbe dire una catena che
        finisce di salire dopo che tutti hanno dichiarato «fermo» — ed e' cosi'
        che si e' arrivati a due catene vive, ai bottoni di una che rimettevano
        quelli dell'altra e a un Avvia che non faceva niente.

        Quindi qui si passa a «in arresto» e la chiusura vera la fa **chi sta
        partendo**, appena ha qualcosa in mano. Chi guarda i bottoni lo vede: in
        arresto non si preme niente, perche' non c'e' niente da chiedere.
        """
        with self._lucchetto:
            if self._stato == IN_ARRESTO:
                return  # ci sta gia' pensando qualcuno
            fra_poco = self._stato == IN_PARTENZA
            if fra_poco:
                self._stato = IN_ARRESTO
        if fra_poco:
            self.stop.set()
            return
        self._chiudi()

    def _chiudi(self) -> None:
        """Ferma i cicli **e** chiude la sessione. Le due cose non sono la stessa.

        La prima versione di questa cura si era fermata a meta': i due thread
        uscivano, ma la sessione restava aperta col WAV mai scritto. Qui si fa
        tutto e in ordine — thread, catena, rapporto, file — e ogni pezzo che
        possa fallire non deve impedire i successivi.

        **E adesso quella frase e' anche vera.** Era scritta e non fatta: il
        rapporto della catena stava fuori da qualunque `try`, quindi un
        `finish()` che sollevasse — su una catena costruita a meta' da un avvio
        fallito e' il caso normale — saltava il salvataggio, lo stato «fermo» e
        il «finito», cioe' lasciava esattamente i bottoni incoerenti che questo
        file esiste per non produrre piu'. Lo stato torna a `fermo` in ogni caso.
        """
        self._stato = IN_ARRESTO
        self.stop.set()
        for t in self.threads:
            t.join(timeout=2.0)
        self.threads.clear()
        try:
            if self.pipeline is not None:
                self.pipeline.finish()
                self.manda("nota", "--- personaggi ---")
                if self.pipeline.tracker is not None:
                    for r in self.pipeline.tracker.report().splitlines():
                        self.manda("nota", r)
                self.manda("nota", self.pipeline.pool.report())
        except Exception as exc:
            self.manda("nota", f"! chiusura della catena fallita: "
                               f"{type(exc).__name__}: {exc}")
        if self.sessione is not None:
            try:
                if self._registro is not None:
                    self._registro.close()
                    self._registro = None
                # **Il riepilogo va nella cartella, non solo sul terminale.**
                # Senza, `mix.underrun` e `speak.first_sample` restano nella
                # finestra e muoiono con lei — e sono esattamente i due numeri che
                # dicono se lo streaming ha retto. Con loro va `overlay.ritardo`,
                # che veniva misurato a ogni giro e poi buttato.
                rapporto = self.pipeline.report() if self.pipeline is not None else ""
                rapporto = f"{rapporto}\n\n-- finestra --\n{self.metriche.report()}"
                self.manda("nota", f"sessione salvata in "
                                   f"{self.sessione.close(self.cfg, rapporto)}")
            except Exception as exc:
                self.manda("nota", f"! salvataggio fallito: {exc}")
        self.pipeline = None
        self.sessione = None
        self._registro = None
        # **Lo stato prima dei messaggi.** Chi riceve «finito» ridipinge i
        # bottoni leggendo `stato`: mandandolo prima, la finestra leggerebbe «in
        # arresto» e si spegnerebbe tutta, restando cosi' fino al giro dopo.
        self._stato = FERMO
        self.manda("stato", "fermo")
        self.manda("finito", None)
