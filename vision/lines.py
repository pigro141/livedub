"""Dalla ROI alle righe di testo, classificate per colore.

E' il primo stadio del dominio video e la fondamenta di tutto il resto: se qui
una riga di suggerimento passa per dialogo, il doppiaggio legge ad alta voce
"premi E per entrare"; se una riga grigia viene fusa con quella bianca sopra,
due personaggi diventano uno.

**Nota sull'ordine dei canali.** Le due grandezze usate per classificare sono la
luminanza (media sui canali) e la saturazione (max meno min sui canali):
entrambe sono simmetriche rispetto all'ordine dei canali, quindi RGB e BGR danno
lo stesso risultato. Non e' un caso ma una scelta — la cattura Windows produce
BGRA e un'inversione di canali e' il tipo di bug che non da' errore, cambia solo
i risultati. Qui non puo' succedere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.config import VisionConfig
from core.types import LineClass


@dataclass(slots=True)
class LineBand:
    """Una banda orizzontale di testo trovata nella ROI."""

    top: int
    bottom: int  # incluso
    cls: LineClass
    luma: float  # luminanza del corpo dei glifi acromatici
    sat: float  # saturazione di picco sui pixel di testo
    # Ritaglio pronto per l'OCR: la luminanza vera dove c'e' testo, nero
    # altrove. NON binario, e la differenza si misura — il riconoscitore e'
    # addestrato su testo antialiasato, e una maschera a due livelli gli toglie
    # proprio le sfumature dei bordi su cui conta. Passando dal binario al
    # grigio mascherato il CER scende da 4,4% a 2,9% sul bianco e da 5,5% a
    # 4,0% sul grigio, a parita' di costo.
    crop: np.ndarray
    x0: int = 0
    x1: int = 0  # escluso
    # **Il colore medio dell'inchiostro**, 0-255 per canale. Serve ai giochi che
    # danno un colore a ciascun personaggio (`vision/label.py`): la sola coppia
    # luminanza+saturazione non lo puo' dire — un blu e un rosso della stessa
    # intensita' hanno gli stessi due numeri, quindi la misura non poteva
    # esprimere la risposta. Su GTA V non lo guarda nessuno, e non costa niente:
    # sono i pixel gia' mascherati.
    rgb: tuple[float, float, float] = (0.0, 0.0, 0.0)
    sat_share: float = 0.0  # quota dell'inchiostro che e' satura: 0 = riga pulita
    # La riga e' stata scartata perche' conteneva una **parola** colorata, non
    # per la quota. E' un campo e non un booleano interno perche' senza di lui
    # non c'e' modo di distinguere "il criterio non e' scattato" da "il criterio
    # e' spento" — e questo progetto ha gia' pagato due volte per un trattamento
    # creduto applicato e mai applicato.
    color_word: bool = False

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x0, self.top, self.x1 - self.x0, self.height)


def luma_sat(roi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Luminanza e saturazione della ROI, come float32.

    Su un'immagine a 3 canali entrambe si calcolano senza sapere se e' RGB o
    BGR. Se arriva un canale alfa (BGRA della cattura Windows) viene scartato.
    """
    if roi.ndim == 2:
        luma = roi.astype(np.float32)
        return luma, np.zeros_like(luma)
    if roi.ndim != 3:
        raise ValueError(f"ROI con forma inattesa: {roi.shape}")
    rgb = roi[:, :, :3].astype(np.float32)
    luma = rgb.mean(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    return luma, sat


def find_bands(
    text_mask: np.ndarray,
    min_height: int,
    min_pixels: int = 1,
    grow: float = 0.45,
) -> list[tuple[int, int]]:
    """Righe di testo come gruppi di righe-pixel contigue non vuote.

    **Due soglie, non una, ed e' il punto di tutta la funzione.** `min_pixels`
    alza l'asticella su quanti pixel servono perche' una riga-pixel *apra* una
    banda: uno solo e' rumore di compressione, non una lettera. Ma la stessa
    asticella applicata ai bordi taglia le lettere.

    Misurato su GTA V, ROI larga 1136 px e quindi `min_pixels` = 11: le righe
    dove passano solo le **code** di g, q, p ne hanno tre o quattro, restano
    fuori dalla banda, e il ritaglio che arriva all'OCR e' un testo decapitato.
    Il modello poi non sbaglia affatto — legge esattamente quello che vede:

        Oggi recuperiamo veicoli acquistati  ->  Oaai recuperiamo veicoli acauistati
        figlio                               ->  fialio
        negri!                               ->  near!
        avessi, vorrei, insieme              ->  avessl, vorrel, insleme
        che                                  ->  cne

    Una `g` senza coda **e'** una `a`, una `i` senza punto **e'** una `l`. Non e'
    un errore di riconoscimento, e' una domanda diversa.

    Quindi: il nucleo della banda si trova con `min_pixels` (robusto al rumore),
    poi si **estende** sopra e sotto finche' c'e' anche un solo pixel di testo,
    al massimo di `grow` volte l'altezza del nucleo. Il limite serve a non far
    saldare due righe vicine quando la coda di una tocca l'asta dell'altra.
    """
    profile = text_mask.sum(axis=1)
    active = profile >= min_pixels
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for i, on in enumerate(active):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= min_height:
                bands.append((start, i - 1))
            start = None
    if start is not None and len(active) - start >= min_height:
        bands.append((start, len(active) - 1))

    if grow <= 0 or not bands:
        return bands
    return [_grow(top, bottom, profile, grow) for top, bottom in bands]


def _grow(top: int, bottom: int, profile: np.ndarray, grow: float) -> tuple[int, int]:
    """Allarga la banda finche' trova pixel di testo, entro il limite."""
    margin = max(1, int(round((bottom - top + 1) * grow)))
    lo = top
    while lo > 0 and top - lo < margin and profile[lo - 1] > 0:
        lo -= 1
    hi = bottom
    n = len(profile)
    while hi < n - 1 and hi - bottom < margin and profile[hi + 1] > 0:
        hi += 1
    return lo, hi


def _estensione(colonne: np.ndarray) -> int:
    """Da dove comincia a dove finisce l'inchiostro della riga, in pixel.

    Non la somma delle colonne accese: l'**estensione**, dalla prima all'ultima.
    Fra due parole c'e' uno spazio, e uno spazio fa parte della frase quanto le
    lettere — contarne solo l'inchiostro darebbe una riga piu' corta di com'e' e
    farebbe sembrare ogni parola piu' larga di quanto sia.
    """
    accese = np.flatnonzero(colonne)
    return int(accese[-1] - accese[0] + 1) if accese.size else 0


def _chiudi_buchi(colonne: np.ndarray, max_buco: int) -> np.ndarray:
    """Riempie i vuoti stretti fra colonne accese. Una parola torna un tratto solo.

    **Serve perche' una parola non e' contigua, e crederlo ha spento il
    criterio.** Fra una lettera e l'altra c'e' del fondo, quindi la corsa piu'
    lunga di colonne colorate non misurava la parola: misurava **la lettera piu'
    larga**. Su «Raggiungi la destinazione» con `destinazione` colorata la corsa
    valeva 17-21 px su 415 di riga — quota 0,04 contro una soglia di 0,15 — e il
    criterio non poteva scattare mai, per nessuna parola, di nessuna lunghezza.
    Restava in piedi la sola quota `sat_ink_max`, che vede la riga solo quando il
    colorato e' almeno un quarto dell'inchiostro: le righe di missione con una
    parola corta evidenziata passavano, e venivano lette.

    Il vuoto da chiudere si misura in **quote dell'altezza della banda**, che e'
    l'unica unita' che non dipende dalla risoluzione ne' da quanto grande scrive
    il gioco. Misurato su Arial grassetto a 20, 34 e 60 punti:

    | vuoto | quota dell'altezza |
    |---|---|
    | fra due lettere della stessa parola | 0,16 - 0,205 |
    | fra due parole (lo spazio) | 0,375 - 0,438 |

    In mezzo c'e' un altopiano largo, e `color_word_gap` ci sta dentro con un
    fattore due da tutte e due le parti: chiude le lettere, non salda le parole.
    """
    if max_buco <= 0 or colonne.size == 0 or not colonne.any():
        return colonne
    accese = np.flatnonzero(colonne)
    fuori = colonne.copy()
    salti = np.flatnonzero(np.diff(accese) - 1 <= max_buco)
    for i in salti:
        fuori[accese[i] : accese[i + 1]] = True
    return fuori


def _corsa_piu_lunga(colonne: np.ndarray) -> int:
    """La corsa contigua piu' lunga di colonne accese, in pixel.

    Serve a distinguere una **parola** colorata da pixel colorati sparsi. Lo
    scenario che entra nella ROI lascia macchie e puntini; una parola lascia un
    tratto continuo largo quanto lei. Contarli tutti insieme, come faceva la
    quota, mette le due cose nello stesso numero.

    Va chiamata su colonne gia' passate da `_chiudi_buchi`: da sola misura una
    lettera, non una parola.
    """
    if colonne.size == 0 or not colonne.any():
        return 0
    massimo = corrente = 0
    for acceso in colonne:
        corrente = corrente + 1 if acceso else 0
        if corrente > massimo:
            massimo = corrente
    return massimo


def text_mask(luma: np.ndarray, cfg: VisionConfig) -> np.ndarray:
    """Quali pixel sono testo.

    La soglia assoluta da sola non basta: sotto un cielo chiaro l'intera ROI la
    supera, le bande si fondono in una sola e il sottotitolo sparisce. Misurato
    su frame sintetici, succede da luminanza di fondo 120 in su.

    Il testo di gioco pero' e' bordato di nero, quindi il fondo *locale* sotto un
    glifo e' scuro qualunque cosa ci sia dietro. Togliendo una stima del fondo
    locale (media su una finestra larga) il limite si sposta a 180, al costo di
    ~0,7 ms per frame.

    **Limite noto**, da sciogliere sulla registrazione vera: testo piu' scuro di
    cio' che lo circonda — una riga grigia su una scena molto chiara — non viene
    trovato, perche' questo operatore cerca il chiaro sullo scuro. Quanto sia un
    caso reale in GTA V lo dice il video, non un frame inventato: fino ad allora
    e' una supposizione da non ottimizzare.
    """
    absolute = luma > cfg.grey_min_luma
    if not cfg.use_local_contrast:
        return absolute
    try:
        import cv2
    except ImportError:  # pragma: no cover - opencv assente
        return absolute
    k = max(3, int(cfg.contrast_kernel) | 1)  # dispari
    background = cv2.blur(luma, (k, k))
    return absolute & ((luma - background) > cfg.contrast_min)


def classify_lines(roi: np.ndarray, cfg: VisionConfig) -> list[LineBand]:
    """Trova le righe nella ROI e assegna a ciascuna la sua classe cromatica.

    Il corpo del glifo si misura con un **percentile alto** della luminanza, non
    con la mediana: il testo di gioco e' antialiasato e bordato di nero, quindi
    la maschera di un testo bianco contiene molti pixel di bordo scuri che
    tirerebbero la mediana verso il basso fino a confondere il bianco col
    grigio. Il 90esimo percentile guarda il cuore delle lettere, che e' la cosa
    che davvero distingue le due classi.

    **L'inchiostro saturo non e' testo, ed esce prima di tutto il resto.** Un
    glifo di dialogo e' bianco o grigio per definizione, quindi un pixel saturo
    dentro la banda o e' un glifo colorato — e allora la riga non e' dialogo —
    oppure e' scenario entrato nella ROI, e va tolto e basta. A distinguere i
    due casi e' la **quota**: si veda `VisionConfig.sat_ink_max`. Togliere quei
    pixel migliora anche il ritaglio che va all'OCR, che altrimenti si porta
    dietro pezzi di scena.
    """
    luma, sat = luma_sat(roi)
    mask = text_mask(luma, cfg)
    if not mask.any():
        return []

    # **L'esclusione delle righe colorate e' un interruttore dell'utente.** Si
    # veda `VisionConfig.exclude_colored`: il colore vuol dire l'HUD in GTA V e
    # il nome di chi parla in Mafia, e nessuna soglia distingue i due casi.
    #
    # Spegnerlo si fa alzando la soglia oltre il massimo possibile, e non e' un
    # trucco: la saturazione e' `max - min` sui canali, quindi non puo' superare
    # 255 e nessun pixel risulta colorato. Da li' in giu' tutto si spegne da
    # solo — la quota `sat_ink_max` vale 0, la corsa colorata e' vuota, e i pixel
    # colorati restano nel ritaglio invece di essere tolti. Un solo posto da
    # cambiare invece di quattro rami paralleli, che e' il modo in cui in questo
    # progetto una cura e' stata applicata a meta'.
    sat_max = cfg.sat_max if getattr(cfg, "exclude_colored", True) else 255

    min_px = max(1, int(roi.shape[1] * cfg.min_line_fill))
    out: list[LineBand] = []
    for top, bottom in find_bands(mask, cfg.min_line_height, min_px, cfg.line_grow):
        band_mask = mask[top : bottom + 1]
        if not band_mask.any():
            continue
        band_sat_img = sat[top : bottom + 1]
        band_luma_img = luma[top : bottom + 1]

        hot = band_mask & (band_sat_img > sat_max)  # inchiostro colorato
        cool = band_mask & ~hot  # i glifi bianchi o grigi, se ci sono
        n_hot, n_cool = int(hot.sum()), int(cool.sum())
        share = n_hot / max(1, n_hot + n_cool)

        # **La domanda e' "c'e' una parola colorata?", non "che percentuale di
        # questa riga e' satura".** Sono due cose diverse, e la seconda e'
        # fragile per costruzione: il denominatore e' la maschera del testo,
        # che dipende da `contrast_min`. Tarando l'OCR si spostava il filtro del
        # colore senza che niente lo dicesse — e infatti con le soglie severe di
        # una sessione dal vivo (contrasto 68,8 contro i 28,9 del profilo) del
        # glifo colorato entrano meno pixel, la quota scende sotto la soglia, e
        # una riga colorata smette di sembrare colorata.
        #
        # Una **parola** invece e' un tratto orizzontale continuo di inchiostro
        # colorato, e la sua larghezza non dipende da quanti pixel la maschera
        # lascia passare. Si guarda quindi la corsa piu' lunga di colonne che
        # contengono saturo: se e' larga come una parola, la riga non e' dialogo.
        #
        # Il colore si cerca sulla **sola soglia assoluta di luminanza**, senza
        # il contrasto locale: per dire "questo pixel e' colorato" non serve che
        # stacchi dal fondo, e chiederlo e' proprio cio' che rendeva la misura
        # dipendente dalla taratura dell'OCR. Il ritaglio per l'OCR continua a
        # usare `band_mask`, che di quel rigore ha bisogno.
        #
        # **E la larghezza si misura in frazione della riga, non in pixel.** Un
        # numero assoluto sarebbe legato alla risoluzione e a quanto largo e'
        # stato disegnato il rettangolo — che l'utente disegna come vuole, ed e'
        # il percorso di produzione dichiarato. Una parola invece occupa sempre
        # la stessa **quota** della frase che la contiene, a qualunque
        # ingrandimento.
        band_ink = band_luma_img > cfg.grey_min_luma
        colonne_ink = band_ink.any(axis=0)
        colonne_calde = (band_ink & (band_sat_img > sat_max)).any(axis=0)
        estensione = _estensione(colonne_ink)
        # **Le lettere si saldano prima di misurare la corsa**, se no si misura
        # la lettera piu' larga e il criterio non scatta per nessuna parola.
        corsa = _corsa_piu_lunga(_chiudi_buchi(
            colonne_calde, int(round(cfg.color_word_gap * (bottom - top + 1)))))
        parola_colorata = (
            cfg.min_color_word_frac > 0.0
            and estensione > 0
            and corsa / estensione >= cfg.min_color_word_frac
        )

        # Una riga di soli glifi colorati non lascia niente di acromatico: e' il
        # caso limite della stessa regola, non un caso a parte.
        colored = n_cool < min_px or share > cfg.sat_ink_max or parola_colorata
        body_mask = band_mask if colored else cool
        if not body_mask.any():
            continue

        body_luma = float(np.percentile(band_luma_img[body_mask], cfg.luma_percentile))
        peak_sat = float(np.percentile(band_sat_img[band_mask], cfg.sat_percentile))

        if colored:
            cls = LineClass.COLORED
        elif body_luma >= cfg.white_min_luma:
            cls = LineClass.WHITE
        else:
            cls = LineClass.GREY

        # Il colore medio dei pixel di testo, se la ROI e' a colori.
        if roi.ndim == 3 and roi.shape[2] >= 3:
            banda_rgb = roi[top : bottom + 1, :, :3].astype(np.float32)
            medio = banda_rgb[body_mask]
            ink_rgb = (
                (float(medio[:, 0].mean()), float(medio[:, 1].mean()), float(medio[:, 2].mean()))
                if medio.size
                else (0.0, 0.0, 0.0)
            )
        else:
            ink_rgb = (body_luma, body_luma, body_luma)

        cols = np.where(body_mask.any(axis=0))[0]
        x0, x1 = (int(cols[0]), int(cols[-1]) + 1) if cols.size else (0, roi.shape[1])
        # **Il ritaglio si ferma al blocco del sottotitolo, non all'ultima
        # colonna della riga.** Andando dalla prima all'ultima, qualunque
        # scritta sulla stessa altezza ci finisce dentro: il nome della strada,
        # la radio, il nome di un'app. L'OCR le legge di seguito alla battuta e
        # **vengono pronunciate**. Nella sessione dell'utente sono 63 battute su
        # 576 — l'11% — con dentro roba come `.San An`, `.Las Laguni`,
        # `.Del. Pe`, `Sini`, `Sp`: tutti frammenti tagliati dal bordo dell'area.
        #
        # I due si separano da soli: fra due parole il buco vale 0,4 volte
        # l'altezza della banda (p75 misurato 0,39), fra il sottotitolo e l'HUD
        # molto di piu'. E fra i blocchi si tiene **quello piu' vicino al centro**
        # dell'area, perche' GTA V scrive i sottotitoli centrati e l'HUD ai bordi
        # — la stessa ancora che sceglie la banda da sfocare.
        if cfg.line_gap_split > 0.0 and cols.size > 1:
            alt = max(1, bottom - top + 1)
            taglio = cfg.line_gap_split * alt
            stacchi = np.flatnonzero(np.diff(cols) - 1 >= taglio)
            if stacchi.size:
                bordi = [0, *(stacchi + 1), cols.size]
                centro = roi.shape[1] / 2.0
                blocchi = [(cols[a], cols[b - 1] + 1) for a, b in zip(bordi, bordi[1:])]
                a, b = min(blocchi, key=lambda z: abs((z[0] + z[1]) / 2.0 - centro))
                x0, x1 = int(a), int(b)
        # **Il ritaglio ha un margine sopra e sotto, e senza non si legge.**
        #
        # La banda finisce dove finisce l'inchiostro che la maschera ha trovato,
        # e li' dentro non ci stanno gli accenti, le code di `g` e `p` e i bordi
        # antialiasati dei glifi. Su GTA V si legge lo stesso; su un secondo
        # gioco no, e non a meta': **niente affatto**.
        #
        # Misurato sullo screenshot dell'utente, banda alta 20 px in un ritaglio
        # di 73:
        #
        #   la banda come la dava la catena  ->  (vuoto)
        #   la stessa con 4 px sopra e sotto ->  letta intera, confidenza 1,00
        #
        # E non lo curava nessuno dei parametri che sembravano fatti apposta:
        # `line_grow` lasciava la banda a 20 px a ogni valore da 0,45 a 2,00.
        #
        # **Mascherare o no non c'entra**, ed e' stato provato prima di scrivere
        # questo: col margine l'OCR legge in tutti e due i modi, su fondo scuro e
        # su fondo chiaro. Una prima versione aggiungeva un `mask_crop` per
        # spegnere la maschera; era la cura del difetto sbagliato ed e' stata
        # tolta.
        pad = int(round(cfg.line_pad * (bottom - top + 1)))
        if pad > 0:
            t0 = max(0, top - pad)
            t1 = min(luma.shape[0], bottom + 1 + pad)
            band_grey = luma[t0:t1, x0:x1] * mask[t0:t1, x0:x1]
        else:
            band_grey = band_luma_img[:, x0:x1] * body_mask[:, x0:x1]
        out.append(
            LineBand(
                top=int(top),
                bottom=int(bottom),
                cls=cls,
                luma=body_luma,
                sat=peak_sat,
                rgb=ink_rgb,
                crop=np.clip(band_grey, 0, 255).astype(np.uint8),
                x0=x0,
                x1=x1,
                sat_share=share,
                color_word=parola_colorata,
            )
        )
    return out
