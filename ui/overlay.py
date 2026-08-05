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

## Il fondo sfocato, che credevo impossibile e non lo e'

Avevo scritto qui che dal vivo il blur non si poteva fare, perche' sfocare vuol
dire leggere i pixel sotto e leggerli richiederebbe una seconda cattura dello
schermo. **Era sbagliato**: la catena cattura gia' il fotogramma a 30 Hz per
darlo all'OCR. Quei pixel sono in mano nostra, e prenderli costa un ritaglio.

Quindi il fondo e' la ROI **sfocata**: l'originale diventa illeggibile ma il gioco
resta visibile sotto, molto meno invadente di un rettangolo nero. Il rettangolo
resta come ripiego dichiarato per quando il fotogramma non c'e'.

## E si copre solo dove c'e' il testo

Coprire tutta la ROI vuol dire mettere una fascia larga mezzo schermo anche per
una battuta di due parole. Il riquadro si stringe quindi sull'**inchiostro vero**,
trovato con la stessa maschera che usa l'OCR (`vision.lines.text_mask`): non una
stima della posizione del testo, letteralmente i pixel che l'OCR ha letto.
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
        blur: float = 0.12,
    ) -> None:
        # Quanto sfocare, come frazione del lato corto del ritaglio: in frazione e
        # non in pixel, cosi' lo stesso valore vale a 1080p e a 1440p.
        self.blur = max(0.0, blur)
        self._foto = None
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

    def mostra(self, testo: str, sfondo=None, box=None) -> None:
        """Mostra il testo, sfocando `sfondo` sotto e stringendosi su `box`.

        `sfondo` e' il ritaglio della ROI dal fotogramma corrente (BGR), `box` il
        rettangolo dell'inchiostro **dentro** quel ritaglio, in pixel. Senza i
        due, si ricade sul rettangolo pieno su tutta la ROI — che e' il
        comportamento di prima, dichiarato come ripiego e non come scelta.
        """
        testo = (testo or "").strip()
        if not testo:
            self.nascondi()
            return

        self._foto = None
        geom = self.geom
        if sfondo is not None and box is not None:
            fatto = self._prepara_sfondo(sfondo, box)
            if fatto is not None:
                self._foto, geom = fatto

        if self._foto is not None:
            self.etichetta.configure(text=testo, image=self._foto, compound="center")
        else:
            self.etichetta.configure(text=testo, image="", compound="none")
        self.etichetta.configure(wraplength=max(80, geom[0] - 16))
        self.top.geometry("%dx%d+%d+%d" % geom)

        if not self._visibile:
            self.top.deiconify()
            self.top.attributes("-topmost", True)
            self._visibile = True

    def _prepara_sfondo(self, roi, box):
        """La ROI sfocata, ritagliata sull'inchiostro. `None` se non si puo'.

        Il margine attorno al riquadro non e' estetica: l'inchiostro ha un
        contorno e un'ombra, e un ritaglio esatto sui pixel accesi lascerebbe
        scoperto proprio il bordo delle lettere vecchie — cioe' l'unica parte che
        si vede ancora sotto quelle nuove.
        """
        try:
            import cv2
            import numpy as np
            from PIL import Image, ImageTk
        except ImportError:  # pragma: no cover - dipende dall'ambiente
            return None

        h_roi, w_roi = roi.shape[:2]
        if not h_roi or not w_roi:
            return None
        x, y, w, h = box
        m = max(6, int(0.02 * w_roi))
        x0, y0 = max(0, x - m), max(0, y - m)
        x1, y1 = min(w_roi, x + w + m), min(h_roi, y + h + m)
        if x1 - x0 < 8 or y1 - y0 < 8:
            return None

        pezzo = np.ascontiguousarray(roi[y0:y1, x0:x1])
        k = max(3, (int(min(pezzo.shape[:2]) * self.blur) // 2) * 2 + 1)
        pezzo = cv2.GaussianBlur(pezzo, (k, k), 0)
        if pezzo.ndim == 3 and pezzo.shape[2] >= 3:
            pezzo = cv2.cvtColor(pezzo[:, :, :3], cv2.COLOR_BGR2RGB)

        # Dalla ROI allo schermo: il ritaglio e' in pixel del fotogramma, la
        # finestra in pixel dello schermo, e i due possono non coincidere.
        sx = self.geom[0] / float(w_roi)
        sy = self.geom[1] / float(h_roi)
        larg = max(40, int((x1 - x0) * sx))
        alt = max(24, int((y1 - y0) * sy))
        img = Image.fromarray(pezzo).resize((larg, alt))
        foto = ImageTk.PhotoImage(img, master=self.top)
        geom = (larg, alt, self.geom[2] + int(x0 * sx), self.geom[3] + int(y0 * sy))
        return foto, geom

    def nascondi(self) -> None:
        if self._visibile:
            self.top.withdraw()
            self._visibile = False

    def distruggi(self) -> None:
        try:
            self.top.destroy()
        except tk.TclError:  # pragma: no cover
            pass
