"""La finestra di livedub, in Qt, vestita **Menta**.

    .\\.venv\\Scripts\\python.exe -m tools.ui_qt --profile gtav

Il disegno sta in `docs/interfaccia.md` e i numeri in `ui/qt_tema.py`: qui non se
ne inventa nessuno. Chi aggiunge un pezzo cerca li' la distanza, il raggio e il
corpo; se il numero non c'e', lo **ricava con la regola** (`R(h)`, la scala
`S0..S7`) e lo aggiunge alla tabella. I 3, 6, 8, 9, 10, 12, 14, 16, 18, 22, 24
sparsi che questo file aveva erano nati uno per uno guardando il pezzo e non la
finestra: nessuno sbagliato da solo, insieme un'interfaccia senza scala.

**La colonna, dall'alto in basso**, con le altezze fisse dichiarate nel tema:

    testata 56  ·  barra dei comandi 52  ·  striscia 40 (compare e sparisce)
    linguette 40  ·  il contenuto, che si allunga  ·  barra della misura 28

**La prima cosa che si vede e' cosa fare**, non il log: al centro della scheda
Sessione, finche' la catena non e' partita, sta il pannello dei tre passi.
Quella riga esisteva gia' — era scritta nel log come testo, terza riga dopo la
scheda tecnica, e spariva sotto la prima decina di messaggi. Era l'interfaccia
vera della prima volta, in mezzo a un registro diagnostico.

**Come sono arrivati qui i due cicli.** Non copiandoli. Vivevano dentro
`tools/ui.py`, intrecciati con Tkinter; sono stati estratti in `core/motore.py`,
che non sa cosa sia una finestra e parla in un verso solo — `manda(tipo, dato)`
su una coda. Lo stesso vale per l'overlay: `ui.overlay.OverlayBase` decide cosa
disegnare e dove, `ui/overlay.py` e `ui/overlay_qt.py` mettono i pixel a schermo
e basta.

**E le regole non stanno qui.** Di che colore va la pillola (`colore_stato`), che
marca va nel margine di una riga di log (`gravita`) e quali numeri sono fuori
norma in fondo alla finestra (`barra_misura`) vivono in `core/motore.py`, perche'
sono regole e non disegno — e si verificano in una suite che gira senza aprire
niente. Quattro dei cinque difetti trovati rileggendo le cure a freddo stavano
nella finestra o al suo confine, che era l'unica parte del programma senza
**nessuna** verifica.
"""

from __future__ import annotations

import argparse
import html
import queue
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import (  # noqa: E402
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
)
from PySide6.QtGui import QGuiApplication, QIcon, QKeySequence, QPixmap, QShortcut  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QDialog,
    QScrollArea,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QFileDialog,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import preferenze, registro  # noqa: E402
from core.config import PROFILES_DIR, Config  # noqa: E402
from core.motore import (  # noqa: E402
    STATO_GUASTO,
    Motore,
    Opzioni,
    barra_misura,
    colore_stato,
    fase_catena,
    gravita,
    in_coda,
    righe_guasto_audio,
)
from core.versione import NOME, VERSIONE, scheda  # noqa: E402
from ui import lingua  # noqa: E402
from ui import qt_tema as tema  # noqa: E402
from ui import tutorial  # noqa: E402  # >>> tutorial (ui/tutorial.py)
from ui.qt_audio import Audio  # noqa: E402
from ui.qt_controlli import BarraCarico, Elidibile, Rettangolo, Velo  # noqa: E402
from ui.qt_pannello import Pannello  # noqa: E402

# **Le schede, come elenchi di percorsi.** Ognuna risponde a una domanda sola, e
# contiene quello che serve a rispondere a quella — non quello che sta nella
# stessa sezione di `core/config.py`. Sono elenchi e non valori: le *scelte*
# vengono dallo schema, quindi aggiungere un backend non richiede di toccare
# questo file.
#
# Cio' che resta fuori non e' nascosto: sta nell'albero intero dell'ultima
# scheda, che mostra tutto e dice quanti campi sta mostrando su quanti.

# Come suona: chi parla, con che voce, quanto forte, quanto di fretta.
VOCE = (
    # `label.regex` sta accanto a `label.form` perche' e' la sua via d'uscita: le
    # forme in elenco sono quelle viste, non tutte quelle possibili, e un gioco
    # che ne usa un'altra non deve essere un gioco non supportato.
    "label.enabled", "label.form", "label.regex", "label.names", "label.require_names",
    # La tabella dei personaggi: e' la funzione per cui uno accende i nomi.
    "label.voices", "label.colors",
    "speaker.backend", "speaker.decide_after_ms", "speaker.max_speakers",
    "speaker.similarity", "speaker.gender_fallback",
    "tts.backend", "tts.device", "tts.pool_size", "tts.speed", "tts.native_rate_max",
    "timing.rate_max", "timing.accepted_delay_ms",
    "mix.duck_db", "mix.dub_gain_db", "mix.duck_hold_ms",
)

# Cosa c'e' scritto: tradurre, e come si disegna il tradotto sopra il gioco.
TRADUZIONE = (
    "translate.enabled", "translate.backend", "translate.source", "translate.target",
    "translate.preserve_register", "translate.context_lines",
    "translate.overlay", "translate.background_mode", "translate.color",
    "translate.font", "translate.font_frac", "translate.outline",
    "translate.blur_strength", "translate.background_opacity",
)

# Cosa legge: sta dentro la scheda della preparazione, sotto l'area.
#
# **`ui.lingua` sta qui e non nella scheda Traduzione**, ed e' una distinzione
# che costa una sessione a chi la sbaglia: quella scheda decide in che lingua il
# programma *parla*, questo campo decide in che lingua il programma *scrive sui
# bottoni*. Messi vicini si confondono — si mette `en` credendo di aver acceso
# la traduzione, e la catena continua a doppiare in italiano. Nella
# preparazione invece e' la prima cosa che si sceglie, ed e' l'unica che si
# possa scegliere prima di saper leggere il resto della finestra.
LETTURA = (
    "ui.lingua",
    "vision.ocr_backend", "vision.ocr_device", "vision.exclude_colored",
    "vision.sat_max", "vision.max_ocr_hz", "capture.fps",
    # Erano nella scheda «Aree», che non c'e' piu': sono i tre parametri
    # dell'area che si legge, e adesso l'area e' una sola.
    "capture.solo_roi", "capture.roi_margin", "vision.line_pad",
)



def campi_di(cfg) -> list[str]:
    """I percorsi di tutti i campi, per copiare una config dentro un'altra."""
    from core.schema import campi

    return [c.percorso for c in campi(cfg) if c.modificabile]


class ComeTk:
    """La tavolozza Menta vestita da modulo del tema Tk.

    Serve a `colore_stato`, che e' **una regola sola** per due finestre: la
    riscrittura era di tre righe, e tre righe riscritte sono due regole al primo
    ritocco. Questo adattatore ne costa tre e non si tocca mai.

    `VERDE` diventa **l'accento**, e non e' un ripiego: in Menta c'e' un colore
    acceso solo, e vuol dire *interazione e vita* — il bottone che si preme, la
    spia quando la catena gira. Il verde «sta funzionando» e il blu «questo si
    preme» erano due colori per una cosa sola.
    """

    def __init__(self, tavolozza) -> None:
        self.ROSSO = tavolozza.rosso
        self.VERDE = tavolozza.accento
        self.TESTO_FIOCO = tavolozza.testo_fioco


# ============================================================ i due selettori ==


class SelettoreArea(QWidget):
    """Una finestra a tutto schermo su cui si tira il rettangolo dell'area.

    **Semitrasparente e non opaca**, perche' l'area va scelta *guardando i
    sottotitoli*: su un pannello nero si tirerebbe un rettangolo a memoria, che
    e' esattamente il modo in cui la ROI di default ha finito per inquadrare il
    tappeto.

    Le coordinate escono **normalizzate** sullo schermo, quindi non dipendono
    ne' dalla risoluzione ne' dal fattore di scala di Windows: e' la stessa forma
    che il profilo salva su disco.

    **E l'avviso sull'altezza arriva mentre si tira, non dopo.** Prima era una
    riga di log che compariva quando il rettangolo era gia' stato lasciato: la
    fascia d'analisi e' l'area piu' un respiro proporzionale a lei, e un
    rettangolo alto un sesto dello schermo diventa 391 px per una riga da 45.
    Nessun filtro disfa una saldatura fra il testo e cio' che ha attorno;
    stringere l'area si'.
    """

    # Sopra questa frazione l'etichetta passa in ambra e lo dice a parole.
    TROPPO_ALTA = 0.12

    def __init__(self, al_termine, tavolozza) -> None:
        super().__init__()
        self.al_termine = al_termine
        self.t = tavolozza
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)
        g = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(g)
        self.w, self.h = max(1, g.width()), max(1, g.height())
        self.p0 = self.p1 = QPoint(0, 0)
        self.tirando = False

    # -- disegno ------------------------------------------------------------

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # Il velo lascia vedere il gioco; dentro il rettangolo si toglie del
        # tutto, se no si sceglie il bordo di una cosa che non si distingue.
        p.fillRect(self.rect(), QColor(0, 0, 0, 140))  # 0,55 di opacita'
        if not (self.tirando or not self._vuoto()):
            return
        r = self._rett()
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.fillRect(r, Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        # **Il colore e' quello della tavolozza, non un verde scritto a mano.**
        # Il `#39d353` che stava qui funzionava, si vedeva, e nel tema chiaro non
        # l'aveva mai guardato nessuno: e' l'esempio di come comincia un colore
        # fuori dal sistema.
        p.setPen(QPen(QColor(tema.MENTA), 2))
        p.drawRect(r)
        self._squadrette(p, r)
        self._etichetta(p, r)

    def _squadrette(self, p: QPainter, r: QRect) -> None:
        """I quattro angoli marcati: dicono dove **finisce** il rettangolo.

        Un tratto da 2 px su una scena chiara si perde; gli angoli no, e sono
        anche i punti che l'occhio usa per giudicare se l'area e' stretta.
        """
        L = 12
        p.setPen(QPen(QColor(tema.MENTA), 3))
        for x, verso_x in ((r.left(), 1), (r.right(), -1)):
            for y, verso_y in ((r.top(), 1), (r.bottom(), -1)):
                p.drawLine(x, y, x + L * verso_x, y)
                p.drawLine(x, y, x, y + L * verso_y)

    def _etichetta(self, p: QPainter, r: QRect) -> None:
        """Le quattro frazioni sotto il cursore, in monospazio."""
        x, y, w, h = (r.x() / self.w, r.y() / self.h,
                      r.width() / self.w, r.height() / self.h)
        alta = h > self.TROPPO_ALTA
        testo = f"x{x:.3f}  y{y:.3f}  w{w:.3f}  h{h:.3f}"
        if alta:
            testo += "   troppo alta"
        p.setFont(QFont(tema.MONO, tema.C_NOTA + 1))
        misura = p.fontMetrics()
        largo = misura.horizontalAdvance(testo) + 2 * tema.S3
        alto = misura.height() + tema.S2
        # Sotto il rettangolo, e sopra se sotto non ci sta: l'etichetta non deve
        # uscire dallo schermo proprio mentre si tira il bordo basso.
        ex = min(max(r.left(), 0), self.w - largo)
        ey = r.bottom() + tema.S2
        if ey + alto > self.h:
            ey = max(0, r.top() - tema.S2 - alto)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.t.superficie))
        p.drawRoundedRect(ex, ey, largo, alto, tema.R_CAMPO, tema.R_CAMPO)
        p.setPen(QColor(self.t.ambra if alta else self.t.testo))
        p.drawText(QRect(ex, ey, largo, alto), Qt.AlignCenter, testo)

    # -- interazione --------------------------------------------------------

    def _rett(self) -> QRect:
        return QRect(self.p0, self.p1).normalized()

    def _vuoto(self) -> bool:
        r = self._rett()
        return r.width() < 20 or r.height() < 8

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.close()  # Esc chiude senza toccare niente

    def mousePressEvent(self, e) -> None:
        self.p0 = self.p1 = e.position().toPoint()
        self.tirando = True
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self.tirando:
            self.p1 = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        self.p1 = e.position().toPoint()
        self.tirando = False
        r = self._rett()
        vuoto = self._vuoto()
        self.close()
        if vuoto:
            return  # un clic per sbaglio non deve azzerare la ROI
        self.al_termine((r.x() / self.w, r.y() / self.h,
                         r.width() / self.w, r.height() / self.h))


class SelettoreFinestra(QDialog):
    """L'elenco delle finestre aperte, per scegliere **cosa** catturare.

    E' la scelta che viene prima di tutte le altre. Catturando lo schermo intero,
    nel fotogramma che va all'OCR finisce anche cio' che sta davanti al gioco —
    comprese le nostre finestre — e il programma finisce per leggere se stesso.
    Scegliendo la finestra, la cattura contiene quella e basta: verificato
    mettendo sopra a quella catturata una finestra rossa che la copriva a meta',
    nel fotogramma ne e' arrivato lo **0,000**.

    L'elenco e' ordinato per area perche' il gioco e' quasi sempre la finestra
    piu' grande: la risposta giusta e' in cima nove volte su dieci.
    """

    def __init__(self, padre, al_termine) -> None:
        super().__init__(padre)
        self.al_termine = al_termine
        self.setWindowTitle("Scegli la finestra da doppiare")
        self.resize(820, 460)
        L = QVBoxLayout(self)
        L.setContentsMargins(tema.S5, tema.S5, tema.S5, tema.S5)
        L.setSpacing(tema.S3)
        nota = QLabel("Il gioco e' quasi sempre il primo della lista. Deve stare in "
                      "finestra o senza bordi, non a schermo intero esclusivo.")
        nota.setObjectName("tenue")
        nota.setWordWrap(True)
        L.addWidget(nota)
        self.lista = QListWidget()
        self.lista.itemDoubleClicked.connect(lambda _i: self.scegli())
        L.addWidget(self.lista, 1)
        piede = QHBoxLayout()
        piede.setSpacing(tema.S2)
        b = QPushButton("Aggiorna")
        b.clicked.connect(self.aggiorna)
        piede.addWidget(b)
        piede.addStretch(1)
        b = QPushButton("Tutto lo schermo")
        b.clicked.connect(self.schermo)
        piede.addWidget(b)
        b = QPushButton("Usa questa")
        b.setObjectName("primario")
        b.setDefault(True)
        b.clicked.connect(self.scegli)
        piede.addWidget(b)
        L.addLayout(piede)
        self.finestre = []
        self.aggiorna()

    def aggiorna(self) -> None:
        from capture.finestre import elenco

        self.finestre = elenco()
        self.lista.clear()
        for f in self.finestre:
            self.lista.addItem(
                f"  {f.larghezza:>5}x{f.altezza:<5} {f.processo:<22} {f.titolo}")
        if self.finestre:
            self.lista.setCurrentRow(0)

    def schermo(self) -> None:
        self.accept()
        self.al_termine(None)

    def scegli(self) -> None:
        riga = self.lista.currentRow()
        if riga < 0 or riga >= len(self.finestre):
            return
        f = self.finestre[riga]
        self.accept()
        self.al_termine(f)


class DialogoCrash(QDialog):
    """L'unica finestra modale del programma, e resta l'unica.

    Un'eccezione dentro un callback di Qt stampa su una console che
    nell'eseguibile non esiste, e la finestra resta li' come se niente fosse —
    **peggio di un crash, perche' si continua a usarla credendo che funzioni**.

    Dice il tipo, il messaggio, il percorso del registro, e ha un bottone che
    copia tutto negli appunti: chiedere «che versione hai e cosa e' successo» a
    chi segnala un difetto non funziona mai, o non lo sa o lo copia male.
    """

    def __init__(self, padre, tipo: str, messaggio: str, dettaglio: str) -> None:
        super().__init__(padre)
        self.setWindowTitle("Guasto")
        self.resize(720, 440)
        self._tutto = f"{tipo}: {messaggio}\n\n{dettaglio}"
        L = QVBoxLayout(self)
        L.setContentsMargins(tema.S5, tema.S5, tema.S5, tema.S5)
        L.setSpacing(tema.S3)
        titolo = QLabel(f"{tipo}: {messaggio}")
        titolo.setObjectName("tesseraTitolo")
        titolo.setWordWrap(True)
        L.addWidget(titolo)
        corpo = QTextEdit()
        corpo.setReadOnly(True)
        corpo.setPlainText(dettaglio)
        L.addWidget(corpo, 1)
        piede = QHBoxLayout()
        piede.setSpacing(tema.S2)
        b = QPushButton("Copia tutto")
        b.clicked.connect(lambda: QApplication.clipboard().setText(self._tutto))
        piede.addWidget(b)
        piede.addStretch(1)
        b = QPushButton("Chiudi")
        b.setObjectName("primario")
        b.clicked.connect(self.accept)
        piede.addWidget(b)
        L.addLayout(piede)


# ================================================================ i pezzetti ==


class BarraMisura(QWidget):
    """I numeri della sessione, in fondo, sempre presenti.

    Esiste perche' questo progetto misura tutto e poi **non lo guarda finche' non
    finisce la sessione**. Le stesse quantita' stanno gia' nel rapporto scritto
    in `runs/`: metterle sotto gli occhi durante la partita e' la differenza fra
    accorgersi che l'OCR e' sceso a 12 Hz e scoprirlo mezz'ora dopo.

    Sono gli unici numeri della finestra che cambiano da soli, e per questo si
    aggiornano a **2 Hz** e non a trenta: qualunque cosa si muova in periferia si
    prende un'attenzione che appartiene al gioco.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("misura")
        # **Un foglio di stile non dipinge il fondo di una sottoclasse di
        # QWidget** finche' non glielo si chiede: senza questo attributo la
        # regola c'e', non da' errore, e a schermo non si vede niente — che e'
        # esattamente il tipo di difetto che questo progetto trova solo
        # guardando l'immagine.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(tema.H_MISURA)
        self.riga = QHBoxLayout(self)
        self.riga.setContentsMargins(tema.S5, 0, tema.S5, 0)
        self.riga.setSpacing(tema.S2)
        # **La spia sta qui**, non piu' in testata: e' l'unico posto della
        # finestra che porta un alone, e vuol dire «sta parlando adesso». In un
        # angolo in alto sarebbe una cosa che pulsa in periferia mentre si gioca;
        # in fondo, accanto ai numeri che gia' cambiano, e' dove si guarda.
        self.spia = QLabel()
        self.spia.setAccessibleName("la catena sta girando")
        self.riga.addWidget(self.spia)
        self.testo = QLabel("")
        self.testo.setTextFormat(Qt.RichText)
        self.testo.setAccessibleName("le misure della sessione")
        # **Si accorcia invece di farsi tagliare.** A finestra stretta l'ultima
        # cifra della ROI restava mezza fuori: un numero tagliato si legge
        # comunque, e si legge **sbagliato**.
        self.testo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.testo.setMinimumWidth(0)
        self.riga.addWidget(self.testo, 1)
        self._tavolozza = tema.SCURA

    def veste(self, tavolozza) -> None:
        """Il colore lo tiene lei, perche' e' scritto **dentro** l'HTML.

        Un colore congelato in una stringa smette di funzionare al cambio di
        tema senza dare errore: `ambra` e' `#f5b544` sullo scuro e `#a16207` sul
        chiaro, e la riga resterebbe quella di prima finche' non cambia un
        numero.
        """
        self._tavolozza = tavolozza

    def spegni_o_accendi(self, colore: str, con_alone: bool) -> None:
        """La spia: il colore dello stato, e l'alone solo mentre esce audio."""
        self.spia.setStyleSheet(tema.spia(colore))
        tema.alone(self.spia, colore if con_alone else None)

    def mostra(self, misure) -> None:
        """Una riga sola in HTML: il nome in `C_NOTA` tenue, il valore in `C_TESTO`.

        **Il valore era due corpi piu' grande del nome, e in monospazio**: la
        riga sembrava un terminale incollato in fondo a una finestra. Un numero
        qui non ha nessuna colonna con cui allinearsi — il monospazio serve nel
        log, dove ora, sigla, voce e latenza *sono* colonne — e un salto da 9 a
        13 punti fra l'etichetta e il suo numero non e' una gerarchia, e'
        un'incoerenza. Uno scalino solo: 9 tenue per il nome, 10 pieno per il
        valore.

        Un'etichetta per valore era piu' pulita da guardare nel codice e piu'
        cara da ridipingere: a 2 Hz per tutta la partita, e con il colore che
        cambia da un giro all'altro, cambiare `objectName` a widget vivi vuol
        dire un `unpolish/polish` per ognuno.
        """
        t = self._tavolozza
        tinte = {"avviso": t.ambra, "guasto": t.rosso}
        pezzi = []
        for m in misure:
            colore = tinte.get(m.stato, t.testo)
            nome = (f'<span style="color:{t.testo_tenue};font-size:{tema.C_NOTA}pt">'
                    f'{html.escape(m.nome)}</span> ' if m.nome else "")
            pezzi.append(f'{nome}<span style="color:{colore};font-size:{tema.C_TESTO}pt">'
                         f'{html.escape(m.testo)}</span>')
        punto = (f'<span style="color:{t.testo_fioco};font-size:{tema.C_NOTA}pt">'
                 f' &nbsp;·&nbsp; </span>')
        self.testo.setText(punto.join(pezzi))


class TesseraGuasto(QFrame):
    """Un guasto non e' una riga: e' una tessera, e **dentro ci sta il bottone**.

    Viene da un difetto vero: la prima versione del guasto audio scriveva
    «Ricollega e premi Avvia» e lasciava `Avvia` **spento**, la sessione aperta,
    il WAV mai scritto e lo stato verde. Il messaggio indicava un bottone che non
    si poteva premere.

    Metterci dentro il bottone e' la conclusione naturale — se il testo sa cosa
    fare, lo puo' fare — e ha un effetto secondario che vale da solo: **non si
    puo' scrivere la tessera senza decidere quale sia l'azione di ricupero**,
    quindi il caso in cui non c'e' azione salta fuori mentre si scrive l'errore
    invece che davanti all'utente.
    """

    def __init__(self, apri_registro, riprova) -> None:
        super().__init__()
        self.setObjectName("tessera")
        # **Un foglio di stile non dipinge il fondo di una sottoclasse di
        # QWidget** finche' non glielo si chiede: senza questo attributo la
        # regola c'e', non da' errore, e a schermo non si vede niente — che e'
        # esattamente il tipo di difetto che questo progetto trova solo
        # guardando l'immagine.
        self.setAttribute(Qt.WA_StyledBackground, True)
        L = QVBoxLayout(self)
        L.setContentsMargins(tema.S4, tema.S3, tema.S4, tema.S3)
        L.setSpacing(tema.S2)
        alto = QHBoxLayout()
        self.titolo = QLabel("")
        self.titolo.setObjectName("tesseraTitolo")
        self.titolo.setWordWrap(True)
        alto.addWidget(self.titolo, 1)
        self.ora = QLabel("")
        self.ora.setObjectName("tesseraMono")
        alto.addWidget(self.ora)
        L.addLayout(alto)
        self.dettaglio = QLabel("")
        self.dettaglio.setObjectName("tesseraMono")
        self.dettaglio.setWordWrap(True)
        L.addWidget(self.dettaglio)
        self.consiglio = QLabel("")
        self.consiglio.setWordWrap(True)
        L.addWidget(self.consiglio)
        piede = QHBoxLayout()
        piede.setSpacing(tema.S2)
        piede.addStretch(1)
        b = QPushButton("Apri il registro")
        b.clicked.connect(apri_registro)
        piede.addWidget(b)
        self.b_riprova = QPushButton("RIPROVA")
        self.b_riprova.setObjectName("primario")
        self.b_riprova.clicked.connect(riprova)
        piede.addWidget(self.b_riprova)
        L.addLayout(piede)
        self.setVisible(False)

    def mostra(self, titolo: str, dettaglio: str, consiglio: str) -> None:
        self.titolo.setText(titolo)
        self.ora.setText(time.strftime("%H:%M:%S"))
        self.dettaglio.setText(dettaglio)
        self.consiglio.setText(consiglio)
        self.setVisible(True)


class PannelloPassi(QWidget):
    """I tre passi: **la prima cosa che deve arrivare all'occhio**.

    Non il log. Oggi quella riga esisteva gia' — «Scegli finestra -> Seleziona
    area -> Avvia», terza riga dopo la scheda tecnica — e spariva sotto la prima
    decina di messaggi: era l'interfaccia vera della prima volta in mezzo a un
    registro diagnostico, mentre tutto il resto (166 parametri) sta li' per dopo.

    Numerati e in ordine, perche' l'ordine non e' estetico: senza aver scelto la
    finestra non si puo' tirare l'area (il rettangolo sarebbe in coordinate dello
    schermo invece che del gioco). Ogni passo fatto diventa una **spunta menta**
    e il successivo si accende.
    """

    PASSI = (
        "Scegli la finestra del gioco",
        "Tira l'area sui sottotitoli",
        "Avvia",
    )

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pannello")
        # **Un foglio di stile non dipinge il fondo di una sottoclasse di
        # QWidget** finche' non glielo si chiede: senza questo attributo la
        # regola c'e', non da' errore, e a schermo non si vede niente — che e'
        # esattamente il tipo di difetto che questo progetto trova solo
        # guardando l'immagine.
        self.setAttribute(Qt.WA_StyledBackground, True)
        L = QVBoxLayout(self)
        L.setContentsMargins(tema.S7, tema.S6, tema.S7, tema.S6)
        L.setSpacing(tema.S4)

        immagine = QLabel()
        immagine.setAlignment(Qt.AlignCenter)
        immagine.setAccessibleName("il logo di livedub")
        pix = QPixmap(str(tema.logo(taglia=256)))
        if not pix.isNull():
            immagine.setPixmap(pix.scaled(96, 96, Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))
        L.addWidget(immagine)
        L.addSpacing(tema.S4)

        self._numeri: list[QLabel] = []
        self._titoli: list[QLabel] = []
        for i, titolo in enumerate(self.PASSI, start=1):
            riga = QHBoxLayout()
            riga.setSpacing(tema.S3)
            n = QLabel(str(i))
            n.setObjectName("passo")
            riga.addWidget(n)
            t = QLabel(titolo)
            t.setObjectName("titoloPasso")
            riga.addWidget(t, 1)
            L.addLayout(riga)
            self._numeri.append(n)
            self._titoli.append(t)

        L.addSpacing(tema.S4)
        nota = QLabel("Il gioco deve stare in finestra o senza bordi, "
                      "non a schermo intero esclusivo.")
        nota.setObjectName("tenue")
        nota.setWordWrap(True)
        L.addWidget(nota)
        self.setMaximumWidth(tema.MAX_CONTENUTO)

    def aggiorna(self, fatti: list[bool]) -> None:
        """Spunta i passi fatti e accende il primo che manca."""
        primo_da_fare = next((i for i, f in enumerate(fatti) if not f), len(fatti))
        for i, (n, t) in enumerate(zip(self._numeri, self._titoli)):
            if fatti[i]:
                n.setText("✓")
                n.setObjectName("passo")
                t.setObjectName("titoloPassoSpento")
            else:
                n.setText(str(i + 1))
                n.setObjectName("passo" if i == primo_da_fare else "passoSpento")
                t.setObjectName("titoloPasso" if i == primo_da_fare
                                else "titoloPassoSpento")
            for w in (n, t):
                w.style().unpolish(w)
                w.style().polish(w)


class TesseraOra(QFrame):
    """**La battuta che sta uscendo adesso**, che e' l'unica cosa che si guarda.

    La scheda Sessione era un log e basta. Un log risponde benissimo a «cosa e'
    successo» e malissimo a «cosa sta succedendo»: mentre si gioca non si legge
    una lista che scorre, si getta un'occhiata — e un'occhiata prende un colore,
    una parola e una riga, non venti righe in colonna.

    Quindi qui ci sono quattro cose e non una in piu':

    | cosa | a che domanda risponde |
    |---|---|
    | la spia e la **fase** | sta ancora funzionando? (`core.motore.fase_catena`) |
    | la **sigla** nel colore del personaggio | e' sempre lo stesso a parlare? |
    | latenza e fretta dell'**ultima** battuta | sta arrivando in tempo, e schiacciata? |
    | il testo letto | e sta dicendo quello che c'e' scritto? |

    **Non ripete la barra in fondo.** Quella dice i percentili di tutta la
    sessione — quanto — e si aggiorna a 2 Hz; questa dice l'ultima battuta e la
    parola di adesso. Sono due domande, e la lezione gia' pagata («lo stato era
    detto in tre posti») riguarda la stessa parola scritta due volte, non due
    granularita' diverse.

    **E la sigla e' un colore di testo**, mai un riempimento: le sei tinte delle
    voci sono dei personaggi, menta ambra e rosso sono degli stati, e le due
    famiglie non usano mai lo stesso canale. Il colore arriva qui dentro come
    HTML, esattamente come nel log, e per questo non compare nel foglio di stile.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ora")
        # Un foglio di stile non dipinge il fondo di una sottoclasse finche' non
        # glielo si chiede: senza, la regola c'e' e a schermo non si vede niente.
        self.setAttribute(Qt.WA_StyledBackground, True)
        L = QVBoxLayout(self)
        L.setContentsMargins(tema.S4, tema.S3, tema.S4, tema.S3)
        L.setSpacing(tema.S1)

        alto = QHBoxLayout()
        alto.setSpacing(tema.S2)
        self.spia = QLabel()
        self.spia.setAccessibleName("la catena sta girando")
        alto.addWidget(self.spia)
        self.fase = QLabel("")
        self.fase.setObjectName("fase")
        # La parola la sceglie `fase_catena` e la traduce chi disegna: e' composta
        # a runtime, quindi la passeggiata dei cataloghi non la deve toccare.
        self.fase.setProperty(lingua.MARCHIO, True)
        alto.addWidget(self.fase)
        alto.addStretch(1)
        self.chi = QLabel("")
        self.chi.setObjectName("conta")
        self.chi.setTextFormat(Qt.RichText)
        self.chi.setProperty(lingua.MARCHIO, True)
        self.chi.setAccessibleName("chi parla, con che voce e con quanta fretta")
        alto.addWidget(self.chi)
        L.addLayout(alto)

        # **Si accorcia con i puntini invece di andare a capo.** Una battuta
        # lunga farebbe crescere la tessera, e una tessera che cambia altezza a
        # ogni riga e' esattamente la cosa che si muove in periferia mentre si
        # gioca. Il testo intero resta nel suggerimento.
        self.testo = Elidibile("")
        self.testo.setObjectName("oraTesto")
        self.testo.setProperty(lingua.MARCHIO, True)
        L.addWidget(self.testo)

        self.barra = BarraCarico()
        L.addWidget(self.barra)
        self.barra.setVisible(False)
        self._tavolozza = tema.SCURA
        self._vuota = True

    @property
    def vuota(self) -> bool:
        """Ha gia' detto qualcosa? Chi rimette i segnaposto lo deve chiedere.

        Senza, il cambio di lingua a sessione accesa cancellerebbe la battuta a
        schermo per rimetterci «in attesa della prima battuta» — un segnaposto
        che sostituisce l'informazione che stava aspettando.
        """
        return self._vuota

    def veste(self, tavolozza) -> None:
        """I colori li tiene lei: stanno **dentro** l'HTML, e un colore congelato
        in una stringa smette di funzionare al cambio di tema senza dare errore.
        """
        self._tavolozza = tavolozza
        self.barra.veste(tavolozza)

    def svuota(self, quando_dirlo: str) -> None:
        """Finche' non ha parlato nessuno: una riga fioca, non una tessera vuota."""
        self._vuota = True
        self.chi.setText("")
        self.testo.setObjectName("oraVuoto")
        self.testo.setToolTip("")
        self.testo.setText(quando_dirlo)
        for w in (self.testo,):
            w.style().unpolish(w)
            w.style().polish(w)

    def dillo(self, sigla: str, voce: str, testo: str, colore: str,
              latenza: float, fretta: float) -> None:
        """Una battuta appena uscita. `colore` e' la tinta di quel personaggio."""
        if self._vuota:
            self._vuota = False
            self.testo.setObjectName("oraTesto")
            self.testo.style().unpolish(self.testo)
            self.testo.style().polish(self.testo)
        t = self._tavolozza
        pezzi = [f'<span style="color:{colore};font-weight:600">{html.escape(sigla)}</span>',
                 html.escape(voce), f"{latenza:.0f} ms"]
        # La fretta si scrive solo quando ce n'e' stata: `1.00×` su ogni riga e'
        # una colonna che non dice mai niente, e le colonne che non dicono mai
        # niente si smette di guardarle — comprese le volte in cui parlano.
        if fretta > 1.005:
            pezzi.append(f"{fretta:.2f}×")
        punto = (f'<span style="color:{t.testo_fioco}"> · </span>')
        self.chi.setText(punto.join(pezzi))
        self.testo.setToolTip(testo)
        self.testo.setText(testo)

    def mostra_fase(self, fase, colore: str, alone: bool) -> None:
        """La parola di `fase_catena` piu' la spia, che e' l'unica cosa colorata."""
        tinte = {"avviso": self._tavolozza.ambra, "guasto": self._tavolozza.rosso}
        self.fase.setText(fase.testo)
        self.fase.setStyleSheet(f"color: {tinte.get(fase.stato, self._tavolozza.testo)}")
        self.spia.setStyleSheet(tema.spia(colore))
        tema.alone(self.spia, colore if alone else None)

    # -- l'attesa dell'avvio, che e' l'unica cosa lunga di questa finestra --

    def aspetta(self) -> None:
        """Da Avvia alla prima riga di stato viva: caricare Kokoro costa secondi.

        Indeterminata e non a riempimento: quanto ci mette dipende dal motore e
        dal disco, e una barra che arriva in fondo mentre non e' finito niente
        dice una cosa falsa.
        """
        self.barra.scorre(tema.durata(1100))

    def pronto(self) -> None:
        self.barra.ferma()


class FilaPersonaggi(QWidget):
    """**I personaggi sentiti**, con quante battute ciascuno.

    E' la risposta grafica alla domanda che il README dichiara essere quella
    vera: non «cosa ha detto» ma «e' sempre lo stesso a parlare?». Nel log quella
    risposta c'e' gia' — sei colori a rotazione — ma va **letta**, riga per riga,
    e mentre si gioca non si legge niente. Qui sta tutta in una riga: tre
    tessere vuol dire tre personaggi, e se la quarta compare a meta' scena vuol
    dire che il riconoscimento ne ha inventato uno.

    **Il colore sta nella sigla e non nella tessera**, che e' la regola dei
    canali: le sei tinte sono colore del testo, e menta ambra e rosso sono
    riempimenti, marche e contorni. Una tessera riempita col colore del
    personaggio sembrerebbe un'ottima idea e comincerebbe a smontare il sistema
    dal giorno dopo — per gradi, senza dare errore.

    Le tessere si aggiungono in **ordine di comparsa** e non per numero di
    battute: ordinarle per conteggio le farebbe scambiare di posto da sole
    durante una conversazione, cioe' qualcosa che si muove mentre si gioca.
    """

    # Sopra questo numero si scrive «+n», perche' una fila di sedici tessere non
    # e' piu' un colpo d'occhio: e' un altro elenco. Sedici identita' su una
    # scena di battibecchi corti sono misurate, non ipotetiche.
    MAX_TESSERE = 10

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("gruppo")
        self.riga = QHBoxLayout(self)
        self.riga.setContentsMargins(0, 0, 0, 0)
        self.riga.setSpacing(tema.S2)
        self.vuoto = QLabel("")
        self.vuoto.setObjectName("spento")
        self.vuoto.setProperty(lingua.MARCHIO, True)
        self.riga.addWidget(self.vuoto)
        self.riga.addStretch(1)
        # `sid -> (tessera, quante, sigla)`. La sigla si tiene per nome e non si
        # ricerca fra i figli: una verifica che cerca «la prima QLabel dentro la
        # tessera» prova l'ordine in cui sono state aggiunte, non la regola.
        self._tessere: dict[str, tuple[QWidget, QLabel, QLabel]] = {}
        self._tavolozza = tema.SCURA

    def veste(self, tavolozza) -> None:
        self._tavolozza = tavolozza

    def svuota(self, quando_dirlo: str) -> None:
        self.vuoto.setText(quando_dirlo)

    def aggiorna(self, conteggi: dict[str, int], colore) -> None:
        """`conteggi` in ordine di comparsa; `colore(sid)` da' la tinta."""
        self.vuoto.setVisible(not conteggi)
        for i, (sid, quante) in enumerate(conteggi.items()):
            if i >= self.MAX_TESSERE:
                break
            if sid not in self._tessere:
                self._tessere[sid] = self._nuova(sid, colore(sid))
            self._tessere[sid][1].setText(str(quante))
        avanzano = len(conteggi) - self.MAX_TESSERE
        self.vuoto.setVisible(avanzano > 0 or not conteggi)
        if avanzano > 0:
            self.vuoto.setText(f"+{avanzano}")

    def _nuova(self, sid: str, colore: str) -> tuple[QWidget, QLabel, QLabel]:
        """Una tessera nuova **compare sfumando**: un personaggio in piu' e' un
        avvenimento, e una cosa che appare di colpo in periferia si legge come
        un guasto.
        """
        t = QFrame()
        t.setObjectName("personaggio")
        t.setAttribute(Qt.WA_StyledBackground, True)
        L = QHBoxLayout(t)
        L.setContentsMargins(tema.S2, tema.S1, tema.S2, tema.S1)
        # `S2` e non `S1`: con quattro pixel `M1 2` si legge «M12», che e' un
        # numero. Il conteggio dev'essere staccato dalla sigla.
        L.setSpacing(tema.S2)
        nome = QLabel(sid)
        nome.setProperty(lingua.MARCHIO, True)
        # Il colore del personaggio, e solo come **colore del testo**.
        nome.setStyleSheet(f"color: {colore}; font-weight: 600")
        L.addWidget(nome)
        quante = QLabel("1")
        quante.setObjectName("conta")
        quante.setProperty(lingua.MARCHIO, True)
        L.addWidget(quante)
        self.riga.insertWidget(self.riga.count() - 2, t)
        ms = tema.durata(tema.MS_CONTROLLO)
        if ms:
            velo = QGraphicsOpacityEffect(t)
            t.setGraphicsEffect(velo)
            comparsa = QPropertyAnimation(velo, b"opacity", t)
            comparsa.setDuration(ms)
            comparsa.setStartValue(0.0)
            comparsa.setEndValue(1.0)
            comparsa.setEasingCurve(QEasingCurve.OutCubic)
            # **L'effetto si toglie quando ha finito, e non e' pulizia.** Un velo
            # che parte da zero lascia la tessera **invisibile** finche' qualcuno
            # non fa girare il ciclo degli eventi: fotografata subito dopo, la
            # fila dei personaggi usciva vuota — con la suite verde, perche' i
            # widget c'erano tutti. Un pezzo la cui visibilita' dipende da
            # un'animazione e' un pezzo che sparisce ovunque quell'animazione non
            # giri, e togliere l'effetto e' il modo di dichiarare che lo stato
            # finale e' «si vede».
            comparsa.finished.connect(lambda w=t: w.setGraphicsEffect(None))
            comparsa.start()
            t._comparsa = comparsa  # se no il garbage collector se la porta via
        return t, quante, nome


# ================================================================ la finestra ==


class Finestra(QMainWindow):
    # **Ogni quanto la finestra guarda la coda, in millisecondi.** Questo passo
    # e' un **ritardo aggiunto**: un ritaglio che arriva subito dopo il giro
    # aspetta un giro intero prima di essere disegnato. Misurato il costo del
    # ridisegno sul percorso vero: **10,5 ms** nel caso peggiore. A 16 ms ci sta
    # con un terzo di margine.
    PASSO_UI = 16

    # I nomi delle schede, in ordine. Servono a raggiungerne una per nome invece
    # che per numero: `setCurrentIndex(3)` scritto a mano si scolla alla prima
    # scheda aggiunta in mezzo, **in silenzio**, e porta l'utente altrove.
    PREPARAZIONE, SESSIONE, VOCE_, TRADUZIONE_, TUTTE = range(5)

    def __init__(self, cfg, args) -> None:
        super().__init__()
        self.cfg = cfg
        self.args = args
        self._in_attesa: list[str] = []
        self._voci: dict[str, int] = {}
        # Quante battute a testa, **in ordine di comparsa**: e' quello che la
        # fila dei personaggi disegna, e l'ordine di un dizionario in Python e'
        # l'ordine di inserimento — quindi non c'e' niente da ordinare.
        self._conta: dict[str, int] = {}
        self._detta_qualcosa = False
        # **Un passo e' fatto quando lo hai fatto tu.** Prima il secondo si
        # spuntava da solo perche' il profilo porta gia' una ROI: la finestra si
        # apriva dicendo «l'area l'hai tirata» a chi non aveva toccato niente, e
        # il primo passo — quello vero da fare — restava sotto una spunta verde.
        # Un indicatore che dice «fatto» per una cosa non fatta non e' un
        # dettaglio: e' l'unica cosa che quel pannello deve dire.
        self._area_scelta = False
        self.coda: queue.Queue = queue.Queue()
        self.motore = Motore(cfg, Opzioni.da_args(args), in_coda(self.coda))

        self.setWindowTitle(f"{NOME} {VERSIONE}")
        ico = tema.icona()
        if ico is not None:
            # Non c'era **nessun** `QIcon` nel progetto: la finestra prendeva
            # l'icona generica di Python, nella barra delle applicazioni e nel
            # commutatore. Un `.ico` multi-risoluzione e non un PNG grande,
            # perche' Windows non ridimensiona bene un PNG a 16 px.
            self.setWindowIcon(QIcon(str(ico)))

        self._geometria()
        # **Il tema lo decide Windows, e cambia mentre la finestra e' aperta.**
        # Qt avvisa (`colorSchemeChanged`), quindi non si legge il registro e non
        # si riavvia: si riapplica il foglio di stile. Chi tiene Windows in
        # chiaro si vedeva arrivare un rettangolo nero in mezzo allo schermo.
        app = QApplication.instance()
        self.tavolozza = tema.attuale(app)
        self.setStyleSheet(tema.foglio(self.tavolozza))
        try:
            app.styleHints().colorSchemeChanged.connect(self._tema_cambiato)
        except Exception:  # Qt piu' vecchio: si resta sul tema scelto all'avvio
            pass

        centro = QWidget()
        self.setCentralWidget(centro)
        L = QVBoxLayout(centro)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(0)

        L.addWidget(self._testata())
        L.addWidget(self._barra())
        L.addWidget(self._striscia())

        # **Le schede rispondono a domande, non a sezioni di config.** Erano
        # «Sessione, Tecnologie, Aree, Impostazioni avanzate»: tre nomi su
        # quattro descrivono come e' fatto il programma dentro, non cosa vuole
        # fare chi lo apre. Chi apre questa finestra vuole, in ordine:
        # **prepararlo**, **sentirlo andare**, **cambiare come suona**,
        # **cambiare cosa c'e' scritto**, **dire dove guardare**. L'ultima resta
        # l'albero intero, per chi tara — ed e' l'unica che parla di campi.
        self.schede = QTabWidget()
        # `documentMode` disegna una linea di base sotto le linguette che il
        # foglio di stile non tocca: restava un filo chiaro a destra dell'ultima
        # scheda, cioe' un bordo che non appartiene a niente.
        self.schede.setDocumentMode(False)
        L.addWidget(self.schede, 1)

        self.schede.addTab(self._scheda_avvio(), "Preparazione")
        self.schede.addTab(self._scheda_sessione(), "Sessione")
        self.p_voce = Pannello(
            cfg, al_cambio=self._campo_cambiato, solo=VOCE, cerca=False,
            intestazione="Come suona il doppiaggio: chi parla, con che voce, quanto forte "
                         "e quanto di fretta. Il volume e la fretta si sentono subito; il "
                         "motore e il numero di voci al prossimo avvio.",
        )
        self.schede.addTab(self._in_margine(self.p_voce), "Voce")
        self.p_traduzione = Pannello(
            cfg, al_cambio=self._campo_cambiato, solo=TRADUZIONE, cerca=False,
            intestazione="Solo per giocare in una lingua diversa da quella dei sottotitoli. "
                         "Spenta, il programma legge e doppia nella lingua che trova — che "
                         "e' il caso normale.",
        )
        self.schede.addTab(self._scheda_traduzione(), "Traduzione")
        self.p_avanzate = Pannello(
            cfg, al_cambio=self._campo_cambiato, su_disegna=self.scegli_area)
        self.schede.addTab(self._in_margine(self.p_avanzate), "Tutte le impostazioni")

        self.misura = BarraMisura()
        self.misura.veste(self.tavolozza)
        self.misura.spegni_o_accendi(self._colore_stato, False)
        L.addWidget(self.misura)

        # **Il velo sta fuori dai layout**, ed e' l'unica cosa della finestra che
        # lo fa: e' un figlio del centro che si dimensiona a mano in
        # `resizeEvent`. Dentro un layout imporrebbe una taglia minima a tutto
        # quello che copre, cioe' cambierebbe il minimo della finestra — che e'
        # una cosa che non si vede guardando, e che una verifica misura.
        self.velo = Velo(centro)
        self.velo.veste(self.tavolozza)
        self.ora.veste(self.tavolozza)
        self.personaggi.veste(self.tavolozza)

        self._scorciatoie()
        self.schede.setCurrentIndex(
            min(int(self._pref.get("scheda", 0)), self.schede.count() - 1))
        # **La lingua si veste alla fine, quando i widget ci sono tutti.** Non
        # e' una scelta di comodo: il catalogo si applica percorrendo l'albero
        # (`ui/lingua.py`), quindi un widget costruito dopo resterebbe in
        # italiano — e resterebbe in italiano **in silenzio**, che e' la forma
        # di difetto che questa finestra ha gia' pagato quattro volte.
        self.vesti_lingua()
        registro.apri()
        self.aggiorna_pronto()
        self.scrivi(scheda())
        self.scrivi("")

        # >>> tutorial (ui/tutorial.py): la prima volta si apre da solo, e dopo
        # che la finestra esiste — se no il dialogo comparirebbe sul nulla.
        QTimer.singleShot(0, self._forse_tutorial)
        # <<< tutorial

        # **La coda si guarda con un timer, non dentro i cicli.** I due domini
        # restano nei loro thread; qui arriva solo il testo gia' pronto. Mettere
        # l'interfaccia dentro il ciclo video sarebbe il modo piu' rapido di far
        # perdere battute a una catena che finora non ne perde.
        self.orologio = QTimer(self)
        self.orologio.timeout.connect(self._svuota_coda)
        self.orologio.start(self.PASSO_UI)
        # I numeri della barra in fondo: **due volte al secondo e non trenta**.
        self.orologio_misura = QTimer(self)
        self.orologio_misura.timeout.connect(self._aggiorna_misura)
        self.orologio_misura.start(int(1000 / tema.HZ_MISURA))
        self._aggiorna_misura()

    # -- produzione: ricordare, salvare, non morire in silenzio -------------

    def _geometria(self) -> None:
        """Taglia e posizione: l'ultima usata, **se sta ancora in uno schermo**.

        Ripartire sempre al centro a una misura fissa e' un fastidio su un
        monitor grande e un guasto su uno da 1366x768, dove la finestra nasceva
        piu' alta dello spazio disponibile. Si legge lo schermo vero e ci si sta
        dentro, con un tetto all'apertura; **lo schermo di ieri puo' non esserci
        piu'**, quindi la posizione si accetta solo se ci cade dentro una.
        """
        self._pref = preferenze.leggi()
        schermo = QGuiApplication.primaryScreen().availableGeometry()
        tetto_l = max(tema.MIN_LARGO, schermo.width() - 48)
        tetto_a = max(tema.MIN_ALTO, schermo.height() - 72)
        largo = min(int(self._pref.get("larghezza", tema.LARGO)), tetto_l)
        alto = min(int(self._pref.get("altezza", tema.ALTO)), tetto_a)
        # **Sotto il minimo non si comprime niente.** Un controllo che si stringe
        # fino a diventare illeggibile e' peggio di un controllo che esce dalla
        # finestra, perche' il secondo si vede e il primo si usa per sbaglio.
        self.setMinimumSize(tema.MIN_LARGO, tema.MIN_ALTO)
        self.resize(max(tema.MIN_LARGO, largo), max(tema.MIN_ALTO, alto))
        if "x" in self._pref and "y" in self._pref:
            x, y = int(self._pref["x"]), int(self._pref["y"])
            if schermo.contains(x + 60, y + 30):
                self.move(x, y)

    def _scorciatoie(self) -> None:
        """Le cinque che si usano davvero. Il resto lo fa Qt col Tab."""
        for tasti, cosa in (
            ("Ctrl+S", self.salva_profilo),
            ("Ctrl+O", self.apri_profilo),
            ("Ctrl+F", self._vai_a_cerca),
            ("Ctrl+L", self.copia_diagnostica),
            ("F1", self.chi_siamo),
        ):
            QShortcut(QKeySequence(tasti), self, activated=cosa)

    def _vai_a_cerca(self) -> None:
        self.schede.setCurrentIndex(self.TUTTE)
        self.p_avanzate.casella.setFocus()
        self.p_avanzate.casella.selectAll()

    def salva_profilo(self) -> None:
        """La configurazione come profilo: un file che si legge e si manda.

        **Non un file di preferenze opaco**, e la differenza conta: un profilo si
        apre, si diffa e si allega a un rapporto. Salvare 166 campi dentro un
        blob vorrebbe dire perdere l'unica cosa che rende riproducibile una prova.
        """
        percorso, _ = QFileDialog.getSaveFileName(
            self, "Salva la configurazione", str(PROFILES_DIR / "mio.json"),
            "Profili livedub (*.json)")
        if not percorso:
            return
        try:
            self.cfg.save(percorso)
            self.scrivi(f"configurazione salvata in {percorso}")
        except Exception as e:
            self._guaio(f"non sono riuscito a salvare: {e}")

    def apri_profilo(self) -> None:
        percorso, _ = QFileDialog.getOpenFileName(
            self, "Apri una configurazione", str(PROFILES_DIR), "Profili livedub (*.json)")
        if not percorso:
            return
        try:
            nuova = Config.load(percorso)
        except Exception as e:
            self._guaio(f"quel profilo non si apre: {e}")
            return
        # Si copia **dentro** l'oggetto che tutti hanno in mano, invece di
        # sostituirlo: i pannelli e la catena tengono un riferimento, e cambiarlo
        # sotto di loro li lascerebbe a guardare una config che non e' piu' in uso.
        for campo in campi_di(nuova):
            try:
                self.cfg.set(campo, nuova.get(campo))
            except Exception:
                pass
        self._riallinea()
        self.scrivi(f"configurazione caricata da {percorso}")

    def copia_diagnostica(self) -> None:
        """Versione, sistema e configurazione negli appunti, per un rapporto.

        Chiedere «che versione hai e com'era configurato» a chi segnala un
        difetto non funziona mai: o non lo sa, o lo copia male. Un tasto si'.
        """
        testo = f"{scheda()}\n\n--- configurazione ---\n{self.cfg.dump()}"
        QApplication.clipboard().setText(testo)
        self.scrivi(f"diagnostica negli appunti ({len(testo.splitlines())} righe) — "
                    f"incollala in un rapporto di errore")

    # >>> tutorial (ui/tutorial.py): due metodi, e non uno, perche' «aprirlo» e
    # «aprirlo da solo» sono due decisioni diverse — la seconda deve saper dire
    # di no quando la finestra non e' a schermo.
    def apri_tutorial(self, prima_volta: bool = False) -> None:
        tutorial.Tutorial(self, prima_volta=prima_volta).exec()

    def _forse_tutorial(self) -> None:
        """La prima volta si apre da solo. La regola sta in `core/preferenze.py`.

        `WA_DontShowOnScreen` e' la guardia che serve davvero: `tools/scatta.py`
        e `tools/traduci_ui.py` costruiscono questa finestra senza mostrarla, e
        un dialogo modale li' dentro li bloccherebbe per sempre — con la suite
        verde, perche' nessuno dei due e' nella suite.

        **Ma quella guardia da sola era meta', e la meta' che mancava e' quella
        che ha morso.** Copriva «costruita e dichiarata non a schermo» e non
        «costruita e mai mostrata», che e' il caso della suite: il gruppo
        `coerenza` costruisce la finestra e chiama `processEvents()`, il timer
        parte, `exec()` non torna **mai**. Misurato: la suite intera e' rimasta
        ferma oltre dieci minuti senza stampare una riga, cioe' il peggior modo
        possibile di fallire — non rossa, appesa.

        Quindi la condizione non e' «e' stato chiesto di nasconderla» ma «e'
        davvero davanti a qualcuno», che e' la domanda vera e che nessun
        chiamante nuovo deve ricordarsi di porsi.
        """
        if not self.isVisible() or self.testAttribute(Qt.WA_DontShowOnScreen):
            return
        if preferenze.tutorial_da_mostrare():
            self.apri_tutorial(prima_volta=True)
    # <<< tutorial

    def chi_siamo(self) -> None:
        d = QDialog(self)
        d.setWindowTitle(f"{NOME} {VERSIONE}")
        d.resize(640, 420)
        L = QVBoxLayout(d)
        L.setContentsMargins(tema.S5, tema.S5, tema.S5, tema.S5)
        L.setSpacing(tema.S3)
        alto = QHBoxLayout()
        alto.setSpacing(tema.S3)
        immagine = QLabel()
        pix = QPixmap(str(tema.logo(taglia=256)))
        if not pix.isNull():
            immagine.setPixmap(pix.scaled(64, 64, Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))
        alto.addWidget(immagine)
        nome = QLabel(f"{NOME} {VERSIONE}")
        nome.setObjectName("nomeApp")
        alto.addWidget(nome, 1)
        L.addLayout(alto)
        corpo = QTextEdit()
        corpo.setReadOnly(True)
        corpo.setPlainText(
            f"{scheda()}\n\nRegistro: {registro.percorso()}\n"
            f"Licenza: GPL-3.0-or-later (vedi LICENZE.md)")
        L.addWidget(corpo, 1)
        piede = QHBoxLayout()
        piede.addStretch(1)
        b = QPushButton("Chiudi")
        b.setObjectName("primario")
        b.clicked.connect(d.accept)
        piede.addWidget(b)
        L.addLayout(piede)
        d.exec()

    def _guaio(self, testo: str) -> None:
        registro.scrivi(testo)
        self.scrivi("! " + testo)
        self.stato("guasto", self.tavolozza.rosso)

    def apri_registro(self) -> None:
        """Il file del registro, aperto con quello che Windows usa per i testi."""
        import os

        try:
            os.startfile(registro.percorso())  # noqa: S606
        except Exception as e:
            self.scrivi(f"! non riesco ad aprire il registro: {e}")

    def closeEvent(self, evento) -> None:
        """Chiudendo si ricorda dov'era la finestra e cosa si stava guardando.

        **E si ferma la sessione**, che non e' la stessa cosa che chiudere la
        finestra: senza, i due thread restano vivi come demoni, il WAV non viene
        scritto e la cartella in `runs/` resta a meta' — la stessa forma della
        cura che si era fermata a meta' col guasto dell'audio.
        """
        if self.motore.acceso or self.motore.pipeline is not None:
            self.ferma()
        if self.overlay is not None:
            self.overlay.distruggi()
        g = self.geometry()
        preferenze.aggiorna(
            x=g.x(), y=g.y(), larghezza=g.width(), altezza=g.height(),
            scheda=self.schede.currentIndex(),
        )
        registro.scrivi("finestra chiusa")
        super().closeEvent(evento)

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nome imposto da Qt)
        """Il velo copre il centro, e il centro cambia taglia.

        Il `hasattr` non e' prudenza generica: `_geometria()` chiama `resize()`
        **prima** che il widget centrale esista, quindi il primo evento arriva a
        una finestra senza velo. Senza questa riga la finestra non si apre
        affatto — e si aprirebbe benissimo sulla macchina di chi l'ha scritta,
        perche' li' l'ultima geometria salvata coincide gia'.
        """
        super().resizeEvent(evento)
        if hasattr(self, "velo") and self.centralWidget() is not None:
            self.velo.setGeometry(self.centralWidget().rect())

    def _tema_cambiato(self, *_a) -> None:
        """Windows e' passato da chiaro a scuro (o viceversa) mentre giocavamo."""
        nuova = tema.attuale(QApplication.instance())
        if nuova.nome == self.tavolozza.nome:
            return
        vecchia = self.tavolozza
        self.tavolozza = nuova
        self.setStyleSheet(tema.foglio(nuova))
        # **Il colore congelato va tradotto nella tavolozza nuova.** `rosso` e'
        # `#ff6b5e` sullo scuro e `#cc372c` sul chiaro: un confronto scritto su
        # una stringa di colore vecchia smette di funzionare **senza dare
        # errore**, e con lui il logo che cambia faccia.
        if self._colore_stato == vecchia.rosso:
            self._colore_stato = nuova.rosso
        elif self._colore_stato == vecchia.ambra:
            self._colore_stato = nuova.ambra
        elif self._colore_stato == vecchia.testo_fioco:
            self._colore_stato = nuova.testo_fioco
        else:
            self._colore_stato = nuova.accento
        self.misura.veste(nuova)
        self.velo.veste(nuova)
        self.ora.veste(nuova)
        self.personaggi.veste(nuova)
        self.stato(self._stato_testo, self._colore_stato)
        self.scrivi(f"tema di sistema: {nuova.nome}")

    def cambia_lingua(self) -> None:
        """Il cambio di lingua a finestra aperta, **coperto dal velo**.

        Rivestire la finestra costa 32-43 ms secondo il catalogo (misurato su
        `de`, `it` e `ja`): non e' lento, e' *istantaneo*, e a schermo 605
        stringhe che cambiano tutte insieme si leggono come uno scatto. Il velo
        mette un principio e una fine attorno a quel salto — entra, il lavoro si
        fa mentre non si vede niente, esce. Cronometrato dal clic alla scomparsa:
        **341 ms**, di cui 61 il rifacimento vero.

        **La regola su quando non farlo sta fuori da qui** (`tema.durata_carico`):
        a sessione accesa il velo non c'e', perche' i due thread della catena non
        devono pagare un'animazione. `copri` fa il lavoro comunque, ed e' la meta'
        che si dimentica: un velo spento non deve voler dire una lingua che non
        cambia.

        Non e' la stessa cosa di `vesti_lingua`, che serve anche alla
        **costruzione** della finestra: li' non c'e' niente da coprire, perche' a
        schermo non c'e' ancora niente.
        """
        self.velo.copri(tema.durata_carico(self.in_sessione), self.vesti_lingua)

    def vesti_lingua(self) -> None:
        """Mette la finestra nella lingua di `ui.lingua`, e dice **quanto manca**.

        A caldo, come il tema: si ripercorre l'albero dei widget e si
        riscrivono i testi. Non c'e' niente da riavviare, quindi il campo non
        e' fra i `FREDDI` e la finestra non promette un «all'avvio» che non
        servirebbe.

        La riga nel registro non e' decorazione. Un catalogo a meta' non si
        vede guardando: si vedono due parole italiane in mezzo al tedesco e si
        pensa che siano parole che non si traducono. Qui si dice il numero, ed
        e' lo stesso numero che la verifica `ui_lingua` tiene sotto un tetto.
        """
        scelta = lingua.risolvi(self.cfg.ui.lingua)
        tradotte, in_italiano = lingua.applica(self, scelta)
        # La riga «da fare nella preparazione» e' marcata `nontradurre` perche'
        # se la compone da sola: la passeggiata l'ha saltata, quindi va rifatta
        # qui o resterebbe nella lingua di prima — che e' peggio dell'italiano,
        # perche' sembrerebbe una parola non tradotta invece di una vecchia. E
        # va rifatta **anche** tornando all'italiano, che e' il ritorno da ogni
        # altra lingua. Lo stesso vale per i due segnaposto della scheda
        # Sessione, per la stessa ragione e con la stessa cura.
        self.aggiorna_pronto()
        self._svuota_sessione()
        if scelta == lingua.SORGENTE:
            # **Il ripiego si dichiara, ma solo quando c'e' stato un ripiego.**
            # `auto` su una Windows in svedese e' un ripiego: la finestra resta
            # in italiano e senza una riga sembrerebbe che la scelta non abbia
            # funzionato. `auto` su una Windows **italiana** non lo e': ha fatto
            # esattamente quello che doveva. La prima stesura le confondeva e
            # scriveva un `!` su tutte e due — visto nel registro di una prova
            # vera. Un `!` speso dove non e' successo niente e' il ripiego
            # silenzioso girato dall'altra parte: la volta che conta, non lo
            # legge piu' nessuno. La regola sta in `ui.lingua.perche_italiano`,
            # fuori dalla finestra, perche' e' una regola.
            perche = lingua.perche_italiano(self.cfg.ui.lingua)
            if perche == "senza catalogo":
                self.scrivi(f"! nessun catalogo per «{self.cfg.ui.lingua}»: "
                            f"la finestra resta in italiano")
            elif perche == "sistema":
                self.scrivi("lingua della finestra: it (come Windows)")
            return
        self.scrivi(f"lingua della finestra: {scelta} "
                    f"({tradotte} scritte, {in_italiano} ancora in italiano)")

    # -- pezzi della finestra ----------------------------------------------

    @staticmethod
    def _in_margine(w: QWidget) -> QWidget:
        """Il margine standard di un contenitore: `S5` ai lati e `S3` sopra e sotto.

        **Non e' simmetrico apposta**: una finestra e' larga e bassa, e lo stesso
        margine sopra e ai lati fa sembrare tutto schiacciato in alto.
        """
        fuori = QWidget()
        fuori.setObjectName("scheda")
        L = QVBoxLayout(fuori)
        L.setContentsMargins(tema.S5, tema.S3, tema.S5, tema.S3)
        L.addWidget(w)
        return fuori

    def _testata(self) -> QWidget:
        w = QWidget()
        w.setObjectName("testata")
        w.setFixedHeight(tema.H_TESTATA)
        L = QHBoxLayout(w)
        L.setContentsMargins(tema.S5, 0, tema.S5, 0)
        L.setSpacing(tema.S3)

        # **Il logo, grande e senza niente dietro.** Era 32 px dentro una tessera
        # 40x40 stondata: due angoli stondati uno dentro l'altro, e il quadratino
        # faceva sembrare il personaggio piu' piccolo di quello che e'. Il fondo
        # dei PNG e' stato tolto apposta perche' stiano su qualunque superficie,
        # quindi la tessera non serviva a niente. **E' l'unica immagine
        # dell'interfaccia**, e scambia col guasto.
        self.tessera_logo = QLabel()
        self.tessera_logo.setObjectName("logo")
        self.tessera_logo.setAlignment(Qt.AlignCenter)
        self.tessera_logo.setAccessibleName("il logo di livedub")
        self._dipingi_logo(rotto=False)
        L.addWidget(self.tessera_logo)

        nome = QLabel("livedub")
        nome.setObjectName("nomeApp")
        L.addWidget(nome)

        # **Lo stato non sta piu' qui.** C'era una pillola con dentro la stessa
        # parola che la barra in fondo scrive gia', e a un centimetro dal logo che
        # cambia faccia sulla stessa condizione: tre modi di dire una cosa sola,
        # in due angoli opposti della finestra. Resta il colore, che decide la
        # faccia del logo e la spia in fondo.
        self._colore_stato = self.tavolozza.testo_fioco
        self._stato_testo = "fermo"

        L.addStretch(1)
        # La risposta a «ma sta guardando la finestra giusta?», che ci si fa una
        # volta all'inizio e mai piu'.
        self.l_bersaglio = QLabel("nessuna finestra scelta")
        self.l_bersaglio.setObjectName("tenue")
        L.addWidget(self.l_bersaglio)
        # >>> tutorial (ui/tutorial.py): il modo esplicito di rivedere la guida.
        L.addWidget(tutorial.bottone(self, self.apri_tutorial))
        # <<< tutorial
        # I due bottoni senza fondo di tutta la finestra.
        info = QPushButton("ⓘ")
        info.setObjectName("aiuto")
        info.setCursor(Qt.PointingHandCursor)
        info.setToolTip("Versione, sistema e provider (F1)")
        info.setAccessibleName("informazioni sul programma")
        info.clicked.connect(self.chi_siamo)
        L.addWidget(info)
        return w

    def _dipingi_logo(self, rotto: bool) -> None:
        # Si parte dal PNG a 256 e si scala: partendo da quello a 64 px, ingrandito
        # a 44 il logo veniva sgranato — e a quella taglia si vede.
        pix = QPixmap(str(tema.logo(rotto=rotto, taglia=256)))
        if not pix.isNull():
            self.tessera_logo.setPixmap(
                pix.scaled(tema.LATO_LOGO, tema.LATO_LOGO,
                           Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.tessera_logo.setAccessibleDescription(
            "la catena e' in avaria" if rotto else "il programma e' vivo")

    def _barra(self) -> QWidget:
        """Le azioni che devono essere raggiungibili **sempre**, e nient'altro.

        «Scegli finestra», «Seleziona area» e le impostazioni della lettura
        stanno nella scheda della preparazione, dove hanno il numero del passo e
        la spiegazione accanto. Tenerle anche qui vorrebbe dire **lo stesso
        comando in due posti** — due griglie di caselle sopra un solo oggetto,
        che e' la forma di difetto che questo progetto ha gia' inseguito due
        volte.

        Restano Avvia e Ferma, perche' si premono col gioco davanti e non si puo'
        chiedere di cercare la scheda giusta; e — dopo un filo da 1 px — la riga
        che dice cosa manca. Senza il filo le due zone si leggono come un'unica
        barra di comandi, e la riga di stato sembra un bottone.
        """
        w = QWidget()
        w.setObjectName("barra")
        w.setFixedHeight(tema.H_BARRA)
        L = QHBoxLayout(w)
        L.setContentsMargins(tema.S5, 0, tema.S5, 0)
        L.setSpacing(tema.S2)
        # **Un solo bottone e' quello che si preme, e si vede**: se fossero tutti
        # uguali l'occhio dovrebbe leggerli tutti per trovarlo.
        self.b_avvia = QPushButton("Avvia")
        self.b_avvia.setObjectName("primario")
        self.b_avvia.setAccessibleName("avvia il doppiaggio")
        self.b_avvia.clicked.connect(self.avvia)
        L.addWidget(self.b_avvia)
        self.b_ferma = QPushButton("Ferma")
        self.b_ferma.setAccessibleName("ferma il doppiaggio")
        self.b_ferma.setEnabled(False)
        self.b_ferma.clicked.connect(self.ferma)
        L.addWidget(self.b_ferma)

        # **Niente filo, e niente ROI.** Il filo divideva due zone — le azioni e
        # le impostazioni della sessione — ma le impostazioni sono nella scheda
        # della preparazione: restava una riga grigia verticale fra un bottone e
        # una frase, cioe' un separatore che non separa niente. E la ROI era
        # scritta due volte a quindici centimetri di distanza: quella in fondo
        # c'e' sempre ed e' quella giusta.
        L.addSpacing(tema.S4)
        # **Si accorcia invece di allargare la finestra.** «da fare nella
        # preparazione: scegli la finestra del gioco · sistema l'audio · l'area e'
        # troppo alta» e' lunga quanto tre bottoni: da `QLabel` normale imponeva
        # a tutta la barra — e quindi alla finestra — un minimo di 978 px, cioe'
        # piu' del minimo dichiarato. Il testo intero resta nel suggerimento.
        self.l_pronto = Elidibile("")
        self.l_pronto.setObjectName("tenue")
        # **Questa riga se la traduce da sola**, e per questo la passeggiata dei
        # cataloghi non la deve toccare: si veda `aggiorna_pronto`.
        self.l_pronto.setProperty(lingua.MARCHIO, True)
        L.addWidget(self.l_pronto, 1)
        return w

    def aggiorna_pronto(self) -> None:
        """Dice a colpo d'occhio **cosa manca ancora**, e non «pronto: si'/no».

        Un indicatore binario lascia cercare da soli quale dei passi non e' stato
        fatto. Questo nomina il primo che manca, che e' il passo da andare a fare
        — ed e' la stessa lista che accende i tre passi nella scheda Sessione.
        """
        # **Si traducono i pezzi e poi si uniscono, non la frase unita.** Questa
        # riga nasce a runtime da un elenco che cambia con lo stato, quindi nel
        # catalogo finiva come **una combinazione sola** — quella che c'era
        # all'estrazione. Corrispondeva a un istante e a nessun altro: sistemato
        # l'audio, la frase nuova non era piu' nel catalogo e tornava in
        # italiano in mezzo al tedesco, con tutto il resto della finestra
        # tradotto. Tre pezzi in catalogo coprono invece tutte e otto le
        # combinazioni.
        def dillo(testo: str) -> str:
            return lingua.traduci(testo, self.cfg.ui.lingua)

        manca = []
        if self.motore.finestra is None:
            manca.append(dillo("scegli la finestra del gioco"))
        if not (hasattr(self, "audio") and self.audio.valido()):
            manca.append(dillo("sistema l'audio"))
        if self.cfg.vision.roi[3] > 0.12:
            manca.append(dillo("l'area e' troppo alta"))
        if self.motore.acceso:
            testo = ""
        elif manca:
            testo = dillo("da fare nella preparazione:") + "  " + " · ".join(manca)
        else:
            testo = dillo("pronto")
        # Il suggerimento si riscrive **prima** del testo: `Elidibile` lo usa come
        # testo intero solo se non ce n'e' gia' uno, e senza questa riga resterebbe
        # per sempre quello del primo giro — cioe' l'elenco di cose da fare di
        # quando la finestra si e' aperta.
        self.l_pronto.setToolTip(testo)
        self.l_pronto.setText(testo)
        if hasattr(self, "passi"):
            self.passi.aggiorna([
                self.motore.finestra is not None,
                self._area_scelta,
                self.motore.acceso,
            ])

    def _striscia(self) -> QWidget:
        self.striscia = QWidget()
        self.striscia.setObjectName("striscia")
        self.striscia.setFixedHeight(tema.H_STRISCIA)
        L = QHBoxLayout(self.striscia)
        L.setContentsMargins(tema.S4, tema.S1, tema.S2, tema.S1)
        L.setSpacing(tema.S2)
        self.l_attesa = QLabel("")
        L.addWidget(self.l_attesa, 1)
        lascia = QPushButton("Lascia stare")
        lascia.clicked.connect(self.scarta_in_attesa)
        L.addWidget(lascia)
        applica = QPushButton("Applica ora")
        applica.setObjectName("accento")
        applica.clicked.connect(self.applica_in_attesa)
        L.addWidget(applica)
        self.striscia.setVisible(False)
        fuori = QWidget()
        F = QVBoxLayout(fuori)
        F.setContentsMargins(tema.S5, 0, tema.S5, tema.S2)
        F.addWidget(self.striscia)
        self._guscio_striscia = fuori
        return fuori

    # -- la scheda della preparazione ---------------------------------------

    def _passo(self, numero: str, titolo: str, spiegazione: str, dentro) -> QWidget:
        """Un passo della preparazione: numero, titolo, perche', e il comando.

        **Numerati e in ordine**, perche' l'ordine non e' estetico: senza aver
        scelto la finestra non si puo' tirare l'area (il rettangolo sarebbe in
        coordinate dello schermo invece che del gioco), e senza audio non c'e'
        riconoscimento di chi parla. Una griglia di comandi tutti uguali lascia
        indovinare la sequenza; una lista numerata la dice.
        """
        w = QWidget()
        w.setObjectName("gruppo")
        L = QVBoxLayout(w)
        L.setContentsMargins(0, 0, 0, tema.S6)
        L.setSpacing(tema.S1)
        alto = QHBoxLayout()
        alto.setSpacing(tema.S3)
        n = QLabel(numero)
        n.setObjectName("passo")
        alto.addWidget(n)
        t = QLabel(titolo)
        t.setObjectName("titoloPasso")
        alto.addWidget(t)
        alto.addStretch(1)
        L.addLayout(alto)
        # Il rientro del corpo e' la pillola (28) piu' la sua distanza (S3): il
        # testo si allinea al titolo invece di partire a caso.
        rientro = tema.H_PILLOLA + tema.S3
        if spiegazione:
            s = QLabel(spiegazione)
            s.setObjectName("tenue")
            s.setWordWrap(True)
            s.setContentsMargins(rientro, 0, 0, tema.S1)
            L.addWidget(s)
        guscio = QWidget()
        guscio.setObjectName("gruppo")
        G = QVBoxLayout(guscio)
        G.setContentsMargins(rientro, 0, 0, 0)
        G.setSpacing(tema.S2)
        if isinstance(dentro, QWidget):
            G.addWidget(dentro)
        else:
            G.addLayout(dentro)
        L.addWidget(guscio)
        return w

    def _colonna(self, dentro: QWidget) -> QWidget:
        """Colonna unica, larga al massimo `MAX_CONTENUTO`, centrata se avanza.

        Un elenco di parametri lungo 2400 px su un monitor grande e' illeggibile:
        l'occhio perde la riga fra l'etichetta e il controllo. Il log fa
        eccezione — quello usa tutta la larghezza, perche' e' fatto di colonne
        allineate in monospazio.
        """
        fuori = QWidget()
        fuori.setObjectName("gruppo")
        L = QHBoxLayout(fuori)
        L.setContentsMargins(0, 0, 0, 0)
        L.addStretch(1)
        dentro.setMaximumWidth(tema.MAX_CONTENUTO)
        L.addWidget(dentro, 1)
        L.addStretch(1)
        return fuori

    def _scheda_avvio(self) -> QWidget:
        fuori = QScrollArea()
        fuori.setObjectName("scheda")
        fuori.setWidgetResizable(True)
        dentro = QWidget()
        dentro.setObjectName("pannello")
        L = QVBoxLayout(dentro)
        L.setContentsMargins(tema.S5, tema.S5, tema.S5, tema.S5)
        L.setSpacing(0)

        # ① la finestra --------------------------------------------------
        riga = QHBoxLayout()
        riga.setSpacing(tema.S3)
        b = QPushButton("Scegli la finestra del gioco")
        b.setObjectName("accento")
        b.clicked.connect(self.scegli_finestra)
        riga.addWidget(b)
        self.l_scelta = QLabel("nessuna finestra scelta")
        self.l_scelta.setObjectName("tenue")
        riga.addWidget(self.l_scelta, 1)
        L.addWidget(self._passo(
            "1", "Che cosa catturare",
            "Il gioco dev'essere in finestra o senza bordi, non a schermo intero "
            "esclusivo. Scegliendo la finestra invece dello schermo, nel fotogramma "
            "che va all'OCR non entra nient'altro — nemmeno le nostre finestre, che "
            "altrimenti il programma finisce per leggere.", riga))

        # ② l'area -------------------------------------------------------
        blocco = QVBoxLayout()
        blocco.setSpacing(tema.S2)
        self.c_roi = Rettangolo()
        self.c_roi.imposta(self.cfg.vision.roi)
        self.c_roi.disegna.connect(self.scegli_area)
        blocco.addWidget(self.c_roi)
        L.addWidget(self._passo(
            "2", "Dove sono i sottotitoli",
            "Tira un rettangolo stretto attorno alla riga: attorno all'area il "
            "programma si prende un margine, e un'area alta un sesto dello schermo "
            "diventa una fascia in cui ci sta mezza scena.", blocco))

        # ③ l'audio ------------------------------------------------------
        self.audio = Audio(self.motore.opz)
        self.audio.cambiato.connect(self._audio_scelto)
        L.addWidget(self._passo(
            "3", "L'audio",
            "Il programma ascolta una scheda per sentire il gioco e suona su "
            "un'altra per farti sentire la voce. Non serve un microfono. Se non sai "
            "cosa scegliere, premi «Non ho Voicemeeter».", self.audio))

        # ④ cosa legge ---------------------------------------------------
        self.p_lettura = Pannello(
            self.cfg, al_cambio=self._campo_cambiato, solo=LETTURA, cerca=False,
            scorre=False)
        L.addWidget(self._passo(
            "4", "Come leggere (si puo' lasciare com'e')",
            "I default vanno bene quasi sempre. «Ignora i sottotitoli colorati» e' "
            "l'unico che due giochi vogliono al contrario: e' l'HUD in GTA V e il "
            "nome di chi parla in altri.", self.p_lettura))

        L.addStretch(1)
        fuori.setWidget(self._colonna(dentro))
        return fuori

    def _scheda_traduzione(self) -> QWidget:
        """Le impostazioni, **e la prova che quelle scelte funzionino qui**.

        Cinque traduttori in un menu sembrano cinque possibilita'. Misurati su
        questa macchina erano due: `locale` vuole un `pip install` che nessuno ha
        fatto, `ollama` vuole un server acceso. E quando non funzionano non danno
        errore — si tiene l'originale, in silenzio, e le battute escono nella
        lingua di partenza mentre la finestra dice che sta traducendo.
        """
        w = QWidget()
        w.setObjectName("scheda")
        L = QVBoxLayout(w)
        L.setContentsMargins(tema.S5, tema.S3, tema.S5, tema.S3)
        L.setSpacing(tema.S3)
        L.addWidget(self.p_traduzione, 1)

        riga = QHBoxLayout()
        riga.setSpacing(tema.S3)
        b = QPushButton("Prova i traduttori")
        b.setToolTip("Traduce una battuta con ognuno e dice quale funziona **qui**,\n"
                     "quanto costa e se i sottotitoli escono dal PC.")
        b.clicked.connect(self.prova_traduttori)
        riga.addWidget(b)
        self.l_traduttori = QLabel("")
        self.l_traduttori.setObjectName("mono")
        self.l_traduttori.setWordWrap(True)
        riga.addWidget(self.l_traduttori, 1)
        L.addLayout(riga)
        return w

    def prova_traduttori(self) -> None:
        from translate import diagnosi

        self.l_traduttori.setText("provo… (il primo giro carica i modelli)")
        QApplication.processEvents()
        esiti = diagnosi.tutti(self.cfg.translate)
        for e in esiti:
            self.scrivi("traduttori:  " + diagnosi.riga(e))
        buoni = [e.backend for e in esiti if e.ok and e.testo]
        locali = [e.backend for e in esiti if e.ok and e.testo and e.riservato]
        self.l_traduttori.setText(
            f"funzionano qui: {', '.join(buoni) or 'nessuno'}"
            + (f"   —   senza uscire dal PC: {', '.join(locali)}" if locali else "")
            + "   (il dettaglio e' nel registro della sessione)"
        )

    def _scheda_sessione(self) -> QWidget:
        """**Non un log**, ma tre blocchi in ordine di quanto si guardano.

        Era un registro a tutta pagina, cioe' la risposta a «cosa e' successo»
        messa al posto della risposta a «cosa sta succedendo». Mentre si gioca
        non si legge una lista che scorre: si getta un'occhiata, e un'occhiata
        prende un colore e una riga.

            ┌ la battuta di adesso ────────────────────┐   chi parla, e come va
            └──────────────────────────────────────────┘
              i personaggi sentiti  [M1 12] [M2 8]         e' sempre lo stesso?
              registro                                     cosa e' successo
            ┌──────────────────────────────────────────┐
            │  …                                       │
            └──────────────────────────────────────────┘

        Il log **resta**, e resta intero: e' il posto dove si va a leggere
        quando qualcosa non va, ed e' l'unico che tenga tutta la storia. Ma sta
        sotto, con il suo titolo, invece di essere la prima cosa che si vede.
        """
        contenitore = QWidget()
        contenitore.setObjectName("scheda")
        C = QVBoxLayout(contenitore)
        C.setContentsMargins(tema.S5, tema.S3, tema.S5, tema.S3)
        C.setSpacing(tema.S3)

        # I tre passi stanno **al centro** della scheda, e finche' la catena non
        # parte sono l'unica cosa che si vede qui. Il guscio li centra invece di
        # stirarli: un pannello alto quanto la finestra, con tre righe dentro
        # separate da duecento pixel, non si legge piu' come una lista di passi.
        self.passi = PannelloPassi()
        self._guscio_passi = QWidget()
        G = QVBoxLayout(self._guscio_passi)
        G.setContentsMargins(0, 0, 0, 0)
        G.addStretch(1)
        G.addWidget(self._colonna(self.passi))
        G.addStretch(1)
        C.addWidget(self._guscio_passi, 1)

        # -- il blocco vivo: compare tutto insieme quando la catena parte -----
        self._guscio_vivo = QWidget()
        self._guscio_vivo.setObjectName("gruppo")
        V = QVBoxLayout(self._guscio_vivo)
        V.setContentsMargins(0, 0, 0, 0)
        V.setSpacing(tema.S2)

        self.ora = TesseraOra()
        V.addWidget(self.ora)

        V.addSpacing(tema.S1)
        # **Due titoli di sezione, e nessuno dei due e' una parola sola.** Un
        # titolo di una parola minuscola — `registro`, `personaggi` — e'
        # indistinguibile da un percorso di config, e `ui.lingua._traducibile` lo
        # scarta apposta: sarebbe uscito in italiano in mezzo a una finestra
        # tradotta, senza che niente lo dicesse. Provato: `registro` non compariva
        # nemmeno fra le chiavi estratte.
        titolo = QLabel("chi ha parlato")
        titolo.setObjectName("sezione")
        V.addWidget(titolo)
        self.personaggi = FilaPersonaggi()
        V.addWidget(self.personaggi)

        V.addSpacing(tema.S1)
        titolo = QLabel("registro della sessione")
        titolo.setObjectName("sezione")
        V.addWidget(titolo)
        self.log = QPlainTextEdit()
        self.log.setObjectName("registro")
        self.log.setReadOnly(True)
        # **Un tetto alle righe.** Senza, una sessione di tre ore se lo mangia
        # tutto: e' la domanda 23, e costa una riga.
        self.log.setMaximumBlockCount(5000)
        self.log.setAccessibleName("registro della sessione")
        self.log.setAccessibleDescription("chi parla e cosa e' stato detto, in sola lettura")
        self.log.setFont(tema.carattere_log())
        V.addWidget(self.log, 1)

        self._guscio_vivo.setVisible(False)
        C.addWidget(self._guscio_vivo, 1)

        self.tessera = TesseraGuasto(self.apri_registro, self._riprova)
        C.addWidget(self.tessera)
        return contenitore

    def _mostra_log(self) -> None:
        """Fatti i tre passi, il pannello **si dissolve** e sotto c'e' la sessione.

        Duecento millisecondi, che e' la durata dichiarata per la comparsa e la
        scomparsa di un pannello — e vanno a zero se il sistema chiede meno
        movimento, perche' chi apre questa finestra sta gia' guardando uno
        schermo che si muove molto.
        """
        if self._guscio_vivo.isVisible():
            return
        self._guscio_vivo.setVisible(True)
        self._svuota_sessione()
        ms = tema.durata(tema.MS_PANNELLO)
        if not ms:
            self._guscio_passi.setVisible(False)
            return
        velo = QGraphicsOpacityEffect(self._guscio_passi)
        self._guscio_passi.setGraphicsEffect(velo)
        self._dissolvenza = QPropertyAnimation(velo, b"opacity", self)
        self._dissolvenza.setDuration(ms)
        self._dissolvenza.setStartValue(1.0)
        self._dissolvenza.setEndValue(0.0)
        self._dissolvenza.setEasingCurve(QEasingCurve.OutCubic)
        self._dissolvenza.finished.connect(
            lambda: self._guscio_passi.setVisible(False))
        self._dissolvenza.start()

    def _svuota_sessione(self, forza: bool = False) -> None:
        """I due segnaposto della scheda Sessione, **nella lingua della finestra**.

        `forza` cancella anche una battuta gia' detta, e lo chiede solo chi
        fotografa: lo stato «sto partendo» esiste **prima** della prima battuta,
        e mostrarlo sopra una battuta gia' uscita sarebbe un'immagine che dal
        vivo non capita mai.

        Si compongono qui e non stanno scritti su un widget perche' altrimenti la
        passeggiata dei cataloghi li ricorderebbe come originale italiano e al
        primo cambio di lingua li congelerebbe: e' lo stesso difetto della riga
        «da fare nella preparazione», gia' pagato una volta.
        """
        def dillo(testo: str) -> str:
            return lingua.traduci(testo, self.cfg.ui.lingua)

        if forza or self.ora.vuota:
            self.ora.svuota(dillo("in attesa della prima frase"))
        if forza or not self._conta:
            self.personaggi.svuota(dillo("nessuno ancora"))

    def _audio_scelto(self) -> None:
        """Le schede audio si scelgono a freddo: si applicano al prossimo Avvia."""
        self.aggiorna_pronto()
        if self.in_sessione:
            self._segna_in_attesa("audio (scheda di cattura o di uscita)")

    # -- comportamento ------------------------------------------------------

    def _testo_roi(self) -> str:
        x, y, w, h = self.cfg.vision.roi
        return f"ROI  x{x:.3f}  y{y:.3f}  w{w:.3f}  h{h:.3f}"

    def scrivi(self, testo: str) -> None:
        self._al_log(str(testo), self.tavolozza.testo, gravita(str(testo)))
        registro.scrivi(testo)

    def _al_log(self, testo: str, colore: str, marca: str = "") -> None:
        """Una riga nel registro: la marca nel margine, gli spazi che restano spazi.

        Serve l'HTML perche' **il colore e' l'informazione**: la domanda che si
        fa guardando questo log non e' «cosa ha detto» ma «e' sempre lo stesso a
        parlare?», e a quella l'occhio risponde da un colore molto prima che da
        una sigla. Gli spazi si proteggono a mano: in HTML si mangiano, e le
        colonne allineate sono meta' di cio' che rende leggibile questa lista.

        **La gravita' e' una marca, non un colore del testo.** Colorare di rosso
        una riga di errore brucerebbe il canale che appartiene alle voci, e
        addestrerebbe l'occhio a ignorare il rosso — perche' gli `!` di questo
        programma sono quasi tutti avvisi che non fermano niente. Le due celle
        del margine ci sono **sempre**, cosi' il testo resta allineato che ci sia
        o no la marca.
        """
        tinta = {"avviso": self.tavolozza.ambra,
                 "guasto": self.tavolozza.rosso}.get(marca)
        segno = (f'<span style="color:{tinta}">&#9612;</span>&nbsp;' if tinta
                 else "&nbsp;&nbsp;")
        for riga in testo.split("\n"):
            corpo = html.escape(riga).replace(" ", "&nbsp;") or "&nbsp;"
            self.log.appendHtml(
                f'<span style="line-height:125%">{segno}'
                f'<span style="color:{colore}">{corpo}</span></span>')

    def _colore_voce(self, sid: str) -> str:
        """La tinta di quel personaggio, **assegnata in un posto solo**.

        Adesso quel colore lo usano in tre — il log, la tessera della battuta di
        adesso e la fila dei personaggi — e tre giri di `len(self._voci) % 6`
        scritti a mano sarebbero tre assegnazioni che al primo caso di bordo si
        separano: la stessa sigla di due colori diversi in due punti della stessa
        finestra, senza errore e senza che la suite possa vederlo.
        """
        if sid not in self._voci:
            self._voci[sid] = len(self._voci) % len(self.tavolozza.voci)
        return self.tavolozza.voci[self._voci[sid]]

    def _scrivi_voce(self, sid: str, testo: str) -> None:
        """Una battuta, col colore del personaggio che l'ha detta.

        Sei colori a rotazione, e la sigla accanto **non si toglie mai «perche'
        tanto c'e' il colore»**: chi non distingue le tinte perde le sei voci
        come identita' a colpo d'occhio e le ritrova nella sigla.
        """
        self._al_log(testo, self._colore_voce(sid))
        registro.scrivi(testo)

    def stato(self, testo: str, colore: str | None = None) -> None:
        # Il colore lo decide **la regola**, non chi chiama: «audio interrotto»
        # scritto senza punto esclamativo veniva verde, cioe' il colore del «va
        # tutto bene» sopra una catena morta.
        self._colore_stato = colore or colore_stato(testo, ComeTk(self.tavolozza))
        self._stato_testo = testo
        self.misura.spegni_o_accendi(self._colore_stato, self.motore.sta_parlando)
        # **La barra dell'avvio si spegne su quello che stava aspettando**, non su
        # un timer: chi ha scritto «tre secondi bastano» ha scritto un numero che
        # e' giusto su una macchina e sbagliato su tutte le altre. La prima riga
        # di stato viva vuol dire che i due cicli sono partiti.
        if hasattr(self, "ora") and self.motore.acceso:
            self.ora.pronto()
        self._aggiorna_misura()
        # **Il logo cambia sulla stessa regola, non su una seconda.** Un elenco di
        # stati brutti scritto qui si separerebbe da `colore_stato` al primo stato
        # nuovo, e si separerebbe in silenzio, con la suite verde.
        self._dipingi_logo(rotto=self._colore_stato == self.tavolozza.rosso)

    @property
    def in_sessione(self) -> bool:
        return self.motore.pipeline is not None

    @property
    def overlay(self):
        """**Uno solo, e ce l'ha il motore.** Tenerne una copia qui vorrebbe dire
        che a un certo punto le due divergono, ed e' gia' successo: la finestra
        ne aveva uno costruito all'avvio del programma e il motore un altro —
        cioe' `None` — quindi la traduzione usciva e non la disegnava nessuno.
        """
        return self.motore.overlay

    def _stile(self) -> dict:
        """Com'e' fatto il sottotitolo, secondo la config di **adesso**.

        Una mappatura sola per due usi — costruire la finestra e ristilarla a
        sessione accesa. Scriverla due volte vorrebbe dire che il giorno in cui
        si aggiunge un campo, uno dei due lo prende e l'altro no.

        **Nell'overlay sopra il gioco non ci va niente di Menta.** Quella
        finestra ha regole opposte — niente bordi, i clic la attraversano, non
        ruba il fuoco — e un compito solo: far sembrare che il sottotitolo
        originale non ci sia mai stato. Nessun logo, nessun angolo stondato.
        """
        tr = self.cfg.translate
        return {
            "colore": tr.color,
            "fondo": tr.background,
            "font": tr.font,
            "font_frac": tr.font_frac,
            "opacita": tr.background_opacity,
            "contorno": tr.outline,
            "modo": tr.background_mode,
            "blur": tr.blur_strength,
        }

    def _nuovo_overlay(self):
        """Una finestra senza bordi sopra il gioco, con la config di **adesso**."""
        from ui.overlay_qt import OverlayQt

        return OverlayQt(
            self.cfg.vision.roi,
            trasparente=self.cfg.translate.transparent,
            escludi_cattura=not getattr(self.args, "overlay_catturabile", False),
            **self._stile(),
        )

    def _riallinea(self) -> None:
        """Rilegge **tutti** i pannelli: la config e' una sola, le viste sono sei.

        Stava scritto a mano — `p_tecnologie` e `p_avanzate` — e la
        riprogettazione ha rinominato i gruppi: `p_tecnologie` non esisteva piu'
        da allora, e il `getattr(..., None)` lo trasformava in «niente da fare»
        invece che in un errore. Risultato: solo «Tutte le impostazioni» si
        aggiornava, e le altre schede mostravano il valore di prima.

        Adesso i pannelli si **cercano**, non si elencano: una scheda nuova, o
        rinominata, non puo' restare indietro perche' nessuno se l'e' ricordata.
        """
        for p in self.findChildren(Pannello):
            p.aggiorna()

    # I campi che l'overlay si copia dentro alla nascita: cambiandoli non basta
    # scriverli in config, va **detto alla finestra**. Sono le chiavi di `_stile`
    # tradotte in percorsi, e la verifica `overlay_stile` tiene le due liste
    # insieme invece di sperare che restino d'accordo.
    STILE = (
        "translate.color", "translate.background", "translate.font",
        "translate.font_frac", "translate.background_opacity", "translate.outline",
        "translate.background_mode", "translate.blur_strength",
    )

    def _campo_cambiato(self, campo, valore) -> None:
        self._riallinea()
        if campo.percorso == "vision.roi":
            if hasattr(self, "c_roi"):
                self.c_roi.imposta(self.cfg.vision.roi)
            self.aggiorna_pronto()
        elif campo.percorso == "ui.lingua":
            self.cambia_lingua()
        elif campo.percorso in self.STILE and self.overlay is not None:
            self.overlay.ristila(**self._stile())
            self.scrivi("  (l'aspetto cambia dalla prossima battuta: quella a "
                        "schermo tiene la sua geometria)")
        if campo.caldo:
            self.scrivi(f"{campo.percorso} = {valore}")
        else:
            self.scrivi(f"{campo.percorso} = {valore}   (si legge solo all'avvio)")
            if self.in_sessione:
                self._segna_in_attesa(campo.percorso)

    # -- cosa si cattura ----------------------------------------------------

    def scegli_finestra(self) -> None:
        SelettoreFinestra(self, self._applica_finestra).exec()

    def _applica_finestra(self, finestra) -> None:
        from capture.finestre import rettangolo_client

        self.motore.finestra = finestra
        if finestra is None:
            self.l_bersaglio.setText("tutto lo schermo")
            self.l_scelta.setText("tutto lo schermo — l'OCR leggera' anche cio' che ci sta davanti")
            self.scrivi("cattura: tutto lo schermo")
            if self.overlay is not None:
                self.overlay.aggancia(None)
                # Catturando lo schermo l'overlay ci rientra: va nascosto alla
                # cattura, e il prezzo e' che non lo vede nemmeno chi registra.
                self.overlay.esclusione(True)
                self.scrivi("  (l'overlay resta fuori dagli screenshot e da OBS)")
        else:
            self.l_bersaglio.setText(f"{finestra.processo}  {finestra.titolo[:40]}")
            self.l_scelta.setText(f"{finestra.titolo}   ({finestra.larghezza}×{finestra.altezza})")
            self.scrivi(f"cattura: {finestra}")
            if self.overlay is not None:
                self.overlay.aggancia(rettangolo_client(finestra.hwnd))
                # Catturando la sola finestra del gioco l'overlay **non** ci
                # rientra: misurato, zero righe lette che fossero nostre. Quindi
                # torna una finestra normale, e chi registra lo vede.
                self.overlay.esclusione(False)
        self._riallinea()
        self.aggiorna_pronto()
        if self.in_sessione:
            self.scrivi("(vale dalla prossima partenza)")

    def scegli_area(self) -> None:
        # Il riferimento va tenuto: un `QWidget` senza padre che nessuno regge
        # viene raccolto dal garbage collector e la finestra sparisce prima che
        # si sia potuto tirare il rettangolo.
        self._selettore = SelettoreArea(self._applica_roi, self.tavolozza)
        self._selettore.showFullScreen()

    def _in_finestra(self, roi) -> tuple:
        """**Il rettangolo si tira sullo schermo, ma la ROI e' della finestra.**

        Il selettore normalizza su quello che vede — lo schermo — mentre il
        fotogramma che arriva all'OCR e' la finestra del gioco. Senza questa
        conversione l'area finirebbe sulla stessa frazione di *schermo* invece
        che sulla stessa frazione di *finestra*: cioe' quasi sempre altrove, e
        sarebbe la prima cosa che si rompe usando il programma come si deve.
        """
        if self.motore.finestra is None:
            return tuple(roi)
        from capture.finestre import rettangolo_client

        from ui.overlay_qt import schermo_fisico

        r = rettangolo_client(self.motore.finestra.hwnd)
        if not r:
            return tuple(roi)
        ax, ay, aw, ah = r
        # In pixel **fisici**, come il rettangolo della finestra: con Windows al
        # 125% i due sistemi non coincidono, e l'area cadrebbe un quarto piu' in
        # la' — il difetto «il riquadro sta dove il testo non c'era», causato da
        # un'unita' di misura invece che dalla geometria.
        (sw, sh), _dpr = schermo_fisico()
        x = (roi[0] * sw - ax) / max(1, aw)
        y = (roi[1] * sh - ay) / max(1, ah)
        w = roi[2] * sw / max(1, aw)
        h = roi[3] * sh / max(1, ah)
        if x < -0.02 or y < -0.02 or x + w > 1.02 or y + h > 1.02:
            self.scrivi("! l'area che hai tirato esce dalla finestra scelta: "
                        "l'ho tagliata al suo bordo")
        return (min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0), min(w, 1.0), min(h, 1.0))

    def _applica_roi(self, roi) -> None:
        roi = self._in_finestra(roi)
        self.cfg.vision.roi = tuple(roi)
        self._area_scelta = True
        # **Un'area alta e' il difetto che si vede di piu', e non sembra suo.**
        # La fascia d'analisi e' l'area piu' un respiro proporzionale a lei:
        # tirandola alta un sesto dello schermo diventa 391 px per una riga da
        # 45, e in quello spazio ci finisce mezza scena. Su un fondo chiaro la
        # riga di testo si **salda** a cio' che ha attorno, e il riquadro sfocato
        # cresce con lei. Nessun filtro puo' disfare una saldatura; stringere
        # l'area si' — e adesso il selettore lo dice **mentre** si tira.
        if roi[3] > 0.12:
            self.scrivi(f"! l'area e' alta {roi[3]:.3f} dello schermo: tirala stretta "
                        f"attorno alla riga dei sottotitoli (0,06-0,10), se no il blur "
                        f"si allarga su quello che le sta intorno")
        self.c_roi.imposta(self.cfg.vision.roi)
        # **L'overlay deve seguire l'area.** Senza, la finestra del tradotto
        # resta dove stava la ROI di partenza — un difetto che si attribuirebbe
        # al calcolo del riquadro.
        if self.overlay is not None:
            self.overlay.riposiziona(self.cfg.vision.roi)
        self._riallinea()
        self.aggiorna_pronto()
        self.scrivi(f"area impostata: {self._testo_roi()}")
        if self.in_sessione:
            self.scrivi("(vale dalla prossima partenza)")

    # -- avvio e arresto ----------------------------------------------------

    def avvia(self) -> None:
        if self.motore.acceso:
            return
        # **L'overlay si costruisce adesso, con la configurazione di adesso.**
        # E si dice a chiare lettere se c'e' o no: una traduzione che esce e non
        # si vede e' un difetto che non lascia tracce da nessuna parte.
        self.motore.prepara_overlay(self._nuovo_overlay)
        self.tessera.setVisible(False)
        # Terzo passo fatto: il pannello lascia il posto al log.
        self.schede.setCurrentIndex(self.SESSIONE)
        self._mostra_log()
        # **L'unica attesa lunga della finestra si vede.** Fra Avvia e la prima
        # riga di stato ci sono l'apertura dei device e il caricamento del
        # motore: con Kokoro sono secondi, e una finestra che non dice niente per
        # tre secondi si legge come una finestra bloccata. La barra si spegne da
        # sola in `stato()`, alla prima riga viva.
        self.ora.aspetta()
        if self.cfg.translate.enabled:
            self.scrivi(
                f"traduzione {self.cfg.translate.source}→{self.cfg.translate.target} "
                f"con {self.cfg.translate.backend}: "
                + ("il tradotto si disegna sopra il gioco" if self.overlay is not None
                   else "! solo voce, niente a schermo (translate.overlay e' spento)")
            )
        self.b_avvia.setEnabled(False)
        self.b_ferma.setEnabled(True)
        self.schede.setTabEnabled(self.PREPARAZIONE, False)
        self.aggiorna_pronto()
        self.motore.avvia()

    def ferma(self) -> None:
        self.motore.ferma()

    def _riprova(self) -> None:
        """Il bottone dentro la tessera del guasto: rimette in piedi la sessione.

        **La strada normale fa quattro cose**, non una: chiude la sessione,
        scrive il WAV, rimette i bottoni e scrive lo stato. Una cura che ne fa
        una sola lascia una finestra in uno stato che non esiste — ed e'
        esattamente il difetto per cui questa tessera e' stata scritta.
        """
        self.tessera.setVisible(False)
        if self.motore.acceso or self.motore.pipeline is not None:
            self.ferma()
        self.avvia()

    def _fine_thread(self) -> None:
        self.b_avvia.setEnabled(True)
        self.b_ferma.setEnabled(False)
        # Anche l'avvio **fallito** finisce qui, ed e' il ramo che si dimentica:
        # senza, una barra di caricamento resterebbe a scorrere sopra una catena
        # che non e' mai partita.
        self.ora.pronto()
        # **La preparazione si spegne tutta, non due bottoni.** Cosa si cattura,
        # da dove arriva l'audio e dove sono i sottotitoli si leggono all'avvio:
        # lasciarli toccabili a sessione accesa vorrebbe dire una finestra che
        # mostra una configurazione diversa da quella in uso.
        self.schede.setTabEnabled(self.PREPARAZIONE, True)
        self._mostra_attesa()
        self.aggiorna_pronto()

    def _audio_guasto(self, dettaglio: str) -> None:
        """Il ciclo audio e' morto: si chiude la sessione come se fosse un Ferma.

        **Il guasto piu' probabile e' anche quello da cui si deve poter
        tornare**: cuffie staccate, il device cambiato sotto i piedi. Dirlo e
        basta lasciava la finestra in uno stato che non esiste — nessun thread
        vivo, Avvia spento, la sessione aperta e il WAV mai scritto — e l'unica
        via d'uscita era premere Ferma, che nessuno pensa di premere quando ha
        appena letto «premi Avvia».
        """
        for riga in righe_guasto_audio(dettaglio):
            self.scrivi(riga)
        self.tessera.mostra(
            "L'audio si e' fermato", dettaglio,
            "Probabile: cuffie o altoparlanti staccati, oppure il device e' "
            "cambiato sotto i piedi. Ricollega e premi RIPROVA.")
        self._mostra_log()
        self.schede.setCurrentIndex(self.SESSIONE)
        if self.motore.acceso or self.motore.pipeline is not None:
            self.ferma()
        else:
            # **E se la catena era gia' morta, i bottoni li rimette comunque
            # qualcuno.** Senza questo ramo il messaggio dice «premi Avvia»
            # indicando un bottone spento: e' lo stesso difetto di prima, e
            # sopravvive dentro la sua stessa cura.
            self._fine_thread()
        # Dopo `ferma`, se no lo stato «fermo» che manda lei arriverebbe dopo
        # questo e cancellerebbe il rosso.
        self.coda.put(("stato", STATO_GUASTO))

    # -- il giro della coda -------------------------------------------------

    def _aggiorna_misura(self) -> None:
        """Un solo giro di misure per i due posti che le guardano, a 2 Hz.

        La barra in fondo prende i percentili, la tessera in cima prende la
        parola di adesso: **stesso dizionario**, letto con due domande. Due
        chiamate a `misure()` costerebbero due letture del registro della catena
        e — peggio — permetterebbero ai due di mostrare istanti diversi.
        """
        dati = self.motore.misure()
        dati["stato"] = self._stato_testo
        self.misura.mostra(barra_misura(dati))
        if hasattr(self, "ora"):
            self.ora.mostra_fase(
                self._fase_tradotta(fase_catena(dati)),
                self._colore_stato,
                bool(dati.get("parla")),
            )

    def _fase_tradotta(self, fase):
        """Le quattro parole della fase, nella lingua della finestra.

        Sono **scritte qui per esteso** e non ricavate da `motore.FASI` con un
        ciclo, e non e' pigrizia al contrario: la verifica `ui_lingua` legge il
        sorgente di questo file e pretende che ogni stringa passata a `dillo`
        stia in `lingua.COMPOSTE`. Un ciclo passerebbe una variabile, la verifica
        non vedrebbe niente, e le quattro parole uscirebbero in italiano in mezzo
        a una finestra tradotta — che e' esattamente il difetto per cui
        `COMPOSTE` esiste. La suite tiene i due elenchi d'accordo.
        """
        def dillo(testo: str) -> str:
            return lingua.traduci(testo, self.cfg.ui.lingua)

        parole = {
            "fermo": dillo("fermo"),
            "sta leggendo": dillo("sta leggendo"),
            "sta parlando": dillo("sta parlando"),
            "in ritardo": dillo("in ritardo"),
        }
        return replace(fase, testo=parole.get(fase.testo, fase.testo))

    def _svuota_coda(self) -> None:
        # **Dei ritagli si disegna solo l'ultimo.** Ne arrivano trenta al secondo
        # e questo giro ne fa sessanta al piu': disegnarli tutti vorrebbe dire
        # fare piu' lavoro per mostrare solo l'ultimo, e — peggio — se disegnare
        # costa piu' di quanto arriva, la coda si allunga e la macchia sfocata
        # resta indietro **sempre di piu'**.
        ultimo_ritaglio = None
        try:
            while True:
                tipo, dato = self.coda.get_nowait()
                if tipo == "aggiorna":
                    ultimo_ritaglio = dato
                    continue
                if tipo == "riga":
                    sid, voce, testo, lat, t = dato
                    self._detta_qualcosa = True
                    # **Separata dai punti, non dagli spazi.** Il riempimento a
                    # larghezza fissa (`{voce:<14}`) incolonna solo in
                    # monospazio: col carattere dell'interfaccia quelle colonne
                    # non si allineano e restano spazi a caso. I punti dicono
                    # dove finisce un campo senza chiedere niente al carattere, e
                    # i numeri restano incolonnati lo stesso perche' il carattere
                    # del log usa le **cifre tabulari** (si veda
                    # `tema.carattere_log`).
                    self._scrivi_voce(
                        sid, f"{t:6.1f}s · {sid} · {voce} · {lat:.0f} ms · {testo}")
                    # **La stessa battuta va anche in cima alla scheda**, dove si
                    # legge con un'occhiata invece che riga per riga. La fretta e'
                    # l'ultimo campione di `dub.rate_x1000`, cioe' quella chiesta
                    # a questa battuta: il p50 della barra in fondo risponde a
                    # un'altra domanda.
                    self._conta[sid] = self._conta.get(sid, 0) + 1
                    self.ora.dillo(sid, voce, testo, self._colore_voce(sid), lat,
                                   float(self.motore.misure().get("fretta") or 0.0))
                    self.personaggi.aggiorna(self._conta, self._colore_voce)
                elif tipo == "overlay":
                    self._overlay(dato)
                elif tipo == "spegni":
                    if self.overlay is not None:
                        self.overlay.nascondi()
                elif tipo == "stato":
                    self.stato(dato)
                elif tipo == "guasto":
                    self._audio_guasto(dato)
                elif tipo == "finito":
                    # I bottoni li rimette a posto **il thread della finestra**:
                    # il motore si spegne anche da solo (avvio fallito, device
                    # sparito) e da li' non si tocca Qt.
                    self._fine_thread()
                elif tipo == "nota":
                    self.scrivi(dato)
        except queue.Empty:
            pass
        if ultimo_ritaglio is not None and self.overlay is not None:
            pezzo, quando = ultimo_ritaglio
            self.overlay.aggiorna(pezzo)
            self.motore.ritardo((time.perf_counter() - quando) * 1000.0)
        self.motore.segui_finestra()
        # **Il sottotitolo tradotto sparisce da solo**, e aspettando il conto dei
        # giri vuoti invece del solo orologio: spegnere sul tempo scavalcherebbe
        # l'isteresi del ciclo video, e il tradotto sparirebbe al primo buco di
        # letture. Il ritardo di due secondi e' la rete per il caso in cui il
        # ciclo video si sia fermato — li' i giri vuoti non arrivano piu', e una
        # finestra che non si spegne resta in mezzo allo schermo.
        if self.overlay is not None and self.overlay._visibile:
            scaduto = time.perf_counter() >= self.motore.overlay_fino_a
            fermo = time.perf_counter() >= self.motore.overlay_fino_a + 2.0
            if fermo or (scaduto and self.overlay._vuoti
                         >= self.cfg.translate.overlay_hold_frames):
                self.overlay.nascondi()

    def _overlay(self, dato) -> None:
        testo, originale, fine, t_on, pezzo, bande, rett, tinta = dato
        if self.overlay is None:
            return
        # **Una battuta arrivata tardi si mostra lo stesso, per un minimo.**
        # Prima si mostrava solo se il sottotitolo originale era ancora a
        # schermo, e se no la traduzione veniva buttata senza dirlo. Il giocatore
        # quella riga l'ha letta un secondo fa e sta ascoltando la voce che la
        # dice: un buco e' peggio di un ritardo.
        #
        # L'unica cosa che non si fa mai e' **tornare indietro**: una battuta
        # piu' vecchia di quella gia' a schermo si accavallerebbe alla nuova,
        # che e' il difetto peggiore — due sottotitoli insieme.
        if t_on >= self.overlay.t_on:
            self.overlay.mostra(testo, pezzo, bande, rett, tinta, originale)
            self.overlay.t_on = t_on
            if not (self.motore.pipeline is None
                    or self.motore.pipeline.a_schermo(t_on)):
                fine = max(fine, time.perf_counter() + self.cfg.translate.overlay_min_s)
            self.motore.overlay_fino_a = fine
        # **La riga che divide in due il problema.** Se qui c'e' scritto un
        # riquadro e a schermo non si vede niente, il difetto e' di Windows
        # (finestra) e non nostro (traduzione, OCR, geometria).
        self.scrivi(f"overlay  {self.overlay.geometria()}  "
                    f"{'visibile' if self.overlay._visibile else 'NASCOSTO'}")

    # -- le modifiche che aspettano ----------------------------------------

    def _segna_in_attesa(self, percorso: str) -> None:
        if percorso not in self._in_attesa:
            self._in_attesa.append(percorso)
        self._mostra_attesa()

    def _mostra_attesa(self) -> None:
        if not self._in_attesa or not self.in_sessione:
            self.striscia.setVisible(False)
            return
        quante = len(self._in_attesa)
        cosa = ", ".join(self._in_attesa[:3]) + ("…" if quante > 3 else "")
        self.l_attesa.setText(
            f"{quante} modific{'a' if quante == 1 else 'he'} in attesa ({cosa}): "
            f"si applic{'a' if quante == 1 else 'ano'} rifacendo la catena, un paio di secondi"
        )
        self.striscia.setVisible(True)

    def scarta_in_attesa(self) -> None:
        self._in_attesa.clear()
        self._mostra_attesa()
        self.scrivi("le modifiche restano scritte: avranno effetto al prossimo avvio")

    def applica_in_attesa(self) -> None:
        """Ferma e riavvia la catena perche' i parametri freddi facciano effetto.

        **Il prezzo e' dichiarato e non nascosto**: la sessione si chiude e se ne
        apre un'altra, quindi il rapporto viene scritto e i personaggi imparati
        fin qui ripartono da quello che `cast.json` ha salvato. Non e' un cambio
        a caldo travestito: e' un riavvio, fatto per te, in un clic.
        """
        if not self.in_sessione:
            self._in_attesa.clear()
            self._mostra_attesa()
            return
        cosa = ", ".join(self._in_attesa)
        self._in_attesa.clear()
        self._mostra_attesa()
        self.scrivi(f"--- rifaccio la catena per applicare: {cosa}")
        self.stato("riavvio in corso", self.tavolozza.ambra)
        self.ferma()
        # Si riparte al giro dopo, cosi' `ferma()` ha finito di svuotare la coda
        # e il log dice le cose nell'ordine in cui sono successe.
        QTimer.singleShot(400, self.avvia)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.ui_qt", description="livedub, finestra Qt")
    ap.add_argument("--profile", default=None)
    # I dispositivi e il modo di catturare: non stanno in `Config` perche' non
    # sono del gioco ne' del setup salvato in un profilo, sono di questa macchina.
    ap.add_argument("--loopback", default="voicemeeter")
    ap.add_argument("--output", default=None)
    ap.add_argument("--block", type=int, default=480)
    ap.add_argument("--backend", default="auto")
    ap.add_argument("--monitor", type=int, default=1)
    ap.add_argument("--tts", default=None)
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--avvia", action="store_true",
                    help="parte subito, senza aspettare il tasto (l'area e' quella del profilo)")
    ap.add_argument("--overlay-catturabile", action="store_true",
                    help="l'overlay entra negli screenshot: serve solo a fotografarlo")
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    args = ap.parse_args(argv)

    cfg, da_dove = preferenze.riprendi(args.profile, args.overrides)
    if args.tts:
        cfg.tts.backend = args.tts

    app = QApplication.instance() or QApplication(sys.argv[:1])
    # **Fusion, e non lo stile nativo.** Una base neutra e uguale su ogni
    # macchina: lo stile di Windows non si lascia vestire del tutto da un foglio
    # di stile, e cio' che resta suo cambia da un PC all'altro.
    app.setStyle("Fusion")
    app.setApplicationName(NOME)
    app.setApplicationVersion(VERSIONE)
    ico = tema.icona()
    if ico is not None:
        app.setWindowIcon(QIcon(str(ico)))
    # Il carattere dell'interfaccia con il suo ripiego: `Segoe UI Variable` c'e'
    # su Windows 11, e dove non c'e' si scende a `Segoe UI` invece di prendere il
    # ripiego di Qt, che e' un altro carattere in un'altra taglia.
    if tema.UI not in QFontDatabase.families():
        app.setFont(QFont(tema.UI_RIPIEGO, tema.C_TESTO))

    finestra = Finestra(cfg, args)
    finestra.scrivi(f"configurazione: {da_dove}")

    # **Niente esce di scena in silenzio.** Un'eccezione dentro un callback di Qt
    # stampa su una console che nell'eseguibile non esiste, e la finestra resta
    # li' come se niente fosse: peggio di un crash, perche' si continua a usarla
    # credendo che funzioni.
    def al_guasto(tipo, valore, testo):
        try:
            finestra._guaio(f"{tipo.__name__}: {valore}")
            DialogoCrash(
                finestra, tipo.__name__, str(valore),
                f"{testo}\n\nRegistro: {registro.percorso()}",
            ).exec()
        except Exception:
            pass

    registro.cattura_eccezioni(al_guasto)
    finestra.show()
    if args.avvia:
        # Comodo per riprovare la stessa cosa dieci volte di fila: l'area e'
        # quella del profilo, che se non e' quella giusta si ridisegna dopo.
        QTimer.singleShot(300, finestra.avvia)
    esito = app.exec()
    # L'ultima configurazione usata si ritrova: non e' un salvataggio con un
    # nome, serve solo a non perdere quello che si stava facendo. La rilegge
    # `configurazione()` al prossimo avvio — che e' la meta' che mancava.
    try:
        cfg.save(preferenze.ultima())
    except Exception:
        pass
    return esito


if __name__ == "__main__":
    raise SystemExit(main())
