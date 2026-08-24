"""Come si vedrebbe l'overlay dal vivo, montato in un MP4 — senza il gioco.

    python -m tools.overlay_mp4 testGameplayFattoDaMe.mp4 runs\\tr --start 1240 --end 1270
    python -m tools.overlay_mp4 testGameplayFattoDaMe.mp4 runs\\tr --frames 6

Esiste per una ragione sola, ed e' un errore di metodo pagato caro: l'overlay
dal vivo si giudicava **solo** accendendo il gioco, quindi ogni giro di
correzione costava all'utente una sessione intera — Voicemeeter, la selezione
dell'area, la partita. Due giri cosi' e si consegna una cosa sbagliata perche'
nessuno ha voglia di farne un terzo.

**La cosa che rende questo video una prova e non un disegno**: il fotogramma
viene dipinto dalla stessa identica funzione che dipinge la finestra dal vivo
(`ui.overlay.dipingi`). Non e' una simulazione della grafica, e' la grafica.
L'MP4 di `tools/dub.py` invece la disegna con ffmpeg, che e' un secondo
disegnatore: quello mostra il doppiaggio, non l'overlay.

Cosa **non** dice: se la finestra ruba i clic, se sfarfalla quando si sposta, e
se il gioco la lascia stare sopra di se'. Quelle tre restano da vedere a schermo.

Le battute tradotte si prendono da una passata di `tools/dub.py` gia' fatta
(`runs/<cartella>/events.jsonl`), cosi' il testo e' quello vero e i tempi sono
quelli veri.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, load_profile  # noqa: E402
from ui.overlay import (  # noqa: E402
    MisuraCarattere, Sostituzione, inchiostro, inchiostro_da_box, ritaglia,
)



def prepara(frame, cfg, testo, originale, misura, boxes=(), ink=None,
            roi=None, stringi=False):
    """Dipinge **una volta** il sottotitolo tradotto. `None` se non c'e' testo.

    Torna la `Sostituzione`, che tiene **la geometria decisa una volta**: taglia,
    colore, posizione e a-capo non si toccano piu' finche' la battuta resta a
    schermo. Ricalcolarli a ogni fotogramma li faceva ballare — il riquadro
    inseguiva l'immagine come un tracker, e nei fotogrammi di dissolvenza il
    sottotitolo spariva del tutto. Un sottotitolo compare, sta fermo, sparisce.

    I **pixel** invece si rifanno a ogni fotogramma (`disegna`): se no la toppa
    che cancella la riga italiana resta quella del primo fotogramma e diventa un
    rettangolo di immagine vecchia mentre la scena si muove.

    Usa `ui.overlay.inchiostro` e `ui.overlay.dipingi`, cioe' **le stesse due
    funzioni del vivo**. Una copia locale sarebbe divergita al primo ritocco, e
    il video avrebbe smesso di dire la verita' sulla finestra senza che nessun
    numero lo mostrasse.
    """
    # **La stessa fonte di geometria del vivo, e questo e' il punto.** Prima
    # l'MP4 ricercava l'inchiostro da se' mentre dal vivo lo ricercava un'altra
    # chiamata su un altro fotogramma: due rilevatori per lo stesso lavoro, che
    # e' esattamente la forma di difetto per cui questo strumento esiste. I box
    # scritti in `events.jsonl` sono quelli che il lettore ha validato, e adesso
    # li usano tutti e due. `inchiostro()` resta il ripiego per le passate
    # vecchie, che quei campi non li hanno.
    pezzo = bande = rett = tinta = None
    if boxes:
        # **La ROI e' quella dell'area che ha letto la battuta.** Con piu' aree
        # dichiarate i rettangoli sono in coordinate della *sua*, e passare
        # sempre `cfg.vision.roi` metterebbe la traduzione di un cartello dentro
        # la fascia del dialogo — nel posto sbagliato e senza nessun errore.
        pezzo, bande, rett, tinta = inchiostro_da_box(frame, cfg, boxes, ink, roi=roi)
    if pezzo is None:
        pezzo, bande, rett, tinta = inchiostro(frame, cfg)
    if pezzo is None:
        return None
    rx = int(round(rett[0] * frame.shape[1]))
    ry = int(round(rett[1] * frame.shape[0]))
    corpo = (int(frame.shape[0] * cfg.translate.font_frac)
             if cfg.translate.font_frac > 0
             else misura.aggiorna(bande, originale, 1.0, cfg.translate.font))
    sost = Sostituzione(
        pezzo, bande, testo,
        scala=1.0,
        nome_font=cfg.translate.font,
        colore=None if not cfg.translate.color else _rgb(cfg.translate.color),
        corpo=corpo,
        contorno=cfg.translate.outline,
        blur=cfg.translate.blur_strength,
        inchiostro_rgb=tinta,
        modo=cfg.translate.background_mode,
        # Vuoto = si campiona dalla scena, come dal vivo. E **non** invertito:
        # `_rgb` legge gia' `#rrggbb` in RGB, e `Sostituzione` lo usa come RGB —
        # lo scambio qui dava a un fondo colorato il colore sbagliato, invisibile
        # finche' il default e' stato il nero.
        fondo_rgb=_rgb(cfg.translate.background) if cfg.translate.background else None,
        testo_originale=originale,
        larghezza_schermo=frame.shape[1],
        # Una scritta in mezzo allo schermo sta nel **suo** riquadro: se la
        # traduzione e' piu' lunga si stringe il carattere invece di allargare
        # la toppa, perche' li' attorno c'e' altra roba — spesso un'altra
        # scritta che si sta traducendo nello stesso fotogramma.
        stringi=bool(stringi),
        corpo_min=int(getattr(cfg.translate, "corpo_min", 11)),
    )
    return sost, rett, rx, ry


def _rgb(s: str):
    s = (s or "#000000").lstrip("#")
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))


def _incolla(frame, tela, x, y):
    """Sovrappone una tela RGBA al fotogramma BGR, rispettando l'alfa."""
    a = np.array(tela)
    h, w = a.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sotto = frame[y0:y1, x0:x1].astype(np.float32)
    sopra = a[y0 - y : y1 - y, x0 - x : x1 - x]
    alfa = (sopra[:, :, 3:4].astype(np.float32)) / 255.0
    rgb = sopra[:, :, :3][:, :, ::-1].astype(np.float32)  # RGBA -> BGR
    frame[y0:y1, x0:x1] = (sotto * (1 - alfa) + rgb * alfa).astype(np.uint8)


def battute(cartella: Path):
    """Le battute tradotte di una passata, come dizionari.

    Erano tuple posizionali di cinque campi: con `roi` e `stringi` diventano
    sette, e a quel punto `attiva[3]` non dice piu' niente a chi legge — un
    indice sbagliato prenderebbe il rettangolo di un'altra area senza dare
    errore, che e' esattamente la classe di difetti che questo strumento esiste
    per far vedere.
    """
    righe = []
    for r in (cartella / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if not r.strip():
            continue
        e = json.loads(r)
        if not e.get("text"):
            continue
        righe.append({
            "t": e["t_subtitle"],
            "testo": e["text"],
            "originale": e.get("text_original", ""),
            "boxes": tuple(tuple(b) for b in e.get("boxes") or ()),
            "ink": tuple(e.get("ink") or ()) or None,
            "roi": tuple(e.get("roi") or ()) or None,
            "stringi": bool(e.get("stringi")),
        })
    return righe


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools.overlay_mp4",
                                 description="Monta come si vedrebbe l'overlay dal vivo.")
    ap.add_argument("video")
    ap.add_argument("run", help="cartella di una passata di tools.dub (per i testi tradotti)")
    ap.add_argument("--profile", default="gtav")
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    # I tempi in `events.jsonl` partono da zero all'inizio della fetta: se la
    # passata era `--start 1240`, qui va lo stesso 1240, se no si dipinge la
    # battuta giusta sul fotogramma sbagliato — e si giudicherebbe la grafica su
    # un accostamento che dal vivo non capita mai.
    ap.add_argument("--offset", type=float, default=0.0,
                    help="il --start con cui era stata fatta la passata di tools.dub")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--out", default="runs/overlay.mp4")
    ap.add_argument("--frames", type=int, default=0,
                    help="invece del video, N fotogrammi PNG: si guardano subito")
    args = ap.parse_args(argv)

    cfg = (load_profile(args.profile, args.overrides) if args.profile
           else Config().apply(args.overrides))
    cfg.translate.enabled = True
    righe = battute(Path(args.run))
    if not righe:
        print(f"nessuna battuta tradotta in {args.run}")
        return 2
    print(f"{len(righe)} battute tradotte, da {righe[0]['t']:.1f}s a {righe[-1]['t']:.1f}s")

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    t0 = args.start if args.start else max(0.0, args.offset + righe[0]["t"] - 1.0)
    t1 = args.end if args.end else args.offset + righe[-1]["t"] + 6.0
    cap.set(cv2.CAP_PROP_POS_MSEC, t0 * 1000.0)

    uscita = Path(args.out)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    misura = MisuraCarattere()
    video = None
    scritti = png = 0
    # **A schermo c'e' una scritta sola, ed e' l'ultima comparsa.** Qui si
    # tenevano vive tutte le battute degli otto secondi precedenti e si
    # dipingevano insieme: residuo delle aree multiple, dove ce n'erano N
    # contemporanee. Tolte quelle, su una fascia di dialogo se ne sovrapponevano
    # cinque — e dal vivo non succede mai, perche' `core/motore.py` manda un
    # `overlay` per volta e la finestra **sostituisce** il precedente. Un
    # montatore che mostra una cosa mentre il vivo ne fa un'altra e' peggio di
    # nessun montatore: e' esattamente com'era nato il difetto che questo
    # strumento esiste per far vedere.
    #
    # Gli otto secondi restano come **tetto** alla permanenza, non come durata:
    # quasi sempre e' la battuta dopo a chiudere quella prima.
    #
    # La chiave resta `(t_on, testo)` e non il solo `t_on`: e' quella che dice
    # se la battuta a schermo e' ancora la stessa, e quindi se la geometria
    # gia' preparata si puo' riusare invece di rifarla a ogni fotogramma.
    correnti: dict = {}
    ultimo_png = None
    while True:
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        ok, frame = cap.read()
        if not ok or t > t1:
            break
        # Ogni battuta si dipinge **una volta sola**: chiuderla sulla durata
        # dell'audio doppiato la faceva sparire mentre l'originale era ancora a
        # schermo; ridisegnarla a ogni fotogramma la faceva tremare.
        tr = t - args.offset
        aperte = [r for r in righe if r["t"] <= tr < r["t"] + 8.0]
        # L'ultima comparsa, e una sola: `max` sul solo `t` sceglierebbe a caso
        # fra due battute nate nello stesso fotogramma, quindi si prende
        # l'ultima nell'ordine del file, che e' quello in cui sono state lette.
        attive = aperte[-1:]
        chiavi = {(r["t"], r["testo"]) for r in attive}
        for morta in [k for k in correnti if k not in chiavi]:
            del correnti[morta]
        for r in attive:
            k = (r["t"], r["testo"])
            if k in correnti:
                continue
            fatto = prepara(frame, cfg, r["testo"], r["originale"], misura,
                            r["boxes"], r["ink"], roi=r["roi"], stringi=r["stringi"])
            if fatto:
                correnti[k] = fatto
        for sost, rett, rx, ry in correnti.values():
            pezzo = ritaglia(frame, rett)
            if pezzo is not None and pezzo.shape[:2] == sost.forma:
                tela, (ox, oy) = sost.disegna(pezzo)
                _incolla(frame, tela, rx + ox, ry + oy)
        if args.frames:
            marca = min(chiavi) if chiavi else None
            if correnti and png < args.frames and marca != ultimo_png:
                nome = uscita.with_name(f"{uscita.stem}_{png}.png")
                cv2.imwrite(str(nome), frame)
                quante = len(correnti)
                stretti = sum(1 for s, *_ in correnti.values() if getattr(s, "stretto", False))
                corpi = sorted({s.corpo for s, *_ in correnti.values()})
                print(f"  {nome}  t={t:.1f}s  {quante} scritte, corpi {corpi}"
                      f"{f', {stretti} al pavimento' if stretti else ''}")
                for r in attive[:8]:
                    print(f"      '{r['originale']}' -> '{r['testo']}'")
                png += 1
                ultimo_png = marca
            if png >= args.frames:
                break
            continue
        if video is None:
            h, w = frame.shape[:2]
            video = cv2.VideoWriter(str(uscita), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        video.write(frame)
        scritti += 1
    cap.release()
    if video is not None:
        video.release()
        print(f"scritti {scritti} fotogrammi in {uscita}")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
