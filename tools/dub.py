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
import json
import sys
import time
import wave
from dataclasses import asdict
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
        "--tempo-reale",
        action="store_true",
        help="conta il costo del lavoro nel tempo del media, e salta i frame arretrati come dal vivo",
    )
    ap.add_argument(
        "--mp4-nudo",
        action="store_true",
        help="niente banda coi sottotitoli letti: solo gioco e voce",
    )
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

        # `steps` e `speed` vanno passati: senza, `--set tts.speed=...` non
        # arrivava al modello e il banco misurava una configurazione diversa da
        # quella che diceva di misurare — mentre `tools/live.py` li passa da
        # sempre, quindi banco e vivo giravano con due velocita' diverse.
        tts = SupertonicTts(
            samplerate=cfg.tts.samplerate, steps=cfg.tts.steps, speed=cfg.tts.speed
        )
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
    if not args.dump_speaker:
        # La traccia costa una riga a battuta e risponde alla domanda che viene
        # sempre — "in che punto banco e vivo divergono?" — quindi si scrive
        # sempre, accanto agli altri file della prova.
        Path(args.out).mkdir(parents=True, exist_ok=True)
        args.dump_speaker = str(Path(args.out) / "speaker.jsonl")
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
    # **Il costo del lavoro, contato dentro il tempo del media.**
    #
    # Con l'orologio virtuale la sintesi e' gratis: mentre SuperTonic lavora per
    # trecento millisecondi veri il tempo del banco sta fermo, e la battuta
    # risulta programmata come se fosse nata istantanea. E' il motivo per cui il
    # banco dava 567 ms di latenza dove il vivo, sulla stessa scena e con le
    # stesse voci, ne dava 951: **la differenza era tutta e sola la sintesi**,
    # 363 ms, piu' la coda che ne consegue.
    #
    # Non e' una sfumatura: e' che il banco prometteva un doppiaggio
    # irraggiungibile, e un file approvato all'ascolto mandava a cercare dal vivo
    # un difetto che non c'era. Qui il tempo speso a lavorare si somma al tempo
    # del media, e i frame arretrati si **saltano** invece di essere lavorati in
    # ritardo — come fa il ciclo dal vivo. L'audio invece si versa sempre, perche'
    # il thread audio dal vivo non salta niente: e' proprio da quell'asimmetria
    # che nasce il ritardo dell'anello.
    #
    # Resta deterministico e ripetibile — il costo si misura, non si simula — a
    # differenza di far girare la catena a tempo vero, che dipenderebbe da cosa
    # sta facendo la macchina in quel momento.
    lavoro = 0.0
    saltati = 0
    try:
        for packet in source.packets():
            if primo:
                t0_video = packet.t
                primo = False
            t_ciclo = time.perf_counter()
            clock.set(packet.t - origine + lavoro)
            # **L'audio prima del video, come nel banco.** Il blocco audio di un
            # pacchetto comincia all'istante del suo frame: se il dominio video
            # annunciasse la battuta prima che quell'audio sia entrato
            # nell'anello, il tracker deciderebbe su cio' che ha sentito **fino
            # al frame precedente** — trenta millisecondi di parlato in meno
            # proprio dove ce n'e' poco.
            if packet.audio is not None:
                uscita.append(pipeline.on_audio(packet.audio, n=len(packet.audio)))
            # Un frame arretrato non serve a vedere se **adesso** c'e' un
            # sottotitolo: si salta, come dal vivo.
            arretrato = args.tempo_reale and lavoro > 1.5 / max(1e-6, cfg.capture.fps)
            if packet.frame is not None and not arretrato:
                for riga in pipeline.on_frame(packet.frame):
                    print(
                        f"  t={riga.t_subtitle + origine:7.1f}s  {riga.speaker_id:>4} -> "
                        f"{riga.voice_id:<14} {riga.duration:4.2f}s  {riga.text[:46]!r}"
                    )
            elif packet.frame is not None:
                saltati += 1
            if args.tempo_reale:
                speso = time.perf_counter() - t_ciclo
                # Il tempo del pacchetto avanza da solo: si accumula solo cio'
                # che si e' speso **oltre** il suo ritmo, cioe' il vero arretrato.
                lavoro = max(0.0, lavoro + speso - 1.0 / max(1e-6, cfg.capture.fps))
    finally:
        set_clock(precedente)
    pipeline.finish()
    if registro is not None:
        registro.close()
        print(f"\nimpronte registrate in {args.dump_speaker} (-> python -m tools.recluster)")

    mix = np.concatenate(uscita) if uscita else np.zeros((0, 2), np.float32)
    out = Path(args.out)
    path = scrivi_wav(out / "dub.wav", mix, sr)

    # **La stessa forma di una sessione dal vivo**, cosi' `tools.reopen` legge
    # anche le prove sul banco. Non e' comodita': una prova che si guarda con uno
    # strumento diverso da quello del vivo si finisce per confrontarla con misure
    # calcolate in un altro modo, e la differenza fra le due passa per un
    # risultato. Qui `t_wav` e' il secondo dentro `dub.wav`, che parte da zero
    # come il mixer.
    eventi = out / "events.jsonl"
    with eventi.open("w", encoding="utf-8") as f:
        for riga in pipeline.spoken:
            record = asdict(riga)
            record["t_wav"] = round(riga.t_scheduled, 3)
            record["latency_ms"] = round(riga.latency_ms, 1)
            record["live_latency_ms"] = round(riga.live_latency_ms, 1)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    cfg.save(out / "config.json")

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
    print(f"-> {eventi}   (si rilegge con: python -m tools.reopen {out})")
    if args.tempo_reale:
        print(f"\ntempo reale: {saltati} frame saltati perche' arretrati")
    if args.mp4:
        ass = scrivi_sottotitoli(pipeline.spoken, out / "letto.ass", args.mp4_width)
        video = monta(
            args.video,
            path,
            out / "dub.mp4",
            t0_video,
            len(mix) / sr,
            args.mp4_width,
            sottotitoli=None if args.mp4_nudo else ass,
        )
        if video is not None:
            print(f"-> {video}")
    return 0


def _ass_tempo(s: float) -> str:
    s = max(0.0, s)
    ore, resto = divmod(s, 3600)
    minuti, secondi = divmod(resto, 60)
    return f"{int(ore)}:{int(minuti):02d}:{secondi:05.2f}"


def scrivi_sottotitoli(righe: list, destinazione: Path, larghezza: int) -> Path:
    """I sottotitoli **letti dall'OCR**, in una banda nera sopra il gioco.

    Non sono i sottotitoli del gioco: sono cio' che la catena ha letto e mandato
    al sintetizzatore. E' l'unico modo di rispondere alla domanda che viene
    sempre per prima quando una battuta suona sbagliata — *ha sbagliato a
    leggere, o ha sbagliato a dire?* — e per rispondere non serve fermare niente,
    basta guardare il video.

    Accanto al testo va il nome della voce: cosi' si vede anche a chi la catena
    ha attribuito la battuta, nello stesso istante in cui la si sente.
    """
    testa = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {larghezza}
PlayResY: {int(larghezza * 9 / 16)}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ocr,Consolas,{max(14, larghezza // 44)},&H00FFFFFF,&HFF000000,0,4,3,0,8,20,20,8,1

[Events]
Format: Layer, Start, End, Style, Text
"""
    eventi = []
    for r in righe:
        inizio = r.t_scheduled
        fine = inizio + max(r.duration, 0.8)
        testo = r.text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")
        eventi.append(
            f"Dialogue: 0,{_ass_tempo(inizio)},{_ass_tempo(fine)},ocr,,"
            f"[{r.voice_id}] {testo}"
        )
    destinazione.write_text(testa + "\n".join(eventi) + "\n", encoding="utf-8")
    return destinazione


def _filtro_video(larghezza: int, sottotitoli: Path | None) -> str:
    """Scala, e se ci sono i sottotitoli aggiunge la fascia nera in alto.

    La fascia si ottiene allargando il fotogramma verso l'alto (`pad`) invece di
    coprire il gioco: il testo letto e il gioco vanno guardati insieme, e uno
    sopra l'altro renderebbe illeggibile proprio la parte inquadrata dalla ROI.
    """
    base = f"scale={larghezza}:-2"
    if sottotitoli is None:
        return base
    alta = max(64, larghezza // 12)
    # ffmpeg vuole il percorso con le barre in avanti e i due punti protetti.
    via = str(sottotitoli.resolve()).replace("\\", "/").replace(":", "\:")
    return (
        f"{base},pad=iw:ih+{alta}:0:{alta}:black,"
        f"subtitles='{via}':force_style='MarginV=10'"
    )


def monta(
    sorgente: str,
    wav: Path,
    destinazione: Path,
    start: float,
    durata: float,
    larghezza: int,
    sottotitoli: Path | None = None,
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
        "-vf", _filtro_video(larghezza, sottotitoli), "-r", "30",
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
