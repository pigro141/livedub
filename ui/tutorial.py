"""Il tutorial iniziale: **una guida che porta a una sessione che funziona**.

Non un carosello di schermate. Chi apre questo programma per la prima volta non
sa cos'e' un loopback, non sa che il gioco deve stare in finestra, e non ha mai
sentito nominare Voicemeeter — e se dopo sette schermate non riesce a sentire una
battuta doppiata, il tutorial ha fallito anche se e' bello.

## Dove puo', **controlla** invece di chiedere fiducia

Il programma sa gia' rispondere da solo a meta' delle domande che il tutorial
pone: quante schede audio ci sono e se una e' la stessa da tutti e due i lati
(`capture/audio.py`), se OneOCR e' stato copiato, se il provider CUDA c'e'
davvero (`core/onnx.py`), quanto e' alta l'area di adesso (`vision/roi.py`).
Ogni passo che puo' essere verificato porta la sua riga di verifica, ed e' la
differenza fra una guida e un depliant: qui un ripiego silenzioso e' gia' costato
due volte, e una guida che *dice* «adesso funziona» senza guardare e' un ripiego
silenzioso con le illustrazioni.

## Le verifiche non passano dal catalogo, e il perche' e' gia' scritto altrove

Dentro ci sono nomi di dispositivi, percorsi e numeri — «Altoparlanti (Realtek
USB2.0 Audio)», `0.18`, `CUDAExecutionProvider`. E' la stessa regola del registro
e della barra della misura: quei widget sono marcati `nontradurre`, e cio' che di
loro **e'** una frase nostra viaggia come **modello** (`MODELLI`) tradotto pezzo
per pezzo e poi riempito. La ragione sta in `ui/lingua.py`: tradurre la frase
gia' composta significa mettere in catalogo una chiave che corrisponde a un
istante e a nessun altro.

## Le stringhe di una finestra che non esiste

`tools/traduci_ui.py --estrai` costruisce la finestra e la **percorre**: un
dialogo che nasce solo quando lo si apre non lo vede nessuno, e le sue parole
resterebbero in italiano in mezzo a una finestra tradotta. E' lo stesso problema
di `ui.lingua.COMPOSTE` e ha la stessa cura: `testi()` dichiara tutto quello che
questo dialogo dice, `ui.lingua.fuori_dalla_passeggiata()` lo somma alle chiavi,
e la verifica `tutorial` costruisce il dialogo davvero e pretende che le due
liste coincidano — un paragrafo aggiunto e non dichiarato rende la suite rossa
invece di uscire in italiano.

## Saltarlo non deve costare niente

Si apre da solo la prima volta e mai piu' (`core.preferenze.tutorial_da_mostrare`,
che sta fuori da Qt apposta: «va mostrato?» e' una regola, e si verifica senza
aprire una finestra). Si puo' saltare sempre, e saltarlo segna la stessa cosa che
finirlo — se no si riaprirebbe a ogni avvio, cioe' saltarlo lascerebbe il
programma **peggio** di non averlo mai aperto.

## Quello che scrive, e solo se glielo si chiede

Due cose, e tutte e due dopo un gesto: la **lingua**, se la si sceglie, e i
**motori**, se si preme il bottone del passo 6. Niente parte da solo: il banco
misura e scarica fino a mezzo gigabyte, e un dialogo che comincia a scaricare
perche' lo si e' aperto e' peggio di uno che non scarica affatto.

La regola che decide *quali* motori sta in `core/banco.py` e non qui, per la
ragione di sempre — si prova con numeri finti, senza CUDA, senza rete e senza
aprire una finestra. Qui restano le parole con cui la si racconta, che e' l'unica
cosa che ha bisogno del catalogo.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core import preferenze
from ui import lingua
from ui import qt_tema as tema

# La misura del dialogo. La larghezza e' quella che `ui/qt_audio.py` usa gia' per
# la sua spiegazione dell'audio: due finestre d'aiuto della stessa taglia si
# leggono come lo stesso oggetto.
#
# **L'altezza e' stata misurata sul catalogo piu' lungo e non scelta.** A 560 e a
# 620 il passo delle sei schede, in tedesco, finiva sotto il bordo: la barra di
# scorrimento compariva — quindi il difetto non era muto — ma un elenco che si
# legge tutto in italiano e a meta' in tedesco e' esattamente cio' che
# `tools/traduci_ui.py --misura` esiste per prendere. A 680 ci sta intero, e
# 680 piu' la barra del titolo sta ancora dentro uno schermo da 768.
LARGO, ALTO = 760, 680

# Dove si scarica Voicemeeter. Sta gia' in `ui/qt_audio.py`, e si prende da li'
# invece di riscriverlo: un indirizzo copiato due volte e' un indirizzo che
# invecchia una volta sola.
from ui.qt_audio import SCARICA_VOICEMEETER  # noqa: E402


# ======================================================== quello che si dice ==


@dataclass(frozen=True)
class Passo:
    """Un passo: il titolo, i paragrafi, e semmai un pezzo vivo da montarci.

    `vivo` e' il nome di cio' che va costruito sotto il testo — la scelta della
    lingua, la riga di verifica dell'audio — e non un widget: questo elenco deve
    restare leggibile (e traducibile) senza aprire Qt.
    """

    titolo: str
    righe: tuple[str, ...]
    vivo: str = ""


PASSI: tuple[Passo, ...] = (
    Passo(
        "La lingua di questa finestra",
        (
            "Il programma si e' aperto nella lingua in cui usi Windows. Se non e' "
            "quella che vuoi, cambiala qui: cambia subito, senza riavviare niente.",
            "Non e' la lingua del doppiaggio. Quella si sceglie nella scheda "
            "«Traduzione», e sono due cose diverse apposta: qui decidi cosa c'e' "
            "scritto sui bottoni, li' decidi cosa viene detto.",
        ),
        vivo="lingua",
    ),
    Passo(
        "L'audio: cosa sente il programma, e dove suona",
        (
            "Il programma ascolta una scheda audio per sentire il gioco e ne usa "
            "un'altra per farti sentire la voce doppiata. Non serve un microfono e "
            "non serve nessun cavo: Windows sa gia' far riascoltare quello che una "
            "scheda sta suonando.",
            "L'unica regola e' che le due non siano la stessa scheda. Se lo "
            "fossero, la voce doppiata rientrerebbe nella cattura, verrebbe "
            "doppiata di nuovo, e in due secondi avresti un fischio. Il programma "
            "se ne accorge e non parte.",
            "Voicemeeter non serve. Il loopback di Windows e' incluso e basta: due "
            "uscite diverse — le cuffie e gli altoparlanti, o l'audio del monitor "
            "via HDMI — e sei a posto. Voicemeeter serve solo se vuoi tutto in un "
            "paio di cuffie sole, e costa un'installazione e un riavvio.",
            "Le due scelte, con il bottone che prova ad ascoltare davvero, stanno "
            "nel passo 3 della scheda «Preparazione».",
        ),
        vivo="audio",
    ),
    Passo(
        "La finestra del gioco",
        (
            "Si cattura una finestra sola, non lo schermo. Cosi' nel fotogramma che "
            "va a leggere il testo non entra nient'altro: nemmeno queste nostre "
            "finestre, che altrimenti il programma finisce per leggere al posto del "
            "gioco.",
            "Quindi il gioco deve stare in finestra o senza bordi, non a schermo "
            "intero esclusivo. Nelle opzioni video dei giochi c'e' quasi sempre "
            "«Senza bordi», e a vedersi e' identico allo schermo intero.",
            "Il vantaggio si sente subito: il rettangolo dei sottotitoli e' "
            "relativo alla finestra, quindi se sposti il gioco l'area lo segue.",
        ),
    ),
    Passo(
        "L'area dei sottotitoli: stretta",
        (
            "Tira un rettangolo stretto attorno alla riga dei sottotitoli, non "
            "attorno a mezzo schermo.",
            "Se lo tiri largo il programma legge lo stesso: un'area grande e' meno "
            "precisa, non muta.",
            "Quello che peggiora davvero e' la grafica: il tradotto viene disegnato "
            "sopra l'originale ricostruendo lo sfondo attorno alla riga, e piu' "
            "l'area e' alta piu' quella ricostruzione prende roba che non c'entra. "
            "Sopra 0,12 di altezza il programma te lo dice, mentre tiri il "
            "rettangolo e quando avvii la catena. Il rettangolo si tira dal passo 2 "
            "della scheda «Preparazione».",
        ),
        vivo="area",
    ),
    Passo(
        "Le sei schede, in due righe l'una",
        (
            "Nessuna di queste va toccata per sentire la prima battuta: si aprono "
            "quando serve.",
        ),
        vivo="schede",
    ),
    Passo(
        "Questo PC: cosa riesce a fare, e cosa manca",
        (
            "Quale voce e quale traduttore convengano non si decide a occhio: "
            "dipende da questa macchina, e si decide con un numero. Il bottone "
            "qui sotto misura, sceglie da solo e scarica quello che manca. Meno "
            "di un minuto, piu' il tempo dello scaricamento.",
            # **Niente asterischi nei paragrafi.** Sono `QLabel` di testo
            # semplice, non Markdown: visto nella schermata, i due asterischi si
            # leggevano tali e quali in mezzo alla frase.
            "Serve perche' un modello che manca non da' errore. I programmi sono "
            "gia' installati; i modelli no — si prendono alla prima richiesta, e "
            "se non arrivano il programma non si ferma: ripiega su qualcosa di "
            "piu' leggero e va avanti. Senza questo passo staresti ascoltando il "
            "ripiego senza saperlo.",
            "Non installa nessun programma, e non e' pigrizia: i programmi di "
            "questo ambiente dipendono l'uno dall'altro, e installarne uno da qui "
            "potrebbe spegnere la scheda video senza dirlo. Se ne manca uno, "
            "trovi qui sotto la riga esatta da incollare.",
        ),
        vivo="banco",
    ),
    Passo(
        "Premi Avvia, e guarda due cose",
        (
            "Da quel momento il programma legge lo schermo, capisce chi parla dalla "
            "voce, sintetizza la battuta e la mixa abbassando l'audio del gioco.",
            "La voce arriva sempre un po' dopo il sottotitolo, ed e' voluto: mezzo "
            "secondo serve a capire chi sta parlando prima di scegliere la voce. "
            "Misurato dal vivo: circa 670 ms con Piper, circa 1150 ms con Kokoro.",
            "La prima cosa da guardare e' il registro, nella scheda «Sessione»: un "
            "colore per personaggio, perche' la domanda che ti fai guardandolo non "
            "e' «cosa ha detto» ma «e' sempre lo stesso a parlare?».",
            "La seconda e' la barra in fondo alla finestra: letture al secondo, "
            "battute, latenza, compressione, underrun. L'unico rosso e' underrun, e "
            "non e' un numero fuori norma: e' una battuta che non si e' sentita.",
        ),
    ),
)


# Le schede, come le nomina `tools/ui_qt.py`, con due righe ciascuna. I nomi
# sono le **stesse stringhe** delle linguette, quindi il catalogo li traduce una
# volta sola e la scheda si chiama qui come si chiama li'.
SCHEDE: tuple[tuple[str, str], ...] = (
    ("Preparazione",
     "I quattro passi in ordine: cosa catturare, dove sono i sottotitoli, "
     "l'audio, come leggere. E' l'unica che serve prima di premere Avvia."),
    ("Sessione",
     "Il registro dal vivo: chi parla, con che voce, quanto ci ha messo. "
     "E i tre passi ancora da fare, finche' ce ne sono."),
    ("Voce",
     "Come suona il doppiaggio: il motore, quante voci, quanta fretta. La "
     "fretta si sente subito, il motore al prossimo avvio."),
    ("Volumi",
     "Quanto forte la nostra voce e quanto quella del gioco, che non si toglie "
     "ma si abbassa dov'e' il parlato. Si cambia mentre ascolti."),
    ("Traduzione",
     "Solo se vuoi giocare in una lingua diversa da quella dei sottotitoli. "
     "Spenta, il programma doppia nella lingua che trova."),
    ("Tutte le impostazioni",
     "Tutte le manopole, con la spiegazione e la misura di ognuna. Serve a chi "
     "tara; la casella in alto cerca un campo per nome."),
)


# I bottoni e le poche etichette fisse. Stanno qui e non sparsi nel codice per la
# stessa ragione per cui ci stanno i paragrafi: `testi()` deve poter dichiarare
# **tutto** quello che questo dialogo dice, e una stringa scritta a mano dentro un
# `QPushButton` piu' in basso e' esattamente quella che sfugge.
TITOLO = "Prima di cominciare"
SOTTOTITOLO = "dalla lingua della finestra alla prima battuta doppiata"
# **Le etichette dei bottoni sono frasi, non parole, e non e' uno sfizio.** La
# prima stesura diceva «Avanti», «Indietro», «Salta»: tre parole che in italiano
# sono chiarissime e che un traduttore automatico non puo' disambiguare, perche'
# non sa che stanno su un bottone. Misurato sui cataloghi veri: «Avanti» e'
# tornato «Go ahead», «Gehen Sie voran», «Allez-y» — cioe' un incoraggiamento, e
# «Salta» e' diventato «Sauter», che in francese e' il salto. Un contesto scritto
# nella chiave costa due parole e toglie l'ambiguita' in tutte e quarantuno le
# lingue insieme; e' la stessa lezione di `uk — Ucraino` diventato «Regno Unito».
SALTA = "Salta la guida"
INDIETRO = "Passo precedente"
AVANTI = "Passo successivo"
FINE = "Chiudi la guida"
SCARICA = "Scarica Voicemeeter (facoltativo)"
# **Il bottone del banco dice cosa fa, non «Avvia».** Preme chi non sa cos'e' un
# motore di sintesi, e sotto quel bottone ci sono fino a mezzo gigabyte di
# scaricamento: un'etichetta corta qui vorrebbe dire un download a sorpresa.
MISURA = "Misura questo PC e scarica quello che manca"
# E si annulla **fra un pezzo e l'altro**: un trasferimento interrotto a meta'
# lascia un file troncato, ed e' precisamente il difetto che il controllo di
# completezza degli stili esiste per non avere. L'etichetta lo dice, se no il
# bottone sembra rotto per i secondi in cui non succede niente.
ANNULLA = "Annulla: si ferma dopo il file che sta scaricando"
NIENTE_DA_FARE = "c'e' gia' tutto: non serve scaricare niente"

# **Perche' si e' scelto cosi'.** Le regole stanno in `core/banco.py` e parlano
# per **codici** (`cuda_no`, `sintesi_lenta`); qui ci sono le frasi, che e'
# l'unica meta' che ha bisogno di un catalogo. Le due liste non possono
# scollarsi: la verifica `banco` pretende che le chiavi di questo dizionario
# siano esattamente `core.banco.MOTIVI` — un codice nuovo e non tradotto
# uscirebbe come una riga **vuota**, cioe' la spiegazione sparita senza errore.
MOTIVI: dict[str, str] = {
    "cuda_si":
        "c'e' una scheda video utilizzabile: viene usata la voce che articola "
        "meglio",
    "cuda_no":
        "nessuna scheda video utilizzabile: la voce migliore costerebbe 725 ms "
        "per ogni frase detta invece di 207, quindi resta la voce leggera",
    "cuda_persa":
        "la scheda video e' stata chiesta, ma e' arrivato {0}: sarebbero i "
        "tempi del processore",
    "sintesi_ok":
        "la voce costa {0} ms per ogni frase detta, su questo PC",
    "sintesi_lenta":
        "la voce costa {0} ms per ogni frase detta, piu' dei {1} che si "
        "accettano: si torna alla voce leggera",
    "passo_corto":
        "questo motore dice {0} caratteri al secondo invece di {1}: ogni frase "
        "uscirebbe schiacciata",
    "traduzione_locale":
        "la traduzione resta su questo PC: nessun sottotitolo esce da qui",
    "traduzione_llm":
        "la traduzione resta su questo PC, con il modello in memoria: piu' lenta "
        "della prima scelta ma non esce niente",
    "traduzione_manca":
        "manca il programma della traduzione locale. Da incollare in PowerShell, "
        "nella cartella del programma: {0}",
    "traduzione_lenta":
        # **I due numeri hanno tutti e due la loro unita', e sono due frasi.**
        # Con «piu' dei {1} di attesa» l'hindi si e' **mangiato il secondo
        # segnaposto**: una cifra sparita e nessun errore, perche' `format`
        # non si lamenta di un argomento in piu'. La verifica dei segnaposto
        # l'ha preso, e la cura sta nella frase italiana e non in un catalogo.
        "la traduzione costa {0} ms, e l'attesa per sapere chi parla e' di "
        "{1} ms: la voce arrivera' piu' tardi",
    "motore_mancante":
        "il modello della voce migliore non e' arrivato: resta la voce leggera",
}

# Come si chiamano i pezzi, per chi guarda scaricare. I codici sono quelli di
# `core.banco.PEZZI` piu' le due fasi di misura, che passano dallo **stesso**
# canale di avanzamento: due canali vorrebbero dire due posti in cui aggiornare
# la stessa riga a schermo, e il secondo non lo aggiorna mai nessuno.
PEZZI_NOMI: dict[str, str] = {
    "piper": "le due voci italiane",
    "kokoro": "il modello della voce",
    "voci_kokoro": "gli stili di voce",
    "ecapa": "il riconoscimento di chi parla",
    "oneocr": "il lettore di testo di Windows",
    "traduzione": "la coppia di lingue",
    "misura_sintesi": "sto misurando la voce",
    "misura_traduzione": "sto misurando la traduzione",
}

# **Quello che si vede solo mentre il banco lavora, o dopo che ha finito.**
# La verifica `tutorial` percorre il dialogo passo per passo e pretende che ogni
# stringa dichiarata compaia **davvero** — una riga elencata e mai mostrata e'
# una chiave tradotta per niente. Queste compaiono, ma in stati che quella
# passeggiata non attraversa: il bottone mentre scarica, la riga di «c'e' gia'
# tutto», e i nomi dei pezzi, che finiscono **dentro** un modello riempito e
# quindi dentro un widget `nontradurre`. Dichiararle qui e' la differenza fra
# una verifica che sa cosa aspettarsi e una che si disattiva.
SOLO_DURANTE: tuple[str, ...] = (ANNULLA, NIENTE_DA_FARE, *PEZZI_NOMI.values())

# **Le frasi che si compongono a runtime.** Dentro ci finiscono nomi di
# dispositivi, codici di lingua e numeri, quindi il widget che le porta e'
# marcato `nontradurre` e la passeggiata non le vede: si traduce il **modello** e
# poi lo si riempie. E' la regola di `ui.lingua.traduci`, e la verifica
# `tutorial` legge il sorgente di questo file per pretendere che ogni modello
# usato stia qui dentro — un modello nuovo e non dichiarato rende la suite rossa
# invece di uscire in italiano in mezzo a una finestra tradotta.
# **E i segnaposto sono numerati, che e' l'unica forma che sopravvive.** La
# prima stesura usava dei nomi — `{nome}`, `{entrate}`, `{ocr}` — e un traduttore
# automatico dentro le graffe ci vede delle parole: misurato sui cataloghi veri,
# `{nome}` e' tornato `{Name}` in tedesco, `{имя}` in russo, `{ن}` in arabo.
# **Tutte e quarantuno le lingue avevano almeno un modello rotto**, quindi ogni
# riga di verifica ricadeva sull'italiano — il ripiego funzionava, e proprio per
# questo non si vedeva: nessun errore, nessun contatore, e la funzione morta.
#
# Con `{0}` e `{1}` non c'e' niente da tradurre dentro le graffe, e riprovato su
# otto lingue diverse sono tornati intatti tutte le volte. Numerati e non `{}`
# perche' una frase si **riordina**: l'hindi ha restituito «{1} का चरण {0}», e
# con dei segnaposto anonimi i due valori sarebbero finiti scambiati **senza
# nessun errore**, che e' il difetto peggiore dei due.
MODELLI: tuple[str, ...] = (
    "passo {0} di {1}",
    "«come Windows» qui vuol dire: {0}",
    "per «{0}» non c'e' ancora un catalogo: resta l'italiano",
    "{0} schede audio da ascoltare, {1} su cui suonare",
    "non riesco a leggere le schede audio: {0}",
    "l'area di adesso e' alta {0} dello schermo",
    "lettura del testo: {0}",
    "scheda video: {0}",
    "motore della voce: {0}",
    # Il banco: cosa sta facendo, quanto manca, e cosa non ce l'ha fatta.
    "{0} di {1}: {2}",
    "da scaricare: {0} MB",
    "pronto: {0} MB scaricati",
    "{0}: non riuscito — {1}",
    *MOTIVI.values(),
)


def testi() -> tuple[str, ...]:
    """Tutto quello che questo dialogo dice, senza doppioni e in ordine.

    Serve a `ui.lingua.fuori_dalla_passeggiata()`: un dialogo che non esiste
    finche' non lo si apre non puo' essere trovato percorrendo la finestra, e
    senza questa dichiarazione le sue parole non finirebbero in nessun catalogo.
    """
    fuori: list[str] = [TITOLO, SOTTOTITOLO, SALTA, INDIETRO, AVANTI, FINE, SCARICA,
                        MISURA, ANNULLA, NIENTE_DA_FARE]
    for p in PASSI:
        fuori.append(p.titolo)
        fuori.extend(p.righe)
    for nome, riga in SCHEDE:
        fuori.extend((nome, riga))
    # I nomi dei pezzi sono frasi intere e non modelli: finiscono **dentro** un
    # modello come valore, quindi vanno tradotti per conto loro. Senza questa
    # riga la frase uscirebbe tradotta con dentro un pezzo di italiano, che e'
    # peggio dell'italiano intero — sembra una parola che non si traduce.
    fuori.extend(PEZZI_NOMI.values())
    fuori.extend(MODELLI)
    return tuple(dict.fromkeys(fuori))


# ====================================================== quello che si verifica =


@dataclass(frozen=True)
class Esito:
    """Una riga di verifica: e' andata bene, e cosa si e' trovato."""

    ok: bool
    testo: str


def _T(modello: str, codice: str, *valori) -> str:
    """Un modello tradotto e poi riempito. Si veda `MODELLI`.

    **Un traduttore automatico puo' rompere un segnaposto.** `{n}` che torna
    `{ n }` o `｛n｝` fa sollevare `format`, e sollevare qui vuol dire un dialogo
    che non si apre per una parola in fiammingo. Si ricade sull'italiano, che e'
    il testo del sorgente: una riga nella lingua sbagliata e' un difetto, una
    finestra che non si apre e' un guasto.
    """
    tradotto = lingua.traduci(modello, codice)
    try:
        return tradotto.format(*valori)
    except (KeyError, IndexError, ValueError):
        return modello.format(*valori)


def controllo_lingua(cfg) -> Esito:
    """Che lingua ha trovato `auto`, e se per quella c'e' un catalogo."""
    codice = cfg.ui.lingua
    scelta = lingua.risolvi(codice)
    perche = lingua.perche_italiano(codice)
    if perche == "senza catalogo":
        return Esito(False, _T("per «{0}» non c'e' ancora un catalogo: "
                               "resta l'italiano", scelta,
                               lingua.di_sistema() if codice == "auto" else codice))
    if codice != "auto":
        return Esito(True, "")
    from translate.lingue import nome_it

    return Esito(True, _T("«come Windows» qui vuol dire: {0}", scelta,
                          nome_it(scelta)))


def controllo_audio(cfg) -> Esito:
    """Quante schede ci sono da ascoltare e su quante si puo' suonare.

    **Non dice «l'audio e' a posto»**, che sarebbe una promessa: dice cosa c'e'.
    Con una sola uscita e nessuna scheda finta le due scelte finirebbero per
    forza sullo stesso dispositivo, ed e' l'unico caso in cui questa riga e' un
    avviso invece di un conto.
    """
    scelta = lingua.risolvi(cfg.ui.lingua)
    try:
        from capture.audio import list_devices, uscite

        loops, _predefinita = list_devices()
        fuori = uscite()
    except Exception as guasto:  # nessun WASAPI, driver assente, macchina virtuale
        return Esito(False, _T("non riesco a leggere le schede audio: {0}",
                               scelta, f"{type(guasto).__name__}: {guasto}"))
    return Esito(len(loops) >= 1 and len(fuori) >= 2,
                 _T("{0} schede audio da ascoltare, {1} su cui suonare",
                    scelta, len(loops), len(fuori)))


def controllo_area(cfg) -> Esito:
    """Quanto e' alta l'area di adesso, misurata con la regola vera."""
    from vision.roi import troppo_grande

    scelta = lingua.risolvi(cfg.ui.lingua)
    roi = cfg.vision.roi
    return Esito(not troppo_grande(roi),
                 _T("l'area di adesso e' alta {0} dello schermo", scelta,
                    f"{float(roi[3]):.2f}"))


def controllo_macchina(cfg) -> tuple[Esito, ...]:
    """Cosa c'e' davvero su questo PC: il lettore, la scheda video, il motore.

    Sono le tre cose che decidono com'e' la sessione, e sono tutte e tre gia'
    interrogabili — `installa.ps1` fa esattamente questi controlli. Il provider
    CUDA si **guarda** invece di dedurlo dal nome del pacchetto: chiedere un
    acceleratore non e' ottenerlo, ed e' il difetto che `core/onnx.py` esiste per
    chiudere.
    """
    from pathlib import Path

    scelta = lingua.risolvi(cfg.ui.lingua)
    fuori: list[Esito] = []

    radice = Path(__file__).resolve().parent.parent
    ha_oneocr = (radice / "models" / "oneocr" / "oneocr.onemodel").is_file()
    fuori.append(Esito(ha_oneocr, _T("lettura del testo: {0}", scelta,
                                     "OneOCR" if ha_oneocr else "PP-OCR")))

    try:
        from core.onnx import preload

        preload()
        import onnxruntime as rt

        ha_cuda = "CUDAExecutionProvider" in rt.get_available_providers()
        gpu = "CUDA" if ha_cuda else "CPU"
    except Exception as guasto:  # onnxruntime assente o rotto
        ha_cuda, gpu = False, f"{type(guasto).__name__}"
    fuori.append(Esito(ha_cuda, _T("scheda video: {0}", scelta, gpu)))

    fuori.append(Esito(True, _T("motore della voce: {0}", scelta,
                                cfg.tts.backend)))
    return tuple(fuori)


def motivo_in_riga(m, codice_lingua: str) -> str:
    """Un `core.banco.Motivo` diventa una frase, nella lingua della finestra.

    Sta fuori dalla classe perche' e' l'unico pezzo di traduzione del banco che
    si puo' provare senza costruire il dialogo — e un `Motivo` senza frase e' una
    riga vuota a schermo, cioe' il difetto che non da' errore.
    """
    modello = MOTIVI.get(m.codice)
    if not modello:
        # Non puo' succedere finche' la verifica `banco` e' verde. Se succede,
        # meglio il codice nudo che una riga vuota: un nome strano si vede, il
        # nulla no.
        return m.codice
    return _T(modello, codice_lingua, *m.valori)


class _Lavoro(QThread):
    """Il banco, in un thread suo. **La guida non si deve poter bloccare.**

    E' un dialogo modale, e in questo progetto un modale ha gia' tenuto ferma la
    suite oltre dieci minuti senza stampare una riga — non rossa: appesa. Qui il
    lavoro dura da qualche secondo a qualche minuto (mezzo gigabyte di modelli),
    e farlo nel thread della finestra vorrebbe dire una finestra che non si
    ridisegna, cioe' Windows che la dichiara «non risponde» mentre invece sta
    lavorando benissimo.

    **Il padre e' l'applicazione e non il dialogo**, ed e' la riga che evita un
    crash: chiudendo la guida a scaricamento in corso, un `QThread` figlio del
    dialogo verrebbe distrutto mentre gira. Cosi' invece finisce per conto suo —
    e finire e' innocuo, perche' l'unico effetto e' che i modelli sono sul disco,
    che e' esattamente cio' che si voleva.
    """

    avanza = Signal(str, int, int)
    finito = Signal(object)

    def __init__(self, cfg) -> None:
        from PySide6.QtWidgets import QApplication

        super().__init__(QApplication.instance())
        self.cfg = cfg
        self._ferma = False

    def annulla(self) -> None:
        self._ferma = True

    def run(self) -> None:  # pragma: no cover - gira solo con un dito sopra
        from core import banco

        try:
            esito = banco.esegui(self.cfg, passo=self.avanza.emit,
                                 fermati=lambda: self._ferma)
        except Exception as guasto:
            # **Un guasto qui non deve sparire.** Il thread muore in silenzio di
            # suo: senza questa riga il bottone resterebbe «Annulla» per sempre,
            # con la barra che scorre su un lavoro che non c'e' piu'.
            esito = guasto
        self.finito.emit(esito)


# ============================================================== il dialogo ====


class Tutorial(QDialog):
    """Sette passi, uno alla volta, e in fondo tre bottoni sempre uguali.

    Uno alla volta e non una pagina sola da scorrere: una pagina lunga si legge
    in diagonale, e i due passi che qui contano davvero — l'audio e l'area — sono
    proprio quelli che in diagonale sembrano ovvi.
    """

    def __init__(self, padre=None, *, prima_volta: bool = False, cfg=None) -> None:
        super().__init__(padre)
        self.padre = padre
        self.cfg = cfg if cfg is not None else padre.cfg
        self._prima_volta = prima_volta
        self._i = 0
        # Lo stato del banco vive sul **dialogo** e non sul widget del passo:
        # navigando avanti e indietro `_mostra()` ricostruisce la pagina da zero,
        # e uno stato tenuto nel widget sparirebbe insieme a lui — cioe' un
        # scaricamento in corso che a tornare indietro sembra non essere mai
        # partito.
        self._lavoro: _Lavoro | None = None
        self._banco_esito = None
        self._banco_riga = ""
        # Quanto si sta per scaricare, detto **prima** di premere. Si calcola una
        # volta e si tiene: guardare il disco costa poco, ma rifarlo a ogni
        # ridisegno della pagina lo farebbe pagare anche a chi passa di li' e va
        # avanti.
        self._banco_da_prendere = None
        # Lo stato in cui **posare** il banco per fotografarlo. Si veda
        # `posa_banco`.
        self._banco_posa = ""
        # I tre widget vivi del passo 6, o `None` se la pagina di adesso e'
        # un'altra. Si azzerano in cima a `_mostra()`: toccare da un segnale un
        # widget che Qt ha gia' distrutto e' un crash, e i segnali arrivano
        # quando pare a loro.
        self._b_bottone = None
        self._b_stato = None
        self._b_barra = None

        self.setWindowTitle(TITOLO)
        self.setModal(True)
        self.resize(LARGO, ALTO)
        # Con un padre il foglio di stile della finestra scende fin qui da solo.
        # Senza — le schermate, una prova — no, e il dialogo uscirebbe con i
        # colori di serie di Qt: cioe' una fotografia che non puo' mostrare il
        # difetto che si sta cercando.
        if padre is None:
            from PySide6.QtWidgets import QApplication

            self.setStyleSheet(tema.foglio(tema.attuale(QApplication.instance())))

        L = QVBoxLayout(self)
        L.setContentsMargins(tema.S5, tema.S5, tema.S5, tema.S5)
        L.setSpacing(tema.S3)
        L.addWidget(self._testata())

        # Il corpo scorre: in tedesco gli stessi paragrafi sono piu' lunghi, e un
        # testo che esce dal dialogo senza una barra di scorrimento e' un testo
        # che non si legge. La misura vera si prende con `tools/traduci_ui.py
        # --misura`, ma una guardia costa una riga.
        self._scorre = QScrollArea()
        self._scorre.setWidgetResizable(True)
        self._scorre.setFrameShape(QFrame.NoFrame)
        L.addWidget(self._scorre, 1)

        L.addWidget(self._piede())
        self._mostra()
        # Il dialogo si veste da solo: aperto dalla finestra la vestirebbe anche
        # `vesti_lingua`, ma aperto da uno strumento (le schermate) no — e una
        # finestra d'aiuto in italiano dentro un programma in tedesco e' proprio
        # il difetto che questo passo esiste per togliere.
        lingua.applica(self, self.cfg.ui.lingua)

    # -- i pezzi fissi -------------------------------------------------------

    def _testata(self) -> QWidget:
        w = QWidget()
        w.setObjectName("gruppo")
        R = QHBoxLayout(w)
        R.setContentsMargins(0, 0, 0, 0)
        R.setSpacing(tema.S3)
        immagine = QLabel()
        pix = QPixmap(str(tema.logo(taglia=256)))
        if not pix.isNull():
            immagine.setPixmap(pix.scaled(tema.LATO_LOGO, tema.LATO_LOGO,
                                          Qt.KeepAspectRatio, Qt.SmoothTransformation))
        R.addWidget(immagine)
        colonna = QVBoxLayout()
        colonna.setSpacing(0)
        titolo = QLabel(TITOLO)
        titolo.setObjectName("nomeApp")
        colonna.addWidget(titolo)
        sotto = QLabel(SOTTOTITOLO)
        sotto.setObjectName("tenue")
        colonna.addWidget(sotto)
        R.addLayout(colonna, 1)
        # «passo 2 di 6» ha dentro dei numeri: si compone, quindi non passa dalla
        # passeggiata.
        self.l_conta = QLabel("")
        self.l_conta.setObjectName("tenue")
        self.l_conta.setProperty(lingua.MARCHIO, True)
        R.addWidget(self.l_conta, 0, Qt.AlignTop)
        return w

    def _piede(self) -> QWidget:
        w = QWidget()
        w.setObjectName("gruppo")
        R = QHBoxLayout(w)
        R.setContentsMargins(0, 0, 0, 0)
        R.setSpacing(tema.S2)
        # **Saltare e' sempre a portata di mano, e a sinistra.** Un tutorial da
        # cui non si esce e' una finestra modale che tiene in ostaggio il
        # programma appena installato.
        b_salta = QPushButton(SALTA)
        b_salta.clicked.connect(self._chiudi)
        R.addWidget(b_salta)
        R.addStretch(1)
        self.b_indietro = QPushButton(INDIETRO)
        self.b_indietro.clicked.connect(self._indietro)
        R.addWidget(self.b_indietro)
        # L'unico riempimento menta del dialogo: e' quello che si preme.
        self.b_avanti = QPushButton(AVANTI)
        self.b_avanti.setObjectName("primario")
        self.b_avanti.setDefault(True)
        self.b_avanti.clicked.connect(self._avanti)
        R.addWidget(self.b_avanti)
        return w

    # -- il passo di adesso --------------------------------------------------

    def _mostra(self) -> None:
        passo = PASSI[self._i]
        # Si veda `__init__`: da qui in poi i widget del banco sono quelli della
        # pagina che si sta per costruire, e quelli di prima non esistono piu'.
        self._b_bottone = self._b_stato = self._b_barra = None
        dentro = QWidget()
        dentro.setObjectName("gruppo")
        C = QVBoxLayout(dentro)
        C.setContentsMargins(0, 0, tema.S3, 0)
        C.setSpacing(tema.S2)

        alto = QHBoxLayout()
        alto.setSpacing(tema.S3)
        pillola = QLabel(str(self._i + 1))
        pillola.setObjectName("passo")
        alto.addWidget(pillola, 0, Qt.AlignTop)
        titolo = QLabel(passo.titolo)
        titolo.setObjectName("titoloPasso")
        titolo.setWordWrap(True)
        alto.addWidget(titolo, 1)
        C.addLayout(alto)

        for riga in passo.righe:
            eti = QLabel(riga)
            eti.setWordWrap(True)
            eti.setContentsMargins(tema.H_PILLOLA + tema.S3, 0, 0, 0)
            C.addWidget(eti)

        vivo = self._vivo(passo.vivo)
        if vivo is not None:
            vivo.setContentsMargins(tema.H_PILLOLA + tema.S3, tema.S2, 0, 0)
            C.addWidget(vivo)
        C.addStretch(1)

        self._scorre.setWidget(dentro)
        self.l_conta.setText(_T("passo {0} di {1}", self.cfg.ui.lingua,
                                self._i + 1, len(PASSI)))
        self.b_indietro.setEnabled(self._i > 0)
        # **Non `setText`.** La passeggiata dei cataloghi ricorda l'italiano di
        # ogni widget, quindi un `setText` normale qui non tiene: si veda
        # `ui.lingua.cambia`.
        lingua.cambia(self.b_avanti, FINE if self._i == len(PASSI) - 1 else AVANTI)
        # Il pezzo appena costruito non e' passato dalla passeggiata: senza questa
        # riga il passo 2 uscirebbe in italiano dentro un dialogo tradotto.
        lingua.applica(self, self.cfg.ui.lingua)

    def _vivo(self, quale: str):
        if quale == "lingua":
            return self._scelta_lingua()
        if quale == "audio":
            return self._verifiche([controllo_audio(self.cfg)], con_voicemeeter=True)
        if quale == "area":
            return self._verifiche([controllo_area(self.cfg)])
        if quale == "schede":
            return self._tabella_schede()
        if quale == "banco":
            return self._banco()
        return None

    # -- il banco ------------------------------------------------------------

    def _banco(self) -> QWidget:
        """Cosa c'e' su questo PC, il bottone che misura, e com'e' andata.

        Le tre righe in cima sono le stesse che stavano nell'ultimo passo
        (`controllo_macchina`): lettore, scheda video, motore della voce. Sono
        andate a stare qui perche' e' qui che diventano una **risposta** invece
        che una descrizione — la terza riga, dopo il bottone, dice il motore che
        il banco ha appena scelto.
        """
        from ui.qt_controlli import BarraCarico

        w = QWidget()
        w.setObjectName("gruppo")
        C = QVBoxLayout(w)
        C.setContentsMargins(0, 0, 0, 0)
        C.setSpacing(tema.S2)

        # 1. cosa c'e' qui, misurato e non dedotto
        adesso = self._verifiche(list(controllo_macchina(self.cfg)))
        if adesso is not None:
            C.addWidget(adesso)

        # 2. il bottone, la barra e la riga di stato
        in_corso = (self._banco_posa == "in corso"
                    or (self._lavoro is not None and self._lavoro.isRunning()))
        riga = QHBoxLayout()
        riga.setSpacing(tema.S3)
        self._b_bottone = QPushButton(ANNULLA if in_corso else MISURA)
        self._b_bottone.setCursor(Qt.PointingHandCursor)
        self._b_bottone.clicked.connect(self._banco_premuto)
        riga.addWidget(self._b_bottone)
        riga.addStretch(1)
        C.addLayout(riga)

        self._b_barra = BarraCarico()
        self._b_barra.veste(self._tavolozza())
        C.addWidget(self._b_barra)
        if in_corso:
            # Indeterminata, e non una percentuale: quanto duri lo scaricamento
            # di un modello lo decidono la rete e il disco, e una barra che
            # promette una fine che non sa dice una cosa falsa.
            self._b_barra.scorre()
        else:
            self._b_barra.ferma()

        # Prima di premere, la riga dice **quanto costa premere**. Sono fino a
        # mezzo gigabyte: un bottone che non dichiara cosa sta per scaricare e'
        # un download a sorpresa, e questo lo preme chi ha appena installato il
        # programma.
        if not in_corso and self._banco_esito is None:
            self._banco_riga = self._preventivo()

        # La riga di stato porta dentro nomi di pezzi e numeri gia' composti:
        # e' un modello riempito, quindi la passeggiata non la deve toccare.
        self._b_stato = QLabel(self._banco_riga)
        self._b_stato.setObjectName("tenue")
        self._b_stato.setProperty(lingua.MARCHIO, True)
        self._b_stato.setWordWrap(True)
        self._b_stato.setVisible(bool(self._banco_riga))
        C.addWidget(self._b_stato)

        # 3. com'e' andata, quando e' andata
        esito = self._verifiche(self._righe_esito())
        if esito is not None:
            C.addWidget(esito)
        return w

    def posa_banco(self, quale: str) -> None:
        """Mette il passo del banco in uno stato preciso, **per fotografarlo**.

        E' la stessa ragione di `BarraCarico.posa`: i due stati che contano di
        questo passo — mentre scarica, e quando qualcosa non e' arrivato — non
        si vedono ne' aprendo la guida ne' facendola scorrere, e in questo
        progetto un pezzo che nessuno ha guardato non e' «scritto», e'
        «supposto». Aspettare uno scaricamento vero per fotografarlo vorrebbe
        dire un'immagine diversa a ogni giro e nessuna quando serve.

        Lo stato «non e' arrivato» e' quello che vale di piu': e' l'unico in cui
        il riquadro passa in ambra, ed e' il caso per cui questo passo esiste.
        """
        from core import banco

        self._banco_posa = quale
        if quale == "in corso":
            self._banco_esito = None
            self._banco_riga = _T("{0} di {1}: {2}", self.cfg.ui.lingua, 2, 4,
                                  lingua.traduci(PEZZI_NOMI["kokoro"],
                                                 self.cfg.ui.lingua))
        elif quale == "finito":
            self._banco_esito = banco.Referto(
                scelta=banco.Scelta(
                    tts="piper", traduzione="locale",
                    motivi=(banco.Motivo("cuda_si"),
                            banco.Motivo("motore_mancante"),
                            banco.Motivo("traduzione_locale"))),
                sonda=banco.Sonda(cuda=True),
                falliti={"kokoro": "ConnectionError: rete non raggiungibile"},
                mb=117)
            self._banco_riga = ""
        else:
            self._banco_esito = None
            self._banco_riga = ""
        self._mostra()

    def _preventivo(self) -> str:
        """«da scaricare: 451 MB», oppure «c'e' gia' tutto».

        **Si guarda cosa c'e' dentro le cartelle, non che ci siano**: la
        risposta la danno gli stessi controlli che usano i backend
        (`core.banco.presenti`), e non un secondo elenco di file scritto qui.
        L'archivio delle voci di Kokoro si considerava «buono» perche' il file
        esisteva, e la prima voce inglese e' morta con un `KeyError` dentro la
        libreria, lontanissimo dal difetto.
        """
        from core import banco

        codice = self.cfg.ui.lingua
        if self._banco_da_prendere is None:
            try:
                sonda = banco.sonda_veloce(self.cfg)
                scelta = banco.scegli(sonda)
                self._banco_da_prendere = banco.peso_mb(banco.da_scaricare(
                    banco.serve(scelta, traduzione=self.cfg.translate.enabled),
                    sonda.presenti))
            except Exception:  # pragma: no cover - dipende dall'ambiente
                # Un preventivo che non si riesce a fare non deve impedire di
                # premere: il bottone sa gia' rifare questo conto da solo.
                self._banco_da_prendere = 0
        if not self._banco_da_prendere:
            return lingua.traduci(NIENTE_DA_FARE, codice)
        return _T("da scaricare: {0} MB", codice, self._banco_da_prendere)

    def _righe_esito(self) -> list[Esito]:
        """Le righe da mettere sotto il bottone: i perche' e i fallimenti.

        **I fallimenti non sono un dettaglio in fondo**: sono la ragione per cui
        questo passo esiste. Senza rete si scarica quello che si puo' e si
        continua — ma cio' che non e' arrivato deve stare scritto accanto alla
        scelta che ne dipende, se no il ripiego torna a essere muto e siamo al
        punto di prima.
        """
        esito = self._banco_esito
        if esito is None:
            return []
        codice = self.cfg.ui.lingua
        if isinstance(esito, Exception):
            return [Esito(False, _T("{0}: non riuscito — {1}", codice,
                                    lingua.traduci(MISURA, codice),
                                    f"{type(esito).__name__}: {esito}"))]

        # **Una rinuncia non porta la spunta.** Quali motivi lo siano lo dice
        # `core.banco.AVVISI` e non un elenco scritto qui: un secondo elenco
        # diverge al primo motivo nuovo, e diverge dalla parte sbagliata —
        # verso il verde.
        from core.banco import AVVISI

        righe = [Esito(m.codice not in AVVISI, motivo_in_riga(m, codice))
                 for m in esito.scelta.motivi]
        for pezzo, perche in esito.falliti.items():
            righe.append(Esito(False, _T(
                "{0}: non riuscito — {1}", codice,
                lingua.traduci(PEZZI_NOMI.get(pezzo, pezzo), codice), perche)))
        if esito.mb:
            righe.append(Esito(True, _T("pronto: {0} MB scaricati", codice, esito.mb)))
        elif not esito.falliti:
            righe.append(Esito(True, lingua.traduci(NIENTE_DA_FARE, codice)))
        return righe

    def _banco_premuto(self) -> None:
        """Il bottone fa due cose opposte, e lo dice: parte, oppure annulla."""
        if self._lavoro is not None and self._lavoro.isRunning():
            self._lavoro.annulla()
            return
        self._banco_esito = None
        self._banco_da_prendere = None
        self._lavoro = _Lavoro(self.cfg)
        self._lavoro.avanza.connect(self._banco_avanza)
        self._lavoro.finito.connect(self._banco_finito)
        self._lavoro.start()
        self._banco_riga = ""
        self._mostra()

    def _banco_avanza(self, pezzo: str, fatti: int, quanti: int) -> None:
        codice = self.cfg.ui.lingua
        nome = lingua.traduci(PEZZI_NOMI.get(pezzo, pezzo), codice)
        # Le due fasi di misura arrivano da questo stesso canale con `quanti = 0`:
        # «3 di 0» non vuol dire niente, quindi li' si scrive solo cosa si sta
        # facendo.
        self._banco_riga = (_T("{0} di {1}: {2}", codice, fatti + 1, quanti, nome)
                            if quanti else nome)
        self._aggiorna_riga()

    def _aggiorna_riga(self) -> None:
        """Scrive la riga di stato **se quel widget esiste ancora**.

        Un segnale arriva quando pare a lui, e nel frattempo l'utente puo' aver
        premuto «Passo precedente»: allora `_mostra()` ha ricostruito la pagina e
        il widget di prima Qt lo ha gia' distrutto. In Python l'oggetto e' ancora
        li' e chiamargli `setText` solleva — un dialogo che si chiude da solo
        mentre scarica, per un bottone premuto due schermate prima.
        """
        if self._b_stato is None:
            return
        try:
            self._b_stato.setText(self._banco_riga)
            self._b_stato.setVisible(bool(self._banco_riga))
        except RuntimeError:  # pragma: no cover - il widget non c'e' piu'
            self._b_stato = None

    def _banco_finito(self, esito) -> None:
        """Finito: si scrive in configurazione e si ridipinge il passo.

        **Solo se e' andata**: `banco.applica` scrive quello che ha verificato,
        non quello che ha scelto, e un guasto arriva qui come eccezione — in quel
        caso la configurazione resta quella di prima e la riga lo dice. Cambiare
        `tts.backend` dopo che lo scaricamento e' fallito vorrebbe dire una
        catena che parte con un motore che non c'e'.
        """
        from core import banco

        self._banco_esito = esito
        self._banco_riga = ""
        if not isinstance(esito, Exception):
            banco.applica(self.cfg, esito)
            if self.padre is not None:
                self.padre._riallinea()
        # La guida puo' essere gia' stata chiusa: il thread e' figlio
        # dell'applicazione apposta, quindi finisce comunque, e i modelli sul
        # disco restano presi. Ridipingere una finestra chiusa no.
        if self.isVisible() and PASSI[self._i].vivo == "banco":
            self._mostra()

    def _tavolozza(self):
        from PySide6.QtWidgets import QApplication

        return tema.attuale(QApplication.instance())

    def _scelta_lingua(self) -> QWidget:
        w = QWidget()
        # `#gruppo` e' il fondo trasparente del foglio di stile: un `QWidget`
        # nudo prende `fondo`, cioe' una fascia scura in mezzo alla pagina che
        # sembra un pannello e non e' niente.
        w.setObjectName("gruppo")
        C = QVBoxLayout(w)
        C.setContentsMargins(0, 0, 0, 0)
        C.setSpacing(tema.S2)
        riga = QHBoxLayout()
        riga.setSpacing(tema.S3)

        # L'elenco viene da `ui/qt_controlli.py`, che e' dove lo costruisce gia'
        # la scheda «Preparazione»: due elenchi delle stesse lingue sarebbero due
        # elenchi che si scollano, e questo progetto ne ha gia' contati sette.
        from ui.qt_controlli import _lingue_finestra, allarga_tendina

        valori, etichette = _lingue_finestra()
        self.c_lingua = QComboBox()
        # **Le voci non passano dal catalogo.** L'etichetta e' «codice — nome», e
        # dandola a un traduttore automatico `uk — Ucraino` e' gia' tornato
        # «Regno Unito — ucraino»: un codice di lingua trasformato in un paese.
        self.c_lingua.setProperty(lingua.MARCHIO, True)
        self.c_lingua.setMinimumWidth(320)
        self._codici = tuple(valori)
        for codice in self._codici:
            self.c_lingua.addItem(f"{codice} — {etichette.get(codice, codice)}")
        attuale = (self.cfg.ui.lingua or "auto").strip()
        if attuale in self._codici:
            self.c_lingua.setCurrentIndex(self._codici.index(attuale))
        self.c_lingua.currentIndexChanged.connect(self._lingua_scelta)
        # Quarantatre lingue: aperte tutte insieme sono alte 1093 px, cioe' piu'
        # di questo dialogo. Stessa regola delle altre tendine, un posto solo.
        allarga_tendina(self.c_lingua)
        riga.addWidget(self.c_lingua)
        riga.addStretch(1)
        C.addLayout(riga)
        # **Un riquadro senza righe dentro non e' un riquadro vuoto, e' un
        # difetto.** Con una lingua scelta a mano `controllo_lingua` non ha
        # niente da dire — `auto` non c'entra piu' — e la prima stesura
        # disegnava lo stesso la cornice: nella schermata in arabo si vedeva una
        # barra grigia con dentro il nulla. Vista guardando l'immagine, che e'
        # l'unico modo in cui si vedeva.
        verifica = self._verifiche([controllo_lingua(self.cfg)])
        if verifica is not None:
            C.addWidget(verifica)
        return w

    def _lingua_scelta(self, i: int) -> None:
        """La lingua si applica a caldo, qui e nella finestra dietro."""
        if not (0 <= i < len(self._codici)):
            return
        self.cfg.set("ui.lingua", self._codici[i])
        if self.padre is not None:
            # La finestra rilegge i pannelli e si riveste; il dialogo e' un suo
            # figlio, quindi la passeggiata lo prende insieme al resto.
            self.padre._riallinea()
            self.padre.vesti_lingua()
        self._mostra()

    def _tabella_schede(self) -> QWidget:
        w = QWidget()
        w.setObjectName("gruppo")
        C = QVBoxLayout(w)
        C.setContentsMargins(0, 0, 0, 0)
        C.setSpacing(tema.S2)
        for nome, riga in SCHEDE:
            eti = QLabel(nome)
            eti.setObjectName("titoloPasso")
            C.addWidget(eti)
            sotto = QLabel(riga)
            sotto.setObjectName("tenue")
            sotto.setWordWrap(True)
            C.addWidget(sotto)
        return w

    def _verifiche(self, esiti: list[Esito], *,
                   con_voicemeeter: bool = False) -> QWidget | None:
        """Il riquadro delle righe di verifica: menta se va, ambra se manca qualcosa.

        Il colore e' un **bordo**, non del testo: le sei tinte dei personaggi sono
        l'unico canale di colore del testo in questo programma, e usarne un
        settimo qui romperebbe la regola che tiene in piedi il log.
        """
        from PySide6.QtWidgets import QApplication

        righe = [e for e in esiti if e.testo]
        if not righe and not con_voicemeeter:
            return None
        tavolozza = tema.attuale(QApplication.instance())
        tutto_bene = all(e.ok for e in esiti)  # anche le righe mute contano
        bordo = tema.MENTA if tutto_bene else tavolozza.ambra
        w = QFrame()
        # **Il selettore e' per nome, e non per tipo.** Con `QFrame { … }` la
        # regola scendeva su ogni figlio, e `QLabel` **e'** un `QFrame`: nella
        # schermata ogni riga di verifica si portava dietro la sua sbarretta
        # menta da 3 px, tre marche invece di una. Nessun errore, e non lo si
        # poteva vedere se non guardando l'immagine.
        w.setObjectName("verifica")
        w.setStyleSheet(
            f"QFrame#verifica {{ background: {tavolozza.superficie_alta};"
            f" border-radius: {tema.R_TESSERA}px;"
            f" border-left: 3px solid {bordo}; }}")
        C = QVBoxLayout(w)
        C.setContentsMargins(tema.S3, tema.S2, tema.S3, tema.S2)
        C.setSpacing(tema.S1)
        for e in righe:
            eti = QLabel(("✓  " if e.ok else "⚠  ") + e.testo)
            # Dentro ci sono nomi di dispositivi e numeri: si veda `MODELLI`.
            eti.setProperty(lingua.MARCHIO, True)
            eti.setWordWrap(True)
            C.addWidget(eti)
        if con_voicemeeter:
            b = QPushButton(SCARICA)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(self._apri_voicemeeter)
            riga = QHBoxLayout()
            riga.addWidget(b)
            riga.addStretch(1)
            C.addLayout(riga)
        return w

    def _apri_voicemeeter(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(SCARICA_VOICEMEETER))

    # -- andare avanti, e uscirne --------------------------------------------

    def _avanti(self) -> None:
        if self._i >= len(PASSI) - 1:
            self._chiudi()
            return
        self._i += 1
        self._mostra()

    def _indietro(self) -> None:
        if self._i > 0:
            self._i -= 1
            self._mostra()

    def _chiudi(self) -> None:
        """Finito o saltato, e' la stessa cosa: si segna e non si riapre piu'.

        Distinguere «finito» da «saltato» vorrebbe dire riaprirlo a chi l'ha
        saltato — cioe' punire l'unica scelta che il tutorial gli lascia. Chi lo
        rivuole ha il bottone in testata.
        """
        preferenze.tutorial_visto()
        self.accept()

    def done(self, r: int) -> None:
        """Chiudendo si **chiede** al banco di fermarsi, e non lo si aspetta.

        Non lo si aspetta perche' un pezzo in corso puo' essere un modello da
        326 MB: bloccare la chiusura finche' non arriva vorrebbe dire una
        finestra che non si chiude, che e' peggio del problema. E lasciarlo
        finire e' innocuo — il suo unico effetto e' che i modelli finiscono sul
        disco, cioe' proprio quello per cui e' stato acceso, e la volta dopo li
        trova gia' li'.

        `annulla()` morde comunque **prima del pezzo successivo**, quindi chi
        chiude non si porta dietro mezzo gigabyte che non voleva.
        """
        if self._lavoro is not None and self._lavoro.isRunning():
            self._lavoro.annulla()
        super().done(r)


# ============================================ come si riapre, e chi lo apre ===

# Il glifo del bottone in testata, accanto a ⓘ. Un glifo e non «Guida» perche'
# `#aiuto` e' un cerchio da 28 px: e' l'unico bottone senza fondo della finestra,
# e ce ne sono gia' due — un terzo con dentro una parola romperebbe la fila.
GLIFO = "?"
# Il suggerimento invece e' una frase, e questa la trova la passeggiata normale:
# il bottone vive nella finestra, non in questo dialogo. Per la stessa ragione
# **non** sta in `testi()`, che dichiara solo cio' che nessuna passeggiata vede.
RIAPRI = "La guida iniziale: dalla lingua alla prima battuta"


def bottone(padre, quando_premuto) -> QPushButton:
    """Il bottone che riapre la guida, gia' vestito.

    Lo costruisce questo modulo e non `tools/ui_qt.py` perche' cosi' l'aggancio
    nella finestra e' una riga: il tutorial e' un pezzo che si aggiunge e si
    toglie intero, e un pezzo sparso in sei punti non si toglie piu'.
    """
    b = QPushButton(GLIFO, padre)
    b.setObjectName("aiuto")
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(RIAPRI)
    b.setAccessibleName(RIAPRI)
    b.clicked.connect(quando_premuto)
    return b
