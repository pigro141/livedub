"""Fotografa la finestra nei due temi, **senza aprire il gioco e senza aprirla**.

    .\\.venv\\Scripts\\python.exe -m tools.scatta runs\\menta
    .\\.venv\\Scripts\\python.exe -m tools.scatta runs\\menta --profile gtav --tema chiaro

Esiste per la stessa ragione di `tools/overlay_mp4.py`. **Il pezzo peggiore mai
consegnato in questo progetto e' arrivato verde e con gli import a posto**, e il
difetto era il primo che si vedeva mettendolo a schermo: la finestra dimensionata
sul testo originale con dentro quello tradotto. Nessuna verifica lo prendeva
perche' non ne esisteva nessuna su quel pezzo, e la suite verde e' stata scambiata
per una conferma. Quindi la regola e' che dopo ogni ritocco alla grafica si
guarda un'immagine — e se guardarla costa una sessione col gioco acceso, dopo due
giri nessuno ne fa un terzo e si consegna una cosa sbagliata.

**Tre cose che questo strumento fa e che a mano non verrebbero mai.**

`WA_DontShowOnScreen`: la finestra viene costruita, misurata e disegnata senza
comparire. Non e' comodita' — e' che una finestra che lampeggia sul desktop
mentre si scattano dodici immagini fa chiudere lo strumento al secondo giro.

**Non `QT_QPA_PLATFORM=offscreen`.** Sembra la strada ovvia ed e' una trappola:
la piattaforma offscreen ha **zero famiglie di caratteri** installate, quindi
restituisce una finestra piena di quadratini. E' una fotografia che non puo'
mostrare il difetto che si sta cercando — la stessa forma di «controllare che la
misura possa esprimere la risposta», portata su un'immagine.

`tema.attuale` **forzata**: i due temi si guardano tutti e due sempre. Il tema
chiaro e' quello che non guarda mai nessuno, ed e' li' che sono finiti il
`#39d353` scritto a mano e il contorno preso dalla tavolozza sbagliata.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import preferenze  # noqa: E402
from ui import qt_tema as tema  # noqa: E402


class _Args:
    """Quello che la finestra si aspetta dalla riga di comando, tutto spento.

    `no_save=True` perche' scattare non deve creare una cartella in `runs/`: una
    sessione finta in mezzo a quelle vere e' rumore in un archivio che serve a
    rileggere le prove.
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


def _finta_sessione(f) -> None:
    """Riempie la finestra come sarebbe **a meta' partita**.

    A finestra vuota si vedono la testata e i tre passi, cioe' meta' del
    disegno: le marche di gravita', i colori dei personaggi, la tessera del
    guasto e i numeri fuori norma esistono solo mentre qualcosa va (o non va).
    Quello che non si riempie non si guarda, e quello che non si guarda si
    consegna rotto.
    """
    from core.motore import Misura

    f._mostra_log()
    # La dissolvenza dei tre passi dura 200 ms e nessuno li aspetta: senza
    # questa riga la fotografia esce con il pannello ancora sopra il log,
    # cioe' mostra uno stato che dal vivo dura un quinto di secondo.
    f._guscio_passi.setVisible(False)
    f.stato("in corso  |  120 frame  |  34 battute  |  6 personaggi  |  4 voci")
    f.scrivi("carico piper...")
    f.scrivi("! l'area e' alta 0,180 dello schermo: tirala stretta attorno alla riga")
    for sid, voce, testo in (
        ("M1", "it_riccardo", "Lamar, che cazzo stai facendo?"),
        ("M2", "it_paola", "Niente, fratello."),
        ("M1", "it_riccardo", "Non ci credo neanche un po'."),
    ):
        f._scrivi_voce(sid, f"  12.4s · {sid} · {voce} · 620 ms · {testo}")
    f.scrivi("! l'audio si e' fermato: OSError: [Errno -9988] Stream closed")

    f._in_attesa[:] = ["vision.ocr_backend", "tts.backend"]
    f.striscia.setVisible(True)
    f.l_attesa.setText(
        "2 modifiche in attesa (vision.ocr_backend, tts.backend): si applicano "
        "rifacendo la catena, un paio di secondi")
    f.tessera.mostra(
        "L'audio si e' fermato", "OSError: [Errno -9988] Stream closed",
        "Probabile: cuffie o altoparlanti staccati, oppure il device e' cambiato "
        "sotto i piedi. Ricollega e premi RIPROVA.")
    # Con un valore in ambra e uno in rosso: sono gli unici due stati che quella
    # barra sa dire, e vanno visti tutti e due almeno una volta.
    f.misura.mostra([
        Misura("", "in corso"), Misura("OCR", "12.3 Hz", "avviso"),
        Misura("battute", "34"), Misura("latenza p50", "1150 ms"),
        Misura("compress.", "1.23"), Misura("underrun", "3", "guasto"),
        Misura("ROI", "x0.204 y0.884 w0.592 h0.070"),
    ])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.scatta", description="Le schermate della finestra, nei due temi")
    ap.add_argument("fuori", help="la cartella in cui scrivere i PNG")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--tema", choices=("scuro", "chiaro", "tutti"), default="tutti")
    # **La lingua della finestra si fotografa come il tema.** «Impostazioni
    # avanzate» in tedesco e' molto piu' lungo che in italiano, e una riga che
    # sfora non si vede nella suite: si vede nell'immagine. Il nome del file la
    # porta, se no due passate in due lingue si sovrascrivono a vicenda.
    ap.add_argument("--lingua", default=None,
                    help="il codice di `ui.lingua` (it, en, de, ar…)")
    ap.add_argument("--largo", type=int, default=tema.LARGO)
    ap.add_argument("--alto", type=int, default=tema.ALTO)
    args = ap.parse_args(argv)

    fuori = Path(args.fuori)
    fuori.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")

    from tools.ui_qt import Finestra

    tavolozze = {"scuro": tema.SCURA, "chiaro": tema.CHIARA}
    scelte = tavolozze if args.tema == "tutti" else {args.tema: tavolozze[args.tema]}

    vero = tema.attuale
    scritti = 0
    sigla = f"{args.lingua}-" if args.lingua else ""
    try:
        for nome, tavolozza in scelte.items():
            tema.attuale = lambda _a, _t=tavolozza: _t
            cfg, _ = preferenze.riprendi(args.profile, None)
            if args.lingua:
                cfg.ui.lingua = args.lingua
            finti = _Args()
            finti.profile = args.profile
            f = Finestra(cfg, finti)
            f.resize(args.largo, args.alto)
            f.setAttribute(Qt.WA_DontShowOnScreen, True)
            f.show()
            app.processEvents()
            try:
                for i in range(f.schede.count()):
                    f.schede.setCurrentIndex(i)
                    app.processEvents()
                    etichetta = f.schede.tabText(i).split()[0].lower()
                    f.grab().save(str(fuori / f"{sigla}{nome}-{i}-{etichetta}.png"))
                    scritti += 1
                f.schede.setCurrentIndex(f.SESSIONE)
                _finta_sessione(f)
                app.processEvents()
                f.grab().save(str(fuori / f"{sigla}{nome}-viva.png"))
                scritti += 1
            finally:
                f.close()
    finally:
        tema.attuale = vero

    print(f"{scritti} schermate in {fuori}")
    print("Guardale al 100%: il logo a 64 px e' l'unica taglia a cui si vede se e'")
    print("ancora riconoscibile, e i contrasti si giudicano a grandezza vera.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
