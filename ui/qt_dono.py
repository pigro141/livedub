"""Le donazioni, dalla parte che si vede: **una porta fissa e una domanda sola**.

## Cosa c'e' qui, e cosa non c'e'

Qui ci sono le parole e i due widget. L'indirizzo e la regola su quando si possa
chiedere stanno in `core/dono.py`, fuori da Qt, dove si provano senza aprire una
finestra — che e' la lezione piu' cara di questo repo.

## I due pezzi rispondono a due domande diverse

**Il cuore in testata** e' la *porta*: sta accanto al `?` e alla ⓘ, e' un cerchio
da 28 px senza fondo come loro, e non se ne va mai. Il glifo e non una parola
perche' `#aiuto` e' un cerchio, e in `ui/tutorial.py` c'e' gia' scritto che un
terzo bottone con dentro una parola romperebbe la fila. E' un cuore e non una
tazza di caffe' perche' `☕` su Windows lo disegna il carattere a **colori**:
sarebbe l'unica cosa colorata della testata, in mezzo a due glifi monocromatici,
cioe' un quarto colore d'interfaccia in un programma che ne dichiara uno solo.
Il colore glielo da' `#aiuto`, che e' menta come gli altri due: niente di nuovo.

**Il riquadro** e' la *domanda*, e si fa una volta sola. Compare quando la catena
si e' appena fermata — mai durante una sessione: interrompere un doppiaggio con
una richiesta di soldi e' il modo di far chiudere il programma — e non torna piu'
in nessun caso. Chiuderlo, aprire la pagina o premere il bottone che dice «Non
chiedermelo piu'» sono la stessa cosa, e sul bottone c'e' scritto esattamente
quello che succede.

## Il tono, che qui e' una scelta tecnica

Questo programma non mente mai a chi lo usa, e una richiesta di soldi e' il punto
in cui e' piu' facile cominciare. Quindi: nessun conto alla rovescia, nessuna
versione «pro», nessuna cifra suggerita, e il riquadro dice per prima cosa la
verita' piu' importante — che e' gratis, che e' GPL, e che continuera' a
funzionare identico senza pagare niente.

**E il bottone che porta alla pagina non e' il riempimento menta.** Quello e' di
Avvia, e vuol dire «e' questo che sei venuto a premere». Qui e' `#accento`,
contornato: si vede, si preme, e non finge di essere l'azione principale di
questa finestra.

## Le parole passano dai cataloghi, e qui e' l'unico modo

Un riquadro che non esiste finche' non lo si apre non lo trova nessuna
passeggiata (`ui/lingua.py`): senza `testi()` le sue frasi resterebbero in
italiano in mezzo a un programma tradotto — che e' peggio dell'italiano intero,
perche' sembra una parola che non si traduce invece di una che nessuno ha
tradotto.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from core import dono, preferenze
from ui import lingua, qt_tema as tema

# ============================================================== le parole =====

TITOLO = "Il programma e' gratis, e resta gratis"
# **La prima riga dice cosa non succede.** Prima di chiedere qualcosa va detto
# che non chiedere non costa niente, se no la frase dopo si legge come un
# ricatto gentile.
RIGHE: tuple[str, ...] = (
    "Lo hai usato per qualche sessione, quindi ha funzionato. Non c'e' niente da "
    "sbloccare, niente che scada e nessuna funzione tenuta da parte per chi paga: "
    "e' software libero (GPL), e continuera' a fare esattamente queste cose senza "
    "che tu paghi niente.",
    "Se ti va di lasciare qualcosa a chi lo scrive, la pagina e' qui sotto. "
    "Quanto lo decidi tu, e non dare niente va benissimo.",
    # **«in testata» non si traduce, «in cima alla finestra» si'.** Provato coi
    # cataloghi veri: la prima forma e' tornata «The heart on the head» in
    # inglese e «Das Herz auf dem Kopf» in tedesco — la testata di una pagina
    # letta come la testa di una persona. E' la stessa lezione di `uk —
    # Ucraino` diventato «Regno Unito»: una parola che in italiano ha due sensi
    # non si disambigua da sola in quarantuno lingue, e il difetto non da'
    # nessun errore.
    "In ogni caso non te lo chiedo piu': questo riquadro compare una volta sola. "
    "Il cuore in cima alla finestra resta dov'e', se un giorno cambi idea.",
)
APRI = "Apri la pagina delle donazioni"
# **Il bottone che chiude dice cosa fa il chiudere.** «Chiudi» sarebbe vero e
# non direbbe la cosa che interessa a chi lo preme: che questo non torna. E'
# anche l'unica forma in cui «non chiedermelo piu'» puo' non essere una bugia —
# vale per qualunque modo di chiudere il riquadro, X compresa.
BASTA = "Non chiedermelo piu'"
# Il suggerimento del cuore in testata. Questo la passeggiata normale lo trova
# da sola — il bottone vive nella finestra, non in questo riquadro — quindi
# **non** sta in `testi()`, come `ui.tutorial.RIAPRI`.
SUGGERIMENTO = "Offri qualcosa a chi lo scrive: il programma e' gratis e resta gratis"

# Il glifo del bottone in testata. Si veda la testata del file per il perche' non
# e' una tazza di caffe'.
#
# **Vuoto e non pieno, e la differenza si e' vista solo guardandola.** Con `♥` la
# fila esce con due glifi sottili (`?` e `ⓘ`, che e' un contorno) e una macchia
# piena in mezzo: stessa taglia, stesso colore, peso diverso. `♡` ha lo stesso
# tratto degli altri due, e la fila torna a leggersi come un oggetto solo.
# Nessuna misura poteva dirlo — sono tutte misure di *quanto*, e lo sbaglio era
# di *peso*: e' la stessa ragione per cui `tools/scatta.py` esiste.
GLIFO = "♡"


def testi() -> tuple[str, ...]:
    """Tutto quello che questo riquadro dice. Per `ui.lingua.fuori_dalla_passeggiata`."""
    return (TITOLO, *RIGHE, APRI, BASTA)


# ============================================================== la porta ======


def apri_pagina() -> None:
    """Apre la pagina delle donazioni nel browser.

    **Un posto solo**, e ci passano tutti e tre i punti da cui si arriva li': il
    cuore in testata, questo riquadro e l'ultimo passo della guida. L'indirizzo
    non e' scritto qui: sta in `core.dono.LINK`, che e' l'unica riga del codice
    in cui compare.
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl(dono.LINK))


def bottone(padre) -> QPushButton:
    """Il cuore in testata, gia' vestito. **Non si nasconde mai.**

    Non dipende da nessuno dei contatori: chi ha risposto «non chiedermelo piu'»
    ha chiesto di non essere interrotto, non di non poter piu' donare. Un bottone
    che compare e sparisce a seconda di quanto hai usato il programma sarebbe
    esattamente il genere di cosa che questo file esiste per non fare.
    """
    b = QPushButton(GLIFO, padre)
    b.setObjectName("aiuto")
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(SUGGERIMENTO)
    b.setAccessibleName(SUGGERIMENTO)
    b.clicked.connect(apri_pagina)
    return b


# ============================================================== il riquadro ===


class DialogoDono(QDialog):
    """La domanda, una volta sola. Si apre con `forse_chiedi()`.

    **Chiudere in qualunque modo vale come risposta**, e vale per sempre: e'
    quello che c'e' scritto sul bottone. La riga che lo segna sta in `_finito`,
    che passa da `closeEvent` (la X) e dai due bottoni — e **non** da `reject()`
    chiamata da fuori, che e' come `tools/scatta.py` fotografa il riquadro senza
    rispondere al posto di chi lo usa.
    """

    # Stessa larghezza del riquadro d'installazione: due finestre d'aiuto della
    # stessa taglia si leggono come lo stesso oggetto.
    LARGO = tema.MAX_CONTENUTO // 2 + tema.S7

    def __init__(self, cfg, padre=None) -> None:
        super().__init__(padre)
        self.cfg = cfg
        self.risposto = False

        self.setWindowTitle(TITOLO)
        self.setModal(True)
        # Senza padre — le schermate — il foglio di stile non scende fin qui da
        # solo, e il riquadro uscirebbe coi colori di serie di Qt: cioe' una
        # fotografia che non puo' mostrare il difetto che si sta cercando.
        if padre is None:
            from PySide6.QtWidgets import QApplication

            self.setStyleSheet(tema.foglio(tema.attuale(QApplication.instance())))

        L = QVBoxLayout(self)
        L.setContentsMargins(tema.S5, tema.S5, tema.S5, tema.S5)
        L.setSpacing(tema.S3)

        titolo = QLabel(TITOLO)
        titolo.setObjectName("titoloPasso")
        titolo.setWordWrap(True)
        L.addWidget(titolo)

        for riga in RIGHE:
            eti = QLabel(riga)
            eti.setWordWrap(True)
            L.addWidget(eti)

        L.addStretch(1)

        piede = QHBoxLayout()
        piede.setSpacing(tema.S3)
        piede.addStretch(1)
        self.b_basta = QPushButton(BASTA)
        self.b_basta.setCursor(Qt.PointingHandCursor)
        self.b_basta.clicked.connect(self._chiudi)
        piede.addWidget(self.b_basta)
        # `#accento` e non `#primario`: si veda la testata del file.
        self.b_apri = QPushButton(APRI)
        self.b_apri.setObjectName("accento")
        self.b_apri.setCursor(Qt.PointingHandCursor)
        self.b_apri.clicked.connect(self._apri)
        piede.addWidget(self.b_apri)
        L.addLayout(piede)

        self.setMinimumWidth(self.LARGO)
        lingua.applica(self, cfg.ui.lingua)

    def _finito(self) -> None:
        """Segna che la domanda e' stata fatta. Idempotente: si passa di qui due volte.

        Premendo un bottone si passa da `_chiudi` e poi da `closeEvent`, che Qt
        manda quando il dialogo si chiude davvero.
        """
        if self.risposto:
            return
        self.risposto = True
        preferenze.dono_chiesto()

    def _chiudi(self) -> None:
        self._finito()
        self.accept()

    def _apri(self) -> None:
        """Aprire la pagina e' una risposta anche lei, e chiude il riquadro.

        Lasciarlo aperto dietro al browser vorrebbe dire ritrovarselo davanti al
        ritorno, cioe' chiedere due volte a chi ha appena detto di si'.
        """
        apri_pagina()
        self._chiudi()

    def closeEvent(self, evento) -> None:  # noqa: N802 (nome imposto da Qt)
        self._finito()
        super().closeEvent(evento)


def forse_chiedi(cfg, padre=None) -> bool:
    """Apre il riquadro **se e' il momento**. Torna se l'ha aperto.

    Due guardie, e nessuna delle due e' prudenza generica:

    - **la regola** (`core.dono.da_chiedere`) dice se il programma ha gia'
      servito abbastanza e se non si e' gia' chiesto. Sta fuori da qui apposta;
    - **c'e' qualcuno a guardare** (`isVisible`), che e' la condizione vera e non
      l'attributo dichiarato: in questo progetto la guardia scritta come
      «costruita e dichiarata fuori schermo» non copriva «costruita e mai
      mostrata», ed e' cosi' che un modale ha tenuto la suite appesa dieci minuti
      senza stampare una riga.
    """
    if padre is None or not padre.isVisible():
        return False
    if not preferenze.dono_da_chiedere():
        return False
    DialogoDono(cfg, padre).exec()
    return True
