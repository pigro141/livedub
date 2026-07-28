"""Il doppiaggio dal vivo: schermo dentro, voce italiana fuori.

    python -m tools.live --profile live --loopback voicemeeter --seconds 60

E' la prima volta che la catena serve a qualcosa invece che a essere misurata.
Prende i frame dallo schermo, legge i sottotitoli, li fa dire a una voce
italiana, e li mescola all'audio del gioco abbassandone il centro mentre parla.

## Due domini, due thread, e il motivo

L'audio non puo' aspettare. Un blocco perso e' un buco che si sente, mentre un
frame perso non lo nota nessuno — e la sintesi di una battuta costa decine di
millisecondi, cioe' diversi blocchi audio. Se stessero nello stesso ciclo, ogni
battuta doppiata produrrebbe un salto nel suono del gioco.

Quindi: **il thread audio non fa mai niente di lento**. Legge un blocco dal
loopback, lo passa al mixer, scrive il risultato. Il thread video fa tutto il
resto — cattura, OCR, sintesi — e comunica col mixer solo mettendo battute in
coda.

Il coordinamento sta **dentro il mixer**, attorno alla sola coda, e questa
frase e' costata una misura: il primo tentativo aveva un lucchetto attorno
all'intero passo video, e il thread audio e' rimasto fermo 1,9 secondi mentre
Piper sintetizzava una battuta lunga. Il commento diceva "il thread audio non fa
mai niente di lento" ed era vero; era il lucchetto a farglielo aspettare. Un
buco di due secondi nel suono del gioco non e' un dettaglio di implementazione.

**L'orologio del mixer avanza con l'audio processato**, non col tempo di sistema:
in tempo reale sono la stessa cosa, ma se la scheda audio rallenta e' l'audio ad
avere ragione, perche' e' lui che l'orecchio sente.

## Perche' catturare e suonare su due dispositivi diversi non e' un dettaglio

Se si cattura lo stesso dispositivo su cui si suona, il doppiaggio rientra,
viene ri-doppiato, e si ottiene un fischio. Qui si cattura VoiceMeeter — dove
entra il gioco — e si suona sull'uscita predefinita di Windows, che sono due
percorsi separati.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.audio import Loopback, Player, find_loopback, list_devices  # noqa: E402
from capture.screen import make_screen  # noqa: E402
from core.clock import RealClock, set_clock  # noqa: E402
from core.config import Config, load_profile  # noqa: E402
from core.pipeline import DubPipeline  # noqa: E402
from speak.base import ToneTts  # noqa: E402
from tools.session import Session  # noqa: E402


def costruisci_tts(nome: str, cfg):
    """Il backend di sintesi. `tone` non e' un ripiego, e' uno strumento: fa
    sentire il *tempo* del doppiaggio senza il costo della voce vera, ed e' il
    modo di capire se un problema e' di ritmo o di sintesi."""
    if nome == "tone":
        return ToneTts()
    if nome == "supertonic":
        from speak.backends.supertonic import SupertonicTts

        return SupertonicTts(
            samplerate=cfg.tts.samplerate, steps=cfg.tts.steps, speed=cfg.tts.speed
        )
    from speak.backends.piper import PiperTts

    return PiperTts(samplerate=cfg.tts.samplerate)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.live", description="Doppiaggio dal vivo: schermo dentro, voce fuori."
    )
    ap.add_argument("--profile", default=None, help="profilo del gioco (ROI e soglie)")
    ap.add_argument("--loopback", default="voicemeeter", help="pezzo di nome del device da catturare")
    ap.add_argument("--output", default=None, help="device di uscita (senza: la predefinita)")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--delay", type=float, default=10.0, help="tempo per portare il gioco davanti")
    ap.add_argument("--block", type=int, default=480, help="campioni per blocco (480 = 10 ms)")
    ap.add_argument("--backend", default="auto", help="cattura schermo: auto | dxcam | mss")
    ap.add_argument("--monitor", type=int, default=1)
    ap.add_argument("--tts", default=None, help="backend TTS (senza: quello di config)")
    ap.add_argument("--devices", action="store_true", help="elenca i device audio e basta")
    ap.add_argument(
        "--no-save",
        action="store_true",
        help="non registrare la sessione (senza, salva mix.wav + events.jsonl in runs/)",
    )
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    args = ap.parse_args(argv)

    if args.devices:
        loops, default = list_devices()
        print("loopback disponibili (si cattura da qui):")
        for d in loops:
            print(f"  {d}")
        print(f"\nuscita predefinita di Windows: {default}")
        return 0

    cfg = load_profile(args.profile, args.overrides) if args.profile else Config().apply(args.overrides)
    if args.tts:
        cfg.tts.backend = args.tts
    set_clock(RealClock())

    loops, default = list_devices()
    entrata = find_loopback(args.loopback)
    uscita = default
    if args.output:
        cercato = [d for d in loops if args.output.lower() in d.name.lower()]
        uscita = cercato[0] if cercato else default
    if entrata.index == uscita.index:
        print("! cattura e uscita sono lo stesso dispositivo: il doppiaggio rientrerebbe")
        return 2

    print(f"catturo:  {entrata}")
    print(f"suono su: {uscita}")

    sr = 48000
    tts = costruisci_tts(cfg.tts.backend, cfg)
    pipeline = DubPipeline(cfg, tts, samplerate=sr)
    # Si registra per difetto. Una prova d'ascolto senza artefatti produce
    # impressioni, e un'impressione non si riapre: la sessione che ha bocciato
    # SuperTonic aveva il numero colpevole in bella vista, e sembrava innocuo
    # finche' non lo si e' messo accanto a cio' che l'orecchio aveva sentito.
    sessione = None if args.no_save else Session(samplerate=sr)
    print(f"TTS: {cfg.tts.backend}   voci nel pool: {len(pipeline.pool)}")
    print(f"profilo: {args.profile or '(default)'}   ROI {cfg.vision.roi}")

    # Nessun lucchetto qui: sta dentro il mixer, attorno alla sola coda. Il
    # primo tentativo ne aveva uno attorno all'intero passo video, e il thread
    # audio e' rimasto fermo 1,9 secondi mentre Piper sintetizzava una battuta
    # lunga — la misura ha trovato subito il difetto che il commento del codice
    # dichiarava impossibile.
    stop = threading.Event()
    # Il video non comincia finche' l'audio non e' partito: un frame letto
    # prima verrebbe programmato su una linea temporale che non esiste ancora.
    pronto = threading.Event()
    stat = {"blocchi": 0, "frame": 0, "underrun": 0, "audio_ms": [], "video_ms": []}
    t_avvio = time.perf_counter()  # origine dei tempi stampati nel log

    def ciclo_audio() -> None:
        """Non fa mai niente di lento: legge, mescola, scrive."""
        with Loopback(entrata, block=args.block, samplerate=sr) as ingresso, Player(
            uscita, block=args.block, samplerate=sr
        ) as altoparlanti:
            # Qui, e non prima: l'orologio del mixer deve partire quando parte
            # l'audio vero, altrimenti tutto cio' che viene programmato nasce
            # gia' in ritardo di quanto c'e' voluto ad arrivare fin qui.
            pipeline.start_live()
            pronto.set()
            while not stop.is_set():
                gioco = ingresso.read()
                t0 = time.perf_counter()
                # L'istante si prende **prima** di processare, ed e' quello del
                # mixer: e' la scala su cui vivono gli istanti delle battute, e
                # usare `perf_counter` qui rimetterebbe due origini diverse
                # esattamente dove il progetto le ha gia' pagate una volta.
                quando = pipeline.mixer.now
                fuori = pipeline.on_audio(gioco, n=len(gioco))
                stat["audio_ms"].append((time.perf_counter() - t0) * 1000.0)
                altoparlanti.write(fuori)
                if sessione is not None:
                    sessione.audio(fuori, quando)
                stat["blocchi"] += 1

    def ciclo_video() -> None:
        """Tutto cio' che e' lento sta qui: cattura, OCR, sintesi."""
        schermo = make_screen(args.backend, monitor=args.monitor)
        pronto.wait(timeout=10.0)
        periodo = 1.0 / max(1e-6, cfg.capture.fps)
        prossimo = time.perf_counter()
        try:
            while not stop.is_set():
                ora = time.perf_counter()
                if ora < prossimo:
                    time.sleep(min(0.002, prossimo - ora))
                    continue
                prossimo += periodo
                g = schermo.grab()
                if not g.ok:
                    continue
                t0 = time.perf_counter()
                dette = pipeline.on_frame(g.frame)
                stat["video_ms"].append((time.perf_counter() - t0) * 1000.0)
                stat["frame"] += 1
                for riga in dette:
                    if sessione is not None:
                        sessione.line(riga)
                    # L'istante serve: senza, una battuta strana non si puo'
                    # collocare nella sessione. Una riga grigia comparsa nei
                    # primi secondi puo' essere il terminale ancora in primo
                    # piano, e una comparsa a meta' e' un fatto del gioco — sono
                    # due cose diverse che nel log sembravano identiche.
                    # Quando si registra, l'istante stampato e' la **posizione
                    # nel WAV**: cosi' una battuta segnalata a voce durante la
                    # prova si riapre con un `seek` invece che con una sottrazione
                    # fra due orologi.
                    quando = (
                        riga.t_scheduled - sessione.t0
                        if sessione is not None and sessione.t0 is not None
                        else time.perf_counter() - t_avvio
                    )
                    print(
                        f"  [{quando:6.1f}s] [{riga.cls:5}] [{riga.voice_id:>12}] "
                        f"{riga.text[:56]!r}  sintesi {riga.synth_ms:.0f} ms, "
                        f"attesa {(riga.t_scheduled - riga.t_subtitle)*1000:.0f} ms, "
                        f"durata {riga.duration:.1f}s"
                    )
        finally:
            schermo.close()

    if args.delay > 0:
        print(f"\n>>> {args.delay:.0f} secondi per portare il gioco in primo piano...")
        time.sleep(args.delay)
        print(">>> doppiaggio attivo\n")

    thread_audio = threading.Thread(target=ciclo_audio, name="audio", daemon=True)
    thread_video = threading.Thread(target=ciclo_video, name="video", daemon=True)
    thread_audio.start()
    thread_video.start()
    try:
        stop.wait(args.seconds)
    except KeyboardInterrupt:
        pass
    stop.set()
    thread_video.join(timeout=3)
    thread_audio.join(timeout=3)

    pipeline.finish()

    durata = stat["blocchi"] * args.block / sr
    print(f"\naudio: {stat['blocchi']} blocchi = {durata:.1f}s")
    print(f"video: {stat['frame']} frame")
    for nome in ("audio_ms", "video_ms"):
        v = np.asarray(stat[nome]) if stat[nome] else np.zeros(1)
        print(f"  {nome:9} p50 {np.percentile(v,50):6.2f}  p95 {np.percentile(v,95):7.2f}  "
              f"max {v.max():7.2f} ms")
    print()
    report = pipeline.report()
    print(report)
    if sessione is not None:
        dove = sessione.close(cfg, report)
        print(f"\nsessione salvata -> {dove}")
        print("   mix.wav  events.jsonl  config.json  report.txt")
        print("   una battuta storta si riapre col secondo stampato qui sopra:")
        print(f"   .\\.venv\\Scripts\\python.exe -m tools.reopen {dove} 95.4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
