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

## Un rettangolo, sfocato, con sopra il testo

La forma finale e' la piu' semplice, ed e' quella che l'utente ha proposto dopo
aver visto fallire le altre: si prende il **rettangolo che circoscrive il
sottotitolo** letto dall'OCR, lo si sfoca sui pixel di **questo** fotogramma, e
ci si scrive sopra la traduzione.

Le due strade tentate prima sono un promemoria di cosa costa complicare. La
prima sfocava tutta la ROI: una fascia larga mezzo schermo per coprire una riga.
La seconda cancellava riga per riga ricostruendo lo sfondo con la morfologia, e
inseguiva l'inchiostro fotogramma per fotogramma per restare aggiornata: da li'
venivano toppe accanto al testo, macchie sull'asfalto, e righe cancellate che
non erano righe — perche' su una scena luminosa dell'inchiostro si trova sempre.

**Geometria ferma, pixel vivi.** Il rettangolo si calcola una volta alla
comparsa e non si muove piu' (se no il sottotitolo balla); la sfocatura dentro
si rifa' a ogni giro sul fotogramma corrente (se no e' una toppa di immagine
vecchia incollata su una scena che si muove).

**E sparisce quando sparisce l'originale**, che e' cosa sa il lettore di
sottotitoli e non i pixel: `DubPipeline.a_schermo(t_on)`. Chiedendolo
all'inchiostro, la stessa frase inglese e' rimasta a schermo **diciotto
secondi** mentre il gioco era gia' a tre battute dopo.

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
    altezza = max(y1 - y0 for _, y0, _, y1 in bande) * scala
    testo = " ".join((testo_originale or "").split())
    if not testo or larghezza <= 0:
        import statistics

        alta = statistics.median(sorted(y1 - y0 for _, y0, _, y1 in bande)) * scala
        return max(8, int(round(alta / 0.72)))  # inchiostro maiuscolo / corpo

    from PIL import Image, ImageDraw

    misura = ImageDraw.Draw(Image.new("L", (1, 1)))

    def errore(corpo: int) -> float:
        """Quanto quel corpo sbaglia, **su tutti e due i lati**.

        La sola larghezza basterebbe se il carattere fosse quello del gioco, e
        non lo e': GTA V ne usa uno stretto, Arial no. Con la sola larghezza il
        testo viene giusto di lunghezza e **piu' alto** dell'originale; con la
        sola altezza viene giusto di altezza e molto piu' lungo. Si cerca quindi
        il corpo che sbaglia meno su entrambi, con l'altezza pesata la meta'
        perche' la larghezza e' misurata su una riga intera e l'altezza su un
        glifo — la prima e' la misura piu' affidabile delle due.
        """
        f = carica_font(nome_font, corpo)
        w = misura.textlength(testo, font=f)
        a, b, cx, d = f.getbbox("Ag")
        h = max(1, d - b)
        return abs(w - larghezza) / larghezza + 0.5 * abs(h - altezza) / max(1.0, altezza)

    # Si parte dalla stima sulla sola larghezza — poche iterazioni, converge —
    # e poi si cerca il minimo attorno, che e' dove i due lati si accordano.
    corpo = max(8, int(larghezza / max(1, len(testo)) * 2.0))
    for _ in range(10):
        w = misura.textlength(testo, font=carica_font(nome_font, corpo))
        if w <= 0:
            break
        if abs(w - larghezza) <= max(2.0, 0.01 * larghezza):
            break
        corpo = max(8, int(round(corpo * larghezza / w)))
    # **Un tetto duro sull'altezza, e non e' pignoleria.** Il compromesso e' un
    # minimo, e un minimo su una banda dalle proporzioni impossibili — dodici
    # lettere larghe 700 px e alte 30, cioe' non il testo che dice di essere —
    # puo' cadere su un carattere alto il triplo della riga che deve coprire. A
    # schermo si vede un sottotitolo gonfio, che e' il difetto da cui e' partito
    # tutto questo. Sopra la riga si puo' sconfinare di un filo, non di piu'.
    def sta_dentro(corpo: int) -> bool:
        a, b, cc, d = carica_font(nome_font, corpo).getbbox("Ag")
        return (d - b) <= altezza * 1.35

    candidati = [c for c in range(max(8, corpo - 8), corpo + 9) if sta_dentro(c)]
    if not candidati:
        candidati = [max(8, int(round(altezza / 0.72)))]
    return min(candidati, key=errore)


class MisuraCarattere:
    """Ricorda quanto e' grande il carattere del gioco. **Uno, sempre lo stesso.**

    Un gioco scrive i sottotitoli sempre della stessa taglia, quindi una taglia
    che cambia da una battuta all'altra e' rumore della misura, non un fatto — e
    a schermo si vede benissimo.

    Le fonti del rumore sono tre, tutte viste dal vivo:

    - la **dissolvenza** con cui il sottotitolo compare: a meta' sfumatura la
      maschera prende solo il cuore dei glifi;
    - l'OCR che legge **una parte** della riga (`RecupeSenti, amico`): pochi
      caratteri su molti pixel di inchiostro, e la stima esplode;
    - le battute su **due righe**, dove basta che il testo letto sia di una riga
      sola perche' il rapporto salti del doppio.

    Da qui due regole. La prima: si scartano le stime **incoerenti**, cioe'
    quelle troppo lontane da quanto si e' gia' visto. La seconda: dopo un po' di
    stime d'accordo fra loro **la taglia si blocca** e non si muove piu'. Un
    sottotitolo non cambia corpo a meta' partita, e continuare a rimisurarlo puo'
    solo peggiorare una risposta che si e' gia' avuta.
    """

    def __init__(self, quante: int = 25, bastano: int = 6) -> None:
        self.viste: list[int] = []
        self.quante = quante
        self.bastano = bastano
        self.corpo = 0
        self.bloccata = False
        # **Questo gioco centra i sottotitoli?** Si impara, non si decide su una
        # battuta sola. Una lettura parziale — `Recupe`, `that youTL` — e' stretta
        # e spostata, e centrandoci sopra la traduzione finisce decentrata; ma un
        # gioco che allinea a sinistra esiste, e ricentrare d'ufficio sarebbe
        # sbagliato per lui. Chi risponde e' la maggioranza delle battute viste.
        self._centrati = 0
        self._totali = 0

    def azzera(self) -> None:
        self.viste.clear()
        self.corpo = 0
        self.bloccata = False
        self._centrati = self._totali = 0

    @property
    def centra(self) -> bool:
        """Il gioco scrive i sottotitoli centrati? Si risponde da tre battute."""
        return self._totali >= 3 and self._centrati >= 0.7 * self._totali

    def guarda_allineamento(self, bande, larghezza: int) -> None:
        """Registra se questa battuta stava al centro dell'area.

        Si guarda **prima** di sapere se la lettura e' parziale, perche' una
        lettura parziale e' comunque centrata quando il gioco centra: e' larga
        meta' e sta in mezzo. Quelle davvero decentrate sono i giochi che
        allineano, ed e' proprio quello che si vuole distinguere.
        """
        if not bande or larghezza <= 0:
            return
        cx = (min(b[0] for b in bande) + max(b[2] for b in bande)) / 2.0
        self._totali += 1
        if abs(cx - larghezza / 2.0) <= 0.12 * larghezza:
            self._centrati += 1

    def aggiorna(self, bande, testo_originale, scala: float, nome_font: str) -> int:
        if self.bloccata:
            return self.corpo
        c = corpo_del_gioco(bande, testo_originale, scala, nome_font)
        if c <= 0:
            return self.corpo or 8
        # **Una stima molto lontana dalle altre non e' una taglia nuova, e' una
        # lettura sbagliata.** Senza questa riga, una riga letta a meta' fa
        # scrivere la battuta successiva al doppio.
        if self.corpo and not (0.6 * self.corpo <= c <= 1.6 * self.corpo):
            return self.corpo
        self.viste.append(c)
        del self.viste[: -self.quante]

        import statistics

        self.corpo = int(round(statistics.median(self.viste)))
        # Bloccata quando ci sono abbastanza stime **e sono d'accordo**: se
        # ballano ancora, il gioco non e' quello che si crede e si continua a
        # guardare.
        if len(self.viste) >= self.bastano:
            recenti = self.viste[-self.bastano:]
            if max(recenti) - min(recenti) <= max(1, int(0.12 * self.corpo)):
                self.bloccata = True
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
    # **Solo le righe che stanno col gruppo.** `classify_lines` scarta le righe
    # colorate ma non un dito chiaro contro una camicia scura: quello entra come
    # riga acromatica, e la cancellatura ci lascia sopra una toppa — vista a
    # schermo, accanto al testo. La riga di sottotitolo piu' larga e' il
    # sottotitolo; cio' che non le sta accanto in orizzontale non e' testo suo.
    # L'ancora e' la riga che passa per il **centro** della ROI, non la piu'
    # larga: i sottotitoli sono centrati, e un braccio chiaro puo' benissimo
    # essere piu' largo della riga di testo — prendendolo come ancora si
    # scarterebbe il testo e si terrebbe il braccio.
    centro = pezzo.shape[1] // 2
    passanti = [b for b in bande if b[0] <= centro <= b[2]]
    larga = max(passanti or bande, key=lambda b: b[2] - b[0])
    bande = [
        b for b in bande
        if min(b[2], larga[2]) - max(b[0], larga[0])
        >= 0.3 * min(b[2] - b[0], larga[2] - larga[0])
    ]
    peso = float(sum(r.x1 - r.x0 for r in righe)) or 1.0
    canali = [sum(r.rgb[i] * (r.x1 - r.x0) for r in righe) / peso for i in range(3)]
    rett = (rx / w_f, ay0 / h_f, rw / w_f, (ay1 - ay0) / h_f)
    return pezzo, bande, rett, (canali[2], canali[1], canali[0])


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
        centra: bool | None = None,
    ) -> None:
        from PIL import Image, ImageDraw

        self.bande = list(bande)
        # **Quanto e' alta una riga di questo gioco.** Al rinfresco arrivano le
        # bande di adesso, e li' dentro puo' esserci di tutto: dal vivo un dito
        # chiaro contro una camicia scura e' passato per una riga di testo, e la
        # cancellatura ci e' passata sopra lasciando un rettangolo grigio. Una
        # riga di sottotitolo e' alta quanto le altre; il resto no.
        self.alta = max(1, max(y1 - y0 for _, y0, _, y1 in bande))
        self.modo = (modo or "blur").lower()
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
        limite = max(80, limite)

        # **Una traduzione lunga va a capo, e se non basta rimpicciolisce.**
        # Nell'ordine, perche' l'ordine e' quello che tiene la resa piu' vicina
        # all'originale: prima si mandano a capo le parole (il gioco fa lo
        # stesso), e solo se cosi' occuperebbe piu' di `righe_max` si stringe il
        # carattere. Non c'e' un terzo passo perche' non serve: a quel punto ci
        # sta. Quello che **non** si fa mai e' lasciarla uscire dai lati o
        # tagliarla — un sottotitolo illeggibile e' peggio di uno un po' piccolo.
        testo = (testo or "").strip()
        righe_max = 3
        self.righe = _righe(misura, testo, self.font, limite)
        while len(self.righe) > righe_max and self.corpo > 10:
            self.corpo = max(10, int(self.corpo * 0.92))
            self.font = carica_font(nome_font, self.corpo)
            self.righe = _righe(misura, testo, self.font, limite)
        self.passo = int(round(self.corpo * 1.22))
        largh = int(max(misura.textlength(r, font=self.font) for r in self.righe))
        alt = self.passo * len(self.righe)

        # **Un rettangolo solo, quello che circoscrive il sottotitolo.**
        # Prima la tela era larga quanto tutta la fascia e dentro si cancellava
        # riga per riga, inseguendo l'inchiostro fotogramma per fotogramma. Da
        # li' venivano tutti i difetti visti a schermo: toppe accanto al testo,
        # macchie sull'asfalto, righe cancellate che non erano righe. Il
        # rettangolo si calcola **una volta**, alla comparsa, e non si muove
        # piu': e' l'ingombro delle righe che l'OCR ha letto, piu' un margine.
        pad = self.contorno + 3
        m = max(4, int(0.35 * self.alta))
        rx0 = max(0, min(b[0] for b in bande) - m)
        ry0 = max(0, min(b[1] for b in bande) - m)
        rx1 = min(w_pezzo, max(b[2] for b in bande) + m)
        ry1 = min(h_pezzo, max(b[3] for b in bande) + m)
        self.taglio = (rx0, ry0, rx1, ry1)  # nel pezzo, pixel del fotogramma

        # La tela e' l'unione fra quel rettangolo e il testo tradotto: se la
        # traduzione e' piu' lunga dell'originale deve starci, e se e' piu'
        # corta il rettangolo resta comunque coperto.
        sx0, sy0, sx1, sy1 = (su(rx0), su(ry0), su(rx1), su(ry1))
        # **Il testo si centra dove il gioco centra i suoi, non su cio' che
        # l'OCR e' riuscito a leggere.** Se la lettura e' parziale — succede, e
        # nel log si vede: `Recupe`, `that youTL` — il rettangolo dell'inchiostro
        # e' stretto e spostato, e centrandoci sopra la traduzione finisce
        # decentrata rispetto al sottotitolo vero. Il centro dell'area scelta
        # dall'utente e' invece stabile per costruzione: e' li' che il gioco
        # scrive.
        #
        # Ci si centra solo se l'inchiostro **e' effettivamente centrato** li'
        # attorno: un gioco che allinea i sottotitoli a sinistra esiste, e in
        # quel caso comanda l'inchiostro.
        centro_roi = su(w_pezzo) // 2
        centro_letto = (sx0 + sx1) // 2
        if centra is None:
            # Senza memoria si decide sulla sola battuta: si centra se cio' che
            # si e' letto e' gia' li' attorno.
            centra = abs(centro_letto - centro_roi) <= 0.18 * su(w_pezzo)
        self.cx = centro_roi if centra else centro_letto
        cy = (sy0 + sy1) // 2
        self.ty0 = cy - alt // 2
        tx0, tx1 = self.cx - largh // 2 - pad, self.cx + largh // 2 + pad
        self.ox = min(sx0, tx0)
        self.oy = min(sy0, self.ty0 - pad)
        self.larg = max(1, max(sx1, tx1) - self.ox)
        self.alt = max(1, max(sy1, self.ty0 + alt + pad) - self.oy)
        self.misura = misura

    # -- i pixel, che invece si rifanno ------------------------------------

    def disegna(self, pezzo, bande=None, opaco: bool = False):
        """La tela di adesso: il rettangolo sfocato **sui pixel di questo
        fotogramma**, e sopra il testo tradotto.

        Il *live* e' il punto. La geometria e' decisa una volta e non si muove —
        se no il sottotitolo balla — ma i pixel si riprendono a ogni giro dal
        fotogramma corrente: una toppa congelata mentre la scena si muove
        diventa un rettangolo di immagine vecchia, e si vede.

        `bande` non serve piu' e resta per compatibilita': inseguire l'inchiostro
        fotogramma per fotogramma era proprio cio' che lasciava macchie dove un
        sottotitolo non c'era mai stato.
        """
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw

        h_pezzo, w_pezzo = pezzo.shape[:2]
        x0, y0, x1, y1 = self.taglio
        x1, y1 = min(x1, w_pezzo), min(y1, h_pezzo)

        tela = Image.new("RGBA", (self.larg, self.alt),
                         (0, 0, 0, 255) if opaco else (0, 0, 0, 0))
        if opaco:
            # Senza colore-chiave il buco lo riempiono i pixel veri del gioco.
            fondo = np.array(Image.fromarray(
                np.ascontiguousarray(pezzo[:, :, :3][:, :, ::-1])
            ).resize((self.su(w_pezzo), self.su(h_pezzo))))
            su_, sx_ = max(0, -self.oy), max(0, -self.ox)
            giu = max(0, self.alt - su_ - fondo.shape[0])
            dx = max(0, self.larg - sx_ - fondo.shape[1])
            if su_ or giu or sx_ or dx:
                fondo = np.pad(fondo, ((su_, giu), (sx_, dx), (0, 0)), mode="edge")
            tela.paste(Image.fromarray(
                np.ascontiguousarray(fondo[: self.alt, : self.larg])), (0, 0))

        if self.modo != "nessuno" and x1 > x0 and y1 > y0:
            fetta = np.ascontiguousarray(pezzo[y0:y1, x0:x1, :3])
            w = max(1, self.su(x1) - self.su(x0))
            h = max(1, self.su(y1) - self.su(y0))
            if self.modo == "riquadro":
                patch = Image.new("RGB", (w, h), self.fondo_rgb)
            else:
                # **Il raggio segue l'altezza dei glifi.** `blur_strength` e'
                # dichiarato su un inchiostro alto 40 px (GTA V a 1080p): cosi'
                # lo stesso numero rende illeggibile una riga a 1080p, a 1440p e
                # su un gioco che scrive piu' grande. Sotto una certa forza il
                # sottotitolo vecchio si legge ancora attraverso il nostro.
                raggio = max(2.0, self.blur * self.alta / 40.0)
                fetta = cv2.GaussianBlur(fetta, (0, 0), sigmaX=raggio, sigmaY=raggio)
                patch = Image.fromarray(np.ascontiguousarray(fetta[:, :, ::-1]))
                patch = patch.resize((w, h))
            tela.paste(patch, (self.su(x0) - self.ox, self.su(y0) - self.oy))

        d = ImageDraw.Draw(tela)
        for i, riga in enumerate(self.righe):
            w = self.misura.textlength(riga, font=self.font)
            x = self.cx - int(w) // 2 - self.ox
            y = self.ty0 + i * self.passo - self.oy
            d.text((x, y), riga, font=self.font, fill=(*self.colore, 255),
                   stroke_width=self.contorno, stroke_fill=(0, 0, 0, 255))
        return tela, (self.ox, self.oy)


def dipingi(pezzo, bande, testo: str, opaco: bool = False, **kw):
    """Decide e disegna in un colpo solo. `None` se non c'e' niente da coprire."""
    if not bande:
        return None
    return Sostituzione(pezzo, bande, testo, **kw).disegna(pezzo, opaco=opaco)


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
        trasparente: bool = True,
    ) -> None:
        self.blur = max(0.0, blur)
        # **Spegnerla serve solo a fotografarla.** La finestra e' esclusa dalla
        # cattura, e uno screenshot *e'* una cattura: con l'esclusione accesa
        # l'overlay non compare in nessuna immagine, nemmeno nelle nostre. Per
        # guardarlo si spegne, e si riaccende — non e' un'opzione da config,
        # perche' spenta l'OCR ricomincia a leggere noi.
        self.escludi_cattura = escludi_cattura
        # `trasparente` = il buco e' un colore-chiave. Spento, la finestra e'
        # opaca e il buco lo riempiono i pixel del gioco: piu' rozzo (la scena
        # dietro e' ferma fra un rinfresco e l'altro) ma **si vede sempre**.
        self.trasparente = trasparente
        self.modo = (modo or "cancella").lower()
        self.nome_font = font
        self.contorno = contorno
        # Vuoto e zero vogliono dire «come il gioco», e sono i default: un colore
        # e una misura scelti da noi sarebbero un cartello appiccicato sopra il
        # sottotitolo invece del sottotitolo.
        self.colore = self._rgb(colore) if colore else None
        self.misura = MisuraCarattere()
        self.sost = None     # la battuta a schermo adesso, con la sua geometria
        self.t_on = -1.0     # quale sottotitolo del gioco sta traducendo
        self._vuoti = 0      # giri di seguito senza inchiostro del gioco
        # L'ultima tela disegnata e dove sta sullo schermo. La legge la
        # telecamera virtuale: **gli stessi pixel** che sono a schermo, non
        # una seconda composizione che divergerebbe al primo ritocco.
        self.ultima = None
        self.vision = None   # le soglie con cui ritrovare l'inchiostro
        self.rett = None
        self.fondo_rgb = self._rgb(fondo) if fondo else (0, 0, 0)
        self.font_frac = font_frac
        self._foto = None
        self.schermo = (root.winfo_screenwidth(), root.winfo_screenheight())
        # **Dove sta il gioco.** Catturando una finestra, le coordinate del
        # fotogramma sono le sue, non quelle dello schermo: senza questo
        # rettangolo l'overlay cadrebbe sulla stessa *frazione* di schermo
        # invece che sulla stessa frazione di finestra, cioe' quasi sempre
        # altrove. `None` = si cattura lo schermo intero, ed e' come prima.
        self.ancora = None

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
        ax, ay, aw, ah = self.ancora or (0, 0, *self.schermo)
        x, y, w, h = roi
        return (max(1, int(aw * w)), max(1, int(ah * h)), ax + int(aw * x), ay + int(ah * y))

    def riposiziona(self, roi) -> None:
        """La ROI e' cambiata (il selettore d'area): il ripiego deve seguirla."""
        self.geom = self._geom_roi(roi)

    def aggancia(self, rett_px) -> None:
        """Il gioco sta li'. Si richiama quando la finestra si sposta.

        Costa una chiamata a Windows e va rifatta spesso: una finestra che si
        sposta senza che l'overlay la segua e' un sottotitolo tradotto in mezzo
        al desktop.
        """
        self.ancora = tuple(int(v) for v in rett_px) if rett_px else None

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
        if self.trasparente:
            try:
                self.top.attributes("-transparentcolor", CHIAVE)
            except tk.TclError:  # pragma: no cover
                print("overlay: colore trasparente non disponibile", file=sys.stderr)
        self._dichiara_esclusione()

    def esclusione(self, attiva: bool) -> None:
        """Accende o spegne l'esclusione dalla cattura, a finestra gia' aperta.

        **Serve solo a chi cattura lo schermo intero.** Li' la nostra finestra
        rientra nel fotogramma dato all'OCR — misurato, il 100% dei suoi pixel —
        e va nascosta. Scegliendo la finestra del gioco non rientra affatto
        (misurato: zero righe lette che fossero nostre su quattro), e allora
        nascondere l'overlay a **tutte** le catture e' un prezzo pagato per
        niente: e' quello che lo rende invisibile anche a OBS, e sospettato di
        renderlo invisibile e basta quando si somma al colore-chiave.

        Si rimette a `WDA_NONE` invece di omettere la chiamata: l'affinita' e'
        una proprieta' della finestra, e ometterla lascia quella di prima.
        """
        self.escludi_cattura = bool(attiva)
        if sys.platform != "win32":
            return
        import ctypes

        WDA_EXCLUDEFROMCAPTURE = 0x00000011
        u32 = ctypes.windll.user32
        hwnd = u32.GetParent(self.top.winfo_id()) or self.top.winfo_id()
        u32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE if attiva else 0)

    def _dichiara_esclusione(self) -> None:
        """Applica l'esclusione decisa alla nascita, e dice se non ci riesce.

        Un ripiego che non si dichiara e' peggio di un errore: senza esclusione,
        chi cattura lo schermo ci legge, e il difetto sembra dell'OCR.
        """
        self.esclusione(self.escludi_cattura)
        if not self.escludi_cattura:
            print("overlay: non escluso dalla cattura — giusto se si cattura una "
                  "finestra, sbagliato se si cattura lo schermo", file=sys.stderr)

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

    def aggiorna(self, pezzo) -> None:
        """Rifa' **la sfocatura** sui pixel nuovi, senza muovere niente.

        Arriva gia' ritagliato: mandare tutto il fotogramma trenta volte al
        secondo vorrebbe dire copiare 11 MB a giro per usarne mezzo.

        La geometria non si tocca — se no il sottotitolo balla — ma i pixel
        sotto sono quelli di adesso, se no la macchia sfocata resta indietro
        rispetto alla scena che scorre.
        """
        if self.sost is None or not self._visibile or pezzo is None:
            return
        if pezzo.shape[:2] != self.sost.forma:
            return
        try:
            tela, _ = self.sost.disegna(pezzo, opaco=not self.trasparente)
        except Exception:  # pragma: no cover - meglio una toppa vecchia che un crollo
            return
        from PIL import ImageTk

        self._foto = ImageTk.PhotoImage(
            su_chiave(tela) if self.trasparente else tela.convert("RGB"), master=self.top
        )
        self.etichetta.configure(image=self._foto)
        self.ultima = (tela, self.top.winfo_x(), self.top.winfo_y())

    def _prepara(self, testo, pezzo, bande, rett, inchiostro, originale=""):
        from PIL import ImageTk

        sw, sh = self.schermo
        ax, ay, aw, ah = self.ancora or (0, 0, sw, sh)
        h_pezzo, w_pezzo = pezzo.shape[:2]
        scala = (rett[2] * aw) / max(1, w_pezzo)
        self.misura.guarda_allineamento(bande, pezzo.shape[1])
        corpo = (int(sh * self.font_frac) if self.font_frac > 0
                 else self.misura.aggiorna(bande, originale, scala, self.nome_font))
        self.sost = Sostituzione(
            pezzo, bande, testo,
            scala=scala, nome_font=self.nome_font, colore=self.colore,
            corpo=corpo, contorno=self.contorno, blur=self.blur,
            inchiostro_rgb=inchiostro, modo=self.modo, fondo_rgb=self.fondo_rgb,
            testo_originale=originale, larghezza_schermo=min(aw, sw),
            centra=self.misura.centra or None,
        )
        self.rett = rett
        self._vuoti = 0
        tela, (ox, oy) = self.sost.disegna(pezzo, opaco=not self.trasparente)
        piatta = su_chiave(tela) if self.trasparente else tela.convert("RGB")
        foto = ImageTk.PhotoImage(piatta, master=self.top)
        x = ax + int(rett[0] * aw) + ox
        y = ay + int(rett[1] * ah) + oy
        geom = (piatta.width, piatta.height,
                max(0, min(sw - piatta.width, x)), max(0, min(sh - piatta.height, y)))
        self.ultima = (tela, geom[2], geom[3])
        return foto, geom

    def nascondi(self) -> None:
        self.sost = None
        self.ultima = None
        self.t_on = -1.0
        if self._visibile:
            self.top.withdraw()
            self._visibile = False

    def distruggi(self) -> None:
        try:
            self.top.destroy()
        except tk.TclError:  # pragma: no cover
            pass
