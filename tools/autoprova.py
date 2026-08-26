"""L'eseguibile si prova da dentro, perche' da fuori non si vede niente.

    .\\.venv\\Scripts\\python.exe -m tools.autoprova rapporto.json
    dist\\livedub\\livedub.exe --autoprova rapporto.json

**Perche' esiste.** Un pacchetto sbagliato non da' errore: si apre, mostra la
finestra giusta e non sa ne' leggere ne' parlare. E' successo davvero — il
pacchetto del 20 agosto portava il codice e lasciava a casa i dati, e quattro
delle cinque librerie che portano dati non ne avevano nemmeno uno, fra cui i due
motori *di serie*. Guardarlo da fuori (il file c'e', pesa 800 MB) non poteva
dirlo; guardarlo da dentro costa trenta secondi.

**Le prove devono poter fallire.** Un import riuscito non dice quasi niente in
questo progetto: `piper` importa e muore alla prima sintesi, perche'
`espeakbridge.pyd` si apre pigramente. Quindi qui non si importa, si **usa**: si
legge una riga disegnata e si sintetizza una battuta, che sono le due cose che il
pacchetto del 20 agosto non sapeva fare pur essendo verde.

**E l'uscita e' un file, non lo schermo.** L'eseguibile e' costruito con
`console=False`: `sys.stdout` non esiste e `pyi_uscite.py` lo dirotta nel
registro. Un rapporto JSON su disco e' l'unico canale che si legge uguale da
sorgente, dall'eseguibile e da un runner di integrazione continua.

Il codice di uscita e' 0 se tutte le prove **richieste** sono passate. Una prova
saltata (niente rete, niente Qt) e' `saltata` e non `ok`: dire «passata» a una
cosa che non si e' fatta e' il ripiego silenzioso girato dall'altra parte.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover — lanciato come file
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import percorsi  # noqa: E402
from core import versione as _versione  # noqa: E402


class Rapporto:
    """L'elenco delle prove, con il perche' di ognuna."""

    def __init__(self) -> None:
        self.righe: list[dict] = []

    def prova(self, nome: str, funzione) -> None:
        avvio = time.perf_counter()
        try:
            nota = funzione()
            esito, nota = "ok", str(nota)
        except _Saltata as e:
            esito, nota = "saltata", str(e)
        except Exception as e:  # noqa: BLE001 — qualunque cosa sia, la prova non e' passata
            esito, nota = "rotta", f"{type(e).__name__}: {e}"
        ms = (time.perf_counter() - avvio) * 1000
        self.righe.append({"prova": nome, "esito": esito, "nota": nota, "ms": round(ms, 1)})
        print(f"{esito.upper():>8}  {nome:<22} {nota}  [{ms:.0f} ms]", flush=True)

    @property
    def rotte(self) -> list[dict]:
        return [r for r in self.righe if r["esito"] == "rotta"]


class _Saltata(Exception):
    """Non si e' potuta fare qui, e si dichiara invece di darla per buona."""


class _ArgsFinti:
    """Quello che la finestra si aspetta dalla riga di comando, tutto spento.

    Copiato da `tools/scatta.py` invece di importarlo: quello e' uno strumento di
    sviluppo e non deve finire dentro il pacchetto solo per una classe di undici
    righe. `no_save=True` perche' una prova non deve lasciare una sessione finta
    in `runs/`.
    """

    profile = None
    loopback = "voicemeeter"
    output = None
    block = 480
    backend = "auto"
    monitor = 1
    tts = None
    no_save = True
    avvia = False
    overlay_catturabile = False
    overrides = None


# ================================================================= le prove ===
#
# Ognuna torna la frase che finisce nel rapporto, e solleva se non e' andata.
# Nessuna stampa «ok» da sola: l'esito lo decide il fatto che non abbia sollevato.


def _versione_e_posto() -> str:
    scheda = _versione.scheda()
    if not scheda.strip():
        raise AssertionError("la scheda della versione e' vuota")
    dove = "eseguibile" if percorsi.congelato() else "sorgente"
    return f"{dove}, radice {percorsi.radice()} | " + scheda.replace("\n", " | ")


def _profili() -> str:
    from core.config import PROFILES_DIR, load_profile

    trovati = sorted(p.name for p in PROFILES_DIR.glob("*.json"))
    for nome in ("gtav", "live"):
        cfg = load_profile(nome, None)
        if not cfg.vision.roi:
            raise AssertionError(f"il profilo {nome} non porta una ROI")
    # **`ultima.json` non e' un profilo**: e' la configurazione con cui si e'
    # chiuso l'ultimo avvio di chi ha compilato. Nel pacchetto del 20 agosto c'era,
    # e l'eseguibile partiva con addosso la ROI dello schermo di un altro senza
    # dare errore. `livedub.spec` elenca i file uno per uno proprio per questo.
    if percorsi.congelato() and "ultima.json" in trovati:
        raise AssertionError("nel pacchetto c'e' `ultima.json`: la sessione di chi ha compilato")
    return f"{len(trovati)} file: {', '.join(trovati)}"


def _config_come_dato() -> str:
    """Le spiegazioni dei campi vengono dai **commenti** di `core/config.py`.

    In un pacchetto i `.py` non ci sono — c'e' il bytecode, e i commenti il
    bytecode li ha buttati. Senza `core/config.py` fra i dati l'exe partiva e
    moriva costruendo il pannello delle impostazioni.
    """
    from core.config import Config
    from core.schema import campi

    elenco = campi(Config())
    con_aiuto = [c for c in elenco if (c.aiuto or "").strip()]
    if len(elenco) < 150 or len(con_aiuto) < 100:
        raise AssertionError(
            f"{len(elenco)} campi, {len(con_aiuto)} con spiegazione: i commenti non sono arrivati")
    return f"{len(elenco)} campi, {len(con_aiuto)} con la spiegazione presa dai commenti"


def _cataloghi() -> str:
    """`ui/lingue/*.json` accanto al modulo: senza, il menu ha una voce sola.

    Non darebbe errore — darebbe un programma solo in italiano, e sembrerebbe
    una scelta.
    """
    from ui import lingua

    lingue = lingua.disponibili()
    if len(lingue) < 41:
        raise AssertionError(f"solo {len(lingue)} cataloghi: {lingue}")
    catalogo = lingua.carica("de")
    if len(catalogo) < 200:
        raise AssertionError(f"il catalogo tedesco ha {len(catalogo)} voci")
    return f"{len(lingue)} lingue, il tedesco con {len(catalogo)} voci"


def _immagini_del_foglio() -> str:
    """Ogni `url(...)` del foglio di stile deve esistere sul disco.

    `url()` con un nome inventato non solleva: Qt disegna un **quadrato pieno**
    al posto della spunta. E la spunta e le freccine si generano dentro
    `models/ui`, quindi questa prova dice anche che `models/` e' scrivibile —
    che nel pacchetto non era scontato.
    """
    import re

    from ui import qt_tema as tema

    mancanti: list[str] = []
    quante = 0
    for tavolozza in (tema.SCURA, tema.CHIARA):
        for percorso in re.findall(r'url\("([^"]+)"\)', tema.foglio(tavolozza)):
            quante += 1
            if not Path(percorso).exists():
                mancanti.append(percorso)
    if mancanti:
        raise AssertionError(f"immagini che non esistono: {mancanti}")
    for rotto in (False, True):
        if not tema.logo(rotto).exists():
            raise AssertionError(f"manca il logo (rotto={rotto})")
    if tema.icona() is None:
        raise AssertionError("manca l'icona della finestra")
    return f"{quante} immagini nei due temi, generate in {tema._DISEGNI}"


def _licenze() -> str:
    """Il pannello «info» rimanda a `LICENZE.md`, e nel pacchetto non c'era."""
    mancano = [n for n in ("LICENSE", "LICENZE.md")
               if not (percorsi.radice() / n).exists()
               and not (percorsi.radice() / "_internal" / n).exists()
               and not (percorsi.radice() / "docs" / n).exists()]
    if mancano:
        raise AssertionError(f"non ci sono: {mancano}")
    return "LICENSE e LICENZE.md raggiungibili"


def _dati_delle_librerie() -> str:
    """I file che le librerie aprono **per percorso**, che nessun import nomina.

    E' il difetto storico di questo pacchetto: PyInstaller segue gli `import` e
    butta i dati. Qui si guarda dove ognuna li cerca davvero.
    """
    import importlib

    trovati: list[str] = []

    import rapidocr_onnxruntime

    base = Path(rapidocr_onnxruntime.__file__).parent
    onnx = sorted(p.name for p in base.rglob("*.onnx"))
    if len(onnx) < 3 or not list(base.rglob("config.yaml")):
        raise AssertionError(f"PP-OCR senza i suoi dati: {len(onnx)} onnx in {base}")
    trovati.append(f"rapidocr {len(onnx)} onnx")

    import piper

    dati_espeak = list(Path(piper.__file__).parent.rglob("espeak-ng-data"))
    if not dati_espeak:
        # Piper 1.3 tiene espeak dentro `piper_phonemize`/`espeakng_loader`:
        # basta che *qualcuno* li porti, non che li porti lui.
        import espeakng_loader

        dati_espeak = list(Path(espeakng_loader.__file__).parent.rglob("espeak-ng-data"))
    if not dati_espeak:
        raise AssertionError("nessun `espeak-ng-data`: il g2p non ha i suoi dizionari")
    trovati.append("espeak-ng-data")

    import espeakng_loader

    dll = list(Path(espeakng_loader.__file__).parent.rglob("*espeak*"))
    if not dll:
        raise AssertionError("espeakng_loader senza binari")
    trovati.append(f"espeakng_loader {len(dll)} file")

    lt = importlib.import_module("language_tags")
    if not list(Path(lt.__file__).parent.rglob("index.json")):
        raise AssertionError("language_tags senza i suoi JSON (li chiede `phonemizer`)")
    trovati.append("language_tags")

    return ", ".join(trovati)


NASCOSTI = (
    "speak.backends.piper",
    "speak.backends.supertonic",
    "speak.backends.kokoro",
    "vision.oneocr_worker",
    "capture.printwindow",
    "translate.locale",
    "translate.ollama",
    "translate.google",
    "translate.llm",
)


def _moduli_nascosti() -> str:
    """I moduli che si costruiscono **per nome** e che l'analisi statica non vede.

    `capture.printwindow` e' il caso che morde: si importa dentro una funzione,
    quindi senza `hiddenimports` il pacchetto viene su lo stesso e muore
    all'Avvia proprio sulla macchina che ne ha bisogno.
    """
    import importlib

    rotti: list[str] = []
    for nome in NASCOSTI:
        try:
            importlib.import_module(nome)
        except Exception as e:  # noqa: BLE001
            rotti.append(f"{nome} ({type(e).__name__}: {e})")
    if rotti:
        raise AssertionError("; ".join(rotti))
    return f"{len(NASCOSTI)} moduli costruiti per nome, tutti raggiungibili"


def _dove_stanno_i_modelli() -> str:
    """`models/` accanto all'eseguibile, non dentro `_internal\\`.

    Se sta dentro `_internal\\` mentre `runs/` e `cast.json` sono relativi alla
    cartella di lancio, chi apre l'exe da un collegamento riscarica cinquecento
    MB a ogni avvio, senza un errore e senza capire perche'. La regola sta in
    `core/percorsi.py`.
    """
    from listen.embed import ECAPA_DIR
    from speak.backends.piper import MODELS_DIR
    from ui import qt_tema as tema

    attesa = percorsi.modelli()
    for nome, p in (("piper", MODELS_DIR), ("ecapa", ECAPA_DIR), ("ui", tema._DISEGNI)):
        if attesa not in p.parents:
            raise AssertionError(f"{nome} cerca in {p}, fuori da {attesa}")
        if "_internal" in p.parts:
            raise AssertionError(f"{nome} cerca dentro `_internal`: {p}")
    prova = attesa / ".scrivibile"
    prova.parent.mkdir(parents=True, exist_ok=True)
    prova.write_text("x", encoding="utf-8")
    prova.unlink()
    return f"tutti sotto {attesa}, ed e' scrivibile"


def _legge_una_riga() -> str:
    """Il lettore di serie su un sottotitolo disegnato: **niente da scaricare**.

    I tre ONNX di PP-OCR stanno dentro il pacchetto pip, quindi questa prova
    dice se `livedub.spec` li ha portati e se ONNX Runtime li sa aprire qui
    dentro. Il pacchetto del 20 agosto non li aveva.
    """
    import numpy as np
    from PIL import Image, ImageDraw

    from ui.overlay import carica_font
    from vision.ocr import make_ocr

    testo = "LAVORIAMO INSIEME"
    tela = Image.new("RGB", (760, 72), (18, 18, 18))
    ImageDraw.Draw(tela).text((16, 14), testo, font=carica_font("Arial", 40),
                              fill=(245, 245, 245))
    riga = np.array(tela)[:, :, ::-1].copy()  # RGB -> BGR, come la cattura

    letto, fiducia = make_ocr("ppocr").read(riga)
    pulito = "".join(ch for ch in letto.upper() if ch.isalpha() or ch == " ")
    if "LAVORIAMO" not in pulito:
        raise AssertionError(f"ha letto {letto!r} (fiducia {fiducia:.2f}) invece di {testo!r}")
    return f"{letto!r}, fiducia {fiducia:.2f}"


def _parla_davvero() -> str:
    """Piper sintetizza una battuta vera, e non e' un import.

    `espeakbridge.pyd` si apre **pigramente alla prima sintesi**: un import non
    lo tocca nemmeno. E' l'unica prova che dica qualcosa su quella libreria, ed
    e' la ragione per cui questa funzione scarica il modello (~45 MB) invece di
    accontentarsi del motore finto.
    """
    from dataclasses import replace

    from core.config import Config
    from fuse.timing import spoken_length
    from speak.base import make_tts
    from speak.pool import build_pool

    cfg = Config()
    tts = make_tts(replace(cfg.tts, backend="piper"), preload=False)
    voce = build_pool(cfg.tts.voices, cfg.tts.pool_size, backend="piper")[0]
    battuta = "Sali in macchina, muoviti, non ho tempo per queste cose."
    avvio = time.perf_counter()
    parlato = tts.synthesize(battuta, voce)
    costo = (time.perf_counter() - avvio) * 1000

    campioni = len(parlato.audio)
    if campioni < 1000:
        raise AssertionError(f"solo {campioni} campioni: non ha parlato")
    durata = campioni / parlato.samplerate
    passo = spoken_length(battuta) / durata
    # Un numero fuori scala e' l'unica traccia che lascia un'unita' sbagliata:
    # 30 car/s non e' la velocita' di parlato di nessuno, e fu cosi' che si
    # scopri' un ramo che non ricampionava.
    if not 5.0 <= passo <= 25.0:
        raise AssertionError(f"passo implausibile: {passo:.1f} car/s su {durata:.2f} s")
    return (f"{durata:.2f} s di audio a {parlato.samplerate} Hz, {passo:.1f} car/s, "
            f"sintesi {costo:.0f} ms")


def _apre_la_finestra() -> str:
    """La finestra vera, costruita e **mai mostrata** (`WA_DontShowOnScreen`).

    Non si giudica l'aspetto qui: `QT_QPA_PLATFORM=offscreen` ha zero caratteri
    installati e restituirebbe una finestra di quadratini. Si giudica solo che
    si costruisca — che e' cio' che un pacchetto sbagliato non riesce a fare.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from core import preferenze
    from tools.ui_qt import Finestra

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    cfg, _ = preferenze.riprendi(None, None)
    finestra = Finestra(cfg, _ArgsFinti())
    finestra.setAttribute(Qt.WA_DontShowOnScreen, True)
    finestra.show()
    app.processEvents()
    schede = finestra.schede.count() if hasattr(finestra, "schede") else 0
    if schede < 6:
        raise AssertionError(f"{schede} schede invece di sei")
    finestra.close()
    return f"{schede} schede, minimo {finestra.minimumSizeHint().width()} px"


# ================================================================ il seguito ==

PROVE = [
    ("versione", _versione_e_posto, "sempre"),
    ("profili", _profili, "sempre"),
    ("config-come-dato", _config_come_dato, "sempre"),
    ("cataloghi-lingua", _cataloghi, "sempre"),
    ("dove-i-modelli", _dove_stanno_i_modelli, "sempre"),
    ("dati-librerie", _dati_delle_librerie, "sempre"),
    ("moduli-nascosti", _moduli_nascosti, "sempre"),
    ("licenze", _licenze, "sempre"),
    ("immagini-foglio", _immagini_del_foglio, "qt"),
    ("legge-una-riga", _legge_una_riga, "sempre"),
    ("parla-davvero", _parla_davvero, "rete"),
    ("apre-la-finestra", _apre_la_finestra, "qt"),
]


def esegui(senza_rete: bool = False, senza_qt: bool = False) -> Rapporto:
    r = Rapporto()
    for nome, funzione, richiede in PROVE:
        if richiede == "rete" and senza_rete:
            r.righe.append({"prova": nome, "esito": "saltata",
                            "nota": "chiesto --senza-rete", "ms": 0.0})
            print(f" SALTATA  {nome:<22} chiesto --senza-rete", flush=True)
            continue
        if richiede == "qt" and senza_qt:
            r.righe.append({"prova": nome, "esito": "saltata",
                            "nota": "chiesto --senza-qt", "ms": 0.0})
            print(f" SALTATA  {nome:<22} chiesto --senza-qt", flush=True)
            continue
        r.prova(nome, funzione)
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.autoprova",
        description="Prova il pacchetto da dentro: i dati ci sono, e i motori funzionano.")
    ap.add_argument("rapporto", nargs="?", default="autoprova.json",
                    help="dove scrivere il rapporto JSON")
    ap.add_argument("--senza-rete", action="store_true",
                    help="salta le prove che scaricano un modello")
    ap.add_argument("--senza-qt", action="store_true",
                    help="salta le prove che costruiscono la finestra")
    args = ap.parse_args(argv)

    # **Chi simula scrive nel registro del banco.** Questa prova costruisce la
    # finestra, e `Finestra.__init__` apre il registro dell'utente: senza questa
    # riga, un'autoprova sporcherebbe il file dove si cercano i guasti veri — che
    # e' esattamente il difetto gia' chiuso una volta, quando 122 righe di guasto
    # finte scritte da `tools/scatta.py` sembravano venire dalla catena viva.
    from core import registro

    registro.banco()

    r = esegui(senza_rete=args.senza_rete, senza_qt=args.senza_qt)
    fuori = {
        "congelato": percorsi.congelato(),
        "radice": str(percorsi.radice()),
        "modelli": str(percorsi.modelli()),
        "cartella_di_lancio": os.getcwd(),
        "versione": _versione.VERSIONE,
        "revisione": _versione.revisione(),
        "python": sys.version.split()[0],
        "prove": r.righe,
        "rotte": len(r.rotte),
    }
    percorso = Path(args.rapporto)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(fuori, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nrapporto in {percorso.resolve()} — {len(r.rotte)} prove rotte su {len(r.righe)}",
          flush=True)
    return 1 if r.rotte else 0


if __name__ == "__main__":
    raise SystemExit(main())
