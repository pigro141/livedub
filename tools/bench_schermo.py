"""Le tre domande dell'area grande, una alla volta.

    python -m tools.bench_schermo --cancello testGameplayFattoDaMe.mp4 --start 1240
    python -m tools.bench_schermo --blocchi  testGameplayFattoDaMe.mp4 --start 1250
    python -m tools.bench_schermo --costo    testGameplayFattoDaMe.mp4 --start 1240
    python -m tools.bench_schermo --pavimento

`CLAUDE.md` dichiara che tradurre tutto lo schermo «e' un altro prodotto», e non
e' un'opinione: sono tre misure, e questo banco le rifa'. Ognuna risponde a una
domanda sola e nessuna ha bisogno del gioco acceso.

**`--cancello`** — un'area grande legge? Il cancello che decide se rileggere
guarda la frazione di pixel cambiati, e quella frazione ha l'area al
denominatore: a schermo intero non si apre mai. Qui si conta, sulla stessa
registrazione, quanti fotogrammi passano prima e dopo — e, che e' la meta' che
conta, quanti ne passano quando **non cambia niente**. Un cancello che si apre
sempre risolve il primo numero e rompe tutto il resto.

**`--blocchi`** — le scritte si trovano? Disegna i rettangoli trovati sul
fotogramma e li scrive in un PNG. Su una correzione geometrica la verifica e'
l'immagine: tutte le misure di *quanto* non possono dire *dove*.

**`--costo`** — quanto costa un fotogramma intero, e a che frequenza si puo'
girare. La risposta va **dichiarata**: se sono 2 Hz e non 30, si scrive.

**`--pavimento`** — sotto che corpo il carattere smette di leggersi. Non e' una
questione di gusto: il testo si disegna con un contorno nero sopra l'asta del
glifo, e sotto una certa misura il glifo **e'** il suo contorno.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, load_profile  # noqa: E402
from vision.diff import Change, RoiDiff  # noqa: E402
from vision.roi import crop  # noqa: E402


def _apri(video: str, inizio: float):
    import cv2

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"non riesco ad aprire {video}")
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    return cap


def _fotogrammi(video: str, inizio: float, quanti: int):
    cap = _apri(video, inizio)
    for _ in range(quanti):
        ok, frame = cap.read()
        if not ok:
            break
        yield frame
    cap.release()


def _diff(cfg, cella: int) -> RoiDiff:
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


def cancello(cfg, video: str, inizio: float, quanti: int) -> None:
    """Quanti fotogrammi passano il cancello, per altezza d'area e per cancello.

    **Tre colonne e non una.** «Quanti passano» da solo non e' una risposta: un
    cancello sempre aperto lo massimizza ed e' il difetto opposto. Servono
    insieme:

    - *passa*: quanti fotogrammi svegliano l'OCR sulla scena vera;
    - *fermo*: quanti ne passano quando si ripresenta **lo stesso** fotogramma,
      cioe' il caso nullo. Deve essere zero;
    - *sui cambi*: di quelli in cui la fascia stretta — il cancello che gia'
      funziona — ha visto comparire o cambiare del testo, quanti ne prende anche
      l'area grande. E' la sensibilita', e senza di lei «passa poco» e «non vede»
      sono lo stesso numero.
    """
    frames = list(_fotogrammi(video, inizio, quanti))
    if not frames:
        raise SystemExit("nessun fotogramma letto")
    print(f"{len(frames)} fotogrammi da {video} a partire da {inizio:.0f}s "
          f"({frames[0].shape[1]}x{frames[0].shape[0]})\n")

    # Il riferimento: la fascia stretta col cancello di sempre. E' la
    # configurazione che legge davvero, quindi e' lei a dire quando a schermo e'
    # comparso del testo.
    stretta = tuple(cfg.vision.roi)
    rif = _diff(cfg, 0)
    cambi = set()
    for i, f in enumerate(frames):
        d = rif.update(crop(f, stretta))
        if d.change in (Change.APPEARED, Change.REPLACED):
            cambi.add(i)
    print(f"riferimento: la fascia {stretta} col cancello di sempre vede "
          f"{len(cambi)} comparse/sostituzioni\n")

    aree = [
        ("fascia stretta", stretta),
        ("mezzo schermo", (0.0, 0.25, 1.0, 0.50)),
        ("schermo intero", (0.0, 0.0, 1.0, 1.0)),
    ]
    print(f"{'area':<16} {'cancello':<14} {'passa':>10} {'fermo':>8} {'sui cambi':>12}")
    print("-" * 64)
    for nome, roi in aree:
        for etichetta, cella in (("media (di sempre)", 0), ("celle da 32", 32)):
            d = _diff(cfg, cella)
            passati = presi = 0
            for i, f in enumerate(frames):
                r = d.update(crop(f, roi))
                if r.changed:
                    passati += 1
                    if i in cambi:
                        presi += 1
            # Il caso nullo: lo stesso fotogramma due volte di seguito.
            fermo = _diff(cfg, cella)
            fermo.update(crop(frames[len(frames) // 2], roi))
            immobili = sum(
                1 for _ in range(20)
                if fermo.update(crop(frames[len(frames) // 2], roi)).changed
            )
            quota = f"{presi}/{len(cambi)}" if cambi else "-"
            print(f"{nome:<16} {etichetta:<14} {passati:>6}/{len(frames)} "
                  f"{immobili:>6}/20 {quota:>12}")
        print()


def fermo(cfg, video: str, inizio: float, quanti: int) -> None:
    """Il caso che rompe il cancello, e non e' quello che sembra.

    `--cancello` misura una scena che **si muove**, e li' il cancello vecchio
    non fallisce affatto: a schermo intero si apre 149 volte su 300 e prende
    tutte le comparse, perche' a cambiare e' l'inquadratura. E' il difetto
    rovesciato gia' scritto in `CLAUDE.md` — l'OCR gira sempre, sul fotogramma
    intero — non quello di cui parla la tabella.

    Il difetto vero e' l'aritmetica del denominatore, e si vede solo dove il
    denominatore e' l'unica cosa che cambia: **schermo fermo, compare una
    scritta**. Qui si cercano nella registrazione le coppie di fotogrammi che
    sono cosi' davvero — fuori dalla fascia dei sottotitoli identiche, dentro
    diverse — e su quelle si fa crescere l'area.

    Cercarle invece di costruirle e' la differenza fra una misura e un
    surrogato: un fotogramma sintetico direbbe quello che gli si chiede, e
    questo progetto ha gia' archiviato una conclusione falsa in quel modo.
    """
    aree = [("0,08", (0.0, 0.86, 1.0, 0.08)), ("0,12", (0.0, 0.84, 1.0, 0.12)),
            ("0,30", (0.0, 0.66, 1.0, 0.30)), ("0,50", (0.0, 0.48, 1.0, 0.50)),
            ("0,70", (0.0, 0.28, 1.0, 0.70)), ("1,00", (0.0, 0.0, 1.0, 1.0))]
    stretta = tuple(cfg.vision.roi)
    media = {n: [] for n, _ in aree}
    celle = {n: [] for n, _ in aree}
    nulla: list[float] = []   # cella peggiore quando non cambia proprio niente
    trovate = 0

    # **Si scandisce tutta la registrazione, non una finestra.** Una scena con
    # la telecamera ferma *e* un sottotitolo che compare e' rara: su
    # novecento fotogrammi di un inseguimento non ce n'e' nessuna, e la prima
    # stesura di questo banco ha risposto «non ce ne sono» per tre `--start` di
    # fila. Su ventisei minuti ce ne sono abbastanza per una tabella.
    finestre = list(range(int(inizio), int(inizio) + 1560, 80))
    for avvio in finestre:
        frames = list(_fotogrammi(video, float(avvio), quanti))
        if len(frames) < 2:
            continue
        h_f = frames[0].shape[0]
        banda = slice(int(stretta[1] * h_f) // 4,
                      max(1, int((stretta[1] + stretta[3]) * h_f) // 4))
        piccoli = [f[::4, ::4, :3].astype(np.float32).mean(axis=2) for f in frames]

        def scarto(a, b, _b=banda):
            d = np.abs(a - b) > 16.0
            return (float(np.delete(d, np.s_[_b], axis=0).mean()), float(d[_b].mean()))

        # **Le coppie si cercano dentro una *ripresa* ferma, non fra due
        # fotogrammi adiacenti.** Consecutivi la scritta compare in dissolvenza,
        # un pixel per volta, e non supera nessuna soglia; il salto vero e' fra
        # il primo fotogramma della ripresa e quello in cui la scritta c'e'
        # tutta.
        coppie: list[tuple[int, int]] = []
        ancora = 0
        for i in range(1, len(piccoli)):
            fuori_ora, _ = scarto(piccoli[i - 1], piccoli[i])
            if fuori_ora > 0.006:  # la telecamera si e' mossa: ripresa finita
                ancora = i
                continue
            fuori, dentro = scarto(piccoli[ancora], piccoli[i])
            if fuori < 0.006 and dentro > 0.015:
                coppie.append((ancora, i))
                ancora = i  # la stessa comparsa non si conta due volte
            elif fuori < 5e-4 and dentro < 5e-4 and len(nulla) < 400:
                # **Il caso nullo condivide tutto tranne la risposta**: due
                # fotogrammi in cui non e' cambiato niente, dallo stesso tratto
                # e dalla stessa scena delle coppie buone.
                d = _diff(cfg, 32)
                d.update(crop(frames[i - 1], (0.0, 0.0, 1.0, 1.0)))
                nulla.append(d.update(crop(frames[i], (0.0, 0.0, 1.0, 1.0))).ratio)
        trovate += len(coppie)
        for nome, roi in aree:
            for prima, dopo in coppie:
                a, b = crop(frames[prima], roi), crop(frames[dopo], roi)
                for d, dove in ((_diff(cfg, 0), media[nome]), (_diff(cfg, 32), celle[nome])):
                    d.update(a)
                    dove.append(d.update(b).ratio)

    if not trovate:
        print("nessuna coppia «schermo fermo, la scritta cambia»: serve una "
              "registrazione con almeno una scena a telecamera ferma.")
        return
    print(f"{trovate} coppie «schermo fermo, la scritta cambia» in "
          f"{len(finestre)} finestre da {quanti} fotogrammi\n")

    print(f"{'altezza area':>13} {'media p50':>11} {'apre?':>8}   "
          f"{'cella p50':>11} {'apre?':>8}")
    print("-" * 60)
    for nome, _ in aree:
        v, c = media[nome], celle[nome]
        av = sum(1 for x in v if x > cfg.vision.diff_threshold)
        ac = sum(1 for x in c if x > cfg.vision.diff_cella_soglia)
        print(f"{nome:>13} {statistics.median(v):>11.4f} {f'{av}/{len(v)}':>8}   "
              f"{statistics.median(c):>11.4f} {f'{ac}/{len(c)}':>8}")
    print(f"\nsoglie: media {cfg.vision.diff_threshold}, "
          f"celle {cfg.vision.diff_cella_soglia}")

    # -- e dove sta l'altopiano della soglia nuova ---------------------------
    #
    # Non si eredita `diff_threshold`: e' misurata sulla media dell'area, e qui
    # la distribuzione e' un'altra. Riusarla sarebbe la quinta volta in questo
    # progetto che una soglia cambia distribuzione sotto i piedi.
    grandi = celle["1,00"]
    if grandi and nulla:
        fermi = sorted(nulla)
        print(f"\nla cella peggiore a schermo intero quando **non cambia niente** "
              f"(n={len(fermi)}): p50 {statistics.median(fermi):.5f}, "
              f"p95 {fermi[int(0.95 * (len(fermi) - 1))]:.5f}, max {fermi[-1]:.5f}")
        print(f"quando la scritta cambia (n={len(grandi)}): "
              f"{' '.join(f'{x:.4f}' for x in sorted(grandi))}\n")
        print(f"{'soglia':>8} {'prende':>12} {'falsi':>12}")
        for s in (0.005, 0.010, 0.020, 0.025, 0.030, 0.040, 0.060, 0.080, 0.100):
            print(f"{s:>8.3f} {f'{sum(1 for x in grandi if x > s)}/{len(grandi)}':>12} "
                  f"{f'{sum(1 for x in fermi if x > s)}/{len(fermi)}':>12}")
        print("\nLa soglia si prende **in mezzo** all'altopiano dove prende tutto e "
              "non sbaglia niente,\nnon sul suo orlo: sull'orlo un numero non e' "
              "tarato, e' vinto.")


def blocchi(cfg, video: str, inizio: float, quanti: int, fuori: Path) -> None:
    """Le scritte trovate a schermo intero, disegnate su un PNG.

    Su una correzione geometrica la verifica e' l'immagine: un riquadro che
    migliora tutti i numeri puo' stare dove il testo non c'e', e nessuna misura
    di *quanto* lo puo' dire.
    """
    import cv2

    from vision import blocchi as B

    fuori.mkdir(parents=True, exist_ok=True)
    conteggi = []
    for k, frame in enumerate(_fotogrammi(video, inizio, quanti)):
        riga = cfg.vision.schermo_riga_frac * frame.shape[0]
        t0 = time.perf_counter()
        trovati, scartati = B.trova(frame, cfg.vision, riga,
                                    massimo=cfg.vision.schermo_max_blocchi)
        ms = (time.perf_counter() - t0) * 1000.0
        conteggi.append(len(trovati))
        tela = frame.copy()
        for i, b in enumerate(trovati):
            cv2.rectangle(tela, (b.x0, b.y0), (b.x1, b.y1), (60, 241, 67), 2)
            cv2.putText(tela, str(i), (b.x0 + 3, max(14, b.y0 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 241, 67), 1)
        nome = fuori / f"blocchi_{k}.png"
        cv2.imwrite(str(nome), tela)
        print(f"  {nome}  {len(trovati)} blocchi ({scartati} scartati)  {ms:.1f} ms")
    if conteggi:
        print(f"\nblocchi per fotogramma: mediana {statistics.median(conteggi):.0f}, "
              f"max {max(conteggi)}")


def costo(cfg, video: str, inizio: float, quanti: int, con_ocr: bool) -> None:
    """Quanto costa un fotogramma intero, stadio per stadio, e a che Hz si gira.

    Il costo si misura **a muro** e non sull'orologio del media: e' la regola dei
    due tempi, e confonderli farebbe risultare gratis ogni stadio.
    """
    from vision.blocchi import allarga, trova
    from vision.lines import classify_lines

    motore = None
    if con_ocr:
        from vision.ocr import make_ocr

        motore = make_ocr(cfg.vision.ocr_backend, cfg.vision.ocr_device)
        print(f"OCR: {getattr(motore, 'name', motore)}")

    t_trova, t_classe, t_ocr, n_blocchi, n_righe = [], [], [], [], []
    for frame in _fotogrammi(video, inizio, quanti):
        riga = cfg.vision.schermo_riga_frac * frame.shape[0]
        t0 = time.perf_counter()
        trovati, _ = trova(frame, cfg.vision, riga,
                           massimo=cfg.vision.schermo_max_blocchi)
        t_trova.append((time.perf_counter() - t0) * 1000.0)
        n_blocchi.append(len(trovati))

        ms_c = ms_o = 0.0
        righe = 0
        for b in trovati:
            g = allarga(b, riga, frame.shape)
            pezzo = frame[g.y0 : g.y1, g.x0 : g.x1]
            t0 = time.perf_counter()
            bande = classify_lines(pezzo, cfg.vision)
            ms_c += (time.perf_counter() - t0) * 1000.0
            righe += len(bande)
            if motore is not None:
                for banda in bande:
                    if not banda.cls.is_dialogue:
                        continue
                    t0 = time.perf_counter()
                    motore.read(banda.crop)
                    ms_o += (time.perf_counter() - t0) * 1000.0
        t_classe.append(ms_c)
        t_ocr.append(ms_o)
        n_righe.append(righe)

    def riga_tab(nome, v):
        if not v:
            return
        s = sorted(v)
        print(f"  {nome:<22} p50 {statistics.median(s):7.1f} ms   "
              f"p95 {s[int(0.95 * (len(s) - 1))]:7.1f} ms   max {s[-1]:7.1f} ms")

    totali = [a + b + c for a, b, c in zip(t_trova, t_classe, t_ocr)]
    print(f"\n{len(t_trova)} fotogrammi a schermo intero, "
          f"{statistics.median(n_blocchi):.0f} blocchi e "
          f"{statistics.median(n_righe):.0f} righe di mediana\n")
    riga_tab("trovare i blocchi", t_trova)
    riga_tab("classificare", t_classe)
    if con_ocr:
        riga_tab("OCR", t_ocr)
    riga_tab("TOTALE", totali)
    if totali:
        p50 = statistics.median(totali)
        p95 = sorted(totali)[int(0.95 * (len(totali) - 1))]
        print(f"\nfrequenza sostenibile: {1000.0 / max(1e-6, p50):.1f} Hz al p50, "
              f"{1000.0 / max(1e-6, p95):.1f} Hz al p95")
        print("(e il dominio video gira a 30 Hz: sopra i 33 ms al fotogramma "
              "questa modalita' toglie fotogrammi al doppiaggio)")


def pavimento(nome_font: str = "Arial", contorno: int = 2) -> None:
    """Sotto che corpo il glifo **e'** il suo contorno.

    **La prima stesura di questa misura non poteva rispondere**, ed e' istruttivo
    perche' non dava nessun segnale: contava che quota dei pixel a piena
    intensita' «sopravvive» al contorno, e la risposta era 100% a ogni corpo
    fino a sparire di colpo. Ovvio a posteriori — PIL disegna il contorno
    **attorno** al glifo e poi il glifo sopra, quindi il nucleo pieno non viene
    toccato per costruzione. Era una soglia che si guardava allo specchio.

    La domanda giusta e' quanta parte del glifo e' **nucleo pieno** invece di
    sfumatura, perche' e' la sfumatura quella che il contorno nero si mangia: un
    glifo fatto di soli pixel grigi, chiuso fra due bordi neri, e' nero su nero.
    Si contano quindi i pixel a piena intensita' **per carattere**, e si guarda
    dove crollano.

    E si guarda dove crollano e non dove scendono: fra un corpo e il successivo
    il conteggio cala piano, e poi in un punto preciso si divide per sette. Quel
    punto e' il pavimento, ed e' una proprieta' del carattere, non un gusto.
    """
    from PIL import Image, ImageDraw

    from ui.overlay import carica_font

    testo = "Rimuovi il veicolo"
    n = sum(1 for ch in testo if not ch.isspace())
    print(f"{nome_font}, contorno {contorno} px, «{testo}» ({n} caratteri)\n")
    print(f"{'corpo':>6} {'asta stimata':>13} {'nucleo pieno':>13} "
          f"{'per carattere':>14} {'contro il corpo prima':>22}")
    print("-" * 74)
    prima = None
    for corpo in range(20, 5, -1):
        f = carica_font(nome_font, corpo)
        w = int(f.getlength(testo)) + 8 * corpo
        h = 6 * corpo
        tela = Image.new("L", (w, h), 0)
        ImageDraw.Draw(tela).text((4 * corpo, h // 2), testo, font=f, fill=255,
                                  anchor="mm", stroke_width=contorno, stroke_fill=1)
        pieni = int((np.array(tela) == 255).sum())
        per_car = pieni / n
        salto = "" if prima is None else f"{pieni / max(1, prima):.2f}x"
        segno = ""
        if prima is not None and pieni < 0.4 * prima:
            segno = "  <- il precipizio"
        print(f"{corpo:>6} {0.12 * corpo:>12.1f}px {pieni:>13} {per_car:>14.1f} "
              f"{salto:>22}{segno}")
        prima = pieni
    print("\nIl pavimento sta **sopra** il precipizio, non su di lui: sull'orlo\n"
          "una taratura e' vinta, non tarata.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools.bench_schermo",
                                 description="Le tre domande dell'area grande.")
    ap.add_argument("video", nargs="?", default="testGameplayFattoDaMe.mp4")
    ap.add_argument("--profile", default="gtav")
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    ap.add_argument("--start", type=float, default=1240.0)
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--out", default="runs/schermo")
    ap.add_argument("--cancello", action="store_true")
    ap.add_argument("--fermo", action="store_true",
                    help="il caso vero: schermo fermo e la scritta cambia")
    ap.add_argument("--blocchi", action="store_true")
    ap.add_argument("--costo", action="store_true")
    ap.add_argument("--ocr", action="store_true", help="con --costo, misura anche l'OCR vero")
    ap.add_argument("--pavimento", action="store_true")
    args = ap.parse_args(argv)

    if args.pavimento:
        pavimento()
        return 0

    cfg = (load_profile(args.profile, args.overrides) if args.profile
           else Config().apply(args.overrides))
    if args.cancello:
        cancello(cfg, args.video, args.start, args.frames)
    if args.fermo:
        fermo(cfg, args.video, args.start, args.frames)
    if args.blocchi:
        blocchi(cfg, args.video, args.start, min(args.frames, 12), Path(args.out))
    if args.costo:
        costo(cfg, args.video, args.start, args.frames, args.ocr)
    if not (args.cancello or args.fermo or args.blocchi or args.costo):
        ap.error("scegli una domanda: --cancello, --fermo, --blocchi, --costo "
                 "o --pavimento")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
