"""Riaprire una sessione: da «qui e' andata male» a quale battuta e perche'.

    python -m tools.reopen runs\\2026-07-28_21-30-00           # il quadro d'insieme
    python -m tools.reopen runs\\2026-07-28_21-30-00 95.4 132  # cosa succedeva li'

E' la meta' che mancava alla prova d'ascolto. Il giudizio dell'orecchio e' il
solo che conta e non e' analizzabile da solo: *«qui la voce e' andata di corsa»*
non dice quale battuta ne' quanto. Con `mix.wav` e `events.jsonl` sulla stessa
scala, un secondo detto a voce diventa una riga con tutti i suoi numeri.

**Il quadro d'insieme si stampa comunque, anche quando si chiede un istante.**
Una battuta storta e' quasi sempre un caso particolare di un difetto generale, e
guardarla da sola invita a curare il sintomo: la compressione satura su *una*
battuta e' sfortuna, satura sul p50 e' il difetto che ha bocciato SuperTonic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load(session: Path) -> list[dict]:
    path = session / "events.jsonl"
    if not path.exists():
        raise SystemExit(f"nessun events.jsonl in {session}")
    return [json.loads(r) for r in path.read_text(encoding="utf-8").splitlines() if r.strip()]


def quadro(righe: list[dict]) -> None:
    """I numeri della sessione, e accanto a ognuno cosa vorrebbe dire se e' alto."""
    dette = [r for r in righe if r.get("kind") != "mark"]
    marks = [r for r in righe if r.get("kind") == "mark"]
    if not dette:
        print("nessuna battuta doppiata in questa sessione")
        return

    rate = np.array([r.get("rate", 1.0) for r in dette])
    lat = np.array([r.get("live_latency_ms", 0.0) for r in dette])
    synth = np.array([r.get("synth_ms", 0.0) for r in dette])
    dur = np.array([r.get("duration", 0.0) for r in dette])
    attesa = np.array([r.get("latency_ms", 0.0) for r in dette])

    print(f"{len(dette)} battute doppiate" + (f", {len(marks)} segnate a mano" if marks else ""))
    print(f"   sintesi        p50 {np.percentile(synth,50):6.0f}  p95 {np.percentile(synth,95):6.0f} ms")
    print(f"   attesa in coda p50 {np.percentile(attesa,50):6.0f}  p95 {np.percentile(attesa,95):6.0f} ms")
    print(f"   latenza totale p50 {np.percentile(lat,50):6.0f}  p95 {np.percentile(lat,95):6.0f} ms")
    print(f"   durata detta   p50 {np.percentile(dur,50):6.2f}  p95 {np.percentile(dur,95):6.2f} s")
    print(f"   compressione   p50 {np.percentile(rate,50):6.3f}  p95 {np.percentile(rate,95):6.3f}")

    # La riga che conta, e il motivo per cui e' scritta cosi'. Una compressione
    # media alta non e' "un po' veloce": e' il segnale che la finestra della
    # battuta e' finita prima che la voce potesse dirla, cioe' che il tempo si
    # sta perdendo altrove — nella sintesi o nella coda.
    sature = float((rate >= 1.34).mean())
    print(f"\n   battute al massimo dell'accelerazione: {sature:.0%}", end="")
    if sature > 0.35:
        print("  <- e' il difetto che ha bocciato SuperTonic:")
        print("      non e' la voce ad andare di corsa, e' la finestra a essere gia' finita.")
        print(f"      guardare dove va il tempo: sintesi p50 {np.percentile(synth,50):.0f} ms, "
              f"attesa p50 {np.percentile(attesa,50):.0f} ms")
    else:
        print(" (sotto la soglia di allarme)")

    voci = {}
    for r in dette:
        voci.setdefault(r.get("voice_id", "?"), []).append(r)
    print(f"\n   voci usate: " + ", ".join(f"{v} x{len(rs)}" for v, rs in sorted(voci.items())))


def istante(righe: list[dict], t: float, raggio: float) -> None:
    """Cosa stava succedendo attorno al secondo `t` del WAV."""
    print(f"\n== attorno a t_wav = {t:.1f}s (+-{raggio:.1f}s) ==")
    vicine = [
        r
        for r in righe
        if r.get("t_wav") is not None and abs(r["t_wav"] - t) <= raggio
    ]
    if not vicine:
        print("   nessuna battuta qui: se l'orecchio ne ha sentita una, non e' passata")
        print("   dalla pipeline — il difetto sta prima, nella lettura o nel tracker.")
        return
    for r in sorted(vicine, key=lambda r: r["t_wav"]):
        if r.get("kind") == "mark":
            print(f"   t={r['t_wav']:7.1f}s  [SEGNATA A MANO] {r.get('nota','')}")
            continue
        print(
            f"   t={r['t_wav']:7.1f}s  [{r.get('cls','?'):5}] [{r.get('voice_id','?'):>12}] "
            f"{r.get('text','')[:60]!r}"
        )
        print(
            f"              sintesi {r.get('synth_ms',0):5.0f} ms   "
            f"attesa {r.get('latency_ms',0):5.0f} ms   "
            f"durata {r.get('duration',0):4.1f}s   "
            f"compressione {r.get('rate',1.0):.3f}"
            + ("  <- satura" if r.get("rate", 1.0) >= 1.34 else "")
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.reopen",
        description="Riapre una sessione salvata da tools.live.",
    )
    ap.add_argument("session", help="cartella runs/<data>")
    ap.add_argument("istanti", nargs="*", type=float, help="secondi nel mix.wav da guardare")
    ap.add_argument("--raggio", type=float, default=4.0, help="quanto guardare attorno")
    args = ap.parse_args(argv)

    session = Path(args.session)
    righe = load(session)
    wav = session / "mix.wav"
    if wav.exists():
        import wave

        with wave.open(str(wav), "rb") as w:
            secondi = w.getnframes() / w.getframerate()
        print(f"{session.name}: {secondi:.0f}s di mix.wav")
    quadro(righe)
    for t in args.istanti:
        istante(righe, t, args.raggio)
    if not args.istanti:
        print("\nper guardare un momento preciso: aggiungi i secondi del mix.wav")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
