"""Doppia una registrazione su file, senza gioco e senza cattura.

    python -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav --start 1240 --end 1400

Mancava il pezzo che rende la catena intera verificabile a freddo. `replay` fa
girare il solo dominio video e misura; `demo` fa girare la catena completa ma su
una scena finta; `live` fa girare tutto sul vero e richiede il gioco acceso,
VoiceMeeter e le cuffie. Restava scoperto proprio il caso che serve piu' spesso:
**la catena completa sull'audio e sul video veri, ripetibile, mentre si lavora.**

Serve soprattutto a chi parla. Il tracker impara da cio' che sente, quindi il
suo comportamento non si deduce da un gruppo di verifiche su vettori costruiti:
va visto su un dialogo vero, dove i personaggi si alternano, si interrompono e
tornano dopo cinque minuti. E il verdetto, in questo progetto, si da' con le
orecchie: da qui esce un WAV.

**Un avvertimento sulla latenza.** Qui l'orologio e' virtuale, quindi
`latency_ms` non conta il tempo che la sintesi consuma davvero e risulta
migliore del vero. Vale come misura di *decisione*, non di *costo*: per il
secondo c'e' `live_latency_ms`, e per il numero vero c'e' `tools/live.py`.
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import VirtualClock, set_clock  # noqa: E402
from core.config import Config, load_profile  # noqa: E402
from core.pipeline import DubPipeline  # noqa: E402


def scrivi_wav(path: Path, audio: np.ndarray, samplerate: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[:, None]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(audio.shape[1])
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.dub", description="Doppia una registrazione su file, senza gioco."
    )
    ap.add_argument("video")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--out", default="runs/dub", help="cartella di uscita")
    ap.add_argument("--tone", action="store_true", help="voci finte: prova la catena senza TTS")
    ap.add_argument(
        "--mp4",
        action="store_true",
        help="scrivi anche il video con la traccia doppiata, per vedere il sincro",
    )
    ap.add_argument("--mp4-width", type=int, default=1280)
    ap.add_argument(
        "--dump-speaker",
        default=None,
        metavar="PERCORSO",
        help="registra le impronte per il banco (tools.recluster): una passata, mille tarature",
    )
    args = ap.parse_args(argv)

    cfg = (
        load_profile(args.profile, args.overrides)
        if args.profile
        else Config().apply(args.overrides)
    )
    from tools.sources import VideoSource

    source = VideoSource(args.video, fps=cfg.capture.fps, start=args.start, end=args.end)
    if not source.has_audio:
        print(f"{args.video} non ha traccia audio: senza, nessuno sa chi parla", file=sys.stderr)
        return 2
    sr = source.samplerate

    if args.tone:
        from speak.base import ToneTts

        tts = ToneTts()
    elif cfg.tts.backend == "supertonic":
        from speak.backends.supertonic import SupertonicTts

        tts = SupertonicTts(samplerate=cfg.tts.samplerate)
    else:
        from speak.backends.piper import PiperTts

        tts = PiperTts(samplerate=cfg.tts.samplerate)
        print("carico le voci...")
        tts.preload(list(cfg.tts.voices))

    clock = VirtualClock()
    precedente = set_clock(clock)
    pipeline = DubPipeline(cfg, tts, clock=clock, samplerate=sr)
    uscita: list[np.ndarray] = []
    registro = None
    if args.dump_speaker:
        percorso = Path(args.dump_speaker)
        percorso.parent.mkdir(parents=True, exist_ok=True)
        registro = percorso.open("w", encoding="utf-8")
        pipeline.speaker_log = registro

    print(f"doppio {args.start:.0f}s-{args.end if args.end else 'fine'} di {source.info.path.name}\n")
    # **Il tempo parte da zero, non da `--start`.** Il mixer ha un orologio suo
    # che avanza coi campioni versati e comincia sempre a zero: dandogli battute
    # timbrate al minuto 1240 le programma millecentoquaranta secondi nel futuro,
    # e non le versa mai. Il guasto non e' un errore, e' un WAV **identico
    # all'ingresso** mentre i log dicono 46 battute doppiate — cioe' una catena
    # che sembra funzionare e non si sente. Portare tutti i tempi a un'origine
    # comune e' l'unico modo di non doverli riconciliare.
    origine = args.start
    # L'istante del primo frame **davvero emesso**: il seek su H.264 atterra sul
    # keyframe piu' vicino, e il montaggio deve partire da li' o introdurrebbe uno
    # sfasamento suo, che si scambierebbe per uno sfasamento della catena.
    t0_video = args.start
    primo = True
    try:
        for packet in source.packets():
            if primo:
                t0_video = packet.t
                primo = False
            clock.set(packet.t - origine)
            # **L'audio prima del video, come nel banco.** Il blocco audio di un
            # pacchetto comincia all'istante del suo frame: se il dominio video
            # annunciasse la battuta prima che quell'audio sia entrato
            # nell'anello, il tracker deciderebbe su cio' che ha sentito **fino
            # al frame precedente** — trenta millisecondi di parlato in meno
            # proprio dove ce n'e' poco.
            if packet.audio is not None:
                uscita.append(pipeline.on_audio(packet.audio, n=len(packet.audio)))
            if packet.frame is not None:
                for riga in pipeline.on_frame(packet.frame):
                    print(
                        f"  t={riga.t_subtitle + origine:7.1f}s  {riga.speaker_id:>4} -> "
                        f"{riga.voice_id:<14} {riga.duration:4.2f}s  {riga.text[:46]!r}"
                    )
    finally:
        set_clock(precedente)
    pipeline.finish()
    if registro is not None:
        registro.close()
        print(f"\nimpronte registrate in {args.dump_speaker} (-> python -m tools.recluster)")

    mix = np.concatenate(uscita) if uscita else np.zeros((0, 2), np.float32)
    out = Path(args.out)
    path = scrivi_wav(out / "dub.wav", mix, sr)

    # **La verifica che questo file non sia l'originale travestito.** Nata da un
    # difetto vero: la catena riportava 46 battute doppiate e produceva un WAV
    # bit per bit identico all'ingresso. Nessun contatore lo diceva — le battute
    # erano state programmate, semplicemente in un futuro irraggiungibile — e
    # l'unico modo di accorgersene era ascoltare. Una misura che non puo' dire di
    # no non sta misurando: questa puo'.
    from tools.sources import AudioPipe

    pipe = AudioPipe(args.video, samplerate=sr, channels=2, start=args.start, end=args.end)
    originale = pipe.read(len(mix))
    pipe.close()
    n = min(len(mix), len(originale))
    scarto = float(np.abs(mix[:n] - originale[:n]).max()) if n else 0.0
    if scarto < 1e-3:
        print(
            f"\nATTENZIONE: l'uscita e' identica all'audio di gioco (scarto {scarto:.2e}).\n"
            "Nessuna voce italiana e' stata versata. Se i log dicono che le battute\n"
            "sono state doppiate, sono state programmate a un istante che il mixer\n"
            "non raggiunge: e' un disallineamento fra orologi, non un problema di\n"
            "sintesi, e non si vede in nessun contatore.",
            file=sys.stderr,
        )
    else:
        print(f"\nl'uscita differisce dall'audio di gioco (scarto max {scarto:.3f}): la voce c'e'")

    print(f"\n{pipeline.report()}")
    t_emb = pipeline.metrics.timer("speaker.embed")
    if t_emb.count:
        print(f"\nimpronta: {t_emb.count} calcoli, {t_emb.mean:.0f} ms l'uno")
    print(f"\n-> {path}  ({len(mix)/sr:.0f}s)")
    if args.mp4:
        video = monta(args.video, path, out / "dub.mp4", t0_video, len(mix) / sr, args.mp4_width)
        if video is not None:
            print(f"-> {video}")
    return 0


def monta(
    sorgente: str, wav: Path, destinazione: Path, start: float, durata: float, larghezza: int
) -> Path | None:
    """Il video del gioco con la traccia doppiata al posto dell'originale.

    Esiste perche' un errore di sincronizzazione **non si sente**, si vede: la
    voce italiana in ritardo di due decimi somiglia molto a una voce italiana
    puntuale, finche' non si guarda il sottotitolo comparire.

    `start` e' l'istante del **primo frame che la pipeline ha davvero emesso**,
    non quello chiesto sulla riga di comando. Il seek su H.264 atterra sul
    keyframe piu' vicino, e usare il valore chiesto introdurrebbe uno
    sfasamento tutto del montaggio — che si scambierebbe per uno sfasamento
    della catena, cioe' si andrebbe a cercare un difetto dove non c'e'.
    """
    from tools.sources import ffmpeg_exe

    exe = ffmpeg_exe()
    if exe is None:
        print("ffmpeg non disponibile: niente mp4", file=sys.stderr)
        return None
    import subprocess

    cmd = [
        exe, "-hide_banner", "-loglevel", "error", "-y",
        "-accurate_seek", "-ss", f"{start:.6f}", "-i", str(sorgente),
        "-i", str(wav),
        "-map", "0:v:0", "-map", "1:a:0", "-t", f"{durata:.3f}",
        "-vf", f"scale={larghezza}:-2", "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(destinazione),
    ]
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    if subprocess.run(cmd).returncode != 0:
        print("ffmpeg ha fallito il montaggio", file=sys.stderr)
        return None
    return destinazione


if __name__ == "__main__":
    raise SystemExit(main())
