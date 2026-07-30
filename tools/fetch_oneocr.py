"""Copia il riconoscitore di Windows 11 dentro `models/oneocr/`.

    python -m tools.fetch_oneocr

I tre file — `oneocr.dll`, `oneocr.onemodel` e la `onnxruntime.dll` che gli
appartiene — vivono dentro lo Strumento di cattura installato, in
`C:\\Program Files\\WindowsApps`. Non sono ridistribuibili, quindi non stanno nel
repository e vanno presi dalla macchina su cui si gira.

**Non serve `takeown` e non serve l'elevazione**, che e' la ragione per cui
questo strumento esiste invece di una riga di istruzioni. `WindowsApps` nega
l'*elencazione* della cartella radice, e questo fa credere che tutto il contenuto
sia inaccessibile; ma la lettura di un percorso **noto** al suo interno e'
permessa. Il percorso lo dice il sistema, con `Get-AppxPackage`. La differenza
fra "non posso guardare cosa c'e' dentro" e "non posso leggere questo file" e'
tutta la differenza fra prendersi la proprieta' di una cartella di sistema e
copiare tre file.

La `onnxruntime.dll` va copiata **insieme alle altre due** e non e' un dettaglio:
`oneocr.dll` pretende una versione di API che l'onnxruntime di Python non offre,
e senza la sua accanto risolve quella sbagliata e muore con un accesso a memoria
non valido. E' anche il motivo per cui il motore gira in un processo separato,
si veda `vision/oneocr_worker.py`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DESTINAZIONE = Path(__file__).resolve().parent.parent / "models" / "oneocr"
FILE = ("oneocr.dll", "oneocr.onemodel", "onnxruntime.dll")


def posizione_pacchetto(nome: str = "Microsoft.ScreenSketch") -> Path | None:
    """Dove Windows ha installato il pacchetto. Lo chiede al sistema."""
    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-AppxPackage -Name '{nome}').InstallLocation",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return None
    percorso = (out.stdout or "").strip().splitlines()
    return Path(percorso[0]) if percorso and percorso[0] else None


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        print("OneOCR e' il riconoscitore di Windows: qui non c'e'.", file=sys.stderr)
        return 2

    base = posizione_pacchetto()
    if base is None:
        print(
            "Strumento di cattura non trovato. Si installa dal Microsoft Store\n"
            "(cercare 'Strumento di cattura'), poi si rilancia questo comando.",
            file=sys.stderr,
        )
        return 2

    sorgente = base / "SnippingTool"
    mancanti = [f for f in FILE if not (sorgente / f).exists()]
    if mancanti:
        print(
            f"in {sorgente} mancano: {', '.join(mancanti)}.\n"
            "Probabilmente una versione dello Strumento di cattura che li dispone\n"
            "altrimenti: il backend `oneocr` restera' non disponibile, e la catena\n"
            "continua con `ppocr`.",
            file=sys.stderr,
        )
        return 2

    DESTINAZIONE.mkdir(parents=True, exist_ok=True)
    for f in FILE:
        shutil.copy2(sorgente / f, DESTINAZIONE / f)
        mb = (DESTINAZIONE / f).stat().st_size / (1024 * 1024)
        print(f"  {f:<20} {mb:6.1f} MB")
    print(f"\n-> {DESTINAZIONE}")
    print("Ora si accende con `--set vision.ocr_backend=oneocr`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
