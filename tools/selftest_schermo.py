"""Verifiche dell'area grande: piu' scritte, ognuna nel suo riquadro.

`CLAUDE.md` dichiara che tradurre tutto lo schermo «e' un altro prodotto», e le
ragioni erano tre misure. Queste verifiche stanno **su quelle tre**, e non su una
lista di casi:

1. **il cancello non si diluisce** — la stessa scritta dentro un'area che cresce
   deve dare lo stesso numero, se no a schermo intero non si legge affatto;
2. **due scritte sono due scritte** — affiancate alla stessa altezza, il profilo
   per righe le fonde in una sola, ed e' il difetto che `vision/blocchi.py`
   esiste per togliere;
3. **il riquadro comanda e il carattere cede**, con un pavimento dichiarato.

Piu' la quarta, che non era una misura ma un difetto trovato scrivendole: **la
marca sopravvive a `replace`**. La pipeline teneva «questa battuta e' muta» in
una mappa indicizzata per `id()` dell'evento, e un `SubtitleEvent` e' congelato:
ogni correzione del testo ne crea uno nuovo che in quella mappa non c'e'. La
verifica che c'era guardava la mappa — cioe' il deposito invece della proprieta'
— e per questo non poteva accorgersene.

**E la quinta e' la piu' importante di tutte**: a modalita' spenta la catena a
una riga dev'essere identica. Qui si prende il pezzo che si puo' provare senza
hardware (il lettore non cambia niente del suo comportamento); il resto e' un
confronto di due passate di `tools/dub.py`, che una suite non puo' fare.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from tools.frames import empty_frame, font_available, render_subtitles


def _cfg():
    from core.config import Config

    cfg = Config()
    cfg.vision.use_lexicon = False
    return cfg


def _diff(cfg, cella: int):
    from vision.diff import RoiDiff

    return RoiDiff(
        threshold=cfg.vision.diff_threshold,
        stride=cfg.vision.diff_stride,
        ink_min_luma=cfg.vision.grey_min_luma,
        contrast_min=cfg.vision.contrast_min if cfg.vision.use_local_contrast else 0.0,
        contrast_kernel=cfg.vision.contrast_kernel,
        ink_min_columns=cfg.vision.ink_min_columns,
        vanish_frames=cfg.vision.vanish_frames,
        cella=cella,
        cell_threshold=cfg.vision.diff_cella_soglia,
    )


def test_cancello_celle(c) -> None:
    """Il cancello del diff non deve diluirsi con l'area.

    **La prova e' un rapporto, non un valore.** «A schermo intero apre» sarebbe
    verde anche con un cancello sempre aperto, che e' il difetto opposto e
    peggiore — l'OCR girerebbe sul fotogramma intero a ogni giro. Si guardano
    quindi tre cose insieme: apre quando la scritta compare, **non** apre quando
    non cambia niente, e il numero **non cambia** al crescere dell'area.
    """
    c.group("cancello_celle")
    if not font_available():  # pragma: no cover - macchina senza font
        c.ok(False, "niente font di sistema: la prova sul cancello non si puo' fare")
        return
    cfg = _cfg()

    vuoto = empty_frame((1080, 1920), background=40)
    scritto = vuoto.copy()
    scritto[900:960, 500:1400] = render_subtitles(
        [("Rimuovi il veicolo dalla strada", (255, 255, 255))], size=(60, 900), font_px=34
    )

    from vision.roi import crop

    # **Si verifica la legge, non il valore.** Su un fotogramma sintetico il
    # sottotitolo copre il 100% dei pixel della sua banda, mentre su una scena
    # vera ne cambia meno di un decimo: i numeri assoluti qui sono dieci volte
    # quelli veri e una soglia messa su di loro non direbbe niente di questo
    # programma. Quello che invece e' identico nei due casi — perche' e'
    # aritmetica e non fotografia — e' **come scalano**: la media ha l'area al
    # denominatore, la cella no.
    #
    # I numeri veri stanno in `tools/bench_schermo.py --fermo`, su nove coppie
    # «schermo fermo, la scritta cambia» prese dalla registrazione: la media
    # passa da 0,0165 a 0,0047 (soglia 0,004, cioe' arriva a sfiorarla), la
    # cella peggiore da 0,0966 a 0,0977 (soglia 0,025) — ferma.
    aree = [
        ("stretta", (0.0, 0.82, 1.0, 0.08)),
        ("meta'", (0.0, 0.40, 1.0, 0.55)),
        ("intera", (0.0, 0.0, 1.0, 1.0)),
    ]
    medie, celle = [], []
    for nome, roi in aree:
        for cella, dove in ((0, medie), (32, celle)):
            d = _diff(cfg, cella)
            d.update(crop(vuoto, roi))
            dove.append((nome, d.update(crop(scritto, roi)).ratio))

    # 1. La media si dilata **come l'area**, che e' il difetto: da 0,08 a 1,00
    #    l'area cresce 12,5 volte e il numero deve scendere di altrettanto.
    caduta = medie[0][1] / max(1e-9, medie[2][1])
    c.ok(
        8.0 <= caduta <= 18.0,
        f"la media si dilata come l'area: {medie[0][1]:.4f} -> {medie[2][1]:.4f}, "
        f"cioe' {caduta:.1f} volte per un'area 12,5 volte piu' grande",
    )

    # 2. La cella peggiore no: resta dello stesso ordine a ogni altezza. Non
    #    identica — la griglia cade in posti diversi e la cella migliore
    #    inquadra una porzione diversa di scritta — ma senza **nessuna**
    #    tendenza a scendere con l'area, che e' l'unica cosa che conta.
    valori = [v for _, v in celle]
    c.ok(
        max(valori) <= 3.0 * min(valori),
        f"la cella peggiore non dipende dall'area: {['%.3f' % v for v in valori]}",
    )
    c.ok(
        valori[2] > 0.5 * valori[0],
        f"e passando dalla fascia allo schermo intero non crolla "
        f"({valori[0]:.3f} -> {valori[2]:.3f}), che e' quello che fa la media",
    )
    for nome, v in celle:
        c.ok(v > cfg.vision.diff_cella_soglia,
             f"e apre con l'area {nome} ({v:.3f} > {cfg.vision.diff_cella_soglia})")

    # 3. Il caso nullo: se non cambia niente non deve aprirsi. Senza questa, un
    #    cancello inchiodato su «aperto» passerebbe tutte le righe di sopra.
    for cella in (0, 32):
        d = _diff(cfg, cella)
        d.update(crop(scritto, (0.0, 0.0, 1.0, 1.0)))
        aperti = sum(
            1 for _ in range(5) if d.update(crop(scritto, (0.0, 0.0, 1.0, 1.0))).changed
        )
        c.eq(aperti, 0, f"e con lo schermo fermo non si apre mai (celle={cella})")

    # 4. Spento vuol dire **identico a prima**, non «quasi».
    a, b = _diff(cfg, 0), _diff(cfg, 0)
    a.update(crop(vuoto, (0.0, 0.7, 1.0, 0.2)))
    b.update(crop(vuoto, (0.0, 0.7, 1.0, 0.2)))
    c.eq(
        a.update(crop(scritto, (0.0, 0.7, 1.0, 0.2))).ratio,
        b.update(crop(scritto, (0.0, 0.7, 1.0, 0.2))).ratio,
        "a celle spente il numero e' quello di sempre",
    )
    c.eq(_diff(cfg, 0).soglia, cfg.vision.diff_threshold, "e la soglia pure")
    c.eq(_diff(cfg, 32).soglia, cfg.vision.diff_cella_soglia,
         "accese, la soglia e' l'altra: due distribuzioni, due numeri")


def test_blocchi(c) -> None:
    """Trovare le scritte dove sono, e **quante sono**.

    La prova che conta e' quella orizzontale: due scritte affiancate alla stessa
    altezza. `find_bands` lavora sul profilo delle righe-pixel, quindi per lui
    sono una banda sola — e `line_gap_split` di quella banda ne terrebbe **un
    pezzo solo**, quello piu' vicino al centro. Cioe' senza questo modulo la
    seconda scritta non e' «letta male»: non esiste.
    """
    c.group("blocchi")
    if not font_available():  # pragma: no cover
        c.ok(False, "niente font di sistema: la prova sui blocchi non si puo' fare")
        return
    from vision.blocchi import allarga, trova

    cfg = _cfg()
    riga = 0.030 * 1080  # 32 px

    # Tre scritte in tre posti: due affiancate in alto, una in basso.
    frame = empty_frame((1080, 1920), background=30)
    frame[60:120, 120:620] = render_subtitles(
        [("Vespucci Beach", (255, 255, 255))], size=(60, 500), font_px=34)
    frame[60:120, 1300:1800] = render_subtitles(
        [("Munizioni 24", (255, 255, 255))], size=(60, 500), font_px=34)
    frame[940:1000, 600:1400] = render_subtitles(
        [("Rimuovi il veicolo", (255, 255, 255))], size=(60, 800), font_px=34)

    blocchi, scartati = trova(frame, cfg.vision, riga)
    c.eq(scartati, 0, "sotto il tetto non si scarta niente")
    c.eq(len(blocchi), 3, f"tre scritte, tre blocchi (trovati {len(blocchi)})")

    # **E ciascuno sta dove sta la sua scritta.** Contarli non basta: tre
    # rettangoli nel posto sbagliato farebbero verde la riga di sopra, ed e'
    # esattamente lo sbaglio che le misure di *quanto* non possono esprimere.
    veri = [(120, 60, 620, 120), (1300, 60, 1800, 120), (600, 940, 1400, 1000)]
    for x0, y0, x1, y1 in veri:
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        dentro = [b for b in blocchi if b.x0 <= cx <= b.x1 and b.y0 <= cy <= b.y1]
        c.eq(len(dentro), 1, f"un blocco solo contiene il centro di ({x0},{y0})")
        if dentro:
            b = dentro[0]
            c.ok(
                b.x1 - b.x0 < 0.55 * frame.shape[1],
                f"e non si e' saldato all'altra scritta (largo {b.x1 - b.x0} px "
                f"su {frame.shape[1]})",
            )

    # -- e la prova che dice perche' il modulo esiste -------------------------
    #
    # Le stesse due scritte affiancate, date a `classify_lines` come le riceve
    # oggi la catena: una banda sola, e di quella un pezzo solo.
    from vision.lines import classify_lines

    fascia = frame[40:140]
    bande = classify_lines(fascia, cfg.vision)
    c.ok(
        len(bande) == 1,
        f"il profilo per righe ne vede una sola banda ({len(bande)}): e' il difetto",
    )
    if bande:
        b = bande[0]
        c.ok(
            (b.x1 - b.x0) < 0.5 * frame.shape[1],
            "e di quella banda tiene un blocco solo: la seconda scritta sparisce",
        )

    # -- il margine attorno: serve a `classify_lines`, che senza non legge -----
    g = allarga(blocchi[0], riga, frame.shape)
    c.ok(g.x0 < blocchi[0].x0 and g.y0 < blocchi[0].y0, "il blocco allargato ha respiro")
    c.ok(g.x0 >= 0 and g.y0 >= 0 and g.x1 <= frame.shape[1] and g.y1 <= frame.shape[0],
         "e non esce dall'immagine")

    # -- il tetto e' un budget dell'OCR, e si dichiara ------------------------
    pochi, buttati = trova(frame, cfg.vision, riga, massimo=2)
    c.eq(len(pochi), 2, "col tetto a due se ne tengono due")
    c.eq(buttati, 1, "e il terzo viene **dichiarato**, non perso in silenzio")

    # -- uno schermo vuoto non inventa scritte --------------------------------
    vuoti, _ = trova(empty_frame((1080, 1920), background=30), cfg.vision, riga)
    c.eq(len(vuoti), 0, "e su uno schermo vuoto non se ne trova nessuna")


def test_stringi(c) -> None:
    """Il riquadro comanda, il carattere cede, e il pavimento e' dichiarato.

    Sono tre affermazioni diverse e servono tre prove: che la traduzione lunga
    **stia dentro**, che per starci il corpo sia **sceso**, e che sotto il
    pavimento non scenda piu' — dichiarandolo invece di consegnare una scritta
    illeggibile.
    """
    c.group("stringi_riquadro")
    if not font_available():  # pragma: no cover
        c.ok(False, "niente font di sistema: la prova sul riquadro non si puo' fare")
        return
    from ui.overlay import Sostituzione

    pezzo = np.full((300, 1200, 3), 40, dtype=np.uint8)
    # Un riquadro di riferimento: una riga alta 40 px e larga 400.
    bande = [(100, 120, 500, 160)]
    corto, lungo = "Esci", "Esci immediatamente dal veicolo e allontanati"

    base = Sostituzione(pezzo, bande, corto, corpo=30, testo_originale=corto)
    stretta = Sostituzione(pezzo, bande, lungo, corpo=30, testo_originale=corto,
                           stringi=True, corpo_min=11)
    larga = Sostituzione(pezzo, bande, lungo, corpo=30, testo_originale=corto)

    c.eq(base.corpo, 30, "col testo corto il corpo resta quello del gioco")
    c.ok(stretta.corpo < 30, f"col testo lungo il corpo scende (a {stretta.corpo})")
    c.ok(
        stretta.larg <= larga.larg,
        f"e il riquadro non cresce piu' di quanto crescerebbe senza "
        f"({stretta.larg} <= {larga.larg})",
    )
    # **La prova vera e' geometrica**: il testo disegnato sta dentro l'originale?
    largo_orig, alto_orig = 400, 40
    from PIL import Image, ImageDraw

    from ui.overlay import carica_font

    m = ImageDraw.Draw(Image.new("L", (1, 1)))
    f = carica_font("Arial", stretta.corpo)
    largo = max(m.textlength(r, font=f) for r in stretta.righe)
    c.ok(largo <= 1.05 * largo_orig,
         f"il tradotto sta nella larghezza dell'originale ({largo:.0f} <= {largo_orig})")
    c.ok(stretta.passo * len(stretta.righe) <= 1.05 * alto_orig,
         f"e nella sua altezza ({stretta.passo * len(stretta.righe)} <= {alto_orig})")
    c.ok(not stretta.stretto, "e non ha avuto bisogno del pavimento")

    # -- il pavimento: sotto non si scende, e lo si dice ----------------------
    impossibile = " ".join(["parola"] * 40)
    giu = Sostituzione(pezzo, bande, impossibile, corpo=30, testo_originale=corto,
                       stringi=True, corpo_min=11)
    c.eq(giu.corpo, 11, "sotto il pavimento non si stringe piu'")
    c.ok(giu.stretto, "e si **dichiara** che non ci sta: illeggibile e' peggio di sforare")

    # -- e spento non cambia niente, che e' la meta' che conta ----------------
    normale = Sostituzione(pezzo, bande, lungo, corpo=30, testo_originale=corto)
    c.ok(not normale.stringi, "di suo il riquadro non comanda: la catena di sempre")
    c.ok(not normale.stretto, "e non c'e' nessun pavimento da dichiarare")
    c.eq(normale.corpo, larga.corpo, "e il corpo e' quello che era prima")


def test_marca(c) -> None:
    """La marca deve sopravvivere a `replace`, se no la battuta muta parla.

    E' il difetto trovato scrivendo queste verifiche, non uno inventato per
    averne una: la pipeline teneva «questa e' muta» in `dict[id(evento)]`, e
    ogni miglioramento del testo costruisce un evento **nuovo**. Il sintomo
    sarebbe stato una battuta di HUD pronunciata a voce ogni volta che l'OCR
    leggeva meglio la seconda volta — cioe' quasi sempre — e nessun contatore lo
    diceva.
    """
    c.group("marca")
    from core.pipeline import area_di, parla
    from core.types import LineClass, SubtitleEvent
    from vision.aree import Marca

    zitta = SubtitleEvent(text="Munizioni 24", cls=LineClass.WHITE, t_on=1.0,
                          marca=Marca(roi=(0.1, 0.0, 0.3, 0.1), modo="testo"))
    parlante = SubtitleEvent(text="Andiamo", cls=LineClass.WHITE, t_on=1.0)

    c.ok(not parla(zitta), "una battuta di un'area muta non parla")
    c.ok(parla(parlante), "e una senza marca parla: e' la ROI di sempre")
    c.eq(area_di(zitta), (0.1, 0.0, 0.3, 0.1), "e porta con se' il suo rettangolo")
    c.eq(area_di(parlante), (), "senza marca il rettangolo e' la ROI")

    # **La prova che la mappa per `id()` non poteva dare.** Ogni `replace`
    # costruisce un oggetto nuovo: la proprieta' deve viaggiare con lui.
    migliorata = replace(zitta, text="Munizioni 240")
    c.ok(migliorata is not zitta, "il testo che migliora crea un evento nuovo")
    c.ok(not parla(migliorata), "e la battuta muta resta muta anche dopo `replace`")
    c.eq(area_di(migliorata), area_di(zitta), "e tiene il suo rettangolo")
    c.ok(not parla(migliorata.closed(4.0)), "e anche dopo essere stata chiusa")

    # -- e passa dal tracker, che l'evento lo **ricostruisce** ----------------
    from core.config import Config
    from core.types import OcrLine, merge_lines
    from vision.subtitles import SubtitleTracker

    cfg = Config()
    cfg.vision.stable_reads = 1
    tracker = SubtitleTracker(cfg.vision)
    riga = OcrLine(text="Munizioni 24", cls=LineClass.WHITE, bbox=(0, 0, 100, 20))
    marca = Marca(roi=(0.1, 0.0, 0.3, 0.1), modo="schermo")
    fuori = tracker.feed(merge_lines([riga], t_on=0.0, marca=marca), 0.0)
    c.eq(len(fuori.opened), 1, "il tracker apre la battuta")
    c.ok(not parla(fuori.opened[0]),
         "e l'evento che ne esce e' ancora muto: la marca attraversa la conferma")


def test_schermo_catena(c) -> None:
    """La modalita' accesa non parla, e spenta non cambia niente."""
    c.group("schermo_catena")
    from core.clock import VirtualClock
    from core.config import Config
    from core.pipeline import DubPipeline
    from speak.base import make_tts
    from vision.aree import Area, troppo_grande

    def tono():
        return make_tts(type("T", (), {"backend": "tone", "samplerate": 22050})())

    # -- l'avviso sull'area grande non deve scattare qui ----------------------
    c.ok(troppo_grande((0.0, 0.0, 1.0, 1.0)),
         "un'area alta tutto lo schermo, in modo normale, viene ancora dichiarata muta")
    c.eq(troppo_grande((0.0, 0.0, 1.0, 1.0), "schermo"), "",
         "ma in modo `schermo` no: li' il cancello e' stato rifatto apposta")
    c.ok(not Area((0.0, 0.0, 1.0, 1.0), modo="schermo").parla,
         "e un'area `schermo` non parla mai")
    c.ok(Area((0.0, 0.0, 1.0, 1.0), modo="schermo").molte,
         "da lei escono piu' scritte insieme")

    # -- accesa: un lettore in modalita' molte, col cancello a celle ----------
    cfg = Config()
    cfg.tts.backend, cfg.speaker.backend, cfg.vad.backend = "tone", "none", "energy"
    cfg.vision.aree = ("0.0:0.0:1.0:1.0:schermo",)
    acceso = DubPipeline(cfg, tono(), clock=VirtualClock(), samplerate=48000)
    lettore = acceso.lettori[0][0]
    c.ok(lettore.molte, "il lettore dell'area `schermo` legge piu' scritte")
    c.eq(lettore.diff.cella, 32,
         "e il suo cancello e' a celle: a 0 non leggerebbe **niente**")
    c.eq(lettore.marca.modo, "schermo", "e timbra le sue battute")

    # -- spenta: tutto com'era, e questa e' la riga che conta -----------------
    base = Config()
    base.tts.backend, base.speaker.backend, base.vad.backend = "tone", "none", "energy"
    spento = DubPipeline(base, tono(), clock=VirtualClock(), samplerate=48000)
    normale = spento.lettori[0][0]
    c.ok(not normale.molte, "senza aree il lettore e' quello di sempre")
    c.eq(normale.diff.cella, 0, "col cancello di sempre")
    c.eq(normale.diff.soglia, base.vision.diff_threshold, "e la soglia di sempre")
    c.eq(normale.marca.modo, "testo_audio", "e la sua battuta parla")
    c.eq(tuple(normale.roi), tuple(base.vision.roi), "e guarda la ROI")
