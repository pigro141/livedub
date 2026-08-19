"""L'audio: da dove arriva il gioco, dove esce la voce, e **come si prova**.

Era l'unica parte del programma che non stava nella finestra: si sceglieva con
`--loopback voicemeeter` sulla riga di comando, e chi apriva la finestra non
aveva modo ne' di sapere che esistesse ne' di cambiarla. Che e' il difetto
peggiore possibile su questo pezzo, perche' **l'audio e' cio' che viene prima**:
senza, non c'e' riconoscimento di chi parla, e il sintomo — tutte le battute con
la stessa voce — sembra un difetto del doppiaggio.

## Le tre strade, e perche' non sono equivalenti

Il programma **ascolta** un dispositivo di uscita (WASAPI in loopback: si sente
cio' che quel dispositivo sta suonando, senza cavi e senza microfoni) e **suona**
su un altro. Sono due percorsi, e la domanda vera e' se si toccano.

1. **Due schede diverse** — il gioco suona sugli altoparlanti, la voce esce dalle
   cuffie. Funziona senza installare niente, ed e' la strada per chi vuole
   provare adesso. Il prezzo e' che gioco e doppiaggio arrivano da due parti.
2. **Voicemeeter** — il gioco suona su una scheda *finta*, noi la ascoltiamo, e
   la voce esce sulle cuffie vere insieme al gioco. E' l'unica strada che rimette
   tutto in un paio di cuffie sole, e costa un'installazione.
3. **La stessa scheda da tutti e due i lati** — non e' una strada: il doppiaggio
   rientra nella cattura, viene ri-doppiato, e si ottiene un fischio. Il
   programma lo impedisce e dice perche'.

## La prova, che vale piu' della scelta

Scegliere il dispositivo giusto e' facile; **sapere di averlo scelto** no. Con
quello sbagliato non arriva nessun errore: arriva silenzio, e il silenzio somiglia
in tutto e per tutto a un doppiaggio che non funziona. Il bottone «Prova» ascolta
un secondo e mezzo e dice **quanto** ha sentito — che e' la differenza fra
diagnosticare in tre secondi e passare una serata a incolpare l'OCR.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from capture.audio import list_devices, nome_scheda, stesso_dispositivo, uscite
from ui import qt_tema as tema
from ui.lingua import MARCHIO
from ui.qt_controlli import allarga_tendina

SCARICA_VOICEMEETER = "https://vb-audio.com/Voicemeeter/"


class _Ascolto(QObject):
    """Ascolta un attimo il dispositivo scelto e dice quanto ha sentito."""

    fatto = Signal(float, str)

    def parti(self, device, secondi: float = 1.5) -> None:
        threading.Thread(target=self._lavora, args=(device, secondi), daemon=True).start()

    def _lavora(self, device, secondi: float) -> None:
        import numpy as np

        from capture.audio import Loopback

        try:
            picco = 0.0
            with Loopback(device, block=480, samplerate=48000) as ing:
                for _ in range(int(secondi * 100)):
                    blocco = ing.read()
                    if blocco is not None and len(blocco):
                        picco = max(picco, float(np.abs(np.asarray(blocco)).max()))
            self.fatto.emit(picco, "")
        except Exception as e:  # il device puo' essere occupato o sparito
            self.fatto.emit(0.0, f"{type(e).__name__}: {e}")


class Audio(QWidget):
    """Le due scelte, la guardia contro l'anello e la prova."""

    cambiato = Signal()

    def __init__(self, opzioni) -> None:
        super().__init__()
        self.opz = opzioni
        self._ascolto = _Ascolto()
        self._ascolto.fatto.connect(self._sentito)

        L = QVBoxLayout(self)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(tema.S2)

        griglia = QGridLayout()
        griglia.setHorizontalSpacing(tema.S3)
        griglia.setVerticalSpacing(tema.S2)

        griglia.addWidget(QLabel("L'audio del gioco arriva da"), 0, 0)
        self.entrata = QComboBox()
        # **I nomi dei dispositivi sono della macchina, non del programma.**
        # «Altoparlanti (Realtek USB2.0 Audio)» finirebbe fra le chiavi del
        # catalogo dell'interfaccia, cioe' l'estrazione darebbe un elenco
        # diverso su ogni PC — e tradotto sarebbe un dispositivo che non
        # esiste.
        self.entrata.setProperty(MARCHIO, True)
        self.entrata.setMinimumWidth(360)
        self.entrata.currentIndexChanged.connect(self._scelto)
        griglia.addWidget(self.entrata, 0, 1)
        self.b_prova = QPushButton("Prova")
        self.b_prova.setToolTip("Ascolta un secondo e mezzo e dice quanto ha sentito.\n"
                                "Fai suonare qualcosa nel gioco mentre premi.")
        self.b_prova.clicked.connect(self.prova)
        griglia.addWidget(self.b_prova, 0, 2)

        self.livello = QProgressBar()
        self.livello.setRange(0, 100)
        self.livello.setTextVisible(False)
        self.livello.setFixedHeight(6)
        # Si vede solo mentre si prova: a riposo era una riga sottile sotto
        # l'elenco, che sembrava un difetto del disegno invece di un misuratore.
        self.livello.setVisible(False)
        griglia.addWidget(self.livello, 1, 1)
        self.esito = QLabel("")
        self.esito.setObjectName("tenue")
        # Riga viva: «sento -32 dBFS», con dentro un numero.
        self.esito.setProperty(MARCHIO, True)
        griglia.addWidget(self.esito, 1, 2)

        griglia.addWidget(QLabel("La voce doppiata esce da"), 2, 0)
        self.uscita = QComboBox()
        self.uscita.setProperty(MARCHIO, True)
        self.uscita.setMinimumWidth(360)
        self.uscita.currentIndexChanged.connect(self._scelto)
        griglia.addWidget(self.uscita, 2, 1)
        aiuto = QPushButton("Non ho Voicemeeter")
        aiuto.setToolTip("Le tre strade per far sentire il gioco al programma")
        aiuto.clicked.connect(self.spiega)
        griglia.addWidget(aiuto, 2, 2)
        L.addLayout(griglia)

        self.avviso = QLabel("")
        self.avviso.setObjectName("errore")
        self.avviso.setWordWrap(True)
        self.avviso.setVisible(False)
        L.addWidget(self.avviso)

        self.aggiorna()

    # -- gli elenchi -------------------------------------------------------

    def aggiorna(self) -> None:
        """Rilegge i dispositivi: una cuffia si attacca a programma aperto."""
        try:
            loops, predefinita = list_devices()
            fuori = uscite()
        except Exception as e:
            self._dillo(f"non riesco a leggere le schede audio: {e}")
            return
        self.loops, self.fuori, self.predefinita = loops, fuori, predefinita

        self.entrata.blockSignals(True)
        self.entrata.clear()
        for d in loops:
            # **Quale sia quella giusta lo sa Windows, non l'utente.** La scheda
            # su cui Windows sta suonando adesso e' quella su cui suonera' il
            # gioco: dirlo qui evita la scelta a caso fra cinque nomi uguali.
            nota = ("  ← qui suona Windows adesso"
                    if predefinita is not None and stesso_dispositivo(d, predefinita) else "")
            virtuale = " (scheda finta: il gioco va mandato qui)" if _finta(d) else ""
            self.entrata.addItem(f"{_pulito(d.name)}{virtuale}{nota}")
        self.entrata.blockSignals(False)

        self.uscita.blockSignals(True)
        self.uscita.clear()
        for d in fuori:
            nota = ("  ← predefinita di Windows"
                    if predefinita is not None and stesso_dispositivo(d, predefinita) else "")
            self.uscita.addItem(f"{_pulito(d.name)}{nota}")
        self.uscita.blockSignals(False)

        # **Dopo aver riempito, non prima.** Queste due tendine nascono vuote e
        # si riempiono con le schede della macchina: la regola su quanto sono
        # larghe e quante voci se ne vedono va applicata quando le voci ci sono.
        # Su un PC con dodici schede audio e' l'unica cosa che tiene l'elenco
        # dentro lo schermo.
        allarga_tendina(self.entrata)
        allarga_tendina(self.uscita)

        self._preseleziona()
        self._controlla()

    def _preseleziona(self) -> None:
        """Quello scelto dalla riga di comando, o il piu' probabile."""
        ago = (self.opz.loopback or "").lower().strip()
        for i, d in enumerate(self.loops):
            if ago and ago in d.name.lower():
                self.entrata.setCurrentIndex(i)
                break
        else:
            # Nessuna corrispondenza: la scheda su cui Windows sta suonando e'
            # la scommessa giusta, non la prima dell'elenco.
            for i, d in enumerate(self.loops):
                if self.predefinita is not None and stesso_dispositivo(d, self.predefinita):
                    self.entrata.setCurrentIndex(i)
                    break
        ago = (self.opz.output or "").lower().strip()
        for i, d in enumerate(self.fuori):
            if ago and ago in d.name.lower():
                self.uscita.setCurrentIndex(i)
                break
        else:
            for i, d in enumerate(self.fuori):
                if self.predefinita is not None and stesso_dispositivo(d, self.predefinita):
                    self.uscita.setCurrentIndex(i)
                    break

    # -- cosa e' stato scelto ----------------------------------------------

    def scelta_entrata(self):
        i = self.entrata.currentIndex()
        return self.loops[i] if 0 <= i < len(self.loops) else None

    def scelta_uscita(self):
        i = self.uscita.currentIndex()
        return self.fuori[i] if 0 <= i < len(self.fuori) else None

    def valido(self) -> bool:
        a, b = self.scelta_entrata(), self.scelta_uscita()
        return a is not None and b is not None and not stesso_dispositivo(a, b)

    def _scelto(self, _i: int) -> None:
        self._controlla()
        # I nomi finiscono nelle opzioni del motore: e' li' che li legge chi
        # apre i flussi, e da li' finiscono nel rapporto della sessione.
        a, b = self.scelta_entrata(), self.scelta_uscita()
        if a is not None:
            self.opz.loopback = a.name
        if b is not None:
            self.opz.output = b.name
        self.cambiato.emit()

    def _controlla(self) -> None:
        a, b = self.scelta_entrata(), self.scelta_uscita()
        if a is None or b is None:
            self._dillo("non trovo le schede audio")
            return
        if stesso_dispositivo(a, b):
            self._dillo(
                f"Stessa scheda da tutti e due i lati ({_pulito(a.name)}): il doppiaggio "
                f"rientrerebbe nella cattura e verrebbe ri-doppiato — un fischio, non una "
                f"voce. Scegli un'altra uscita, oppure manda il gioco a Voicemeeter."
            )
            return
        self.avviso.setVisible(False)

    def _dillo(self, testo: str) -> None:
        self.avviso.setText("⚠  " + testo)
        self.avviso.setVisible(True)

    # -- la prova ----------------------------------------------------------

    def prova(self) -> None:
        d = self.scelta_entrata()
        if d is None:
            return
        self.b_prova.setEnabled(False)
        self.esito.setText("ascolto…")
        self.livello.setVisible(True)
        self.livello.setValue(0)
        self._ascolto.parti(d)

    def _sentito(self, picco: float, guasto: str) -> None:
        self.b_prova.setEnabled(True)
        if guasto:
            self.esito.setText("non si apre")
            self._dillo(f"quella scheda non si apre: {guasto}")
            return
        self.livello.setValue(int(min(1.0, picco) * 100))
        if picco < 0.001:
            # **Silenzio non vuol dire «rotto», e va detto cosi'.** Quasi sempre
            # vuol dire che il gioco sta suonando su un'altra scheda, oppure che
            # in quel momento non c'era suono.
            self.esito.setText("silenzio")
            self._dillo(
                "Da quella scheda non arriva niente. O il gioco sta suonando su un'altra "
                "(guarda quale ha il ← accanto), o in questo momento era muto: fai partire "
                "un suono e riprova."
            )
        else:
            self.esito.setText(f"sente ({picco:.2f})")
            self._controlla()

    # -- il tutorial -------------------------------------------------------

    def spiega(self) -> None:
        d = QDialog(self)
        d.setWindowTitle("Far sentire il gioco al programma")
        d.resize(760, 560)
        L = QVBoxLayout(d)
        testo = QTextBrowser()
        testo.setOpenExternalLinks(True)
        testo.setHtml(_TUTORIAL.format(scarica=SCARICA_VOICEMEETER))
        L.addWidget(testo, 1)
        piede = QHBoxLayout()
        piede.addStretch(1)
        b = QPushButton("Ho capito")
        b.setObjectName("primario")
        b.clicked.connect(d.accept)
        piede.addWidget(b)
        L.addLayout(piede)
        d.exec()


def _pulito(nome: str) -> str:
    return nome.replace("[Loopback]", "").strip()


def _finta(d) -> bool:
    """Una scheda virtuale (Voicemeeter, VB-Cable): il gioco va mandato li'."""
    n = nome_scheda(d)
    return any(marchio in n for marchio in ("voicemeeter", "vb-audio", "vb-cable", "virtual"))


_TUTORIAL = """
<style>
 body {{ font-family: 'Segoe UI'; line-height: 1.5; }}
 h3 {{ margin-bottom: 4px; }}
 code {{ font-family: Consolas; }}
 .ok {{ color: #43b581; }} .no {{ color: #e5534b; }}
</style>

<p>Il programma <b>ascolta</b> una scheda audio per sentire il gioco, e
<b>suona</b> su un'altra per farti sentire la voce doppiata. Non serve un
microfono e non serve nessun cavo: Windows sa far ascoltare cio' che una scheda
sta suonando.</p>

<p>La sola cosa che conta e' che le due <b>non siano la stessa scheda</b>. Se lo
fossero, la voce doppiata rientrerebbe nella cattura, verrebbe doppiata di nuovo,
e in due secondi avresti un fischio.</p>

<h3 class="ok">1. Senza installare niente — due schede diverse</h3>
<p>Se hai almeno due uscite (per esempio le cuffie <i>e</i> gli altoparlanti, o
l'audio del monitor via HDMI):</p>
<ol>
  <li>in Windows, manda l'audio del gioco su una delle due — <i>Impostazioni →
      Sistema → Audio → Volume app</i>, e scegli quella scheda per il gioco;</li>
  <li>qui sopra, <b>l'audio del gioco arriva da</b> = quella scheda;</li>
  <li><b>la voce doppiata esce da</b> = l'altra, quella che stai ascoltando.</li>
</ol>
<p>Funziona subito. Il difetto e' che il gioco e la voce arrivano da due parti
diverse, quindi va bene per provare, meno per giocare.</p>

<h3 class="ok">2. Con Voicemeeter — tutto nelle stesse cuffie</h3>
<p>Voicemeeter aggiunge una scheda audio <b>finta</b>. Il gioco ci suona dentro,
noi la ascoltiamo, e la voce doppiata esce sulle cuffie vere insieme al gioco:
e' l'unico modo per avere tutto in un paio di cuffie sole.</p>
<ol>
  <li>scarica e installa Voicemeeter (il primo, quello base, e' sufficiente):
      <a href="{scarica}">{scarica}</a>, poi riavvia il PC;</li>
  <li>in Voicemeeter, alla voce <b>A1</b> in alto a destra scegli le tue cuffie
      vere: e' li' che uscira' tutto;</li>
  <li>in Windows, imposta <b>Voicemeeter Input</b> come dispositivo di uscita
      predefinito (o solo per il gioco, da <i>Volume app</i>);</li>
  <li>qui sopra, <b>l'audio del gioco arriva da</b> = <code>Voicemeeter
      Input</code>, e <b>la voce doppiata esce da</b> = le tue cuffie.</li>
</ol>

<h3 class="no">3. Quello che non si puo' fare</h3>
<p>Scegliere la <b>stessa</b> scheda da tutti e due i lati. Il programma se ne
accorge e non parte: non e' una limitazione da aggirare, e' un anello di
reazione — la voce si sentirebbe rientrare, ri-doppiare e salire finche' non
resta che un fischio.</p>

<h3>Come si controlla di aver scelto giusto</h3>
<p>Con il bottone <b>Prova</b>. Fai suonare qualcosa nel gioco e premilo:
ascolta un secondo e mezzo e dice quanto ha sentito. Serve perche' con la scheda
sbagliata non arriva nessun errore — arriva <b>silenzio</b>, e il silenzio
somiglia in tutto e per tutto a un doppiaggio che non funziona.</p>
"""
