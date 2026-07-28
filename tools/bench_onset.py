"""L'onset del parlato coincide con la comparsa del sottotitolo? E di quanto?

    python -m tools.bench_onset gameplay.mp4 --profile gtav --start 1240 --end 1400

E' la misura che viene **prima** di agganciare la voce italiana all'onset. Il
piano dice che l'istante in cui il personaggio apre la bocca e' un ancoraggio
migliore della comparsa del sottotitolo; e' un'ipotesi, e finche' non la si
misura sulla registrazione vera resta tale. Se gli onset del VAD sull'audio di
gioco non hanno niente a che vedere con le battute, agganciarcisi sposterebbe
l'attacco *a caso* — un difetto peggiore di quello che vuole curare, e
indistinguibile da un ritardo generico all'ascolto.

## Perche' la copertura, da sola, non risponde

"Il 90% dei sottotitoli ha un onset vicino" sembra una conferma e non lo e'. Un
gioco d'azione e' pieno di suoni che staccano dal fondo: spari, motori, urti,
musica che entra. Se il VAD apre un segmento ogni due secondi, una finestra di
mezzo secondo intorno a un istante qualunque ne contiene uno quasi sempre, e la
misura restituirebbe 90% anche su tempi inventati. Sarebbe di nuovo una soglia
che si guarda allo specchio.

Quindi qui la copertura si stampa **sempre accanto al suo caso nullo**: la
stessa ricerca fatta su sottotitoli traslati di alcuni secondi, che conservano
il ritmo del dialogo ma non possono piu' essere quelli giusti. La distanza fra
le due e' l'unica cosa che parla. Se coincidono, il segnale non c'e' — e va
saputo prima di scrivere una riga in `core/pipeline.py`, non dopo.

## E il segno conta piu' del modulo

Un onset *prima* del sottotitolo e uno *dopo* chiedono due cose opposte:

- **prima**: il personaggio ha gia' cominciato quando il testo compare. Non si
  puo' tornare indietro, ma la finestra della battuta e' piu' corta di quanto la
  pipeline crede — cioe' si sta comprimendo meno del necessario;
- **dopo**: il testo precede la voce. Qui l'aggancio si puo' usare davvero,
  ritardando l'attacco italiano fino all'onset, e la battuta guadagna il tempo
  di sintesi invece di perderlo.

Sommare i due in un errore assoluto cancella proprio la differenza fra i due
rimedi, ed e' la stessa forma dell'errore corretto in `bench_timing` fra
"in anticipo (innocuo)" e "in ritardo (sfora)".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, load_profile  # noqa: E402
from core.types import SubtitleEvent  # noqa: E402,F401
from listen.vad import Speech, make_vad  # noqa: E402
from mix.center import split  # noqa: E402


def collect(
    path: str, cfg: Config, start: float, end: float | None
) -> tuple[list[SubtitleEvent], list[Speech], float]:
    """Una sola passata: battute dal video, prese di parola dall'audio.

    Le due cose si raccolgono **insieme** e non in due corse, perche' la
    domanda e' su come sono allineate: due esecuzioni separate sullo stesso
    file darebbero gli stessi numeri ma non sarebbero piu' una prova
    dell'allineamento, solo di due elenchi che si somigliano.
    """
    from tools.replay import Replay
    from tools.sources import VideoSource

    source = VideoSource(path, fps=cfg.capture.fps, start=start, end=end)
    if not source.has_audio:
        raise RuntimeError(
            f"{path} non ha traccia audio leggibile: la misura non puo' esprimere la risposta"
        )
    vad = make_vad(cfg.vad, source.samplerate)
    segments: list[Speech] = []

    def on_audio(t: float, block: np.ndarray) -> None:
        # Il dialogo sta al centro: e' la stessa estrazione che usa il duck, e
        # usarne una diversa qui misurerebbe un segnale che la pipeline non
        # vedra' mai.
        mono = split(block)[0] if block.ndim == 2 and block.shape[1] == 2 else block.reshape(-1)
        segments.extend(vad.push(mono, t=t))

    replay = Replay(source, cfg, real=True)
    stats = replay.run(quiet=True, on_audio=on_audio)
    segments.extend(vad.flush())
    return sorted(stats.closed, key=lambda e: e.t_on), segments, stats.media_seconds


def pair(
    events: list[SubtitleEvent], onsets: np.ndarray, pre: float, post: float
) -> np.ndarray:
    """Per ogni battuta lo sfasamento `onset - t_on` piu' vicino, o NaN.

    "Piu' vicino" e non "il primo dopo": l'ipotesi da provare e' che i due
    istanti indichino lo stesso evento, e un evento puo' cadere da entrambe le
    parti. Cercare solo in avanti darebbe una distribuzione tutta positiva per
    costruzione — un'altra misura incapace di dire di no.
    """
    out = np.full(len(events), np.nan)
    if onsets.size == 0:
        return out
    for i, e in enumerate(events):
        d = onsets - e.t_on
        d = d[(d >= -pre) & (d <= post)]
        if d.size:
            out[i] = d[np.argmin(np.abs(d))]
    return out


def describe(name: str, delta: np.ndarray) -> float:
    """Stampa la riga e restituisce la copertura, che serve al confronto."""
    found = ~np.isnan(delta)
    cover = float(found.mean()) if delta.size else 0.0
    if not found.any():
        print(f"   {name:26} {cover:6.1%}  (nessun accoppiamento)")
        return cover
    d = delta[found]
    print(
        f"   {name:26} {cover:6.1%}  |sfasamento| p50 {np.median(np.abs(d)):5.2f}s   "
        f"p50 {np.percentile(d,50):+5.2f}  p10 {np.percentile(d,10):+5.2f}  "
        f"p90 {np.percentile(d,90):+5.2f}"
    )
    return cover


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.bench_onset",
        description="L'onset del VAD e' un ancoraggio migliore della comparsa del sottotitolo?",
    )
    ap.add_argument("video", help="registrazione con traccia audio")
    ap.add_argument("--profile", default=None, help="profilo del gioco")
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--pre", type=float, default=1.0, help="quanto cercare PRIMA del sottotitolo")
    ap.add_argument("--post", type=float, default=1.0, help="e quanto DOPO")
    args = ap.parse_args(argv)

    cfg = (
        load_profile(args.profile, args.overrides)
        if args.profile
        else Config().apply(args.overrides)
    )
    events, segments, media = collect(args.video, cfg, args.start, args.end)
    if len(events) < 10:
        print(f"troppe poche battute: {len(events)}", file=sys.stderr)
        return 2

    onsets = np.array([s.t0 for s in segments], dtype=float)
    parlato = sum((s.duration or 0.0) for s in segments)

    # Il denominatore, prima di tutto. Se il VAD parla quasi sempre, qualunque
    # copertura qui sotto e' garantita e non significa niente: e' il numero che
    # rende leggibile ogni riga che segue.
    print(f"{len(events)} battute chiuse in {media:.0f}s di media, backend VAD '{cfg.vad.backend}'")
    print(
        f"prese di parola: {len(segments)}  ({60*len(segments)/max(media,1e-9):.1f} al minuto, "
        f"durata p50 {np.median([s.duration or 0.0 for s in segments]):.2f}s)"
    )
    print(f"il VAD dichiara parlato per il {parlato/max(media,1e-9):6.1%} del tempo")

    # **La larghezza della finestra non e' un dettaglio della misura: e' la
    # misura.** Con una finestra larga la copertura sale sempre, anche sui tempi
    # finti, e le due curve si toccano; il numero che parla e' l'eccesso sul
    # caso, e dove quell'eccesso e' massimo sta l'ancoraggio. Una soglia sola
    # avrebbe risposto "non c'e' segnale" a +-1 s e "c'e'" a +-0,2 s sugli
    # stessi dati — cioe' avrebbe descritto la finestra scelta, non l'audio.
    print("\n== eccesso sul caso, in funzione della finestra ==")
    print("   semilarghezza   vere   caso   eccesso")
    migliore = (0.0, -1.0)
    for w in (0.10, 0.15, 0.20, 0.30, 0.50, 0.75, 1.00):
        cover = float((~np.isnan(pair(events, onsets, w, w))).mean())
        # Tre traslazioni invece di una: una sola potrebbe cadere per sfortuna
        # in un tratto muto e far sembrare il segnale piu' forte di com'e'. Si
        # traslano gli **onset**, che e' la stessa cosa a segno invertito e non
        # richiede di fabbricare battute con `t_on` spostato e `t_off` fermo —
        # una durata assurda che finirebbe prima o poi in una misura che la
        # crede vera.
        atteso = float(
            np.mean([(~np.isnan(pair(events, onsets + s, w, w))).mean() for s in (-11.0, 7.0, 23.0)])
        )
        segno = "  <-" if cover - atteso > migliore[1] else ""
        if cover - atteso > migliore[1]:
            migliore = (w, cover - atteso)
        print(f"   +-{w:4.2f}s      {cover:6.1%} {atteso:6.1%}   {cover-atteso:+6.1%}{segno}")

    w, eccesso = migliore
    print(f"\n   eccesso massimo a +-{w:.2f}s: {eccesso:+.1%}")
    if eccesso < 0.10:
        print("   NON c'e' segnale a nessuna larghezza. L'onset del VAD non sa dire")
        print("   dov'e' la battuta: agganciarcisi sposterebbe l'attacco a caso, e")
        print("   prima di riusarlo va cambiato il rilevatore, non il modo di usarlo.")
    else:
        print(f"   Il segnale c'e', ed e' concentrato: l'onset vale come ancoraggio solo")
        print(f"   dentro +-{w:.2f}s dal sottotitolo, e su una battuta su "
              f"{1/max(eccesso,1e-9):.0f} circa.")

    print(f"\n== accoppiamento in [-{args.pre:.1f}, +{args.post:.1f}] s ==")
    vero = pair(events, onsets, args.pre, args.post)
    describe("battute vere", vero)
    print("   -- e le stesse battute spostate, che non possono piu' essere quelle giuste --")
    for shift in (-11.0, 7.0, 23.0):
        describe(f"traslate di {-shift:+.0f}s", pair(events, onsets + shift, args.pre, args.post))

    # E il segno, che decide quale dei due rimedi e' quello utile.
    found = ~np.isnan(vero)
    if found.any():
        d = vero[found]
        prima, dopo = d[d < 0], d[d >= 0]
        print(f"\n== da che parte cade, sulle {found.sum()} accoppiate ==")
        print(
            f"   onset PRIMA del sottotitolo: {len(prima)/len(d):6.1%}  "
            f"(la finestra e' piu' corta di quanto si crede, p50 {np.median(-prima) if len(prima) else 0:.2f}s)"
        )
        print(
            f"   onset DOPO il sottotitolo:   {len(dopo)/len(d):6.1%}  "
            f"(qui l'attacco si puo' ritardare, p50 {np.median(dopo) if len(dopo) else 0:.2f}s)"
        )
        print(f"\n   sfasamento mediano complessivo: {np.median(d):+.3f}s")
        print(f"   dispersione (p90-p10): {np.percentile(d,90)-np.percentile(d,10):.3f}s")
        print(
            "\n   La dispersione conta piu' della mediana: uno sfasamento costante e' un\n"
            "   `lead_ms` da scrivere nel profilo, uno sparso non e' un ancoraggio."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
