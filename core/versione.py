"""La versione del programma, in un posto solo.

**Perche' serve.** Senza un numero, un rapporto di errore non si puo' leggere:
«non funziona» non dice quale codice stava girando. E' la domanda 17 di
`DOMANDE_PRODUZIONE.md`, e costa una riga.

Il numero e' scritto a mano perche' e' una **dichiarazione**, non un dato
ricavato: dire "0.9" significa "so cosa manca alla 1.0", e quell'elenco sta in
`SviluppoProgetto.md`. La revisione di git invece si legge, quando c'e': dice
esattamente da dove viene un eseguibile.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

VERSIONE = "0.9.0"
NOME = "livedub"


def revisione() -> str:
    """Il commit da cui viene questa copia, o `(non da git)`."""
    try:
        fuori = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True, text=True, timeout=3,
        )
        if fuori.returncode == 0:
            return fuori.stdout.strip()
    except Exception:
        pass
    return "(non da git)"


def scheda() -> str:
    """Tutto quello che serve per leggere un rapporto di errore, in sei righe."""
    righe = [
        f"{NOME} {VERSIONE}  ({revisione()})",
        f"Python  {sys.version.split()[0]}",
        f"sistema {platform.platform()}",
    ]
    try:
        import PySide6

        righe.append(f"Qt      {PySide6.__version__}")
    except Exception:
        pass
    try:
        # `core.onnx.preload()` — il nome giusto. La prima versione chiamava
        # `preload_dlls`, che e' come si chiama la funzione **di onnxruntime**
        # che sta dentro: la scheda diceva «ORT non disponibile (ImportError)» su
        # una macchina dove ORT c'era e funzionava. Una diagnostica che sbaglia e'
        # peggio di una che manca, perche' manda a cercare dalla parte sbagliata.
        from core.onnx import cuda_ottenuta

        import onnxruntime as ort

        # **Due numeri e non uno, ed e' il difetto per cui questa riga esiste.**
        # `get_available_providers()` elenca i provider **compilati dentro**: nel
        # pacchetto congelato scriveva `Tensorrt, CUDA, CPU` mentre il registro
        # dello stesso avvio diceva `Failed to load cublasLt64_13.dll`. Chi legge
        # un rapporto di errore leggeva percio' «c'e' la CUDA» sulla macchina che
        # non ce l'aveva. `cuda_ottenuta()` apre una sessione e guarda cosa ha
        # preso: e' l'unica delle due che risponde alla domanda che si sta
        # facendo.
        _, ottenuto = cuda_ottenuta("il rapporto")
        righe.append(
            f"ORT     {ort.__version__}  compilato: "
            f"{', '.join(ort.get_available_providers())}  ottenuto: {ottenuto}")
    except Exception as e:
        righe.append(f"ORT     non disponibile ({type(e).__name__})")
    return "\n".join(righe)
