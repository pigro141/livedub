"""Dove stanno le scritte quando sono **piu' di una** e non si sa dove.

`vision/lines.py` risponde alla domanda «dov'e' la riga di sottotitolo», e la
risponde bene perche' e' costruito su un'ipotesi: il testo sta in una fascia
stretta e ce n'e' uno solo. Da li' due scelte che qui diventano difetti:

- **le bande si trovano sul profilo delle righe-pixel** (`find_bands`), quindi
  due scritte affiancate alla **stessa altezza** — il nome della strada a
  sinistra e il conta-munizioni a destra — sono una banda sola;
- **fra i blocchi orizzontali se ne tiene uno**, quello piu' vicino al centro
  (`line_gap_split`). E' giusto per un sottotitolo con dell'HUD accanto, ed e'
  esattamente il contrario di quello che serve qui, dove l'HUD **e'** il
  bersaglio.

Quindi questo modulo non tara quelli: ne aggiunge uno **prima**. Trova i
rettangoli dove c'e' del testo, e a ciascuno si applica poi `classify_lines`
com'e'. La localizzazione e' nuova, la classificazione — colore, maschera,
ritaglio per l'OCR, la grammatica delle righe — resta quella gia' misurata.

**Come si trovano.** Maschera del testo, dilatazione, componenti connesse. La
dilatazione e' la parte che decide tutto: salda i glifi in parole, le parole in
righe e le righe in blocchi, e **non deve saldare due scritte diverse**. Il
raggio non e' un numero di pixel ma un multiplo dell'altezza di una riga
(`riga_px`), che e' l'unica unita' che non cambia con la risoluzione — la stessa
scelta gia' fatta per `color_word_gap` e `line_gap_split`.

**E si lavora sottocampionati.** Localizzare non ha bisogno della piena
risoluzione: i dettagli che si perdono sono le forme dei glifi, e qui non si
legge niente. Il ritaglio che poi va all'OCR e' preso dal fotogramma intero, a
risoluzione piena. Misurato in `tools/bench_schermo.py`: e' la differenza fra
una modalita' che gira e una che non gira.

**Il nucleo che il sottocampionamento non puo' mangiare.** `text_mask` chiede
che il pixel stacchi dal proprio intorno, e quell'intorno e' `contrast_kernel`
pixel: sottocampionando di `stride` la finestra diventa `stride` volte piu'
larga di quella voluta e la maschera cambia significato. Il nucleo si rimpicciola
insieme all'immagine — e' lo stesso pezzo di codice che `RoiDiff._ink` ha gia'
dovuto scrivere, e per la stessa ragione.

**Il tetto al numero di blocchi non e' prudenza, e' il costo.** Ogni blocco e'
una chiamata all'OCR, e l'OCR e' l'85% del lavoro della catena. Uno schermo
intero di gioco ne offre molti piu' di quanti se ne possano leggere a 30 Hz:
quindi si tengono i piu' grossi e si **dichiara** quanti se ne sono buttati, che
e' l'unico modo perche' «non l'ha tradotto» non si confonda con «non l'ha
visto».
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Blocco:
    """Un rettangolo di testo trovato nell'area, in pixel dell'area."""

    x0: int
    y0: int
    x1: int  # escluso
    y1: int  # escluso
    inchiostro: int = 0  # pixel di testo dentro: serve a ordinarli, non a giudicarli

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def h(self) -> int:
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        return self.w * self.h


# **Quanto e' alta una riga di testo, in frazione dell'altezza del fotogramma.**
# Da qui escono tutti i raggi di questo modulo. 0,030 sono 43 px su 1440 e 32 su
# 1080: i sottotitoli di GTA V ne misurano 45 a 1440p, l'HUD un po' meno.
#
# Non e' una misura dello schermo dell'utente: e' un **punto di partenza
# dichiarato**, e sbagliarlo di poco non rompe niente (le distanze fra scritte
# diverse sono molto piu' grandi delle distanze dentro una scritta). Sbagliarlo
# del doppio si': troppo grande salda due scritte vicine, troppo piccolo spezza
# una frase in due blocchi.
RIGA_FRAC = 0.030

# **I due raggi della saldatura**, in multipli dell'altezza di una riga.
#
# Orizzontale: dev'essere piu' largo di uno spazio fra due parole e piu' stretto
# della distanza fra due scritte diverse. Lo spazio fra due parole e' gia'
# misurato altrove in questo progetto (`_chiudi_buchi`): 0,375-0,438 dell'altezza
# della banda. 0,8 sta al doppio di li' e continua a non saldare due scritte, che
# sullo schermo di un gioco stanno a diverse altezze di riga l'una dall'altra.
#
# Verticale: dev'essere piu' largo dell'interlinea (una riga di sottotitolo su
# due righe lascia 0,2-0,5 di vuoto fra l'una e l'altra) e piu' stretto della
# distanza fra due blocchi. 0,5 e' dentro quell'intervallo.
GAP_X = 0.8
GAP_Y = 0.5

# Sottocampionamento della localizzazione. 2 e non 4: a 4 una riga da 43 px ne
# diventa 11, e la dilatazione verticale (0,5 * 43 / 4 = 5) comincia a saldare
# due righe di blocchi diversi.
STRIDE = 2

# **Quanti blocchi al massimo.** Non e' una soglia di qualita': e' il budget
# dell'OCR, e sta qui perche' e' qui che si scelgono. Si veda il commento in
# testa.
MAX_BLOCCHI = 12


def _maschera(piccolo: np.ndarray, cfg, stride: int) -> np.ndarray:
    """La maschera del testo su un'immagine gia' sottocampionata.

    Non e' `vision.lines.text_mask` con un'immagine piu' piccola: il nucleo del
    contrasto locale va rimpicciolito insieme all'immagine, se no guarda una
    finestra `stride` volte piu' larga di quella dichiarata e la maschera
    risponde a un'altra domanda. Stesso identico aggiustamento di
    `RoiDiff.contrast_kernel`, dove e' gia' costato una taratura.
    """
    if piccolo.ndim == 3:
        luma = piccolo[:, :, :3].astype(np.float32).mean(axis=2)
    else:
        luma = piccolo.astype(np.float32)
    assoluta = luma > cfg.grey_min_luma
    if not getattr(cfg, "use_local_contrast", True) or not assoluta.any():
        return assoluta
    try:
        import cv2
    except ImportError:  # pragma: no cover - opencv assente
        return assoluta
    k = max(3, (int(cfg.contrast_kernel) // max(1, stride)) | 1)
    fondo = cv2.blur(luma, (k, k))
    return assoluta & ((luma - fondo) > cfg.contrast_min)


def trova(
    roi: np.ndarray,
    cfg,
    riga_px: float,
    *,
    stride: int = STRIDE,
    gap_x: float = GAP_X,
    gap_y: float = GAP_Y,
    massimo: int = MAX_BLOCCHI,
) -> tuple[list[Blocco], int]:
    """I rettangoli di testo dentro `roi`. Torna `(blocchi, quanti scartati)`.

    `riga_px` e' quanto e' alta **una riga** di testo, in pixel dell'immagine
    che si sta guardando: la decide chi chiama, dal fotogramma e da `RIGA_FRAC`.
    Tutti i raggi qui dentro sono suoi multipli, quindi la funzione non sa e non
    deve sapere a che risoluzione sta girando.

    Il secondo numero non e' decorativo: senza, «quel cartello non e' stato
    tradotto» non si distingue da «quel cartello non e' stato visto», e sono due
    difetti in due posti diversi.
    """
    if roi is None or roi.size == 0 or riga_px <= 0:
        return [], 0
    try:
        import cv2
    except ImportError:  # pragma: no cover - opencv assente
        return [], 0

    stride = max(1, int(stride))
    piccolo = roi[::stride, ::stride]
    if piccolo.shape[0] < 4 or piccolo.shape[1] < 4:
        return [], 0
    maschera = _maschera(piccolo, cfg, stride)
    if not maschera.any():
        return [], 0

    r = riga_px / stride
    kx = max(1, int(round(gap_x * r)))
    ky = max(1, int(round(gap_y * r)))
    # Un rettangolo e non una croce: due parole sulla stessa riga si saldano in
    # orizzontale, due righe dello stesso blocco in verticale, e il caso misto —
    # la seconda riga piu' corta e spostata — ha bisogno di tutti e due insieme.
    nucleo = np.ones((2 * ky + 1, 2 * kx + 1), np.uint8)
    saldato = cv2.dilate(maschera.astype(np.uint8), nucleo)
    n, etichette, stat, _ = cv2.connectedComponentsWithStats(saldato, 8)

    # Le soglie di forma, tutte in multipli dell'altezza di una riga. Sono
    # **grossolane apposta**: qui si decide solo cosa vale una chiamata all'OCR,
    # e a giudicare se e' testo c'e' gia' `classify_lines` dopo, con le soglie
    # che sono state misurate per quello.
    h_min = 0.45 * r
    w_min = 0.60 * r
    trovati: list[Blocco] = []
    for i in range(1, n):
        x, y, w, h, _ = stat[i]
        if h < h_min or w < w_min:
            continue
        dentro = maschera[y : y + h, x : x + w]
        inchiostro = int(dentro.sum())
        if inchiostro <= 0:
            continue
        pieno = inchiostro / float(max(1, w * h))
        # **Una macchia piena non e' testo, e nemmeno una traccia sottile.** Una
        # carrozzeria bianca al sole riempie il suo rettangolo quasi tutto; un
        # bordo di scenario quasi niente. Il testo sta in mezzo — e' la stessa
        # misura di `_sembra_testo` in `ui/overlay.py`, dove gli intervalli sono
        # stati presi su fotogrammi veri (riempimento 0,036-0,27 per il testo,
        # 0,014-0,015 per lo scenario). Qui si allarga da tutte e due le parti,
        # perche' la dilatazione ha gia' riempito i vuoti fra i glifi.
        if not (0.02 <= pieno <= 0.75):
            continue
        trovati.append(
            Blocco(
                x0=int(x * stride),
                y0=int(y * stride),
                x1=int(min(roi.shape[1], (x + w) * stride)),
                y1=int(min(roi.shape[0], (y + h) * stride)),
                inchiostro=inchiostro,
            )
        )

    # **Si tengono i piu' grossi**, e i piu' grossi per inchiostro e non per
    # superficie: un rettangolo largo e vuoto e' proprio cio' che si vuole
    # perdere per primo, e ordinare per superficie lo metterebbe in cima.
    trovati.sort(key=lambda b: b.inchiostro, reverse=True)
    scartati = max(0, len(trovati) - int(massimo))
    trovati = trovati[: int(massimo)]
    # Rimessi in ordine di lettura: prima l'alto, poi la sinistra. Non cambia
    # niente per la catena e cambia tutto per chi legge un log.
    trovati.sort(key=lambda b: (b.y0, b.x0))
    return trovati, scartati


def allarga(b: Blocco, riga_px: float, forma: tuple[int, int]) -> Blocco:
    """Il blocco con un margine attorno, senza uscire dall'immagine.

    Serve perche' `classify_lines` girera' **dentro** questo rettangolo, e li'
    dentro ha bisogno di respiro: la sua maschera cerca il chiaro che stacca dal
    fondo, e un ritaglio che finisce sul primo pixel di inchiostro non ha fondo
    da nessuna parte. E' la stessa ragione per cui esiste `line_pad`, misurata li'
    sopra: senza margine una banda alta 20 px non veniva letta **affatto**.
    """
    m = max(2, int(round(0.30 * riga_px)))
    h, w = forma[:2]
    return Blocco(
        x0=max(0, b.x0 - m),
        y0=max(0, b.y0 - m),
        x1=min(w, b.x1 + m),
        y1=min(h, b.y1 + m),
        inchiostro=b.inchiostro,
    )
