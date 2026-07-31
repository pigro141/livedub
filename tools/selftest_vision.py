"""Verifiche del dominio video: ROI, classificatore di righe, diff, tracker.

Sta in un file suo perche' e' il gruppo piu' grosso della suite, e perche' e'
l'unico che renderizza testo vero: la grammatica dei colori si verifica su frame
di cui si conosce gia' la risposta, non sui frame di gioco dove la risposta e'
quella che si sta cercando.
"""

from __future__ import annotations

import numpy as np

from core.config import VisionConfig
from core.types import LineClass, SubtitleEvent
from tools.frames import GREEN, GREY, WHITE, YELLOW, empty_frame, frame_with_roi, render_subtitles
from vision.diff import Change, RoiDiff
from vision.lines import classify_lines, find_bands, luma_sat, text_mask
from vision.ocr import EchoOcr, NullOcr, make_ocr, prepare
from vision.reader import SubtitleReader
from vision.roi import crop, roi_pixels
from vision.subtitles import SubtitleTracker, normalize, similarity, wrong_chars

ROI = (0.15, 0.72, 0.70, 0.22)


class _FixedClock:
    """Orologio pilotato a mano dai test: `orologio.t = 3.0`."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def now(self) -> float:
        return self.t


def test_roi(c) -> None:
    c.group("roi")

    c.eq(roi_pixels((100, 200), (0.0, 0.0, 1.0, 1.0)), (0, 0, 200, 100), "ROI piena")
    c.eq(roi_pixels((100, 200), (0.5, 0.5, 0.5, 0.5)), (100, 50, 100, 50), "ROI a meta'")
    c.eq(
        roi_pixels((100, 200), (0.9, 0.9, 0.5, 0.5)),
        (180, 90, 20, 10),
        "una ROI che sborda viene riportata dentro il frame",
    )
    c.raises(ValueError, lambda: roi_pixels((100, 200), (0.1, 0.1, 0.0, 0.5)), "ROI di area nulla")

    frame = np.zeros((100, 200, 3), np.uint8)
    frame[50:75, 100:200] = 255
    got = crop(frame, (0.5, 0.5, 0.5, 0.5))
    c.eq(got.shape, (50, 100, 3), "crop restituisce la forma attesa")
    c.ok(bool((got[:25] == 255).all()), "crop ritaglia nel punto giusto")


def test_lines(c) -> None:
    c.group("lines")
    cfg = VisionConfig()

    # L'ordine dei canali non deve poter cambiare il risultato: luminanza e
    # saturazione sono simmetriche, e la cattura Windows produce BGRA.
    rgb = np.array([[[10, 200, 90]]], np.uint8)
    bgr = rgb[:, :, ::-1].copy()
    lr, sr = luma_sat(rgb)
    lb, sb = luma_sat(bgr)
    c.close(float(lr[0, 0]), float(lb[0, 0]), "la luminanza non dipende dall'ordine dei canali")
    c.close(float(sr[0, 0]), float(sb[0, 0]), "la saturazione non dipende dall'ordine dei canali")
    c.close(float(sr[0, 0]), 190.0, "la saturazione e' max meno min")

    bgra = np.dstack([rgb, np.full((1, 1, 1), 255, np.uint8)])
    c.close(float(luma_sat(bgra)[0][0, 0]), float(lr[0, 0]), "il canale alfa viene ignorato")
    c.close(float(luma_sat(np.array([[100]], np.uint8))[0][0, 0]), 100.0, "accetta un'immagine 2-D")
    c.raises(ValueError, lambda: luma_sat(np.zeros((2, 2, 2, 2), np.uint8)), "forma inattesa")

    # Bande.
    m = np.zeros((20, 10), bool)
    m[2:6] = True
    m[10:18] = True
    c.eq(find_bands(m, min_height=3), [(2, 5), (10, 17)], "due bande separate")
    c.eq(find_bands(m, min_height=6), [(10, 17)], "min_height scarta le bande sottili")
    c.eq(find_bands(np.zeros((5, 5), bool), 1), [], "nessuna banda su maschera vuota")
    m2 = np.zeros((6, 10), bool)
    m2[3:] = True
    c.eq(find_bands(m2, 3), [(3, 5)], "una banda che arriva al bordo viene chiusa")
    m3 = np.zeros((6, 10), bool)
    m3[2, 0] = True
    c.eq(find_bands(m3, 1, min_pixels=2), [], "min_pixels scarta il pixel isolato")

    # Le code delle lettere. Sotto la linea di base passano solo le code di
    # g, q, p: poche righe-pixel con pochissimi pixel, che `min_pixels` scarta.
    # Se finiscono fuori dalla banda il ritaglio arriva decapitato all'OCR, e
    # una `g` senza coda *e'* una `a` — il modello non sbaglia, legge quello
    # che vede. Sulla registrazione vera questo produceva "Oaai recuperiamo
    # veicoli acauistati" al posto di "Oggi recuperiamo veicoli acquistati".
    coda = np.zeros((30, 100), bool)
    coda[5:20, :60] = True  # il corpo delle lettere
    coda[20:24, :3] = True  # le code di due o tre lettere
    c.eq(
        find_bands(coda, min_height=5, min_pixels=10, grow=0.45),
        [(5, 23)],
        "la banda si estende sulle code",
    )
    c.eq(
        find_bands(coda, min_height=5, min_pixels=10, grow=0.0),
        [(5, 19)],
        "senza estensione le code restano fuori",
    )

    # L'estensione ha un limite, altrimenti la coda di una riga si salda
    # all'asta di quella sotto e due battute diventano una.
    vicine = np.zeros((44, 100), bool)
    vicine[2:16, :60] = True
    vicine[16:26, :2] = True  # un filo sottile che collega le due righe
    vicine[26:40, :60] = True
    bande = find_bands(vicine, min_height=5, min_pixels=10, grow=0.45)
    c.eq(len(bande), 2, "due righe collegate da un filo restano due")
    c.ok(bande[0][1] < 26, "la prima non arriva alla seconda")
    c.ok(bande[1][0] > 15, "la seconda non arriva alla prima")

    # E la prova su testo vero: il ritaglio che arriva all'OCR deve contenere
    # **tutto** l'inchiostro della riga, non solo il suo nucleo.
    con_code = render_subtitles([("Oggi paghi que" + "l gioco?", WHITE)], size=(90, 700))
    luma_cc, _ = luma_sat(con_code)
    mask_cc = text_mask(luma_cc, cfg)
    bande_cc = classify_lines(con_code, cfg)
    c.eq(len(bande_cc), 1, "una riga sola")
    b = bande_cc[0]
    dentro = int(mask_cc[b.top : b.bottom + 1, b.x0 : b.x1].sum())
    totale = int(mask_cc[:, b.x0 : b.x1].sum())
    c.ok(
        dentro >= totale * 0.98,
        f"il ritaglio contiene tutto l'inchiostro della riga ({dentro}/{totale})",
    )

    # Classificazione su testo renderizzato davvero.
    roi = render_subtitles(
        [
            ("Non ho tempo per queste stronzate.", WHITE),
            ("Dove credi di andare?", GREY),
            ("Premi E per entrare", YELLOW),
            ("Obiettivo: il molo", GREEN),
        ],
        size=(260, 900),
    )
    bands = classify_lines(roi, cfg)
    c.eq(len(bands), 4, "trova tutte e quattro le righe")
    c.eq([b.cls for b in bands][:2], [LineClass.WHITE, LineClass.GREY], "bianco e grigio separati")
    c.eq(bands[2].cls, LineClass.COLORED, "il giallo e' colorato")
    c.eq(bands[3].cls, LineClass.COLORED, "il verde e' colorato")
    c.ok(bands[0].luma > bands[1].luma + 50, "il bianco stacca nettamente dal grigio")
    c.ok(bands[0].sat < cfg.sat_max, "una riga bianca non e' satura")
    c.ok(bands[2].sat > cfg.sat_max, "una riga gialla e' satura")
    c.ok(all(b.height >= cfg.min_line_height for b in bands), "nessuna banda troppo bassa")
    c.ok(
        all(0 <= b.x0 < b.x1 <= roi.shape[1] for b in bands),
        "i limiti orizzontali sono dentro la ROI",
    )
    c.ok(bands[0].x0 > 0, "il ritaglio orizzontale e' stretto sul testo")
    c.ok(
        bands[0].crop.shape == (bands[0].height, bands[0].x1 - bands[0].x0),
        "il ritaglio ha la forma della banda",
    )
    # Il ritaglio NON e' binario: conserva le sfumature dei bordi, che sono cio'
    # su cui il riconoscitore conta. Binarizzare costava 1,5 punti di CER.
    c.ok(len(np.unique(bands[0].crop)) > 2, "il ritaglio conserva i livelli intermedi")
    c.eq(int(bands[0].crop.min()), 0, "fuori dal testo il ritaglio e' nero")
    c.ok(int(bands[0].crop.max()) > 200, "il corpo del glifo bianco resta chiaro")
    c.ok(
        int(bands[1].crop.max()) < int(bands[0].crop.max()),
        "il ritaglio del grigio e' piu' scuro di quello del bianco",
    )

    c.eq(classify_lines(np.zeros((100, 400, 3), np.uint8), cfg), [], "ROI nera: nessuna riga")

    # Robustezza al rumore di fondo.
    for noise in (0.02, 0.05, 0.10):
        r = render_subtitles(
            [("Battuta bianca", WHITE), ("Battuta grigia", GREY)],
            size=(160, 900),
            noise=noise,
            seed=1,
        )
        got = [b.cls for b in classify_lines(r, cfg)]
        c.eq(got, [LineClass.WHITE, LineClass.GREY], f"regge il rumore {noise:.2f}")

    # Sfondo chiaro: il contrasto locale e' quello che salva il caso.
    bright = render_subtitles(
        [("Battuta bianca", WHITE), ("Battuta grigia", GREY)], size=(160, 900), background=120
    )
    with_contrast = [b.cls for b in classify_lines(bright, cfg)]
    c.eq(with_contrast, [LineClass.WHITE, LineClass.GREY], "sfondo 120: il contrasto locale regge")

    flat = VisionConfig()
    flat.use_local_contrast = False
    got_flat = [b.cls for b in classify_lines(bright, flat)]
    c.ok(
        got_flat != [LineClass.WHITE, LineClass.GREY],
        "sfondo 120 con la sola soglia assoluta: fallisce (e' il motivo del contrasto locale)",
    )

    # La maschera dice quali pixel sono testo.
    luma, _ = luma_sat(bright)
    c.ok(text_mask(luma, cfg).mean() < 0.5, "il contrasto locale non prende tutto lo sfondo")
    c.ok(text_mask(luma, flat).mean() > 0.9, "la soglia assoluta invece prende tutto")


def test_diff(c) -> None:
    c.group("diff")

    d = RoiDiff(threshold=0.004, stride=2, ink_min_luma=110)
    black = np.zeros((80, 200, 3), np.uint8)
    white_bar = black.copy()
    white_bar[20:40, 20:180] = 255

    c.eq(d.update(black).change, Change.NONE, "primo frame vuoto: nessun cambiamento")
    c.eq(d.update(black).change, Change.NONE, "fermo su nero: nessun cambiamento")
    r = d.update(white_bar)
    c.eq(r.change, Change.APPEARED, "il testo che compare e' una comparsa")
    c.ok(r.ratio > 0.004, "la comparsa supera la soglia")
    c.ok(r.ink > 0.0, "la comparsa porta inchiostro")
    c.eq(d.update(white_bar).change, Change.NONE, "sottotitolo fermo: nessun cambiamento")

    other = black.copy()
    other[20:40, 20:100] = 255
    c.eq(d.update(other).change, Change.REPLACED, "testo diverso al posto del precedente")
    # **La sparizione si conferma, non si intravede.** Il primo frame senza
    # inchiostro non basta piu': dal vivo, una scena chiara dietro il sottotitolo
    # abbassa il contrasto dei glifi per un frame, l'inchiostro scende, e il
    # diff dichiarava sparita una battuta ancora a schermo. Il tracker la
    # chiudeva d'autorita' e la lettura dopo la riapriva **identica**: e' il
    # difetto della voce doppia, trovato all'ascolto e invisibile sul banco.
    c.eq(d.update(black).change, Change.NONE, "un solo frame senza testo non e' una sparizione")
    c.eq(d.update(black).change, Change.NONE, "due nemmeno")
    c.eq(d.update(black).change, Change.VANISHED, "al terzo la sparizione e' confermata")

    # E la prova che il difetto non torni: il testo resta, cambia il contorno.
    # Deve **non** succedere niente, per quanti lampi passino.
    lampo = RoiDiff(vanish_frames=3)
    barra = np.zeros((60, 200, 3), np.uint8)
    barra[20:40, 20:180] = 255
    lampo.update(barra)
    for k in range(6):
        sfondo = barra.copy()
        # Sfondo che si accende e si spegne: il testo c'e' sempre, ma il suo
        # contrasto locale crolla, ed e' esattamente cio' che accade dietro un
        # sottotitolo quando esplode qualcosa.
        sfondo[:, :] = np.maximum(sfondo, 200 if k % 2 == 0 else 0)
        c.ok(
            lampo.update(sfondo).change is not Change.VANISHED,
            f"lampo {k}: il contorno che cambia non fa sparire il sottotitolo",
        )

    fresh = RoiDiff()
    c.eq(
        fresh.update(white_bar).change,
        Change.APPEARED,
        "un sottotitolo gia' a schermo all'avvio viene visto",
    )

    moved = RoiDiff(threshold=0.5)
    moved.update(black)
    c.eq(moved.update(white_bar).change, Change.NONE, "sotto soglia non e' un cambiamento")

    resized = RoiDiff()
    resized.update(black)
    c.eq(
        resized.update(np.zeros((40, 100, 3), np.uint8)).change,
        Change.NONE,
        "cambio di risoluzione senza testo: si riparte in silenzio",
    )

    dark = RoiDiff(threshold=0.004, ink_min_luma=110)
    dark.update(black)
    moving_bg = black.copy()
    moving_bg[:, :] = 60  # lo sfondo del gioco si muove, ma non e' testo
    c.eq(dark.update(moving_bg).change, Change.NONE, "sfondo che cambia senza testo: si ignora")

    # Un muro chiaro non e' inchiostro. E' il caso che aveva rotto tutto: con
    # "almeno un pixel sopra soglia" ogni frame di gioco ha inchiostro, quindi
    # comparsa e sparizione non scattano mai e il t_off preciso non arriva.
    wall = np.full((80, 200, 3), 210, np.uint8)
    c.close(RoiDiff(stride=2)._ink(RoiDiff(stride=2)._sample(wall)), 0.0, "un muro chiaro non e' testo")
    thin = RoiDiff(stride=2)
    c.ok(thin._ink(thin._sample(white_bar)) > 0.20, "una riga di testo lo e'")

    # L'inchiostro si conta per colonna, non per area: lo stesso testo dentro
    # una ROI piu' alta deve dare lo stesso numero. Contandolo per area darebbe
    # meno della meta', e una soglia tarata su una ROI stretta spegnerebbe in
    # silenzio tutte le ROI larghe.
    bassa = np.zeros((60, 200, 3), np.uint8)
    bassa[20:40, 20:180] = 255
    alta = np.zeros((240, 200, 3), np.uint8)
    alta[20:40, 20:180] = 255
    dd = RoiDiff(stride=2)
    c.close(
        dd._ink(dd._sample(alta)),
        dd._ink(dd._sample(bassa)),
        "lo stesso testo da' lo stesso inchiostro in una ROI quattro volte piu' alta",
        tol=0.02,
    )

    c.raises(ValueError, lambda: RoiDiff(stride=0), "stride nullo e' un errore")

    r2 = RoiDiff()
    r2.update(white_bar)
    r2.reset()
    c.eq(r2.update(black).change, Change.NONE, "reset dimentica il passato")


def test_ocr_prep(c) -> None:
    c.group("ocr")

    # La regola e' misurata: il costo del riconoscitore scala con la LARGHEZZA
    # del tensore, e ingrandire in altezza allarga in proporzione. Su una
    # battuta lunga portare a 48 px raddoppia il costo (120 ms invece di 59)
    # senza guadagnare un decimale di accuratezza. Si ingrandisce solo sotto i
    # 20 px, dove qualcosa si guadagna davvero.
    normale = np.zeros((24, 600), np.uint8)
    normale[4:20, 10:590] = 255
    out = prepare(normale)
    c.eq(out.ndim, 3, "prepare produce tre canali")
    c.eq(out.shape[0], 32, "una riga di altezza normale conserva la propria altezza (24+2*4)")
    c.eq(out.shape[1], 608, "e la propria larghezza: nessun allargamento gratuito")
    c.ok(bool((out[0] == 0).all()), "il margine aggiunto e' nero")

    piccola = np.zeros((10, 100), np.uint8)
    piccola[2:8, 5:95] = 255
    su = prepare(piccola)
    c.eq(su.shape[0], 32, "una riga davvero piccola viene ingrandita")
    c.ok(su.shape[1] > 108, "e la larghezza cresce in proporzione")

    tall = np.zeros((80, 200), np.uint8)
    tall[10:70, 10:190] = 255
    c.eq(prepare(tall).shape[0], 88, "una riga alta non viene toccata")

    c.eq(prepare(np.zeros((0, 10), np.uint8)).shape, (32, 32, 3), "una maschera vuota non esplode")
    c.eq(prepare(np.zeros((20, 40, 3), np.uint8)).ndim, 3, "accetta anche un ingresso a 3 canali")

    mask = normale
    c.eq(NullOcr().read(mask), ("", 0.0), "NullOcr non legge niente")
    echo = EchoOcr(["uno", "due"])
    c.eq(echo.read(mask)[0], "uno", "EchoOcr restituisce il primo testo")
    c.eq(echo.read(mask)[0], "due", "EchoOcr avanza")
    c.eq(echo.read(mask)[0], "uno", "EchoOcr ricomincia")
    c.eq(EchoOcr().read(mask)[0], "", "EchoOcr senza testi non esplode")
    c.ok(isinstance(make_ocr("none"), NullOcr), "make_ocr costruisce il backend nullo")
    c.raises(ValueError, lambda: make_ocr("inventato"), "backend OCR sconosciuto e' un errore")


def test_tracker(c) -> None:
    c.group("tracker")

    c.eq(normalize("  Ciao   MONDO "), "ciaomondo", "normalize tiene solo lettere e cifre")
    c.close(similarity("ciao mondo", "ciao mondo"), 1.0, "testi identici")
    c.ok(similarity("ciao mondo", "ciao mondu") > 0.88, "un carattere di scarto resta la stessa")
    c.ok(similarity("ciao mondo", "tutt'altra frase") < 0.5, "frasi diverse")
    c.close(similarity("", ""), 1.0, "due vuoti sono uguali")
    c.close(similarity("a", ""), 0.0, "vuoto contro non vuoto")

    # La forma di confronto si verifica su casi noti prima che su un frame vero:
    # sono tutti presi dalla registrazione, dove ognuno riapriva una battuta.
    # A sinistra cio' che l'OCR ha letto, a destra la stessa battuta letta bene.
    for a, b, why in [
        ("Ma domani...", "Madomani.", "spazi e punti di sospensione"),
        ("Saremo insieme!", "Saremoinsieme！！", "punteggiatura a larghezza intera"),
        ("Toc toc, negri!", "Toc toc，negri！", "virgola a larghezza intera"),
        ("→Dalle palle", "Dalle palle", "glifo spurio in testa"),
        ("Piantala... Davvero?", "Piantala...Davvero？", "spazio mancante"),
        ("perche'", "perché", "accento contro apostrofo"),
        ("Franklin ha ottenuto il titolo.", "Franklin ha ottenuto il titolo. .", "coda spuria"),
    ]:
        c.eq(normalize(a), normalize(b), f"stessa battuta malgrado {why}")

    c.eq(normalize("..."), "", "una lettura di sola punteggiatura si annulla")

    # Lo scarto si conta in caratteri, e la verifica sta tutta nel confronto fra
    # le due righe: le stesse due lettere sbagliate, su una battuta corta e su
    # una lunga. Una soglia in percentuale ne accettava una e rifiutava l'altra.
    corta = (normalize("Piantala... Davvero?"), normalize("Piantala... Dawwero?"))
    lunga = (
        normalize("Franklin ha ottenuto il titolo di dipendente del mese."),
        normalize("Franklln ha ottenuto il titolo di dipendente del rnese."),
    )
    c.ok(wrong_chars(*corta) <= 2.5, "due lettere su una battuta corta restano due")
    c.ok(wrong_chars(*lunga) <= 3.5, "due lettere su una battuta lunga restano due")
    c.ok(similarity(*corta) < similarity(*lunga), "in percentuale invece la corta pagava di piu'")

    # E l'altra meta' della verifica, senza la quale la prima non dimostra
    # niente: uno scarto generoso non deve far combaciare battute diverse.
    for a, b, why in [
        ("Come va, bello?", "Mi prendi per il culo, vero?", "battute diverse"),
        ("Non mi accontento.", "Non me ne frega.", "stesso inizio, seguito diverso"),
        ("Dalle palle", "alla cappella.", "due righe della stessa frase"),
        ("Sali sulla moto.", "Sali sulla macchina.", "stesso ordine, oggetto diverso"),
    ]:
        na, nb = normalize(a), normalize(b)
        cfg_ = VisionConfig()
        budget = max(float(cfg_.max_wrong_chars), cfg_.max_wrong_frac * max(len(na), len(nb)))
        c.ok(wrong_chars(na, nb) > budget, f"restano distinte: {why}")

    # I gruppi che seguono verificano il conteggio a **passate**, quindi
    # spengono la tenuta a tempo: con entrambe attive una scadenza non
    # avverrebbe mai su timeline lunghe un decimo di secondo, e il test
    # misurerebbe la condizione sbagliata. La tenuta a tempo ha un gruppo suo
    # piu' sotto.
    cfg = VisionConfig()
    cfg.stable_reads = 2
    cfg.hold_frames = 0
    cfg.hold_seconds = 0.0

    def w(text, t):
        return SubtitleEvent(text=text, cls=LineClass.WHITE, t_on=t)

    tr = SubtitleTracker(cfg)
    out = tr.feed([w("Sali in macchina", 1.0)], 1.0)
    c.eq(len(out.opened), 0, "una lettura sola non basta a confermare")
    out = tr.feed([w("Sali in macchina", 1.033)], 1.033)
    c.eq(len(out.opened), 1, "due letture concordi confermano")
    c.close(
        out.opened[0].t_on,
        1.0,
        "il t_on e' quello della PRIMA lettura, non della conferma",
    )
    c.eq(len(tr.active), 1, "la battuta risulta attiva")

    out = tr.feed([w("Sali in macchina", 1.1)], 1.1)
    c.eq(len(out.opened), 0, "la stessa battuta non viene riaperta")
    out = tr.feed([w("Sali in macchinaa", 1.2)], 1.2)
    c.eq(len(out.opened), 0, "uno sfarfallio dell'OCR non apre una battuta nuova")

    out = tr.feed([], 2.0)
    c.eq(len(out.closed), 1, "quando sparisce, la battuta si chiude")
    c.close(out.closed[0].duration, 1.0, "la chiusura fissa la durata reale")
    c.eq(len(tr.active), 0, "dopo la chiusura non resta nulla di attivo")

    # Sostituzione: chiude la vecchia e apre la nuova. La vecchia si chiude
    # nell'istante in cui il testo a schermo cambia, **non** quando la nuova
    # viene confermata: quella conferma arriva `stable_reads` passate dopo, e
    # attribuirle la chiusura allungherebbe la durata della battuta precedente
    # di altrettanto. Con `hold_frames = 0` la differenza e' visibile subito.
    tr = SubtitleTracker(cfg)
    tr.feed([w("prima battuta", 0.0)], 0.0)
    tr.feed([w("prima battuta", 0.1)], 0.1)
    out = tr.feed([w("seconda battuta", 1.0)], 1.0)
    c.eq(len(out.closed), 1, "la sostituzione chiude quella prima")
    c.close(out.closed[0].duration, 1.0, "e la chiude quando il testo e' cambiato")
    out = tr.feed([w("seconda battuta", 1.1)], 1.1)
    c.eq(len(out.opened), 1, "la sostituzione apre quella nuova")
    c.eq(out.opened[0].text, "seconda battuta", "la nuova e' quella giusta")
    c.eq(len(out.closed), 0, "e non chiude due volte la stessa")

    # La sostituzione senza schermo vuoto, con hold_frames > 0: qui la vecchia
    # non e' ancora scaduta quando la nuova si conferma, ed e' la conferma a
    # chiuderla. Senza questo ramo resterebbe aperta per tutta la battuta dopo.
    lento = VisionConfig()
    lento.stable_reads = 2
    lento.hold_frames = 5
    lento.hold_seconds = 0.0
    tr_lento = SubtitleTracker(lento)
    tr_lento.feed([w("prima battuta", 0.0)], 0.0)
    tr_lento.feed([w("prima battuta", 0.1)], 0.1)
    tr_lento.feed([w("seconda battuta", 1.0)], 1.0)
    out = tr_lento.feed([w("seconda battuta", 1.1)], 1.1)
    c.eq(len(out.opened), 1, "la nuova si conferma")
    c.eq(len(out.closed), 1, "e chiude la vecchia, che non era ancora scaduta")
    c.eq(out.closed[0].text, "prima battuta", "quella chiusa e' la vecchia")

    # Continuazione invece di sostituzione. E' la strada da cui passava il 64%
    # delle chiusure sui 27 minuti, e l'80% di quelle era seguita subito da una
    # riapertura: la stessa battuta, letta abbastanza male da uscire dal budget
    # di caratteri ma non abbastanza da essere un'altra frase.
    # Le tenute qui sono quelle vere, e non e' un dettaglio: con tenuta zero la
    # battuta a schermo muore alla prima lettura che non la ritrova, e quando la
    # storpiata si conferma non c'e' piu' nessuna orfana da continuare. La
    # continuazione esiste solo finche' la vecchia e' ancora viva.
    cont = VisionConfig()
    cont.stable_reads = 2
    tr_cont = SubtitleTracker(cont)
    tr_cont.feed([w("Non ho mai avuto un figlio nero", 0.0)], 0.0)
    tr_cont.feed([w("Non ho mai avuto un figlio nero", 0.1)], 0.1)
    tr_cont.feed([w("Nan hg mai avuta un fiqlio nera", 0.2)], 0.2)
    out = tr_cont.feed([w("Nan hg mai avuta un fiqlio nera", 0.3)], 0.3)
    c.eq(len(out.opened), 0, "una lettura storpiata non apre una battuta nuova")
    c.eq(len(out.closed), 0, "e non chiude quella che c'era")
    c.eq(len(tr_cont.active), 1, "resta una battuta sola")
    c.close(tr_cont.active[0].t_on, 0.0, "che conserva il t_on della prima lettura")

    # E il caso che NON deve scattare, senza il quale il precedente non
    # dimostra niente: due battute davvero diverse si sostituiscono.
    tr_cont = SubtitleTracker(cont)
    tr_cont.feed([w("Come va, bello?", 0.0)], 0.0)
    tr_cont.feed([w("Come va, bello?", 0.1)], 0.1)
    tr_cont.feed([w("Mi prendi per il culo, vero?", 0.2)], 0.2)
    out = tr_cont.feed([w("Mi prendi per il culo, vero?", 0.3)], 0.3)
    c.eq(len(out.opened), 1, "una battuta diversa apre davvero")
    c.eq(len(tr_cont.active), 1, "e prende il posto della precedente")
    c.eq(tr_cont.active[0].text, "Mi prendi per il culo, vero?", "quella giusta resta a schermo")

    # **La seconda forma della rilettura: un pezzo, poi il testo intero.**
    # L'OCR legge il sottotitolo mentre compare e ne prende meta'. Il rapporto
    # fra il frammento e la frase intera e' basso per costruzione — meta' del
    # lungo non ha corrispondenza — quindi la continuazione non scattava e la
    # battuta veniva **riaperta**: due eventi, due sintesi, e la stessa frase
    # detta due volte. Dal vivo una battuta letta cosi' tre volte ha messo 6,6
    # secondi di parlato in coda.
    tr_pezzo = SubtitleTracker(cont)
    tr_pezzo.feed([w("Non me ne frega un cazzo. C'e un", 0.0)], 0.0)
    tr_pezzo.feed([w("Non me ne frega un cazzo. C'e un", 0.1)], 0.1)
    intero = "Non me ne frega un cazzo. C'e un motivo se Simeon paga uno dall'aria cattiva"
    tr_pezzo.feed([w(intero, 0.2)], 0.2)
    out = tr_pezzo.feed([w(intero, 0.3)], 0.3)
    c.eq(len(out.opened), 0, "il testo intero non riapre la battuta di cui e' la continuazione")
    c.eq(len(tr_pezzo.active), 1, "resta una battuta sola")
    c.eq(tr_pezzo.active[0].text, intero, "e si tiene la lettura piu' ricca")
    c.close(tr_pezzo.active[0].t_on, 0.0, "col t_on della prima lettura, non del completamento")

    # E il contrario: la coda riletta da sola. `contenimento` guarda il piu'
    # corto dentro il piu' lungo, quindi vale in tutti e due i versi.
    tr_coda = SubtitleTracker(cont)
    lunga = "Tu fai qualche lavoro per un idiota, poi il rapporto diventa complicato."
    tr_coda.feed([w(lunga, 0.0)], 0.0)
    tr_coda.feed([w(lunga, 0.1)], 0.1)
    tr_coda.feed([w("rapporto diventa complicato.", 0.2)], 0.2)
    out = tr_coda.feed([w("rapporto diventa complicato.", 0.3)], 0.3)
    c.eq(len(out.opened), 0, "nemmeno la sola coda riletta apre una battuta nuova")

    # **La guardia che rende utili le due sopra**: sotto `continue_min_chars` il
    # contenimento non si applica, altrimenti due battute corte e diverse
    # verrebbero fuse. Senza questa, "Segui." mangerebbe "Se qui".
    tr_corta = SubtitleTracker(cont)
    tr_corta.feed([w("Segui.", 0.0)], 0.0)
    tr_corta.feed([w("Segui.", 0.1)], 0.1)
    tr_corta.feed([w("Fermo!", 0.2)], 0.2)
    out = tr_corta.feed([w("Fermo!", 0.3)], 0.3)
    c.eq(len(out.opened), 1, "due battute corte e diverse restano due")

    # Una banda di texture che si infila sopra la riga vera ne sposterebbe la
    # posizione. Con l'abbinamento per somiglianza non cambia niente: e' il bug
    # che sul video vero produceva 55 aperture in 50 secondi invece di ~20.
    tr_pos = SubtitleTracker(cfg)
    tr_pos.feed([w("Il tuo amico Simeon non stava sparando cazzate.", 0.0)], 0.0)
    tr_pos.feed([w("Il tuo amico Simeon non stava sparando cazzate.", 0.1)], 0.1)
    out = tr_pos.feed(
        [
            w("rumore di scena", 0.2),
            w("Il tuo amico Simeon non stava sparando cazzate.", 0.2),
        ],
        0.2,
    )
    c.eq(len(out.opened), 0, "una riga in piu' non riapre quella che c'era gia'")
    c.eq(len(out.closed), 0, "e non la chiude")

    # Bianco e grigio sono due posti diversi: non si scacciano a vicenda.
    tr = SubtitleTracker(cfg)
    g = SubtitleEvent(text="lasciami stare", cls=LineClass.GREY, t_on=0.0)
    tr.feed([w("dove vai?", 0.0), g], 0.0)
    out = tr.feed([w("dove vai?", 0.1), g], 0.1)
    c.eq(len(out.opened), 2, "bianco e grigio si confermano insieme")
    c.eq({e.cls for e in out.opened}, {LineClass.WHITE, LineClass.GREY}, "una per classe")
    out = tr.feed([w("dove vai?", 0.2)], 0.2)
    c.eq(len(out.closed), 1, "sparisce solo la grigia")
    c.eq(out.closed[0].cls, LineClass.GREY, "si chiude proprio quella grigia")
    c.eq(len(tr.active), 1, "la bianca resta a schermo")

    # hold_frames tollera un frame perso dall'OCR.
    tolerant = VisionConfig()
    tolerant.stable_reads = 1
    tolerant.hold_frames = 2
    tolerant.hold_seconds = 0.0
    tr = SubtitleTracker(tolerant)
    tr.feed([w("resisti", 0.0)], 0.0)
    c.eq(len(tr.active), 1, "con stable_reads=1 basta una lettura")
    out = tr.feed([], 0.1)
    c.eq(len(out.closed), 0, "un frame mancante non chiude la battuta")
    out = tr.feed([w("resisti", 0.2)], 0.2)
    c.eq(len(out.opened), 0, "la battuta ritrovata non viene riaperta")
    tr.feed([], 0.3)
    tr.feed([], 0.4)
    out = tr.feed([], 0.5)
    c.eq(len(out.closed), 1, "dopo hold_frames assenze la battuta si chiude")

    # E la tenuta a TEMPO, che e' l'altra meta' della stessa condizione:
    # entrambe devono cadere. Nelle scene mosse il diff apre passate a raffica e
    # tre di esse valgono un decimo di secondo — misurato sui 27 minuti, 539
    # raffiche di letture fallite, novantesimo percentile 17 passate.
    a_tempo = VisionConfig()
    a_tempo.stable_reads = 1
    a_tempo.hold_frames = 1
    a_tempo.hold_seconds = 0.5
    tr = SubtitleTracker(a_tempo)
    tr.feed([w("resisti", 0.0)], 0.0)
    for k in range(1, 8):  # sette passate a vuoto in 70 ms: le passate bastano...
        out = tr.feed([], k * 0.01)
    c.eq(len(out.closed), 0, "molte passate in poco tempo non chiudono la battuta")
    out = tr.feed([], 0.6)  # ...ma il tempo no, finche' non passa
    c.eq(len(out.closed), 1, "quando cade anche il tempo, la battuta si chiude")

    # La prova indipendente scavalca entrambe: il diff ha VISTO sparire
    # l'inchiostro, e non c'e' niente da attendere.
    tr = SubtitleTracker(a_tempo)
    tr.feed([w("resisti", 0.0)], 0.0)
    out = tr.feed([], 0.01, certain=True)
    c.eq(len(out.closed), 1, "la sparizione certa chiude subito, tenuta o no")

    # Testo vuoto e chiusura finale.
    tr = SubtitleTracker(tolerant)
    c.eq(len(tr.feed([w("   ", 0.0)], 0.0).opened), 0, "una lettura vuota non apre nulla")
    tr.feed([w("ultima", 1.0)], 1.0)
    closed = tr.close_all(2.0)
    c.eq(len(closed), 1, "close_all chiude quello che resta aperto")
    c.close(closed[0].duration, 1.0, "close_all fissa la durata")
    c.eq(len(tr.active), 0, "dopo close_all non resta niente")


def test_reader(c) -> None:
    c.group("reader")

    cfg = VisionConfig()
    cfg.stable_reads = 2
    cfg.hold_frames = 0
    cfg.roi = ROI

    testi = ["Sali in macchina, muoviti!"]
    ocr = EchoOcr(testi)
    reader = SubtitleReader(cfg, ocr)

    vuoto = empty_frame()
    con_testo = frame_with_roi([("Sali in macchina, muoviti!", WHITE)], roi=ROI)

    reader.run(vuoto)
    c.eq(ocr.calls, 0, "senza testo l'OCR non viene mai chiamato")

    out1 = reader.run(con_testo)
    c.eq(len(out1.opened), 0, "la prima lettura non conferma ancora")
    c.eq(ocr.calls, 1, "la comparsa fa scattare una lettura")

    out2 = reader.run(con_testo)
    c.eq(len(out2.opened), 1, "la seconda lettura conferma la battuta")
    c.eq(out2.opened[0].text, testi[0], "il testo e' quello letto")
    c.eq(ocr.calls, 2, "sono bastate due letture")

    prima = ocr.calls
    for _ in range(30):
        reader.run(con_testo)
    c.eq(ocr.calls, prima, "un sottotitolo fermo non viene riletto nemmeno una volta")
    c.ok(
        reader.metrics.counter("vision.frames.gated").value >= 30,
        "i frame fermi risultano fermati dal cancello",
    )

    # Tre frame vuoti: la sparizione si conferma prima di essere creduta. I due
    # frame in piu' sono il prezzo dichiarato di non chiudere una battuta che e'
    # ancora a schermo e ha solo perso contrasto per un istante.
    c.eq(len(reader.run(vuoto).closed), 0, "il primo frame vuoto non chiude niente")
    c.eq(len(reader.run(vuoto).closed), 0, "il secondo nemmeno")
    out = reader.run(vuoto)
    c.eq(len(out.closed), 1, "quando sparisce davvero, la battuta si chiude")

    # Le righe colorate non arrivano mai al riconoscitore.
    ocr2 = EchoOcr(["dialogo"])
    reader2 = SubtitleReader(cfg, ocr2)
    misto = frame_with_roi(
        [("Sali in macchina", WHITE), ("Premi E per entrare", YELLOW), ("Obiettivo: molo", GREEN)],
        roi=ROI,
    )
    reader2.run(misto)
    c.eq(ocr2.calls, 1, "delle tre righe solo quella di dialogo paga l'OCR")
    c.eq(
        reader2.metrics.counter("vision.lines.colored").value,
        2,
        "le due righe colorate risultano scartate dal colore",
    )

    # Bianco e grigio: due battute, non una.
    ocr3 = EchoOcr(["Dove vai?", "Lasciami stare"])
    reader3 = SubtitleReader(cfg, ocr3)
    due = frame_with_roi([("Dove vai?", WHITE), ("Lasciami stare", GREY)], roi=ROI)
    reader3.run(due)
    out = reader3.run(due)
    c.eq(len(out.opened), 2, "bianco e grigio producono due battute")
    c.eq(
        [e.cls for e in out.opened],
        [LineClass.WHITE, LineClass.GREY],
        "nell'ordine in cui stanno a schermo",
    )

    # Righe troppo corte per essere una battuta. Sulla registrazione vera la
    # texture della scena (un cordolo, una striscia bianca) produce bande che
    # l'OCR legge come '1' o '—': passano ogni soglia di colore, perche' sono
    # davvero bianche e davvero acromatiche. Le ferma la lingua, non il colore.
    corto = VisionConfig()
    corto.stable_reads = 1
    corto.roi = ROI
    corto.min_ocr_chars = 2
    una_riga = frame_with_roi([("Sali in macchina", WHITE)], roi=ROI)
    reader_corto = SubtitleReader(corto, EchoOcr(["1"]))
    aperte = len(reader_corto.run(una_riga).opened) + len(reader_corto.run(una_riga).opened)
    c.eq(aperte, 0, "una riga di un carattere non diventa una battuta")

    corto2 = VisionConfig()
    corto2.stable_reads = 1
    corto2.roi = ROI
    corto2.min_ocr_chars = 2
    reader_ok = SubtitleReader(corto2, EchoOcr(["Va bene"]))
    c.eq(len(reader_ok.run(una_riga).opened), 1, "una riga vera passa lo stesso filtro")

    # La durata misurata deve essere quella vera, indipendentemente da cosa
    # succede a schermo dopo. Questa verifica esiste per un bug preso sul banco:
    # hold_frames conta le passate del tracker, e le passate avvengono solo
    # quando il diff apre il cancello — una battuta sparita restava aperta fino
    # al successivo cambiamento qualunque, e riportava 4,0 s invece di 2,0.
    # Sulla durata poggia tutta la calibrazione del tempo di F2.
    lento = VisionConfig()
    lento.stable_reads = 2
    lento.hold_frames = 3
    lento.roi = ROI
    reader5 = SubtitleReader(lento, EchoOcr(["battuta breve"]), clock=_FixedClock())
    orologio = reader5._clock
    testo_frame = frame_with_roi([("battuta breve", WHITE)], roi=ROI)

    orologio.t = 1.0
    reader5.run(testo_frame)
    orologio.t = 1.033
    reader5.run(testo_frame)
    # Tre frame vuoti: la sparizione si conferma prima di essere creduta, e
    # allora chiude senza aspettare `hold_frames`. I due frame che servono a
    # confermarla sono il prezzo dichiarato di non chiudere una battuta ancora
    # a schermo.
    orologio.t = 2.933
    reader5.run(vuoto)
    orologio.t = 2.967
    reader5.run(vuoto)
    orologio.t = 3.0
    out = reader5.run(vuoto)
    c.eq(len(out.closed), 1, "la sparizione confermata chiude senza aspettare hold_frames")
    c.close(out.closed[0].duration, 2.0, "la durata e' quella vera", tol=1e-6)

    # ...e hold_frames continua a proteggere dallo sfarfallio dell'OCR, che e'
    # il caso per cui esiste: li' il testo c'e' ancora, e' l'OCR che non lo vede.
    tol = VisionConfig()
    tol.stable_reads = 1
    tol.hold_frames = 2
    presente = SubtitleEvent(text="presente", cls=LineClass.WHITE, t_on=0.0)
    tr_flicker = SubtitleTracker(tol)
    tr_flicker.feed([presente], 0.0)
    c.eq(len(tr_flicker.feed([], 0.1).closed), 0, "assenza incerta: non chiude")
    c.eq(len(tr_flicker.feed([], 0.2, certain=True).closed), 1, "assenza certa: chiude subito")

    # Spento, non deve fare nulla e non deve rompere niente.
    reader4 = SubtitleReader(cfg, EchoOcr(["x"]), enabled=False)
    c.eq(len(reader4.run(con_testo).opened), 0, "lo stadio spento non produce battute")
    c.eq(len(reader4.run(None).opened), 0, "un frame assente non e' un errore")
