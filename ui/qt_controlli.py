"""Le manopole: **una per significato**, non una per tipo Python.

Il pannello delle impostazioni nasceva percorrendo l'albero di config e sceglieva
il controllo guardando il *tipo*: booleano -> casella, elenco dichiarato nel
commento -> menu, **tutto il resto -> campo di testo**. Il risultato, guardato a
schermo, e' la ragione per cui questo file esiste:

    roi          [ 0.204, 0.8843, 0.592, 0.07 ]
    duck_db      [ -14 ]
    source       [ auto ]
    color        [ ]

Quattro campi di testo per quattro cose che nessuno puo' digitare: un rettangolo
si tira col mouse, un guadagno si cerca a orecchio, una lingua si sceglie da un
elenco, un colore si prende da una tavolozza. Un campo di testo per un valore che
l'utente non puo' conoscere non e' una manopola neutra: **e' un invito a
sbagliare**, e in questo progetto sbagliare vuol dire una sessione che gira con
una configurazione diversa da quella che si crede.

La regola, function by function: **il controllo dice cosa e' lecito**. Un cursore
dice «fra questo e questo, e in mezzo c'e' tutto»; un elenco dice «questi e basta
questi»; una casella dice «si' o no». Un campo di testo non dice niente, e va
tenuto solo per le cose che sono davvero testo — un nome di modello, un percorso.

**E la rotellina non tocca niente.** Passando il mouse sopra un elenco a discesa
mentre si scorre la pagina, Qt di serie cambia il valore: si scende di tre righe
e si e' cambiato il motore di sintesi senza saperlo. E' il difetto piu' grave di
tutti perche' non lascia traccia — la finestra mostra il valore nuovo, e sembra
che l'abbia scelto l'utente.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    Property,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui import qt_tema as tema
from ui.lingua import MARCHIO

# --------------------------------------------------------- la rotellina ------


class _Rotella(QObject):
    """Scorre la pagina, non il valore.

    Qt manda la rotellina al controllo sotto il puntatore anche quando non ha il
    fuoco: scorrendo un elenco di impostazioni si cambiano i valori che si
    attraversano. L'evento si intercetta e si **passa all'area scorrevole**, cosi'
    la pagina scorre come ci si aspetta e il controllo resta com'era.

    Chi vuole davvero cambiarlo con la rotellina ci clicca sopra prima: col fuoco
    l'evento passa. E' la stessa convenzione dei browser.
    """

    def eventFilter(self, oggetto, evento):  # noqa: N802 (nome imposto da Qt)
        if evento.type() != QEvent.Wheel or oggetto.hasFocus():
            return False
        area = oggetto
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if area is not None:
            QApplication.sendEvent(area.viewport(), evento)
        return True


_ROTELLA = _Rotella()


def blocca_rotella(w: QWidget) -> QWidget:
    """Applica il filtro a un controllo e a tutti i suoi figli."""
    for bersaglio in [w, *w.findChildren(QWidget)]:
        if isinstance(bersaglio, (QComboBox, QSpinBox, QDoubleSpinBox, QSlider)):
            bersaglio.setFocusPolicy(Qt.StrongFocus)
            bersaglio.installEventFilter(_ROTELLA)
    return w


# ------------------------------------------------- la tendina che si apre ----


class _Tendina(QObject):
    """Rimisura la tendina **quando le cambia il carattere sotto**.

    E' la meta' che mancava, ed e' un errore di *quando* e non di *quanto*.
    `allarga_tendina` misurava alla costruzione: li' il controllo non e' ancora
    figlio della finestra, quindi non ha addosso il foglio di stile e porta il
    carattere di serie di Qt — 9 punti invece dei 10 del tema. Misurato su
    `tts.backend`: 278 px chiesti contro i **323** che poi servono davvero, e
    `tone — un bip al posto della voce, per sentire i tempi` esce come
    `…per sentire i tem`. Con `ElideNone` non ci sono nemmeno i puntini a dire
    che manca qualcosa: la frase finisce a meta' parola e sembra scritta cosi'.

    **E non si rimisura all'apertura**, che sembrava il momento giusto e non lo
    e': misurato con un cronometro sugli eventi, `showPopup` fissa la geometria
    a +0,7 ms e il `Show` arriva a **+156**, perche' Qt apre la tendina con una
    dissolvenza. Allargarla li' vuol dire far comparire l'elenco stretto e
    poi vederlo saltare — e la fotografia della dissolvenza e' quella di prima.
    Il carattere invece cambia una volta, quando il controllo entra nella
    finestra vestita, ed e' li' che si rifanno i conti.
    """

    QUANDO = (QEvent.FontChange, QEvent.StyleChange, QEvent.Polish)

    def eventFilter(self, oggetto, evento):  # noqa: N802 (nome imposto da Qt)
        if evento.type() in self.QUANDO and isinstance(oggetto, QComboBox):
            _misura_tendina(oggetto)
        return False


_TENDINA = _Tendina()


def _misura_tendina(combo: QComboBox) -> None:
    """Larghezza dell'elenco aperto: quella della voce piu' lunga.

    **Il carattere piu' largo fra i due**, non quello dell'elenco e basta: la
    vista prende il suo dal foglio di stile solo quando la si apre — cioe' dopo
    che questa misura serve — mentre il controllo ce l'ha appena entra nella
    finestra. Nel foglio di Menta sono lo stesso carattere; prendendo il
    massimo, il giorno in cui non lo saranno la tendina resta larga abbastanza
    invece di diventare stretta in silenzio.
    """
    vista = combo.view()
    m_vista = vista.fontMetrics()
    m_casella = combo.fontMetrics()
    largo = max((max(m_vista.horizontalAdvance(combo.itemText(i)),
                     m_casella.horizontalAdvance(combo.itemText(i)))
                 for i in range(combo.count())), default=0)
    # Il respiro e' l'imbottitura dell'elenco piu' la barra di scorrimento, che
    # compare quando le voci sono tante: senza, l'ultima lettera finisce sotto.
    voluto = largo + 2 * tema.S3 + 20
    # **E si chiede anche alla vista quanto le serve**, perche' un testo non si
    # misura sempre con un carattere solo: nel menu dei caratteri installati
    # ogni nome e' scritto **col proprio**, quindi «Segoe Script» e' largo
    # tutt'altro che i suoi dodici caratteri. Misurato, 356 px contro i 255 che
    # il conto qui sopra prevedeva.
    try:
        voluto = max(voluto, vista.sizeHintForColumn(0) + 2 * tema.S3 + 20)
    except Exception:  # una vista che non sa rispondere: resta il conto sopra
        pass
    # **Il minimo va anche alla finestrella che contiene l'elenco**, ed e' quello
    # che decide: quello della sola vista non ci arriva, e Qt apre la tendina
    # larga quanto il controllo. Piu' dello schermo non si chiede — a Qt il
    # compito di non farla uscire dal bordo, a noi quello di non chiedere
    # l'impossibile.
    schermo = QApplication.primaryScreen()
    if schermo is not None:
        voluto = min(voluto, schermo.availableGeometry().width())
    vista.setMinimumWidth(voluto)
    padre = vista.parentWidget()
    if padre is not None:
        padre.setMinimumWidth(voluto)


def allarga_tendina(combo: QComboBox) -> QComboBox:
    """La tendina che si apre: **larga quanto la voce piu' lunga, alta quanto serve**.

    *Larga*: di serie Qt apre il menu largo quanto il controllo e taglia il
    resto con dei puntini. Qui le voci sono `piper — svelto, gira ovunque
    (consigliato)` e `google — ⚠ manda i sottotitoli a Google`: la parte
    tagliata e' **proprio quella che dice cosa fa la scelta**, cioe' l'unica
    ragione per cui le etichette umane sono state scritte. Chiuso il menu resta
    stretto e si legge il solo nome, che li' basta.

    La misura non si fa qui ma **all'apertura**, per la ragione scritta in
    `_Tendina`: qui si misura lo stesso, cosi' la prima apertura non parte da
    zero, ma il numero che conta e' quello dell'ultimo momento.

    *Alta*: si vede tutto finche' le voci sono poche e si scorre quando sono
    tante, e il confine e' `tema.VOCI_TENDINA` — dove quel numero viene, e
    perche' 16 e non un altro, sta scritto accanto a lui. Il conto non lo fa
    questa funzione: qui si dichiara e basta, cosi' quarantatre lingue e cinque
    motori seguono la stessa regola invece di dipendere dallo spazio che c'e'
    sotto il controllo.

    **Chiama questa, non `setMaxVisibleItems`**: da sola non basta, perche' la
    proprieta' viene ignorata finche' il foglio di stile non dichiara
    `combobox-popup: 0` — e quella riga sta in `ui/qt_tema.py`, dove si vede.
    """
    combo.setMaxVisibleItems(tema.VOCI_TENDINA)
    combo.view().setTextElideMode(Qt.ElideNone)
    if not combo.property("tendina_misurata"):
        combo.setProperty("tendina_misurata", True)
        combo.installEventFilter(_TENDINA)
    _misura_tendina(combo)
    return combo


class Elidibile(QLabel):
    """Un'etichetta che si **accorcia** invece di allargare la finestra.

    Un `QLabel` chiede sempre la larghezza del suo testo intero, quindi una
    spiegazione di centoventi caratteri accanto a una manopola impone alla riga
    una larghezza minima che nessun ridimensionamento puo' togliere: le schede
    Voce, Traduzione e Tutte le impostazioni **sforavano** al minimo della
    finestra, e le etichette «all'avvio» e ⓘ finivano una sopra l'altra.

    Andare a capo non era la risposta: righe di parametro alte il doppio delle
    altre spezzano la colonna delle manopole, che e' cio' che rende leggibile
    quell'elenco. Si taglia con i puntini e il testo intero resta nel
    suggerimento — dove peraltro c'era gia' la spiegazione per esteso.
    """

    def __init__(self, testo: str = "") -> None:
        super().__init__()
        self._intero = testo
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(testo)

    def setText(self, testo: str) -> None:  # noqa: N802 (nome imposto da Qt)
        self._intero = testo
        if not self.toolTip():
            self.setToolTip(testo)
        super().setText(testo)
        self._taglia()

    def resizeEvent(self, evento) -> None:  # noqa: N802
        super().resizeEvent(evento)
        self._taglia()

    def _taglia(self) -> None:
        corto = self.fontMetrics().elidedText(
            self._intero, Qt.ElideRight, max(0, self.width()))
        if corto != super().text():
            super().setText(corto)


# ------------------------------------------------------ il caricamento -------


class BarraCarico(QWidget):
    """La barra menta del caricamento, nei **due modi che vogliono dire due cose**.

    `riempi(ms)` — si sa quanto dura: la barra cresce da zero a tutta la
    larghezza e arriva in fondo esattamente quando il lavoro e' finito. E' il
    caso del cambio di lingua, dove il lavoro e' misurato (596 stringhe in ~35 ms)
    e la durata la decidiamo noi.

    `scorre(ms)` — non si sa quanto dura: una barra corta va e torna. E' il caso
    dell'avvio della catena, dove il costo e' caricare un modello e dipende dal
    motore e dal disco. Una barra determinata che finisce e poi resta li' piena
    mentre non e' finito niente dice una cosa falsa; una che va e torna dice
    «sto lavorando» e non promette niente.

    **Il colore e' la menta e basta**, che in Menta vuol dire interazione e vita.
    Ambra e rosso sono stati, e un caricamento non e' uno stato: e' una cosa che
    sta succedendo.

    **E si ferma sempre.** Il documento dice che niente si muove in un angolo
    mentre il gioco gira: qui il movimento e' legato a una cosa che finisce — un
    velo di due decimi, o l'attesa fra Avvia e la prima riga di stato — e
    `ferma()` e' chiamata da chi l'ha accesa. Una girandola che nessuno spegne
    sarebbe esattamente la cosa vietata.
    """

    # Quanto della larghezza occupa la barretta che va e torna. Piu' corta
    # sembra un puntino che rimbalza, piu' lunga non si capisce che si muove.
    PARTE = 0.28

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(4)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # Non c'e' niente da tradurre qui dentro, e la passeggiata dei cataloghi
        # non deve nemmeno provarci.
        self.setProperty(MARCHIO, True)
        self._t = 0.0
        self._pieno = True
        self._binario = tema.SCURA.superficie_alta
        self._anim = None

    # -- il tema -----------------------------------------------------------

    def veste(self, tavolozza) -> None:
        """Il binario cambia col tema; la menta no, ed e' il punto di `MENTA`."""
        self._binario = tavolozza.superficie_alta
        self.update()

    # -- la proprieta' animata ---------------------------------------------

    def _leggi(self) -> float:
        return self._t

    def _scrivi(self, v: float) -> None:
        self._t = float(v)
        self.update()

    avanzamento = Property(float, _leggi, _scrivi)

    # -- accendere e spegnere ----------------------------------------------

    def riempi(self, ms: int) -> None:
        """Da vuota a piena in `ms`, una volta sola."""
        self._parti(ms, pieno=True, giri=1, curva=QEasingCurve.InOutCubic)

    def scorre(self, ms: int = 1100) -> None:
        """Va e torna finche' non la si ferma, un giro ogni `ms`."""
        self._parti(ms, pieno=False, giri=-1, curva=QEasingCurve.InOutSine)

    def _parti(self, ms: int, *, pieno: bool, giri: int, curva) -> None:
        self.ferma()
        self._pieno = pieno
        self.setVisible(True)
        if ms <= 0:
            # Il sistema chiede meno movimento: si mostra il risultato, non il
            # viaggio. Una barra ferma a meta' sarebbe peggio di nessuna barra.
            self._scrivi(1.0 if pieno else 0.0)
            return
        self._anim = QPropertyAnimation(self, b"avanzamento", self)
        self._anim.setDuration(ms)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(curva)
        self._anim.setLoopCount(giri)
        self._anim.start()

    def ferma(self) -> None:
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        self.setVisible(False)

    def posa(self, t: float, *, pieno: bool = True) -> None:
        """La ferma a un punto preciso, **per fotografarla**.

        Un'animazione non si vede in uno screenshot, e in questo progetto un
        pezzo che nessuno ha guardato non e' «scritto», e' «supposto». Provare a
        prendere il fotogramma al volo con un `processEvents` darebbe
        un'immagine diversa a ogni giro e nessuna quando serve: qui il
        fotogramma si **sceglie**, e `tools/scatta.py` ne salva tre.
        """
        self.ferma()
        self._pieno = pieno
        self._t = float(t)
        self.setVisible(True)
        self.update()

    # -- il disegno ---------------------------------------------------------

    def paintEvent(self, _e) -> None:  # noqa: N802 (nome imposto da Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        largo, alto = self.width(), self.height()
        raggio = alto / 2.0
        p.setBrush(QColor(self._binario))
        p.drawRoundedRect(0, 0, largo, alto, raggio, raggio)
        p.setBrush(QColor(tema.MENTA))
        if self._pieno:
            p.drawRoundedRect(0, 0, max(alto, largo * self._t), alto, raggio, raggio)
            return
        # Va e torna senza scatti al giro: l'animazione va sempre da 0 a 1, e il
        # triangolo la ripiega. Un'animazione che torna indietro da sola
        # (`setDirection`) al riavvio del ciclo salta, e il salto si vede.
        u = 2.0 * self._t if self._t < 0.5 else 2.0 * (1.0 - self._t)
        corta = largo * self.PARTE
        p.drawRoundedRect(u * (largo - corta), 0, corta, alto, raggio, raggio)


class Velo(QWidget):
    """Il velo che copre un rifacimento dell'interfaccia, e **quanto dura**.

    Il cambio di lingua ripercorre l'albero dei widget e riscrive 596 stringhe:
    misurato, 32-43 ms secondo il catalogo. Non e' lento — e' **istantaneo**, ed
    e' proprio quello il difetto: a schermo la finestra cambia tutta insieme,
    senza che niente colleghi il prima al dopo, e si legge come uno scatto.

    Il velo mette un principio e una fine attorno a quel salto: entra, il lavoro
    si fa mentre non si vede niente, esce. `MS_CARICO` per parte, che e' la
    durata dichiarata per un controllo e non per un pannello: piu' lungo si
    aspetterebbe. Cronometrato con un ciclo di eventi vero, dal clic alla
    scomparsa passano **341 ms**, di cui 61 sono il rifacimento — cioe' l'unica
    parte che non si puo' accorciare.

    **Cosa vuol dire «non blocca».** Chi chiama `copri` torna subito e la finestra
    resta viva: il lavoro parte da un timer, dentro il giro degli eventi. I 35 ms
    del rifacimento vero restano sul thread dell'interfaccia e non possono
    andarsene — riscrivere un widget da un altro thread e' il modo piu' rapido di
    far cadere Qt — quindi il velo li **copre** invece di fingere di toglierli.

    E a sessione accesa non c'e' velo affatto: si veda `tema.durata_carico`.
    """

    def __init__(self, padre: QWidget) -> None:
        super().__init__(padre)
        self.setProperty(MARCHIO, True)
        self._fondo = tema.SCURA.superficie
        self._opacita = 1.0
        self.barra = BarraCarico()
        L = QVBoxLayout(self)
        L.addStretch(1)
        riga = QHBoxLayout()
        riga.addStretch(2)
        riga.addWidget(self.barra, 3)
        riga.addStretch(2)
        L.addLayout(riga)
        L.addStretch(1)
        self._anim = None
        self.hide()

    def veste(self, tavolozza) -> None:
        self._fondo = tavolozza.superficie
        self.barra.veste(tavolozza)

    # -- la proprieta' animata ---------------------------------------------

    def _leggi(self) -> float:
        return self._opacita

    def _scrivi(self, v: float) -> None:
        self._opacita = float(v)
        self.update()

    velatura = Property(float, _leggi, _scrivi)

    # -- l'unica cosa che si chiede da fuori --------------------------------

    def copri(self, meta_ms: int, lavoro) -> None:
        """Entra, fa `lavoro`, esce. `meta_ms = 0` fa solo il lavoro.

        **Il lavoro si fa comunque**, ed e' la meta' che si dimentica: un velo
        spento non deve voler dire una lingua che non cambia.
        """
        if meta_ms <= 0:
            lavoro()
            return
        padre = self.parentWidget()
        if padre is not None:
            self.setGeometry(padre.rect())
        self.show()
        self.raise_()
        self.barra.riempi(2 * meta_ms)
        self._sfuma(0.0, 1.0, meta_ms, lambda: self._a_meta(meta_ms, lavoro))

    def _a_meta(self, meta_ms: int, lavoro) -> None:
        try:
            lavoro()
        finally:
            self._sfuma(1.0, 0.0, meta_ms, self._finito)

    def _finito(self) -> None:
        self.barra.ferma()
        self.hide()

    def posa(self, velatura: float, avanzamento: float) -> None:
        """Un fotogramma scelto del velo, per `tools/scatta.py`. Si veda
        `BarraCarico.posa`: e' la stessa ragione, ed e' meta' del metodo di
        questo progetto."""
        padre = self.parentWidget()
        if padre is not None:
            self.setGeometry(padre.rect())
        self.show()
        self.raise_()
        self._scrivi(velatura)
        self.barra.posa(avanzamento)

    def _sfuma(self, da: float, a: float, ms: int, poi) -> None:
        self._anim = QPropertyAnimation(self, b"velatura", self)
        self._anim.setDuration(ms)
        self._anim.setStartValue(da)
        self._anim.setEndValue(a)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(poi)
        self._anim.start()

    def paintEvent(self, _e) -> None:  # noqa: N802 (nome imposto da Qt)
        # Dipinto a mano e non da un foglio di stile: un `QWidget` derivato non
        # prende il fondo dal foglio finche' non glielo si chiede, e qui l'opacita'
        # cambia trenta volte al secondo — un `unpolish/polish` per fotogramma
        # sarebbe il modo piu' caro possibile di fare una dissolvenza.
        p = QPainter(self)
        p.setOpacity(self._opacita)
        colore = QColor(self._fondo)
        # Non del tutto opaco: si intuisce che sotto c'e' la finestra, ed e'
        # quello che rende il velo un velo invece di un pannello che compare.
        colore.setAlphaF(0.96)
        p.fillRect(self.rect(), colore)


# ------------------------------------------------------- i nomi umani --------

# **Il nome del campo non e' il nome della funzione.** `duck_db` e' giusto nel
# sorgente e incomprensibile in una finestra: chi la apre non sta cercando un
# campo, sta cercando «di quanto abbasso il gioco quando parla la voce». Dove il
# nome umano c'e' si mostra quello e l'identificatore resta nel suggerimento;
# dove non c'e' — i parametri di taratura — l'identificatore **e' il nome
# giusto**, perche' chi li tocca li cerca cosi'.
NOMI: dict[str, str] = {
    # «lingua» da sola, in una finestra che ne ha altre due, non basta: qui si
    # dice **di che cosa** e' la lingua, se no si scambia per quella del
    # doppiaggio.
    "ui.lingua": "Lingua della finestra",
    "capture.fps": "Fotogrammi al secondo",
    "capture.solo_roi": "Cattura solo la fascia dei sottotitoli",
    "vision.roi": "Area dei sottotitoli",
    "vision.exclude_colored": "Ignora i sottotitoli colorati",
    "vision.sat_max": "Quanto acceso e' «colorato»",
    "vision.ocr_backend": "Motore di lettura",
    "vision.ocr_device": "Dove gira la lettura",
    "vision.max_ocr_hz": "Letture al secondo (tetto)",
    "vision.line_pad": "Respiro attorno alla riga",
    "label.enabled": "Usa il nome che scrive il gioco",
    "label.form": "Come il gioco scrive il nome",
    "label.regex": "Se il gioco la scrive in un altro modo",
    "label.voices": "Chi parla con che voce",
    "label.colors": "Il colore di ciascun personaggio",
    "label.require_names": "Solo i nomi dell'elenco",
    "tts.kokoro_speed": "Velocita' del parlato (Kokoro)",
    "tts.gap_seconds": "Pausa fra due battute",
    "translate.preserve_register": "Non ammorbidire le parolacce",
    "translate.context_lines": "Battute di contesto",
    "translate.outline": "Contorno del testo",
    "speaker.name_min_score": "Sotto questo punteggio, voce neutra",
    "label.names": "Nomi ammessi",
    "translate.enabled": "Traduci i sottotitoli",
    "translate.backend": "Traduttore",
    "translate.source": "Lingua del gioco",
    "translate.target": "Lingua in cui parlare",
    "translate.overlay": "Disegna il tradotto sopra il gioco",
    "translate.background_mode": "Come coprire la riga originale",
    "translate.color": "Colore del testo",
    "translate.misura_originale": "Tieni la misura dell'originale",
    "translate.font": "Carattere",
    "translate.font_frac": "Taglia del carattere",
    "translate.blur_strength": "Quanto sfocare",
    "translate.background_opacity": "Opacita' dello sfondo",
    "tts.backend": "Motore della voce",
    "tts.device": "Dove gira la voce",
    "tts.pool_size": "Quante voci diverse",
    "tts.native_rate_max": "Quanto puo' accelerare il motore",
    "tts.speed": "Velocita' del parlato",
    "speaker.backend": "Come si riconosce chi parla",
    "speaker.decide_after_ms": "Quanto aspettare per capire chi parla",
    "speaker.similarity": "Quanto somigliarsi per essere la stessa persona",
    "speaker.max_speakers": "Quanti personaggi al massimo",
    "speaker.gender_fallback": "Voce quando il genere non si capisce",
    "timing.rate_max": "Quanta fretta si puo' chiedere",
    "timing.accepted_delay_ms": "Ritardo che si accetta senza rincorrerlo",
    "mix.duck_db": "Quanto abbassare il gioco",
    "mix.dub_gain_db": "Volume della voce",
    "mix.duck_hold_ms": "Per quanto tenerlo abbassato",
    # I tre che restavano col nome di codice nella scheda Volumi, in mezzo a
    # tre scritti a parole: una colonna meta' italiano e meta' identificatori
    # non e' un elenco, sono due.
    "mix.duck_attack_ms": "Quanto svelto si abbassa",
    "mix.duck_release_ms": "Quanto svelto risale",
    "mix.passthrough": "Fai passare l'audio del gioco",
    "ui.save_mix": "Registra l'audio della sessione",
    "audio.samplerate": "Frequenza di campionamento",
    "audio.blocksize": "Blocco audio",
}

# L'unita' mostrata accanto al numero. Un cursore senza unita' e' un numero senza
# senso: -14 puo' essere decibel, millisecondi o pixel.
UNITA: dict[str, str] = {
    "mix.duck_db": " dB", "mix.dub_gain_db": " dB",
    "mix.duck_hold_ms": " ms", "mix.prebuffer_ms": " ms",
    "mix.duck_attack_ms": " ms", "mix.duck_release_ms": " ms",
    "speaker.decide_after_ms": " ms", "speaker.max_wait_ms": " ms",
    "speaker.min_clip_ms": " ms", "speaker.lead_ms": " ms",
    "timing.accepted_delay_ms": " ms",
    "capture.fps": " fps", "vision.max_ocr_hz": " Hz",
    "audio.samplerate": " Hz", "tts.samplerate": " Hz",
    "timing.rate_max": "×", "timing.rate_min": "×", "tts.native_rate_max": "×",
    "tts.speed": "×",
    "vision.min_line_height": " px", "translate.blur_strength": " px",
}

# I due capi del cursore, detti a parole. Un cursore dice «di piu'» e «di meno»;
# **quale dei due sia il bene** lo dice questa riga, e senza si prova a caso.
ESTREMI: dict[str, tuple[str, str]] = {
    "mix.duck_db": ("il gioco resta alto", "il gioco quasi sparisce"),
    "mix.dub_gain_db": ("voce piu' bassa", "voce piu' alta"),
    "mix.duck_attack_ms": ("scende di scatto", "scende piano, e copre l'inizio"),
    "mix.duck_release_ms": ("risale di scatto", "risale piano"),
    "mix.duck_hold_ms": ("risale fra una battuta e l'altra", "resta giu' per tutta la scena"),
    "timing.rate_max": ("non accelera mai", "accelera fino a mangiarsi le parole"),
    "tts.speed": ("parlato lento", "parlato svelto"),
    "tts.native_rate_max": ("mai", "molto"),
    "speaker.decide_after_ms": ("decide subito, sbaglia di piu'", "aspetta, e la voce tarda"),
    "vision.sat_max": ("basta un filo di colore", "solo colori accesi"),
    "translate.font_frac": ("come il gioco", "molto grande"),
    "speaker.similarity": ("fonde tutti insieme", "ognuno un personaggio nuovo"),
}


def nome_umano(percorso: str, ripiego: str) -> str:
    return NOMI.get(percorso, ripiego)


# ------------------------------------------------------------ le manopole ----


class Manopola(QWidget):
    """Quello che ogni controllo sa fare: dire il suo valore e riceverne uno.

    Un'interfaccia sola invece di una catena di `isinstance` sparsa nel pannello:
    aggiungere un tipo di manopola non deve voler dire ritoccare tre punti che si
    dimenticano a vicenda.
    """

    cambiato = Signal()

    def valore(self) -> Any:
        raise NotImplementedError

    def imposta(self, v: Any) -> None:
        raise NotImplementedError


class Cursore(Manopola):
    """Un cursore **con il numero accanto**, e i due capi detti a parole.

    Per tutto cio' che ha un intervallo dichiarato in `core.schema.LIMITI`: il
    controllo mostra da solo cosa e' lecito, quindi un valore fuori scala non si
    puo' nemmeno esprimere — che e' meglio che rifiutarlo dopo.

    Il numero resta scritto: un cursore da solo nasconde il valore, e questo
    progetto vive di numeri che si confrontano fra una prova e l'altra.
    """

    def __init__(self, basso: float, alto: float, *, intero: bool = False,
                 unita: str = "", estremi: tuple[str, str] | None = None) -> None:
        super().__init__()
        self.basso, self.alto, self.intero, self.unita = basso, alto, intero, unita
        # I passi: interi piccoli si muovono di uno, il resto in centesimi
        # dell'intervallo. Un cursore che si muove di un millesimo e' un cursore
        # che non si riesce a fermare dove si vuole.
        self.passi = int(alto - basso) if intero and (alto - basso) <= 400 else 100
        L = QHBoxLayout(self)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(tema.S2)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, self.passi)
        self.slider.setMinimumWidth(120)
        self.slider.valueChanged.connect(self._mosso)
        L.addWidget(self.slider, 1)
        self.numero = QLabel("")
        self.numero.setObjectName("mono")
        # Il valore vivo (`-14 dB`, `500 ms`): un numero con la sua unita', non
        # una parola dell'interfaccia. Nel catalogo diventerebbe una chiave
        # nuova a ogni scatto del cursore.
        self.numero.setProperty(MARCHIO, True)
        self.numero.setMinimumWidth(58)
        self.numero.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        L.addWidget(self.numero)
        if estremi:
            self.setToolTip(f"a sinistra: {estremi[0]}\na destra: {estremi[1]}")
        self._v = basso

    def _dal_passo(self, p: int) -> float:
        v = self.basso + (self.alto - self.basso) * p / max(1, self.passi)
        return round(v) if self.intero else round(v, 4)

    def _al_passo(self, v: float) -> int:
        frazione = (float(v) - self.basso) / max(1e-9, self.alto - self.basso)
        return max(0, min(self.passi, round(frazione * self.passi)))

    def _mosso(self, p: int) -> None:
        self._v = self._dal_passo(p)
        self.numero.setText(f"{self._v:g}{self.unita}")
        self.cambiato.emit()

    def valore(self) -> Any:
        return int(self._v) if self.intero else float(self._v)

    def imposta(self, v: Any) -> None:
        """Mostra quello che c'e' in config — **anche se sta fuori scala**.

        Tirando il cursore un valore fuori scala non si puo' nemmeno esprimere,
        ed e' il punto di avere un cursore. Ma in config puo' arrivarci lo stesso,
        da un profilo scritto a mano: li' la cosa da **non** fare e' pinzarlo in
        silenzio e mostrare -14 dove c'e' scritto 999 — sarebbe una finestra che
        mostra una configurazione diversa da quella in uso, cioe' il difetto
        contro cui esiste tutto questo pannello. Si tiene il numero vero, si
        appoggia il cursore al suo capo, e **si dice che e' fuori scala**.
        """
        try:
            n = float(v)
        except (TypeError, ValueError):
            return
        self._v = int(n) if self.intero else n
        self.slider.blockSignals(True)
        self.slider.setValue(self._al_passo(n))
        self.slider.blockSignals(False)
        fuori = n < self.basso or n > self.alto
        self.numero.setText(f"{'⚠ ' if fuori else ''}{self._v:g}{self.unita}")
        self.numero.setToolTip(
            f"fuori dall'intervallo ammesso ({self.basso:g}–{self.alto:g}): "
            f"tira il cursore per riportarlo dentro" if fuori else "")

    def fuori_scala(self) -> bool:
        return not (self.basso <= float(self._v) <= self.alto)


class SceltaColore(Manopola):
    """Un colore, con «come il gioco» come primo valore e default.

    Vuoto vuol dire «copia il colore del sottotitolo che stai coprendo», ed e' la
    scelta giusta quasi sempre: un colore deciso da noi e' sbagliato per
    costruzione, perche' ogni gioco scrive i sottotitoli come vuole. Ma vuoto in
    un campo di testo sembra **un campo non compilato**, non una scelta.
    """

    def __init__(self, testo_vuoto: str = "come il gioco") -> None:
        super().__init__()
        L = QHBoxLayout(self)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(tema.S2)
        # Cosa vuol dire «vuoto» dipende da dove sta questo controllo: nel
        # tradotto vuol dire «copia il colore del gioco», nella tabella dei
        # personaggi vuol dire «di che colore lo scrive non l'ho dichiarato».
        # Riusare la parola sbagliata sarebbe la stessa etichetta per due sensi.
        self.come_gioco = QCheckBox(testo_vuoto)
        self.come_gioco.toggled.connect(self._interruttore)
        L.addWidget(self.come_gioco)
        self.bottone = QPushButton("")
        self.bottone.setFixedWidth(46)
        self.bottone.setCursor(Qt.PointingHandCursor)
        self.bottone.clicked.connect(self._scegli)
        L.addWidget(self.bottone)
        L.addStretch(1)
        self._v = ""

    def _interruttore(self, acceso: bool) -> None:
        self.bottone.setEnabled(not acceso)
        self._v = "" if acceso else (self._v or "#ffffff")
        self._dipingi()
        self.cambiato.emit()

    def _scegli(self) -> None:
        c = QColorDialog.getColor(QColor(self._v or "#ffffff"), self, "Colore del testo")
        if c.isValid():
            self._v = c.name()
            self._dipingi()
            self.cambiato.emit()

    def _dipingi(self) -> None:
        """Il campione, col grigio del «non scelto» **preso dalla tavolozza**.

        Erano `#808080` e `tema.SCURA.bordo` scritti qui: un colore fuori
        tavolozza e uno del tema sbagliato. Il secondo e' il piu' insidioso —
        con la finestra chiara, il contorno del campione restava quello dello
        scuro e nessuno l'aveva mai guardato li'. E' la stessa forma del
        `#39d353` del selettore d'area.
        """
        t = tema.attuale(QApplication.instance())
        colore = self._v or t.testo_fioco
        self.bottone.setStyleSheet(
            f"background: {colore}; border: 1px solid {t.bordo_forte};"
            f" border-radius: {tema.R_CAMPO}px;")

    def valore(self) -> Any:
        return self._v

    def imposta(self, v: Any) -> None:
        self._v = str(v or "")
        self.come_gioco.blockSignals(True)
        self.come_gioco.setChecked(not self._v)
        self.come_gioco.blockSignals(False)
        self.bottone.setEnabled(bool(self._v))
        self._dipingi()


def voci_del_pool(cfg) -> list[tuple[str, str]]:
    """Le voci **che questa sessione avra' davvero**, col genere accanto.

    Si chiama lo stesso `build_pool` con gli stessi argomenti di
    `core/pipeline.py`, e non e' pedanteria: il pool e' tagliato a
    `tts.pool_size`, e una voce fuori dal pool il motore la **ignora** con un
    messaggio su stderr che dal vivo non legge nessuno. Offrire dodici voci
    quando la sessione ne costruira' sei vorrebbe dire un menu che contiene sei
    scelte che non fanno niente — la stessa forma del ripiego silenzioso che
    questo progetto ha gia' pagato tre volte.
    """
    try:
        from speak.pool import build_pool

        lingua = cfg.translate.target if cfg.translate.enabled else "it"
        pool = build_pool(
            cfg.tts.voices, cfg.tts.pool_size,
            backend=cfg.tts.backend, lingua=lingua,
        )
    except Exception:
        # Un backend senza voci native (`tone`, `silent`) non e' un errore: e'
        # una sessione in cui assegnare una voce non vuol dire niente.
        return []
    genere = {"m": "maschile", "f": "femminile"}
    return [(v.voice_id, genere.get(v.gender, "")) for v in pool]


class Tabella(Manopola):
    """Una riga per personaggio: il nome che il gioco scrive, e cosa gli tocca.

    E' la manopola dei due dizionari — `label.voices` e `label.colors` — che fino
    a ieri il pannello mostrava **spenti**, con scritto «non modificabile».
    Quello era onesto (`_coerce` non sapeva scriverli) ma nascondeva la funzione
    che l'utente cerca per prima: dare a Franklin *quella* voce. Senza, la voce
    non e' del personaggio, e' del **turno** in cui compare — chi apre la scena
    prende la prima voce libera.

    Il nome e' testo perche' testo e': lo scrive il gioco, e nessun elenco lo
    conosce prima di averlo visto. Il valore no — una voce e' un elenco chiuso, e
    digitarne una che non sta nel pool e' esattamente il modo di non accorgersi
    di niente.
    """

    def __init__(self, fai_valore, *, titolo_valore: str, esempio: str = "Franklin") -> None:
        super().__init__()
        self._fai_valore = fai_valore
        self._esempio = esempio
        self._righe: list[tuple[QLineEdit, QWidget, QWidget]] = []
        self._ricostruendo = False

        fuori = QVBoxLayout(self)
        fuori.setContentsMargins(0, 0, 0, 0)
        fuori.setSpacing(tema.S2)

        intestazione = QHBoxLayout()
        intestazione.setSpacing(tema.S2)
        for testo, largo in (("chi", 150), (titolo_valore, 0)):
            e = QLabel(testo)
            e.setObjectName("etichettaCampo")
            if largo:
                e.setFixedWidth(largo)
            intestazione.addWidget(e)
        intestazione.addStretch(1)
        self._intestazione = intestazione
        fuori.addLayout(intestazione)

        self._corpo = QVBoxLayout()
        self._corpo.setContentsMargins(0, 0, 0, 0)
        self._corpo.setSpacing(tema.S1)
        fuori.addLayout(self._corpo)

        self._vuoto = QLabel("Nessuno: le voci se le assegna il programma da solo.")
        self._vuoto.setObjectName("descrizione")
        fuori.addWidget(self._vuoto)

        self.piu = QPushButton("+  Aggiungi personaggio")
        self.piu.setCursor(Qt.PointingHandCursor)
        self.piu.clicked.connect(lambda: self._aggiungi("", None))
        fuori.addWidget(self.piu, 0, Qt.AlignLeft)

    # -- righe ---------------------------------------------------------------

    def _aggiungi(self, nome: str, valore: Any) -> None:
        riga = QWidget()
        L = QHBoxLayout(riga)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(tema.S2)

        chi = QLineEdit(nome)
        chi.setPlaceholderText(self._esempio)
        chi.setFixedWidth(150)
        # **A fine scrittura, non a ogni tasto**: e' la stessa regola di
        # `collega` per il testo, e qui non e' solo pulizia. Ogni applicazione
        # rilegge la config e ridisegna la tabella; a ogni tasto vorrebbe dire
        # scrivere `F`, `Fr`, `Fra` e perdere il fuoco da sotto le dita.
        chi.editingFinished.connect(self._forse_cambiato)
        L.addWidget(chi)

        w = self._fai_valore()
        # Senza un minimo, l'elenco si stringe finche' «riccardo — maschile»
        # diventa «riccardo —»: il genere, che e' l'unica cosa per cui si sceglie
        # una voce senza sentirla, e' la prima a sparire.
        w.setMinimumWidth(200)
        if valore is not None:
            scrivi(w, valore)
        collega(w, self.cambiato.emit)
        L.addWidget(w)
        L.addStretch(1)

        # **Una parola invece di un glifo.** Con la ✕ il bottone usciva vuoto —
        # il carattere della finestra non ha quel segno — cioe' un quadratino
        # muto accanto a ogni riga, che non si capisce se toglie la riga o
        # qualcos'altro. Un simbolo che dipende dal carattere installato non e'
        # un'etichetta.
        via = QPushButton("Togli")
        via.setFixedWidth(64)
        via.setCursor(Qt.PointingHandCursor)
        via.setToolTip("Togli questo personaggio dalla tabella")
        via.clicked.connect(lambda: self._togli(riga))
        L.addWidget(via)

        self._corpo.addWidget(riga)
        self._righe.append((chi, w, riga))
        self._vuoto.setVisible(False)
        self._forse_cambiato()

    def _togli(self, riga: QWidget) -> None:
        self._righe = [r for r in self._righe if r[2] is not riga]
        riga.setParent(None)
        riga.deleteLater()
        self._vuoto.setVisible(not self._righe)
        self._forse_cambiato()

    def _forse_cambiato(self) -> None:
        """Zitta mentre si sta ricostruendo: chi ricostruisce ha gia' il valore."""
        if not self._ricostruendo:
            self.cambiato.emit()

    # -- valore --------------------------------------------------------------

    def valore(self) -> Any:
        """Le righe con un nome. **Una riga senza nome non e' una riga vuota da
        buttare: e' una riga che l'utente sta scrivendo**, e sparirebbe da sotto
        le dita se la si applicasse."""
        fuori: dict[str, str] = {}
        for chi, w, _ in self._righe:
            nome = chi.text().strip()
            valore = str(leggi(w))
            # Nome senza valore non e' un'assegnazione: e' una riga a meta'. Il
            # motore la ignorerebbe comunque, ma la ignorerebbe **in silenzio**.
            if nome and valore:
                fuori[nome] = valore
        return fuori

    def imposta(self, v: Any) -> None:
        """**Non si ricostruisce cio' che gia' mostra la cosa giusta.**

        Il pannello rilegge la config dopo ogni modifica, che e' il suo pregio:
        mostra quello che c'e' davvero, non quello che ha appena mandato. Ma per
        una tabella «rileggere» vuol dire buttare le righe e rifarle — cioe'
        togliere di sotto le dita la casella in cui si sta scrivendo, a ogni
        riga. La verifica di uguaglianza costa niente e rende la rilettura
        gratuita nel caso normale, che e' «era andata bene».
        """
        nuovo = {str(k): str(x) for k, x in (v or {}).items()}
        if nuovo == self.valore():
            return
        self._ricostruendo = True
        try:
            for _, _, riga in self._righe:
                riga.setParent(None)
                riga.deleteLater()
            self._righe = []
            for nome, valore in nuovo.items():
                self._aggiungi(nome, valore)
        finally:
            self._ricostruendo = False
        self._vuoto.setVisible(not self._righe)


class SceltaLingua(Manopola):
    """Le centotrentatre lingue di Google, col nome per esteso e **da filtrare**.

    Tre cose, e la prima e' la meno interessante.

    **Si digita per cercare.** Con tredici voci un menu liscio andava bene; con
    centotrentatre no — si scorre a vuoto, e chi cerca il giapponese non sa se
    l'elenco lo chiama «Giapponese» o «Japanese». La casella e' modificabile e un
    `QCompleter` filtra per **contenuto** e non per prefisso, cosi' `giapp`,
    `ja` e `pones` trovano tutti la stessa riga.

    **Il menu dice la verita' per il backend scelto**, che e' la parte che conta.
    Google le fa tutte; `locale` esiste solo per coppie pubblicate; `llm` e
    `ollama` dipendono dal modello. Le lingue che il backend **certamente** non
    fa prendono un `⚠`; dove non c'e' un elenco chiuso non si marca niente e si
    scrive la frase che dice da cosa dipende (`translate.lingue.copertura`). Un
    menu che offre centotrentatre lingue a un traduttore che ne fa due consegna
    una battuta muta o non tradotta senza dire perche'.

    **E dichiara quando quella lingua non ha una voce.** I tre motori hanno
    cataloghi diversi — Piper 50 lingue, SuperTonic 31, Kokoro 8 — e tradurre
    verso una che quello montato non parla non da' errore: esce una voce che ne
    pronuncia un'altra, cioe' un modello fonemizzato con le regole sbagliate.
    La regola sta in `speak.pool.ha_voce`, fuori da Qt; e da quando il motore
    **segue la lingua** (`core.motore.motore_per_lingua`) questa frase compare
    solo nel caso che resta: nessun motore la parla.

    Le due frasi stanno in un'etichetta **elidibile** sotto la casella: i nomi
    lunghi («Cinese semplificato», «Creolo haitiano») e una spiegazione da
    centoventi caratteri sono esattamente cio' che faceva sforare le schede al
    minimo della finestra, e un `QLabel` normale impone la larghezza del suo
    testo intero.
    """

    # Quanti caratteri la casella chiusa deve poter mostrare. Non e' la voce piu'
    # lunga: e' quanto basta a leggere il nome scelto. La voce piu' lunga la
    # mostra la tendina, che si apre larga quanto serve (`allarga_tendina`).
    LARGHEZZA_TESTO = 18

    def __init__(self, con_auto: bool, cfg=None) -> None:
        super().__init__()
        from translate.lingue import AUTO, LINGUE, copertura, etichetta

        self._cfg = cfg
        self._con_auto = con_auto
        self._copertura = copertura(
            getattr(getattr(cfg, "translate", None), "backend", "") if cfg else "")

        L = QVBoxLayout(self)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(tema.S1)

        self.combo = QComboBox()
        # **Le centotrentatre voci non passano dal catalogo della finestra.** I
        # nomi delle lingue stanno gia' in `translate/lingue.py`; metterli anche
        # nel catalogo vorrebbe dire centotrentatre chiavi in piu' per ogni
        # lingua dell'interfaccia, tradotte da una macchina, per un dato che qui
        # c'e' gia' scritto a mano.
        self.combo.setProperty(MARCHIO, True)
        self.codici: list[str] = []
        if con_auto:
            self._aggiungi(AUTO, etichetta(AUTO))
        for x in LINGUE:
            self._aggiungi(x.codice, x.etichetta)
        self._noti = len(self.codici)

        # **Modificabile per cercare, non per inventare.** Il testo scritto a
        # mano viene risolto a fine scrittura: se corrisponde a una voce si
        # sceglie quella, se no si torna a quella che c'era — perche' scrivere
        # `giappone` non e' scegliere una lingua, e' non averla ancora trovata.
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        # Quante se ne vedono aperte lo dice `allarga_tendina`, in fondo a
        # questo costruttore: il 16 scritto qui a mano era lo stesso numero, ma
        # scritto due volte — e la seconda non l'avrebbe aggiornata nessuno.
        # Senza questa coppia la casella chiede la larghezza della voce piu'
        # lunga dell'elenco: 28 caratteri di «Meitei (manipuri) (mni-Mtei)»
        # imposti a una riga che ne ha 300 in tutto, e la scheda sfora.
        self.combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(self.LARGHEZZA_TESTO)
        self.combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

        completer = QCompleter(self.combo.model(), self.combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        # **Per contenuto e non per prefisso.** `ja` e' dentro «Giapponese (ja)»
        # ma non lo comincia: col filtro di serie, digitare il codice — che e'
        # l'unica cosa che si sa a memoria — non trova niente.
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.combo.setCompleter(completer)

        self.combo.currentIndexChanged.connect(self._scelta)
        self.combo.lineEdit().editingFinished.connect(self._digitato)
        allarga_tendina(self.combo)
        L.addWidget(self.combo)

        self.nota = Elidibile("")
        self.nota.setObjectName("tenue")
        # Riga viva, con dentro il nome del backend e l'elenco delle lingue con
        # una voce: e' una f-string, non una chiave. Sta in italiano insieme al
        # registro e alla barra della misura, per la stessa ragione.
        self.nota.setProperty(MARCHIO, True)
        self.nota.setVisible(False)
        L.addWidget(self.nota)

    def _aggiungi(self, codice: str, testo: str) -> None:
        """Una voce, col `⚠` davanti se questo backend **certamente** non la fa."""
        avvisa = not self._copertura.sa_fare(codice)
        self.combo.addItem(f"⚠ {testo}" if avvisa else testo)
        if avvisa:
            self.combo.setItemData(
                self.combo.count() - 1,
                "Il traduttore scelto non fa questa lingua.", Qt.ToolTipRole)
        self.codici.append(codice)

    # -- il valore -----------------------------------------------------------

    def _scelta(self, _i: int) -> None:
        self._dall_inizio()
        self._nota()
        self.cambiato.emit()

    def _dall_inizio(self) -> None:
        """La casella mostra l'**inizio** del nome, non la fine.

        Difetto visto a schermo, non nel codice: una casella modificabile e' un
        `QLineEdit`, e dopo `setCurrentIndex` il cursore sta in fondo — quindi
        con un nome piu' lungo della casella si leggeva `inese semplificato
        (zh-CN)` e `uto — riconoscila da sola`. La parte tagliata era **la
        prima**, cioe' quella che dice qual e' la lingua; il codice fra
        parentesi, che si vedeva benissimo, e' l'unica cosa che si puo' dedurre
        dal resto.
        """
        riga = self.combo.lineEdit()
        if riga is not None:
            riga.setCursorPosition(0)

    def _digitato(self) -> None:
        """Il testo scritto a mano, risolto contro l'elenco.

        Anche per **codice**: chi sa che il giapponese e' `ja` lo digita, e
        pretendere il nome italiano sarebbe togliere l'unica cosa che l'utente
        gia' sapeva fare prima di questo menu.
        """
        from translate.lingue import normalizza

        testo = self.combo.currentText().strip()
        if not testo:
            self.imposta(self.valore())
            return
        codice = normalizza(testo)
        if codice in self.codici:
            i = self.codici.index(codice)
        else:
            basso = testo.lower()
            candidati = [k for k in range(self.combo.count())
                         if basso in self.combo.itemText(k).lower()]
            if len(candidati) != 1:
                # Ambiguo o inesistente: si rimette quello in uso invece di
                # scegliere al posto suo. Un testo a meta' non e' una scelta.
                self.imposta(self.valore())
                return
            i = candidati[0]
        if i == self.combo.currentIndex():
            self.imposta(self.valore())   # rimette l'etichetta piena
            return
        self.combo.setCurrentIndex(i)

    def valore(self) -> Any:
        i = self.combo.currentIndex()
        return self.codici[i] if 0 <= i < len(self.codici) else "it"

    def imposta(self, v: Any) -> None:
        """**Un codice che non e' in elenco si mostra, non si sostituisce.**

        Stessa regola di `SceltaFra`: il pannello rilegge e riscrive dopo ogni
        modifica, quindi un valore sconosciuto zittito qui verrebbe
        **archiviato** come un altro. Un profilo scritto a mano con una lingua
        che questa tabella non conosce resta quello che e', e lo dice.
        """
        from translate.lingue import normalizza

        codice = normalizza(str(v or "it"))
        self.combo.blockSignals(True)
        try:
            while len(self.codici) > self._noti:
                self.codici.pop()
                self.combo.removeItem(self.combo.count() - 1)
            if codice in self.codici:
                self.combo.setCurrentIndex(self.codici.index(codice))
            else:
                self.codici.append(codice)
                self.combo.addItem(f"⚠ {codice} — non e' fra le lingue note")
                self.combo.setCurrentIndex(len(self.codici) - 1)
            self.combo.lineEdit().setText(self.combo.currentText())
            self._dall_inizio()
        finally:
            self.combo.blockSignals(False)
        self._nota()

    # -- quello che il menu da solo non direbbe -------------------------------

    def _nota(self) -> None:
        """Le due frasi: cosa non fa il traduttore, e se manca la voce.

        Si ricalcola a ogni `imposta`, e `imposta` la chiama anche il pannello
        quando cambia **un altro** campo (`Pannello.aggiorna` da `_riallinea`):
        cosi' cambiando `translate.backend` o `tts.backend` la frase si aggiorna
        invece di restare quella del backend di ieri.
        """
        from speak.pool import ha_voce, lingue_con_voce
        from translate.lingue import AUTO, copertura

        cfg = self._cfg
        tr = getattr(cfg, "translate", None) if cfg is not None else None
        self._copertura = copertura(getattr(tr, "backend", "") if tr else "")
        codice = self.valore()

        pezzi: list[str] = []
        if not self._copertura.sa_fare(codice):
            # Su `auto` la nota del backend **e' gia'** la spiegazione giusta —
            # dice che diventa `en` — e sostituirla con «non fa questa lingua»
            # toglierebbe l'unica informazione che serve: quale lingua verra'
            # usata al suo posto.
            pezzi.append("⚠ " + (self._copertura.nota if codice == AUTO else
                                 f"il traduttore «{getattr(tr, 'backend', '?')}» "
                                 f"non fa questa lingua."))
        elif self._copertura.nota:
            pezzi.append(self._copertura.nota)

        # La voce riguarda **la lingua che si parla**, cioe' quella d'arrivo:
        # su `source` non c'e' niente da dire, e dirlo lo stesso sarebbe un
        # avviso in piu' su una scelta che non lo merita.
        if not self._con_auto and codice != AUTO:
            motore = getattr(getattr(cfg, "tts", None), "backend", "") if cfg else ""
            if motore and not ha_voce(motore, codice):
                # **Non si elencano piu' le lingue che il motore parla.** Con due
                # erano un'informazione («solo italiano e inglese»); con
                # cinquanta sono una riga che nessuno legge, e che sfora la
                # scheda. Si dice quante sono e si lascia il come all'utente.
                quante = len(lingue_con_voce(motore))
                pezzi.append(
                    f"⚠ «{motore}» non ha voci in questa lingua (ne parla "
                    f"{quante}): la battuta uscirebbe con una voce che ne "
                    f"pronuncia un'altra.")

        testo = " ".join(p.replace("**", "").replace("`", "") for p in pezzi)
        self.nota.setToolTip(testo)
        self.nota.setText(testo)
        self.nota.setVisible(bool(testo))


class SceltaFra(Manopola):
    """Un elenco di valori, con l'etichetta umana accanto a quello tecnico.

    `piper | supertonic | kokoro | tone | silent` sono nomi di programmi: dicono
    tutto a chi li conosce e niente a chi apre la finestra. L'elenco mostra
    **cosa fa la scelta**, e tiene il nome tecnico perche' e' quello che finisce
    nei rapporti e nei comandi.
    """

    # **Due segni e non uno, perche' sono due cose diverse.** `⚠` vuol dire «c'e'
    # e su questa macchina non va», e non c'e' niente da fare; `↓` vuol dire
    # «funziona, e prima bisogna prenderla», che e' una porta aperta e non una
    # chiusa. Dare lo stesso segno a un guasto e a un download manderebbe a
    # cercare un difetto dove c'e' solo un file che manca — ed e' la stessa
    # distinzione che `core.bloccati` fa fra `criterio` e `assente`.
    #
    # `↓` e non `⬇`: la freccia sottile sta in praticamente ogni carattere di
    # sistema, quella grossa no, e un glifo che manca si disegna come un
    # quadratino. Un segno che a schermo diventa un quadratino non e' un segno.
    SEGNO_ROTTO = "⚠"
    SEGNO_MANCA = "↓"

    def __init__(self, valori: tuple[str, ...], etichette: dict[str, str] | None = None,
                 indisponibili: dict[str, str] | None = None,
                 da_installare: dict[str, str] | None = None) -> None:
        super().__init__()
        L = QHBoxLayout(self)
        L.setContentsMargins(0, 0, 0, 0)
        self.valori = list(valori)
        self._noti = len(self.valori)   # quante voci sono davvero disponibili
        self.etichette = dict(etichette or {})
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._scelto)
        self.rimarca(indisponibili, da_installare)
        L.addWidget(self.combo, 1)

    # -- i segni -------------------------------------------------------------

    def rimarca(self, indisponibili: dict[str, str] | None = None,
                da_installare: dict[str, str] | None = None) -> None:
        """Riscrive le voci con i segni di adesso, **tenendo la scelta**.

        Esiste per una richiesta sola, ed e' la meta' che l'utente ha chiesto
        insieme al bottone: **installato il pezzo, il segno e la scritta devono
        sparire**. I segni si calcolano quando si costruisce il menu; senza un
        modo di rifarli, «da installare» resterebbe scritto accanto a una cosa
        appena installata fino alla prossima apertura del programma — cioe' un
        avviso che dice il falso, che e' peggio di uno che non si poteva
        soddisfare.

        **Una scelta che qui non funziona si marca, non si toglie**: togliere una
        voce nasconderebbe che il programma la sa fare e che il difetto e' di
        questa macchina, e lascerebbe l'utente a chiedersi dove sia finita.
        """
        self._indisponibili = dict(indisponibili or {})
        self._da_installare = dict(da_installare or {})
        scelto = self.combo.currentIndex()
        self.combo.blockSignals(True)
        try:
            self.combo.clear()
            for i, v in enumerate(self.valori):
                if i >= self._noti:
                    # L'intruso: un valore che in configurazione c'e' e in
                    # elenco no. Si riscrive com'era, se no rimarcando
                    # diventerebbe una voce qualunque e sparirebbe la sola cosa
                    # che dice che quel valore non sara' usato.
                    self.combo.addItem(f"{self.SEGNO_ROTTO} {v} — {FUORI_ELENCO}")
                    self.combo.setItemData(self.combo.count() - 1,
                                           _perche_intruso(v), Qt.ToolTipRole)
                    continue
                testo = self.etichette.get(v)
                voce = f"{v} — {testo}" if testo else v
                motivo = self._perche_di(v)
                if v in self._indisponibili:
                    voce = f"{self.SEGNO_ROTTO} {voce}"
                elif v in self._da_installare:
                    voce = f"{self.SEGNO_MANCA} {voce}"
                self.combo.addItem(voce)
                if motivo:
                    self.combo.setItemData(self.combo.count() - 1, motivo,
                                           Qt.ToolTipRole)
            if 0 <= scelto < self.combo.count():
                self.combo.setCurrentIndex(scelto)
        finally:
            self.combo.blockSignals(False)
        # La tendina va rimisurata: con o senza il segno le voci sono larghe due
        # caratteri di differenza, e una casella misurata sul testo di prima
        # taglia l'ultima parola senza nemmeno i puntini che dicono che manca.
        allarga_tendina(self.combo)
        self._perche()

    def _perche_di(self, v: str) -> str:
        """La ragione che accompagna un segno, o niente se quella voce non ne ha."""
        return self._indisponibili.get(v) or self._da_installare.get(v, "")

    def _scelto(self, _i: int) -> None:
        self._perche()
        self.cambiato.emit()

    def _perche(self) -> None:
        """La ragione sulla casella **chiusa**, e non solo sulla voce in elenco.

        Il suggerimento messo sulla voce si vede aprendo la tendina, cioe' solo
        se si e' gia' sospettato qualcosa. Ma la scelta che non funziona e' quasi
        sempre **quella gia' scritta in configurazione**, e quella la si vede a
        tendina chiusa: senza questa riga il `⚠` resterebbe un segno senza
        spiegazione, che e' meta' dell'avviso — e la meta' che serve e' l'altra.
        """
        self.combo.setToolTip(self._perche_di(str(self.valore())))

    def valore(self) -> Any:
        i = self.combo.currentIndex()
        return self.valori[i] if 0 <= i < len(self.valori) else ""

    def imposta(self, v: Any) -> None:
        """**Un valore che non e' in elenco si mostra, non si sostituisce.**

        Prima, `imposta` con un valore sconosciuto non faceva niente: l'elenco
        restava sulla prima voce, quindi `valore()` rispondeva *un'altra cosa* —
        e il pannello, che dopo ogni modifica rilegge e riscrive, finiva per
        **archiviare** quella. Un profilo scritto a mano con un motore che non
        c'e' piu' diventava `piper` senza che nessuno lo dicesse, ed e' la stessa
        forma del ripiego silenzioso gia' pagata con `preload_dlls()` e con la
        voce fuori dal pool: il difetto non e' il valore sbagliato, e' che
        nessuno lo dice.
        """
        testo = str(v)
        self.combo.blockSignals(True)
        try:
            # Via l'eventuale intruso di prima: si tiene solo quello in uso.
            while len(self.valori) > self._noti:
                self.valori.pop()
                self.combo.removeItem(self.combo.count() - 1)
            if testo in self.valori:
                self.combo.setCurrentIndex(self.valori.index(testo))
                # I segnali sono zittiti apposta, quindi `_scelto` non passa di
                # qui: la ragione del `⚠` va rimessa a mano, se no resta quella
                # del valore di prima.
                self._perche()
                return
            self.valori.append(testo)
            self.combo.addItem(f"{self.SEGNO_ROTTO} {testo} — {FUORI_ELENCO}")
            self.combo.setItemData(self.combo.count() - 1, _perche_intruso(testo),
                                   Qt.ToolTipRole)
            self.combo.setCurrentIndex(len(self.valori) - 1)
            self.combo.setToolTip(_perche_intruso(testo))
        finally:
            self.combo.blockSignals(False)
            # L'intruso e' la voce piu' lunga di tutte: senza rimisurare,
            # l'avviso che dice perche' e' li' verrebbe tagliato a meta'.
            allarga_tendina(self.combo)


# Le due frasi dell'intruso — un valore scritto in configurazione che qui in
# elenco non c'e'. Stanno fuori dalla classe perche' le scrivono due strade
# (`imposta` quando l'intruso arriva, `rimarca` quando i segni si rifanno) e una
# frase scritta due volte e' una che al primo ritocco ne diventa due diverse.
FUORI_ELENCO = "non e' fra quelli disponibili"


def _perche_intruso(valore: str) -> str:
    return (f"«{valore}» non e' fra le scelte possibili qui. Resta scritto "
            f"perche' e' quello che c'e' in configurazione, ma non sara' usato.")


class SceltaCarattere(Manopola):
    """I caratteri **installati**, non un nome da indovinare.

    Scrivendo un nome che non esiste non arriva nessun errore: PIL ripiega su un
    carattere di sistema e il sottotitolo esce con un'altra forma — cioe' la
    misura presa dalla larghezza del testo si riferisce a un carattere e il
    disegno a un altro.
    """

    def __init__(self) -> None:
        super().__init__()
        L = QHBoxLayout(self)
        L.setContentsMargins(0, 0, 0, 0)
        self.combo = QFontComboBox()
        # **I duecentottanta caratteri installati non sono testo nostro.** Sono i
        # nomi che Windows da' ai suoi font, e tradurli sceglierebbe un carattere
        # che non esiste: `SceltaCarattere.valore()` restituisce la famiglia, e
        # una famiglia tradotta e' una famiglia sbagliata.
        self.combo.setProperty(MARCHIO, True)
        self.combo.currentFontChanged.connect(lambda _f: self.cambiato.emit())
        # Duecentonovanta caratteri sono la tendina piu' lunga della finestra:
        # senza la regola comune si aprirebbe con il numero di serie di Qt, che
        # e' un terzo numero accanto ai due che ci siamo dati.
        allarga_tendina(self.combo)
        L.addWidget(self.combo, 1)

    def valore(self) -> Any:
        return self.combo.currentFont().family()

    def imposta(self, v: Any) -> None:
        from PySide6.QtGui import QFont

        self.combo.blockSignals(True)
        self.combo.setCurrentFont(QFont(str(v or "Arial")))
        self.combo.blockSignals(False)


class SceltaCartella(Manopola):
    """Un percorso, col bottone che apre la finestra di sistema."""

    def __init__(self, file_singolo: bool = False) -> None:
        super().__init__()
        self.file_singolo = file_singolo
        L = QHBoxLayout(self)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(tema.S2)
        self.campo = QLineEdit()
        self.campo.editingFinished.connect(self.cambiato.emit)
        L.addWidget(self.campo, 1)
        b = QPushButton("Sfoglia…")
        b.clicked.connect(self._sfoglia)
        L.addWidget(b)

    def _sfoglia(self) -> None:
        if self.file_singolo:
            p, _ = QFileDialog.getOpenFileName(self, "Scegli il file", self.campo.text())
        else:
            p = QFileDialog.getExistingDirectory(self, "Scegli la cartella", self.campo.text())
        if p:
            self.campo.setText(p)
            self.cambiato.emit()

    def valore(self) -> Any:
        return self.campo.text()

    def imposta(self, v: Any) -> None:
        self.campo.blockSignals(True)
        self.campo.setText(str(v or ""))
        self.campo.blockSignals(False)


class Rettangolo(Manopola):
    """L'area dei sottotitoli: **si mostra, non si digita.**

    Quattro frazioni separate da virgole in un campo di testo erano il caso piu'
    chiaro di tutti: `0.204, 0.8843, 0.592, 0.07` non e' un valore che qualcuno
    possa inventare, e nemmeno correggere. Qui si legge dove sta il rettangolo, e
    per cambiarlo si tira col mouse — che e' l'unico modo in cui ha senso.
    """

    disegna = Signal()

    def __init__(self) -> None:
        super().__init__()
        L = QHBoxLayout(self)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(tema.S2)
        self.testo = QLabel("—")
        self.testo.setObjectName("mono")
        # `59%x13% a 23%,87%`: il rettangolo vivo, cioe' dei numeri.
        self.testo.setProperty(MARCHIO, True)
        L.addWidget(self.testo, 1)
        b = QPushButton("Disegna")
        b.setToolTip("Tira il rettangolo col mouse attorno alla riga dei sottotitoli")
        b.clicked.connect(self.disegna.emit)
        L.addWidget(b)
        self._v: tuple = (0.0, 0.0, 1.0, 1.0)

    def valore(self) -> Any:
        return self._v

    def imposta(self, v: Any) -> None:
        try:
            x, y, w, h = (float(n) for n in v)
        except (TypeError, ValueError):
            return
        self._v = (x, y, w, h)
        # In percentuale dello schermo: le frazioni non le legge nessuno, e
        # «larga il 59% e alta il 7%» dice subito se l'area e' troppo alta —
        # che e' il difetto piu' frequente di tutti.
        self.testo.setText(f"{w * 100:.0f}%×{h * 100:.0f}%  a {x * 100:.0f}%,{y * 100:.0f}%")
        self.testo.setToolTip(
            f"larga il {w * 100:.1f}% dello schermo e alta il {h * 100:.1f}%, "
            f"con l'angolo in alto a sinistra a {x * 100:.1f}%, {y * 100:.1f}%")


def leggi(w: QWidget) -> Any:
    """Il valore di una manopola, qualunque essa sia."""
    if isinstance(w, Manopola):
        return w.valore()
    if isinstance(w, QCheckBox):
        return w.isChecked()
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, (QSpinBox, QDoubleSpinBox)):
        return w.value()
    return w.text()


def scrivi(w: QWidget, v: Any) -> None:
    """Rimette nella manopola quello che c'e' davvero in config."""
    w.blockSignals(True)
    try:
        if isinstance(w, Manopola):
            w.imposta(v)
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(v))
        elif isinstance(w, QComboBox):
            w.setCurrentText(str(v))
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.setValue(v)
        else:
            w.setText(_testo(v))
    finally:
        w.blockSignals(False)


def collega(w: QWidget, quando) -> None:
    """Aggancia `quando` al segnale giusto per quel tipo di manopola."""
    if isinstance(w, Manopola):
        w.cambiato.connect(quando)
    elif isinstance(w, QCheckBox):
        w.toggled.connect(lambda _=False: quando())
    elif isinstance(w, QComboBox):
        w.currentIndexChanged.connect(lambda _i: quando())
    elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
        w.valueChanged.connect(lambda _v: quando())
    else:
        # Si applica quando si e' finito di scrivere: a ogni tasto vorrebbe dire
        # applicare `1` mentre si sta digitando `12`.
        w.editingFinished.connect(quando)


# Le etichette umane per gli elenchi che contano. Non tutti: dove i valori si
# spiegano da soli (`cpu | cuda | auto`) una parafrasi e' rumore.
ETICHETTE: dict[str, dict[str, str]] = {
    "tts.backend": {
        "piper": "svelto, gira ovunque (consigliato)",
        "supertonic": "piu' espressivo, piu' lento",
        "kokoro": "il migliore, vuole una GPU",
        "tone": "un bip al posto della voce, per sentire i tempi",
        "silent": "muto, per misurare senza sentire",
    },
    "vision.ocr_backend": {
        "ppocr": "gira ovunque",
        "oneocr": "quello di Windows, piu' preciso",
        "none": "non legge niente",
    },
    "translate.backend": {
        "locale": "sul tuo PC, senza mandare niente in rete",
        "llm": "sul tuo PC, modello piccolo",
        "ollama": "sul tuo PC, serve Ollama acceso",
        "google": "⚠ manda i sottotitoli a Google",
        "nessuno": "non traduce",
    },
    "translate.background_mode": {
        "blur": "sfoca la riga originale (consigliato)",
        "riquadro": "una tinta piatta — l'unico senza ritardo",
        "nessuno": "non copre niente: ci scrive sopra",
    },
}


# **Un esempio per forma, e l'elenco viene da chi le usa.** Questo elenco era
# scritto a mano e si era gia' scollato da `vision/label.py`: offriva `nome )`,
# `(nome)` e `NOME:`, che li' non esistono — sceglierne una fa **sollevare** il
# lettore all'avvio della catena, cioe' una voce del menu che rompe la sessione —
# e nascondeva le quattro vere aggiunte dopo (`-nome:`, `nome>>`, `NOME`,
# `nome(nota):`). E' la stessa forma dei difetti gia' visti qui: due
# posti che dicono la stessa cosa, e il secondo non lo aggiorna nessuno.
#
# Adesso l'elenco **e'** `FORME`: aggiungere una forma la' la fa comparire qui, e
# l'esempio serve a scegliere senza sapere cos'e' una regex — si riconosce come
# scrive il proprio gioco, non si legge `(?P<nome>...)`.
ESEMPI_FORMA: dict[str, str] = {
    "nome:": "Franklin: come va",
    "[nome]": "[Franklin] come va   (anche tonde e uncinate)",
    "nome-": "Franklin - come va",
    "-nome:": "- Franklin: come va",
    "nome>>": "Franklin >> come va",
    "NOME": "FRANKLIN come va   (⚠ solo con l'elenco dei nomi pieno)",
    "nome(nota):": "Franklin (arrabbiato): come va",
}


def _forme() -> tuple[tuple[str, ...], dict[str, str]]:
    """Le forme che il lettore sa leggere, con un esempio ciascuna."""
    from vision.label import FORME

    return tuple(FORME), {f: ESEMPI_FORMA.get(f, f) for f in FORME}


def _lingue_finestra() -> tuple[tuple[str, ...], dict[str, str]]:
    """Le lingue in cui la finestra sa vestirsi, **lette dal disco**.

    Non un elenco scritto: `ui/lingue/*.json`. Aggiungere una lingua e' lanciare
    `tools/traduci_ui.py`, non ritoccare due file di cui il secondo si dimentica
    — e' la stessa regola per cui `label.form` prende le forme da `vision.label`
    invece di riscriverle.

    E ogni voce dice **quanto e' completa**. Un catalogo a meta' non si vede
    guardando la finestra: si vede una parola in italiano in mezzo al tedesco e
    si pensa che sia una parola che non si traduce.
    """
    from ui import lingua as L

    from translate.lingue import nome_it

    valori = L.disponibili()
    etichette: dict[str, str] = {"auto": "come Windows"}
    for codice in valori:
        if codice == L.SORGENTE:
            etichette[codice] = f"{nome_it(codice)} — la lingua del sorgente"
            continue
        buchi = len(L.mancanti(codice))
        etichette[codice] = (
            nome_it(codice) if not buchi
            else f"{nome_it(codice)} — {buchi} parole ancora in italiano")
    return ("auto", *valori), etichette


SCELTE_A_MANO: dict[str, tuple[tuple[str, ...], dict[str, str]]] = {
    "speaker.gender_fallback": (
        ("m", "f"),
        {"m": "voce maschile", "f": "voce femminile"},
    ),
    "label.form": _forme(),
}


def per_campo(campo, *, limiti, cfg=None) -> QWidget:
    """La manopola giusta per questo campo — **scelta dal significato**.

    L'ordine dei casi e' l'ordine di quanto un controllo dice: prima quelli che
    dichiarano cosa e' lecito (rettangolo, colore, lingua, elenco, cursore), e il
    campo di testo per ultimo, che e' l'unico che non dice niente.

    `cfg` serve alle tabelle dei personaggi: le voci fra cui si sceglie dipendono
    da **altri campi** (motore, numero di voci, lingua), e un elenco costruito
    senza guardarli offrirebbe voci che questa sessione non avra'.
    """
    percorso = campo.percorso
    if not campo.modificabile:
        w = QLineEdit(_testo(campo.valore))
        w.setEnabled(False)
        return w
    if percorso == "label.voices":
        voci = voci_del_pool(cfg) if cfg is not None else []
        if not voci:
            # Nessuna voce da offrire: meglio una casella spenta che dice
            # perche', che un elenco vuoto da cui non si puo' scegliere.
            w = QLineEdit("prima scegli un motore della voce")
            w.setEnabled(False)
            return w
        etichette = {v: g for v, g in voci if g}
        return Tabella(
            lambda: blocca_rotella(SceltaFra(tuple(v for v, _ in voci), etichette)),
            titolo_valore="parla con la voce",
        )
    if percorso == "label.colors":
        return Tabella(
            lambda: SceltaColore("non lo so"),
            titolo_valore="il gioco lo scrive di questo colore",
        )
    if percorso == "vision.roi":
        return Rettangolo()
    if percorso in ("translate.color", "translate.background"):
        return SceltaColore()
    if percorso in ("translate.source", "translate.target"):
        # `cfg` non e' un di piu': senza, il menu non sa quale traduttore e quale
        # sintetizzatore sono montati, cioe' non puo' dire quali di quelle
        # centotrentatre lingue funzionano davvero in questa sessione.
        return SceltaLingua(con_auto=percorso.endswith("source"), cfg=cfg)
    if percorso == "ui.lingua":
        # **L'elenco si costruisce adesso e non all'import.** Un catalogo
        # aggiunto mentre il programma e' chiuso deve comparire alla riapertura
        # senza toccare codice: `SCELTE_A_MANO` viene valutato una volta sola
        # all'import, e `label.form` puo' permetterselo perche' le forme stanno
        # nel sorgente. Le lingue no, stanno sul disco.
        w = blocca_rotella(SceltaFra(*_lingue_finestra()))
        # **Le voci di questo elenco non passano dal catalogo, e il perche' l'ha
        # trovato una verifica.** L'etichetta di `SceltaFra` e' `codice —
        # nome`, quindi il codice viaggia dentro la stringa: dandola a un
        # traduttore automatico, `uk — Ucraino` e' tornato «Regno Unito —
        # ucraino» in polacco e in arabo. Il catalogo aveva trasformato un
        # codice di lingua in un paese. I nomi delle lingue stanno gia' in
        # `translate/lingue.py`, e li' sono scritti a mano.
        w.setProperty(MARCHIO, True)
        return w
    if percorso == "translate.font":
        return blocca_rotella(SceltaCarattere())
    if percorso.endswith(("_dir", "model_dir", "lexicon_dir")):
        return SceltaCartella()
    if campo.tipo == "bool":
        w = QCheckBox()
        w.setChecked(bool(campo.valore))
        return w
    a_mano = SCELTE_A_MANO.get(percorso)
    if a_mano is not None:
        return blocca_rotella(SceltaFra(*a_mano))
    if campo.scelte:
        return blocca_rotella(SceltaFra(campo.scelte, ETICHETTE.get(percorso),
                                        indisponibili=indisponibili_qui(percorso),
                                        da_installare=da_installare(percorso, cfg)))
    coppia = limiti(percorso)
    if coppia is not None and campo.tipo in ("int", "float"):
        return blocca_rotella(Cursore(
            coppia[0], coppia[1], intero=campo.tipo == "int",
            unita=UNITA.get(percorso, ""), estremi=ESTREMI.get(percorso),
        ))
    w = QLineEdit(_testo(campo.valore))
    return w


def indisponibili_qui(percorso: str) -> dict[str, str]:
    """Quali scelte di questo campo non funzionano su questa macchina, e perche'.

    La regola sta in `core.bloccati.scelte_indisponibili`, fuori da Qt; qui
    resta solo la protezione contro il caso in cui **chiedere** sia il problema:
    il pannello si costruisce anche mentre si scattano le schermate, e una
    finestra che non si apre per colpa di una prova d'ambiente sarebbe un difetto
    peggiore di quello che questa riga dichiara.
    """
    try:
        from core.bloccati import scelte_indisponibili

        return scelte_indisponibili(percorso)
    except Exception:  # pragma: no cover - non deve poter fermare la finestra
        return {}


def da_installare(percorso: str, cfg) -> dict[str, str]:
    """`{valore: cosa manca}` per un campo a scelta, o un dizionario vuoto.

    **La regola sta in `core.banco`, fuori da Qt**, ed e' la stessa che il passo
    6 della guida usa per il suo preventivo: quali pezzi servono a una scelta
    (`RICHIESTE`), quali di quelli mancano (`manca_per_scelta`) e quanto pesano
    (`peso_mb`). Qui resta solo il modo di scriverlo in una riga.

    **Vuoto vuol dire «non ho niente da dichiarare», non «c'e' tutto».** Se il
    disco non risponde entro il tetto (`presenti_svelto`) non si marca, e va
    bene: non marcare non promette niente, marcare a torto sarebbe un avviso che
    nessuno puo' soddisfare. La risposta intanto arriva e finisce in cache,
    quindi al prossimo ridisegno il segno c'e'.

    E il ripiego largo non e' pigrizia: il pannello si costruisce anche mentre si
    scattano le schermate, e una finestra che non si apre per colpa di una prova
    d'ambiente sarebbe un difetto peggiore di quello che questa riga dichiara.
    """
    try:
        from core import banco

        if percorso not in banco.RICHIESTE or cfg is None:
            return {}
        avuti = banco.presenti_svelto(cfg)
        if avuti is None:
            return {}
        fuori: dict[str, str] = {}
        for valore in banco.RICHIESTE[percorso]:
            manca = banco.manca_per_scelta(percorso, valore, avuti)
            if manca:
                fuori[valore] = DA_PRENDERE.format(banco.peso_mb(manca))
        return fuori
    except Exception:  # pragma: no cover - non deve poter fermare la finestra
        return {}


# La frase che accompagna il `↓`. E' un modello riempito con un numero, quindi
# si traduce lui e non la frase composta — la stessa regola di `ui.lingua`.
DA_PRENDERE = "Va installato: {0} MB da scaricare. Scegliendolo, il programma offre di farlo."


def _testo(valore: Any) -> str:
    if isinstance(valore, tuple):
        return ", ".join(_testo(v) for v in valore)
    if isinstance(valore, float):
        return f"{valore:g}"
    if isinstance(valore, dict):
        return f"({len(valore)} voci)"
    return str(valore)
