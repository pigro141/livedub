"""«Questo va installato»: cosa manca, quanto pesa, e **un bottone che lo prende**.

## Perche' esiste

Meta' delle scelte di questo programma hanno qualcosa dietro che non c'e' ancora
sul disco. Kokoro sono 331 MB di modello piu' 1132 di librerie NVIDIA, il lettore
di Windows 115, la traduzione offline tre giga di pacchetti. Niente di tutto
questo si scarica al primo avvio, ed e' una scelta dichiarata: paga il peso chi
usa la funzione, non chiunque installi il programma.

Il difetto era il **seguito** di quella scelta. Il pannello marcava la voce con un
segno e diceva che andava installata, e li' finiva: chi la sceglieva restava con
un avviso in mano e nessun modo di soddisfarlo dentro il programma — il rimedio
stava altrove (il passo 6 della guida) o da nessuna parte. Un avviso che non si
puo' soddisfare e' gia' scritto in questo progetto come quello che si spegne da
solo nella testa di chi lo legge.

Quindi qui c'e' il pezzo che mancava e basta: **un riquadro che dice cosa manca,
quanto pesa, e lo installa**. E quando ha finito, il segno e la scritta se ne
vanno — perche' un avviso che resta dopo essere stato soddisfatto e' peggio di
quello che non si poteva soddisfare.

## Le tre cose che non si vedono leggendo in fretta

**Non c'e' niente di deciso qui dentro.** Cosa manchi lo dice
`core.banco.manca_per_scelta`, quanto pesi `core.banco.peso_mb`, e a prenderlo e'
`core.banco.scarica` — le stesse identiche funzioni del passo 6 della guida. Due
posti che scaricano la stessa cosa in due modi sono due posti che si contraddicono,
e in questo progetto l'hanno gia' fatto.

**Il lavoro sta in un thread e il thread e' figlio dell'applicazione.** Un modale
in questo progetto ha gia' tenuto la suite appesa dieci minuti senza stampare una
riga — non rossa: appesa — e un `QThread` figlio di un dialogo che si chiude
mentre gira viene distrutto sotto i piedi del lavoro. Cosi' invece finisce per
conto suo, e finire e' innocuo: l'unico effetto e' che i file sono sul disco.

**Le risposte tenute da parte, dopo, sono vecchie.** `core.bloccati` ricorda per
tutto il processo che «argos non si importa», e `core.onnx` che «la CUDA non
c'e'». Senza buttarle via, il programma continuerebbe a marcare come mancante una
cosa appena installata — cioe' proprio la meta' della richiesta che non ha a che
fare con l'installare.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ui import lingua, qt_tema as tema

# ============================================================== le parole =====
#
# Stanno qui come costanti e non scritte dentro i widget perche' `testi()` le
# dichiari a `ui.lingua`: un dialogo che non esiste finche' non lo si apre non lo
# trova nessuna passeggiata, e le sue parole resterebbero in italiano in mezzo a
# un programma tedesco — che e' peggio dell'italiano intero, perche' sembra una
# parola che non si traduce invece di una che nessuno ha tradotto.

TITOLO = "Questo va installato"
INSTALLA = "Installa"
ANNULLA = "Annulla"
NON_ADESSO = "Non adesso"
CHIUDI = "Chiudi"
FATTO = "Installato: adesso questa scelta funziona."
# **Perche' si dice quanto pesa prima e non dopo.** Un'attesa dichiarata e'
# un'attesa; un'attesa muta e' una finestra che sembra bloccata. Qui si arriva a
# un gigabyte e mezzo.
QUANTO = "Da scaricare: {0} MB"
# La riga che dice **per cosa**. Prima era composta a mano e non passava da
# nessun catalogo: nella finestra inglese dell'utente si leggeva
# «This must be installed» sopra «"tts.backend = piper" ha bisogno di:», cioe'
# una frase italiana in mezzo a una schermata tradotta. Il percorso e il valore
# stanno nel segnaposto, dove nessun traduttore li tocca.
SERVE_A = "Serve a «{0} = {1}»:"
# **Il caso che non e' un'installazione: qui non si puo' fare.** Dentro il
# pacchetto congelato non c'e' ne' un venv ne' `pip` (si veda
# `core.banco.NON_DI_QUI`), e il riquadro deve dirlo **prima** invece di offrire
# un bottone che solleva. Il perche' per esteso lo porta `NON_DI_QUI`, che e'
# tecnico e resta in italiano come il registro; questa e' la riga che si legge.
QUI_NO = "Questo non si puo' installare da qui."
# I modelli che si riempiono a runtime: dentro ci finiscono numeri, percorsi di
# config e nomi di pezzi, quindi il widget che li porta e' marcato `nontradurre`
# e si traduce il **modello**, non la frase composta.
MODELLI: tuple[str, ...] = (QUANTO, SERVE_A)


def testi() -> tuple[str, ...]:
    """Tutto quello che questo riquadro dice. Per `ui.lingua.fuori_dalla_passeggiata`."""
    return (TITOLO, INSTALLA, ANNULLA, NON_ADESSO, CHIUDI, FATTO, QUI_NO, *MODELLI)


# ============================================================== il lavoro =====


class _Lavoro(QThread):
    """Lo scaricamento, fuori dal thread della finestra.

    **Il padre e' l'applicazione e non il dialogo**, ed e' la riga che evita un
    crash: chiudendo il riquadro a scaricamento in corso, un `QThread` figlio del
    dialogo verrebbe distrutto mentre gira.
    """

    avanza = Signal(str, int, int)
    finito = Signal(object)

    def __init__(self, codici: tuple[str, ...], cfg) -> None:
        from PySide6.QtWidgets import QApplication

        super().__init__(QApplication.instance())
        self.codici = tuple(codici)
        self.cfg = cfg
        self._ferma = False

    def annulla(self) -> None:
        self._ferma = True

    def run(self) -> None:  # pragma: no cover - gira solo con un dito sopra
        from core import banco

        try:
            esito = banco.scarica(self.codici, self.cfg, dillo=self.avanza.emit,
                                  fermati=lambda: self._ferma)
        except Exception as guasto:
            # Un thread muore in silenzio di suo: senza questa riga il bottone
            # resterebbe «Annulla» per sempre, sopra un lavoro che non c'e' piu'.
            esito = guasto
        self.finito.emit(esito)


# ============================================================== il riquadro ===


class DialogoInstalla(QDialog):
    """Cosa manca, quanto pesa, e il bottone che lo prende.

    Si apre con `chiedi()`, che e' l'unica porta: costruire il dialogo per una
    scelta che non ha niente da installare sarebbe un riquadro vuoto, e uno che
    si apre mentre nessuno guarda (le schermate, la suite) sarebbe un modale che
    non torna piu'.
    """

    # **La larghezza sta scritta, e viene dalla regola.** Senza, il dialogo la
    # prendeva dal suo testo piu' lungo: l'elenco dei pezzi e' corto, quindi
    # usciva stretto — righe da tre parole sotto un titolo, e un messaggio di
    # guasto da trecento caratteri che sbordava. Meta' del contenuto della
    # finestra (`tema.MAX_CONTENUTO`) e' la stessa misura con cui si impagina il
    # resto del programma, non un numero d'occhio.
    LARGO = tema.MAX_CONTENUTO // 2 + tema.S7

    def __init__(self, percorso: str, valore, codici: tuple[str, ...], cfg,
                 padre=None, congelato: bool | None = None) -> None:
        super().__init__(padre)
        from core import banco

        self.cfg = cfg
        self.percorso = percorso
        self.valore = valore
        self.codici = tuple(codici)
        self._lavoro: _Lavoro | None = None
        self.installato = False
        # **Quello che da qui non si puo' prendere, saputo prima di disegnare.**
        # La regola sta in `core.banco.non_di_qui`, fuori da Qt, e il booleano
        # arriva da fuori cosi' il caso dell'eseguibile si puo' fotografare e
        # verificare da sorgente.
        if congelato is None:
            congelato = banco.congelato()
        self.non_di_qui = banco.non_di_qui(self.codici, congelato)

        self.setWindowTitle(TITOLO)
        self.setModal(True)
        if padre is None:
            from PySide6.QtWidgets import QApplication

            self.setStyleSheet(tema.foglio(tema.attuale(QApplication.instance())))

        L = QVBoxLayout(self)
        L.setContentsMargins(tema.S5, tema.S5, tema.S5, tema.S5)
        L.setSpacing(tema.S3)

        titolo = QLabel(TITOLO)
        titolo.setObjectName("titoloPasso")
        L.addWidget(titolo)

        # La riga che dice per **quale scelta**: modello tradotto, valori dentro
        # il segnaposto. Marcata `nontradurre` perche' e' composta a runtime.
        self.a_cosa = QLabel("")
        self.a_cosa.setObjectName("tenue")
        self.a_cosa.setWordWrap(True)
        self.a_cosa.setProperty(lingua.MARCHIO, True)
        L.addWidget(self.a_cosa)

        # **Cosa manca, per nome e non per codice.** I nomi sono quelli del passo
        # 6 (`ui.tutorial.PEZZI_NOMI`): scriverne una seconda serie qui vorrebbe
        # dire che la stessa cosa si chiama in due modi in due schermate, e che
        # la seconda serie non la traduce nessuno.
        self.che_cosa = QLabel("")
        self.che_cosa.setWordWrap(True)
        self.che_cosa.setProperty(lingua.MARCHIO, True)
        L.addWidget(self.che_cosa)

        self.stato = QLabel("")
        self.stato.setObjectName("tenue")
        self.stato.setWordWrap(True)
        self.stato.setProperty(lingua.MARCHIO, True)
        L.addWidget(self.stato)

        from ui.qt_controlli import BarraCarico

        self.barra = BarraCarico()
        from PySide6.QtWidgets import QApplication

        self.barra.veste(tema.attuale(QApplication.instance()))
        self.barra.ferma()
        L.addWidget(self.barra)

        # Il respiro fra il testo e i bottoni sta **qui** e non fra il titolo e
        # l'elenco: le righe che si leggono insieme stanno vicine, e il vuoto va
        # dove finisce il discorso. Prima era il contrario, e si vedeva.
        L.addStretch(1)

        riga = QHBoxLayout()
        riga.setSpacing(tema.S3)
        riga.addStretch(1)
        self.b_dopo = QPushButton(NON_ADESSO)
        self.b_dopo.setCursor(Qt.PointingHandCursor)
        self.b_dopo.clicked.connect(self.reject)
        riga.addWidget(self.b_dopo)
        self.b_installa = QPushButton(INSTALLA)
        self.b_installa.setObjectName("primario")
        self.b_installa.setCursor(Qt.PointingHandCursor)
        self.b_installa.clicked.connect(self._premuto)
        riga.addWidget(self.b_installa)
        L.addLayout(riga)

        self.setMinimumWidth(self.LARGO)
        self._riempi()
        lingua.applica(self, cfg.ui.lingua)

    # -- le parole, che passano tutte dalla stessa porta ---------------------

    def _T(self, testo: str, *valori) -> str:
        """Una frase di questo riquadro, nella lingua della finestra.

        **Ogni `setText` di qui dentro passa da questa riga**, ed e' la cura di
        un difetto fotografato: `_finito` e `_premuto` riscrivevano il bottone
        con la costante italiana (`setText(INSTALLA)`), quindi dopo un tentativo
        d'installazione il riquadro inglese mostrava «Non adesso» accanto a
        «Installa». La passeggiata di `ui.lingua` traduce quello che trova
        **quando passa**: chi riscrive dopo deve tradurre da se'.
        """
        fuori = lingua.traduci(testo, self.cfg.ui.lingua)
        return fuori.format(*valori) if valori else fuori

    def _bottone(self, b, testo: str) -> None:
        """Scrive su un bottone tradotto, **e ricorda l'originale italiano**.

        `lingua.cambia` e non `setText`: senza la memoria, la passeggiata
        successiva prenderebbe la traduzione come originale e al secondo cambio
        di lingua tradurrebbe una traduzione.
        """
        lingua.cambia(b, testo)
        b.setText(self._T(testo))

    # -- cosa si sta per fare ------------------------------------------------

    def _elenco(self) -> str:
        """I pezzi che mancano, coi loro nomi tradotti, uno per riga."""
        from ui.tutorial import PEZZI_NOMI

        codice = self.cfg.ui.lingua
        return "\n".join(f"  • {lingua.traduci(PEZZI_NOMI.get(c, c), codice)}"
                         for c in self.codici)

    def _riempi(self) -> None:
        """Le tre righe di partenza, e il bottone che ne consegue.

        **Il caso «da qui no» non e' un guasto ed e' l'unico senza bottone.**
        Offrire «Installa» dentro il pacchetto congelato voleva dire una porta
        chiusa dipinta come aperta: si premeva, e usciva un `RuntimeError` che
        diceva la cosa giusta nel momento sbagliato.
        """
        from core import banco

        self.a_cosa.setText(self._T(SERVE_A, self.percorso, self.valore))
        self.che_cosa.setText(self._elenco())
        if self.non_di_qui:
            self._tinta("errore")
            # Le frasi di `NON_DI_QUI` nascono come messaggi di eccezione,
            # quindi cominciano in minuscolo: qui vengono dopo un punto, e una
            # minuscola dopo un punto si legge come una riga tagliata a meta'.
            motivi = "; ".join(banco.NON_DI_QUI[c][:1].upper()
                               + banco.NON_DI_QUI[c][1:] for c in self.non_di_qui)
            self.stato.setText(f"{self._T(QUI_NO)} {motivi}")
            self.b_installa.setVisible(False)
            self._bottone(self.b_dopo, CHIUDI)
            return
        self._quanto()

    def _quanto(self) -> None:
        from core import banco

        mb = banco.peso_mb(self.codici)
        if mb:
            self.stato.setText(self._T(QUANTO, mb))

    # -- premere -------------------------------------------------------------

    def _premuto(self) -> None:
        """Il bottone fa tre cose in tre momenti: installa, annulla, chiude."""
        if self.installato:
            self.accept()
            return
        if self._lavoro is not None and self._lavoro.isRunning():
            self._lavoro.annulla()
            return
        self._bottone(self.b_installa, ANNULLA)
        self.b_dopo.setEnabled(False)
        self.barra.scorre()
        self._lavoro = _Lavoro(self.codici, self.cfg)
        self._lavoro.avanza.connect(self._avanza)
        self._lavoro.finito.connect(self._finito)
        self._lavoro.start()

    def _avanza(self, pezzo: str, fatti: int, quanti: int) -> None:
        from ui.tutorial import PEZZI_NOMI

        codice = self.cfg.ui.lingua
        nome = lingua.traduci(PEZZI_NOMI.get(pezzo, pezzo), codice)
        self.stato.setText(f"{fatti + 1}/{quanti} — {nome}" if quanti else nome)

    def _tinta(self, nome: str) -> None:
        """Cambia il ruolo della riga di stato e la fa ridipingere.

        Qt non riapplica il foglio di stile cambiando `objectName`: senza
        `unpolish/polish` la riga resterebbe tenue mentre dice che qualcosa non
        e' arrivato — cioe' il difetto peggiore, un guasto con l'aria di una nota
        a margine.
        """
        self.stato.setObjectName(nome)
        st = self.stato.style()
        st.unpolish(self.stato)
        st.polish(self.stato)

    def _finito(self, esito) -> None:
        """Finito bene o male, e la differenza si vede senza leggere.

        **Le risposte tenute da parte vanno buttate qui e non altrove.**
        `core.bloccati` ricorda per tutto il processo che un pacchetto non si
        importava, e `core.onnx` che la CUDA non c'era: senza queste due righe la
        cosa appena installata resterebbe marcata come mancante fino alla
        prossima apertura del programma — cioe' la meta' della richiesta che non
        riguarda l'installare.
        """
        self.barra.ferma()
        self.b_dopo.setEnabled(True)
        if isinstance(esito, Exception):
            self._tinta("errore")
            self.stato.setText(f"{type(esito).__name__}: {esito}".splitlines()[0][:300])
            self._bottone(self.b_installa, INSTALLA)
            return
        if esito:
            # `scarica` torna **quello che non ce l'ha fatta**: un pezzo che
            # fallisce non ferma gli altri e non sparisce.
            self._tinta("errore")
            self.stato.setText("; ".join(f"{c}: {p}" for c, p in esito.items())[:300])
            self._bottone(self.b_installa, INSTALLA)
            return

        # `banco.scarica` ha gia' buttato la sua cache — sta in fondo a lei
        # apposta, cosi' nessun chiamante se lo deve ricordare. Qui restano le
        # due che non sono sue: quale pacchetto si importa, e se la sessione
        # ONNX prende la CUDA.
        from core import bloccati, onnx

        bloccati.dimentica()
        onnx.dimentica()
        self.installato = True
        self._tinta("tenue")
        self.stato.setText(self._T(FATTO))
        self._bottone(self.b_installa, CHIUDI)
        self.b_dopo.setVisible(False)


    # -- per fotografarlo --------------------------------------------------

    def posa(self, quale: str) -> None:
        """Mette il riquadro in uno stato preciso, **per guardarlo**.

        Stessa ragione di `Tutorial.posa_banco` e di `BarraCarico.posa`: i due
        stati che contano di questo riquadro — mentre scarica, e quando non ce
        l'ha fatta — non si vedono aprendolo, e in questo progetto un pezzo che
        nessuno ha guardato non e' «scritto», e' «supposto». Aspettare uno
        scaricamento vero per fotografarlo vorrebbe dire un'immagine diversa a
        ogni giro e nessuna quando serve.

        **Il guasto e' un guasto vero e non una stringa inventata.** In questo
        progetto un `-9988` scritto a mano ha gia' descritto un caso impossibile
        e mandato una diagnosi fuori strada per mezza giornata: qui si usa
        quello che `banco.scarica` restituisce davvero — un pezzo per volta, con
        il nome dell'eccezione davanti.
        """
        if quale == "in corso":
            self._bottone(self.b_installa, ANNULLA)
            self.b_dopo.setEnabled(False)
            self.barra.scorre()
            self._avanza(self.codici[0], 0, len(self.codici))
        elif quale == "rotto":
            self._finito({self.codici[0]: "ConnectionError: rete non raggiungibile"})
        else:
            self.barra.ferma()
            self._bottone(self.b_installa, INSTALLA)
            self.b_dopo.setEnabled(True)
            self._tinta("tenue")
            self._quanto()


# ============================================================== la porta ======


def chiedi(percorso: str, valore, cfg, padre=None) -> bool:
    """Se a questa scelta manca qualcosa, offre di installarlo. Torna se e' andata.

    **Non si apre se non c'e' nessuno a guardare**, e la condizione e'
    `isVisible` e non un attributo dichiarato: in questo progetto la guardia
    scritta come «costruita e dichiarata fuori schermo» non copriva «costruita e
    mai mostrata», che e' esattamente quello che fa la suite — e il modale l'ha
    tenuta appesa dieci minuti senza stampare una riga.

    Torna `False` anche quando non c'era niente da fare: chi chiama usa questo
    valore per **ridisegnare i segni**, e ridisegnarli quando non e' cambiato
    niente sarebbe lavoro per nulla.
    """
    from core import banco

    if padre is None or not padre.isVisible():
        return False
    # **Prima si guarda la tabella, poi il disco.** Questa funzione la chiama il
    # pannello a **ogni** campo che cambia, e i campi che hanno qualcosa dietro
    # sono cinque su centosessantasei: chiedere `presenti()` per gli altri
    # centosessantuno vorrebbe dire pagare **due secondi** — misurati: 2022 ms la
    # prima volta, 1 ms le successive — per rispondere «niente da fare» a chi ha
    # spostato un cursore. `RICHIESTE` e' un dizionario, quindi la domanda giusta
    # costa un accesso.
    if percorso not in banco.RICHIESTE:
        return False
    try:
        codici = banco.manca_per_scelta(percorso, valore,
                                        banco.presenti_in_cache(cfg))
    except Exception:  # pragma: no cover - guardare il disco non deve fermare la finestra
        return False
    if not codici:
        return False
    d = DialogoInstalla(percorso, valore, codici, cfg, padre)
    d.exec()
    return d.installato


def chiedi_tutto(cfg, padre=None, gia_chiesto: set | None = None) -> bool:
    """Le scelte **gia' scritte** in configurazione a cui manca qualcosa.

    **Il difetto che questa funzione chiude.** `chiedi` la chiamava solo
    `Pannello.applica`, cioe' solo quando un campo *cambia*: un valore che sta
    li' dall'inizio non faceva comparire il riquadro mai. Il caso e' il piu'
    comune di tutti — `tts.backend = piper` e' il default, e con il suo modello
    non sul disco la sessione parte e ripiega in silenzio, che e' esattamente il
    difetto per cui `core/banco.py` esiste.

    **Il momento giusto e' l'Avvia, e non l'apertura.** All'apertura sarebbe un
    modale che compare da solo prima che qualcuno abbia toccato niente — e la
    prima volta ci pensa gia' il passo 6 della guida, che scarica. L'Avvia
    invece e' un gesto, ed e' l'istante esatto in cui quella scelta smette di
    essere una riga di configurazione e diventa una catena che parte: chiedere
    li' vuol dire chiedere quando la risposta serve.

    `gia_chiesto` tiene le coppie gia' proposte in questa sessione: un pezzo che
    da qui non si puo' prendere (l'eseguibile congelato) non deve ripresentarsi
    a ogni Avvia — un avviso che torna sempre e' quello che si spegne da solo
    nella testa di chi lo legge.
    """
    from core import banco

    if padre is None or not padre.isVisible():
        return False
    try:
        avuti = banco.presenti_in_cache(cfg)
        manca = banco.manca_per_config(cfg, avuti)
    except Exception:  # pragma: no cover - guardare il disco non ferma l'Avvia
        return False
    cambiato = False
    for percorso, valore, codici in manca:
        if gia_chiesto is not None and (percorso, valore) in gia_chiesto:
            continue
        if gia_chiesto is not None:
            gia_chiesto.add((percorso, valore))
        d = DialogoInstalla(percorso, valore, codici, cfg, padre)
        d.exec()
        cambiato = cambiato or d.installato
    return cambiato
