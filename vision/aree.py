"""Piu' aree di lettura sullo stesso schermo, senza lavorare due volte.

**Perche' piu' di una.** Un gioco non mette tutto il testo nello stesso posto:
il dialogo sta in basso al centro, il nome di chi parla puo' stare altrove, e i
cartelli di missione hanno una loro striscia. Con una ROI sola si sceglie: o si
allarga fino a contenerli tutti — e allora dentro ci finisce mezza scena, che e'
il difetto misurato che salda le righe allo scenario — o si rinuncia.

**E non tutte servono alla stessa cosa.** Un'area di dialogo va letta *e* detta a
voce; un cartello di missione va al massimo tradotto e disegnato, ma pronunciarlo
e' esattamente il difetto che l'11% delle battute di GTA V aveva. Da qui il
`modo`: `testo_audio` legge e fa parlare, `testo` legge e basta.

**Le sovrapposizioni si tolgono, non si tollerano.** Due aree che si accavallano
farebbero leggere due volte gli stessi pixel: costo doppio sull'OCR — che e' gia'
l'85% del lavoro della catena — e soprattutto la **stessa battuta letta due
volte**, che a valle diventa due battute e due voci sovrapposte, il difetto
peggiore del prodotto. Quindi la sovrapposizione si sottrae *prima* di leggere.

**Come si sottrae, e perche' cosi'.** L'intersezione di due rettangoli si toglie
tagliando l'area in strisce: fino a quattro rettangoli (sopra, sotto, sinistra,
destra dell'intersezione), tutti ancora rettangoli. Non e' l'unica scomposizione
possibile ma e' l'unica che tiene ogni pezzo **rettangolare**, e tutto quello che
sta a valle — `classify_lines`, il diff, l'overlay — lavora su rettangoli. Una
maschera arbitraria costringerebbe a riscrivere tre stadi per un caso di bordo.

L'ordine decide chi cede: **vince l'area dichiarata prima**. E' una scelta e va
detta, perche' altrimenti sarebbe l'ordine di iterazione a decidere in silenzio
quale delle due aree perde dei pixel.
"""

from __future__ import annotations

from dataclasses import dataclass

Rettangolo = tuple[float, float, float, float]  # x, y, w, h normalizzati

MODI = ("testo_audio", "testo")


@dataclass(slots=True)
class Area:
    """Un rettangolo da leggere, e cosa farne."""

    roi: Rettangolo
    modo: str = "testo_audio"
    nome: str = ""

    def __post_init__(self) -> None:
        if self.modo not in MODI:
            raise ValueError(f"modo sconosciuto: {self.modo!r} (uno fra {', '.join(MODI)})")
        x, y, w, h = self.roi
        if w <= 0 or h <= 0:
            raise ValueError(f"area di superficie nulla: {self.roi}")

    @property
    def parla(self) -> bool:
        return self.modo == "testo_audio"


def interseca(a: Rettangolo, b: Rettangolo) -> Rettangolo | None:
    """Il rettangolo comune, o `None` se non si toccano."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def sottrai(a: Rettangolo, b: Rettangolo) -> list[Rettangolo]:
    """`a` meno `b`, come lista di rettangoli disgiunti.

    Zero pezzi se `b` copre `a` per intero, uno se non si toccano, fino a
    quattro nel caso generale: la striscia sopra e quella sotto prendono tutta la
    larghezza, quelle a sinistra e a destra solo l'altezza rimasta in mezzo — se
    no gli angoli finirebbero in due pezzi contemporaneamente, e un pixel contato
    due volte e' proprio la cosa che questa funzione esiste per evitare.
    """
    comune = interseca(a, b)
    if comune is None:
        return [a]
    ax, ay, aw, ah = a
    cx, cy, cw, ch = comune
    fuori: list[Rettangolo] = []
    if cy > ay:  # sopra
        fuori.append((ax, ay, aw, cy - ay))
    if cy + ch < ay + ah:  # sotto
        fuori.append((ax, cy + ch, aw, ay + ah - (cy + ch)))
    mezzo_h = ch
    if cx > ax:  # sinistra, solo la fascia in mezzo
        fuori.append((ax, cy, cx - ax, mezzo_h))
    if cx + cw < ax + aw:  # destra
        fuori.append((cx + cw, cy, ax + aw - (cx + cw), mezzo_h))
    return [r for r in fuori if r[2] > 0 and r[3] > 0]


@dataclass(slots=True)
class Pezzo:
    """Un rettangolo da leggere davvero, e a quale area appartiene."""

    roi: Rettangolo
    area: int  # indice dell'area nell'elenco dichiarato
    modo: str


def dividi(aree: list[Area], minimo: float = 1e-4) -> list[Pezzo]:
    """Le aree ridotte a rettangoli che **non si sovrappongono**.

    Vince chi e' dichiarato prima: ogni area cede alle precedenti i pixel che ha
    in comune con loro. Il risultato copre la stessa superficie dell'unione delle
    aree, e ogni punto appartiene a un pezzo solo.

    `minimo` butta via le schegge: sottraendo due rettangoli quasi allineati
    restano strisce alte un millesimo di schermo, che non contengono testo e
    costerebbero comunque una passata di OCR.
    """
    pezzi: list[Pezzo] = []
    for i, area in enumerate(aree):
        resti = [area.roi]
        for prima in aree[:i]:
            nuovi: list[Rettangolo] = []
            for r in resti:
                nuovi.extend(sottrai(r, prima.roi))
            resti = nuovi
        for r in resti:
            if r[2] >= minimo and r[3] >= minimo:
                pezzi.append(Pezzo(roi=r, area=i, modo=area.modo))
    return pezzi


# **Quanto puo' essere alta un'area prima di smettere di funzionare.** Non e' una
# preferenza estetica come il consiglio sui 0,12 della ROI: e' il punto in cui la
# catena **smette di leggere**, e il numero viene da una misura.
#
# Il cancello che decide se vale la pena rileggere lo schermo (`RoiDiff`) guarda
# la **frazione** di pixel cambiati, contro `vision.diff_threshold = 0.004`.
# Quella frazione ha l'area al denominatore, quindi lo stesso sottotitolo diluito
# in un'area piu' grande la fa scendere. Misurato su una riga vera, facendo
# crescere l'area attorno:
#
# | altezza dell'area | variazione | il cancello si apre? |
# |---|---|---|
# | 0,08 | 0,0225 | si' |
# | 0,12 | 0,0153 | si' |
# | 0,30 | 0,0081 | si' |
# | 0,50 | 0,0056 | si' |
# | 0,70 | 0,0043 | si' (per un pelo) |
# | 1,00 | **0,0032** | **NO** |
#
# A schermo intero il cancello non si apre mai: misurato, 14 fotogrammi in, 14
# fermati, **zero chiamate all'OCR**. Il difetto e' muto — nessun contatore lo
# dice, perche' per la catena quei fotogrammi semplicemente non contenevano
# niente di nuovo.
#
# La soglia dell'avviso sta a 0,30 e non a 0,70: li' il margine sopra la soglia
# e' gia' sceso da 5,6 volte a 2, e su una scena che si muove il difetto si
# rovescia — il cancello si apre **sempre** e l'OCR gira sull'intero fotogramma,
# che e' il costo che `max_ocr_hz` esiste per limitare.
ALTEZZA_MASSIMA = 0.30


def troppo_grande(roi: Rettangolo) -> str:
    """Se l'area e' troppo alta per essere letta, dice perche'. Se no, `""`.

    Un'area grande non e' «meno precisa»: e' **muta**. Dirlo qui, come regola,
    vuol dire poterlo dire sia all'avvio della catena sia mentre si tira il
    rettangolo col mouse — e verificarlo senza aprire niente.
    """
    h = float(roi[3])
    if h <= ALTEZZA_MASSIMA:
        return ""
    return (
        f"! l'area e' alta {h:.2f} dello schermo: sopra {ALTEZZA_MASSIMA:.2f} la "
        f"catena legge poco o niente. Il cancello che decide se rileggere guarda "
        f"la **frazione** di schermo cambiata, e lo stesso sottotitolo diluito in "
        f"un'area grande non la supera piu' (misurato: a schermo intero, zero "
        f"letture). Tira l'area stretta attorno alla riga."
    )


def superficie(rettangoli: list[Rettangolo]) -> float:
    """Quanta superficie, in frazione di schermo. Usata per verificare."""
    return sum(w * h for _, _, w, h in rettangoli)


# **La tolleranza sulla sovrapposizione, e perche' non e' un modo di far passare
# la verifica.** Sottraendo rettangoli in virgola mobile due pezzi che condividono
# un bordo possono risultare sovrapposti di 2,4e-20 di schermo: `ay + (cy - ay)`
# non e' esattamente `cy`. Misurato, non temuto — l'ha trovato la prova su 200
# gruppi a caso.
#
# Il numero non e' scelto per far passare quel caso: e' scelto sull'unica cosa
# che conta, **un pixel**. Su un fotogramma 1920x1080 un pixel vale 4,8e-7 della
# superficie; 1e-9 e' cinquecento volte meno, quindi una sovrapposizione sotto
# questa soglia non puo' far leggere due volte nemmeno un pixel. Una vera — due
# aree tirate male dall'utente — vale milioni di volte tanto.
TOLLERANZA = 1e-9


def si_sovrappongono(rettangoli: list[Rettangolo], tolleranza: float = TOLLERANZA) -> bool:
    """Vero se due qualsiasi condividono piu' di `tolleranza` di superficie."""
    for i, a in enumerate(rettangoli):
        for b in rettangoli[i + 1 :]:
            comune = interseca(a, b)
            if comune is not None and comune[2] * comune[3] > tolleranza:
                return True
    return False


# ------------------------------------------------------- da e per la config --


def leggi(voci) -> list[Area]:
    """Le aree scritte in config, come `x:y:w:h:modo`.

    I due punti dentro e la virgola fra le aree, e non il contrario: `--set`
    separa gli elementi di una tupla con la virgola, quindi un'area che ne
    contenesse verrebbe letta come cinque aree monche.

    Un testo malformato **solleva**: un'area sbagliata vuol dire leggere il
    posto sbagliato dello schermo per tutta la sessione, e accorgersene
    riascoltando. Meglio non partire.
    """
    fuori: list[Area] = []
    for voce in voci or ():
        testo = str(voce).strip()
        if not testo:
            continue
        pezzi = [p.strip() for p in testo.split(":")]
        if len(pezzi) not in (4, 5):
            raise ValueError(
                f"area malformata: {testo!r} (serve `x:y:w:h` o `x:y:w:h:modo`)"
            )
        try:
            roi = tuple(float(p) for p in pezzi[:4])
        except ValueError as e:
            raise ValueError(f"area malformata: {testo!r} ({e})") from None
        modo = pezzi[4] if len(pezzi) == 5 else "testo_audio"
        fuori.append(Area(roi=roi, modo=modo, nome=testo))  # type: ignore[arg-type]
    return fuori


def da_leggere(cfg) -> tuple:
    """I rettangoli che la catena legge davvero: le aree se ci sono, se no la ROI.

    Sta qui perche' la regola «aree dichiarate oppure la ROI» era gia' scritta
    in `core/pipeline.py` e serviva anche alla cattura: due copie della stessa
    regola divergono al primo che ne cambia una, e qui divergere vorrebbe dire
    catturare una fascia che non contiene quello che si legge — cioe' nero.
    """
    aree = leggi(getattr(cfg.vision, "aree", ()) or ())
    if aree:
        return tuple(a.roi for a in aree)
    return (tuple(cfg.vision.roi),)


def scrivi(aree: list[Area]) -> tuple[str, ...]:
    """L'inverso di `leggi`, per riscrivere in config quello che la UI ha tirato."""
    return tuple(
        f"{a.roi[0]:.4f}:{a.roi[1]:.4f}:{a.roi[2]:.4f}:{a.roi[3]:.4f}:{a.modo}" for a in aree
    )


def da_config(vision) -> list[Area]:
    """Le aree in uso: quelle dichiarate, o `roi` sola se non ce ne sono.

    **Il ripiego e' la ragione per cui questo campo puo' restare vuoto di
    default**: un profilo che non sa niente delle aree continua a leggere la sua
    ROI, e nessun comportamento cambia finche' qualcuno non ne aggiunge una.
    """
    aree = leggi(getattr(vision, "aree", ()))
    return aree or [Area(roi=tuple(vision.roi), modo="testo_audio", nome="roi")]
