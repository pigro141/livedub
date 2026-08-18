"""Verifiche delle aree multiple.

La domanda vera non e' «la divisione funziona» ma **«un punto dello schermo puo'
finire dentro due pezzi?»**. Se puo', lo stesso sottotitolo viene letto due
volte, diventa due battute e due voci si accavallano — il difetto peggiore del
prodotto. Quindi le verifiche sono due invarianti e non una lista di casi:
**niente si sovrappone** e **niente si perde**.
"""

from __future__ import annotations

import random

from vision.aree import (
    Area,
    dividi,
    interseca,
    si_sovrappongono,
    sottrai,
    superficie,
)


def test_aree(c) -> None:
    c.group("aree")

    # -- il modo, che decide se una riga viene pronunciata --------------------
    c.ok(Area((0, 0.9, 1, 0.08)).parla, "l'area di dialogo di default parla")
    c.ok(not Area((0, 0.0, 1, 0.1), modo="testo").parla, "un'area di solo testo non parla")
    c.raises(ValueError, lambda: Area((0, 0, 1, 1), modo="canta"), "un modo inventato e' un errore")
    c.raises(ValueError, lambda: Area((0, 0, 0, 0.5)), "un'area di superficie nulla e' un errore")

    # -- intersezione ---------------------------------------------------------
    c.eq(interseca((0, 0, 1, 1), (0.5, 0.5, 1, 1)), (0.5, 0.5, 0.5, 0.5), "l'angolo comune")
    c.eq(interseca((0, 0, 0.4, 0.4), (0.6, 0.6, 0.2, 0.2)), None, "lontane, niente in comune")
    c.eq(interseca((0, 0, 0.5, 1), (0.5, 0, 0.5, 1)), None, "che si toccano sul bordo, nemmeno")

    # -- sottrazione: la superficie e' un'aritmetica, non un'opinione ---------
    intera = (0.0, 0.0, 1.0, 1.0)
    buco = (0.25, 0.25, 0.5, 0.5)
    pezzi = sottrai(intera, buco)
    c.close(superficie(pezzi), 1.0 - 0.25, "togliere un quarto ne lascia tre quarti", 1e-9)
    c.ok(not si_sovrappongono(pezzi), "e i pezzi rimasti non si sovrappongono fra loro")
    c.eq(len(pezzi), 4, "un buco in mezzo lascia quattro strisce")

    c.eq(sottrai((0, 0, 1, 1), (0, 0, 1, 1)), [], "sottrarre tutto non lascia niente")
    c.eq(sottrai((0, 0, 0.2, 0.2), (0.5, 0.5, 0.2, 0.2)), [(0, 0, 0.2, 0.2)],
         "sottrarre qualcosa di lontano non cambia niente")
    c.eq(len(sottrai((0, 0, 1, 1), (0, 0, 1, 0.5))), 1, "una fetta orizzontale ne lascia una")

    # -- e la stessa cosa a caso, che e' l'unica prova che regge --------------
    # Cinquecento coppie a caso: la superficie che resta deve essere sempre
    # quella dell'originale meno la parte in comune. Tre casi scritti a mano
    # provano tre casi; questo prova la regola.
    rng = random.Random(7)
    male = 0
    for _ in range(500):
        a = _a_caso(rng)
        b = _a_caso(rng)
        resti = sottrai(a, b)
        comune = interseca(a, b)
        atteso = a[2] * a[3] - (comune[2] * comune[3] if comune else 0.0)
        if abs(superficie(resti) - atteso) > 1e-9 or si_sovrappongono(resti):
            male += 1
    c.eq(male, 0, "su 500 coppie a caso la superficie torna e i pezzi restano disgiunti")

    # -- dividi: le due invarianti che contano --------------------------------
    aree = [
        Area((0.20, 0.88, 0.60, 0.08), nome="dialogo"),
        Area((0.00, 0.00, 0.50, 0.12), modo="testo", nome="obiettivo"),
    ]
    pezzi = dividi(aree)
    c.ok(not si_sovrappongono([p.roi for p in pezzi]), "due aree lontane restano intere")
    c.eq(len(pezzi), 2, "e restano due pezzi")
    c.eq([p.modo for p in pezzi], ["testo_audio", "testo"], "ognuno si porta dietro il suo modo")

    # Due aree che si accavallano per meta'.
    aree = [
        Area((0.0, 0.0, 0.6, 0.6), nome="prima"),
        Area((0.4, 0.4, 0.6, 0.6), nome="seconda"),
    ]
    pezzi = dividi(aree)
    c.ok(not si_sovrappongono([p.roi for p in pezzi]), "sovrapposte, i pezzi non si toccano")
    unione = 0.36 + 0.36 - 0.04  # due quadrati meno il comune 0,2 x 0,2
    c.close(superficie([p.roi for p in pezzi]), unione, "la superficie e' l'unione, non la somma", 1e-9)
    # **Vince chi e' dichiarato prima**, e va verificato: se no sarebbe l'ordine
    # di iterazione a decidere in silenzio chi perde dei pixel.
    prima = superficie([p.roi for p in pezzi if p.area == 0])
    c.close(prima, 0.36, "la prima area resta intera", 1e-9)
    c.close(superficie([p.roi for p in pezzi if p.area == 1]), 0.32, "e cede la seconda", 1e-9)

    # Un'area dentro un'altra sparisce del tutto, e va detto invece che scoperto.
    aree = [Area((0.0, 0.0, 1.0, 1.0)), Area((0.3, 0.3, 0.2, 0.2))]
    pezzi = dividi(aree)
    c.eq([p.area for p in pezzi], [0], "un'area contenuta in una precedente non produce pezzi")

    # -- tre aree, e la ricorsione che e' il caso in cui si sbaglia -----------
    aree = [
        Area((0.0, 0.0, 0.6, 0.6)),
        Area((0.3, 0.0, 0.6, 0.6)),
        Area((0.15, 0.3, 0.6, 0.6)),
    ]
    pezzi = dividi(aree)
    c.ok(not si_sovrappongono([p.roi for p in pezzi]), "con tre aree non si sovrappone niente")
    coperto = superficie([p.roi for p in pezzi])
    c.ok(coperto < 0.6 * 0.6 * 3, "e la superficie non e' la somma ingenua")
    c.ok(coperto > 0.6 * 0.6, "ma nemmeno una sola delle tre")

    # -- e a caso anche qui ---------------------------------------------------
    male = 0
    for _ in range(200):
        elenco = [Area(_a_caso(rng)) for _ in range(rng.randint(2, 5))]
        pezzi = dividi(elenco)
        if si_sovrappongono([p.roi for p in pezzi]):
            male += 1
    c.eq(male, 0, "su 200 gruppi a caso nessun punto finisce in due pezzi")

    # **E la tolleranza non deve poter nascondere una sovrapposizione vera.**
    # Vale un cinquecentesimo di pixel su 1920x1080, misurata sul caso che l'ha
    # resa necessaria (due pezzi confinanti risultavano comuni per 2,4e-20 di
    # schermo, perche' `ay + (cy - ay)` non e' esattamente `cy`). Se ammettesse
    # anche solo un pixel, questa verifica cadrebbe.
    c.ok(
        si_sovrappongono([(0.0, 0.0, 0.5, 0.5), (0.25, 0.25, 0.5, 0.5)]),
        "una sovrapposizione vera viene vista comunque",
    )
    un_pixel = 1.0 / 1920 * (1.0 / 1080)
    c.ok(
        si_sovrappongono([(0.0, 0.0, 0.5, 0.5), (0.5 - 1 / 1920, 0.5 - 1 / 1080, 0.5, 0.5)]),
        f"e anche una grande un pixel solo ({un_pixel:.1e} di schermo)",
    )
    c.ok(
        not si_sovrappongono([(0.0, 0.0, 0.5, 0.5), (0.5, 0.0, 0.5, 0.5)]),
        "due aree che si toccano sul bordo non si sovrappongono",
    )

    # -- le schegge si buttano ------------------------------------------------
    # Due aree quasi allineate lasciano strisce alte un millesimo di schermo:
    # non contengono testo e costerebbero comunque una passata di OCR, che e'
    # l'85% del lavoro della catena.
    aree = [Area((0.0, 0.0, 1.0, 0.5)), Area((0.0, 0.0, 1.0, 0.50002))]
    pezzi = dividi(aree)
    c.eq(len(pezzi), 1, "una scheggia da 0,00002 di schermo non diventa un'area da leggere")


def _a_caso(rng) -> tuple[float, float, float, float]:
    x = rng.uniform(0.0, 0.8)
    y = rng.uniform(0.0, 0.8)
    return (x, y, rng.uniform(0.05, 1.0 - x), rng.uniform(0.05, 1.0 - y))


def test_aree_catena(c) -> None:
    """Le aree dentro la catena, non solo in geometria.

    La domanda che la geometria non puo' chiudere: **la catena legge davvero da
    piu' posti, e sta zitta dove le e' stato detto?** Un modo dichiarato e non
    letto sarebbe il quinto campo di questo progetto misurato e mai usato.
    """
    from dataclasses import replace

    import numpy as np

    from core.clock import VirtualClock
    from core.config import Config
    from core.pipeline import DubPipeline
    from tools.frames import WHITE, empty_frame, font_available, render_subtitles
    from vision.aree import da_config, dividi

    c.group("aree")

    cfg = Config()
    cfg.tts.backend = "tone"
    cfg.speaker.backend = "none"
    cfg.vad.backend = "energy"
    cfg.vision.use_lexicon = False

    # -- senza aree dichiarate non cambia niente ------------------------------
    r = DubPipeline(cfg, _tono(), clock=VirtualClock(), samplerate=48000)
    c.eq(len(r.lettori), 1, "senza aree dichiarate c'e' un lettore solo")
    c.eq(r.lettori[0][0].roi, cfg.vision.roi, "e legge la ROI di sempre")
    c.eq(r.lettori[0][1], "testo_audio", "e parla")

    # -- `self.reader` deve restare una vista, non una copia ------------------
    # Le verifiche di tutto il progetto sostituiscono `r.reader` con un lettore
    # finto: se fosse una copia, il finto verrebbe messo da una parte e ignorato
    # dall'altra, e la verifica proverebbe la catena vera credendo di provarne
    # una finta.
    finto = object()
    r.reader = finto  # type: ignore[assignment]
    c.ok(r.lettori[0][0] is finto, "assegnare `reader` cambia chi legge davvero")
    c.eq(r.lettori[0][1], "testo_audio", "e non perde il modo del pezzo")

    # -- due aree: due lettori, ognuno col suo diff e il suo tracker -----------
    due = replace(cfg.vision, aree=("0.2:0.85:0.6:0.10:testo_audio", "0.0:0.0:0.5:0.12:testo"))
    cfg2 = Config()
    cfg2.vision = due
    cfg2.tts.backend, cfg2.speaker.backend, cfg2.vad.backend = "tone", "none", "energy"
    cfg2.vision.use_lexicon = False
    r2 = DubPipeline(cfg2, _tono(), clock=VirtualClock(), samplerate=48000)
    c.eq(len(r2.lettori), 2, "due aree, due lettori")
    c.eq([m for _, m in r2.lettori], ["testo_audio", "testo"], "ognuno col suo modo")
    c.ok(
        r2.lettori[0][0].tracker is not r2.lettori[1][0].tracker,
        "e ognuno col suo tracker: due aree sono due flussi di sottotitoli",
    )
    c.ok(r2.lettori[0][0].diff is not r2.lettori[1][0].diff, "e col suo diff")

    # -- e la sovrapposizione arriva alla catena gia' tolta -------------------
    sovra = replace(cfg.vision, aree=("0.0:0.0:0.6:0.6", "0.4:0.4:0.6:0.6"))
    cfg3 = Config()
    cfg3.vision = sovra
    cfg3.tts.backend, cfg3.speaker.backend, cfg3.vad.backend = "tone", "none", "energy"
    r3 = DubPipeline(cfg3, _tono(), clock=VirtualClock(), samplerate=48000)
    rettangoli = [lettore.roi for lettore, _ in r3.lettori]
    c.ok(not si_sovrappongono(rettangoli), "i rettangoli che arrivano ai lettori sono disgiunti")
    c.eq(len(rettangoli), len(dividi(da_config(sovra))), "e sono i pezzi che la divisione ha prodotto")

    # -- la prova che conta: si legge da due posti, se ne pronuncia uno --------
    if not font_available():  # pragma: no cover - macchina senza font
        c.ok(False, "niente font di sistema: la prova sulle due aree non si puo' fare")
        return

    # Due scritte a due altezze diverse, e un OCR finto che **distingue da quale
    # area viene il ritaglio** dalla sua larghezza. Serve cosi': un finto che
    # restituisce sempre lo stesso testo non potrebbe dire se la battuta muta e'
    # quella giusta, e la verifica passerebbe anche invertendo i due modi.
    frame = empty_frame((1080, 1920))
    frame[80:160, 200:1400] = render_subtitles(
        [("Raggiungi il molo di Vespucci adesso", WHITE)], size=(80, 1200)
    )
    frame[940:1020, 600:1300] = render_subtitles([("Andiamo via", WHITE)], size=(80, 700))

    cfg4 = Config()
    cfg4.tts.backend, cfg4.speaker.backend, cfg4.vad.backend = "tone", "none", "energy"
    cfg4.vision.use_lexicon = False
    cfg4.vision.aree = ("0.30:0.86:0.40:0.09:testo_audio", "0.10:0.07:0.65:0.08:testo")
    cfg4.speaker.decide_after_ms = 0
    cfg4.speaker.max_wait_ms = 0
    orologio = VirtualClock()
    r4 = DubPipeline(cfg4, _tono(), ocr=_OcrPerArea(), clock=orologio, samplerate=48000)
    r4.start_live(warmup=False)

    dette: list = []
    for k in range(12):
        orologio.set(k * 0.1)
        dette.extend(r4.on_frame(np.zeros_like(frame) if k == 0 else frame))

    testi = {d.text for d in dette}
    aperte = r4.metrics.snapshot()["counters"].get("vision.subtitles.opened", 0)
    c.eq(aperte, 2, "si legge da tutte e due le aree")
    c.ok(
        any("Andiamo" in t for t in testi),
        f"la battuta dell'area che parla viene detta (dette: {sorted(testi)})",
    )
    c.ok(
        not any("molo" in t for t in testi),
        f"e quella di solo testo **non** viene pronunciata (dette: {sorted(testi)})",
    )
    c.eq(len(testi), 1, "una battuta detta su due lette")
    # **E lo sa sull'evento, non in una mappa per `id()`.** C'era
    # `len(r4._muti) == 1`, cioe' si verificava il *deposito* invece della
    # proprieta': quella mappa non sopravviveva a nessun `replace` dell'evento —
    # il testo che migliora, la revisione, l'etichetta — e una battuta muta che
    # migliorava tornava a parlare senza che questa riga potesse accorgersene.
    c.eq(
        [lettore.marca.modo for lettore, _ in r4.lettori],
        ["testo_audio", "testo"],
        "e la catena sa quale delle due tenere muta, e lo timbra sulla battuta",
    )


class _OcrPerArea:
    """Un OCR finto che risponde in base a **da dove** arriva il ritaglio.

    La larghezza del ritaglio dice l'area: quella in alto e' larga 0,65 dello
    schermo, quella in basso 0,40. Senza questo, un finto che dice sempre la
    stessa cosa lascerebbe passare la verifica anche a modi invertiti — cioe'
    non potrebbe fallire proprio nel caso per cui esiste.
    """

    name = "finto"

    def read(self, line):
        largo = line.shape[1] > 300
        return ("Raggiungi il molo di Vespucci adesso" if largo else "Andiamo via di qui"), 1.0


def _tono():
    from speak.base import make_tts

    return make_tts(type("T", (), {"backend": "tone", "samplerate": 22050})())


def test_memoria(c) -> None:
    """Il tetto alle battute tenute in memoria (domanda 92).

    **Le due meta' vanno verificate insieme**, se no il rimedio e' peggio del
    difetto: con il tetto la lista si accorcia, ma il conteggio deve restare
    vero e il cancello anti-doppioni deve continuare a scattare. Un tetto che
    zittisce il cancello farebbe ridire le battute — cioe' curerebbe dieci
    megabyte creando il difetto peggiore del prodotto.
    """
    from core.clock import VirtualClock
    from core.config import Config
    from core.pipeline import DubPipeline
    from core.types import LineClass, SubtitleEvent

    c.group("memoria")

    def catena(tetto: int):
        cfg = Config()
        cfg.tts.backend, cfg.speaker.backend, cfg.vad.backend = "tone", "none", "energy"
        cfg.vision.use_lexicon = False
        o = VirtualClock()
        r = DubPipeline(cfg, _tono(), clock=o, samplerate=48000)
        r.start_live(warmup=False)
        r.max_spoken = tetto
        return r, o, cfg

    # -- senza tetto si tengono tutte: e' quello che serve al banco -----------
    r, o, _ = catena(0)
    for i in range(50):
        o.set(i * 3.0)
        r._speak(SubtitleEvent(text=f"Battuta {i} diversa da tutte le altre.",
                               cls=LineClass.WHITE, t_on=i * 3.0))
    c.eq(len(r.spoken), 50, "senza tetto si tengono tutte (il banco scrive i sottotitoli)")
    c.eq(r.dette, 50, "e il conteggio le conta")

    # -- col tetto la lista si accorcia, il conteggio no ---------------------
    r, o, _ = catena(10)
    for i in range(50):
        o.set(i * 3.0)
        r._speak(SubtitleEvent(text=f"Battuta {i} diversa da tutte le altre.",
                               cls=LineClass.WHITE, t_on=i * 3.0))
    c.eq(len(r.spoken), 10, "col tetto in memoria restano solo le ultime")
    c.eq(r.dette, 50, "ma il conteggio resta vero — il rapporto non deve mentire")
    c.ok("49" in r.spoken[-1].text, "e quelle che restano sono le ultime, non le prime")

    # -- e il cancello anti-doppioni deve ancora scattare --------------------
    # Guarda indietro di **secondi**, non di righe: e' per questo che un tetto di
    # 400 righe non lo tocca. Verificato invece che con un tetto assurdo (1) e
    # una ripetizione immediata il cancello regga lo stesso.
    r, o, cfg = catena(1)
    o.set(0.0)
    testo = "Non me ne frega niente di quello che dici."
    r._speak(SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=0.0))
    o.set(1.0)
    doppione = SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=1.0)
    c.ok(r._gia_detta(doppione), "col tetto al minimo il cancello anti-doppioni scatta ancora")

    # -- e lo stesso tetto vale per i sottotitoli chiusi ---------------------
    # Il rimedio della domanda 92 si era fermato a `spoken`: `closed` cresceva
    # ancora, e dal vivo non la rilegge nessuno. Misurato: 3600 `SubtitleEvent`
    # sono +0,79 MB. Poco, ma senza limite — che era proprio la forma del
    # difetto, non la sua taglia.
    r, o, _ = catena(10)
    eventi = [SubtitleEvent(text=f"Sottotitolo {i}", cls=LineClass.WHITE, t_on=i * 1.0)
              for i in range(50)]
    r._chiudi(eventi)
    c.eq(len(r.closed), 10, "col tetto anche i sottotitoli chiusi si accorciano")
    c.ok(r.closed[-1].text.endswith("49"), "e restano gli ultimi, non i primi")
    r, o, _ = catena(0)
    r._chiudi(eventi)
    c.eq(len(r.closed), 50, "senza tetto si tengono tutti (il banco li usa)")


def test_sessione(c) -> None:
    """`ui.save_mix` viene letto davvero (domande 50, 91, 92).

    Era dichiarato in config, valeva `True`, e **non lo leggeva nessuno**: il
    quinto campo di questa forma dopo `max_ocr_hz`, `tts.device`,
    `background_mode` e `overlay.ritardo`. Chi lo metteva a `false` si ritrovava
    lo stesso 660 MB di RAM e 330 MB di WAV per mezz'ora di sessione.

    La verifica non e' che il campo esista: e' che **spegnendolo non si accumuli
    piu' niente**. Un campo che c'e' e non fa niente e' esattamente cio' che
    questo progetto ha pagato quattro volte.
    """
    import tempfile

    import numpy as np

    from tools.session import Session

    c.group("memoria")

    blocco = np.zeros((4800, 2), np.float32)
    with tempfile.TemporaryDirectory() as tmp:
        acceso = Session(root=tmp, samplerate=48000, salva_mix=True)
        for i in range(20):
            acceso.audio(blocco, i * 0.1)
        c.ok(len(acceso._blocks) == 20, "con save_mix acceso i blocchi si accumulano")

        spento = Session(root=tmp + "/b", samplerate=48000, salva_mix=False)
        for i in range(20):
            spento.audio(blocco, i * 0.1)
        c.eq(spento._blocks, [], "con save_mix spento non si accumula **niente**")
        c.eq(spento._n, 0, "e nemmeno il conteggio dei campioni")

        # **Ma la diagnosi deve restare**, ed era proprio quella che si perdeva.
        # Spegnendo il mix si usciva prima di prendere l'origine del tempo,
        # quindi `t0` restava `None` e ogni `t_wav` di `events.jsonl` usciva
        # nullo: `tools/reopen runs\<data> <secondo>` — il comando su cui e'
        # costruito tutto il metodo di questo progetto, «dimmi il secondo in cui
        # l'hai sentita» — non trovava piu' niente, perche' filtra su quel campo.
        c.ok(spento.t0 is not None,
             "e l'origine del tempo si prende lo stesso: senza, ogni t_wav e' nullo")
        c.ok(spento.t0 == acceso.t0, "ed e' la stessa che si prenderebbe registrando")

        # `Session` tiene `events.jsonl` aperto: senza chiuderle, la cartella
        # temporanea non si cancella su Windows e il gruppo esplode in chiusura
        # invece che su una verifica. Un guasto negli attrezzi si legge male
        # quanto uno nel codice.
        for s in (acceso, spento):
            try:
                s._lines.close()
            except Exception:
                pass


def test_ripresa(c) -> None:
    """Le impostazioni si ritrovano riaprendo (domande 15 e 16).

    **Il file c'era, e non lo leggeva nessuno.** `ultima.json` veniva scritto
    all'uscita della finestra Qt e mai riletto all'avvio: chi regolava per
    un'ora, chiudeva e riapriva, ritrovava i default con il file dei valori
    giusti sul disco accanto. La cura per il difetto piu' grave dell'elenco
    aveva la forma del difetto che questo progetto ha gia' pagato cinque volte.

    Le tre domande sono quelle che quella meta' mancante non avrebbe superato:
    **si rilegge?**, **un profilo chiesto vince ancora?**, **un file rotto fa
    ripartire dai default dicendolo?**
    """
    import tempfile
    from pathlib import Path

    from core import preferenze
    from core.config import Config

    c.group("memoria")

    vero = preferenze.ultima
    with tempfile.TemporaryDirectory() as tmp:
        finto = Path(tmp) / "ultima.json"
        preferenze.ultima = lambda: finto
        try:
            # -- niente da riprendere: si parte dai default, e si dice ---------
            cfg, da_dove = preferenze.riprendi(None, None)
            c.eq(da_dove, "default", "senza file salvato si parte dai default")

            # -- si rilegge davvero -------------------------------------------
            salvata = Config()
            salvata.vision.sat_max = 77
            salvata.mix.duck_db = -12.5
            salvata.save(finto)
            cfg, da_dove = preferenze.riprendi(None, None)
            c.eq(cfg.vision.sat_max, 77, "riaprendo si ritrova quello che si era regolato")
            c.close(cfg.mix.duck_db, -12.5, "anche i decimali, non solo gli interi")
            c.ok("ultima" in da_dove, f"e la finestra puo' dire da dove viene ({da_dove})")

            # -- ma `--set` resta sopra ---------------------------------------
            cfg, _ = preferenze.riprendi(None, ["vision.sat_max=33"])
            c.eq(cfg.vision.sat_max, 33, "--set vince sull'ultima configurazione")

            # -- e un profilo chiesto vince su tutto --------------------------
            cfg, da_dove = preferenze.riprendi("gtav", None)
            c.ok(cfg.vision.sat_max != 77,
                 "chi chiede un profilo vuole quello, non la sessione di ieri")
            c.eq(da_dove, "profilo gtav", "e lo dichiara")

            # -- un file rotto non impedisce di partire, e lo dice ------------
            finto.write_text("{ questo non e' json", encoding="utf-8")
            cfg, da_dove = preferenze.riprendi(None, None)
            c.eq(cfg.vision.sat_max, Config().vision.sat_max,
                 "un ultima.json illeggibile fa ripartire dai default")
            c.ok("non si e' potuto leggere" in da_dove,
                 "**dicendolo**: aprirsi diversi da ieri senza spiegare e' peggio")
        finally:
            preferenze.ultima = vero


def test_guasto_audio(c) -> None:
    """Le cuffie staccate a meta' partita (domande 39, 45, 87).

    La cura c'era ed era **meta'**: il ciclo protetto diceva il guasto e fermava
    i due thread, ma la sessione restava aperta col WAV mai scritto, **Avvia
    restava spento** — lo riaccende solo `ferma` — e lo stato usciva *verde*. Il
    messaggio invitava a premere un bottone disabilitato.

    Qui si prova il metodo vero su un finto: e' logica dell'interfaccia, non
    disegno, quindi non serve aprire una finestra.
    """
    import queue as _queue

    from tools.ui import App, colore_stato

    c.group("memoria")

    class FintoMotore:
        """I due cicli, ridotti a quello che la finestra gli chiede."""

        def __init__(self) -> None:
            self.threads = [object()]
            self.pipeline = object()

        @property
        def acceso(self) -> bool:
            return bool(self.threads)

    class Finta:
        def __init__(self) -> None:
            self.righe: list[str] = []
            self.motore = FintoMotore()
            self.coda: _queue.Queue = _queue.Queue()
            self.fermata = False

        def scrivi(self, testo, tag=None) -> None:
            self.righe.append(testo)

        def ferma(self) -> None:
            self.fermata = True
            self.motore.threads.clear()
            self.motore.pipeline = None
            self.coda.put(("stato", "fermo"))

    f = Finta()
    App._audio_guasto(f, "OSError: il device non c'e' piu'")
    c.ok(f.fermata, "il guasto dell'audio chiude la sessione come farebbe Ferma")
    c.ok(any("cuffie" in r for r in f.righe), "e dice cosa e' probabilmente successo")

    msg = []
    while not f.coda.empty():
        msg.append(f.coda.get_nowait())
    stati = [d for t, d in msg if t == "stato"]
    c.ok(stati and stati[-1] != "fermo",
         f"l'ultimo stato non e' «fermo»: sarebbe il colore sbagliato ({stati})")

    # E il colore e' la meta' che non si vedeva: la stringa di prima era verde.
    class _T:
        ROSSO, VERDE, TESTO_FIOCO = "rosso", "verde", "fioco"

    c.eq(colore_stato(stati[-1], _T), "rosso", "e il pallino diventa rosso")
    c.eq(colore_stato("audio interrotto", _T), "rosso",
         "anche scritto senza punto esclamativo: era verde, cioe' «va tutto bene»")
    c.eq(colore_stato("in corso", _T), "verde", "e una sessione viva resta verde")
    c.eq(colore_stato("fermo", _T), "fioco", "e una ferma resta fioca")

    # -- e il registro deve vedere i thread, che e' dove vive questo programma --
    # `sys.excepthook` non li copre: un'eccezione dentro il ciclo audio o quello
    # video finisce in `threading.excepthook` e, senza, il gestore «niente esce
    # di scena in silenzio» guardava l'unico posto dove non muore mai niente.
    import sys as _sys
    import threading as _th

    from core import registro

    visti: list[str] = []
    prima_sys, prima_th = _sys.excepthook, _th.excepthook
    try:
        # Il gestore incatena a quello di prima, che di serie stampa il
        # traceback: qui lo si zittisce **prima**, se no la suite sputa un
        # guasto finto in mezzo ai risultati veri. Che l'incatenamento avvenga
        # lo dice questa stessa riga: se non chiamasse il precedente, il finto
        # qui sotto non verrebbe mai chiamato.
        _th.excepthook = lambda dati: None
        registro.cattura_eccezioni(lambda tipo, valore, testo: visti.append(f"{tipo.__name__}"))

        def esplode() -> None:
            raise RuntimeError("il device non c'e' piu'")

        t = _th.Thread(target=esplode)
        t.start()
        t.join(timeout=5.0)
    finally:
        _sys.excepthook, _th.excepthook = prima_sys, prima_th
    c.eq(visti, ["RuntimeError"], "un thread che esplode arriva al registro, non al silenzio")


def test_uscita_audio(c) -> None:
    """`--output` sceglieva fra i **loopback**, che non sono uscite.

    Trovato provando il programma dal vivo: per non far rientrare il doppiaggio
    nella cattura serve suonare su un altro dispositivo, ed e' esattamente cio'
    che quell'opzione promette. Cercava il nome in `list_devices()[0]`, che sono
    i loopback WASAPI — dispositivi di **ingresso** con zero canali di uscita.
    Col nome giusto si otteneva `OSError -9998 Invalid number of channels`; col
    nome sbagliato, la predefinita **in silenzio**, cioe' il doppiaggio che
    suona da un'altra parte senza dirlo. Verificato a mano su questa macchina
    prima di correggere.

    Qui non si tocca l'hardware: si sostituisce l'elenco, perche' quello che
    era rotto e' la **scelta**, non WASAPI.
    """
    from capture import audio

    c.group("memoria")

    finte = [
        audio.Device(index=22, name="Uscita digitale (Realtek)", channels=2, samplerate=48000),
        audio.Device(index=25, name="Altoparlanti (Realtek)", channels=2, samplerate=48000),
    ]
    vero = audio.uscite
    audio.uscite = lambda: finte
    try:
        d = audio.find_output("altoparlanti")
        c.eq(d.index, 25, "si sceglie fra le uscite, per pezzo di nome")
        c.ok(not d.is_loopback, "e quella scelta non e' un loopback")
        try:
            audio.find_output("cuffie")
            c.ok(False, "un nome che non c'e' deve sollevare")
        except RuntimeError as guasto:
            c.ok("Uscita digitale" in str(guasto),
                 "sollevando **elencando** quelle che ci sono, non «non trovato»")
    finally:
        audio.uscite = vero


def test_solo_roi(c) -> None:
    """Catturare la sola fascia che si legge, e rimetterla al suo posto.

    Misurato su questa macchina a 2560x1440: il fotogramma intero costa
    **29,7 ms** con `mss`, la fascia col margine di serie **6,1 ms**. A 30 Hz il
    giro dura 33: la cattura intera se ne prendeva il 90%, e dal vivo il ciclo
    video girava a ~18 Hz.

    Le due domande che questo pezzo non deve sbagliare sono di **posizione**,
    non di velocita': i pixel finiscono dove finivano prima (se no il lettore
    legge il buio) e la fascia contiene tutte le aree dichiarate (se no le altre
    diventano nere senza che niente lo dica).
    """
    import numpy as np

    from capture.screen import Grab, ScreenSource, SoloRoi, regione_da_roi

    c.group("memoria")

    # -- il rettangolo da catturare -----------------------------------------
    r = regione_da_roi([(0.25, 0.80, 0.50, 0.05)], (2560, 1440), margine=0.0)
    c.eq(r, (640, 1152, 1920, 1224), "senza margine e' esattamente la ROI in pixel")

    r = regione_da_roi([(0.25, 0.80, 0.50, 0.05)], (2560, 1440), margine=0.06)
    c.eq(r, (640 - 86, 1152 - 86, 1920 + 86, 1224 + 86), "col margine si allarga di 0,06 H")

    # Due aree lontane: si prende l'unione, se no la seconda e' nera.
    r = regione_da_roi([(0.05, 0.10, 0.10, 0.05), (0.80, 0.90, 0.15, 0.05)],
                       (1000, 1000), margine=0.0)
    c.eq(r, (50, 100, 950, 950), "con piu' aree si prende l'unione, non la prima")

    # Attaccata al bordo non si esce dallo schermo.
    r = regione_da_roi([(0.9, 0.9, 0.1, 0.1)], (1000, 1000), margine=0.2)
    c.eq(r, (700, 700, 1000, 1000), "il margine non esce dallo schermo")

    # -- e i pixel finiscono dove stavano -----------------------------------
    class Finta(ScreenSource):
        name = "finta"

        def __init__(self, pezzo):
            self.pezzo = pezzo

        def grab(self):
            return Grab(frame=self.pezzo, t=1.0, fresh=True)

    regione = (100, 200, 300, 260)  # 200x60
    pezzo = np.full((60, 200, 3), 200, np.uint8)
    s = SoloRoi(Finta(pezzo), regione, (640, 480))
    g = s.grab()
    c.eq(g.frame.shape, (480, 640, 3), "il fotogramma consegnato e' grande come lo schermo")
    c.ok(g.frame[230, 200].tolist() == [200, 200, 200], "dentro la fascia ci sono i pixel veri")
    c.ok(g.frame[10, 10].tolist() == [0, 0, 0], "fuori e' nero, e chi guarda li' lo vede")
    c.ok(int(g.frame.sum()) == int(pezzo.sum()), "e non c'e' nient'altro: solo la fascia")

    # La stessa ROI ritagliata dal fotogramma ricostruito deve dare il pezzo.
    x, y = 100 / 640, 200 / 480
    w, h = 200 / 640, 60 / 480
    rit = g.frame[int(y * 480):int((y + h) * 480), int(x * 640):int((x + w) * 640)]
    c.ok(np.array_equal(rit, pezzo),
         "ritagliando con la ROI si riottiene esattamente cio' che si e' catturato")

    # Un fotogramma assente resta assente: non si inventa una tela nera.
    class Vuota(ScreenSource):
        name = "vuota"

        def grab(self):
            return Grab(frame=None, t=1.0, fresh=False)

    c.ok(not SoloRoi(Vuota(), regione, (640, 480)).grab().ok,
         "se il backend non da' niente non si consegna una tela nera")


def test_due_sessioni(c) -> None:
    """Due sessioni nello stesso secondo non si pestano i piedi (domanda 32).

    Avevano la **stessa cartella**, e ci scrivevano dentro tutte e due:
    `events.jsonl` aperto due volte, il WAV dell'una sopra quello dell'altra, e
    nessun errore perche' `mkdir(exist_ok=True)` non si lamenta. Due finestre
    aperte per confrontare due configurazioni e' proprio come si usa il
    programma.
    """
    import tempfile

    from tools.session import Session

    c.group("memoria")

    with tempfile.TemporaryDirectory() as tmp:
        sessioni = [Session(root=tmp, salva_mix=False) for _ in range(3)]
        try:
            cartelle = {s.dir for s in sessioni}
            c.eq(len(cartelle), 3, "tre sessioni nello stesso secondo, tre cartelle")
            nomi = sorted(s.dir.name for s in sessioni)
            c.ok(nomi[0][:19] == nomi[-1][:19],
                 "e il nome resta la data leggibile, col suffisso solo dove serve")
        finally:
            for s in sessioni:
                try:
                    s._lines.close()
                except Exception:
                    pass


def test_motore(c) -> None:
    """I due cicli fuori dalle finestre, e le due finestre che li chiamano.

    **Il difetto che questo gruppo esiste per prendere non e' un calcolo: e' una
    strada parallela.** I cicli vivevano dentro Tkinter; con un secondo
    front-end la via breve era copiarli, ed e' esattamente la forma che in questo
    progetto e' gia' costata due volte — il ricampionamento e il taglio del
    silenzio in coda, scritti nel ramo normale e mancanti in quello in
    streaming. La domanda che li avrebbe presi e' **«cosa fa la strada vecchia
    che questa non fa?»**, e qui si fa a una a una: ogni messaggio che il motore
    sa mandare deve essere gestito da **tutte e due** le finestre.

    Gira senza aprire niente: non serve ne' Tk ne' un server grafico, perche'
    quello che si prova sono regole, non disegno.
    """
    import re
    from pathlib import Path

    from core.motore import STATO_GUASTO, Motore, Opzioni, colore_stato, righe_guasto_audio

    c.group("motore")

    # -- le opzioni arrivano dalla riga di comando, quelle che ci sono --------
    class FintiArgs:
        loopback, output, block, backend, monitor = "vb-audio", None, 240, "mss", 2
        no_save = True

    o = Opzioni.da_args(FintiArgs())
    c.eq(o.loopback, "vb-audio", "le opzioni della riga di comando arrivano al motore")
    c.eq(o.block, 240, "anche i numeri, non solo le stringhe")
    c.eq(o.output, None, "e un campo assente resta al suo default invece di diventare None a mano")
    c.eq(Opzioni.da_args(object()).loopback, "voicemeeter",
         "un chiamante che non passa niente ottiene i default, non un guasto")

    # -- il protocollo: chi manda e chi ascolta ------------------------------
    # I `tipo` che il motore emette, letti dal suo sorgente: un tipo nuovo
    # aggiunto li' e dimenticato in una finestra sarebbe un messaggio buttato in
    # **silenzio**, che e' la forma di difetto peggiore qui dentro.
    radice = Path(__file__).resolve().parent.parent
    sorgente = (radice / "core" / "motore.py").read_text(encoding="utf-8")
    mandati = set(re.findall(r'self\.manda\(\s*"([a-z]+)"', sorgente))
    c.ok(len(mandati) >= 6, f"il motore manda piu' di un tipo di messaggio ({sorted(mandati)})")
    for nome, quale in (("tools/ui.py", "Tk"), ("tools/ui_qt.py", "Qt")):
        testo = (radice / nome).read_text(encoding="utf-8")
        gestiti = set(re.findall(r'tipo == "([a-z]+)"', testo))
        mancanti = sorted(mandati - gestiti)
        c.ok(not mancanti,
             f"la finestra {quale} gestisce tutti i messaggi del motore (mancano: {mancanti})")

    # -- fermare una catena mai accesa non deve esplodere --------------------
    # Succede davvero: si preme Ferma dopo un avvio fallito, o si chiude la
    # finestra prima di aver premuto Avvia. E deve **finire lo stesso**, se no i
    # bottoni restano come stavano — cioe' Avvia spento a catena morta, che e'
    # il difetto gia' pagato col guasto dell'audio.
    # **Con l'adattatore vero, non con uno scritto per la verifica.** La prima
    # stesura di questo gruppo usava un `lambda` suo e passava; le finestre
    # passavano `coda.put`, che prende `(oggetto, bloccante, timeout)` — quindi
    # `manda("nota", riga)` infilava il **solo tipo** usando la riga come flag di
    # blocco, e dall'altra parte `tipo, dato = "nota"` esplodeva lontanissimo da
    # dove stava lo sbaglio. La verifica provava una catena che nessuno faceva
    # girare: adesso monta `in_coda` e spacchetta **come fa il giro della coda**.
    import queue as _q

    from core.config import Config
    from core.motore import in_coda

    coda: _q.Queue = _q.Queue()
    m = Motore(Config(), Opzioni(no_save=True), in_coda(coda))
    c.ok(not m.acceso, "un motore appena costruito non e' acceso")
    m.ferma()
    grezzi = []
    while not coda.empty():
        grezzi.append(coda.get_nowait())
    c.ok(grezzi and all(isinstance(x, tuple) and len(x) == 2 for x in grezzi),
         "ogni messaggio arriva come coppia (tipo, dato): e' la riga che le due "
         "finestre spacchettano, e mutilata esplode lontano da dove sta lo sbaglio")
    tipi = [t for t, _ in grezzi]
    c.ok("finito" in tipi, "fermare una catena mai accesa manda comunque «finito»")
    stati = [d for t, d in grezzi if t == "stato"]
    c.eq(stati, ["fermo"], "e lo stato torna «fermo»")

    # -- il colore del pallino vale per tutte e due le finestre --------------
    # La regola era verificata sul tema Tk. La finestra Qt ha una tavolozza di
    # forma diversa, e riscrivere tre righe di adattamento e' esattamente il modo
    # in cui una regola sola diventa due.
    from tools.ui_qt import ComeTk
    from ui import qt_tema

    for tavolozza in (qt_tema.SCURA, qt_tema.CHIARA):
        vestita = ComeTk(tavolozza)
        c.eq(colore_stato(STATO_GUASTO, vestita), tavolozza.rosso,
             f"«{STATO_GUASTO}» accende il rosso anche in Qt ({tavolozza.nome})")
        # **Non «verde»: menta.** In Menta c'e' un colore acceso solo, e vuol
        # dire interazione e vita — il bottone che si preme, la spia quando la
        # catena gira. Il verde «sta funzionando» e il blu «questo si preme»
        # erano due colori per una cosa sola.
        c.eq(colore_stato("in corso  |  120 frame", vestita), tavolozza.accento,
             "una sessione viva prende l'accento")
        c.eq(colore_stato("fermo", vestita), tavolozza.testo_fioco, "e una ferma resta fioca")

    c.eq(len(righe_guasto_audio("OSError")), 2,
         "il guasto dell'audio dice cosa e' successo **e** cosa fare")
    c.ok(any("Avvia" in r for r in righe_guasto_audio("OSError")),
         "e indica il bottone da premere, che deve essere premibile")

    # -- la traduzione che fallisce lo deve **dire** -------------------------
    # Trovato dal vivo: con `locale` e argostranslate non installato, **zero
    # traduzioni su 19 battute** in quattro sessioni di fila. Il ripiego («si
    # tiene l'originale») e' giusto, ma parlava solo a `stderr` — che dietro una
    # finestra non lo legge nessuno e dentro un eseguibile non esiste. Un
    # ripiego che non si dichiara e' peggio di un errore.
    from translate.base import Traduzioni

    class Rotto:
        name = "finto-rotto"

        def traduci(self, testo, da, a):
            raise RuntimeError("argostranslate non installato")

    detti_t: list[str] = []
    tr = Traduzioni(Rotto(), da="it", a="en", dillo=detti_t.append)
    fuori = tr("Voglio vedere i soldi!")
    c.eq(fuori.testo, "Voglio vedere i soldi!",
         "fallendo si tiene l'originale: una battuta muta e' peggio di una in italiano")
    c.eq(len(detti_t), 1, "e la finestra lo viene a sapere")
    c.ok("argostranslate" in detti_t[0], f"col motivo vero, non «non ha funzionato» ({detti_t[0]})")
    for _ in range(5):
        tr("un'altra battuta ancora diversa %d" % _)
    c.eq(len(detti_t), 1,
         "detto una volta sola: trenta righe identiche seppelliscono tutto il resto")
    c.eq(tr.n_falliti, 6, "ma il conto va avanti, ed e' quello che finisce nella testata")


def test_overlay_base(c) -> None:
    """La geometria dell'overlay, senza aprire nessuna finestra.

    Da quando i front-end sono due, `OverlayBase` e' l'unico posto in cui si
    decide **dove** va il sottotitolo tradotto: Tk e Qt mettono i pixel e basta.
    Se questa parte fosse duplicata, le due finestre disegnerebbero in due punti
    diversi — ed e' proprio cosi' che sono nati i difetti di questo pezzo, con
    un secondo disegnatore che mostrava una cosa mentre il vivo ne faceva
    un'altra.
    """
    from ui.overlay import OverlayBase

    c.group("motore")

    class Finto(OverlayBase):
        """Un front-end che non disegna: conta soltanto cosa gli viene chiesto."""

        def __init__(self, *a, **k) -> None:
            self.fatti: list[str] = []
            super().__init__(*a, **k)

        def _dipingi(self, tela, geom) -> None:
            self.fatti.append("dipingi")

        def _apri(self) -> None:
            self.fatti.append("apri")

        def _chiudi(self) -> None:
            self.fatti.append("chiudi")

    o = Finto((0.25, 0.9, 0.5, 0.06), schermo=(2560, 1440))
    c.eq(o.geom, (1280, 86, 640, 1296), "senza finestra agganciata la ROI e' dello schermo")

    # **Agganciata a una finestra, la ROI e' della finestra.** Senza, l'overlay
    # cadrebbe sulla stessa frazione di *schermo* invece che di *finestra*: cioe'
    # quasi sempre altrove, e sarebbe la prima cosa che si rompe usando il
    # programma come si deve.
    o.aggancia((100, 50, 1280, 720))
    o.riposiziona((0.25, 0.9, 0.5, 0.06))
    c.eq(o.geom, (640, 43, 420, 698), "agganciata al gioco, la ROI e' della sua finestra")
    o.aggancia(None)
    o.riposiziona((0.25, 0.9, 0.5, 0.06))
    c.eq(o.geom, (1280, 86, 640, 1296), "e sganciandola si torna allo schermo")

    # -- non si disegna a caso ----------------------------------------------
    # Meglio nessun sottotitolo tradotto che un cartello piazzato dove il testo
    # non c'e': e' il difetto che tutte le misure di *quanto* non potevano
    # vedere, perche' lo sbaglio era *dove*.
    o.fatti.clear()
    o.mostra("ciao", pezzo=None, bande=None, rett=None)
    c.eq(o.fatti, [], "senza sapere dove sta il sottotitolo non si disegna niente")
    o.mostra("")
    c.eq(o.fatti, [], "e una battuta vuota non apre la finestra")

    # -- nascondere e' un'operazione sola, e non si ripete -------------------
    o._visibile = True
    o.sost = object()
    o.t_on = 12.5
    o.nascondi()
    c.eq(o.fatti, ["chiudi"], "nascondere chiude la finestra")
    c.eq(o.t_on, -1.0, "e dimentica quale sottotitolo stava traducendo")
    o.nascondi()
    c.eq(o.fatti, ["chiudi"], "nasconderla di nuovo non fa niente")

    c.ok("+" in o.geometria(), f"la geometria si legge nel log ({o.geometria()})")


def test_overlay_quando(c) -> None:
    """**Quando** si costruisce l'overlay, che non e' un dettaglio di tempi.

    Trovato dal vivo, con la suite verde: si costruiva alla nascita della
    finestra, leggendo `translate.enabled` com'era all'avvio del programma.
    Accendendo la traduzione dalle impostazioni — cioe' il modo dichiarato di
    accenderla — la catena traduceva e **nessuno disegnava**: nella sessione
    dell'utente 26 battute su 27 tradotte, `translate.overlay` a `true` nel
    `config.json` salvato, e zero sottotitoli a schermo. Nessun contatore lo
    diceva, perche' per la catena non era successo niente.

    La domanda che lo prende in un secondo e' quella gia' scritta in `CLAUDE.md`
    per le cure a meta': **cosa succede se questo valore cambia dopo?**
    """
    from core.config import Config
    from core.motore import Motore, Opzioni, in_coda

    c.group("motore")

    class FintoOverlay:
        vivi = 0

        def __init__(self) -> None:
            FintoOverlay.vivi += 1
            self.ancora = self.roi = None
            self.escluso = None

        def riposiziona(self, roi) -> None:
            self.roi = roi

        def aggancia(self, r) -> None:
            self.ancora = r

        def esclusione(self, attiva) -> None:
            self.escluso = attiva

        def distruggi(self) -> None:
            FintoOverlay.vivi -= 1

    import queue as _q

    cfg = Config()
    m = Motore(cfg, Opzioni(no_save=True), in_coda(_q.Queue()))

    # -- traduzione spenta: niente da disegnare ------------------------------
    cfg.translate.enabled = False
    m.prepara_overlay(FintoOverlay)
    c.eq(m.overlay, None, "senza traduzione non si costruisce nessun overlay")

    # -- accesa **dopo**, che e' il caso vero --------------------------------
    cfg.translate.enabled = True
    cfg.translate.overlay = True
    cfg.vision.roi = (0.2, 0.88, 0.6, 0.07)
    m.prepara_overlay(FintoOverlay)
    c.ok(m.overlay is not None,
         "accendendo la traduzione a finestra gia' aperta, l'overlay c'e' comunque")
    c.eq(m.overlay.roi, (0.2, 0.88, 0.6, 0.07), "e sta sull'area di adesso, non su quella di ieri")
    c.eq(m.overlay.escluso, True,
         "catturando lo schermo si nasconde alla cattura, se no l'OCR legge noi")

    # -- e si rifa' a ogni partenza, se no mostra la config di prima ---------
    primo = m.overlay
    m.prepara_overlay(FintoOverlay)
    c.ok(m.overlay is not primo,
         "ripartendo se ne fa uno nuovo: taglia, colore e raggio si leggono alla costruzione")
    c.eq(FintoOverlay.vivi, 1, "e il vecchio viene distrutto, non lasciato sullo schermo")

    # -- rispenta: sparisce ---------------------------------------------------
    cfg.translate.overlay = False
    m.prepara_overlay(FintoOverlay)
    c.eq(m.overlay, None, "spegnendo `translate.overlay` la finestra sparisce davvero")
    c.eq(FintoOverlay.vivi, 0, "senza lasciarne una in giro")


def test_coerenza(c) -> None:
    """**Una configurazione, quattro schede.** Le viste non possono divergere.

    Segnalato dall'utente: disegnata un'area in Preparazione, «Tutte le
    impostazioni» non la mostrava; cambiato il traduttore di la', la scheda
    Traduzione restava indietro. La causa e' una cura a meta' della
    riprogettazione: `_riallinea` elencava a mano `p_tecnologie` e `p_avanzate`,
    e i gruppi erano stati **rinominati**. `getattr(self, "p_tecnologie", None)`
    trasformava il nome morto in «niente da fare» invece che in un errore, cosi'
    tre schede su quattro non si aggiornavano piu' — con la suite verde, perche'
    nessuna verifica guardava due schede insieme.

    Due schede della stessa finestra che dichiarano due valori diversi sono
    peggio di una scheda sola: la seconda **sembra** dire la verita'.
    """
    import argparse
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from core.config import Config
    from tools.ui_qt import Finestra
    from ui.qt_controlli import leggi
    from ui.qt_pannello import Pannello

    c.group("coerenza")
    app = QApplication.instance() or QApplication([])

    args = argparse.Namespace(
        profile=None, set=None, loopback=None, output=None,
        block=None, backend=None, monitor=None, no_save=True,
    )
    f = Finestra(Config(), args)
    pannelli = f.findChildren(Pannello)
    c.ok(len(pannelli) >= 4, f"la finestra ha piu' viste sulla stessa config ({len(pannelli)})")

    # -- un campo cambiato in una scheda si vede in tutte --------------------
    p_tutte = f.p_avanzate
    p_tutte._widget["tts.speed"].imposta(1.4)
    p_tutte.applica(p_tutte._campi["tts.speed"])
    app.processEvents()
    c.close(f.cfg.tts.speed, 1.4, "il valore arriva in configurazione", 0.001)
    c.close(float(leggi(f.p_voce._widget["tts.speed"])), 1.4,
            "e la scheda Voce mostra quello, non quello di prima", 0.001)

    # E nell'altro verso, che e' quello che l'utente ha provato.
    f.p_traduzione._widget["translate.blur_strength"].imposta(30.0)
    f.p_traduzione.applica(f.p_traduzione._campi["translate.blur_strength"])
    app.processEvents()
    c.close(float(leggi(f.p_avanzate._widget["translate.blur_strength"])), 30.0,
            "e un cambio nella scheda Traduzione si vede in «Tutte le impostazioni»", 0.001)

    # -- l'area disegnata e' un cambio come gli altri ------------------------
    f._applica_roi((0.10, 0.50, 0.30, 0.05))
    app.processEvents()
    c.eq(tuple(leggi(f.p_avanzate._widget["vision.roi"])), (0.1, 0.5, 0.3, 0.05),
         "l'area tirata col mouse si vede anche nel pannello dei parametri")

    # -- «riporta ai default» avvisa, invece di cambiare di nascosto ---------
    # Senza, la scheda torna ai default e le altre continuano a mostrare i
    # valori vecchi: la stessa divergenza, da un'altra porta.
    visti: list[str] = []
    vecchio = f._campo_cambiato
    f._campo_cambiato = lambda campo, valore: (visti.append(campo.percorso),
                                               vecchio(campo, valore))[1]
    for p in pannelli:
        p.al_cambio = f._campo_cambiato
    f.p_voce.ripristina()
    app.processEvents()
    c.ok("tts.speed" in visti, f"riportando ai default, ogni campo toccato passa di li' ({len(visti)})")
    c.close(f.cfg.tts.speed, Config().tts.speed,
            "e il valore torna davvero al default", 0.001)
    c.close(float(leggi(f.p_avanzate._widget["tts.speed"])), Config().tts.speed,
            "anche nelle altre schede", 0.001)

    # -- l'aspetto del sottotitolo si cambia a sessione accesa ---------------
    # `translate.color` e compagni non sono in `FREDDI`: la finestra dichiara
    # che si cambiano a caldo e non ci mette il marchio «all'avvio». Ma
    # `OverlayBase.__init__` se li copiava dentro, quindi la sessione continuava
    # con quelli di partenza — una promessa scritta nella UI e non mantenuta.
    from core.schema import campi

    caldi = {k.percorso: k.caldo for k in campi(f.cfg)}
    for percorso in Finestra.STILE:
        c.ok(caldi.get(percorso, False),
             f"{percorso} e' dichiarato modificabile a caldo")

    # **E la traduzione, al contrario, e' fredda — con la prova del perche'.**
    # Undici campi dicevano «a caldo» ed erano letti nel costruttore della
    # catena: con la traduzione spenta `self.traduci` resta `None`, quindi
    # accenderla a sessione avviata non faceva niente, e la finestra — non
    # mettendoci il marchio «all'avvio» — prometteva il contrario. E' il
    # «l'applicazione del traduttore si bugga» segnalato dall'utente.
    #
    # La classificazione da sola sarebbe un'opinione: qui c'e' accanto il
    # comportamento che la giustifica. Se un giorno la catena imparasse a
    # cambiare traduttore da viva, questa riga diventa rossa e ricorda di
    # togliere il campo da `FREDDI` — che e' esattamente quando va tolto.
    from core.clock import VirtualClock
    from core.pipeline import DubPipeline
    from speak.base import ToneTts

    spenta = Config()
    spenta.translate.enabled = False
    catena = DubPipeline(spenta, ToneTts(), clock=VirtualClock(), samplerate=22050)
    spenta.translate.enabled = True
    c.eq(catena.traduci, None,
         "accendendo la traduzione a catena gia' costruita non succede niente…")
    for percorso in ("translate.enabled", "translate.source", "translate.target"):
        c.ok(not caldi.get(percorso, True), f"…e infatti {percorso} e' dichiarato freddo")

    class FintoOverlay:
        # **Un finto incompleto fa uscire un'eccezione dal giro della coda**, che
        # Qt ingoia e stampa: la verifica resta verde e nel mezzo dei risultati
        # compare un traceback che sembra un guasto vero. I tre campi sono quelli
        # che `ui.overlay.OverlayBase` dichiara e che la finestra legge a ogni
        # giro.
        _visibile, _vuoti, t_on = False, 0, 0.0

        def __init__(self) -> None:
            self.stile = {}

        def ristila(self, **kw) -> None:
            self.stile = kw

        def distruggi(self) -> None:
            """La finestra chiudendosi distrugge l'overlay: un finto che non sa
            morire fa esplodere la verifica alla riga dopo l'ultimo controllo."""

    finto = FintoOverlay()
    f.motore.overlay = finto
    f.cfg.translate.color = "#ff0000"
    f._campo_cambiato(next(k for k in campi(f.cfg) if k.percorso == "translate.color"), "#ff0000")
    c.eq(finto.stile.get("colore"), "#ff0000",
         "cambiando il colore, la finestra gia' aperta lo viene a sapere")
    c.eq(finto.stile.get("blur"), f.cfg.translate.blur_strength,
         "e riceve l'aspetto intero, non il solo campo toccato")

    # **Le due liste devono restare d'accordo.** `STILE` dice quali percorsi
    # fanno ristilare, `_stile()` dice cosa si manda: se una cresce e l'altra no,
    # il campo nuovo si cambia in config e non si vede — che e' il difetto di
    # partenza, ricreato.
    c.eq(len(Finestra.STILE), len(f._stile()),
         "i campi che fanno ristilare sono tanti quanti quelli mandati")
    from ui.overlay import OverlayBase
    import inspect

    accettati = set(inspect.signature(OverlayBase.ristila).parameters) - {"self"}
    c.eq(sorted(set(f._stile()) - accettati), [],
         "e l'overlay accetta tutte le chiavi che gli si mandano")

    f.close()


def test_manopole(c) -> None:
    """Il controllo giusto per ogni campo, e la rotellina che non tocca niente.

    Due difetti visti a schermo dall'utente, tutti e due invisibili al codice.

    **Il primo**: il controllo si sceglieva dal *tipo Python*, quindi tutto cio'
    che non era booleano o elenco dichiarato diventava un campo di testo. Un
    rettangolo (`0.204, 0.8843, 0.592, 0.07`), un guadagno in dB, una lingua e un
    colore: quattro cose che nessuno puo' digitare, tutte come testo libero.

    **Il secondo**: passando il mouse sopra un elenco mentre si scorre la pagina,
    Qt cambia il valore. Si scende di tre righe e si e' cambiato il motore di
    sintesi senza saperlo — e la finestra mostra il valore nuovo, quindi sembra
    una scelta dell'utente. Nessun contatore poteva dirlo.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit

    from core.config import Config
    from core.schema import Campo, limiti
    from ui.qt_controlli import (
        Cursore,
        Rettangolo,
        SceltaColore,
        SceltaFra,
        SceltaLingua,
        per_campo,
    )

    c.group("manopole")
    app = QApplication.instance() or QApplication([])

    def campo(percorso, valore, tipo, scelte=()):
        sez, _, nome = percorso.rpartition(".")
        return Campo(percorso=percorso, sezione=sez, nome=nome, valore=valore,
                     default=valore, tipo=tipo, aiuto="", caldo=True, scelte=scelte)

    # -- il controllo dice cosa e' lecito ------------------------------------
    atteso = [
        ("vision.roi", (0.2, 0.9, 0.6, 0.07), "tuple", (), Rettangolo,
         "un rettangolo si tira col mouse, non si digita"),
        ("translate.color", "", "str", (), SceltaColore,
         "un colore si prende da una tavolozza"),
        ("translate.target", "it", "str", (), SceltaLingua,
         "una lingua si sceglie da un elenco, non si scrive `it`"),
        ("mix.duck_db", -14.0, "float", (), Cursore,
         "un guadagno in dB ha un intervallo dichiarato: e' un cursore"),
        ("tts.backend", "piper", "str", ("piper", "kokoro"), SceltaFra,
         "un valore fra pochi e' un elenco"),
        ("tts.kokoro_weights", "modello.onnx", "str", (), QLineEdit,
         "e un nome di file resta testo, perche' testo e'"),
    ]
    for percorso, valore, tipo, scelte, classe, perche in atteso:
        w = per_campo(campo(percorso, valore, tipo, scelte), limiti=limiti)
        c.ok(isinstance(w, classe), f"{percorso}: {perche} ({type(w).__name__})")

    # **Tirandolo, un valore fuori scala non si puo' esprimere.** E' meglio che
    # rifiutarlo dopo: `mix.duck_db` positivo alzerebbe il gioco invece di
    # abbassarlo, ed era digitabile in una casella di testo.
    cur = per_campo(campo("mix.duck_db", -14.0, "float"), limiti=limiti)
    cur.slider.setValue(cur.passi)          # tirato tutto a destra
    c.ok(cur.valore() <= 0.0, f"tirato a fondo corsa resta nell'intervallo ({cur.valore()})")
    cur.slider.setValue(0)
    c.ok(cur.valore() >= -60.0, f"e dall'altra parte pure ({cur.valore()})")

    # **Ma un valore fuori scala gia' in config si mostra com'e'.** Pinzarlo qui
    # vorrebbe dire una finestra che mostra -14 dove c'e' scritto 999: la
    # configurazione in uso e quella a schermo diverse, che e' il difetto contro
    # cui esiste tutto il pannello.
    cur.imposta(999)
    c.eq(cur.valore(), 999.0, "un 999 arrivato da un profilo scritto a mano non si pinza di nascosto")
    c.ok(cur.fuori_scala() and "⚠" in cur.numero.text(), "ma si dichiara fuori scala")
    cur.imposta(-14.0)
    c.close(cur.valore(), -14.0, "e un valore buono resta quello che e'", 0.001)
    c.ok(not cur.fuori_scala(), "senza il marchio")

    # -- la rotellina scorre la pagina, non i valori --------------------------
    from ui.qt_pannello import Pannello

    cfg = Config()
    pannello = Pannello(cfg, solo=("tts.backend", "mix.duck_db"), cerca=False)
    combo = pannello._widget["tts.backend"].findChild(QComboBox)
    slider = pannello._widget["mix.duck_db"].slider

    def rotella(w, giri=-3):
        ev = QWheelEvent(QPointF(5, 5), w.mapToGlobal(QPoint(5, 5)),
                         QPoint(0, giri * 120), QPoint(0, giri * 120),
                         Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(w, ev)

    prima = (cfg.tts.backend, cfg.mix.duck_db)
    for _ in range(3):
        rotella(combo)
        rotella(slider)
    app.processEvents()
    c.eq((cfg.tts.backend, cfg.mix.duck_db), prima,
         "la rotellina sopra le impostazioni non cambia niente")

    # **Il caso nullo: col fuoco l'evento deve passare.** Senza questa meta', un
    # filtro che spegne la rotellina del tutto passerebbe la verifica di sopra, e
    # la verifica direbbe «protetto» di un controllo che non si puo' piu' usare.
    #
    # Si prova la **regola** e non la finestra: senza un gestore di finestre
    # `setFocus` non da' il fuoco (la finestra non e' attiva), quindi provarlo a
    # schermo qui direbbe sempre «bloccato» — una verifica che non puo' fallire.
    from ui.qt_controlli import _Rotella

    class ConFuoco:
        def hasFocus(self):
            return True

    class SenzaFuoco:
        def hasFocus(self):
            return False

        def parentWidget(self):
            return None

    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, -120), QPoint(0, -120),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    filtro = _Rotella()
    c.ok(not filtro.eventFilter(ConFuoco(), ev),
         "col fuoco la rotellina passa: chi ci ha cliccato sopra la vuole usare")
    c.ok(filtro.eventFilter(SenzaFuoco(), ev),
         "senza fuoco no: quella rotellina sta scorrendo la pagina")

    # -- un menu non puo' offrire cio' che il motore non sa fare --------------
    #
    # L'elenco delle forme del nome era ricopiato a mano dentro la finestra e si
    # era scollato da `vision/label.py` in tutti e due i versi: offriva tre forme
    # che li' non esistono — e sceglierne una fa **sollevare** il lettore appena
    # si preme Avvia, cioe' una voce del menu che rompe la sessione — e ne
    # nascondeva quattro vere. Nessuna verifica poteva accorgersene, perche' le
    # due liste erano d'accordo con se stesse.
    #
    # Questa e' la sola verifica che le tiene insieme, e oggi **fallisce** sulla
    # versione ricopiata: e' il caso nullo di se stessa.
    from dataclasses import replace as _replace

    from vision.label import FORME, LabelReader
    from ui.qt_controlli import ESEMPI_FORMA, SCELTE_A_MANO

    forme_menu, esempi = SCELTE_A_MANO["label.form"]
    c.eq(set(forme_menu), set(FORME),
         "il menu offre esattamente le forme che il lettore sa leggere")

    base = _replace(Config().label, enabled=True, regex="", names=(), require_names=False)
    for f in forme_menu:
        try:
            lettore = LabelReader(_replace(base, form=f))
            costruito = True
        except Exception as e:
            lettore, costruito = None, False
            c.ok(False, f"forma {f!r} offerta ma il lettore la rifiuta: {e}")
        if not costruito:
            continue
        # **E l'esempio non e' decorazione.** E' l'unica cosa che l'utente legge
        # per scegliere: se mostra una riga che quella forma non prende, sceglie
        # la forma sbagliata e il gioco «non scrive i nomi». La nota dopo i tre
        # spazi e' commento per l'occhio, non parte della riga.
        riga_esempio = esempi[f].split("   ")[0]
        et = lettore.dal_testo(riga_esempio)
        c.ok(et is not None and et.nome.lower().startswith("franklin")
             and et.testo.startswith("come va"),
             f"forma {f!r}: l'esempio «{riga_esempio}» si legge davvero ({et})")

    c.ok(all(f in ESEMPI_FORMA for f in FORME),
         "e ogni forma ha il suo esempio: senza, il menu mostra la chiave nuda")

    # -- la tabella dei personaggi -------------------------------------------
    #
    # `label.voices` e' «chi ha quale voce, deciso da te», e vince su ogni
    # assegnazione automatica: e' la funzione per cui uno accende i nomi. Il
    # pannello la mostrava **spenta** («non modificabile»), quindi si poteva
    # dichiarare solo aprendo a mano un file di profilo. Senza, la voce non e'
    # del personaggio: e' del turno in cui compare.
    from ui.qt_controlli import Tabella, leggi as _leggi, voci_del_pool

    cfg2 = Config()
    cfg2.label.enabled = True
    cfg2.label.voices = {"Franklin": "riccardo"}
    pann = Pannello(cfg2, solo=("label.voices",), cerca=False)
    tab = pann._widget["label.voices"]
    c.ok(isinstance(tab, Tabella), f"le voci dei personaggi sono una tabella ({type(tab).__name__})")
    c.eq(_leggi(tab), {"Franklin": "riccardo"}, "che parte da quello che c'e' in config")

    # **Le voci offerte sono quelle che la sessione avra' davvero.** Il pool e'
    # tagliato a `tts.pool_size`, e una voce fuori dal pool il motore la scarta
    # con un messaggio su stderr che dal vivo non legge nessuno: offrirne una in
    # piu' vorrebbe dire una scelta che non fa niente.
    offerte = [v for v, _ in voci_del_pool(cfg2)]
    from speak.pool import build_pool

    vere = [v.voice_id for v in build_pool(
        cfg2.tts.voices, cfg2.tts.pool_size, backend=cfg2.tts.backend, lingua="it")]
    c.eq(offerte, vere, "il menu offre esattamente le voci che il pool costruira'")

    # Andata e ritorno vero: aggiungere una riga deve arrivare **in config**,
    # perche' e' la config che la catena legge.
    tab._aggiungi("Lamar", vere[1])
    app.processEvents()
    c.eq(cfg2.label.voices, {"Franklin": vere[0], "Lamar": vere[1]},
         "aggiungere un personaggio arriva in configurazione")
    tab._togli(tab._righe[0][2])
    app.processEvents()
    c.eq(cfg2.label.voices, {"Lamar": vere[1]}, "e toglierlo pure")

    # **Il caso nullo: un valore che l'elenco non conosce non diventa un altro
    # valore.** `SceltaFra.imposta` non faceva niente su un valore sconosciuto,
    # quindi l'elenco restava sulla prima voce e `valore()` rispondeva quella —
    # e il pannello, che dopo ogni modifica rilegge e riscrive, la archiviava. Un
    # profilo con un motore tolto sarebbe diventato `piper` in silenzio.
    from ui.qt_controlli import SceltaFra

    sf = SceltaFra(("piper", "kokoro"))
    sf.imposta("qwen")
    c.eq(sf.valore(), "qwen", "un valore fuori elenco resta quello che e'")
    c.ok("⚠" in sf.combo.currentText(), "ma si vede che non e' fra quelli disponibili")
    sf.imposta("kokoro")
    c.eq(sf.valore(), "kokoro", "e tornando a uno valido l'intruso sparisce")
    c.eq(sf.combo.count(), 2, "senza lasciare voci finte nell'elenco")


def test_aree_muta(c) -> None:
    """Un'area `modo="testo"` viene **tradotta e disegnata**, non solo zittita.

    La verifica che c'era provava mezza frase. `test_aree_catena` chiedeva «la
    battuta di solo testo non viene pronunciata» — ed era vero — ma nessuno
    chiedeva l'altra meta', cioe' quella scritta nel commento di
    `core/pipeline.py`: «restano lette e chiuse, quindi tradotte e disegnate
    sopra il gioco». Non lo erano. Le battute mute venivano scartate **prima**
    di `_speak`, che e' il posto in cui avviene la traduzione e in cui nasce
    `SpokenLine` — l'unica cosa che arriva a chi disegna.

    Il difetto e' rimasto dietro una suite verde perche' una verifica che prova
    solo il ramo negativo non puo' fallire quando manca quello positivo.

    **Il traduttore finto deve cambiare davvero il testo**, se no «tradotto» e
    «lasciato com'era» sono la stessa stringa e la prova non puo' perdere.
    """
    import numpy as np

    from core.clock import VirtualClock
    from core.config import Config
    from core.pipeline import DubPipeline
    from tools.frames import WHITE, empty_frame, font_available, render_subtitles
    from translate.base import Traduzioni

    c.group("aree")

    if not font_available():  # pragma: no cover - macchina senza font
        c.ok(False, "niente font di sistema: la prova sull'area muta non si puo' fare")
        return

    class Finto:
        name = "finto"

        def __init__(self) -> None:
            self.visti: list[str] = []

        def traduci(self, testo, da, a):
            self.visti.append(testo)
            return "[EN] " + testo

    frame = empty_frame((1080, 1920))
    frame[80:160, 200:1400] = render_subtitles(
        [("CARTELLO raggiungi il molo", WHITE)], size=(80, 1200))
    frame[940:1020, 600:1300] = render_subtitles([("Andiamo via", WHITE)], size=(80, 700))

    cfg = Config()
    cfg.tts.backend, cfg.speaker.backend, cfg.vad.backend = "tone", "none", "energy"
    cfg.vision.use_lexicon = False
    cfg.vision.aree = ("0.30:0.86:0.40:0.09:testo_audio", "0.10:0.07:0.65:0.08:testo")
    cfg.speaker.decide_after_ms = cfg.speaker.max_wait_ms = 0
    cfg.translate.enabled = True

    orologio = VirtualClock()
    r = DubPipeline(cfg, _tono(), ocr=_OcrPerArea(), clock=orologio, samplerate=48000)
    finto = Finto()
    r.traduci = Traduzioni(finto, da="it", a="en")
    r.start_live(warmup=False)

    dette = []
    for k in range(14):
        orologio.set(k * 0.1)
        dette.extend(r.on_frame(np.zeros_like(frame) if k == 0 else frame))

    c.eq(len(dette), 2, f"escono tutte e due le battute, non solo quella che parla "
                        f"({[d.text for d in dette]})")
    c.eq(len(finto.visti), 2,
         f"e il traduttore le ha viste tutte e due ({finto.visti}): prima ne vedeva una")

    mute = [d for d in dette if d.muta]
    parlate = [d for d in dette if not d.muta]
    c.eq(len(mute), 1, "una sola e' muta")
    c.eq(len(parlate), 1, "e una sola parla")
    c.ok("molo" in mute[0].text, f"la muta e' quella del cartello ({mute[0].text!r})")
    c.ok(mute[0].text.startswith("[EN] "), "ed e' **tradotta**, che era la meta' mancante")
    c.ok(mute[0].text_original and not mute[0].text_original.startswith("[EN] "),
         "porta con se' l'originale, che e' cio' che va coperto a schermo")

    # **Senza `text_original` non arriva a chi disegna**: il giro della coda
    # manda il messaggio `overlay` solo per le righe che ne hanno uno. E' la
    # condizione vera, non una sua parafrasi.
    c.ok(bool(mute[0].text_original), "quindi il giro della coda la manderebbe all'overlay")

    # -- e resta muta davvero ------------------------------------------------
    c.eq(mute[0].voice_id, "", "la battuta muta non prende una voce dal pool")
    c.eq(mute[0].duration, 0.0, "e non produce audio")
    cont = r.metrics.snapshot()["counters"]
    c.eq(cont.get("mix.utterances", 0), 1,
         "una sola battuta arriva al mixer: la muta non occupa la voce")

    # -- la geometria e' quella della **sua** area ---------------------------
    # `boxes` e' in coordinate dell'area che ha letto la battuta. Chi disegna
    # prendeva sempre `cfg.vision.roi`: con due aree, la traduzione del cartello
    # sarebbe finita dentro la fascia del dialogo — nel posto sbagliato e senza
    # nessun errore.
    c.eq(tuple(round(v, 2) for v in mute[0].roi), (0.10, 0.07, 0.65, 0.08),
         f"la battuta muta sa da che rettangolo viene ({mute[0].roi})")
    c.eq(tuple(round(v, 2) for v in parlate[0].roi), (0.30, 0.86, 0.40, 0.09),
         f"e anche quella parlata ({parlate[0].roi})")


def test_area_sola(c) -> None:
    """Una sola area dichiarata deve essere letta **dove sta**.

    Il difetto piu' insidioso dei tre, perche' viveva dentro un'ottimizzazione
    che sembrava innocua: «con un pezzo solo non serve copiare la config», cioe'
    `cfg.vision if len(pezzi) == 1 else replace(...)`. Con **una** area
    dichiarata quel ramo buttava via il suo rettangolo e leggeva `vision.roi`.

    Perche' nessuno se n'era accorto: senza aree i due rettangoli coincidono
    (`da_config` ripiega gia' sulla ROI) e con due aree il ramo e' l'altro.
    Restava rotto solo il caso di mezzo — che e' precisamente quello che si
    ottiene aggiungendo la **prima** zona dalla finestra.

    E il sintomo era muto: la catena leggeva diligentemente il posto sbagliato.
    """
    from core.clock import VirtualClock
    from core.config import Config
    from core.pipeline import DubPipeline

    c.group("aree")

    def catena(aree):
        cfg = Config()
        cfg.tts.backend, cfg.speaker.backend, cfg.vad.backend = "tone", "none", "energy"
        cfg.vision.use_lexicon = False
        cfg.vision.aree = aree
        return DubPipeline(cfg, _tono(), clock=VirtualClock(), samplerate=48000)

    difetto = Config().vision.roi

    r = catena(())
    c.eq(r.lettori[0][0].roi, difetto, "senza aree si legge la ROI, come sempre")

    # Il caso che era rotto, e il **caso nullo che lo isola**: il rettangolo
    # dichiarato e' diverso dalla ROI di default, quindi «ha letto l'area» e «ha
    # letto la ROI» non possono dare la stessa risposta.
    una = (0.05, 0.40, 0.90, 0.10)
    c.ok(una != difetto, "il rettangolo di prova e' diverso dalla ROI: se no la "
                         "verifica non potrebbe distinguere i due casi")
    r = catena((f"{una[0]}:{una[1]}:{una[2]}:{una[3]}:testo",))
    c.eq(len(r.lettori), 1, "una area, un lettore")
    c.eq(tuple(round(v, 4) for v in r.lettori[0][0].roi), una,
         f"e legge **il suo** rettangolo, non la ROI ({r.lettori[0][0].roi})")
    c.eq(r.lettori[0][1], "testo", "col suo modo")

    r = catena(("0.0:0.0:1.0:0.5:testo", "0.0:0.5:1.0:0.5:testo_audio"))
    c.eq([tuple(lettore.roi) for lettore, _ in r.lettori],
         [(0.0, 0.0, 1.0, 0.5), (0.0, 0.5, 1.0, 0.5)],
         "e con due aree ognuno resta al suo posto")

    # -- e il prezzo che la prima cura si era portata dietro ------------------
    # Quella stesura dava a ogni lettore una **copia** di `cfg.vision`. Il
    # rettangolo tornava giusto e trentuno campi caldi smettevano di arrivare:
    # cambiando «Ignora i sottotitoli colorati» a sessione accesa, il pannello
    # mostrava il valore nuovo e la catena continuava con quello vecchio — il
    # difetto contro cui quel pannello esiste, ricreato dalla sua cura.
    from core.schema import campi as _campi

    prova = Config()
    prova.tts.backend, prova.speaker.backend, prova.vad.backend = "tone", "none", "energy"
    prova.vision.use_lexicon = False
    prova.vision.aree = ("0.05:0.40:0.90:0.10:testo", "0.05:0.60:0.90:0.10:testo_audio")
    viva = DubPipeline(prova, _tono(), clock=VirtualClock(), samplerate=48000)
    caldi = sorted(x.percorso for x in _campi(prova)
                   if x.percorso.startswith("vision.") and x.caldo)
    c.ok(len(caldi) > 20, f"«vision» ha {len(caldi)} campi dichiarati caldi")
    prova.vision.sat_max = 99
    prova.vision.exclude_colored = not prova.vision.exclude_colored
    c.ok(all(lettore.cfg is prova.vision for lettore, _ in viva.lettori),
         "ogni lettore tiene **l'oggetto** di config, non una copia")
    c.eq([lettore.cfg.sat_max for lettore, _ in viva.lettori], [99, 99],
         "quindi una manopola calda arriva a tutti i lettori a sessione accesa")
    c.eq([tuple(lettore.roi) for lettore, _ in viva.lettori],
         [(0.05, 0.40, 0.90, 0.10), (0.05, 0.60, 0.90, 0.10)],
         "senza che nessuno perda il proprio rettangolo")


def test_area_troppo_grande(c) -> None:
    """Un'area grande non e' meno precisa: e' **muta**, e adesso lo dice.

    La misura che sta dietro la soglia: il cancello che decide se rileggere lo
    schermo guarda la **frazione** di pixel cambiati contro `diff_threshold =
    0,004`, e quella frazione ha l'area al denominatore. Lo stesso sottotitolo,
    con l'area che cresce attorno: 0,0225 a 0,08 di altezza, 0,0081 a 0,30,
    0,0043 a 0,70, **0,0032 a schermo intero** — cioe' sotto la soglia. Misurato
    a schermo intero: 14 fotogrammi in, 14 fermati, zero chiamate all'OCR.

    Il difetto non lascia tracce: per la catena quei fotogrammi non contenevano
    niente di nuovo, e nessun contatore distingue «non c'era testo» da «non l'ho
    guardato».
    """
    from vision.aree import ALTEZZA_MASSIMA, troppo_grande

    c.group("aree")

    c.eq(troppo_grande((0.15, 0.72, 0.70, 0.22)), "",
         "una fascia da sottotitoli non dice niente")
    c.eq(troppo_grande((0.0, 0.0, 1.0, ALTEZZA_MASSIMA)), "",
         "e nemmeno una esattamente al limite")
    grande = troppo_grande((0.0, 0.0, 1.0, 1.0))
    c.ok(grande.startswith("!"), "tutto lo schermo invece avvisa")
    c.ok("zero letture" in grande,
         "e dice il numero misurato, non «potrebbe funzionare peggio»")

    # **E l'avviso arriva alla finestra**, che e' l'unico posto dove qualcuno lo
    # legge: scritto in una funzione e mai chiamato sarebbe l'ottavo campo
    # dichiarato e mai letto di questo progetto.
    from core.clock import VirtualClock
    from core.config import Config
    from core.pipeline import DubPipeline

    detti: list[str] = []
    cfg = Config()
    cfg.tts.backend, cfg.speaker.backend, cfg.vad.backend = "tone", "none", "energy"
    cfg.vision.use_lexicon = False
    cfg.vision.aree = ("0.0:0.0:1.0:1.0:testo",)
    DubPipeline(cfg, _tono(), clock=VirtualClock(), samplerate=48000, dillo=detti.append)
    c.ok(any("legge poco o niente" in d for d in detti),
         f"la catena lo dice all'avvio, dove il log lo raccoglie ({detti})")
