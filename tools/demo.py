"""Scena finta completa, dall'inizio alla fine, con un WAV da ascoltare.

    python -m tools.demo                    # con Piper
    python -m tools.demo --backend tone     # senza modelli

E' il banco di prova di F1: costruisce una scena con sottotitoli a schermo e
audio di gioco, ci fa girare l'intera pipeline e scrive il risultato mixato.
L'audio di gioco e' fatto apposta perche' il duck si senta: il parlato originale
sta al **centro**, la musica sta ai **lati**. Se il duck funziona, nel risultato
il parlato inglese si abbassa quando entra l'italiano e la musica no.

Non e' GTA. Serve a rispondere a domande a cui GTA non risponderebbe meglio —
i tempi sono giusti? il duck agisce dove deve? due personaggi in contemporanea
ricevono voci diverse? — su una scena di cui si conosce gia' la risposta.
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import VirtualClock, set_clock  # noqa: E402
from core.config import Config  # noqa: E402
from core.pipeline import DubPipeline  # noqa: E402
from speak.base import BACKEND_NOTI, make_tts  # noqa: E402
from tools.frames import GREY, WHITE, YELLOW, empty_frame, frame_with_roi  # noqa: E402

ROI = (0.15, 0.72, 0.70, 0.22)
SR = 48000
FPS = 30

# (inizio, fine, righe a schermo, f0 del parlato originale)
SCENA = [
    (0.6, 3.2, [("Non ho tempo per queste stronzate, Michael.", WHITE)], 105.0),
    (3.8, 6.4, [("Dove diavolo credi di andare?", WHITE), ("Lasciami in pace!", GREY)], 130.0),
    (7.0, 8.6, [("Premi E per entrare in macchina", YELLOW)], 0.0),
    (9.2, 12.0, [("Va bene, ci sto. Ma a modo mio. Ma non chiedermi di fidarmi.", WHITE)], 98.0),
]
DURATA = 13.0


def audio_di_gioco(t0: float, n: int, sr: int = SR) -> np.ndarray:
    """Blocco stereo: parlato al centro quando c'e' una battuta, musica sempre.

    La musica e' in controfase fra i due canali, cioe' puramente laterale: e' il
    modo piu' netto di verificare che il duck non la tocchi.
    """
    t = t0 + np.arange(n, dtype=np.float32) / sr

    musica = np.zeros(n, dtype=np.float32)
    for f, a in ((220.0, 0.09), (277.0, 0.07), (330.0, 0.06)):
        musica += a * np.sin(2 * np.pi * f * t)
    musica *= 0.8 + 0.2 * np.sin(2 * np.pi * 0.5 * t)

    parlato = np.zeros(n, dtype=np.float32)
    for inizio, fine, _, f0 in SCENA:
        if f0 <= 0:
            continue
        attivo = (t >= inizio) & (t < fine)
        if not attivo.any():
            continue
        voce = sum((0.20 / k) * np.sin(2 * np.pi * f0 * k * t) for k in (1, 2, 3, 4))
        sillabe = 0.4 + 0.6 * np.abs(np.sin(2 * np.pi * 3.5 * t))
        parlato += (voce * sillabe * attivo).astype(np.float32)

    return np.stack([parlato + musica, parlato - musica], axis=1).astype(np.float32)


def frame_a(t: float, cache: dict) -> np.ndarray:
    for i, (inizio, fine, righe, _) in enumerate(SCENA):
        if inizio <= t < fine:
            if i not in cache:
                cache[i] = frame_with_roi(righe, roi=ROI)
            return cache[i]
    if "vuoto" not in cache:
        cache["vuoto"] = empty_frame()
    return cache["vuoto"]


def scrivi_wav(path: Path, stereo: np.ndarray, sr: int = SR) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(stereo, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.demo", description="Scena finta completa.")
    ap.add_argument("--backend", default="piper", choices=BACKEND_NOTI)
    ap.add_argument("--out", default="runs")
    ap.add_argument("--no-duck", action="store_true", help="per sentire la differenza")
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    args = ap.parse_args(argv)

    cfg = Config().apply(args.overrides)
    cfg.vision.roi = ROI
    cfg.vision.stable_reads = 2
    if args.no_duck:
        cfg.mix.duck_db = 0.0

    from dataclasses import replace

    print("carico le voci...")
    tts = make_tts(replace(cfg.tts, backend=args.backend))

    clock = VirtualClock()
    precedente = set_clock(clock)
    pipeline = DubPipeline(cfg, tts, clock=clock, samplerate=SR)

    blocco = SR // 100  # 10 ms
    cache: dict = {}
    uscita: list[np.ndarray] = []
    prossimo_frame = 0.0
    t = 0.0

    print(f"\nscena di {DURATA:.0f}s, blocchi da 10 ms\n")
    try:
        while t < DURATA:
            clock.set(t)
            if t >= prossimo_frame:
                for riga in pipeline.on_frame(frame_a(t, cache)):
                    print(
                        f"  t={riga.t_subtitle:5.2f}s [{riga.cls:5}] {riga.voice_id:<14} "
                        f"lat {riga.latency_ms:4.0f}+{riga.synth_ms:3.0f}="
                        f"{riga.live_latency_ms:4.0f} ms  {riga.duration:4.2f}s  "
                        f"{riga.text[:42]!r}"
                    )
                prossimo_frame += 1.0 / FPS
            uscita.append(pipeline.on_audio(audio_di_gioco(t, blocco)))
            t += blocco / SR
    finally:
        set_clock(precedente)
    pipeline.finish()

    mix = np.concatenate(uscita)
    out_dir = Path(args.out)
    nome = "demo_no_duck.wav" if args.no_duck else "demo_mix.wav"
    path = scrivi_wav(out_dir / nome, mix)
    scrivi_wav(out_dir / "demo_gioco.wav", audio_di_gioco(0.0, int(DURATA * SR)))

    print()
    print("durata dei sottotitoli, misurata:")
    for e in pipeline.closed:
        print(f"  {e.duration:5.2f}s  [{e.cls.value:5}] {e.text[:50]!r}")

    print()
    print(pipeline.report())
    print(f"\n-> {path}")
    print(f"-> {out_dir / 'demo_gioco.wav'}  (solo audio di gioco, per confronto)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
