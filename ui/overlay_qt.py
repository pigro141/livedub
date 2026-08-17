"""Lo stesso overlay, in **Qt**: solo i pixel a schermo.

Tutto quello che decide *cosa* disegnare — geometria, misura del carattere,
quando comparire e quando sparire — sta in `ui.overlay.OverlayBase` e non viene
riscritto qui. Questo file mette una finestra sopra il gioco e ci appoggia la
tela che il pittore ha gia' prodotto.

**La differenza vera con la versione Tk e' il buco.** Tk non sa fare l'alfa per
pixel, quindi il trasparente e' un **colore-chiave**: si dichiara un colore che
sparisce e si sta attenti che il disegno non lo contenga per caso (`su_chiave`,
che sposta di uno i pixel colpevoli). Qt lo fa davvero, per pixel, con
`WA_TranslucentBackground`: la tela RGBA va a schermo com'e', senza colore
riservato e senza collisioni possibili.

**Le tre proprieta' di Windows restano identiche, e non sono rifiniture**: fuori
dalla cattura, trasparente ai clic, incapace di prendere il fuoco. Qt ne offre
due come flag, ma si applicano lo stesso anche a mano: sono la condizione
perche' il resto della catena funzioni, e un flag che il window manager
interpreta a modo suo non e' una garanzia.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from ui.overlay import OverlayBase


def schermo_fisico() -> tuple[tuple[int, int], float]:
    """Lo schermo in pixel **veri**, e di quanto Qt li scala.

    La catena ragiona in pixel del fotogramma catturato, che sono fisici; Qt
    piazza le finestre in pixel logici. Con Windows al 100% i due coincidono e
    non se ne parla; al 125% la finestra cadrebbe un quarto piu' in la' di dove
    sta il sottotitolo — cioe' il difetto «il riquadro sta dove il testo non
    c'e'», ma causato da un'unita' di misura invece che dalla geometria.
    """
    s = QGuiApplication.primaryScreen()
    dpr = float(s.devicePixelRatio() or 1.0)
    g = s.geometry()
    return (int(g.width() * dpr), int(g.height() * dpr)), dpr


class OverlayQt(OverlayBase):
    """Una finestra senza bordi sopra il gioco, con dentro il testo tradotto."""

    def __init__(self, roi: tuple[float, float, float, float], **kw) -> None:
        schermo, self.dpr = schermo_fisico()
        super().__init__(roi, schermo=schermo, **kw)

        self.top = QWidget()
        flag = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.top.setWindowFlags(flag)
        self.top.setAttribute(Qt.WA_ShowWithoutActivating, True)
        if self.trasparente:
            self.top.setAttribute(Qt.WA_TranslucentBackground, True)
        self.top.setWindowOpacity(self.opacita)
        self.etichetta = QLabel(self.top)
        self.etichetta.setAttribute(Qt.WA_TranslucentBackground, self.trasparente)
        self.etichetta.setScaledContents(False)
        self.etichetta.move(0, 0)
        self._pixmap = None

        self._piazza(self.geom)
        # **La finestra va creata prima di poterle cambiare gli stili.** `winId()`
        # la realizza; senza, `SetWindowLongW` scriverebbe su un handle che non
        # esiste ancora e le tre proprieta' non sarebbero applicate — in silenzio,
        # che qui vuol dire l'OCR che ricomincia a leggere noi.
        self.top.winId()
        self._passante()
        self.top.hide()

    # -- le cinque cose che il front-end deve fare --------------------------

    def _dipingi(self, tela, geom) -> None:
        if not self.trasparente:
            tela = tela.convert("RGB").convert("RGBA")
        dati = tela.tobytes("raw", "RGBA")
        img = QImage(dati, tela.width, tela.height, tela.width * 4,
                     QImage.Format_RGBA8888)
        # `copy()` perche' `QImage` non possiede i byte: senza, il buffer di
        # Python viene liberato e a schermo finisce spazzatura o niente.
        self._pixmap = QPixmap.fromImage(img.copy())
        self.etichetta.setPixmap(self._pixmap)
        self.etichetta.resize(tela.width, tela.height)
        if geom is not None:
            self._piazza(geom)

    def _piazza(self, geom) -> None:
        w, h, x, y = geom
        d = self.dpr
        self.top.setGeometry(int(x / d), int(y / d), int(w / d), int(h / d))
        self.etichetta.setGeometry(0, 0, int(w / d), int(h / d))

    def _apri(self) -> None:
        self.top.show()
        self.top.raise_()

    def _chiudi(self) -> None:
        self.top.hide()

    def geometria(self) -> str:
        g = self.top.geometry()
        return f"{g.width()}x{g.height()}+{g.x()}+{g.y()}"

    def distruggi(self) -> None:
        try:
            self.top.close()
            self.top.deleteLater()
        except Exception:  # pragma: no cover
            pass

    # -- Windows ------------------------------------------------------------

    def _hwnd(self) -> int:
        return int(self.top.winId())

    def _passante(self) -> None:
        """Le stesse tre proprieta' della versione Tk, chieste a Windows a mano."""
        if sys.platform != "win32":
            print("overlay: clic passanti ed esclusione dalla cattura non "
                  "disponibili qui — l'OCR leggera' il nostro testo", file=sys.stderr)
            return
        import ctypes
        from ctypes import wintypes

        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080

        u32 = ctypes.windll.user32
        hwnd = self._hwnd()
        u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.GetWindowLongW.restype = ctypes.c_long
        u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        stile = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(
            hwnd, GWL_EXSTYLE,
            stile | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
        )
        self._dichiara_esclusione()

    def esclusione(self, attiva: bool) -> None:
        super().esclusione(attiva)
        if sys.platform != "win32":
            return
        import ctypes

        WDA_EXCLUDEFROMCAPTURE = 0x00000011
        ctypes.windll.user32.SetWindowDisplayAffinity(
            self._hwnd(), WDA_EXCLUDEFROMCAPTURE if attiva else 0
        )
