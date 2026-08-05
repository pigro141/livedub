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


def corpo_del_gioco(bande, testo_originale: str, scala: float, nome_font: str) -> int:
    """Quanto e' grande, in punti, il carattere che il gioco sta usando.

    **Si misura sulla larghezza, non sull'altezza, e la differenza e' un
    quarto.** Il primo tentativo confrontava l'altezza della banda con l'altezza
    dell'inchiostro di `Ag`: ma `Ag` occupa dall'ascendente al discendente,
    mentre una riga come `Ciao, Lamar!` non ha nessun discendente e la sua banda
    e' alta solo quanto le maiuscole. Confrontare le due voleva dire chiedere un
    carattere alto quanto una riga intera per ottenere delle sole maiuscole —
    circa il 40% troppo grande, che e' esattamente quello che si vedeva.

    La larghezza invece si confronta con se' stessa: si prende **il testo che
    l'OCR ha letto**, lo si disegna col carattere scelto e si cerca il corpo in
    cui occupa la stessa larghezza che occupa a schermo. Stesse lettere, stessa
    grandezza — nessuna conversione fra due misure diverse. In piu' funziona con
    un carattere di forma diversa da quello del gioco: GTA V ne usa uno stretto,
    e chiedere la stessa **altezza** ad Arial avrebbe dato una riga molto piu'
    larga dell'originale.

    Senza il testo (non dovrebbe capitare) si ricade sull'altezza, dichiarando
    il rapporto fra inchiostro maiuscolo e corpo invece di far finta che sia 1.
    """
    larghezza = sum(x1 - x0 for x0, _, x1, _ in bande) * scala
    testo = " ".join((testo_originale or "").split())
    if not testo or larghezza <= 0:
        import statistics

        alta = statistics.median(sorted(y1 - y0 for _, y0, _, y1 in bande)) * scala
        return max(8, int(round(alta / 0.72)))  # inchiostro maiuscolo / corpo

    from PIL import Image, ImageDraw

    misura = ImageDraw.Draw(Image.new("L", (1, 1)))
    corpo = max(8, int(larghezza / max(1, len(testo)) * 2.0))
    for _ in range(10):
        w = misura.textlength(testo, font=carica_font(nome_font, corpo))
        if w <= 0:
            break
        if abs(w - larghezza) <= max(2.0, 0.01 * larghezza):
            break
        corpo = max(8, int(round(corpo * larghezza / w)))
    return corpo


class MisuraCarattere:
    """Ricorda quanto e' grande il carattere del gioco. **Uno, sempre lo stesso.**

    Un gioco scrive i sottotitoli sempre della stessa taglia, quindi una taglia
    che cambia da una battuta all'altra e' rumore della misura, non un fatto — e
    a schermo si vede benissimo. Le fonti del rumore sono due, misurate: la
    dissolvenza con cui GTA V fa comparire il sottotitolo (a meta' sfumatura la
    maschera prende solo il cuore dei glifi) e l'OCR che legge una parola in piu'
    o in meno di quelle che ci sono.

    Si tiene quindi la **mediana** delle misure viste, non l'ultima e nemmeno la
    piu' grande: la mediana e' insensibile a entrambe le code, e dopo poche
    battute non si muove piu'. Fino ad allora si muove poco.
    """

    def __init__(self, quante: int = 25) -> None:
        self.viste: list[int] = []
        self.quante = quante
        self.corpo = 0

    def azzera(self) -> None:
        self.viste.clear()
        self.corpo = 0

    def aggiorna(self, bande, testo_originale, scala: float, nome_font: str) -> int:
        c = corpo_del_gioco(bande, testo_originale, scala, nome_font)
        if c > 0:
            self.viste.append(c)
            del self.viste[: -self.quante]
        if not self.viste:
            return self.corpo or 8
        import statistics

        self.corpo = int(round(statistics.median(self.viste)))
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


def bande_veloci(pezzo, cfg):
    """Dove sta l'inchiostro **adesso**, con la sola soglia e senza il resto.

    Esiste perche' la cancellatura va rinfrescata dieci volte al secondo e
    `classify_lines` costa 11 ms: dieci volte al secondo sono il 10% del thread
    video, e in questo progetto un costo nel thread video non si somma, si
    amplifica. Qui non serve sapere *cosa* c'e' scritto ne' di che classe sia la
    riga — serve sapere quali righe di pixel sono accese — e quello costa un
    profilo per righe.

    La soglia e la fascia minima sono **le stesse della config** che usa l'OCR:
    una seconda taratura per la stessa cosa divergerebbe dalla prima.
    """
    import numpy as np

    from vision.lines import find_bands, text_mask

    luma = pezzo[:, :, :3].mean(axis=2) if pezzo.ndim == 3 else pezzo.astype(np.float32)
    # **La stessa maschera dell'OCR, contrasto locale compreso.** Con la sola
    # soglia assoluta una camicia chiara o un tavolo illuminato diventano una
    # riga di testo, e la cancellatura ci passa sopra: a schermo si vedevano
    # rettangoli sfumati grandi mezza inquadratura. Il contrasto locale e' cio'
    # che distingue un glifo bordato di nero da una superficie chiara, e costa
    # una sfocatura.
    mask = text_mask(luma, cfg)
    if not mask.any():
        return []
    min_px = max(1, int(pezzo.shape[1] * cfg.min_line_fill))
    fuori = []
    for top, bottom in find_bands(mask, cfg.min_line_height, min_px, cfg.line_grow):
        cols = np.flatnonzero(mask[top : bottom + 1].any(axis=0))
        if cols.size:
            fuori.append((int(cols[0]), int(top), int(cols[-1]) + 1, int(bottom) + 1))
    return fuori


def ritaglia(frame, rett):
    """La stessa fascia di prima, presa da un fotogramma nuovo.

    Serve ad aggiornare la cancellatura **senza ricalcolare dove sta il
    sottotitolo**: se si ricercassero le bande, il riquadro si sposterebbe di un
    pixel per fotogramma e il sottotitolo tremerebbe. La geometria si decide una
    volta; qui si prendono solo pixel nuovi dentro lo stesso rettangolo.
    """
    import numpy as np

    h, w = frame.shape[:2]
    x0, y0 = int(round(rett[0] * w)), int(round(rett[1] * h))
    x1, y1 = x0 + int(round(rett[2] * w)), y0 + int(round(rett[3] * h))
    fetta = frame[max(0, y0) : min(h, y1), max(0, x0) : min(w, x1)]
    return np.ascontiguousarray(fetta) if fetta.size else None


def _cancella(fetta, alta: int = 0):
    """Toglie i glifi dalla striscia, **ricostruendo lo sfondo** che c'era sotto.

    Confrontato su una riga vera di GTA V, cinque modi di far sparire il
    sottotitolo originale:

        sfocare tutta la striscia    una fascia grigia: si vede che c'e' qualcosa
        sfocare i soli glifi         le lettere restano leggibili, sono chiare
        mediana                      resta il fantasma
        inpaint (Telea)              pulito, **16,3 ms**
        **apri e chiudi**            pulito, **0,15 ms**

    Si usa l'ultimo, e i 16 millisecondi risparmiati non sono un vezzo: sono
    quelli che permettono di **rifare la cancellatura a ogni fotogramma** invece
    di congelarla. Una toppa congelata mentre la scena si muove diventa un
    rettangolo di pixel vecchi in mezzo all'immagine, ed e' peggio del
    sottotitolo che copriva.

    L'apertura toglie il chiaro sottile — l'asta del glifo — e la chiusura toglie
    lo scuro sottile, cioe' il **contorno nero** che l'apertura lascia indietro e
    che da solo si legge ancora. Due passaggi e non uno: con la sola apertura
    resta il fantasma della riga, misurato e guardato.
    """
    import cv2

    alta = alta or fetta.shape[0]
    apri = max(3, int(0.28 * alta) | 1)
    chiudi = max(apri + 2, int(0.55 * alta) | 1)
    ko = cv2.getStructuringElement(cv2.MORPH_RECT, (apri, apri))
    kc = cv2.getStructuringElement(cv2.MORPH_RECT, (chiudi, chiudi))
    out = cv2.morphologyEx(fetta[:, :, :3], cv2.MORPH_OPEN, ko)
    out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, kc)
    # Un velo di sfocatura solo per togliere gli spigoli della morfologia, che e'
    # fatta di rettangoli e si vede.
    return cv2.GaussianBlur(out, (0, 0), max(1.0, 0.08 * alta))


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


class Sostituzione:
    """Il sottotitolo tradotto: **geometria decisa una volta, pixel aggiornati**.

    E' la divisione che risolve i due difetti opposti visti a schermo.

    Ridisegnando tutto a ogni fotogramma, il riquadro veniva ricalcolato da bande
    leggermente diverse: il testo tremava, cambiava taglia e nei fotogrammi in
    cui la dissolvenza nascondeva i glifi spariva del tutto. Un sottotitolo non
    fa niente di tutto questo — compare, sta fermo, sparisce.

    Congelando invece anche i pixel, la toppa che cancella la riga italiana
    restava quella del primo fotogramma: la scena dietro si muove, e resta un
    rettangolo di immagine vecchia in mezzo allo schermo.

    Quindi: **taglia, colore, posizione, a-capo e rettangoli si decidono
    all'inizio e non si toccano piu'**; solo la cancellatura viene rifatta sui
    pixel nuovi, e costa 0,15 ms a riga proprio per poterlo fare.
    """

    def __init__(
        self,
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
        testo_originale: str = "",
        larghezza_schermo: int = 0,
    ) -> None:
        from PIL import Image, ImageDraw

        self.bande = list(bande)
        # **Quanto e' alta una riga di questo gioco.** Al rinfresco arrivano le
        # bande di adesso, e li' dentro puo' esserci di tutto: dal vivo un dito
        # chiaro contro una camicia scura e' passato per una riga di testo, e la
        # cancellatura ci e' passata sopra lasciando un rettangolo grigio. Una
        # riga di sottotitolo e' alta quanto le altre; il resto no.
        self.alta = max(1, max(y1 - y0 for _, y0, _, y1 in bande))
        self.modo = (modo or "cancella").lower()
        self.blur = blur
        self.fondo_rgb = tuple(int(v) for v in fondo_rgb)
        self.scala = scala
        self.forma = pezzo.shape[:2]
        h_pezzo, w_pezzo = self.forma

        self.corpo = corpo or corpo_del_gioco(bande, testo_originale, scala, nome_font)
        self.colore = colore or colore_del_gioco(inchiostro_rgb or (255, 255, 255))
        self.font = carica_font(nome_font, self.corpo)
        self.contorno = max(1, int(round(contorno * scala)))

        su = lambda v: int(round(v * scala))  # noqa: E731
        self.su = su
        rett = [(su(x0), su(y0), su(x1), su(y1)) for x0, y0, x1, y1 in bande]
        bx0, by0 = min(r[0] for r in rett), min(r[1] for r in rett)
        bx1, by1 = max(r[2] for r in rett), max(r[3] for r in rett)

        # L'a-capo alla larghezza a cui va a capo il gioco, e **mai oltre lo
        # schermo**: una battuta piu' larga dello schermo non e' un sottotitolo,
        # e' un difetto che esce dall'immagine.
        misura = ImageDraw.Draw(Image.new("L", (1, 1)))
        limite = su(w_pezzo) - 8
        if larghezza_schermo:
            limite = min(limite, larghezza_schermo - 16)
        self.righe = _righe(misura, (testo or "").strip(), self.font, max(80, limite))
        self.passo = int(round(self.corpo * 1.22))
        largh = int(max(misura.textlength(r, font=self.font) for r in self.righe))
        alt = self.passo * len(self.righe)

        pad = self.contorno + 3
        self.cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2
        self.ty0 = cy - alt // 2
        # **La tela copre tutta la fascia, non solo cio' che c'e' adesso.**
        # Mentre la nostra battuta e' a schermo il gioco puo' essere gia'
        # passato alla riga dopo — succede sempre, perche' la voce arriva un
        # secondo e mezzo dopo il sottotitolo. Se la tela fosse stretta sui
        # rettangoli di partenza, quella riga nuova resterebbe scoperta e si
        # leggerebbero due sottotitoli insieme. Con la tela larga la
        # cancellatura si sposta dentro di lei e **il testo non si muove**.
        self.ox = 0
        self.oy = min(0, self.ty0 - pad)
        self.larg = max(1, su(w_pezzo))
        self.alt = max(1, max(su(h_pezzo), self.ty0 + alt + pad) - self.oy)
        self.misura = misura

    # -- i pixel, che invece si rifanno ------------------------------------

    def disegna(self, pezzo, bande=None):
        """La tela RGBA di adesso, con la geometria di sempre.

        `bande` diverse da quelle di partenza servono a inseguire il sottotitolo
        del gioco quando cambia sotto di noi: cambia **cosa** si cancella, non
        dove sta scritta la traduzione.
        """
        import numpy as np
        from PIL import Image, ImageDraw

        tela = Image.new("RGBA", (self.larg, self.alt), (0, 0, 0, 0))
        h_pezzo, w_pezzo = pezzo.shape[:2]
        scelte = self.bande
        if bande:
            scelte = [b for b in bande if (b[3] - b[1]) <= 2.0 * self.alta] or self.bande
        if self.modo != "nessuno":
            for x0, y0, x1, y1 in scelte:
                # Un filo di margine attorno alla riga: i glifi hanno un contorno
                # e un'ombra, e un ritaglio esatto sui pixel accesi lascerebbe
                # scoperto proprio il bordo delle lettere vecchie.
                m = max(4, int(0.45 * (y1 - y0)))
                a0, b0 = max(0, x0 - m), max(0, y0 - m)
                a1, b1 = min(w_pezzo, x1 + m), min(h_pezzo, y1 + m)
                w = max(1, self.su(a1) - self.su(a0))
                h = max(1, self.su(b1) - self.su(b0))
                if self.modo == "riquadro":
                    patch = Image.new("RGB", (w, h), self.fondo_rgb)
                else:
                    fetta = np.ascontiguousarray(pezzo[b0:b1, a0:a1])
                    if fetta.size == 0:
                        continue
                    if self.modo == "cancella":
                        fetta = _cancella(fetta, y1 - y0)
                    else:
                        import cv2

                        raggio = max(1.5, self.blur * (y1 - y0) / 40.0)
                        fetta = cv2.GaussianBlur(fetta[:, :, :3], (0, 0), sigmaX=raggio)
                    fetta = fetta[:, :, ::-1]  # BGR -> RGB
                    patch = Image.fromarray(np.ascontiguousarray(fetta)).resize((w, h))
                tela.paste(patch, (self.su(a0) - self.ox, self.su(b0) - self.oy))

        d = ImageDraw.Draw(tela)
        for i, riga in enumerate(self.righe):
            w = self.misura.textlength(riga, font=self.font)
            x = self.cx - int(w) // 2 - self.ox
            y = self.ty0 + i * self.passo - self.oy
            d.text((x, y), riga, font=self.font, fill=(*self.colore, 255),
                   stroke_width=self.contorno, stroke_fill=(0, 0, 0, 255))
        return tela, (self.ox, self.oy)


def dipingi(pezzo, bande, testo: str, **kw):
    """Decide e disegna in un colpo solo. `None` se non c'e' niente da coprire."""
    if not bande:
        return None
    return Sostituzione(pezzo, bande, testo, **kw).disegna(pezzo)


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
        escludi_cattura: bool = True,
    ) -> None:
        self.blur = max(0.0, blur)
        # **Spegnerla serve solo a fotografarla.** La finestra e' esclusa dalla
        # cattura, e uno screenshot *e'* una cattura: con l'esclusione accesa
        # l'overlay non compare in nessuna immagine, nemmeno nelle nostre. Per
        # guardarlo si spegne, e si riaccende — non e' un'opzione da config,
        # perche' spenta l'OCR ricomincia a leggere noi.
        self.escludi_cattura = escludi_cattura
        self.modo = (modo or "cancella").lower()
        self.nome_font = font
        self.contorno = contorno
        # Vuoto e zero vogliono dire «come il gioco», e sono i default: un colore
        # e una misura scelti da noi sarebbero un cartello appiccicato sopra il
        # sottotitolo invece del sottotitolo.
        self.colore = self._rgb(colore) if colore else None
        self.misura = MisuraCarattere()
        self.sost = None     # la battuta a schermo adesso, con la sua geometria
        self._vuoti = 0      # giri di seguito senza inchiostro del gioco
        self.vision = None   # le soglie con cui ritrovare l'inchiostro
        self.rett = None
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
        if not self.escludi_cattura:
            # Si **rimette** a WDA_NONE, non si omette la chiamata: l'affinita'
            # e' una proprieta' della finestra, e ometterla lascia quella di
            # prima. Provandolo, lo screenshot continuava a non vedere la
            # finestra e sembrava che l'overlay non venisse disegnato affatto.
            u32.SetWindowDisplayAffinity(hwnd, 0)
            print("overlay: esclusione dalla cattura SPENTA (solo per fotografarlo): "
                  "l'OCR leggera' anche il testo tradotto", file=sys.stderr)
        elif not u32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
            # Un ripiego che non si dichiara e' peggio di un errore: senza
            # esclusione l'OCR legge noi, e il difetto sembrerebbe dell'OCR.
            print("overlay: ATTENZIONE, la finestra non e' esclusa dalla cattura: "
                  "l'OCR leggera' anche il testo tradotto", file=sys.stderr)

    # -- uso ---------------------------------------------------------------

    def mostra(self, testo: str, pezzo=None, bande=None, rett=None, inchiostro=None,
               originale: str = "") -> None:
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
            fatto = self._prepara(testo, pezzo, bande, rett, inchiostro, originale)
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

    def aggiorna(self, frame) -> None:
        """Rifa' **solo la cancellatura** sui pixel nuovi, senza muovere niente.

        La scena dietro il sottotitolo si muove; una toppa congelata al primo
        fotogramma diventa un rettangolo di immagine vecchia in mezzo allo
        schermo. Costa 0,15 ms a riga apposta per poterlo fare.
        """
        if self.sost is None or not self._visibile:
            return
        pezzo = ritaglia(frame, self.rett)
        if pezzo is None or pezzo.shape[:2] != self.sost.forma:
            return
        try:
            bande = bande_veloci(pezzo, self.vision) if self.vision is not None else []
            tela, _ = self.sost.disegna(pezzo, bande)
        except Exception:  # pragma: no cover - meglio una toppa vecchia che un crollo
            return
        # **Sparisce quando sparisce il sottotitolo del gioco, non quando lo dice
        # una previsione.** Il tempo di permanenza si prevede da `D = a + b*n`,
        # che su una battuta corta da' poco piu' di un secondo: dal vivo si e'
        # visto il tradotto sparire con l'italiano ancora a schermo. Qui la
        # risposta ce l'abbiamo sotto gli occhi — l'inchiostro c'e' o non c'e'.
        if bande:
            self._vuoti = 0
        else:
            self._vuoti += 1
            if self._vuoti >= 3:  # tre giri a 10 Hz: tre decimi, non un lampo
                self.nascondi()
                return
        from PIL import ImageTk

        self._foto = ImageTk.PhotoImage(su_chiave(tela), master=self.top)
        self.etichetta.configure(image=self._foto)

    def _prepara(self, testo, pezzo, bande, rett, inchiostro, originale=""):
        from PIL import ImageTk

        sw, sh = self.schermo
        h_pezzo, w_pezzo = pezzo.shape[:2]
        scala = (rett[2] * sw) / max(1, w_pezzo)
        corpo = (int(sh * self.font_frac) if self.font_frac > 0
                 else self.misura.aggiorna(bande, originale, scala, self.nome_font))
        self.sost = Sostituzione(
            pezzo, bande, testo,
            scala=scala, nome_font=self.nome_font, colore=self.colore,
            corpo=corpo, contorno=self.contorno, blur=self.blur,
            inchiostro_rgb=inchiostro, modo=self.modo, fondo_rgb=self.fondo_rgb,
            testo_originale=originale, larghezza_schermo=sw,
        )
        self.rett = rett
        self._vuoti = 0
        tela, (ox, oy) = self.sost.disegna(pezzo)
        piatta = su_chiave(tela)
        foto = ImageTk.PhotoImage(piatta, master=self.top)
        x = int(rett[0] * sw) + ox
        y = int(rett[1] * sh) + oy
        geom = (piatta.width, piatta.height,
                max(0, min(sw - piatta.width, x)), max(0, min(sh - piatta.height, y)))
        return foto, geom

    def nascondi(self) -> None:
        self.sost = None
        if self._visibile:
            self.top.withdraw()
            self._visibile = False

    def distruggi(self) -> None:
        try:
            self.top.destroy()
        except tk.TclError:  # pragma: no cover
            pass
