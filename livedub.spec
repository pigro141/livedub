# -*- mode: python ; coding: utf-8 -*-
"""L'eseguibile, con PyInstaller.

    .\.venv\Scripts\python.exe -m pip install pyinstaller
    .\.venv\Scripts\pyinstaller.exe livedub.spec

**Si impacchetta il programma, non i modelli.** E' una scelta di licenza prima
che di dimensione, e sta scritta in `LICENZE.md`: i pesi (Piper, Kokoro, ECAPA,
il lessico) hanno ognuno la propria, e OneOCR e' di Microsoft e **non e'
ridistribuibile**. Un pacchetto che se li portasse dietro si assumerebbe licenze
che nessuno ha letto — e nel caso di OneOCR ne violerebbe una.

Quindi l'exe al primo avvio scarica cio' che gli serve dentro `models/`, che e'
esattamente quello che fa gia' oggi da sorgente: nessun codice nuovo, nessun
percorso diverso, nessun ramo che esiste solo nel pacchetto. Un ramo che esiste
solo nel pacchetto e' un ramo che non gira mai in sviluppo, e questo progetto ha
gia' pagato per una strada parallela che non ereditava le cure dell'altra.

**Cartella e non file unico** (`onefile`). Con `onefile` tutto viene scompattato
in una cartella temporanea a ogni avvio: quattrocento MB di ONNX ogni volta, e i
percorsi relativi a `__file__` — che qui puntano a `models/`, `profiles/` e
`runs/` — cambiano a ogni esecuzione. La cartella e' piu' brutta e non mente.
"""

import sys
from pathlib import Path

RADICE = Path(SPECPATH)

a = Analysis(
    ["tools/ui.py"],
    pathex=[str(RADICE)],
    binaries=[],
    # I profili di calibrazione servono: senza, la prima cosa che l'utente vede
    # e' una ROI che inquadra il tappeto.
    # **E `core/config.py` come *dato*, non come codice.** Il pannello delle
    # impostazioni estrae le spiegazioni dai commenti del sorgente (si veda
    # `core/schema.py`), e in un pacchetto i `.py` non ci sono: c'e' il bytecode
    # dentro l'archivio, e i commenti il bytecode li ha buttati via. Senza questa
    # riga l'exe partiva e moriva alla costruzione del pannello — trovato
    # facendolo partire, non leggendo lo spec.
    datas=[("profiles", "profiles"), ("core/config.py", "core")],
    # **Gli import che PyInstaller non puo' vedere**, perche' qui i backend si
    # costruiscono per nome (`make_tts`, `make_ocr`) e non con un `import` in
    # cima. E' il prezzo della factory unica, ed e' un prezzo che val la pena
    # pagare: un nome sconosciuto solleva invece di ripiegare in silenzio su
    # Piper.
    hiddenimports=[
        "speak.backends.piper",
        "speak.backends.supertonic",
        "speak.backends.kokoro",
        "speak.backends.tone",
        "vision.oneocr_worker",
        "translate.locale",
        "translate.llm",
        "translate.ollama",
        "translate.google",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    runtime_hooks=[],
    # Torch non c'e' e non deve entrare: le prove GPU di questo progetto girano
    # in venv separati apposta per non avvicinarlo a questo.
    excludes=["torch", "torchaudio", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="livedub",
    debug=False,
    strip=False,
    upx=False,  # UPX rompe le DLL di ONNX Runtime: comprime e poi non caricano
    console=False,  # e' una finestra, non un terminale
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="livedub",
)
