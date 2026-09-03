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
# I due modelli che si riempiono a runtime: dentro ci finiscono numeri e nomi di
# pezzi, quindi il widget che li porta e' marcato `nontradurre` e si traduce il
# **modello**, non la frase composta.
MODELLI: tuple[str, ...] = (QUANTO,)


def testi() -> tuple[str, ...]:
    """Tutto quello che questo riquadro dice. Per `ui.lingua.fuori_dalla_passeggiata`."""
    return (TITOLO, INSTALLA, ANNULLA, NON_ADESSO, CHIUDI, FATTO, *MODELLI)


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

    def __init__(self, percorso: str, valore, codici: tuple[str, ...], cfg,
                 padre=None) -> None:
        super().__init__(padre)
        self.cfg = cfg
        self.percorso = percorso
        self.valore = valore
        self.codici = tuple(codici)
        self._lavoro: _Lavoro | None = None
        self.installato = False

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

        # **Cosa manca, per nome e non per codice.** I nomi sono quelli del passo
        # 6 (`ui.tutorial.PEZZI_NOMI`): scriverne una seconda serie qui vorrebbe
        # dire che la stessa cosa si chiama in due modi in due schermate, e che
        # la seconda serie non la traduce nessuno.
        self.che_cosa = QLabel(self._elenco())
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

        self._quanto()
        lingua.applica(self, cfg.ui.lingua)

    # -- cosa si sta per fare ------------------------------------------------

    def _elenco(self) -> str:
        """I pezzi che mancano, coi loro nomi tradotti, uno per riga."""
        from ui.tutorial import PEZZI_NOMI

        codice = self.cfg.ui.lingua
        righe = [f"«{self.percorso} = {self.valore}» ha bisogno di:"]
        righe += [f"  • {lingua.traduci(PEZZI_NOMI.get(c, c), codice)}"
                  for c in self.codici]
        return "\n".join(righe)

    def _quanto(self) -> None:
        from core import banco

        mb = banco.peso_mb(self.codici)
        if mb:
            self.stato.setText(
                lingua.traduci(QUANTO, self.cfg.ui.lingua).format(mb))

    # -- premere -------------------------------------------------------------

    def _premuto(self) -> None:
        """Il bottone fa tre cose in tre momenti: installa, annulla, chiude."""
        if self.installato:
            self.accept()
            return
        if self._lavoro is not None and self._lavoro.isRunning():
            self._lavoro.annulla()
            return
        self.b_installa.setText(ANNULLA)
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
            self.b_installa.setText(INSTALLA)
            return
        if esito:
            # `scarica` torna **quello che non ce l'ha fatta**: un pezzo che
            # fallisce non ferma gli altri e non sparisce.
            self._tinta("errore")
            self.stato.setText("; ".join(f"{c}: {p}" for c, p in esito.items())[:300])
            self.b_installa.setText(INSTALLA)
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
        self.stato.setText(lingua.traduci(FATTO, self.cfg.ui.lingua))
        self.b_installa.setText(CHIUDI)
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
            self.b_installa.setText(ANNULLA)
            self.b_dopo.setEnabled(False)
            self.barra.scorre()
            self._avanza(self.codici[0], 0, len(self.codici))
        elif quale == "rotto":
            self._finito({self.codici[0]: "ConnectionError: rete non raggiungibile"})
        else:
            self.barra.ferma()
            self.b_installa.setText(INSTALLA)
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
