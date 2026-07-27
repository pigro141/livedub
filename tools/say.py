"""Ascoltare il pool di voci.

    python -m tools.say --pool                       # ogni voce dice la stessa battuta
    python -m tools.say "Sali in macchina, muoviti!" # una battuta con la voce 0
    python -m tools.say --pool --scena               # un dialogo a piu' voci

La qualita' di una voce non si misura: si ascolta. Questo strumento esiste per
mettere il giudizio umano dove i numeri non arrivano — quante voci del pool
suonano davvero come persone diverse, e quali varianti sono spinte troppo in la'.
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config  # noqa: E402
from speak.base import ToneTts  # noqa: E402
from speak.pool import build_pool  # noqa: E402

BATTUTA = "Non ho tempo per queste stronzate. Sali in macchina e muoviti, adesso."

SCENA = [
    "Dove diavolo credi di andare?",
    "Da nessuna parte. Stavo solo prendendo una boccata d'aria.",
    "Non mentirmi. So benissimo cosa stavi per fare.",
    "E allora? Che cosa vuoi farci?",
    "Niente. Assolutamente niente. Ma la prossima volta ti conviene chiamarmi.",
    "Va bene, ci sto. Ma a modo mio.",
]


def scrivi_wav(path: Path, audio: np.ndarray, samplerate: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
    return path


def silenzio(seconds: float, samplerate: int) -> np.ndarray:
    return np.zeros(int(seconds * samplerate), dtype=np.float32)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.say", description="Genera campioni delle voci.")
    ap.add_argument("testo", nargs="?", default=BATTUTA)
    ap.add_argument("--pool", action="store_true", help="tutte le voci del pool")
    ap.add_argument("--scena", action="store_true", help="un dialogo alternato fra le voci")
    ap.add_argument("--backend", default="piper", choices=("piper", "tone"))
    ap.add_argument("--out", default="runs", help="cartella di uscita")
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    args = ap.parse_args(argv)

    cfg = Config().apply(args.overrides)
    out_dir = Path(args.out)

    if args.backend == "tone":
        tts = ToneTts()
    else:
        from speak.backends.piper import PiperTts

        tts = PiperTts(samplerate=cfg.tts.samplerate)

    pool = build_pool(cfg.tts.voices, cfg.tts.pool_size)
    print(f"pool: {len(pool)} voci\n")

    if args.scena:
        pezzi: list[np.ndarray] = []
        for i, riga in enumerate(SCENA):
            voice = pool[i % len(pool)]
            speech = tts.synthesize(riga, voice)
            print(f"  [{voice.voice_id:<16}] {riga}")
            pezzi.append(speech.audio)
            pezzi.append(silenzio(0.35, speech.samplerate))
        path = scrivi_wav(out_dir / "scena.wav", np.concatenate(pezzi), tts.samplerate)
        print(f"\n-> {path}")
        return 0

    if args.pool:
        pezzi = []
        print(f"{'voce':<18} {'base':<24} {'semi':>6} {'durata':>8} {'1o camp':>9} {'RTF':>7}")
        print("-" * 76)
        for voice in pool:
            speech = tts.synthesize(args.testo, voice)
            print(
                f"{voice.voice_id:<18} {voice.base_voice:<24} {voice.semitones:+6.1f} "
                f"{speech.duration:7.2f}s {speech.first_sample_ms:8.1f}ms {speech.rtf:7.3f}"
            )
            pezzi.append(speech.audio)
            pezzi.append(silenzio(0.5, speech.samplerate))
            scrivi_wav(out_dir / f"voce_{voice.voice_id}.wav", speech.audio, speech.samplerate)
        path = scrivi_wav(out_dir / "pool.wav", np.concatenate(pezzi), tts.samplerate)
        print(f"\n-> {path}  (tutte in fila, con mezzo secondo di stacco)")
        return 0

    voice = pool[0]
    speech = tts.synthesize(args.testo, voice)
    path = scrivi_wav(out_dir / "battuta.wav", speech.audio, speech.samplerate)
    print(f"[{voice.voice_id}] {args.testo}")
    print(f"  {speech.duration:.2f}s, primo campione a {speech.first_sample_ms:.1f} ms")
    print(f"-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
