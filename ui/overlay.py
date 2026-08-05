"""Il sottotitolo tradotto, disegnato **sopra il gioco**.

La sostituzione grafica esisteva solo per l'MP4 (`tools/dub.py`), dove ffmpeg
disegna sul fotogramma. Dal vivo il fotogramma non passa da noi: il gioco lo
manda direttamente allo schermo. L'unico modo di coprirlo e' **una finestra
sopra**, senza bordi, sempre in primo piano, piazzata sul sottotitolo.

## La cosa che veniva prima di tutte, e che non era stata vista

**La nostra finestra sta sullo schermo, e lo schermo e' cio' che catturiamo.**
La catena prende un fotogramma a 30 Hz per darlo all'OCR: dentro quel fotogramma
c'era anche l'overlay. Misurato — non supposto — mettendo a schermo una finestra
verde e guardando i pixel catturati: **il 100%** dei suoi pixel finiva nella
cattura, con `mss` e con `dxcam`. Da li' l'OCR non leggeva piu' il sottotitolo del
gioco: leggeva noi, e le righe sparivano.

Il rimedio e' una riga di Windows: `WDA_EXCLUDEFROMCAPTURE`. La finestra resta
sul monitor e sparisce da qualunque cattura — e' la stessa funzione con cui le
applicazioni nascondono le password dalla condivisione schermo. Verificato dopo:
**0%**. Non e' un'ottimizzazione, e' la condizione perche' il resto funzioni.

## Si cancella la scritta, non il riquadro

Sfocare un rettangolo largo quanto la ROI e' facile e sbagliato: si spegne mezzo
schermo per coprire una riga di testo. Si tocca **solo la riga che l'OCR ha
letto**, ognuna larga quanto lei. Tutto il resto della finestra e' un **buco**:
si vede il gioco, intatto, perche' li' non c'e' niente da coprire.

E la domanda giusta non era «rendere illeggibile» ma «far sembrare che quel
sottotitolo non ci sia mai stato», perche' sopra ci va il nostro e due
sottotitoli sovrapposti si vedono anche quando uno e' sfocato. Confrontati sulla
stessa riga vera: sfocare la striscia lascia una fascia grigia, sfocare i soli
glifi li lascia leggibili, il rettangolo pieno e' una macchia. **Ricostruire lo
sfondo** (`cancella`, il default) la fa sparire.

Il buco e' un colore-chiave (`CHIAVE`) dichiarato trasparente da Windows. E' un
quasi-nero apposta: i bordi antialiasati del testo sfumano verso di lui, e uno
sfumato verso il nero e' esattamente il contorno che i sottotitoli hanno gia'.

## E il testo copia quello del gioco

Il carattere non e' una scelta di gusto: **misura e colore si prendono dal
sottotitolo che si sta coprendo**. L'altezza della banda dice quanto e' grande il
carattere del gioco, il colore medio dell'inchiostro dice di che colore e'. Cosi'
la battuta tradotta si posa dove stava quella originale, della stessa taglia e
dello stesso colore, e sembra il sottotitolo del gioco invece di un cartello
appiccicato sopra. L'utente puo' sempre forzare `translate.font_frac` e
`translate.color`; a zero e vuoto valgono "come il gioco".

## Un solo pittore per due usi

`dipingi()` e' puro: prende i pixel e torna un'immagine RGBA con la sua
posizione. La usa la finestra dal vivo **e** la usa `tools/overlay_mp4.py` per
montare un video di come verrebbe. Se fossero due disegnatori diversi, il video
mostrerebbe una cosa e il vivo un'altra — che e' esattamente com'e' nato il
difetto precedente, con ffmpeg che disegnava per l'MP4 e nessuno che avesse mai
guardato il vivo.
"""

from __future__ import annotations

import sys
import tkinter as tk
from functools import lru_cache

# Il colore che Windows rende trasparente. Quasi nero, e non magenta: i pixel di
# bordo del testo sfumano verso di lui, e devono sfumare verso qualcosa che
# assomigli a un contorno.
CHIAVE = "#010203"
CHIAVE_RGB = (1, 2, 3)

# Da nome a file, per PIL. Il nome basta a Tk ma non a Pillow, che vuole un file.
FONT_FILE = {
    "arial": "arialbd.ttf",
    "verdana": "verdanab.ttf",
    "tahoma": "tahomabd.ttf",
    "segoe ui": "seguisb.ttf",
    "calibri": "calibrib.ttf",
    "impact": "impact.ttf",
}


@lru_cache(maxsize=64)
def carica_font(nome: str, corpo: int):
    """Il font di sistema alla misura chiesta, con un ripiego che non esplode.

    In cache perche' `corpo_del_gioco` ne apre fino a otto per battuta cercando
    la misura giusta, e questo gira **nel thread video**: li' un costo si
    amplifica invece di sommarsi, che e' la lezione piu' cara di questo progetto.
    """
    from PIL import ImageFont

    for candidato in (FONT_FILE.get((nome or "").lower().strip()), "arialbd.ttf", "arial.ttf"):
        if not candidato:
            continue
        try:
            return ImageFont.truetype(candidato, corpo)
        except OSError:
            continue
    return ImageFont.load_default()


def corpo_del_gioco(bande, scala: float, nome_font: str) -> int:
    """Quanto e' alto, in punti, il carattere che il gioco sta usando.

    Non si stima con un coefficiente: si **misura per confronto**. La banda alta
    `h` pixel e' l'inchiostro di una riga da ascendenti a discendenti; si cerca
    quindi il corpo il cui `Ag` occupa la stessa altezza. Un coefficiente fisso
    («il corpo e' 1,4 volte l'inchiostro») sarebbe giusto per un font solo, e il
    font lo sceglie l'utente.
    """
    # **La mediana e non il massimo.** Due righe vicine possono saldarsi in una
    # banda sola, e una banda doppia farebbe scrivere la traduzione al doppio
    # della taglia — misurato su un fotogramma vero, il testo veniva grande la
    # meta' in piu' del sottotitolo che stava coprendo.
    import statistics

    alta = statistics.median(sorted(y1 - y0 for _, y0, _, y1 in bande)) * scala
    corpo = max(8, int(alta))
    for _ in range(8):
        f = carica_font(nome_font, corpo)
        x0, y0, x1, y1 = f.getbbox("Ag")
        h = max(1, y1 - y0)
        if abs(h - alta) <= 1:
            break
        corpo = max(8, int(round(corpo * alta / h)))
    return corpo


class MisuraCarattere:
    """Ricorda quanto e' grande il carattere del gioco, contro le dissolvenze.

    Misurato su un fotogramma solo, il corpo segue la **dissolvenza**: GTA V fa
    comparire il sottotitolo sfumando, e a meta' sfumatura la maschera prende
    solo il cuore dei glifi. Misurato su fotogrammi veri della stessa battuta:
    23 punti a un istante, 38 mezzo secondo dopo — e a schermo si vedeva una
    battuta scritta in piccolo in mezzo alle altre.

    Un sottotitolo non cambia taglia da solo, quindi della misura istantanea si
    tiene **la piu' grande vista**: la dissolvenza puo' solo rimpicciolire.
    L'unica cosa che potrebbe gonfiarla e' due righe saldate in una banda sola,
    e quella si riconosce perche' arriva quasi doppia: si scarta.
    """

    def __init__(self) -> None:
        self.corpo = 0

    def azzera(self) -> None:
        self.corpo = 0

    def aggiorna(self, bande, scala: float, nome_font: str) -> int:
        c = corpo_del_gioco(bande, scala, nome_font)
        if self.corpo and c > 1.6 * self.corpo:
            return self.corpo  # una banda saldata, non un carattere piu' grande
        self.corpo = max(self.corpo, c)
        return self.corpo


def colore_del_gioco(rgb) -> tuple[int, int, int]:
    """Il colore dell'inchiostro, riportato alla sua luminosita' vera.

    La media sui pixel mascherati comprende i bordi scuri dei glifi e viene
    quindi sempre piu' scura del colore vero: un bianco misurato 180 e' un bianco
    255 con dentro l'antialiasing. Si tiene la **tinta** e si rialza la
    luminosita' portando il canale piu' alto al massimo — cosi' il giallo di un
    personaggio resta giallo e il bianco torna bianco.
    """
    r, g, b = (max(0.0, float(v)) for v in rgb)
    picco = max(r, g, b)
    if picco < 1.0:
        return (255, 255, 255)
    k = 255.0 / picco
    return tuple(int(min(255, round(v * k))) for v in (r, g, b))


def inchiostro(frame, cfg):
    """Dove sta il sottotitolo del gioco in questo fotogramma.

    Torna `(pezzo, bande, rett, tinta)`:

    - `pezzo`: **copia** di una fascia del fotogramma attorno ai sottotitoli
      (copia e non vista: dxcam riusa il suo buffer, e il pezzo viaggia in una
      coda e viene disegnato fino a un decimo di secondo dopo);
    - `bande`: `(x0, y0, x1, y1)` **di ciascuna riga**, in pixel del pezzo. Una
      per riga, ognuna larga quanto la sua riga: e' cio' che va cancellato, e non
      un pixel di piu';
    - `rett`: dove sta il pezzo nel fotogramma, normalizzato;
    - `tinta`: il colore medio dei glifi, in RGB.

    **La fascia e' piu' alta della ROI, ed e' una correzione misurata.** La ROI e'
    tarata su *dove leggere*, e su GTA V taglia la riga di sopra dei sottotitoli
    su due righe: a `t=1255,7` la banda trovata era alta 13 pixel, cioe' il fondo
    di un `Ciao, Lamar!` che cominciava sopra il bordo. Il risultato a schermo era
    mezza riga italiana rimasta visibile sopra quella inglese. Non si puo'
    cancellare cio' che non si guarda.

    **Le righe sono quelle che l'OCR legge** (`classify_lines`), non l'ingombro
    della maschera: la maschera accesa da un riflesso in un angolo allargherebbe
    il riquadro a tutto lo schermo, e le righe colorate — che l'OCR scarta perche'
    non sono dialogo — lo allargherebbero verso pezzi di HUD.

    Tutto `None` se non si capisce dove sia il testo: si rinuncia a disegnare,
    invece di piazzare un riquadro a caso.
    """
    import numpy as np

    from vision.lines import LineClass, classify_lines
    from vision.roi import roi_pixels

    h_f, w_f = frame.shape[:2]
    rx, ry, rw, rh = roi_pixels(frame.shape, cfg.vision.roi)
    respiro = int(max(0.6 * rh, 0.03 * h_f))
    ay0, ay1 = max(0, ry - respiro), min(h_f, ry + rh + respiro)
    pezzo = np.ascontiguousarray(frame[ay0:ay1, rx : rx + rw])
    if pezzo.size == 0:
        return None, None, None, None
    righe = [r for r in classify_lines(pezzo, cfg.vision) if r.cls is not LineClass.COLORED]
    if not righe:
        return None, None, None, None
    bande = [(r.x0, r.top, r.x1, r.bottom + 1) for r in righe]
    peso = float(sum(r.x1 - r.x0 for r in righe)) or 1.0
    canali = [sum(r.rgb[i] * (r.x1 - r.x0) for r in righe) / peso for i in range(3)]
    rett = (rx / w_f, ay0 / h_f, rw / w_f, (ay1 - ay0) / h_f)
    return pezzo, bande, rett, (canali[2], canali[1], canali[0])


def _cancella(fetta):
    """Toglie i glifi dalla striscia, **ricostruendo lo sfondo** che c'era sotto.

    Confrontato su una riga vera di GTA V, quattro modi di far sparire il
    sottotitolo originale:

        sfocare tutta la striscia   una fascia grigia: si vede che c'e' qualcosa
        sfocare i soli glifi        le lettere restano leggibili, sono chiare
        rettangolo pieno            una macchia in mezzo allo schermo
        **ricostruire** (inpaint)   la riga sparisce e resta la scena

    Solo l'ultimo risponde alla domanda giusta, che non e' «rendere illeggibile»
    ma «far sembrare che quel sottotitolo non ci sia mai stato»: sopra ci va il
    nostro, e due sottotitoli sovrapposti si vedono anche quando uno e' sfocato.

    La maschera dei glifi si ricava dalla striscia stessa e non dalla soglia
    dell'OCR: qui non serve sapere *cosa* c'e' scritto, serve sapere quali pixel
    sono inchiostro, e il percentile alto lo dice senza dipendere da una
    taratura che vive altrove.
    """
    import cv2
    import numpy as np

    luma = fetta[:, :, :3].mean(axis=2)
    alto = float(np.percentile(luma, 99))
    soglia = 0.55 * alto + 0.45 * float(np.median(luma))
    mask = (luma > soglia).astype(np.uint8)
    if not mask.any():
        return fetta
    # **Dilatare non e' generosita'.** Il glifo chiaro e' solo il cuore della
    # lettera: attorno c'e' il contorno **nero**, che sta sotto la soglia e che
    # restando produce il fantasma della riga — leggibile, e a schermo si vede.
    k = max(5, int(0.28 * fetta.shape[0]) | 1)
    mask = cv2.dilate(mask, np.ones((k, k), np.uint8))
    # Il bordo della striscia si tiene pulito: `inpaint` ricostruisce copiando
    # da fuori la maschera, e una maschera che tocca il bordo non ha da dove
    # copiare — il risultato e' un blocco scuro proprio in fondo alla riga, che
    # e' esattamente l'artefatto che si vedeva.
    b = 2
    mask[:b, :] = mask[-b:, :] = 0
    mask[:, :b] = mask[:, -b:] = 0
    return cv2.inpaint(np.ascontiguousarray(fetta[:, :, :3]), mask, 3, cv2.INPAINT_TELEA)


def _righe(disegno, testo: str, font, larghezza_max: int) -> list[str]:
    """Il testo mandato a capo alla larghezza del sottotitolo del gioco."""
    parole, righe, corrente = testo.split(), [], ""
    for p in parole:
        prova = f"{corrente} {p}".strip()
        if corrente and disegno.textlength(prova, font=font) > larghezza_max:
            righe.append(corrente)
            corrente = p
        else:
            corrente = prova
    if corrente:
        righe.append(corrente)
    return righe or [testo]


def dipingi(
    pezzo,
    bande,
    testo: str,
    *,
    scala: float = 1.0,
    nome_font: str = "Arial",
    colore=None,
    corpo: int = 0,
    contorno: float = 2.0,
    blur: float = 12.0,
    inchiostro_rgb=None,
    modo: str = "cancella",
    fondo_rgb=(0, 0, 0),
):
    """Il sottotitolo tradotto su una tela trasparente, e dove va messa.

    - `pezzo`: ritaglio BGR del fotogramma attorno al sottotitolo;
    - `bande`: `[(x0, y0, x1, y1)]` dei glifi del gioco, in pixel del pezzo — sono
      le righe che l'OCR ha letto, non l'ingombro della ROI;
    - `scala`: pixel di schermo per pixel di fotogramma (1.0 per l'MP4);
    - `colore`/`corpo`: `None`/`0` vuol dire «come il gioco».

    Torna `(tela RGBA, (x, y))` con la posizione in pixel **del pezzo per scala**.
    Fuori dai glifi coperti la tela e' trasparente: li' non c'e' niente da
    nascondere e il gioco deve restare quello che e'.
    """
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw

    if not bande:
        return None
    h_pezzo, w_pezzo = pezzo.shape[:2]

    if not corpo:
        corpo = corpo_del_gioco(bande, scala, nome_font)
    if colore is None:
        colore = colore_del_gioco(inchiostro_rgb or (255, 255, 255))
    font = carica_font(nome_font, corpo)

    # Le bande, portate in pixel di schermo.
    su = lambda v: int(round(v * scala))  # noqa: E731
    rett = [(su(x0), su(y0), su(x1), su(y1)) for x0, y0, x1, y1 in bande]
    bx0 = min(r[0] for r in rett)
    by0 = min(r[1] for r in rett)
    bx1 = max(r[2] for r in rett)
    by1 = max(r[3] for r in rett)

    # Il testo, a capo alla stessa larghezza a cui va a capo il gioco.
    misura = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    righe = _righe(misura, testo, font, max(80, su(w_pezzo) - 8))
    passo = int(round(corpo * 1.22))
    largh_testo = int(max(misura.textlength(r, font=font) for r in righe))
    alt_testo = passo * len(righe)

    # La tela: l'unione fra cio' che va coperto e cio' che va scritto, piu' il
    # bordo del contorno. Il testo si centra sul sottotitolo vecchio.
    pad = int(round(contorno * scala)) + 3
    cx = (bx0 + bx1) // 2
    cy = (by0 + by1) // 2
    tx0, tx1 = cx - largh_testo // 2, cx + largh_testo // 2
    ty0, ty1 = cy - alt_testo // 2, cy + alt_testo // 2
    ox = min(bx0, tx0) - pad
    oy = min(by0, ty0) - pad
    larg = max(bx1, tx1) + pad - ox
    alt = max(by1, ty1) + pad - oy

    tela = Image.new("RGBA", (max(1, larg), max(1, alt)), (0, 0, 0, 0))

    # -- 1. si cancella la scritta del gioco, e **solo** quella ---------------
    if modo != "nessuno":
        for x0, y0, x1, y1 in bande:
            # Un filo di margine attorno alla riga: i glifi hanno un contorno e
            # un'ombra, e un ritaglio esatto sui pixel accesi lascerebbe scoperto
            # proprio il bordo delle lettere vecchie. Serve anche a `cancella`,
            # che ha bisogno di sfondo pulito da cui ricostruire.
            m = max(4, int(0.45 * (y1 - y0)))
            a0, b0 = max(0, x0 - m), max(0, y0 - m)
            a1, b1 = min(w_pezzo, x1 + m), min(h_pezzo, y1 + m)
            w = max(1, su(a1) - su(a0))
            h = max(1, su(b1) - su(b0))
            if modo == "riquadro":
                patch = Image.new("RGB", (w, h), tuple(int(v) for v in fondo_rgb))
            else:
                fetta = np.ascontiguousarray(pezzo[b0:b1, a0:a1])
                if fetta.size == 0:
                    continue
                if modo == "cancella":
                    fetta = _cancella(fetta)
                else:
                    # Il raggio segue l'altezza dei glifi invece di essere in
                    # pixel fissi: `blur_strength` e' dichiarato su un inchiostro
                    # alto 40 px (GTA V a 1080p), e cosi' lo stesso numero vale a
                    # 1080p, a 1440p e su un gioco che scrive piu' grande.
                    raggio = max(1.5, blur * (y1 - y0) / 40.0)
                    fetta = cv2.GaussianBlur(fetta, (0, 0), sigmaX=raggio, sigmaY=raggio)
                fetta = cv2.cvtColor(fetta[:, :, :3], cv2.COLOR_BGR2RGB)
                patch = Image.fromarray(fetta).resize((w, h))
            tela.paste(patch, (su(a0) - ox, su(b0) - oy))

    # -- 2. si scrive la nostra, della taglia e del colore del gioco ---------
    d = ImageDraw.Draw(tela)
    bordo = max(1, int(round(contorno * scala)))
    for i, riga in enumerate(righe):
        w = misura.textlength(riga, font=font)
        x = cx - int(w) // 2 - ox
        y = ty0 + i * passo - oy
        d.text((x, y), riga, font=font, fill=(*colore, 255),
               stroke_width=bordo, stroke_fill=(0, 0, 0, 255))
    return tela, (ox, oy)


def su_chiave(tela):
    """La tela RGBA appiattita sul colore-chiave, per una finestra Windows.

    Tk non sa fare finestre con trasparenza per pixel: sa fare un colore che
    sparisce. Quindi il trasparente diventa `CHIAVE`, e i pixel opachi che per
    caso valessero esattamente `CHIAVE` vengono spostati di uno — se no si
    aprirebbero buchi neri dentro il testo.
    """
    import numpy as np
    from PIL import Image

    fondo = Image.new("RGB", tela.size, CHIAVE_RGB)
    fondo.paste(tela, (0, 0), tela)
    arr = np.array(fondo)
    alfa = np.array(tela.getchannel("A"))
    collisione = (alfa > 0) & np.all(arr == np.array(CHIAVE_RGB), axis=2)
    arr[collisione] = (4, 4, 4)
    return Image.fromarray(arr)


class Overlay:
    """Una finestra senza bordi sopra il gioco, con dentro il testo tradotto."""

    def __init__(
        self,
        root: tk.Misc,
        roi: tuple[float, float, float, float],
        *,
        colore: str = "",
        fondo: str = "#000000",
        font: str = "Arial",
        font_frac: float = 0.0,
        opacita: float = 1.0,
        modo: str = "cancella",
        blur: float = 12.0,
        contorno: float = 2.0,
    ) -> None:
        self.blur = max(0.0, blur)
        self.modo = (modo or "cancella").lower()
        self.nome_font = font
        self.contorno = contorno
        # Vuoto e zero vogliono dire «come il gioco», e sono i default: un colore
        # e una misura scelti da noi sarebbero un cartello appiccicato sopra il
        # sottotitolo invece del sottotitolo.
        self.colore = self._rgb(colore) if colore else None
        self.misura = MisuraCarattere()
        self.fondo_rgb = self._rgb(fondo) if fondo else (0, 0, 0)
        self.font_frac = font_frac
        self._foto = None
        self.schermo = (root.winfo_screenwidth(), root.winfo_screenheight())

        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=CHIAVE)
        try:
            self.top.attributes("-alpha", max(0.1, min(1.0, opacita)))
        except tk.TclError:  # pragma: no cover - dipende dal window manager
            pass
        self.etichetta = tk.Label(self.top, bd=0, highlightthickness=0, bg=CHIAVE,
                                  padx=0, pady=0)
        self.etichetta.pack(expand=True, fill="both")

        self.geom = self._geom_roi(roi)
        self.top.geometry("%dx%d+%d+%d" % self.geom)
        self._passante()
        self.top.withdraw()
        self._visibile = False

    @staticmethod
    def _rgb(s: str) -> tuple[int, int, int]:
        s = s.lstrip("#")
        return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))

    def _geom_roi(self, roi) -> tuple[int, int, int, int]:
        sw, sh = self.schermo
        x, y, w, h = roi
        return (max(1, int(sw * w)), max(1, int(sh * h)), int(sw * x), int(sh * y))

    def riposiziona(self, roi) -> None:
        """La ROI e' cambiata (il selettore d'area): il ripiego deve seguirla."""
        self.geom = self._geom_roi(roi)

    def _passante(self) -> None:
        """Tre proprieta' di Windows, e nessuna e' una rifinitura.

        **Fuori dalla cattura** (`WDA_EXCLUDEFROMCAPTURE`): senza, la finestra
        finisce nel fotogramma che diamo all'OCR — misurato, il 100% dei suoi
        pixel — e l'OCR smette di leggere il gioco per leggere noi.

        **Trasparente ai clic** (`WS_EX_TRANSPARENT`): una finestra sopra il
        gioco che intercetta il mouse rende ingiocabile il gioco.

        **Incapace di prendere il fuoco** (`WS_EX_NOACTIVATE`): comparendo,
        toglierebbe il fuoco al gioco, che in molti giochi vuol dire mettere in
        pausa o perdere il puntatore.
        """
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
        WDA_EXCLUDEFROMCAPTURE = 0x00000011

        self.top.update_idletasks()
        u32 = ctypes.windll.user32
        hwnd = u32.GetParent(self.top.winfo_id())
        u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.GetWindowLongW.restype = ctypes.c_long
        u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        stile = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(
            hwnd, GWL_EXSTYLE,
            stile | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
        )
        # Il colore che sparisce. Va messo **dopo** WS_EX_LAYERED.
        try:
            self.top.attributes("-transparentcolor", CHIAVE)
        except tk.TclError:  # pragma: no cover
            print("overlay: colore trasparente non disponibile", file=sys.stderr)
        if not u32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
            # Un ripiego che non si dichiara e' peggio di un errore: senza
            # esclusione l'OCR legge noi, e il difetto sembrerebbe dell'OCR.
            print("overlay: ATTENZIONE, la finestra non e' esclusa dalla cattura: "
                  "l'OCR leggera' anche il testo tradotto", file=sys.stderr)

    # -- uso ---------------------------------------------------------------

    def mostra(self, testo: str, pezzo=None, bande=None, rett=None, inchiostro=None) -> None:
        """Mostra il testo tradotto sopra il sottotitolo del gioco.

        `pezzo` e' il ritaglio del fotogramma attorno al sottotitolo, `bande` i
        rettangoli dei glifi da coprire (pixel del pezzo), `rett` dove sta il
        pezzo nel fotogramma in coordinate normalizzate, `inchiostro` il colore
        medio dei glifi. Senza, non si disegna niente: meglio nessun sottotitolo
        tradotto che un cartello piazzato a caso.
        """
        testo = (testo or "").strip()
        if not testo:
            self.nascondi()
            return
        if pezzo is None or not bande or rett is None:
            return  # non si sa dove sta il sottotitolo: non si disegna a caso
        try:
            fatto = self._prepara(testo, pezzo, bande, rett, inchiostro)
        except Exception as exc:  # pragma: no cover - meglio zoppicare che cadere
            print(f"overlay: {type(exc).__name__}: {exc}", file=sys.stderr)
            fatto = None
        if fatto is None:
            return
        self._foto, geom = fatto
        self.etichetta.configure(image=self._foto)
        self.top.geometry("%dx%d+%d+%d" % geom)
        if not self._visibile:
            self.top.deiconify()
            self.top.attributes("-topmost", True)
            self._visibile = True

    def _prepara(self, testo, pezzo, bande, rett, inchiostro):
        from PIL import ImageTk

        sw, sh = self.schermo
        h_pezzo, w_pezzo = pezzo.shape[:2]
        scala = (rett[2] * sw) / max(1, w_pezzo)
        corpo = (int(sh * self.font_frac) if self.font_frac > 0
                 else self.misura.aggiorna(bande, scala, self.nome_font))
        fatto = dipingi(
            pezzo, bande, testo,
            scala=scala, nome_font=self.nome_font, colore=self.colore,
            corpo=corpo, contorno=self.contorno, blur=self.blur,
            inchiostro_rgb=inchiostro, modo=self.modo, fondo_rgb=self.fondo_rgb,
        )
        if fatto is None:
            return None
        tela, (ox, oy) = fatto
        piatta = su_chiave(tela)
        foto = ImageTk.PhotoImage(piatta, master=self.top)
        x = int(rett[0] * sw) + ox
        y = int(rett[1] * sh) + oy
        geom = (piatta.width, piatta.height,
                max(0, min(sw - piatta.width, x)), max(0, min(sh - piatta.height, y)))
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
