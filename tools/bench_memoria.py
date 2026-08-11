"""La memoria cresce durante una sessione lunga?

    .\\.venv\\Scripts\\python.exe -m tools.bench_memoria --battute 4000

E' la domanda 92 di `DOMANDE_PRODUZIONE.md`, e la piu' importante delle
ventinove mai provate: una partita dura tre ore, tutte le misure archiviate di
questo progetto durano minuti. Un programma che perde memoria non da' nessun
segnale finche' non li da' tutti insieme.

**Non serve aspettare tre ore, e questo e' il punto del banco.** La catena non sa
che ora e': una sessione dal vivo di tre ore sono circa 3600 battute (misurato:
58 battute in 3 minuti, cioe' ~19 al minuto). Farne quattromila qui costa
qualche minuto, e la crescita di memoria dipende da **quante battute** sono
passate, non da quanto e' durato l'orologio.

**La soglia si dichiara prima della prova**, se no si guarda il numero e si
decide dopo se e' accettabile — che e' il modo in cui questo progetto si e' gia'
raccontato un risultato. **Sopra +50 MB su tremilaseicento battute e' un
difetto**: sono venti volte quello che serve a tenere le identita' di sedici
personaggi, e su un PC con 8 GB accanto a un gioco si sente.

E si misura anche **cosa** cresce, non solo quanto: la memoria e' un totale, e un
totale non dice mai dove andare a guardare.
"""

from __future__ import annotations

import argparse
import gc
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import VirtualClock, set_clock  # noqa: E402
from core.config import Config  # noqa: E402
from core.pipeline import DubPipeline  # noqa: E402
from core.types import LineClass, SubtitleEvent  # noqa: E402
from speak.base import make_tts  # noqa: E402


def memoria_mb() -> float:
    """Quanta memoria sta usando questo processo, in MB.

    Senza `psutil` — che non e' fra le dipendenze e non vale la pena aggiungerlo
    per una riga — si chiede a Windows con `GetProcessMemoryInfo`.
    """
    import ctypes
    from ctypes import wintypes

    class CONTATORI(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    # **`K32GetProcessMemoryInfo` di kernel32, non `psapi.GetProcessMemoryInfo`.**
    # La prima versione chiamava la seconda senza dichiarare i tipi degli
    # argomenti: la chiamata non solleva, torna zero, e la prova stampava
    # `0.0 MB` per un processo Python — che ne usa trenta prima ancora di
    # importare qualcosa. Un numero impossibile e' piu' utile di un numero
    # sbagliato, e questo lo era in modo cosi' evidente da non poter passare.
    fn = ctypes.windll.kernel32.K32GetProcessMemoryInfo
    fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(CONTATORI), wintypes.DWORD]
    fn.restype = wintypes.BOOL
    c = CONTATORI()
    c.cb = ctypes.sizeof(c)
    if not fn(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        raise OSError("GetProcessMemoryInfo non ha risposto: la prova non puo' misurare")
    return c.WorkingSetSize / (1024 * 1024)


def quanti_oggetti() -> dict[str, int]:
    """Quanti oggetti vivi per tipo, fra quelli che possono accumularsi.

    **Il totale della memoria non dice mai dove guardare.** Contare gli oggetti
    per tipo si': se crescono i `SubtitleEvent`, il difetto sta in chi li tiene
    in coda; se crescono gli `ndarray`, sta nell'audio.
    """
    conta: dict[str, int] = {}
    for o in gc.get_objects():
        nome = type(o).__name__
        if nome in ("SubtitleEvent", "SpokenLine", "ndarray", "Utterance", "dict", "list"):
            conta[nome] = conta.get(nome, 0) + 1
    return conta


def prova(battute: int, verboso: bool = True) -> dict:
    cfg = Config()
    cfg.tts.backend = "tone"  # deterministico e senza modelli: qui si misura la catena
    cfg.speaker.backend = "none"
    cfg.vad.backend = "energy"
    cfg.vision.use_lexicon = False
    cfg.speaker.decide_after_ms = 0
    cfg.speaker.max_wait_ms = 0
    cfg.ui.save_mix = False

    orologio = VirtualClock()
    set_clock(orologio)
    catena = DubPipeline(cfg, make_tts(cfg.tts), clock=orologio, samplerate=48000)
    catena.start_live(warmup=False)

    blocco = np.zeros((480, 2), np.float32)
    scie: list[tuple[int, float]] = []
    base = None
    passo = max(1, battute // 20)

    for i in range(battute):
        t = i * 3.0  # una battuta ogni tre secondi, come una conversazione vera
        orologio.set(t)
        ev = SubtitleEvent(
            text=f"Battuta numero {i}, di quelle che si dicono guidando.",
            cls=LineClass.WHITE, t_on=t,
        )
        catena._speak(ev)
        # L'anello audio gira comunque: e' li' che vivono i campioni.
        for _ in range(20):
            catena.on_audio(blocco, n=len(blocco))
        if i % passo == 0:
            gc.collect()
            m = memoria_mb()
            if base is None:
                base = m
            scie.append((i, m))
            if verboso:
                print(f"  {i:6}  {m:8.1f} MB   {m - base:+7.1f}")

    gc.collect()
    fine = memoria_mb()
    return {
        "battute": battute,
        "inizio_mb": base or 0.0,
        "fine_mb": fine,
        "crescita_mb": fine - (base or 0.0),
        "scie": scie,
        "oggetti": quanti_oggetti(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.bench_memoria")
    ap.add_argument("--battute", type=int, default=3600,
                    help="3600 = circa tre ore di gioco (misurato: ~19 battute al minuto)")
    ap.add_argument("--tetto", type=float, default=50.0,
                    help="MB di crescita oltre i quali e' un difetto (dichiarato prima)")
    args = ap.parse_args(argv)

    print(f"tre ore di gioco = ~3600 battute. Ne faccio {args.battute}.")
    print(f"soglia dichiarata: +{args.tetto:.0f} MB\n")
    esito = prova(args.battute)
    print(f"\n  inizio   {esito['inizio_mb']:.1f} MB")
    print(f"  fine     {esito['fine_mb']:.1f} MB")
    print(f"  crescita {esito['crescita_mb']:+.1f} MB")
    print(f"\n  oggetti vivi: {esito['oggetti']}")
    if esito["crescita_mb"] > args.tetto:
        print(f"\n! sopra la soglia: e' un difetto, non un margine")
        return 1
    print(f"\n  sotto la soglia dichiarata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
