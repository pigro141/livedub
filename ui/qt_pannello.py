"""Il pannello delle impostazioni, in Qt, generato percorrendo l'albero.

Stessa idea della versione Tk — le manopole nascono da `core.schema.campi()` e
non da un elenco scritto a mano — e le stesse tre regole, che non dipendono dal
toolkit:

1. **la spiegazione e' quella scritta in `core/config.py`**, misure comprese;
2. **cio' che si legge solo all'avvio lo dichiara**, invece di fingere;
3. **quel che si vede e' quel che si usa**: dopo aver scritto si rilegge da
   config, cosi' una conversione o un rifiuto si vedono subito.

Quello che cambia col motore e' solo quanto costa farlo bello: in Tk gli angoli
tondi erano dieci immagini generate e tre giri di prove, qui sono una riga di
foglio di stile.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.schema import (
    LIVELLI,
    TITOLI,
    Campo,
    campi,
    fuori_scala,
    livello,
    visibile_a,
)
from ui import qt_tema as tema


class Pannello(QWidget):
    """Le impostazioni, raggruppate per sezione, con la loro spiegazione."""

    def __init__(
        self,
        cfg,
        *,
        al_cambio: Callable[[Campo, Any], None] | None = None,
        solo: tuple[str, ...] = (),
        cerca: bool = True,
        intestazione: str = "",
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.al_cambio = al_cambio
        self.solo = tuple(solo)
        self._campi: dict[str, Campo] = {}
        self._widget: dict[str, QWidget] = {}
        self._righe: list[tuple[Campo, QWidget]] = []
        self._titoli: list[tuple[str, QWidget]] = []

        fuori = QVBoxLayout(self)
        fuori.setContentsMargins(0, 0, 0, 0)
        fuori.setSpacing(tema.S2)

        if intestazione:
            nota = QLabel(intestazione)
            nota.setObjectName("tenue")
            nota.setWordWrap(True)
            fuori.addWidget(nota)

        if cerca:
            barra = QHBoxLayout()
            barra.setSpacing(tema.S3)
            self.casella = QLineEdit()
            self.casella.setPlaceholderText("Cerca fra i parametri…")
            self.casella.textChanged.connect(self._filtra)
            barra.addWidget(self.casella, 1)
            # **I tre livelli, che sono la correzione piu' importante di questo
            # pannello.** Centosessantasei manopole sono la risposta giusta a una
            # domanda che quasi nessuno fa: chi apre il programma la prima volta
            # vuole sentire il doppiaggio, non tarare `merge_similarity`.
            # Mostrarle tutte allo stesso modo non e' neutrale, e' scegliere
            # l'ultimo dei tre utenti e far pagare agli altri due.
            barra.addWidget(QLabel("mostra"))
            self.v_livello = QComboBox()
            self.v_livello.addItems(["l'essenziale", "le principali", "tutto"])
            self.v_livello.setToolTip(
                "l'essenziale: le dieci che servono per far funzionare il programma\n"
                "le principali: piu' lettura, chi parla e tempi\n"
                "tutto: tutti i parametri, compresi quelli di taratura"
            )
            self.v_livello.currentIndexChanged.connect(self._filtra)
            self.v_livello.setFixedWidth(140)
            barra.addWidget(self.v_livello)
            self.solo_caldi = QCheckBox("solo a caldo")
            self.solo_caldi.setToolTip("Nascondi i parametri che si leggono solo all'avvio")
            self.solo_caldi.toggled.connect(self._filtra)
            barra.addWidget(self.solo_caldi)
            azzera = QPushButton("Riporta ai default")
            azzera.clicked.connect(self.ripristina)
            barra.addWidget(azzera)
            fuori.addLayout(barra)

        self.stato = QLabel("")
        self.stato.setObjectName("tenue")
        fuori.addWidget(self.stato)

        area = QScrollArea()
        area.setWidgetResizable(True)
        dentro = QWidget()
        dentro.setObjectName("pannello")
        self.corpo = QVBoxLayout(dentro)
        self.corpo.setContentsMargins(tema.S4, tema.S3, tema.S4, tema.S4)
        self.corpo.setSpacing(1)
        area.setWidget(dentro)
        fuori.addWidget(area, 1)

        self._costruisci()
        self.corpo.addStretch(1)
        self._filtra()

    # -- costruzione -------------------------------------------------------

    def _costruisci(self) -> None:
        sezione = None
        for campo in campi(self.cfg):
            if self.solo and campo.percorso not in self.solo:
                continue
            if campo.sezione != sezione:
                sezione = campo.sezione
                titolo = QLabel(TITOLI.get(sezione, sezione).upper())
                titolo.setObjectName("sezione")
                titolo.setContentsMargins(0, tema.S5, 0, tema.S1)
                self.corpo.addWidget(titolo)
                self._titoli.append((sezione, titolo))
            self.corpo.addWidget(self._riga(campo))

    def _riga(self, campo: Campo) -> QWidget:
        riga = QFrame()
        riga.setObjectName("riga")
        L = QHBoxLayout(riga)
        L.setContentsMargins(tema.S2, tema.S1, tema.S2, tema.S1)
        L.setSpacing(tema.S3)

        nome = QLabel(campo.nome)
        nome.setObjectName("nomeCampo")
        nome.setFixedWidth(216)
        nome.setToolTip(campo.percorso)
        L.addWidget(nome)

        w = self._manopola(campo)
        w.setFixedWidth(196)
        # **Il nome accessibile e' il percorso del campo, non «casella».** Uno
        # screen reader legge il nome, e trenta caselle di spunta chiamate tutte
        # allo stesso modo non sono navigabili: e' l'unica cosa che le distingue.
        # La descrizione porta la spiegazione vera, cioe' lo stesso testo che
        # l'occhio vede accanto alla manopola.
        w.setAccessibleName(campo.percorso)
        w.setAccessibleDescription(
            (campo.sommario or "nessuna spiegazione scritta")
            + ("" if campo.caldo else " — si legge solo all'avvio")
        )
        # **Le caselle di spunta si allineano con le altre manopole.** Senza, una
        # riga booleana sembrava rientrata rispetto a quella sopra, e la colonna
        # dei valori si spezzava a ogni booleano — che in questo albero sono
        # trenta. Un allineamento rotto trenta volte non e' una rifinitura.
        if isinstance(w, QCheckBox):
            guscio = QWidget()
            G = QHBoxLayout(guscio)
            G.setContentsMargins(0, 0, 0, 0)
            G.addWidget(w)
            G.addStretch(1)
            guscio.setFixedWidth(196)
            L.addWidget(guscio)
        else:
            L.addWidget(w)
        self._widget[campo.percorso] = w
        self._campi[campo.percorso] = campo

        if not campo.caldo:
            marchio = QLabel("all’avvio")
            marchio.setObjectName("avviso")
            marchio.setToolTip(
                "Questo parametro si legge una volta sola quando la catena parte.\n"
                "Cambiandolo a sessione accesa comparira' la striscia per applicarlo."
            )
            L.addWidget(marchio)
        if not campo.modificabile:
            spento = QLabel("non modificabile")
            spento.setObjectName("spento")
            L.addWidget(spento)

        aiuto = QPushButton("ⓘ")
        aiuto.setObjectName("aiuto")
        aiuto.setCursor(Qt.PointingHandCursor)
        aiuto.setToolTip("Cosa fa, quanto e' stato misurato, cosa si rischia a cambiarlo")
        aiuto.setAccessibleName(f"spiegazione di {campo.percorso}")
        aiuto.clicked.connect(lambda _=False, c=campo: self.spiega(c))
        L.addWidget(aiuto)

        if campo.sommario:
            desc = QLabel(_una_riga(campo.sommario))
            desc.setObjectName("tenue")
            L.addWidget(desc, 1)
        else:
            L.addStretch(1)

        self._righe.append((campo, riga))
        return riga

    def _manopola(self, campo: Campo) -> QWidget:
        if not campo.modificabile:
            w = QLineEdit(_testo(campo.valore))
            w.setEnabled(False)
            return w
        if campo.tipo == "bool":
            w = QCheckBox()
            w.setChecked(bool(campo.valore))
            w.toggled.connect(lambda _=False, c=campo: self.applica(c))
            return w
        if campo.scelte:
            w = QComboBox()
            w.addItems(list(campo.scelte))
            w.setCurrentText(str(campo.valore))
            w.currentTextChanged.connect(lambda _="", c=campo: self.applica(c))
            return w
        w = QLineEdit(_testo(campo.valore))
        # Si applica quando si e' finito di scrivere: a ogni tasto vorrebbe dire
        # applicare `1` mentre si sta digitando `12`.
        w.editingFinished.connect(lambda c=campo: self.applica(c))
        return w

    # -- applicare ---------------------------------------------------------

    def applica(self, campo: Campo) -> None:
        """Scrive in config e **rilegge quello che c'e' davvero**."""
        w = self._widget[campo.percorso]
        if isinstance(w, QCheckBox):
            grezzo: Any = w.isChecked()
        elif isinstance(w, QComboBox):
            grezzo = w.currentText()
        else:
            grezzo = w.text()
        # **Fuori scala si rifiuta e si dice, non si corregge di nascosto.**
        # `Config.set` controlla il tipo e non il senso: `capture.fps = -5` passa
        # e ferma la cattura, `decide_after_ms = 99999` passa e rende il
        # programma muto. Correggerlo in silenzio darebbe una sessione che gira
        # con un numero diverso da quello scritto, che e' il difetto contro cui
        # tutto questo pannello esiste.
        male = fuori_scala(campo.percorso, grezzo)
        if male:
            self._dillo(
                f"{campo.nome}: {male}. Resta {_testo(self.cfg.get(campo.percorso))}, "
                f"che e' quello in uso.", errore=True)
            self._rileggi(campo)
            return
        try:
            self.cfg.set(campo.percorso, grezzo)
        except (ValueError, TypeError, KeyError):
            atteso = {
                "int": "un numero intero", "float": "un numero",
                "bool": "vero o falso", "tuple": "dei numeri separati da virgola",
            }.get(campo.tipo, "un testo")
            self._dillo(
                f"{campo.nome}: qui ci va {atteso}. "
                f"Resta {_testo(self.cfg.get(campo.percorso))}, che e' quello in uso.",
                errore=True,
            )
            self._rileggi(campo)
            return
        self._rileggi(campo)
        vero = self.cfg.get(campo.percorso)
        self._dillo(f"{campo.percorso} = {_testo(vero)}")
        if self.al_cambio is not None:
            self.al_cambio(campo, vero)

    def _rileggi(self, campo: Campo) -> None:
        w = self._widget[campo.percorso]
        vero = self.cfg.get(campo.percorso)
        w.blockSignals(True)
        if isinstance(w, QCheckBox):
            w.setChecked(bool(vero))
        elif isinstance(w, QComboBox):
            w.setCurrentText(str(vero))
        else:
            w.setText(_testo(vero))
        w.blockSignals(False)

    def aggiorna(self) -> None:
        """Rilegge tutti i campi: due viste della stessa config non devono divergere."""
        for campo, _ in self._righe:
            self._rileggi(campo)

    def ripristina(self) -> None:
        n = 0
        for campo, _ in self._righe:
            if not campo.modificabile:
                continue
            if self.cfg.get(campo.percorso) != campo.default:
                self.cfg.set(campo.percorso, campo.default)
                n += 1
        self.aggiorna()
        self._dillo(f"riportati ai default {n} campi")

    # -- aiuto e filtro ----------------------------------------------------

    def spiega(self, campo: Campo) -> None:
        d = QDialog(self)
        d.setWindowTitle(campo.percorso)
        d.resize(820, 560)
        L = QVBoxLayout(d)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(0)

        testata = QWidget()
        testata.setObjectName("testata")
        T = QVBoxLayout(testata)
        T.setContentsMargins(18, 14, 18, 12)
        alto = QHBoxLayout()
        nome = QLabel(campo.percorso)
        nome.setStyleSheet(f'font-family: "{tema.MONO}"; font-size: 13pt; font-weight: 600;')
        alto.addWidget(nome)
        alto.addStretch(1)
        t = tema.attuale(QApplication.instance())
        quando = QLabel("si applica subito" if campo.caldo else "si legge solo all’avvio")
        quando.setStyleSheet(f"color: {t.verde if campo.caldo else t.ambra};")
        alto.addWidget(quando)
        T.addLayout(alto)
        dati = QLabel(
            f"adesso  {_testo(self.cfg.get(campo.percorso))}      "
            f"default  {_testo(campo.default)}      tipo  {campo.tipo}"
        )
        dati.setObjectName("mono")
        T.addWidget(dati)
        L.addWidget(testata)

        corpo = QTextEdit()
        corpo.setReadOnly(True)
        corpo.setPlainText(
            campo.aiuto
            or "Questo campo non ha ancora una spiegazione scritta in core/config.py.\n\n"
               "Non e' un dettaglio: vuol dire che nessuno ha ancora messo per iscritto "
               "cosa misura e cosa si rischia a cambiarlo. Cambialo con prudenza."
        )
        L.addWidget(corpo, 1)

        piede = QHBoxLayout()
        piede.setContentsMargins(18, 10, 18, 14)
        piede.addStretch(1)
        chiudi = QPushButton("Chiudi")
        chiudi.clicked.connect(d.accept)
        piede.addWidget(chiudi)
        L.addLayout(piede)
        d.exec()

    def _filtra(self) -> None:
        cerca = self.casella.text().strip().lower() if hasattr(self, "casella") else ""
        caldi = self.solo_caldi.isChecked() if hasattr(self, "solo_caldi") else False
        scelto = (LIVELLI[self.v_livello.currentIndex()]
                  if hasattr(self, "v_livello") else "esperto")
        visti = 0
        vive: set[str] = set()
        for campo, riga in self._righe:
            ok = True
            if not self.solo and not visibile_a(campo.percorso, scelto):
                ok = False
            if caldi and not campo.caldo:
                ok = False
            if cerca and cerca not in campo.percorso.lower() and cerca not in campo.aiuto.lower():
                ok = False
            riga.setVisible(ok)
            if ok:
                visti += 1
                vive.add(campo.sezione)
        # Un titolo di sezione senza campi sotto e' rumore.
        for sezione, titolo in self._titoli:
            titolo.setVisible(sezione in vive)
        # **Il conteggio dice anche quanto si sta nascondendo.** «12 parametri»
        # da solo fa credere che il programma ne abbia dodici; «12 di 166» dice
        # che c'e' altro e dove trovarlo, che e' la differenza fra semplificare e
        # nascondere.
        totale = len(self._righe)
        if visti == totale:
            self.stato.setText(f"{visti} parametri")
        else:
            self.stato.setText(f"{visti} parametri mostrati, {totale - visti} nascosti")

    def _dillo(self, testo: str, errore: bool = False) -> None:
        # **Il colore si chiede alla tavolozza viva, non a una costante.** Con
        # il tema che segue Windows, una costante scritta qui resterebbe quella
        # dello scuro anche a finestra chiara — cioe' rosso acceso su bianco, o
        # peggio, grigio chiaro su bianco: illeggibile proprio dove si scrive
        # perche' un valore e' stato rifiutato.
        t = tema.attuale(QApplication.instance())
        self.stato.setStyleSheet(f"color: {t.rosso if errore else t.testo_tenue};")
        self.stato.setText(testo)


def _testo(valore: Any) -> str:
    if isinstance(valore, tuple):
        return ", ".join(_testo(v) for v in valore)
    if isinstance(valore, float):
        return f"{valore:g}"
    if isinstance(valore, dict):
        return f"({len(valore)} voci)"
    return str(valore)


def _una_riga(testo: str, massimo: int = 120) -> str:
    pulito = " ".join(testo.replace("**", "").replace("`", "").split())
    return pulito if len(pulito) <= massimo else pulito[: massimo - 1] + "…"
