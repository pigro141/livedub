"""La finestra di livedub, in Qt.

    .\\.venv\\Scripts\\python.exe -m tools.ui_qt --profile gtav

**Perche' un secondo front-end e non una modifica del primo.** La finestra Tk
funziona ed e' verificata; questa la sostituira' quando avra' fatto tutto quello
che fa lei. Riscriverla dentro sarebbe stato il modo piu' rapido di restare con
nessuna delle due funzionante — e questo progetto ha gia' pagato per una strada
parallela che non ereditava le cure dell'altra, quindi le due convivono finche'
questa non e' pari.

**Cosa e' gia' pari**: le quattro schede, le impostazioni generate dall'albero
con la spiegazione presa da `core/config.py`, i selettori di tecnologia, le aree
multiple, la striscia delle modifiche in attesa, e il fatto che quel che si vede
sia sempre quel che si usa.

**Cosa manca, dichiarato**: premere Avvia. I due cicli — audio a 10 ms e video a
30 Hz — vivono dentro `tools/ui.py`, intrecciati con l'overlay che e' anch'esso
Tk. Spostarli qui vuol dire portare anche quello, ed e' il pezzo su cui questo
progetto ha trovato i difetti peggiori (il programma che leggeva se stesso, la
finestra dimensionata sul testo sbagliato): va portato con le stesse verifiche,
non di fretta. Finche' non e' fatto, **la finestra dal vivo resta `tools.ui`** e
questa lo dice a chiare lettere invece di offrire un bottone che non fa niente.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import preferenze, registro  # noqa: E402
from core.config import PROFILES_DIR, Config, load_profile  # noqa: E402
from core.versione import NOME, VERSIONE, scheda  # noqa: E402
from ui import qt_tema as tema  # noqa: E402
from ui.qt_pannello import Pannello  # noqa: E402
from vision.aree import Area, dividi, leggi, scrivi  # noqa: E402

# I quattordici percorsi che scelgono un motore. L'elenco e' di percorsi e non di
# valori: le **scelte** vengono dallo schema, cioe' dai commenti di
# `core/config.py`, quindi aggiungere un backend non richiede di toccare questo
# file.
TECNOLOGIE = (
    "vision.ocr_backend", "vision.ocr_device",
    "tts.backend", "tts.device", "tts.kokoro_weights", "tts.pool_size",
    "speaker.backend", "vad.backend", "emotion.backend",
    "translate.enabled", "translate.backend", "translate.source", "translate.target",
    "correct.backend",
)


def campi_di(cfg) -> list[str]:
    """I percorsi di tutti i campi, per copiare una config dentro un'altra."""
    from core.schema import campi

    return [c.percorso for c in campi(cfg) if c.modificabile]


class Finestra(QMainWindow):
    def __init__(self, cfg, args) -> None:
        super().__init__()
        self.cfg = cfg
        self.args = args
        self.in_sessione = False
        self._in_attesa: list[str] = []
        self._voci: dict[str, int] = {}

        self.setWindowTitle(f"{NOME} {VERSIONE}")
        # **La finestra si ricorda dov'era, e non esce dallo schermo.** Ripartire
        # sempre al centro a 1240x800 e' un fastidio su un monitor grande e un
        # guasto su uno da 1366x768, dove la finestra nasceva piu' alta dello
        # spazio disponibile. Si legge lo schermo vero e ci si sta dentro.
        self._pref = preferenze.leggi()
        schermo = QGuiApplication.primaryScreen().availableGeometry()
        largo = min(int(self._pref.get("larghezza", 1240)), schermo.width() - 40)
        alto = min(int(self._pref.get("altezza", 800)), schermo.height() - 60)
        self.setMinimumSize(900, 560)
        self.resize(max(900, largo), max(560, alto))
        if "x" in self._pref and "y" in self._pref:
            x, y = int(self._pref["x"]), int(self._pref["y"])
            if schermo.contains(x + 60, y + 30):  # lo schermo di ieri puo' non esserci piu'
                self.move(x, y)
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

        self.schede = QTabWidget()
        L.addWidget(self.schede, 1)
        contenitore = QWidget()
        C = QVBoxLayout(contenitore)
        C.setContentsMargins(tema.S3, tema.S3, tema.S3, tema.S3)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        # **Un tetto alle righe.** Senza, una sessione di tre ore se lo mangia
        # tutto: e' la domanda 23, e costa una riga.
        self.log.setMaximumBlockCount(5000)
        self.log.setFont(QFont(tema.MONO, 10))
        C.addWidget(self.log)
        self.schede.addTab(contenitore, "Sessione")

        self.p_tecnologie = Pannello(
            cfg, al_cambio=self._campo_cambiato, solo=TECNOLOGIE, cerca=False,
            intestazione="Quale motore usare per ogni stadio. Quasi tutti si leggono una "
                         "volta sola: cambiandoli a sessione accesa compare la striscia "
                         "per applicarli.",
        )
        self.schede.addTab(self._in_margine(self.p_tecnologie), "Tecnologie")
        self.schede.addTab(self._scheda_aree(), "Aree")
        self.p_avanzate = Pannello(cfg, al_cambio=self._campo_cambiato)
        self.schede.addTab(self._in_margine(self.p_avanzate), "Impostazioni avanzate")

        self._scorciatoie()
        self.schede.setCurrentIndex(int(self._pref.get("scheda", 0)))
        registro.apri()
        self.scrivi(scheda())
        self.scrivi("")
        self.scrivi("finestra Qt: impostazioni, tecnologie e aree sono complete.")
        self.scrivi("per doppiare dal vivo si usa ancora `python -m tools.ui` "
                    "(i due cicli e l'overlay non sono ancora portati qui).")

    # -- produzione: ricordare, salvare, non morire in silenzio -------------

    def _scorciatoie(self) -> None:
        """Le quattro che si usano davvero. Il resto lo fa Qt col Tab."""
        for tasti, cosa in (
            ("Ctrl+S", self.salva_profilo),
            ("Ctrl+O", self.apri_profilo),
            ("Ctrl+F", self._vai_a_cerca),
            ("Ctrl+L", self.copia_diagnostica),
            ("F1", self.chi_siamo),
        ):
            QShortcut(QKeySequence(tasti), self, activated=cosa)

    def _vai_a_cerca(self) -> None:
        self.schede.setCurrentIndex(3)
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
        self.c_colorati.setChecked(bool(self.cfg.vision.exclude_colored))
        self.s_sat.setValue(int(self.cfg.vision.sat_max))
        self.l_roi.setText(self._testo_roi())
        self._mostra_aree()
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

    def chi_siamo(self) -> None:
        QMessageBox.information(
            self, f"{NOME} {VERSIONE}",
            f"{scheda()}\n\nRegistro: {registro.percorso()}\n"
            f"Licenza: GPL-3.0-or-later (vedi LICENZE.md)",
        )

    def _guaio(self, testo: str) -> None:
        registro.scrivi(testo)
        self.scrivi("! " + testo)
        self.stato("guasto", self.tavolozza.rosso)

    def closeEvent(self, evento) -> None:
        """Chiudendo si ricorda dov'era la finestra e cosa si stava guardando."""
        g = self.geometry()
        preferenze.aggiorna(
            x=g.x(), y=g.y(), larghezza=g.width(), altezza=g.height(),
            scheda=self.schede.currentIndex(),
        )
        registro.scrivi("finestra chiusa")
        super().closeEvent(evento)

    def _tema_cambiato(self, *_a) -> None:
        """Windows e' passato da chiaro a scuro (o viceversa) mentre giocavamo."""
        nuova = tema.attuale(QApplication.instance())
        if nuova.nome == self.tavolozza.nome:
            return
        self.tavolozza = nuova
        self.setStyleSheet(tema.foglio(nuova))
        self.stato(self.l_stato.text(), self._colore_stato)
        self.scrivi(f"tema di sistema: {nuova.nome}")

    # -- pezzi della finestra ----------------------------------------------

    @staticmethod
    def _in_margine(w: QWidget) -> QWidget:
        fuori = QWidget()
        L = QVBoxLayout(fuori)
        L.setContentsMargins(tema.S3, tema.S3, tema.S3, tema.S3)
        L.addWidget(w)
        return fuori

    def _testata(self) -> QWidget:
        w = QWidget()
        w.setObjectName("testata")
        L = QHBoxLayout(w)
        L.setContentsMargins(tema.S5, tema.S3, tema.S5, tema.S3)
        L.setSpacing(tema.S3)
        nome = QLabel("livedub")
        nome.setObjectName("nomeApp")
        L.addWidget(nome)
        self.spia = QLabel()
        self._colore_stato = self.tavolozza.testo_fioco
        self.spia.setStyleSheet(tema.spia(self._colore_stato))
        L.addWidget(self.spia)
        self.l_stato = QLabel("fermo")
        self.l_stato.setObjectName("tenue")
        L.addWidget(self.l_stato)
        L.addStretch(1)
        self.l_bersaglio = QLabel("nessuna finestra scelta")
        self.l_bersaglio.setObjectName("tenue")
        L.addWidget(self.l_bersaglio)
        info = QPushButton("ⓘ")
        info.setObjectName("aiuto")
        info.setCursor(Qt.PointingHandCursor)
        info.setToolTip("Versione, sistema e provider (F1)")
        info.clicked.connect(self.chi_siamo)
        L.addWidget(info)
        return w

    def _barra(self) -> QWidget:
        w = QWidget()
        L = QHBoxLayout(w)
        L.setContentsMargins(tema.S5, tema.S3, tema.S5, tema.S2)
        L.setSpacing(tema.S2)
        for testo in ("Scegli finestra", "Seleziona area"):
            b = QPushButton(testo)
            b.setEnabled(False)
            b.setToolTip("Disponibile nella finestra dal vivo: python -m tools.ui")
            L.addWidget(b)
        self.b_avvia = QPushButton("Avvia")
        self.b_avvia.setObjectName("primario")
        self.b_avvia.setEnabled(False)
        self.b_avvia.setToolTip(
            "Non ancora portato in questa finestra: i due cicli e l'overlay vivono in\n"
            "tools/ui.py. Per doppiare dal vivo: python -m tools.ui"
        )
        L.addWidget(self.b_avvia)
        # **Un filo di separazione fra due cose diverse.** A sinistra ci sono le
        # *azioni* (scegli, avvia); a destra le *impostazioni della sessione*
        # (colore, soglia). Erano tutte in fila e si leggevano come un'unica
        # barra di comandi, quindi la casella sembrava un bottone che fa qualcosa
        # adesso invece di un interruttore che vale finche' non lo si cambia.
        L.addSpacing(tema.S4)
        filo = QWidget()
        filo.setObjectName("separatore")
        filo.setFixedWidth(1)
        L.addWidget(filo)
        L.addSpacing(tema.S4)

        self.c_colorati = QCheckBox("Ignora i sottotitoli colorati")
        self.c_colorati.setChecked(bool(self.cfg.vision.exclude_colored))
        self.c_colorati.toggled.connect(self._cambia_colorati)
        self.c_colorati.setToolTip(
            "Acceso: le righe con del testo colorato si buttano (l'HUD di GTA V).\n"
            "Spento: si leggono (i giochi che colorano il nome di chi parla)."
        )
        L.addWidget(self.c_colorati)
        L.addWidget(QLabel("soglia"))
        self.s_sat = QSpinBox()
        self.s_sat.setRange(0, 255)
        self.s_sat.setValue(int(self.cfg.vision.sat_max))
        self.s_sat.valueChanged.connect(self._cambia_sat)
        self.s_sat.setToolTip("Quanto acceso dev'essere un colore per contare come colore.")
        L.addWidget(self.s_sat)
        L.addStretch(1)
        self.l_roi = QLabel(self._testo_roi())
        self.l_roi.setObjectName("mono")
        L.addWidget(self.l_roi)
        self._aggiorna_sat()
        return w

    def _striscia(self) -> QWidget:
        self.striscia = QWidget()
        self.striscia.setObjectName("striscia")
        L = QHBoxLayout(self.striscia)
        L.setContentsMargins(tema.S4, tema.S2, tema.S2, tema.S2)
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

    def _scheda_aree(self) -> QWidget:
        w = QWidget()
        L = QVBoxLayout(w)
        L.setContentsMargins(tema.S3, tema.S3, tema.S3, tema.S3)
        nota = QLabel(
            "Piu' zone da leggere sullo stesso schermo. Se due si accavallano, la parte in "
            "comune viene letta una volta sola e resta a quella piu' in alto nell'elenco: "
            "leggerla due volte vorrebbe dire due voci sovrapposte. Le aree si applicano al "
            "prossimo avvio."
        )
        nota.setObjectName("tenue")
        nota.setWordWrap(True)
        L.addWidget(nota)

        corpo = QHBoxLayout()
        corpo.setSpacing(tema.S3)
        self.elenco_aree = QListWidget()
        corpo.addWidget(self.elenco_aree, 1)
        bottoni = QVBoxLayout()
        bottoni.setSpacing(tema.S2)
        for testo, modo in (("Aggiungi (testo + audio)", "testo_audio"),
                            ("Aggiungi (solo testo)", "testo")):
            b = QPushButton(testo)
            b.clicked.connect(lambda _=False, m=modo: self._aggiungi_area(m))
            bottoni.addWidget(b)
        b = QPushButton("Togli la selezionata")
        b.clicked.connect(self._togli_area)
        bottoni.addWidget(b)
        b = QPushButton("Svuota (torna alla ROI)")
        b.clicked.connect(lambda: self._scrivi_aree([]))
        bottoni.addWidget(b)
        bottoni.addStretch(1)
        corpo.addLayout(bottoni)
        L.addLayout(corpo, 1)
        self._mostra_aree()
        return w

    # -- comportamento ------------------------------------------------------

    def _testo_roi(self) -> str:
        x, y, w, h = self.cfg.vision.roi
        return f"ROI  x{x:.3f}  y{y:.3f}  w{w:.3f}  h{h:.3f}"

    def scrivi(self, testo: str) -> None:
        self.log.appendPlainText(testo)
        registro.scrivi(testo)

    def stato(self, testo: str, colore: str | None = None) -> None:
        self._colore_stato = colore or self.tavolozza.testo_fioco
        self.l_stato.setText(testo)
        self.spia.setStyleSheet(tema.spia(self._colore_stato))

    def _cambia_colorati(self, acceso: bool) -> None:
        self.cfg.vision.exclude_colored = bool(acceso)
        self._aggiorna_sat()
        self._riallinea()
        self.scrivi("sottotitoli colorati: " + ("ignorati (difesa dall'HUD accesa)" if acceso
                    else "letti (per i giochi che colorano il nome di chi parla)"))

    def _aggiorna_sat(self) -> None:
        self.s_sat.setEnabled(self.c_colorati.isChecked())

    def _cambia_sat(self, valore: int) -> None:
        if valore == int(self.cfg.vision.sat_max):
            return
        self.cfg.vision.sat_max = int(valore)
        self._riallinea()
        self.scrivi(f"soglia del colore: {valore} (sotto, una riga non e' colorata)")

    def _riallinea(self) -> None:
        for p in (getattr(self, "p_tecnologie", None), getattr(self, "p_avanzate", None)):
            if p is not None:
                p.aggiorna()

    def _campo_cambiato(self, campo, valore) -> None:
        self._riallinea()
        if campo.percorso == "vision.exclude_colored":
            self.c_colorati.setChecked(bool(valore))
        elif campo.percorso == "vision.sat_max":
            self.s_sat.setValue(int(valore))
        elif campo.percorso == "vision.roi":
            self.l_roi.setText(self._testo_roi())
        elif campo.percorso == "vision.aree":
            self._mostra_aree()
        if campo.caldo:
            self.scrivi(f"{campo.percorso} = {valore}")
        else:
            self.scrivi(f"{campo.percorso} = {valore}   (si legge solo all'avvio)")
            if self.in_sessione:
                self._segna_in_attesa(campo.percorso)

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
        cosa = ", ".join(self._in_attesa)
        self._in_attesa.clear()
        self._mostra_attesa()
        self.scrivi(f"--- rifaccio la catena per applicare: {cosa}")

    # -- aree ---------------------------------------------------------------

    def _mostra_aree(self) -> None:
        self.elenco_aree.clear()
        aree = leggi(self.cfg.vision.aree)
        if not aree:
            self.elenco_aree.addItem("(nessuna: si legge la ROI qui sopra, com'e' sempre stato)")
            return
        pezzi = dividi(aree)
        for i, a in enumerate(aree):
            suoi = [p for p in pezzi if p.area == i]
            intera = len(suoi) == 1 and suoi[0].roi == a.roi
            nota = "" if intera else f"   → {len(suoi)} pezzi, tolte le sovrapposizioni"
            x, y, w, h = a.roi
            modo = "testo + audio" if a.parla else "solo testo"
            self.elenco_aree.addItem(
                f"{i + 1}.   x{x:.3f} y{y:.3f} w{w:.3f} h{h:.3f}    {modo}{nota}"
            )

    def _aggiungi_area(self, modo: str) -> None:
        # Senza il selettore col mouse (che sta nella finestra dal vivo) si parte
        # dalla ROI: e' un punto di partenza vero, non un rettangolo inventato.
        aree = leggi(self.cfg.vision.aree)
        aree.append(Area(roi=tuple(self.cfg.vision.roi), modo=modo))
        self._scrivi_aree(aree)

    def _togli_area(self) -> None:
        riga = self.elenco_aree.currentRow()
        aree = leggi(self.cfg.vision.aree)
        if riga < 0 or riga >= len(aree):
            return
        del aree[riga]
        self._scrivi_aree(aree)

    def _scrivi_aree(self, aree) -> None:
        self.cfg.vision.aree = scrivi(aree)
        self._mostra_aree()
        self._riallinea()
        self.scrivi(f"aree: {len(aree)} dichiarate" if aree
                    else "aree: nessuna, si torna a leggere la ROI")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.ui_qt", description="livedub, finestra Qt")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    args = ap.parse_args(argv)

    cfg = (load_profile(args.profile, args.overrides) if args.profile
           else Config().apply(args.overrides))

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")  # base neutra: il resto lo fa il foglio di stile
    app.setApplicationName(NOME)
    app.setApplicationVersion(VERSIONE)

    finestra = Finestra(cfg, args)

    # **Niente esce di scena in silenzio.** Un'eccezione dentro un callback di Qt
    # stampa su una console che nell'eseguibile non esiste, e la finestra resta
    # li' come se niente fosse: peggio di un crash, perche' si continua a usarla
    # credendo che funzioni.
    def al_guasto(tipo, valore, testo):
        try:
            finestra._guaio(f"{tipo.__name__}: {valore}")
            QMessageBox.critical(
                finestra, "Guasto",
                f"{tipo.__name__}: {valore}\n\nIl dettaglio e' nel registro:\n"
                f"{registro.percorso()}",
            )
        except Exception:
            pass

    registro.cattura_eccezioni(al_guasto)
    finestra.show()
    esito = app.exec()
    # L'ultima configurazione usata si ritrova: non e' un salvataggio con un
    # nome, serve solo a non perdere quello che si stava facendo.
    try:
        cfg.save(PROFILES_DIR / "ultima.json")
    except Exception:
        pass
    return esito


if __name__ == "__main__":
    raise SystemExit(main())
