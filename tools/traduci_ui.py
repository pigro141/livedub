"""I cataloghi della finestra: si estraggono, si traducono, si **scrivono nel repo**.

    .\\.venv\\Scripts\\python.exe -m tools.traduci_ui --estrai
    .\\.venv\\Scripts\\python.exe -m tools.traduci_ui de fi ja --backend google
    .\\.venv\\Scripts\\python.exe -m tools.traduci_ui --controlla
    .\\.venv\\Scripts\\python.exe -m tools.traduci_ui --misura de

**Si genera prima e si committa il risultato.** Una finestra che chiede la
traduzione alla rete mentre si apre e' una finestra in bianco quando la rete non
c'e' — e in bianco *senza errore*, che e' la forma di difetto che questo progetto
paga da anni. Qui la rete si tocca una volta, a mano, e quello che esce sta in
`ui/lingue/*.json`.

## Le chiavi non si scrivono: si guarda la finestra

`--estrai` costruisce la finestra vera, offscreen, e le chiede tutte le stringhe
che dice (`ui.lingua.raccogli`). E' **la stessa passeggiata** che poi le
riscrive: l'estrattore e chi applica non possono vedere due elenchi diversi.
Un `grep` dei letterali darebbe invece stringhe che non compaiono mai e
perderebbe quelle costruite in due pezzi.

## Si traduce solo cio' che manca

Rilanciare non rifa' tutto: un catalogo gia' scritto si tiene, e si chiedono
soltanto le chiavi nuove. Cosi' aggiungere un bottone costa una riga di rete per
lingua, e le traduzioni ritoccate a mano non vengono sovrascritte da una macchina.

## In blocchi, e il blocco si controlla

Google prende piu' righe in una richiesta e ne restituisce altrettante, quindi un
catalogo intero costa una dozzina di viaggi invece di duecento. Ma «altrettante»
va **verificato**: se il conto delle righe non torna, le traduzioni scivolerebbero
di una e ogni bottone prenderebbe il testo di quello dopo — un difetto che a
schermo sembra un catalogo tradotto male, non un blocco disallineato. Quando il
conto non torna si ricade sulla riga per riga, che e' lenta e non sbaglia.

## `--misura` non e' un di piu'

Costruisce la finestra **con quel catalogo addosso** e chiede a ogni scheda la
sua larghezza minima. E' la versione misurabile di «controlla che il testo non
sfori»: «Impostazioni avanzate» in tedesco e' molto piu' lungo che in italiano, e
una scheda che non sta piu' nel minimo della finestra non si vede finche' non si
prova a stringerla.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import lingua as L  # noqa: E402

# Quante righe per richiesta. Non e' una taratura fine: e' abbastanza grande da
# togliere il costo dei viaggi e abbastanza piccolo che una richiesta rifiutata
# costi poco a rifare.
BLOCCO = 40


# ----------------------------------------------------------- la finestra --


def _finestra(app, cfg=None):
    """La finestra vera, costruita e non mostrata.

    **Non con `QT_QPA_PLATFORM=offscreen`** quando si vuole guardarla: quella
    piattaforma ha zero caratteri installati. Qui pero' non si guarda niente —
    si leggono le stringhe e le larghezze minime — e le larghezze *dipendono dal
    carattere*, quindi la misura si fa con la piattaforma vera e
    `WA_DontShowOnScreen`, come `tools/scatta.py`.
    """
    from PySide6.QtCore import Qt

    from core import preferenze
    from tools.ui_qt import Finestra
    from ui import qt_tema as tema

    class _Args:
        profile = None; loopback = "voicemeeter"; output = None; block = 480
        backend = "auto"; monitor = 1; tts = None; no_save = True; avvia = False
        overlay_catturabile = False; overrides = None

    if cfg is None:
        cfg, _ = preferenze.riprendi(None, None)
    f = Finestra(cfg, _Args())
    f.resize(tema.LARGO, tema.ALTO)
    f.setAttribute(Qt.WA_DontShowOnScreen, True)
    f.show()
    app.processEvents()
    return f


def _app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    return app


def estrai() -> int:
    """Scrive `ui/lingue/_chiavi.json` guardando la finestra."""
    import json

    app = _app()
    f = _finestra(app)
    try:
        voci = L.raccogli(f)
    finally:
        f.close()
    # **Piu' i pezzi che nessuna passeggiata puo' vedere**: quelli che a schermo
    # esistono solo gia' uniti e quelli di una finestra che non esiste finche'
    # non la si apre — si veda `ui.lingua.fuori_dalla_passeggiata`. Stanno qui e
    # non dentro `raccogli` perche' quella funzione deve restare **la stessa
    # passeggiata** che poi riscrive i testi — se le due divergessero, il conto
    # «ogni stringa e' o tradotta o lasciata in italiano» smetterebbe di
    # tornare, e con lui il contatore che dice quanto manca a un catalogo.
    voci = list(dict.fromkeys([*voci, *L.fuori_dalla_passeggiata()]))
    L.CARTELLA.mkdir(parents=True, exist_ok=True)
    L.CHIAVI.write_text(
        json.dumps(voci, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(voci)} stringhe in {L.CHIAVI}")
    return 0


# ------------------------------------------------------------- tradurre --


def _traduttore(nome: str):
    from core.config import TranslateConfig
    from translate.base import make_traduttore

    return make_traduttore(TranslateConfig(enabled=True, backend=nome))


def _prova(tr, testo: str, a: str) -> str | None:
    """Una traduzione, con la rete che puo' dire di no.

    **Un errore di rete non deve buttare via le lingue gia' fatte.** Girando
    quaranta cataloghi di fila l'endpoint ogni tanto risponde con una pagina
    invece che con del JSON: senza questa rete di sicurezza il programma moriva
    alla diciottesima e le diciassette prima erano gia' su disco solo per
    fortuna — sono scritte a fine lingua.
    """
    try:
        return tr.traduci(testo, "it", a)
    except Exception as e:  # pragma: no cover - dipende dalla rete
        print(f"    (la rete ha detto di no: {e!r})")
        return None


def _blocco(tr, righe: list[str], a: str) -> list[str] | None:
    """Un blocco di righe in una richiesta sola, o `None` se il conto non torna."""
    fuori = _prova(tr, "\n".join(righe), a)
    if not fuori:
        return None
    pezzi = str(fuori).split("\n")
    return pezzi if len(pezzi) == len(righe) else None


def traduci(codici: list[str], backend: str, rifai: bool) -> int:
    chiavi = L.chiavi()
    if not chiavi:
        print("nessuna chiave: lancia prima `--estrai`", file=sys.stderr)
        return 2
    tr = _traduttore(backend)
    for codice in codici:
        if codice == L.SORGENTE:
            print("`it` e' la lingua del sorgente: non ha un catalogo")
            continue
        vecchio = {} if rifai else dict(L.carica(codice))
        # Le chiavi con dentro un a-capo non possono viaggiare in blocco: sono
        # loro il separatore. Vanno da sole, e sono poche.
        da_fare = [k for k in chiavi if k not in vecchio]
        intere = [k for k in da_fare if "\n" not in k]
        singole = [k for k in da_fare if "\n" in k]
        fatte = 0
        for i in range(0, len(intere), BLOCCO):
            pezzo = intere[i:i + BLOCCO]
            uscite = _blocco(tr, pezzo, codice)
            if uscite is None:
                uscite = [_prova(tr, k, codice) for k in pezzo]
            for k, v in zip(pezzo, uscite):
                if v and v.strip():
                    vecchio[k] = v.strip()
                    fatte += 1
            print(f"  {codice}: {fatte}/{len(da_fare)}", end="\r", flush=True)
        for k in singole:
            v = _prova(tr, k, codice)
            if v and v.strip():
                vecchio[k] = v.strip()
                fatte += 1
        # **Via le chiavi che la finestra non dice piu'.** Una stringa tolta dal
        # sorgente resterebbe nel catalogo per sempre: peso inutile, e — quel
        # che conta — una verifica che gira sul contenuto del file misurerebbe
        # traduzioni di testo che non compare da nessuna parte. E' successo:
        # togliendo dal catalogo l'elenco delle lingue, la verifica sulla
        # lunghezza continuava a lamentarsi di `uk — Ucraino`.
        vecchio = {k: v for k, v in vecchio.items() if k in set(chiavi)}
        percorso = L.scrivi(codice, vecchio, backend)
        buchi = len([k for k in chiavi if k not in vecchio])
        print(f"  {codice}: {len(vecchio)} voci, {buchi} ancora in italiano "
              f"-> {percorso}")
    return 0


# -------------------------------------------------------- e non sforare --


def misura(codici: list[str]) -> int:
    """Ogni scheda, con quel catalogo addosso, sta nel minimo della finestra?"""
    from core import preferenze
    from ui import qt_tema as tema

    app = _app()
    rotti = 0
    for codice in codici:
        cfg, _ = preferenze.riprendi(None, None)
        cfg.ui.lingua = codice
        f = _finestra(app, cfg)
        try:
            f.resize(tema.MIN_LARGO, tema.MIN_ALTO)
            app.processEvents()
            peggio = []
            for i in range(f.schede.count()):
                f.schede.setCurrentIndex(i)
                app.processEvents()
                largo = f.schede.widget(i).minimumSizeHint().width()
                if largo > tema.MIN_LARGO:
                    peggio.append((f.schede.tabText(i), largo))
            intera = f.minimumSizeHint().width()
            stato = "ok" if not peggio and intera <= tema.MIN_LARGO else "SFORA"
            print(f"{codice:>8}  finestra {intera:>4} / {tema.MIN_LARGO}  {stato}")
            for nome, largo in peggio:
                print(f"           scheda «{nome}» {largo}")
                rotti += 1
        finally:
            f.close()
    return 1 if rotti else 0


def controlla() -> int:
    chiavi = L.chiavi()
    print(f"{len(chiavi)} chiavi estratte")
    for codice in L.disponibili():
        if codice == L.SORGENTE:
            continue
        buchi = L.mancanti(codice)
        print(f"{codice:>8}  {len(chiavi) - len(buchi):>4}/{len(chiavi)}"
              + (f"   mancano: {buchi[0]!r}…" if buchi else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.traduci_ui",
        description="I cataloghi della finestra: estrarre, tradurre, misurare.")
    ap.add_argument("lingue", nargs="*", help="i codici da (ri)tradurre")
    ap.add_argument("--estrai", action="store_true", help="rifa' l'elenco delle chiavi")
    ap.add_argument("--controlla", action="store_true", help="quanto manca a ogni lingua")
    ap.add_argument("--misura", action="store_true",
                    help="con quel catalogo, le schede stanno nel minimo?")
    ap.add_argument("--backend", default="google",
                    help="locale | llm | ollama | google (default: google)")
    ap.add_argument("--rifai", action="store_true",
                    help="ritraduce anche le chiavi gia' presenti")
    args = ap.parse_args(argv)

    # La finestra si costruisce davvero: senza un carattere vero le larghezze
    # minime sarebbero quelle di un carattere che non esiste.
    os.environ.pop("QT_QPA_PLATFORM", None)

    if args.estrai:
        return estrai()
    if args.controlla:
        return controlla()
    if args.misura:
        return misura(list(args.lingue) or [x for x in L.disponibili()])
    if not args.lingue:
        ap.print_help()
        return 2
    return traduci(list(args.lingue), args.backend, args.rifai)


if __name__ == "__main__":
    raise SystemExit(main())
