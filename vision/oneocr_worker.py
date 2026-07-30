"""OneOCR in un processo tutto suo, perche' non puo' stare in questo.

    python -m vision.oneocr_worker        # parla su stdin/stdout, non si usa a mano

`oneocr.dll` e' il riconoscitore dello Strumento di cattura di Windows 11, ed e'
molto piu' solido di PP-OCR sul testo bordato dei giochi. Ma porta con se' **il
proprio** `onnxruntime.dll`, e pretende la sua versione di API: caricato nello
stesso processo che ha gia' l'onnxruntime di Python — quello che fanno girare
ECAPA, Piper e RapidOCR — trova quello sbagliato e muore con un accesso a
memoria non valido. Provato: `The requested API version [21] is not available,
only API versions [1, 17] are supported`, poi access violation.

Non e' un problema aggirabile con l'ordine degli import: due runtime ONNX nello
stesso spazio di indirizzamento sono incompatibili per costruzione. **Quindi il
confine non e' un ripiego, e' l'unica architettura possibile**, e va difeso:
questo modulo non deve importare `onnxruntime`, ne' direttamente ne' tirandosi
dietro qualcosa che lo faccia. `numpy` e `cv2` sono sicuri; `rapidocr`,
`listen.embed`, `speak.*` no.

Il protocollo e' volutamente stupido, perche' sta dentro il percorso che deve
essere veloce: una riga di intestazione con le dimensioni, poi i byte grezzi
dell'immagine, poi una riga di JSON in risposta. Nessuna codifica, nessuna
compressione, nessuna libreria di serializzazione: un ritaglio di sottotitolo
sono venti kilobyte, e il giro su una pipe locale costa meno di un millisecondo.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

# Dove stanno `oneocr.dll`, `oneocr.onemodel` e la `onnxruntime.dll` che gli
# appartiene. Si copiano dallo Strumento di cattura installato: non sono
# ridistribuibili, quindi non stanno nel repository.
RUNTIME_DIR = Path(__file__).resolve().parent.parent / "models" / "oneocr"


def carica_motore():
    """Costruisce il motore, o spiega cosa manca invece di morire di ctypes."""
    if not (RUNTIME_DIR / "oneocr.dll").exists():
        raise RuntimeError(
            f"OneOCR non installato: mancano i file in {RUNTIME_DIR}.\n"
            "Si copiano dallo Strumento di cattura di Windows 11 con "
            "`python -m tools.fetch_oneocr`."
        )
    # Prima la cartella nel percorso di ricerca delle DLL, poi l'import: al
    # contrario `oneocr.dll` risolverebbe `onnxruntime.dll` altrove, che e'
    # esattamente il guasto per cui questo processo esiste.
    os.add_dll_directory(str(RUNTIME_DIR))
    import oneocr

    oneocr.CONFIG_DIR = str(RUNTIME_DIR)
    return oneocr.OcrEngine()


def estrai(risultato) -> tuple[str, float]:
    """Da cio' che restituisce OneOCR a `(testo, confidenza)`.

    Difensivo di proposito: la forma esatta dipende dalla versione della DLL,
    che arriva da un aggiornamento di Windows e non da noi. Un cambio di forma
    deve degradare a "non ho letto niente", non far cadere la catena.
    """
    if isinstance(risultato, str):
        return risultato.strip(), 1.0
    if not isinstance(risultato, dict):
        return "", 0.0
    testo = str(risultato.get("text") or "").strip()
    righe = risultato.get("lines") or []
    conf = 0.0
    if isinstance(righe, list) and righe:
        valori = [
            float(r.get("confidence", 0.0))
            for r in righe
            if isinstance(r, dict) and r.get("confidence") is not None
        ]
        if valori:
            conf = float(np.mean(valori))
    return testo, (conf if conf > 0 else (1.0 if testo else 0.0))


def main() -> int:
    try:
        motore = carica_motore()
    except Exception as exc:
        # Sulla propria uscita di errore, in una riga sola: chi ci parla la
        # legge e sa dire *perche'* il backend non c'e'.
        print(f"ONEOCR-ERRORE {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 2
    print("ONEOCR-PRONTO", file=sys.stderr, flush=True)

    ingresso = sys.stdin.buffer
    uscita = sys.stdout.buffer
    while True:
        intestazione = ingresso.readline()
        if not intestazione:
            return 0
        try:
            h, w, c = (int(x) for x in intestazione.split())
        except ValueError:
            return 1
        attesi = h * w * c
        dati = bytearray()
        while len(dati) < attesi:
            pezzo = ingresso.read(attesi - len(dati))
            if not pezzo:
                return 0
            dati.extend(pezzo)
        img = np.frombuffer(bytes(dati), dtype=np.uint8).reshape(h, w, c)
        try:
            testo, conf = estrai(motore.recognize_cv2(img))
        except Exception as exc:  # una riga illeggibile non chiude il worker
            testo, conf = "", 0.0
            print(f"ONEOCR-RIGA {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        uscita.write((json.dumps({"t": testo, "c": conf}) + "\n").encode("utf-8"))
        uscita.flush()


if __name__ == "__main__":
    raise SystemExit(main())
