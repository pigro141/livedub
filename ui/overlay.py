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

Quindi il fondo e' il ritaglio **sfocato**: l'originale diventa illeggibile ma il
gioco resta visibile sotto, molto meno invadente di un rettangolo nero. Il
rettangolo resta come ripiego dichiarato per quando il fotogramma non c'e'.

## E si copre solo dove serve — che non e' dove stava il testo vecchio

Coprire tutta la ROI vuol dire mettere una fascia larga mezzo schermo anche per
una battuta di due parole, e il primo tentativo la stringeva sull'**inchiostro
vero** (la stessa maschera che usa l'OCR). Guardandolo a schermo si e' visto
il difetto che nessuna verifica poteva vedere: la finestra veniva dimensionata
sul testo **originale**, e dentro ci si disegnava quello **tradotto**. Una
battuta che in inglese occupa tre righe dove l'italiano ne occupava una veniva
mostrata a meta', ritagliata sopra e sotto — cioe' illeggibile, che e' il
difetto peggiore possibile per un sottotitolo.

Adesso la finestra e' il **massimo fra i due**: l'inchiostro vecchio (per
coprirlo) e il testo nuovo (per leggerlo). Il calcolo sta tutto in
`disposizione()`, che e' una funzione pura e sta fuori da Tk apposta: e' la
parte che puo' sbagliare in silenzio, e dentro un widget si verificherebbe solo
guardandola.
"""

from __future__ import annotations

import sys
import tkinter as tk


def disposizione(schermo, rett, pezzo_wh, box, testo_wh, margine=0.02):
    """Dove va la finestra, e che pezzo di fotogramma le va ritagliato dietro.

    Tutto in pixel, e ogni ingresso dichiara in che pixel e':

    - `schermo` `(w, h)`, pixel dello schermo;
    - `rett` `(x, y, w, h)` del ritaglio dentro il fotogramma, **normalizzato**;
    - `pezzo_wh` `(w, h)` di quel ritaglio, pixel del fotogramma;
    - `box` `(x, y, w, h)` dell'inchiostro vecchio dentro il ritaglio, pixel del
      fotogramma;
    - `testo_wh` `(w, h)` che il testo tradotto chiede, pixel dello schermo.

    Torna `(taglio, geom)`: `taglio` `(x0, y0, x1, y1)` da ritagliare nel pezzo,
    `geom` `(w, h, x, y)` della finestra sullo schermo.

    **La conversione fotogramma -> schermo passa dalle coordinate normalizzate**,
    non dal rapporto fra due rettangoli che si suppongono proporzionali: il
    ritaglio occupa una frazione nota del fotogramma, e quella stessa frazione
    dello schermo e' dove va disegnato. Cosi' una cattura che scala, o che non ha
    le proporzioni dello schermo, non sposta niente.

    La finestra si ancora **in basso** all'inchiostro vecchio e cresce verso
    l'alto: e' li' che l'occhio sta gia' guardando, e sotto c'e' il bordo dello
    schermo.
    """
    sw, sh = schermo
    rx, ry, rw, rh = rett
    pw, ph = max(1, int(pezzo_wh[0])), max(1, int(pezzo_wh[1]))
    bx, by, bw, bh = box

    px0, py0 = rx * sw, ry * sh  # il pezzo, sullo schermo
    pws, phs = rw * sw, rh * sh
    sx, sy = pws / pw, phs / ph  # pixel di schermo per pixel di fotogramma

    m = max(6.0, margine * pws)
    tw, th = testo_wh
    larg = min(float(sw), max(bw * sx + 2 * m, tw + 2 * m))
    alt = min(float(sh), max(bh * sy + 2 * m, th + m))

    x = px0 + (bx + bw / 2.0) * sx - larg / 2.0
    y = py0 + (by + bh) * sy + m - alt
    x = min(max(x, 0.0), sw - larg)
    y = min(max(y, 0.0), sh - alt)

    # Il ritaglio corrispondente, riportato dentro il pezzo. Quando la finestra
    # e' piu' alta del pezzo il ritaglio si ferma al bordo e l'immagine viene
    # stirata: e' sfocata, quindi non si vede — e stirare un fondo e' meglio che
    # tagliare una riga di testo.
    x0 = int(round((x - px0) / sx))
    y0 = int(round((y - py0) / sy))
    x1 = int(round((x + larg - px0) / sx))
    y1 = int(round((y + alt - py0) / sy))
    x0, x1 = max(0, min(pw - 1, x0)), max(1, min(pw, x1))
    y0, y1 = max(0, min(ph - 1, y0)), max(1, min(ph, y1))
    if x1 <= x0:
        x0, x1 = 0, pw
    if y1 <= y0:
        y0, y1 = 0, ph
    return (x0, y0, x1, y1), (int(round(larg)), int(round(alt)), int(round(x)), int(round(y)))


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
        modo: str = "blur",
        blur: float = 12.0,
    ) -> None:
        # `blur` e' il raggio della sfocatura in pixel **a 1080p**, riscalato con
        # l'altezza del fotogramma: e' la stessa grandezza che `tools/dub.py`
        # passa a `boxblur` per l'MP4, cosi' i due non divergono.
        self.blur = max(0.0, blur)
        self.modo = (modo or "blur").lower()
        self._foto = None
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)  # niente bordi, niente barra del titolo
        self.top.attributes("-topmost", True)
        self.top.configure(bg=fondo)
        try:
            self.top.attributes("-alpha", max(0.1, min(1.0, opacita)))
        except tk.TclError:  # pragma: no cover - dipende dal window manager
            pass
        # `nessuno` vuol dire "niente sfondo", e senza questa riga voleva dire
        # "sfondo del colore di `background`", cioe' il riquadro con un altro
        # nome. Il colore dichiarato diventa il buco da cui si vede il gioco.
        if self.modo == "nessuno":
            try:
                self.top.attributes("-transparentcolor", fondo)
            except tk.TclError:  # pragma: no cover - solo Windows
                print("overlay: sfondo trasparente non disponibile qui", file=sys.stderr)

        self.schermo = (root.winfo_screenwidth(), root.winfo_screenheight())
        self.font_frac = font_frac
        self.geom = self._geom_roi(roi)
        self.top.geometry("%dx%d+%d+%d" % self.geom)

        corpo = max(10, int(self.schermo[1] * font_frac))
        self.etichetta = tk.Label(
            self.top,
            text="",
            fg=colore,
            bg=fondo,
            font=(font, corpo, "bold"),
            wraplength=self.geom[0] - 20,
            justify="center",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        self.etichetta.pack(expand=True, fill="both")

        self._passante()
        self.top.withdraw()
        self._visibile = False

    def _geom_roi(self, roi) -> tuple[int, int, int, int]:
        sw, sh = self.schermo
        x, y, w, h = roi
        return (max(1, int(sw * w)), max(1, int(sh * h)), int(sw * x), int(sh * y))

    def riposiziona(self, roi) -> None:
        """La ROI e' cambiata (il selettore d'area), e la finestra deve seguirla.

        Senza, l'overlay resta dove stava la ROI di partenza: si sceglie l'area
        col mouse — che e' il modo dichiarato di usare questo programma — e il
        riquadro compare da un'altra parte. Il ripiego a rettangolo pieno e' il
        solo che ne dipenda davvero, ma sbagliarlo la' vuol dire una banda nera
        in mezzo allo schermo.
        """
        self.geom = self._geom_roi(roi)
        self.etichetta.configure(wraplength=max(80, self.geom[0] - 20))

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

    def mostra(self, testo: str, sfondo=None, box=None, rett=None) -> None:
        """Mostra il testo, sfocando `sfondo` sotto e stringendosi dove serve.

        `sfondo` e' un ritaglio del fotogramma (BGR), `rett` dice che frazione
        del fotogramma sia — normalizzata, come la ROI — e `box` il rettangolo
        dell'inchiostro vecchio **dentro** quel ritaglio, in pixel. Senza i tre,
        si ricade sul rettangolo pieno su tutta la ROI: e' il comportamento di
        prima, dichiarato come ripiego e non come scelta.
        """
        testo = (testo or "").strip()
        if not testo:
            self.nascondi()
            return

        self._foto = None
        geom = self.geom
        if sfondo is not None and box is not None and rett is not None:
            fatto = self._prepara_sfondo(testo, sfondo, box, rett)
            if fatto is not None:
                self._foto, geom = fatto
        if self._foto is None:
            self.etichetta.configure(
                text=testo, image="", compound="none", wraplength=max(80, geom[0] - 16)
            )
        self.top.geometry("%dx%d+%d+%d" % geom)

        if not self._visibile:
            self.top.deiconify()
            self.top.attributes("-topmost", True)
            self._visibile = True

    def _misura(self, testo: str, larghezza_max: int) -> tuple[int, int]:
        """Quanto spazio chiede il testo, mandandolo a capo a `larghezza_max`.

        Si chiede a Tk invece di stimarlo: l'a-capo lo fa lui, e una stima che
        sbagliasse di una riga rifarebbe esattamente il difetto che questa
        funzione esiste per chiudere.
        """
        self.etichetta.configure(
            text=testo, image="", compound="none", wraplength=max(40, larghezza_max)
        )
        self.etichetta.update_idletasks()
        return int(self.etichetta.winfo_reqwidth()), int(self.etichetta.winfo_reqheight())

    def _prepara_sfondo(self, testo, pezzo, box, rett):
        """Lo sfondo pronto e la geometria della finestra. `None` se non si puo'.

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

        h_pezzo, w_pezzo = pezzo.shape[:2]
        if not h_pezzo or not w_pezzo:
            return None

        # L'a-capo alla larghezza del pezzo: e' la stessa a cui va a capo il
        # gioco, perche' il pezzo e' largo quanto la ROI.
        sw = self.schermo[0]
        largh_max = int(rett[2] * sw) - 2 * max(6, int(0.02 * rett[2] * sw))
        testo_wh = self._misura(testo, largh_max)

        taglio, geom = disposizione(
            self.schermo, rett, (w_pezzo, h_pezzo), box, testo_wh
        )
        x0, y0, x1, y1 = taglio
        larg, alt = geom[0], geom[1]
        if larg < 24 or alt < 16:
            return None

        if self.modo == "nessuno":
            self.etichetta.configure(
                text=testo, image="", compound="none", wraplength=max(40, larg - 16)
            )
            return None, geom

        if self.modo == "riquadro":
            fetta = np.zeros((y1 - y0, x1 - x0, 3), dtype=np.uint8)
        else:
            fetta = np.ascontiguousarray(pezzo[y0:y1, x0:x1])
            # Il raggio e' dichiarato a 1080p e segue l'altezza del fotogramma:
            # a 1440p le lettere sono piu' grandi e una sfocatura in pixel fissi
            # ne lascerebbe leggere la forma. Il fotogramma non ce l'abbiamo
            # intero, ma il pezzo e' alto `rett[3]` di lui.
            alt_frame = h_pezzo / max(1e-6, rett[3])
            raggio = max(1.0, self.blur * alt_frame / 1080.0)
            fetta = cv2.GaussianBlur(fetta, (0, 0), sigmaX=raggio, sigmaY=raggio)
            if fetta.ndim == 3 and fetta.shape[2] >= 3:
                fetta = cv2.cvtColor(fetta[:, :, :3], cv2.COLOR_BGR2RGB)

        img = Image.fromarray(fetta).resize((larg, alt))
        foto = ImageTk.PhotoImage(img, master=self.top)
        self.etichetta.configure(
            text=testo, image=foto, compound="center", wraplength=max(40, larg - 16)
        )
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
