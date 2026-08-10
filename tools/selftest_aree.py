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
