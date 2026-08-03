"""Il doppiaggio rallenta su un PC vecchio? Si risponde da qui.

La voce della lista diceva «non provabile qui, serve l'altro PC». È vero solo per
metà: un PC vecchio è **due cose diverse insieme** — meno core e core più lenti —
e la prima si simula su questa macchina restringendo l'affinità del processo.

## Perché non basta cronometrare e basta

La lezione della prova hardware di Qwen: la domanda utile non è «va più piano?» ma
**da cosa dipende il costo**. Se la sintesi scala con i core, un quattro core del
2015 costa il doppio di otto e la stima si fa; se non scala affatto, i core non
c'entrano e conta solo il clock, che è un fattore molto più piccolo. Sono due
risposte opposte e si distinguono con una misura sola.

## Come si simula

`SetProcessAffinityMask` prima che ONNX Runtime costruisca le sessioni — ORT
guarda i processori disponibili **una volta**, al momento della sessione, quindi
l'affinità va imposta all'avvio del processo. Per questo ogni punto della curva è
un processo suo, e non un ciclo dentro lo stesso.

**Cosa questo NON simula**, e va detto: core più lenti (IPC e frequenza), memoria
più lenta, e un disco più lento al primo caricamento. Il numero che esce è quindi
un **limite inferiore** al rallentamento di una macchina vecchia: se già a core
ridotti non ci sta, su un PC vero sta peggio.

## Uso

    .\\.venv\\Scripts\\python.exe -m tools.bench_cpu                 # la curva intera
    .\\.venv\\Scripts\\python.exe -m tools.bench_cpu --cores 4       # un punto solo
    .\\.venv\\Scripts\\python.exe -m tools.bench_cpu --backend piper
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time

# Battute vere della registrazione: lunghezze diverse, come in scena.
FRASI = [
    "Come va, bello?",
    "Non ho mai avuto un figlio nero,",
    "ma se ne avessi uno vorrei che fosse come te.",
    "Oggi recuperiamo veicoli acquistati da idioti a tassi d'interesse alti.",
    "Mi prendi per il culo, vero?",
    "Amico, ci prende per il culo tutti e due.",
]


def limita_core(n: int) -> int:
    """Restringe il processo a `n` **core fisici**. Torna quanti ne ha.

    Va chiamata **prima** di costruire qualunque sessione ONNX: il pool di thread
    di ORT si dimensiona alla creazione della sessione, quindi un'affinità imposta
    dopo non cambia più niente e la misura direbbe di aver simulato qualcosa che
    non ha simulato — il difetto del trattamento non applicato, che qui è già
    costato due letture pulite e false.

    **Fisici, non logici, e la differenza ha già falsato una curva.** La prima
    versione mascherava i primi `n` processori *logici*: su una macchina con
    hyper-threading Windows li enumera a coppie sullo stesso core, quindi «8»
    prendeva due thread di quattro core soli. La curva usciva plausibile — il
    costo saliva — ma ogni etichetta era sbagliata di un fattore due, e «un PC a
    quattro core» sarebbe stato attribuito al numero di un PC a due. Un PC vecchio
    ha meno **core**, non meno thread: si prende un logico ogni due.
    """
    if n <= 0 or os.name != "nt":
        return os.cpu_count() or 1
    from ctypes import wintypes

    # **Gli `argtypes` non sono pignoleria qui.** Senza, ctypes passa la maschera
    # come `int` a 32 bit e l'handle come intero: su Windows a 64 bit la chiamata
    # fallisce e basta. Fallire e' il caso fortunato — se fosse passata a meta'
    # avrebbe ristretto il processo a core diversi da quelli chiesti, e la curva
    # sarebbe stata plausibile e falsa.
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    k32.SetProcessAffinityMask.restype = wintypes.BOOL
    passo = 2 if (os.cpu_count() or 1) >= 2 * n_core_fisici() else 1
    maschera = 0
    for i in range(n):
        maschera |= 1 << (i * passo)
    if not k32.SetProcessAffinityMask(k32.GetCurrentProcess(), maschera):
        raise OSError(f"SetProcessAffinityMask({n}) fallita: {ctypes.get_last_error()}")
    return n


def n_core_fisici() -> int:
    """Quanti core fisici ha questa macchina. Cade sui logici se non si sa."""
    logici = os.cpu_count() or 1
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Processor | "
             "Measure-Object -Property NumberOfCores -Sum).Sum"],
            capture_output=True, text=True, timeout=30,
        )
        n = int(out.stdout.strip())
        return n if n > 0 else logici
    except Exception:
        return logici


def misura(backend: str, ripetizioni: int = 2) -> dict:
    """Costo della sintesi per battuta, su questo processo così com'è."""
    import numpy as np

    from core.config import Config
    from core.types import VoiceSpec
    from fuse.timing import spoken_length
    from speak.base import make_tts
    from speak.pool import FAMIGLIE

    cfg = Config().tts
    cfg.backend = backend
    tts = make_tts(cfg, preload=True)
    base = list(FAMIGLIE.get(backend, ()))[0]
    voce = VoiceSpec(voice_id="banco", backend=backend, base_voice=base,
                     semitones=0.0, rate=1.0, gender="m")

    tts.synthesize("Riscaldamento.", voce)
    costi, passi = [], []
    for _ in range(ripetizioni):
        for f in FRASI:
            t0 = time.perf_counter()
            s = tts.synthesize(f, voce)
            costi.append((time.perf_counter() - t0) * 1000.0)
            if s.duration > 0:
                passi.append(spoken_length(f) / s.duration)
    return {
        "backend": backend,
        "cpu": os.cpu_count(),
        "synth_p50": float(np.median(costi)),
        "synth_p95": float(np.percentile(costi, 95)),
        "cps": float(np.median(passi)) if passi else 0.0,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Il doppiaggio rallenta su un PC vecchio?")
    p.add_argument("--cores", type=int, default=0,
                   help="misura con questo numero di processori logici (0 = tutti)")
    p.add_argument("--backend", default="supertonic")
    p.add_argument("--ripetizioni", type=int, default=2)
    p.add_argument("--figlio", action="store_true", help="uso interno: stampa JSON")
    args = p.parse_args()

    if args.figlio or args.cores:
        limita_core(args.cores)
        r = misura(args.backend, args.ripetizioni)
        r["cores"] = args.cores or n_core_fisici()
        if args.figlio:
            print("JSON:" + json.dumps(r))
        else:
            print(f"  {args.backend} su {r['cores']} core: "
                  f"p50 {r['synth_p50']:.0f} ms, p95 {r['synth_p95']:.0f} ms, "
                  f"{r['cps']:.1f} car/s")
        return

    # La curva: un processo per punto, perché l'affinità si impone all'avvio.
    fisici = n_core_fisici()
    punti = sorted({n for n in (fisici, 8, 6, 4, 2) if n <= fisici}, reverse=True)
    print(f"== {args.backend}: il costo della sintesi al calare dei core ==")
    print(f"  (macchina: {fisici} core fisici, {os.cpu_count()} logici; l'affinità"
          f" simula il **numero** di core, non la loro velocità)\n")
    print(f"  {'core':>5} {'synth p50':>11} {'p95':>9} {'car/s':>7} {'contro pieno':>13}")

    base = None
    for n in punti:
        out = subprocess.run(
            [sys.executable, "-m", "tools.bench_cpu", "--figlio",
             "--cores", str(n), "--backend", args.backend,
             "--ripetizioni", str(args.ripetizioni)],
            capture_output=True, text=True,
        )
        riga = next((l for l in out.stdout.splitlines() if l.startswith("JSON:")), None)
        if riga is None:
            print(f"  {n:>5}  fallito: {out.stderr.strip().splitlines()[-1:] or '?'}")
            continue
        r = json.loads(riga[5:])
        base = base if base is not None else r["synth_p50"]
        print(f"  {n:>5} {r['synth_p50']:>10.0f}ms {r['synth_p95']:>8.0f}ms "
              f"{r['cps']:>7.1f} {r['synth_p50'] / base:>12.2f}x")

    print("\n  Se il costo raddoppia dimezzando i core, la sintesi scala e un PC")
    print("  vecchio con meno core costa in proporzione. Se resta piatto, i core")
    print("  non c'entrano e conta solo la velocità del singolo, che è un fattore")
    print("  molto più piccolo.")


if __name__ == "__main__":
    main()
