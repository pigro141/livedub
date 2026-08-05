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

import time
from dataclasses import dataclass

import numpy as np


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
            left, top, right, bottom = region
            self._box = {"left": left, "top": top, "width": right - left, "height": bottom - top}
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
    """

    name = "finestra"

    def __init__(self, hwnd: int) -> None:
        import threading

        from windows_capture import WindowsCapture

        self.hwnd = int(hwnd)
        self._lock = threading.Lock()
        self._ultimo: np.ndarray | None = None
        self._nuovo = False
        self._chiusa = False
        self._cattura = WindowsCapture(
            cursor_capture=False,  # il puntatore non e' contenuto del gioco
            draw_border=False,  # niente cornice gialla attorno al gioco
            window_hwnd=self.hwnd,
        )

        @self._cattura.event
        def on_frame_arrived(frame, control):  # noqa: ANN001
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
        try:
            self._ctrl.stop()
        except Exception:  # pragma: no cover
            pass


def make_screen(backend: str = "auto", monitor: int = 1, region=None, hwnd: int | None = None) -> ScreenSource:
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
    if hwnd or scelta in ("finestra", "wgc"):
        if not hwnd:
            raise ValueError("il backend 'finestra' vuole l'hwnd della finestra da catturare")
        return FinestraSource(hwnd)
    if scelta in ("auto", "dxcam"):
        try:
            return DxcamSource(monitor=max(0, monitor - 1), region=region)
        except Exception:
            if scelta == "dxcam":
                raise
    if scelta in ("auto", "mss"):
        return MssSource(monitor=monitor, region=region)
    raise ValueError(f"backend di cattura sconosciuto: {backend}")
