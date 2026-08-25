"""Prendere i frame dallo schermo mentre il gioco gira.

Il banco legge da file, e va benissimo per tutto cio' che riguarda *cosa*
produce la pipeline. Ma non puo' rispondere alla domanda che decide il prodotto:
**quanto costa prendere un frame mentre il gioco sta usando la stessa macchina.**
Da file il frame e' gia' li'; in gioco bisogna strapparlo alla scheda video che
sta disegnando altro.

Due backend, e la differenza conta:

- **dxcam** usa Desktop Duplication. E' veloce (copia in GPU, nessun round-trip
  per la parte pesante) ed e' quello che si vuole. Restituisce `None` quando
  nulla e' cambiato sullo schermo, il che e' un'ottimizzazione utilissima e una
  trappola: chi non la gestisce misura zero millisecondi e conclude che la
  cattura e' gratis;
- **mss** e' GDI, funziona ovunque e costa di piu'. E' il ripiego che non lascia
  mai a piedi.

`windows-capture` (WGC) e' quello che regge il fullscreen esclusivo dove Desktop
Duplication cede, ed e' previsto dal piano. Non c'e' ancora: si aggiunge qui
dietro la stessa interfaccia quando servira' provare il gioco a schermo intero
esclusivo. Finche' non c'e', chiederlo lo dice invece di ripiegare in silenzio.

**Cosa si misura e cosa no.** `grab()` restituisce il frame; il costo si prende
a muro attorno alla chiamata, mai col tempo del media. E' la stessa regola dei
due orologi di `core/stage.py`, e qui e' ancora piu' facile sbagliarla perche'
non c'e' nessun tempo del media da confondere: c'e' solo il muro, ed e' proprio
lui l'oggetto della misura.
"""

from __future__ import annotations

import sys
import time
import weakref
from dataclasses import dataclass

import numpy as np

# **Le catture di finestra vive, una per finestra.** E' una tabella debole: chi
# ci sta dentro non ci resta per colpa di questa riga. Serve a una cosa sola —
# accorgersi che la sessione precedente ne ha lasciata una accesa sulla stessa
# finestra — e si veda `FinestraSource`, dove c'e' la misura di quanto costa.
_CATTURE_FINESTRA: "weakref.WeakValueDictionary[int, FinestraSource]" = (
    weakref.WeakValueDictionary()
)

# **E le catture fermate non si liberano: si mettono da parte.** `windows_capture`
# non regge il rilascio dell'oggetto nativo dopo lo stop — misurato, la cattura
# del secondo Avvia moriva con un **accesso a memoria non valido** dentro
# `start_free_threaded`, cioe' un crash del programma invece di una sessione
# lenta. Fermata, una cattura non copia piu' niente e non costa niente: quello
# che pesava — l'ultimo fotogramma della finestra, 11 MB su uno schermo grande —
# e' roba nostra e viene liberata. Si tiene quindi la scatola vuota, e si
# dichiara qui perche' e' una perdita voluta e non una dimenticanza.
_FERMATE: list = []


@dataclass(frozen=True, slots=True)
class Grab:
    """Un frame catturato, o l'assenza di uno."""

    frame: np.ndarray | None
    t: float  # istante a muro della cattura
    fresh: bool  # False = lo schermo non e' cambiato, il backend non ha dato nulla

    @property
    def ok(self) -> bool:
        return self.frame is not None


class ScreenSource:
    """Interfaccia comune ai backend di cattura."""

    name = "?"

    def grab(self) -> Grab:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self) -> "ScreenSource":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class DxcamSource(ScreenSource):
    """Desktop Duplication. Veloce, e restituisce None quando nulla cambia."""

    name = "dxcam"

    def __init__(self, monitor: int = 0, region: tuple[int, int, int, int] | None = None) -> None:
        import dxcam

        self._cam = dxcam.create(output_idx=monitor, output_color="BGR")
        if self._cam is None:
            raise RuntimeError(f"dxcam non riesce ad aprire il monitor {monitor}")
        self._region = region

    def grab(self) -> Grab:
        t0 = time.perf_counter()
        frame = self._cam.grab(region=self._region) if self._region else self._cam.grab()
        # `None` non e' un errore: e' "lo schermo non e' cambiato". Contarlo come
        # una cattura riuscita a costo zero e' il modo di concludere che la
        # cattura non costa niente.
        return Grab(frame=frame, t=t0, fresh=frame is not None)

    def close(self) -> None:
        try:
            self._cam.release()
        except Exception:
            pass

    def __del__(self) -> None:
        # Il duplicatore va rilasciato anche quando il ciclo video esce senza
        # chiudere: `dxcam.create()` tiene una tavola delle telecamere aperte e
        # a quella dopo restituisce **questa**, con un avviso che non legge
        # nessuno. Si veda la nota in `FinestraSource.__del__`.
        try:
            self.close()
        except Exception:  # pragma: no cover - all'uscita del programma
            pass


class MssSource(ScreenSource):
    """GDI. Piu' lento, ma non lascia a piedi e non salta mai un frame."""

    name = "mss"

    def __init__(self, monitor: int = 1, region: tuple[int, int, int, int] | None = None) -> None:
        import mss

        self._sct = mss.mss()
        mons = self._sct.monitors
        if monitor >= len(mons):
            raise RuntimeError(f"monitor {monitor} inesistente: ce ne sono {len(mons) - 1}")
        m = mons[monitor]
        if region is not None:
            # **La regione e' relativa al monitor, non al desktop.** Con due
            # schermi l'origine di `mons[2]` non e' (0,0), e la ROI e'
            # normalizzata sul monitor che si sta catturando: sommare qui
            # l'origine e' l'unico posto dove i due sistemi si incontrano una
            # volta sola. E' la stessa ragione per cui `make_screen` traduce
            # l'indice del monitor invece di lasciarlo fare ai backend.
            left, top, right, bottom = region
            self._box = {
                "left": m["left"] + left,
                "top": m["top"] + top,
                "width": right - left,
                "height": bottom - top,
            }
        else:
            self._box = {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}

    def grab(self) -> Grab:
        t0 = time.perf_counter()
        shot = self._sct.grab(self._box)
        # BGRA -> BGR: `vision/lines.py` classifica con grandezze simmetriche
        # rispetto all'ordine dei canali, ma l'alfa va tolto comunque.
        frame = np.asarray(shot, dtype=np.uint8)[:, :, :3]
        return Grab(frame=frame, t=t0, fresh=True)

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:
            pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # pragma: no cover - all'uscita del programma
            pass


class FinestraSource(ScreenSource):
    """Windows Graphics Capture su **una finestra sola**.

    E' il modo giusto, e la ragione non e' la velocita': catturando lo schermo
    intero, dentro il fotogramma che diamo all'OCR finisce **tutto quello che
    sta davanti al gioco** — comprese le nostre finestre. Misurato: l'overlay
    del tradotto ci entrava al 100%, e l'OCR leggeva il nostro testo invece del
    sottotitolo. Con `CreateForWindow` il contenuto e' quello della finestra
    scelta e basta; verificato mettendole sopra una finestra rossa che la copriva
    a meta', nella cattura ne e' arrivato lo **0,000**.

    Da qui discendono tre cose che prima erano problemi separati: l'overlay non
    ha piu' bisogno di essere escluso dalla cattura (e quindi puo' tornare una
    finestra normale, che OBS vede); la ROI e' relativa alla **finestra**, quindi
    se il gioco si sposta il sottotitolo lo segue; e non c'e' piu' niente da
    ritagliare.

    **Il modello e' a spinta, la nostra interfaccia e' a strappo.** WGC chiama
    noi quando ha un fotogramma; `grab()` viene chiamato dal ciclo video quando
    vuole lui. Si tiene quindi l'ultimo arrivato — e **lo si riconsegna anche se
    non e' cambiato**, che e' l'opposto di quello che fa dxcam e va spiegato.

    Con una scena ferma WGC non manda niente: misurato, un fotogramma su 119 su
    una pagina in pausa. Rispondendo «niente» il ciclo video salterebbe quei
    giri, e il lettore di sottotitoli e' costruito su frame **consecutivi**: un
    sottotitolo rimasto a schermo su una scena immobile smetterebbe di essere
    visto proprio perche' non si muove. Si riconsegna quindi l'ultimo, e a dire
    se e' nuovo ci pensa `fresh` — chi vuole saltare il lavoro inutile ha gia'
    `vision.diff`, che confronta i fotogrammi e non si fida di nessuno.

    **Una finestra, una cattura, e prima non era vero.** I due callback sono
    chiusure su `self`, quindi WGC tiene in vita la sorgente per sempre: nessun
    conteggio di riferimenti arriva a zero, e il ciclo video — che uscendo non
    chiama `close()` — ne lasciava indietro **una per sessione**, ancora accesa a
    copiare la finestra del gioco a ogni fotogramma. Misurato con cinque
    Avvia/Ferma veri, catturando una finestra 1600x900 che cambia a 57 Hz:

        cicli   catture vive   copie/s   sintesi Kokoro   classify_lines
        ---------------------------------------------------------------
          1          1            57        162,9 ms         30,0 ms
          3          3           172        172,1 ms         43,6 ms
          5          5           285        180,4 ms         46,9 ms

    cioe' la stessa deriva dei rapporti dal vivo dell'utente (`vision.classify`
    da 29 a 47 ms in cinque Avvia), piu' 14 MB di VRAM per cattura.

    Aprire la cattura di una finestra **ferma quella che c'era su quella stessa
    finestra**: e' l'unica garanzia che vale a tempo zero, e vale nel momento che
    conta — mentre una sessione e' accesa ne lavora **una sola**.

    **E niente viene liberato, che e' una scelta e non una dimenticanza.** La
    strada pulita — riferimento debole nei callback piu' `__del__` che ferma —
    e' stata scritta, provata e **buttata**: rilasciare l'oggetto dopo lo stop fa
    morire il programma con un accesso a memoria non valido dentro
    `start_free_threaded` all'Avvia successivo (visto due volte su cinque, cioe'
    per giunta a intermittenza). Fra una cattura ferma che resta in memoria e un
    crash, la scelta e' fatta; e una cattura ferma non copia piu' niente.
    """

    name = "finestra"

    def __init__(self, hwnd: int) -> None:
        import threading

        from windows_capture import WindowsCapture

        self.hwnd = int(hwnd)
        # **Chi apre dovrebbe chiudere, ma il ciclo video esce senza farlo**: se
        # su questa finestra c'e' ancora la cattura della sessione precedente, la
        # si ferma adesso invece di lasciarla copiare il gioco per tutta la
        # partita. Si dichiara su stderr perche' e' un rattoppo, non una
        # normalita': la riga sparisce il giorno in cui chi apre chiude.
        vecchia = _CATTURE_FINESTRA.get(self.hwnd)
        if vecchia is not None and not vecchia._fermata:
            print(
                f"cattura: la finestra {self.hwnd} era ancora catturata dalla "
                f"sessione precedente: la fermo",
                file=sys.stderr,
            )
            vecchia.close()
        del vecchia
        self._lock = threading.Lock()
        self._ultimo: np.ndarray | None = None
        self._nuovo = False
        self._chiusa = False
        self._fermata = False  # l'abbiamo fermata noi (diverso da `_chiusa`)
        self._cattura = WindowsCapture(
            cursor_capture=False,  # il puntatore non e' contenuto del gioco
            draw_border=False,  # niente cornice gialla attorno al gioco
            window_hwnd=self.hwnd,
        )
        @self._cattura.event
        def on_frame_arrived(frame, control):  # noqa: ANN001
            if self._fermata:
                # Fermata: si esce **senza copiare**, che e' tutto il costo.
                # Lo stop vero l'ha gia' chiesto `close()`; qui si smette di
                # pagare anche nei fotogrammi che arrivano nel frattempo.
                return
            # Copia e non vista: il buffer torna a WGC appena questa funzione
            # rientra, e il ciclo video lo leggerebbe mentre viene riscritto.
            dati = np.ascontiguousarray(frame.frame_buffer[:, :, :3])
            with self._lock:
                self._ultimo = dati
                self._nuovo = True

        @self._cattura.event
        def on_closed():
            self._chiusa = True

        self._ctrl = self._cattura.start_free_threaded()
        _CATTURE_FINESTRA[self.hwnd] = self

    def grab(self) -> Grab:
        t0 = time.perf_counter()
        with self._lock:
            frame, nuovo = self._ultimo, self._nuovo
            self._nuovo = False
        if frame is None:
            return Grab(frame=None, t=t0, fresh=False)
        return Grab(frame=frame, t=t0, fresh=nuovo)

    @property
    def chiusa(self) -> bool:
        """Il gioco e' stato chiuso. Va detto, non dedotto dal silenzio."""
        return self._chiusa

    def close(self) -> None:
        if self._fermata:
            return
        self._fermata = True
        # I pixel della finestra sono la parte pesante e sono nostri: si lasciano
        # andare adesso, che e' il momento in cui si sa che non serviranno piu'.
        self._ultimo = None
        ctrl = getattr(self, "_ctrl", None)
        cattura = getattr(self, "_cattura", None)
        if ctrl is None:  # pragma: no cover - costruzione fallita a meta'
            return
        try:
            ctrl.stop()
        except Exception:  # pragma: no cover
            pass
        # **Si aspetta che il thread di WGC abbia davvero finito.** `stop()`
        # chiede e torna subito, e il pezzo nativo non va toccato mentre lavora.
        # Si aspetta a giri brevi e con un tetto, perche' qui ci si passa anche
        # da `__del__` — dove restare appesi vorrebbe dire un programma che non
        # si chiude piu'.
        fine = time.perf_counter() + 2.0
        finita = False
        while time.perf_counter() < fine:
            try:
                finita = bool(ctrl.is_finished())
            except Exception:  # pragma: no cover - versione senza is_finished
                finita = True
            if finita:
                break
            time.sleep(0.005)
        if not finita:  # pragma: no cover - non si e' mai visto
            print("cattura: la finestra non si e' fermata entro due secondi",
                  file=sys.stderr)
        # E la scatola resta li' apposta: si veda `_FERMATE`.
        _FERMATE.append((cattura, ctrl))


class SoloRoi(ScreenSource):
    """Cattura **solo la fascia che si legge**, e la rimette al suo posto.

    **Perche' esiste.** Misurato su questa macchina, uno schermo 2560x1440:
    prendere il fotogramma intero costa **29,7 ms**, cioe' il 90% del budget di
    un giro a 30 Hz — e il ciclo video, dal vivo, girava a ~18 Hz. Ma di quel
    fotogramma si guarda una fascia alta il 5%: il sottotitolo. Prendere solo
    quella e reincollarla costa **6,1 ms**.

        fascia + margine    dimensione    grab + incolla
        ------------------------------------------------
        schermo intero      2560x1440         32,4 ms
        0,06 H              1308x248           9,2 ms
        0,08 H              1366x306          11,7 ms   <- il default
        0,10 H              1424x364          11,6 ms

    Il default non e' il piu' stretto: e' il piu' stretto che lasci spazio
    all'overlay, che cresce verso l'alto (si veda `capture.roi_margin`).

    **Perche' si reincolla invece di consegnare la sola fascia.** Tutto cio' che
    sta a valle — la ROI del lettore, le aree multiple, il ritaglio dell'overlay
    — e' in coordinate del fotogramma intero. Consegnare un fotogramma piu'
    piccolo vorrebbe dire cambiare quel sistema di coordinate in cinque posti, e
    il primo che se ne dimenticasse leggerebbe il punto sbagliato **senza
    errore**. La tela nera costa una frazione di quello che fa risparmiare.

    **E il margine non e' prudenza**: l'overlay sfoca i pixel *attorno* alla
    riga e cresce verso l'alto quando il tradotto occupa piu' righe. Fuori dalla
    fascia catturata ci sarebbe nero, e si vedrebbe.
    """

    def __init__(self, sorgente: ScreenSource, regione, dimensione) -> None:
        self.sorgente = sorgente
        self.regione = tuple(int(v) for v in regione)
        self.dimensione = (int(dimensione[0]), int(dimensione[1]))
        self.name = f"{sorgente.name}+roi"

    def grab(self) -> Grab:
        g = self.sorgente.grab()
        if not g.ok:
            return g
        left, top, right, bottom = self.regione
        w, h = self.dimensione
        pezzo = g.frame
        tela = np.zeros((h, w, pezzo.shape[2] if pezzo.ndim == 3 else 1), pezzo.dtype)
        # Il pezzo puo' essere piu' piccolo di quanto chiesto (bordi dello
        # schermo): si incolla quello che c'e' invece di sollevare, se no una
        # ROI attaccata al bordo farebbe cadere la sessione invece di leggere.
        alto = min(pezzo.shape[0], h - top)
        largo = min(pezzo.shape[1], w - left)
        tela[top:top + alto, left:left + largo] = pezzo[:alto, :largo]
        return Grab(frame=tela, t=g.t, fresh=g.fresh)

    def close(self) -> None:
        self.sorgente.close()


def dimensione_monitor(monitor: int = 1) -> tuple[int, int]:
    """Quanto e' grande il monitor che si cattura, in pixel."""
    import mss

    with mss.mss() as sct:
        mons = sct.monitors
        if monitor >= len(mons):
            raise RuntimeError(f"monitor {monitor} inesistente: ce ne sono {len(mons) - 1}")
        m = mons[monitor]
        return int(m["width"]), int(m["height"])


def regione_da_roi(rois, dimensione, margine: float = 0.08) -> tuple[int, int, int, int]:
    """Il rettangolo da catturare per leggere quelle aree, in pixel del monitor.

    Prende **l'unione** dei rettangoli e non il primo: chi chiama ne passa
    se ne legge piu' d'una, e catturare solo la prima farebbe sparire le altre
    senza che niente lo dica — sarebbero semplicemente nere.
    """
    w, h = int(dimensione[0]), int(dimensione[1])
    rois = [r for r in rois if r and len(r) == 4 and r[2] > 0 and r[3] > 0]
    if not rois:
        return (0, 0, w, h)
    m = int(max(0.0, margine) * h)
    left = max(0, int(min(r[0] for r in rois) * w) - m)
    top = max(0, int(min(r[1] for r in rois) * h) - m)
    right = min(w, int(max(r[0] + r[2] for r in rois) * w) + m)
    bottom = min(h, int(max(r[1] + r[3] for r in rois) * h) + m)
    return (left, top, max(left + 1, right), max(top + 1, bottom))


def fascia_da_roi(rois, margine: float = 0.08) -> tuple[float, float] | None:
    """Fra che due frazioni dell'altezza sta cio' che si legge, col margine.

    Frazioni e non pixel perche' chi la usa cattura una **finestra**, e una
    finestra cambia misura: si veda `PrintWindowSource.fascia`. Torna `None` se
    la fascia sarebbe quasi tutta l'altezza — sotto quel punto ritagliare non
    fa risparmiare niente e aggiunge un modo di sbagliare.

    Il margine e' lo stesso di `regione_da_roi` e per la stessa ragione:
    l'overlay sfoca i pixel attorno alla riga e **cresce verso l'alto** quando
    il tradotto occupa piu' righe dell'originale.
    """
    rois = [r for r in rois if r and len(r) == 4 and r[3] > 0]
    if not rois:
        return None
    m = max(0.0, float(margine))
    su = max(0.0, min(r[1] for r in rois) - m)
    giu = min(1.0, max(r[1] + r[3] for r in rois) + m)
    if giu - su >= 0.9:
        return None
    return (su, giu)


def apri_cattura(
    backend: str = "auto",
    monitor: int = 1,
    hwnd: int | None = None,
    *,
    rois=(),
    margine: float = 0.08,
    dillo=None,
) -> ScreenSource:
    """La sorgente di cattura, con la fascia sola se `rois` e' popolato.

    E' il posto dove le due catene dal vivo costruiscono lo schermo, perche' la
    scelta era ripetuta in due file e uno dei due non passava `region` — il
    parametro esisteva in `make_screen` da sempre e **non lo passava nessuno**,
    ottavo campo di questa forma in questo progetto.

    `dillo` riceve una riga da mettere nel log: una cattura ridotta che non si
    dichiara e' indistinguibile da un OCR che ha smesso di leggere.
    """
    if hwnd:
        # **Con WGC la fascia non si ritaglia**: la cattura arriva da sola, in
        # GPU, e il costo non dipende da quanto se ne guarda. Con PrintWindow
        # si', perche' li' il fotogramma si va a **prendere** e la copia dei
        # pixel e' tutto il costo: misurato su una finestra 1278x1391, 17,6 ms
        # per l'intera contro **6,2** per la fascia. E' la stessa idea di
        # `SoloRoi` e lo stesso guadagno, sulla finestra invece che sullo
        # schermo. La fascia sta **dentro** la sorgente e in frazioni, cosi' un
        # gioco che cambia misura non finisce a leggere il punto sbagliato.
        sorgente = make_screen(backend, monitor=monitor, hwnd=hwnd, dillo=dillo)
        fascia = fascia_da_roi(rois, margine)
        if rois and fascia and hasattr(sorgente, "fascia"):
            sorgente.fascia = fascia
            if dillo is not None:
                dillo(f"cattura: della finestra si legge la fascia fra il "
                      f"{fascia[0]:.0%} e il {fascia[1]:.0%} dell'altezza "
                      f"(margine {margine:g})")
        elif rois and dillo is not None:
            dillo("cattura: finestra intera (la cattura non costa per riga)")
        return sorgente
    if not rois:
        return make_screen(backend, monitor=monitor)
    dimensione = dimensione_monitor(monitor)
    regione = regione_da_roi(rois, dimensione, margine)
    dentro = make_screen(backend, monitor=monitor, region=regione)
    fuori = SoloRoi(dentro, regione, dimensione)
    if dillo is not None:
        left, top, right, bottom = regione
        dillo(
            f"cattura: solo la fascia {right - left}x{bottom - top} a ({left},{top}) "
            f"invece di {dimensione[0]}x{dimensione[1]} (margine {margine:g})"
        )
    return fuori


def apri_finestra(hwnd: int, backend: str = "finestra", dillo=None) -> ScreenSource:
    """La cattura di **una finestra sola**, col ripiego **dichiarato**.

    Ci sono due modi di prendere una finestra, e su questa macchina il migliore
    non si puo' usare:

    - **WGC** (`windows_capture`) e' quello giusto — asincrono, in GPU, regge il
      fullscreen esclusivo — e porta una libreria nativa che Smart App Control
      blocca in tutte le versioni pubblicate. Con lei e' bloccato anche l'altro
      pacchetto che espone la stessa API (`winrt-Windows.Graphics.Capture`), e
      con quello il suo `winrt-runtime`: non e' quella libreria, e' **ogni file
      nuovo**;
    - **PrintWindow** (`capture/printwindow.py`) sta in `user32.dll`, cioe' in
      Windows: niente da installare, niente reputazione da maturare. Costa di
      piu' ed e' sincrono, e su un gioco Direct3D puo' restituire nero.

    **Il ripiego si dichiara.** Un `ImportError: DLL load failed` non dice ne'
    cosa cadra' ne' cosa fare, e ripiegare in silenzio sarebbe peggio: si
    catturerebbe la stessa finestra con un'altra cosa, con un altro costo e con
    un modo di fallire diverso, e nel rapporto ci sarebbe scritto lo stesso
    nome. `dillo` riceve una riga per il registro; senza `dillo`, la riga va su
    `stderr`, perche' una rinuncia taciuta e' il difetto che tutto questo
    modulo esiste per togliere.

    `backend` vale `finestra`/`wgc` (prova WGC e ripiega) oppure `finestra-gdi`
    (PrintWindow e basta, per provarlo senza disinstallare niente).
    """
    from core import bloccati

    def _di(riga: str) -> None:
        if dillo is not None:
            dillo(riga)
        else:
            print(riga, file=sys.stderr)

    scelta = (backend or "finestra").lower()
    if scelta not in ("finestra-gdi", "printwindow", "gdi"):
        esito = bloccati.pezzo("wgc")
        if esito.ok:
            return FinestraSource(hwnd)
        _di("cattura: " + bloccati.spiega("wgc"))

    from capture.printwindow import PrintWindowSource

    return PrintWindowSource(hwnd)


def make_screen(backend: str = "auto", monitor: int = 1, region=None,
                hwnd: int | None = None, dillo=None) -> ScreenSource:
    """Costruisce la sorgente chiesta.

    `auto` prova dxcam e ripiega su mss **dicendolo al chiamante** tramite
    `.name`: un ripiego silenzioso qui farebbe misurare GDI credendo di misurare
    Desktop Duplication, e i due non hanno lo stesso costo.

    Nota sull'indice del monitor: `mss` numera da 1 (0 e' lo schermo virtuale
    che li unisce tutti), `dxcam` numera da 0. Tradurre qui evita che lo stesso
    numero in configurazione significhi due schermi diversi a seconda del
    backend — un errore che non da' errore, da' il monitor sbagliato.
    """
    scelta = (backend or "auto").lower()
    # **Se c'e' una finestra scelta, quella vince su tutto**, anche su `auto`:
    # averla scelta e' gia' la risposta alla domanda «cosa catturo».
    if hwnd or scelta in ("finestra", "wgc", "finestra-gdi"):
        if not hwnd:
            raise ValueError("il backend 'finestra' vuole l'hwnd della finestra da catturare")
        return apri_finestra(hwnd, scelta, dillo=dillo)
    if scelta in ("auto", "dxcam"):
        try:
            return DxcamSource(monitor=max(0, monitor - 1), region=region)
        except Exception:
            if scelta == "dxcam":
                raise
    if scelta in ("auto", "mss"):
        return MssSource(monitor=monitor, region=region)
    raise ValueError(f"backend di cattura sconosciuto: {backend}")
