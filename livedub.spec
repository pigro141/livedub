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

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

RADICE = Path(SPECPATH)

# ============================ i dati che stanno dentro le librerie, non qui ===
#
# **PyInstaller impacchetta il codice e butta i dati.** Segue gli `import` e
# porta i `.py` e i `.pyd`; i file che quei moduli aprono per percorso — un
# `config.yaml`, un dizionario di espeak, una DLL caricata con `ctypes` — non
# li vede nessuno, perche' nessuno li importa. Il pacchetto si costruisce senza
# un avviso e il difetto esce alla prima battuta.
#
# Misurato sul pacchetto del 20 agosto, guardando cosa c'era in `_internal`:
# **quattro delle cinque librerie che portano dati non ne avevano nemmeno uno**,
# e fra queste ci sono i due motori *di serie* — PP-OCR (`vision.ocr_backend`)
# e Piper (`tts.backend`). Cioe' l'eseguibile si apriva, mostrava la finestra
# giusta, e non sapeva ne' leggere ne' parlare.
#
# Ognuna e' qui col motivo per cui serve, perche' un elenco di nomi di pacchetto
# non si sa piu' potare: chi legge non puo' distinguere la riga che regge il
# default da quella rimasta li' da una prova.
DATI_LIBRERIE = []
BINARI_LIBRERIE = []

# ================================ i profili, meno la sessione di chi compila ==
#
# `profiles/*.json` sono le calibrazioni, e servono. Ma in quella cartella ci
# finisce anche **`ultima.json`**, che non e' un profilo: e' la configurazione
# con cui si e' chiuso l'ultimo avvio, la scrive `core.preferenze` uscendo e la
# **rilegge aprendo** quando nessuno chiede un profilo — che e' esattamente il
# caso dell'eseguibile, lanciato con un doppio clic e senza argomenti.
#
# E' gitignorata, quindi da un clone pulito non esiste; su una macchina che
# sviluppa esiste sempre. Prendendo la cartella intera, il pacchetto del 20
# agosto partiva con addosso la sessione di chi lo aveva compilato: `ocr_backend
# = oneocr`, `tts.backend = kokoro`, `tts.device = cuda` e la ROI del suo
# schermo. Non dava errore — la barra della misura mostrava `ROI x0.232 y0.786`,
# e per accorgersene bisognava riconoscere quel numero.
#
# Quindi si elencano i file, uno per uno, invece di consegnare una cartella.
PROFILI = [(str(p), "profiles")
           for p in sorted((RADICE / "profiles").glob("*.json"))
           if p.name != "ultima.json"]

# PP-OCR: `config.yaml` piu' i tre ONNX (rilevatore, riconoscitore,
# classificatore) che stanno **dentro il pacchetto pip**, non in `models/`.
# E' il backend di serie di `vision.ocr_backend`.
DATI_LIBRERIE += collect_data_files("rapidocr_onnxruntime")

# Piper: `espeak-ng-data`, il g2p. E' il motore di serie di `tts.backend`, ed e'
# la voce che sente chi apre il pacchetto senza toccare niente.
DATI_LIBRERIE += collect_data_files("piper")

# Kokoro fonemizza con espeak per un'altra strada: `kokoro_onnx.tokenizer`
# importa `espeakng_loader` e `phonemizer`, e la DLL la carica **per percorso**
# (`ctypes`), quindi va messa dove il modulo la cerca — accanto a se stesso.
DATI_LIBRERIE += collect_data_files("espeakng_loader")
DATI_LIBRERIE += collect_data_files("kokoro_onnx")
DATI_LIBRERIE += collect_data_files("phonemizer")
BINARI_LIBRERIE += collect_dynamic_libs("espeakng_loader")

# E dietro a `phonemizer` ce n'e' un'altra che non si sarebbe indovinata:
# `segments` -> `csvw` -> `language_tags`, che tiene l'elenco dei codici di
# lingua in quattordici JSON. Trovata solo premendo «Misura questo PC»: la
# misura della voce rispondeva `FileNotFoundError: ...\language_tags\data\json\
# index.json`, e nessun `import` in nessun nostro file la nomina.
DATI_LIBRERIE += collect_data_files("language_tags")

# Il traduttore `llm` (Gemma in-process): `llama_cpp` carica le sue DLL a mano
# da `llama_cpp/lib`, quindi l'analisi statica non le trova.
#
# **Ed e' facoltativo, quindi la sua assenza non deve fermare la costruzione.**
# `llama-cpp-python` non e' piu' in `requirements.txt`: su Windows non ha una
# ruota ne' su PyPI ne' sull'indice CPU di abetlen, e la riga fermava tutta
# l'installazione (si veda il commento in `requirements.txt`). Senza questo `try`
# `collect_dynamic_libs` solleva `ValueError` e il pacchetto non si costruisce
# affatto — cioe' un pezzo opzionale spegnerebbe il prodotto.
try:
    BINARI_LIBRERIE += collect_dynamic_libs("llama_cpp")
except Exception as e:  # noqa: BLE001 — qualunque cosa dica, il senso e' «non c'e'»
    print(f"livedub.spec: llama_cpp non c'e', il traduttore `llm` restera' fuori ({e})")

a = Analysis(
    # **La finestra Qt, non quella Tk.** L'eseguibile impacchettava
    # `tools/ui.py`, cioe' il front-end vecchio: chi installava il pacchetto
    # riceveva un'altra interfaccia da quella descritta in
    # `docs/interfaccia.md`, con la suite verde e senza un errore da nessuna
    # parte. La Tk resta nel sorgente per il confronto, ma non e' il prodotto.
    ["tools/ui_qt.py"],
    pathex=[str(RADICE)],
    binaries=BINARI_LIBRERIE,
    # I profili di calibrazione servono: senza, la prima cosa che l'utente vede
    # e' una ROI che inquadra il tappeto.
    # **E `core/config.py` come *dato*, non come codice.** Il pannello delle
    # impostazioni estrae le spiegazioni dai commenti del sorgente (si veda
    # `core/schema.py`), e in un pacchetto i `.py` non ci sono: c'e' il bytecode
    # dentro l'archivio, e i commenti il bytecode li ha buttati via. Senza questa
    # riga l'exe partiva e moriva alla costruzione del pannello — trovato
    # facendolo partire, non leggendo lo spec.
    # **E il logo.** E' l'unica immagine dell'interfaccia, sta in testata, si
    # scambia col guasto e diventa l'icona della finestra: senza questa riga il
    # pacchetto parte, non da' errore, e mostra una tessera vuota — che e'
    # esattamente il tipo di difetto che non si vede finche' non lo si guarda.
    # **E i cataloghi della lingua della finestra.** `ui/lingua.py` li cerca in
    # `ui/lingue/*.json` accanto a se stesso: PyInstaller mette il codice
    # nell'archivio e i JSON no, quindi senza questa riga `disponibili()`
    # tornerebbe la sola voce «it» e l'eseguibile sarebbe **solo in italiano**.
    # Non darebbe errore: darebbe un menu con una voce sola, e sembrerebbe una
    # scelta. E' la stessa forma del difetto di `core/config.py` qui sopra.
    # **E le licenze, che qui non sono un adempimento.** Il programma e'
    # GPL-3.0-or-later e la finestra lo dichiara nel pannello «info»: «Licenza:
    # GPL-3.0-or-later (vedi LICENZE.md)» — rimandando a un file che nel
    # pacchetto non c'era. `LICENZE.md` e' anche il posto dove sta scritto
    # perche' i modelli **non** viaggiano con l'eseguibile, che e' la scelta che
    # regge tutto questo file.
    datas=PROFILI + [("core/config.py", "core"),
                     ("assets/logo", "assets/logo"), ("ui/lingue", "ui/lingue"),
                     ("LICENSE", "."), ("docs/LICENZE.md", ".")]
    + DATI_LIBRERIE,
    # **Gli import che PyInstaller non puo' vedere**, perche' qui i backend si
    # costruiscono per nome (`make_tts`, `make_ocr`) e non con un `import` in
    # cima. E' il prezzo della factory unica, ed e' un prezzo che val la pena
    # pagare: un nome sconosciuto solleva invece di ripiegare in silenzio su
    # Piper.
    hiddenimports=[
        "speak.backends.piper",
        "speak.backends.supertonic",
        "speak.backends.kokoro",
        # `speak.backends.tone` stava qui e **non esiste**: `tone` e `silent`
        # vivono dentro `speak/base.py`. PyInstaller lo diceva
        # (`ERROR: Hidden import not found`) in mezzo a millecento righe di
        # INFO, e il pacchetto veniva su lo stesso: un elenco scritto a mano che
        # nessuno rilegge, la forma gia' vista di `tools/say.py` con il
        # `choices` rimasto indietro.
        "vision.oneocr_worker",
        # **La prova del pacchetto viaggia dentro il pacchetto.** `livedub.exe
        # --autoprova rapporto.json` legge una riga disegnata, sintetizza una
        # battuta e costruisce la finestra: sono le tre cose che il pacchetto del
        # 20 agosto non sapeva fare pur essendo verde. `tools/ui_qt.py` lo
        # importa dentro il ramo, quindi l'analisi statica non lo vede.
        "tools.autoprova",
        # **La cattura di ripiego si importa dentro una funzione**, quindi
        # l'analisi statica non la vede: senza questa riga il pacchetto viene su
        # lo stesso e la finestra muore all'Avvia sulla macchina che ne ha
        # bisogno — cioe' esattamente quella per cui esiste.
        "capture.printwindow",
        "translate.locale",
        "translate.llm",
        "translate.ollama",
        "translate.google",
        # Argos carica il suo modello per nome, e `sbd.py` importa questi due
        # anche quando non li usa (il modo di spezzare le frasi di serie e'
        # `ARGOSTRANSLATE`): senza, l'analisi statica non li vede.
        "argostranslate.translate",
        "argostranslate.package",
        "stanza",
        "minisbd",
        "ctranslate2",
        "sentencepiece",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    # **Senza questa riga l'eseguibile non puo' scaricare niente.** `console=
    # False` lascia `sys.stdout` e `sys.stderr` a `None`, e la barra di
    # avanzamento di `huggingface_hub` scrive su stderr: misurato sul pacchetto
    # del 20 agosto, il banco rispondeva `AttributeError: 'NoneType' object has
    # no attribute 'write'` a **ognuno** dei modelli da prendere. Il perche' per
    # esteso sta in `pyi_uscite.py`.
    runtime_hooks=["pyi_uscite.py"],
    # **Torch adesso deve entrare, e non perche' serva.** Questa riga diceva
    # «torch non c'e' e non deve entrare», ed era vera finche' la traduzione
    # offline era opzionale. Ora `translate.locale` e' il default installato di
    # serie, e la catena e' obbligata: argostranslate importa `stanza` in cima a
    # `sbd.py`, e stanza importa torch. Torch non traduce niente — Argos gira su
    # CTranslate2 — ma senza di lui l'eseguibile muore alla prima battuta
    # tradotta con un `ModuleNotFoundError`, cioe' proprio dove l'utente finale
    # non puo' farci niente.
    #
    # Il prezzo e' misurato: +712 MB nel venv (3120 -> 3832), e nel pacchetto
    # sara' lo stesso ordine. Chi volesse un eseguibile piccolo ha una strada
    # dichiarata: rimettere `torch` qui dentro e cambiare il default a
    # `translate.backend=llm` (444 ms invece di 38, ma zero dipendenze nuove).
    excludes=["torchaudio", "matplotlib", "pytest", "IPython"],
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
    # Windows non ridimensiona bene un PNG nella barra delle applicazioni: serve
    # un `.ico` multi-risoluzione, e lo genera `ui.qt_tema.icona()`.
    icon="assets/logo/livedub.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="livedub",
)
