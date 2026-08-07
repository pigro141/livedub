"""Il secondo gioco: la catena puntata su un gioco che non e' GTA V.

**Perche' esiste questo file.** Il 7 agosto la catena e' stata puntata per
curiosita' su *Mafia: The Old Country* in italiano, e non leggeva niente: 109
ritagli mandati all'OCR, 109 vuoti. Ne sono usciti **due difetti distinti**, e
tutti e due erano ipotesi su GTA V travestite da codice generale. Uno e'
corretto (`vision.line_pad`), l'altro no. Senza queste verifiche il primo torna
alla prima modifica e del secondo non si accorge nessuno.

**Il materiale sono due schermate vere**, non un frame inventato:
`assets/gioco2/fondo_chiaro.png` (fondo marrone, interno) e
`fondo_scuro.png` (fondo nero, cinematica). Fondo chiaro e fondo scuro si
comportano **in modo diverso**, e un test che ne prova uno solo non copre
l'altro — e' gia' successo con la toppa precedente, che cadeva proprio sul nero.

**L'area di prova e' tutta la schermata, cioe' larga.** E' il punto e non un
dettaglio: con la ROI stretta di un profilo calibrato il primo difetto **non si
vede**, e un test sull'area stretta passerebbe per il motivo sbagliato. Il
programma va provato nelle condizioni in cui viene usato — un rettangolo
disegnato a mano dall'utente — non in quelle in cui funziona meglio.

**Qui l'OCR e' quello vero, e non e' una svista.** La suite si impone «nessun
modello» perche' un gruppo non deve *scaricare* niente al primo avvio; OneOCR
sta gia' in `models/oneocr` e lo si prende con `tools/fetch_oneocr.py`, quindi
non scarica nulla. E soprattutto: la domanda a cui questo gruppo risponde e'
«l'OCR legge questo ritaglio?». Con un OCR finto la risposta e' sempre si', ed
e' esattamente il modo in cui si archiviano conclusioni false con la suite
verde. Se il modello manca, il gruppo **lo dichiara fallendo**: una verifica
saltata in silenzio vale meno di zero, perche' sembra una conferma.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from core.config import VisionConfig
from core.metrics import MetricsRegistry
from vision.lines import classify_lines
from vision.ocr import make_ocr
from vision.reader import SubtitleReader

RADICE = Path(__file__).resolve().parent.parent
ASSETS = RADICE / "assets" / "gioco2"

# **Il margine dichiarato per il secondo gioco.** E' il numero che questo test
# difende: se qualcuno lo rimette a 0, sotto c'e' una verifica che diventa
# rossa. Misurato sui due screenshot — si veda `_prova_margine`.
PAD_DICHIARATO = 0.2

# Cosa c'e' scritto nelle due schermate. Senza accenti perche' il modello li
# perde ("gia", "Perche"): la verifica e' su cio' che l'OCR **restituisce**, non
# su cio' che il gioco ha disegnato.
ATTESO = {
    "fondo_chiaro": ("ENZO", "Guarda questo posto", "sepolto"),
    "fondo_scuro": ("ALFIO", "non gli mandi un pizzino",),
}


class _Orologio:
    """Orologio pilotato a mano: il lettore ha bisogno di un tempo che scorre."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t


def _carica(nome: str) -> np.ndarray | None:
    try:
        import cv2
    except ImportError:  # pragma: no cover - opencv assente
        return None
    img = cv2.imread(str(ASSETS / f"{nome}.png"))
    return img if img is not None and img.size else None


def _apri_ocr():
    """L'OCR vero, o `None` col motivo gia' stampato."""
    if not (RADICE / "models" / "oneocr" / "oneocr.onemodel").exists():
        return None
    try:
        return make_ocr("oneocr")
    except Exception:
        return None


def _cfg(**kw) -> VisionConfig:
    """La configurazione del secondo gioco: area larga, lessico spento.

    L'area e' **tutta** la schermata: gli screenshot sono gia' il rettangolo che
    l'utente aveva disegnato, e restringerlo qui vorrebbe dire provare qualcosa
    che nessuno usa. Il lessico e' spento perche' fa una domanda diversa (e' una
    parola italiana?) e coprirebbe la domanda di questo gruppo (l'OCR ha letto
    qualcosa?).
    """
    base = replace(
        VisionConfig(),
        roi=(0.0, 0.0, 1.0, 1.0),
        use_lexicon=False,
        max_ocr_hz=0.0,
    )
    return replace(base, **kw)


def _legge(reader: SubtitleReader, orologio: _Orologio, img: np.ndarray) -> list[str]:
    """Fa passare la schermata dal lettore e restituisce le battute aperte.

    Il primo frame e' nero apposta: il lettore legge quando la ROI **cambia**,
    e una schermata sola, immobile, non e' un cambiamento. Poi si ripete lo
    stesso frame perche' una battuta si apre dopo `stable_reads` letture
    d'accordo fra loro.
    """
    aperte: list[str] = []
    nero = np.zeros_like(img)
    for k in range(8):
        orologio.t = k * 0.033
        out = reader.process(nero if k == 0 else img)
        aperte += [b.text for b in (out.opened or [])]
    return aperte


def test_gioco2(c) -> None:
    c.group("gioco2")

    for nome in ATTESO:
        c.ok((ASSETS / f"{nome}.png").exists(), f"la schermata {nome} sta in assets/gioco2")

    chiaro, scuro = _carica("fondo_chiaro"), _carica("fondo_scuro")
    if chiaro is None or scuro is None:
        c.ok(False, "le due schermate del secondo gioco non si aprono (manca opencv?)")
        return

    _prova_colore(c, {"fondo_chiaro": chiaro, "fondo_scuro": scuro})

    ocr = _apri_ocr()
    if ocr is None:
        c.ok(
            False,
            "l'OCR vero non c'e': questo gruppo non puo' rispondere "
            "(`.\\.venv\\Scripts\\python.exe -m tools.fetch_oneocr`)",
        )
        return
    try:
        _prova_margine(c, {"fondo_chiaro": chiaro, "fondo_scuro": scuro}, ocr)
        _prova_contatori(c, {"fondo_chiaro": chiaro, "fondo_scuro": scuro}, ocr)
        _prova_catena(c, {"fondo_chiaro": chiaro, "fondo_scuro": scuro}, ocr)
        _prova_a_caldo(c, scuro, ocr)
    finally:
        chiudi = getattr(ocr, "close", None)
        if chiudi is not None:
            chiudi()


# ------------------------------------------------- il ritaglio senza margine --


def _prova_margine(c, schermate: dict[str, np.ndarray], ocr) -> None:
    """`line_pad`: il ritaglio che arriva all'OCR ha un margine, o non si legge.

    La banda finisce dove finisce l'inchiostro che la maschera ha trovato, e li'
    dentro non ci stanno gli accenti, le code di `g` e `p` e i bordi
    antialiasati. Su GTA V si legge lo stesso; qui **niente affatto**. Misurato
    sulle due schermate, banda alta 19-20 px:

    | `line_pad` | ritaglio | fondo chiaro | fondo scuro |
    |---|---|---|---|
    | 0,0 | 19-20 px | (vuoto) | (vuoto) |
    | 0,1 | 23-24 px | (vuoto) | (vuoto) |
    | **0,2** | 27-28 px | **letto, conf 1,00** | **letto, conf 1,00** |
    | 0,3 | 31-32 px | letto, conf 1,00 | letto, conf 1,00 |

    Le due righe a 0,0 sono la meta' che conta: dicono che il difetto e' ancora
    riproducibile. Se un giorno diventassero verdi anche a zero, il margine ha
    smesso di essere la spiegazione e va rimisurato — non festeggiato.

    Il colore qui e' fuori strada, quindi si guarda con `exclude_colored=False`: se no la
    riga non arriva mai all'OCR e questa tabella misurerebbe l'altro difetto.
    """
    for nome, img in schermate.items():
        for pad, deve_leggere in ((0.0, False), (PAD_DICHIARATO, True)):
            cfg = _cfg(line_pad=pad, exclude_colored=False)
            bande = classify_lines(img, cfg)
            if not c.ok(len(bande) == 1, f"{nome}: una sola banda di testo (pad {pad})"):
                continue
            banda = bande[0]
            testo, conf = ocr.read(banda.crop)
            atteso_h = banda.height + 2 * int(round(pad * banda.height))
            c.eq(banda.crop.shape[0], atteso_h, f"{nome}: il ritaglio ha il margine chiesto (pad {pad})")
            if deve_leggere:
                c.ok(bool(testo), f"{nome}: col margine {pad} l'OCR legge qualcosa")
                for parola in ATTESO[nome]:
                    c.ok(parola in testo, f"{nome}: col margine l'OCR legge {parola!r} (letto {testo!r})")
                c.ok(conf >= 0.9, f"{nome}: confidenza alta col margine (ottenuta {conf:.2f})")
            else:
                c.eq(testo, "", f"{nome}: senza margine l'OCR torna vuoto — il difetto e' ancora li'")

    c.ok(
        PAD_DICHIARATO >= 0.2,
        "il margine dichiarato per il secondo gioco non e' tornato a zero",
    )


# --------------------------------------------------- il nome colorato, e il prezzo --


def _prova_colore(c, schermate: dict[str, np.ndarray]) -> None:
    """Il criterio della parola colorata scarta il **nome di chi parla**.

    Questo gioco scrive `ENZO:` e `ALFIO:` in giallo per progetto, davanti a
    ogni battuta. Il criterio della parola colorata — scritto per togliere l'HUD
    di GTA V — vede una parola satura larga come una parola e scarta la riga
    **prima di pagare l'OCR**. Non e' una lettura sbagliata: e' una riga che
    all'OCR non arriva.

    **Lo scambio e' qui, ed e' diventato un interruttore dell'utente**
    (`vision.exclude_colored`, nella UI «Ignora i sottotitoli colorati»): i due
    giochi lo vogliono al contrario e nessuna soglia li concilia, quindi la
    scelta e' di chi il gioco lo sta guardando. Le verifiche sotto tengono
    visibile il prezzo delle due posizioni invece di nasconderlo dietro un
    numero scelto bene. Il giorno in cui esistera' un criterio che sa dire «il
    colore e' del nome, non di scenario», l'interruttore potra' avere un terzo
    valore invece di due.
    """
    for nome, img in schermate.items():
        bande = classify_lines(img, _cfg())
        if not c.ok(len(bande) == 1, f"{nome}: una sola banda di testo, col colore acceso"):
            continue
        banda = bande[0]
        c.ok(banda.color_word, f"{nome}: il nome giallo fa scattare il criterio della parola colorata")
        c.ok(
            not banda.cls.is_dialogue,
            f"{nome}: con le difese di GTA V la riga non e' dialogo — il gioco non si legge affatto",
        )

        aperto = classify_lines(img, _cfg(exclude_colored=False))
        c.ok(len(aperto) == 1 and aperto[0].cls.is_dialogue,
             f"{nome}: con exclude_colored=False la stessa riga torna dialogo")
        c.ok(not aperto[0].color_word,
             f"{nome}: con exclude_colored=False il criterio della parola colorata non scatta piu'")

    _prezzo_dell_interruttore(c)


def _prezzo_dell_interruttore(c) -> None:
    """E quanto costa `exclude_colored=False`: cade la difesa dall'HUD di GTA V.

    Misurato dal vivo su GTA V, la difesa serve — sono frammenti di HUD colorata
    **incollati** a una battuta vera e pronunciati: `'Rec.Lavoriamo insieme...'`,
    `"Si, era lui.Adam'a App"`. Qui la stessa cosa su un frame di cui si conosce
    gia' la risposta: una riga di suggerimento gialla, che di default viene
    scartata e con `exclude_colored=False` passa per dialogo.
    """
    from tools.frames import YELLOW, font_available, render_subtitles

    if not font_available():  # pragma: no cover - macchina senza font
        c.ok(False, "niente font di sistema: il prezzo di exclude_colored=False non si puo' mostrare")
        return

    hud = render_subtitles([("Raggiungi il molo", YELLOW)], size=(90, 700), font_px=34)
    difeso = classify_lines(hud, _cfg())
    c.ok(
        bool(difeso) and not difeso[0].cls.is_dialogue,
        "GTA V: con le difese accese una riga di HUD gialla viene scartata",
    )
    scoperto = classify_lines(hud, _cfg(exclude_colored=False))
    c.ok(
        bool(scoperto) and scoperto[0].cls.is_dialogue,
        "GTA V: con exclude_colored=False la stessa riga di HUD passa per dialogo — e' il prezzo",
    )
    _interruttore(c, hud)


def _interruttore(c, hud: np.ndarray) -> None:
    """L'interruttore fa **esattamente** quello che si faceva a mano, e niente
    di piu'.

    Prima di avere un nome suo, spegnere il colore si faceva con `sat_max=255`,
    ed e' cosi' che sono state prese tutte le misure archiviate: GTA V 1349
    righe scartate -> 0 e fuori lessico 8,0% -> 9,4%, Mafia 0 battute su 18 ->
    12. Se l'interruttore non fosse la stessa cosa, quelle misure smetterebbero
    di parlare di lui — e sarebbe la settima volta che in questo progetto un
    numero misurato su una quantita' viene applicato a un'altra.

    Quindi la verifica non e' «l'interruttore funziona», e' **«da' lo stesso
    risultato della strada da cui vengono i numeri»**, banda per banda.
    """
    a = classify_lines(hud, _cfg(exclude_colored=False))
    b = classify_lines(hud, _cfg(sat_max=255))
    c.eq(len(a), len(b), "l'interruttore trova le stesse bande di sat_max=255")
    for x, y in zip(a, b):
        c.eq((x.cls, x.color_word, round(x.sat_share, 6)),
             (y.cls, y.color_word, round(y.sat_share, 6)),
             "l'interruttore classifica come sat_max=255")
        c.ok(np.array_equal(x.crop, y.crop), "l'interruttore da' all'OCR lo stesso ritaglio")

    # E acceso non cambia niente rispetto a prima che esistesse: il default e'
    # il comportamento di sempre, non una versione nuova con lo stesso nome.
    d = classify_lines(hud, _cfg())
    c.ok(bool(d) and not d[0].cls.is_dialogue, "acceso, l'interruttore e' il comportamento di sempre")


# ------------------------------------------ la forma del difetto, sui contatori --


def _prova_contatori(c, schermate: dict[str, np.ndarray], ocr) -> None:
    """`vision.ocr.lines > 0` con `vision.ocr.empty` uguale: 109 su 109.

    E' la forma esatta in cui il difetto si e' presentato, e nessun contatore lo
    **dichiarava**: la catena girava «bene», mandava ritagli all'OCR, e ne
    riceveva indietro zero testo. Da qui in giu' non c'e' niente da vedere, e a
    monte tutto sembra a posto.

    I due numeri ci sono gia' e bastano, purche' si guardino **insieme**: `lines`
    da solo dice che si sta lavorando, `empty` da solo non dice su quanto. La
    verifica e' che la loro uguaglianza sia **riproducibile senza margine** e
    **impossibile con**.
    """
    for nome, img in schermate.items():
        rotto = _conta(schermate[nome], _cfg(line_pad=0.0, exclude_colored=False), ocr)
        c.ok(rotto["vision.ocr.lines"] > 0, f"{nome}: senza margine i ritagli all'OCR ci sono")
        c.eq(
            rotto.get("vision.ocr.empty", 0),
            rotto["vision.ocr.lines"],
            f"{nome}: senza margine sono vuoti **tutti** — la forma del difetto",
        )

        sano = _conta(img, _cfg(line_pad=PAD_DICHIARATO, exclude_colored=False), ocr)
        c.ok(sano["vision.ocr.lines"] > 0, f"{nome}: col margine i ritagli all'OCR ci sono")
        c.ok(
            sano.get("vision.ocr.empty", 0) < sano["vision.ocr.lines"],
            f"{nome}: col margine non sono vuoti tutti "
            f"({sano.get('vision.ocr.empty', 0)} su {sano['vision.ocr.lines']})",
        )


def _conta(img: np.ndarray, cfg: VisionConfig, ocr) -> dict[str, int]:
    m = MetricsRegistry()
    orologio = _Orologio()
    lettore = SubtitleReader(cfg, ocr, metrics=m, clock=orologio)
    _legge(lettore, orologio, img)
    return m.snapshot()["counters"]


# ------------------------------------------------------- la catena, in fondo --


def _prova_catena(c, schermate: dict[str, np.ndarray], ocr) -> None:
    """E la domanda che conta: il secondo gioco produce una battuta, si' o no?

    Le verifiche sopra isolano i due difetti uno per volta. Questa li mette
    insieme, ed e' l'unica che l'utente riconoscerebbe: quattro combinazioni,
    **una sola** apre una battuta. Servono tutti e due i rimedi, e ognuno da
    solo non basta — che e' il motivo per cui correggerne uno e provare non
    aveva mostrato nessun progresso.

    | `line_pad` | «Ignora i sottotitoli colorati» | battute aperte |
    |---|---|---|
    | 0,0 | acceso (default, difese GTA V) | nessuna |
    | 0,2 | acceso | nessuna |
    | 0,0 | spento | nessuna |
    | **0,2** | **spento** | **la battuta, per intero** |
    """
    for nome, img in schermate.items():
        for pad, difesa, deve in (
            (0.0, True, False),
            (PAD_DICHIARATO, True, False),
            (0.0, False, False),
            (PAD_DICHIARATO, False, True),
        ):
            orologio = _Orologio()
            lettore = SubtitleReader(
                _cfg(line_pad=pad, exclude_colored=difesa), ocr, metrics=MetricsRegistry(), clock=orologio
            )
            aperte = _legge(lettore, orologio, img)
            if deve:
                if c.ok(len(aperte) == 1, f"{nome}: pad {pad} + difesa {difesa} apre una battuta"):
                    for parola in ATTESO[nome]:
                        c.ok(
                            parola in aperte[0],
                            f"{nome}: la battuta dice {parola!r} (aperta {aperte[0]!r})",
                        )
            else:
                c.eq(aperte, [], f"{nome}: pad {pad} + difesa {difesa} non apre niente")


# ---------------------------------------------------- l'interruttore, a caldo --


def _prova_a_caldo(c, img: np.ndarray, ocr) -> None:
    """La casella si puo' spuntare **a sessione accesa**, e si sente subito.

    La UI la espone come «Ignora i sottotitoli colorati» e scrive nello stesso
    oggetto config che il lettore rilegge a ogni fotogramma. Detta cosi' e' una
    supposizione: qui e' un lettore **gia' costruito** che prima non apre
    niente, e che dopo aver girato l'interruttore apre la battuta — senza
    ricostruire nulla.

    Questo progetto ha gia' pagato per campi dichiarati e non letti
    (`max_ocr_hz`, `tts.device`, `background_mode`, `overlay.ritardo`): un
    interruttore che la UI mostra e che la catena non guarda darebbe una
    sessione diversa da quella che si crede di stare guardando, ed e' il difetto
    peggiore per uno strumento di misura.
    """
    cfg = _cfg(line_pad=PAD_DICHIARATO)  # difesa accesa: com'e' di default
    orologio = _Orologio()
    lettore = SubtitleReader(cfg, ocr, metrics=MetricsRegistry(), clock=orologio)

    c.eq(_legge(lettore, orologio, img), [], "a difesa accesa il lettore non apre niente")

    cfg.exclude_colored = False  # la spunta tolta dall'utente, a sessione accesa
    aperte = _legge(lettore, orologio, img)
    if c.ok(len(aperte) == 1, "tolta la spunta, lo **stesso** lettore apre la battuta"):
        c.ok("ALFIO" in aperte[0], f"e la battuta e' quella giusta ({aperte[0]!r})")

    cfg.exclude_colored = True  # rimessa: si torna indietro senza riavviare
    lettore.diff = SubtitleReader(cfg, ocr, metrics=MetricsRegistry(), clock=orologio).diff
    lettore.tracker.close_all(orologio.t)
    c.eq(_legge(lettore, orologio, img), [], "rimessa la spunta, si torna al comportamento di prima")
