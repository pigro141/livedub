"""Il sottotitolo tradotto, disegnato **sopra il gioco**.

La sostituzione grafica esisteva solo per l'MP4 (`tools/dub.py`), dove ffmpeg
disegna sul fotogramma. Dal vivo il fotogramma non passa da noi: il gioco lo
manda direttamente allo schermo. L'unico modo di coprirlo e' **una finestra
sopra**, senza bordi, sempre in primo piano, piazzata sulla ROI.

## Le tre cose che la rendono utilizzabile invece che fastidiosa

**Non deve rubare i clic.** Una finestra sopra il gioco che intercetta il mouse
rende ingiocabile il gioco. Su Windows si dichiara `WS_EX_TRANSPARENT`, e i clic
passano attraverso come se non ci fosse.

**Non deve rubare il fuoco.** `WS_EX_NOACTIVATE`: comparendo, una finestra
normale toglierebbe il fuoco al gioco — che in molti giochi vuol dire mettere in
pausa o perdere il puntatore.

**E deve sparire quando non serve.** Una banda nera perenne in mezzo allo schermo
e' peggio del sottotitolo che copre: la finestra si nasconde appena la battuta e'
finita.

## Il fondo

`nero` copre l'originale del tutto, ed e' il piu' sicuro. `sfocato` non si puo'
fare qui — sfocare vuol dire leggere i pixel sotto, e leggerli richiederebbe
catturare lo schermo a 30 Hz solo per questo, cioe' pagare una seconda cattura
per un effetto estetico. Chi vuole il blur usa l'MP4.
"""

from __future__ import annotations

import sys
import tkinter as tk


class Overlay:
    """Una finestra senza bordi sopra il gioco, con dentro il testo tradotto."""

    def __init__(
        self,
        root: tk.Misc,
        roi: tuple[float, float, float, float],
        *,
        colore: str = "#ffffff",
        fondo: str = "#000000",
        font: str = "Arial",
        font_frac: float = 0.038,
        opacita: float = 1.0,
    ) -> None:
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)  # niente bordi, niente barra del titolo
        self.top.attributes("-topmost", True)
        self.top.configure(bg=fondo)
        try:
            self.top.attributes("-alpha", max(0.1, min(1.0, opacita)))
        except tk.TclError:  # pragma: no cover - dipende dal window manager
            pass

        schermo_w = root.winfo_screenwidth()
        schermo_h = root.winfo_screenheight()
        x, y, w, h = roi
        self.geom = (
            max(1, int(schermo_w * w)),
            max(1, int(schermo_h * h)),
            int(schermo_w * x),
            int(schermo_h * y),
        )
        self.top.geometry("%dx%d+%d+%d" % self.geom)

        corpo = max(10, int(schermo_h * font_frac))
        self.etichetta = tk.Label(
            self.top,
            text="",
            fg=colore,
            bg=fondo,
            font=(font, corpo, "bold"),
            wraplength=self.geom[0] - 20,
            justify="center",
        )
        self.etichetta.pack(expand=True, fill="both")

        self._passante()
        self.top.withdraw()
        self._visibile = False

    def _passante(self) -> None:
        """Rende la finestra trasparente ai clic e incapace di prendere il fuoco.

        Senza queste due, l'overlay e' peggio del problema che risolve: il gioco
        smette di ricevere il mouse e perde il fuoco a ogni battuta. Fuori da
        Windows non si fa niente e si dichiara — meglio un overlay che ruba i clic
        di un overlay che finge di non farlo.
        """
        if sys.platform != "win32":
            print("overlay: clic passanti non disponibili qui", file=sys.stderr)
            return
        import ctypes
        from ctypes import wintypes

        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080  # niente icona sulla barra delle applicazioni

        self.top.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.top.winfo_id())
        u32 = ctypes.windll.user32
        u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.GetWindowLongW.restype = ctypes.c_long
        u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        stile = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(
            hwnd,
            GWL_EXSTYLE,
            stile | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
        )

    # -- uso ---------------------------------------------------------------

    def mostra(self, testo: str) -> None:
        testo = (testo or "").strip()
        if not testo:
            self.nascondi()
            return
        self.etichetta.configure(text=testo)
        if not self._visibile:
            self.top.deiconify()
            self.top.attributes("-topmost", True)
            self._visibile = True

    def nascondi(self) -> None:
        if self._visibile:
            self.top.withdraw()
            self._visibile = False

    def distruggi(self) -> None:
        try:
            self.top.destroy()
        except tk.TclError:  # pragma: no cover
            pass
