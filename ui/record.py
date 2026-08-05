"""La telecamera virtuale: il gioco **col sottotitolo tradotto sopra**, per OBS.

## Perche' serve, e perche' e' nata da una cura

L'overlay dal vivo e' dichiarato **fuori dalla cattura**
(`WDA_EXCLUDEFROMCAPTURE`), e non e' un dettaglio: senza, la finestra rientra nel
fotogramma che diamo all'OCR e il programma legge il proprio testo invece del
sottotitolo del gioco — misurato, il 100% dei suoi pixel.

Ma «fuori dalla cattura» vale per **tutte** le catture, non solo per la nostra.
Uno streamer che mette «Cattura schermo» in OBS vedrebbe il gioco senza il
sottotitolo tradotto: nella sua diretta il doppiaggio si sente e non si legge.
La cura di un difetto ne ha creato un altro, e questo modulo e' la risposta.

## Cosa manda, e perche' e' gia' sincronizzato

Il fotogramma che il ciclo video ha appena catturato, con sopra **la stessa
identica tela** che la finestra sta mostrando a schermo in quell'istante — non
una seconda composizione fatta apposta. Sono gli stessi pixel: quello che si
vede sul monitor e quello che finisce in OBS non possono divergere, perche' sono
la stessa cosa disegnata due volte. Una seconda strada di disegno per la
registrazione sarebbe l'ennesimo doppione destinato a divergere al primo
ritocco — questo progetto ne ha gia' pagati abbastanza.

## Il costo, che decide la risoluzione

Un fotogramma 2560x1440 in RGB pesa 11 MB: trenta al secondo sono 330 MB/s da
copiare e consegnare, dentro il **thread video**, dove in questo progetto un
costo non si somma ma si amplifica. Quindi si manda ridimensionato
(`record.width`, 1280 di default): OBS riscala comunque, e la differenza fra
1280 e 2560 su un sottotitolo non si vede.

## Se non c'e', lo dice

La telecamera virtuale la fornisce OBS, che la registra in Windows quando lo si
installa. Senza, `pyvirtualcam` non trova nessun ricevitore: qui si dichiara e si
va avanti senza registrare, perche' un ripiego silenzioso su una funzione che
l'utente ha **acceso apposta** vuol dire una diretta senza sottotitoli e nessuna
idea del perche'.
"""

from __future__ import annotations

import sys


class TelecameraVirtuale:
    """Una sorgente video che OBS vede come una webcam.

    Si apre alla prima consegna e non prima: la dimensione la decide il primo
    fotogramma, e chiederla in anticipo vorrebbe dire indovinare la risoluzione
    dello schermo in un posto che non la conosce.
    """

    def __init__(self, larghezza: int = 1280, fps: float = 30.0) -> None:
        self.larghezza = max(160, int(larghezza))
        self.fps = max(1.0, float(fps))
        self.cam = None
        self.attiva = False
        self.errore = ""
        self._forma = None

    # -- ciclo di vita -----------------------------------------------------

    def _apri(self, w: int, h: int) -> bool:
        try:
            import pyvirtualcam
        except ImportError:
            self.errore = "manca pyvirtualcam (pip install pyvirtualcam)"
            return False
        try:
            self.cam = pyvirtualcam.Camera(width=w, height=h, fps=int(round(self.fps)))
        except Exception as exc:
            # Il caso normale e' «OBS non installato», e va detto con il rimedio
            # dentro: senza OBS non esiste nessuna telecamera virtuale da usare.
            self.errore = f"{type(exc).__name__}: {exc}"
            self.cam = None
            return False
        self._forma = (w, h)
        self.attiva = True
        return True

    def chiudi(self) -> None:
        if self.cam is not None:
            try:
                self.cam.close()
            except Exception:  # pragma: no cover
                pass
        self.cam = None
        self.attiva = False

    # -- consegna ----------------------------------------------------------

    def manda(self, frame_bgr, tela=None, x: int = 0, y: int = 0) -> bool:
        """Manda il fotogramma, con `tela` (RGBA) sovrapposta in `(x, y)`.

        `x` e `y` sono in pixel dello **schermo**, cioe' gli stessi con cui la
        finestra e' piazzata: la tela va incollata dov'e' davvero, non dove
        starebbe se la si ricalcolasse.
        """
        import cv2
        import numpy as np

        h0, w0 = frame_bgr.shape[:2]
        if not w0 or not h0:
            return False
        pieno = frame_bgr[:, :, :3]
        if tela is not None:
            pieno = pieno.copy()
            _incolla(pieno, tela, x, y)

        w = self.larghezza
        hh = int(round(h0 * w / w0)) & ~1  # pari: molti ricevitori lo pretendono
        if (w, hh) != self._forma and self.attiva:
            self.chiudi()
        if not self.attiva and not self._apri(w, hh):
            return False
        piccolo = cv2.resize(pieno, (w, hh), interpolation=cv2.INTER_AREA)
        try:
            self.cam.send(np.ascontiguousarray(piccolo[:, :, ::-1]))  # BGR -> RGB
            return True
        except Exception as exc:  # pragma: no cover - la telecamera se n'e' andata
            self.errore = f"{type(exc).__name__}: {exc}"
            self.chiudi()
            return False


def _incolla(frame, tela, x: int, y: int) -> None:
    """Sovrappone una tela RGBA al fotogramma BGR, rispettando l'alfa."""
    import numpy as np

    a = np.asarray(tela)
    if a.ndim != 3 or a.shape[2] != 4:
        return
    h, w = a.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sotto = frame[y0:y1, x0:x1].astype(np.float32)
    sopra = a[y0 - y : y1 - y, x0 - x : x1 - x]
    alfa = sopra[:, :, 3:4].astype(np.float32) / 255.0
    rgb = sopra[:, :, :3][:, :, ::-1].astype(np.float32)  # RGBA -> BGR
    frame[y0:y1, x0:x1] = (sotto * (1 - alfa) + rgb * alfa).astype(np.uint8)


def apri_o_spiega(cfg_record, coda=None) -> "TelecameraVirtuale | None":
    """La telecamera se si puo', `None` con una spiegazione se no."""
    cam = TelecameraVirtuale(cfg_record.width, cfg_record.fps)
    if cam._apri(cam.larghezza, 2):  # una prova a due righe, per sapere subito
        cam.chiudi()
        cam._forma = None
        return cam
    msg = (f"! telecamera virtuale non disponibile: {cam.errore}\n"
           "  serve OBS Studio installato (registra lui la telecamera virtuale)")
    if coda is not None:
        coda.put(("nota", msg))
    else:
        print(msg, file=sys.stderr)
    return None
