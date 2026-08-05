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
from ui.overlay import MisuraCarattere, dipingi, inchiostro  # noqa: E402

# La stessa memoria che tiene la finestra dal vivo: senza, il carattere
# seguirebbe la dissolvenza del sottotitolo e il video mostrerebbe un difetto
# che dal vivo non c'e' — o, peggio, non ne mostrerebbe uno che c'e'.
MISURA = MisuraCarattere()


def componi(frame, cfg, testo):
    """Il fotogramma con sopra il sottotitolo tradotto. `False` se non c'era testo.

    Usa `ui.overlay.inchiostro` e `ui.overlay.dipingi`, cioe' **le stesse due
    funzioni del vivo**. Una copia locale sarebbe divergita al primo ritocco, e
    il video avrebbe smesso di dire la verita' sulla finestra senza che nessun
    numero lo mostrasse.
    """
    pezzo, bande, rett, tinta = inchiostro(frame, cfg)
    if pezzo is None:
        return False
    rx = int(round(rett[0] * frame.shape[1]))
    ry = int(round(rett[1] * frame.shape[0]))
    corpo = (int(frame.shape[0] * cfg.translate.font_frac)
             if cfg.translate.font_frac > 0
             else MISURA.aggiorna(bande, 1.0, cfg.translate.font))
    fatto = dipingi(
        pezzo, bande, testo,
        scala=1.0,
        nome_font=cfg.translate.font,
        colore=None if not cfg.translate.color else _rgb(cfg.translate.color),
        corpo=corpo,
        contorno=cfg.translate.outline,
        blur=cfg.translate.blur_strength,
        inchiostro_rgb=tinta,
        modo=cfg.translate.background_mode,
        fondo_rgb=_rgb(cfg.translate.background)[::-1],
    )
    if fatto is None:
        return False
    tela, (ox, oy) = fatto
    _incolla(frame, tela, rx + ox, ry + oy)
    return True


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
    righe = []
    for r in (cartella / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if r.strip():
            e = json.loads(r)
            if e.get("text"):
                righe.append((e["t_subtitle"], e["text"], e.get("text_original", "")))
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
    print(f"{len(righe)} battute tradotte, da {righe[0][0]:.1f}s a {righe[-1][0]:.1f}s")

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    t0 = args.start if args.start else max(0.0, args.offset + righe[0][0] - 1.0)
    t1 = args.end if args.end else args.offset + righe[-1][0] + 6.0
    cap.set(cv2.CAP_PROP_POS_MSEC, t0 * 1000.0)

    uscita = Path(args.out)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    video = None
    scritti = png = 0
    while True:
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        ok, frame = cap.read()
        if not ok or t > t1:
            break
        # **La battuta corrente e' l'ultima comparsa, e si disegna finche' il
        # sottotitolo del gioco e' a schermo** — che e' `inchiostro` a dirlo, non
        # un orologio. Chiudere la finestra sulla durata dell'audio doppiato la
        # faceva sparire mentre l'originale era ancora li'.
        tr = t - args.offset
        attiva = None
        for r in righe:
            if r[0] <= tr and tr - r[0] < 8.0:
                attiva = r
        disegnata = componi(frame, cfg, attiva[1]) if attiva else False
        if args.frames:
            if disegnata and png < args.frames:
                # Un fotogramma per battuta, non uno ogni tre: due PNG della
                # stessa riga non dicono niente di piu' del primo.
                if png == 0 or attiva[0] != main._ultima:
                    nome = uscita.with_name(f"{uscita.stem}_{png}.png")
                    cv2.imwrite(str(nome), frame)
                    print(f"  {nome}  t={t:.1f}s  '{attiva[2]}' -> '{attiva[1]}'")
                    png += 1
                main._ultima = attiva[0]
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


main._ultima = None


if __name__ == "__main__":
    raise SystemExit(main())
