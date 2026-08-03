"""Ricava dal video i numeri che il codice non deve indovinare.

    python -m tools.calibrate gameplay.mp4
    python -m tools.calibrate gameplay.mp4 --frames 600 --write profiles/gtav.json

I default in `core/config.py` sono punti di partenza dichiarati. Su una
registrazione vera si sono rivelati sbagliati in un modo istruttivo: la ROI di
partenza inquadrava il tappeto invece dei sottotitoli, e con `contrast_min = 30`
il **19% della ROI** passava per testo, cioe' la texture della scena finiva
dentro le righe, le allargava a tutta la ROI e da li' nell'OCR — che costa in
proporzione alla larghezza. Ne uscivano code di spazzatura, righe grigie fatte
di un glifo solo, e 223 ms mediani di riconoscimento contro i 15 misurati sul
sintetico. Un'unica causa, tre sintomi che sembravano tre problemi.

Cosa misura, e in che ordine (ognuno serve al successivo):

1. **dove sta il testo** — profilo di righe e colonne su una maschera severa
   (chiaro, acromatico, che stacca dal proprio intorno). Serve una maschera
   severa e non quella di lavoro perche' la domanda e' "dove", e una maschera
   permissiva risponde "dappertutto": sul frame intero il profilo esce piatto e
   la misura non puo' esprimere la risposta;
2. **quanto e' chiaro il testo, e quanto stacca** — istogrammi dentro la ROI
   trovata, per ricavare le soglie di lavoro;
3. **esiste il grigio** — la grammatica dei sottotitoli dice che una riga piu'
   spenta e' un secondo speaker. E' un'ipotesi, e va verificata prima di
   costruirci sopra: se i due gruppi non si separano, il segnale non esiste.

Il punto 3 non si chiude da solo. Un secondo gruppo di luminanza puo' essere un
secondo speaker o puo' essere il cordolo della strada dentro la ROI, e la
differenza si vede guardando. Per questo lo strumento **salva i ritagli
candidati**: la sua risposta e' "guarda queste dodici immagini", non un verdetto
inventato.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.sources import probe  # noqa: E402

# Maschera severa: serve solo a *localizzare* il testo, non a leggerlo. Ogni
# soglia e' scelta per stare largamente dalla parte del sicuro — meglio perdere
# qualche glifo che accettare un pixel di scena, perche' qui un falso positivo
# sposta la ROI e un falso negativo no.
SEVERE_LUMA = 200
SEVERE_SAT = 40
SEVERE_DELTA = 60
BLUR = 63


@dataclass
class Evidence:
    """Cosa ha visto la calibrazione. Va nel profilo insieme ai numeri, perche'
    un valore senza la misura che lo ha prodotto e' di nuovo un valore
    indovinato — solo con piu' cifre decimali."""

    frames_sampled: int = 0
    frames_with_text: int = 0
    row_band: tuple[float, float] = (0.0, 0.0)
    col_band: tuple[float, float] = (0.0, 0.0)
    body_luma: dict = field(default_factory=dict)
    peak_sat: dict = field(default_factory=dict)
    contrast: dict = field(default_factory=dict)
    grey_candidates: int = 0
    lines_total: int = 0
    multi_line_frames: int = 0

    def to_dict(self) -> dict:
        return {
            "frames_sampled": self.frames_sampled,
            "frames_with_text": self.frames_with_text,
            "row_band": list(self.row_band),
            "col_band": list(self.col_band),
            "body_luma": self.body_luma,
            "peak_sat": self.peak_sat,
            "contrast": self.contrast,
            "grey_candidates": self.grey_candidates,
            "lines_total": self.lines_total,
            "multi_line_frames": self.multi_line_frames,
        }


def _percentiles(values, ps=(1, 5, 25, 50, 75, 95, 99)) -> dict:
    if not len(values):
        return {}
    a = np.asarray(values, dtype=np.float64)
    return {f"p{p}": round(float(np.percentile(a, p)), 2) for p in ps}


def severe_mask(roi: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(maschera severa, luminanza, saturazione, stacco dal fondo locale)."""
    import cv2

    rgb = roi[:, :, :3].astype(np.float32)
    luma = rgb.mean(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    delta = luma - cv2.blur(luma, (BLUR, BLUR))
    mask = (luma > SEVERE_LUMA) & (sat < SEVERE_SAT) & (delta > SEVERE_DELTA)
    return mask, luma, sat, delta


def sample(video: str, n: int, start: float, end: float | None):
    """`n` frame equidistanti fra `start` e `end`. Restituisce (t, frame)."""
    import cv2

    info = probe(video)
    t0 = max(0.0, start)
    t1 = end if end is not None else info.duration
    cap = cv2.VideoCapture(str(info.path))
    try:
        for i in range(n):
            t = t0 + (t1 - t0) * (i + 0.5) / n
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * info.src_fps)))
            ok, frame = cap.read()
            if ok:
                yield t, frame
    finally:
        cap.release()


# -- 1. dove sta il testo --------------------------------------------------


def find_roi(frames, ev: Evidence, verbose: bool):
    """ROI dal profilo di testo, cercando **solo nella fascia bassa**.

    La restrizione non e' pigrizia: sopra ci sono la minimappa, i nomi delle
    missioni e i titoli di coda, tutti bianchi e acromatici quanto un
    sottotitolo. Nessuna soglia di colore li distingue — solo la posizione.
    """
    rows = cols = None
    seen = 0
    for _, frame in frames():
        h, w = frame.shape[:2]
        strip0 = int(h * 0.70)
        mask, *_ = severe_mask(frame[strip0:])
        if rows is None:
            rows = np.zeros(h - strip0, np.int64)
            cols = np.zeros(w, np.int64)
        rows += mask.sum(axis=1)
        cols += mask.sum(axis=0)
        seen += 1
    if not seen or rows is None:
        raise RuntimeError("nessun frame leggibile")
    ev.frames_sampled = seen

    # Banda di righe: il fondo e' il rumore di scena, il picco e' il testo. Si
    # tiene il tratto contiguo attorno al massimo che sta sopra un decimo
    # dell'escursione — abbastanza basso da prendere la seconda riga di una
    # battuta andata a capo, che e' molto meno frequente della prima.
    prof = rows / seen
    floor = float(np.median(prof))
    peak = float(prof.max())
    if peak <= floor * 1.5:
        raise RuntimeError(
            "nessun picco di testo nella fascia bassa: la maschera severa non "
            "trova sottotitoli. Video sbagliato, o sottotitoli spenti nel gioco."
        )
    limit = floor + 0.05 * (peak - floor)
    top = bottom = int(np.argmax(prof))
    while top > 0 and prof[top - 1] >= limit:
        top -= 1
    while bottom < len(prof) - 1 and prof[bottom + 1] >= limit:
        bottom += 1

    h_full = int(round((len(prof)) / (1 - 0.70)))
    strip0 = h_full - len(prof)
    # **Due** altezze di riga di margine sopra la banda trovata. Il picco del
    # profilo e' la prima riga, quella che c'e' sempre; la seconda e la terza
    # riga di una battuta andata a capo sono molto piu' rare e nel profilo
    # medio non superano la soglia. Tagliarle sarebbe un errore silenzioso:
    # niente errore, solo meta' delle frasi lunghe.
    # **E due anche sotto, che prima erano zero virgola due.** Il margine era
    # asimmetrico e solo la meta' di sopra era spiegata. Sotto restavano cinque
    # pixel su una riga da quindici: abbastanza per la banda misurata, non per le
    # code di `g`, `q` e `p`, e non per le battute che il gioco disegna piu' in
    # basso della media campionata — l'obiettivo di missione, per dirne una.
    #
    # Misurato sulla registrazione, ROI da 52 px contro 76: le bande che toccano
    # il bordo basso passano dal **78,8% all'1,8%**, e due battute su
    # quarantatre' smettono di raccogliere caratteri inventati in coda —
    # `'Esteban Jimenez.7'` -> `'Esteban Jimenez.'` e `'Vespucci Beach.!'` ->
    # `'Vespucci Beach.'`. Il primo e' l'artefatto che `CLAUDE.md` cita per nome
    # come causa dello scarto fra le passate archiviate e HEAD.
    #
    # **Non e' un guadagno netto e va detto**: una terza battuta ci guadagna un
    # `.1` che prima non aveva. Due corrette, una peggiorata, trentotto su
    # quarantatre' identiche — piu' il giudizio dell'occhio sui ritagli
    # affiancati, che e' quello che ha deciso.
    line_h = max(1, bottom - top + 1)
    y0 = max(0, strip0 + top - 2 * line_h)
    y1 = min(h_full, strip0 + bottom + 2 * line_h)
    ev.row_band = (round((strip0 + top) / h_full, 4), round((strip0 + bottom) / h_full, 4))

    # Colonne: il blocco di sottotitolo e' centrato, la minimappa e il nome del
    # quartiere no. Si prende quindi il gruppo di colonne che contiene il
    # centro, frame per frame, e se ne guardano gli estremi.
    lefts, rights = [], []
    w_full = len(cols)
    for _, frame in frames():
        mask, *_ = severe_mask(frame[y0:y1])
        active = mask.sum(axis=0) >= 1
        if not active[w_full // 2 - 60 : w_full // 2 + 60].any():
            continue
        dil = np.convolve(active, np.ones(41, bool), mode="same") > 0
        c = w_full // 2
        if not dil[c]:
            continue
        lo, hi = c, c
        while lo > 0 and dil[lo - 1]:
            lo -= 1
        while hi < w_full - 1 and dil[hi + 1]:
            hi += 1
        if lo == 0 or hi == w_full - 1:
            continue  # il gruppo tocca il bordo: si e' saldato alla HUD
        lefts.append(lo / w_full)
        rights.append(hi / w_full)

    if len(lefts) < 5:
        raise RuntimeError("troppo pochi frame con un blocco di testo centrato")
    ev.frames_with_text = len(lefts)
    left = float(np.percentile(lefts, 2))
    right = float(np.percentile(rights, 98))
    ev.col_band = (round(left, 4), round(right, 4))
    # Il blocco e' centrato: si rende simmetrico attorno a 0,5 prendendo il lato
    # piu' largo. Una ROI asimmetrica taglierebbe le battute lunghe da un lato
    # solo, e sarebbe un errore difficile da vedere nei log.
    half = max(0.5 - left, right - 0.5) + 0.01
    x0 = max(0.0, 0.5 - half)
    x1 = min(1.0, 0.5 + half)

    roi = (round(x0, 4), round(y0 / h_full, 4), round(x1 - x0, 4), round((y1 - y0) / h_full, 4))
    if verbose:
        print(f"  profilo righe: fondo {floor:.0f}, picco {peak:.0f} px/frame")
        print(f"  banda di testo: {ev.row_band[0]:.3f} .. {ev.row_band[1]:.3f} dell'altezza")
        print(f"  estremi del blocco centrato: {left:.3f} .. {right:.3f} della larghezza")
    return roi


# -- 2. le soglie ----------------------------------------------------------


def find_thresholds(frames, roi, ev: Evidence, verbose: bool) -> dict:
    """Soglie di lavoro dagli istogrammi dentro la ROI trovata.

    **L'ancora non puo' usare il contrasto**, e non basta nemmeno il colore.
    Due tentativi, due modi diversi di sbagliare:

    1. ancorare il testo con la maschera severa — che pretende uno stacco dal
       fondo maggiore di 60 — e poi misurarne lo stacco. Il primo percentile
       usciva 60,15: la soglia stessa. La misura era vincolata dalla propria
       definizione e non poteva esprimere altro numero;
    2. ancorarlo su "quasi bianco e acromatico". Stacco al primo percentile:
       **-2,3**. Dentro la ROI ci finiscono muri chiari e carrozzerie bianche,
       che sono bianchi e acromatici quanto un glifo e non staccano da niente.

    Quello che distingue davvero un glifo dal resto non e' quanto e' chiaro, e'
    che e' **sottile**. Il top-hat (originale meno la sua apertura morfologica)
    tiene solo le strutture chiare piu' strette del proprio elemento: un tratto
    di lettera resta, un muro sparisce. Ed e' un operatore diverso da quello
    della pipeline — che sottrae una media, non un'apertura — quindi misurare
    l'uno dopo aver selezionato con l'altro e' una misura, non un'eco.
    """
    import cv2

    from vision.roi import crop

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    bodies, peaks, floors = [], [], []
    for _, frame in frames():
        r = crop(frame, roi)
        rgb = r[:, :, :3].astype(np.float32)
        luma = rgb.mean(axis=2)
        sat = rgb.max(axis=2) - rgb.min(axis=2)
        delta = luma - cv2.blur(luma, (BLUR, BLUR))
        tophat = cv2.morphologyEx(luma, cv2.MORPH_TOPHAT, kernel)

        anchor = (luma > 200) & (sat < 30) & (tophat > 50)
        if anchor.sum() < 150:
            continue
        # Il corpo del glifo si misura sull'ancora dilatata, cosi' entrano i
        # bordi antialiasati; la saturazione **no**, perche' la dilatazione
        # pesca anche il pixel di scena appena fuori dal glifo e sarebbe quello
        # a decidere `sat_max`.
        core = cv2.dilate(anchor.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        bodies.append(float(np.percentile(luma[core], 90)))
        peaks.append(float(np.percentile(sat[anchor], 98)))
        # p5 e non p1: anche un'ancora buona raccoglie qualche pixel di scena, e
        # il primo percentile e' proprio dove quelli si accumulano. Perdere il
        # 5% dei pixel di glifo non toglie nemmeno una lettera — la maschera
        # cerca il corpo di una riga, non ogni singolo pixel.
        floors.append(float(np.percentile(delta[anchor], 5)))

    if len(bodies) < 5:
        raise RuntimeError("troppo pochi frame con testo dentro la ROI")
    ev.body_luma = _percentiles(bodies)
    ev.peak_sat = _percentiles(peaks)
    ev.contrast = _percentiles(floors)

    body = np.array(bodies)
    # `white_min_luma` separa bianco e grigio: si mette sotto la coda bassa del
    # bianco misurato, non a meta' strada verso un grigio la cui esistenza e'
    # una domanda a parte (punto 3).
    white_min = int(max(190, np.percentile(body, 2) - 15))
    # `grey_min_luma` e' il cancello "questo non e' nemmeno testo", non una
    # soglia di classe: va sotto qualunque corpo di glifo plausibile.
    grey_min = 110
    sat_max = int(min(60, max(30, np.percentile(peaks, 99) + 8)))
    # Il contrasto e' il criterio forte. La soglia si prende sotto la coda
    # bassa del testo vero, ma con una statistica **robusta**: prendere il
    # minimo fra i frame significa lasciar decidere al frame peggiore, e ne
    # basta uno con un muro bianco dentro la ROI per portare la soglia a zero.
    # Misurato: minimo fra i frame -21, decimo percentile +40.
    contrast_min = float(max(20.0, np.percentile(floors, 10) * 0.8))

    if verbose:
        print(f"  luminanza del corpo per frame: {ev.body_luma}")
        print(f"  saturazione di picco:          {ev.peak_sat}")
        print(
            f"  stacco sul testo vero (p5 per frame): {ev.contrast}  "
            f"(min fra i frame {min(floors):.1f})"
        )
    return {
        "white_min_luma": white_min,
        "grey_min_luma": grey_min,
        "sat_max": sat_max,
        "contrast_min": round(contrast_min, 1),
    }


# -- 3. il grigio esiste? --------------------------------------------------


def grey_check(frames, roi, thr: dict, ev: Evidence, out_dir: Path, verbose: bool):
    """Cerca frame con due righe di luminanza diversa, e ne salva i ritagli.

    Non emette un verdetto. Un secondo gruppo di luminanza dentro la ROI puo'
    essere un secondo speaker oppure il cordolo di un marciapiede, e nessuna
    statistica distingue le due cose: le immagini si'.
    """
    import cv2

    from vision.roi import crop

    candidates = []
    for t, frame in frames():
        r = crop(frame, roi)
        _, luma, sat, delta = severe_mask(r)
        mask = (
            (luma > thr["grey_min_luma"])
            & (delta > thr["contrast_min"])
            & (sat < thr["sat_max"])
        )
        if mask.sum() < 200:
            continue

        prof = mask.sum(axis=1)
        active = prof >= max(2, int(mask.shape[1] * 0.02))
        bands, s = [], None
        for i, on in enumerate(active):
            if on and s is None:
                s = i
            elif not on and s is not None:
                if i - s >= 10:
                    bands.append((s, i - 1))
                s = None
        if s is not None and len(active) - s >= 10:
            bands.append((s, len(active) - 1))

        found = []
        for top, bot in bands:
            bm = mask[top : bot + 1]
            if bm.sum() < 300:
                continue
            cols = np.where(bm.any(axis=0))[0]
            if (cols[-1] - cols[0]) / mask.shape[1] < 0.08:
                continue
            found.append(float(np.percentile(luma[top : bot + 1][bm], 90)))
        ev.lines_total += len(found)
        if len(found) >= 2:
            ev.multi_line_frames += 1
            spread = max(found) - min(found)
            if spread > 25:
                candidates.append((spread, t, max(found), min(found), r))

    ev.grey_candidates = len(candidates)
    if not candidates:
        if verbose:
            print("  nessun frame con due righe di luminanza diversa.")
        return

    candidates.sort(key=lambda c: c[0], reverse=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    for spread, t, hi, lo, r in candidates[:12]:
        cv2.imwrite(str(out_dir / f"grey_t{t:08.2f}_d{spread:03.0f}.png"), r)
    if verbose:
        print(f"  {len(candidates)} frame con due righe di luminanza diversa; i 12 piu' netti:")
        for spread, t, hi, lo, _ in candidates[:12]:
            print(f"    t={t:8.2f}s  chiara {hi:5.1f}  spenta {lo:5.1f}  stacco {spread:5.1f}")
        print(f"  ritagli in {out_dir} — vanno GUARDATI prima di credere al grigio.")


# -- riga di comando -------------------------------------------------------


def _live_frames(args, verbose: bool):
    """Cattura una volta dallo schermo e restituisce i frame, riusabili.

    I frame si tengono in memoria e **non** si scrivono su disco: la
    calibrazione li rilegge tre volte (ROI, soglie, grigio) e ricatturare
    darebbe tre scene diverse, cioe' tre risposte a tre domande diverse. La
    stessa cosa da file viene gratis, perche' il file resta fermo.
    """
    import time

    from capture.screen import make_screen

    screen = make_screen(args.backend, monitor=args.monitor)
    if args.delay > 0:
        print(f">>> {args.delay:.0f} secondi per portare il gioco in primo piano...")
        time.sleep(args.delay)
        print(">>> catturo\n")

    raccolti: list[tuple[float, object]] = []
    periodo = args.live_seconds / max(1, args.frames)
    t0 = time.perf_counter()
    try:
        while (
            len(raccolti) < args.frames and (time.perf_counter() - t0) < args.live_seconds
        ):
            g = screen.grab()
            if g.ok:
                raccolti.append((time.perf_counter() - t0, g.frame.copy()))
            time.sleep(max(0.0, periodo * 0.5))
    finally:
        screen.close()

    if not raccolti:
        raise RuntimeError("nessun frame catturato dallo schermo")
    if verbose:
        h, w = raccolti[0][1].shape[:2]
        print(f"catturati {len(raccolti)} frame da {w}x{h} in "
              f"{time.perf_counter()-t0:.1f}s ({screen.name})\n")

    def frames():
        return iter(raccolti)

    return frames


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.calibrate",
        description="Ricava ROI e soglie di colore da una registrazione.",
    )
    ap.add_argument("video", nargs="?", help="registrazione da calibrare (assente con --live)")
    ap.add_argument("--frames", type=int, default=400, help="quanti frame campionare")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--write", metavar="PROFILO", help="salva il profilo (es. profiles/gtav.json)")
    ap.add_argument("--out", default="runs/calibrate", help="cartella per i ritagli candidati")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument(
        "--live",
        action="store_true",
        help="calibra dallo SCHERMO invece che da un file: la ROI e' del setup di cattura",
    )
    ap.add_argument("--backend", default="auto", help="cattura: auto | dxcam | mss")
    ap.add_argument("--monitor", type=int, default=1)
    ap.add_argument("--delay", type=float, default=0.0, help="attesa prima di cominciare")
    ap.add_argument("--live-seconds", type=float, default=40.0, help="durata della cattura live")
    args = ap.parse_args(argv)

    if not args.video and not args.live:
        ap.error("serve un video, oppure --live per calibrare dallo schermo")

    verbose = not args.quiet
    if args.live:
        # La ROI e' del **setup di cattura**, non del gioco: misurato, gli stessi
        # sottotitoli stanno a 0,965 dell'altezza in una registrazione e a 0,914
        # in un'altra. Calibrare dal vivo non e' una comodita': e' l'unico modo
        # di avere la ROI del percorso che si usera' davvero.
        frames = _live_frames(args, verbose)
        etichetta, risoluzione = "schermo dal vivo", "?"
    else:
        info = probe(args.video)
        print(info)
        print(f"campiono {args.frames} frame\n")
        etichetta, risoluzione = info.path.name, f"{info.width}x{info.height}"

        def frames():
            return sample(args.video, args.frames, args.start, args.end)

    ev = Evidence()
    print("1. dove sta il testo")
    roi = find_roi(frames, ev, verbose)
    print(f"  -> roi = {roi}\n")

    print("2. le soglie")
    thr = find_thresholds(frames, roi, ev, verbose)
    for k, v in thr.items():
        print(f"  -> {k} = {v}")
    print()

    print("3. il grigio esiste?")
    grey_check(frames, roi, thr, ev, Path(args.out), verbose)
    print()

    print("da riga di comando:")
    print(
        f"  --set vision.roi={roi[0]},{roi[1]},{roi[2]},{roi[3]} "
        + " ".join(f"--set vision.{k}={v}" for k, v in thr.items())
    )

    if args.write:
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "vision": {
                "roi": list(roi),
                **thr,
            },
            "_calibrazione": {
                "video": etichetta,
                "risoluzione": risoluzione,
                **ev.to_dict(),
            },
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
