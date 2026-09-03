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

from core import preferenze, registro  # noqa: E402
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


def _lascia_finire(app, ms: int) -> None:
    """Fa girare il ciclo degli eventi per `ms`, e non e' un `sleep`.

    Le animazioni di Qt avanzano su un timer: senza un ciclo che gira, una
    dissolvenza resta ferma sul suo primo fotogramma per sempre. Un `sleep`
    aspetterebbe senza far avanzare niente, cioe' costerebbe il tempo e non
    darebbe il risultato.
    """
    import time as _t

    fine = _t.perf_counter() + ms / 1000.0
    while _t.perf_counter() < fine:
        app.processEvents()


def _finta_sessione(app, f) -> None:
    """Riempie la finestra come sarebbe **a meta' partita**.

    A finestra vuota si vedono la testata e i tre passi, cioe' meta' del
    disegno: le marche di gravita', i colori dei personaggi, la tessera del
    guasto e i numeri fuori norma esistono solo mentre qualcosa va (o non va).
    Quello che non si riempie non si guarda, e quello che non si guarda si
    consegna rotto.
    """
    from core.motore import ACCESA, Misura

    # **L'orologio della misura si ferma**, se no fotografiamo la sua ultima
    # passata invece della nostra. I numeri qui sotto sono scritti a mano proprio
    # perche' una catena spenta ne darebbe sei a zero — e quel timer gira a 2 Hz,
    # quindi finora quei valori sopravvivevano solo perche' lo scatto arrivava
    # prima. Con la fase della catena nella tessera si vedeva: diceva «fermo»
    # accanto a una spia accesa.
    f.orologio_misura.stop()
    f._mostra_log()
    # La dissolvenza dei tre passi dura 200 ms e nessuno li aspetta: senza
    # questa riga la fotografia esce con il pannello ancora sopra il log,
    # cioe' mostra uno stato che dal vivo dura un quinto di secondo.
    f._guscio_passi.setVisible(False)
    # **Anche i bottoni devono dire che la sessione e' accesa.** Finora questa
    # scena fotografava un log vivo sopra un Avvia premibile e un Ferma spento —
    # cioe' proprio lo stato incoerente in cui il programma si e' piantato, messo
    # in una fotografia di riferimento senza che nessuno lo notasse. Lo stato e'
    # uno solo (`core.motore`), quindi per fingere una sessione viva si scrive
    # quello e si ridipinge: non c'e' un secondo posto in cui mentire.
    f.motore._stato = ACCESA
    f._dipingi_bottoni()
    f.stato("in corso  |  120 frame  |  34 battute  |  6 personaggi  |  4 voci")
    f.scrivi("carico piper...")
    f.scrivi("! l'area e' alta 0,180 dello schermo: tirala stretta attorno alla riga")
    # **Le battute passano dalla strada vera**, cioe' la stessa che percorre il
    # messaggio `riga` della coda: il log, la tessera della battuta di adesso e
    # la fila dei personaggi. Riempire solo il log fotograferebbe meta' della
    # scheda — ed era gia' successo, con l'altra meta' consegnata «supposta».
    for sid, voce, testo, lat, fretta in (
        ("M1", "it_riccardo", "Lamar, che cazzo stai facendo?", 620, 1.00),
        ("M2", "it_paola", "Niente, fratello.", 710, 1.18),
        ("M3", "it_neutra", "Ehi, voi due!", 980, 1.00),
        ("M1", "it_riccardo", "Non ci credo neanche un po'.", 640, 1.12),
    ):
        f._scrivi_voce(sid, f"  12.4s · {sid} · {voce} · {lat} ms · {testo}")
        f._conta[sid] = f._conta.get(sid, 0) + 1
        f.ora.dillo(sid, voce, testo, f._colore_voce(sid), lat, fretta)
        f.personaggi.aggiorna(f._conta, f._colore_voce)
    # **Le transizioni vanno lasciate finire prima di scattare.** Ogni tessera di
    # personaggio compare sfumando, e una dissolvenza che nessuno fa girare
    # lascia il widget a opacita' zero: la prima passata di queste schermate ha
    # fotografato una fila di personaggi **vuota** sotto il suo titolo. E' la
    # stessa ragione per cui i tre passi si nascondono a mano qui sopra — una
    # fotografia deve mostrare lo stato in cui si sta, non quello da cui si sta
    # uscendo.
    _lascia_finire(app, 2 * tema.MS_CONTROLLO)
    # La fase si mette **dopo** aver fatto girare gli eventi: prima, il giro
    # dell'orologio della misura la riscriveva con quella di una catena spenta.
    from core.motore import fase_catena

    f.ora.mostra_fase(f._fase_tradotta(fase_catena({"viva": True, "parla": True})),
                      f.tavolozza.accento, True)
    # **Il guasto da fotografare dev'essere un guasto che puo' capitare.** Qui
    # c'era `[Errno -9988] Stream closed`, e -9988 e' `paBadStreamPtr`: quello
    # succede solo se **noi** chiudiamo il flusso mentre qualcuno ci sta ancora
    # leggendo, cioe' mai (misurato: cinque Ferma di fila, zero guasti). Non e'
    # nemmeno `paInputOverflowed`, che sarebbe -9981. La scritta finta descriveva
    # un caso impossibile, e su quello si e' indagato per una sessione intera.
    # -9985 e' `paDeviceUnavailable`: le cuffie staccate, cioe' proprio cio' che
    # la tessera qui sotto dice di fare.
    f.scrivi("! l'audio si e' fermato: OSError: [Errno -9985] Device unavailable")

    f._in_attesa[:] = ["vision.ocr_backend", "tts.backend"]
    f.striscia.setVisible(True)
    f.l_attesa.setText(
        "2 modifiche in attesa (vision.ocr_backend, tts.backend): si applicano "
        "rifacendo la catena, un paio di secondi")
    f.tessera.mostra(
        "L'audio si e' fermato", "OSError: [Errno -9985] Device unavailable",
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


# ======================================================== la scena di vetrina ==
#
# **Una seconda scena, perche' e' una seconda domanda.** `_finta_sessione` mette
# in campo la tessera rossa del guasto audio, la striscia ambra delle modifiche
# in attesa e un `underrun` in rosso: e' giusta per il suo scopo, che e' guardare
# gli stati brutti — quelli esistono solo mentre qualcosa non va, e quello che
# non si guarda si consegna rotto. Ma usata per rispondere ad «ecco com'e' il
# programma» dice **rotto** di un prodotto che funziona: non e' piu' onesta di
# una che nasconde il guasto, e' imprecisa nella direzione opposta.
#
# **E i numeri non si inventano.** Tutti quelli qui sotto vengono da una sola
# sessione **dal vivo**, `runs/2026-08-20_00-01-56`: undici minuti di GTA V in
# italiano con Kokoro su CUDA, 146 battute doppiate, `mix.underrun` 0. Il
# ritratto e' quella sessione a **6'21"**, cioe' all'istante della battuta
# `E sempre San Andreas.`; le battute, le sigle, le voci, le latenze e la fretta
# sono copiate riga per riga da `speaker.jsonl`, i conteggi contati li' dentro.
#
# Un solo numero e' del **quadro intero** e non di quell'istante, e vale la pena
# dirlo invece di lasciarlo credere esatto: la latenza p50. La barra scrive
# `dub.latency_live` (non `dub.latency`, che nel `report.txt` e' 1290) e quella
# quantita' esiste **solo** come aggregato di fine sessione — 1949 ms. Le altre
# tengono: `underrun` e' un contatore che sale, zero alla fine vuol dire zero
# anche prima; la compressione e' la mediana della fretta delle battute fino a
# li'; l'OCR e' `vision.read` su tutta la sessione (10724 letture in 674,9 s),
# che a cattura ferma non si muove.
#
# La riga ambra sulla ROI **ci resta**. E' vera — quella sessione aveva l'area
# alta 0,214 e la finestra sopra 0,12 lo dice — ed e' un avviso, cioe' una marca
# da tre pixel nel margine, non un guasto. Toglierla farebbe di questa
# fotografia una sessione mai esistita. (E vale la pena saperlo: **nessuna**
# delle sessioni del 19-20 agosto sta sotto 0,12, la piu' stretta e' 0,147.
# Quel consiglio non lo segue nessuno, il che e' un problema del prodotto e non
# della fotografia.)
SESSIONE = "runs/2026-08-20_00-01-56"

# `sid -> battute` **in ordine di comparsa**, fino a un attimo prima delle sette
# qui sotto. L'ordine e' l'informazione: `_colore_voce` assegna le tinte in
# ordine di prima comparsa, quindi seminare i conteggi in un ordine diverso
# darebbe a ogni personaggio il colore di un altro.
PRIMA = (("S?", 21), ("S13", 10), ("S4", 31), ("S1", 7), ("S12", 1), ("S11", 1),
         ("S14", 1))

# Le sette battute a schermo: `(secondo, sigla, voce, latenza ms, fretta, testo)`.
# Sono consecutive e vere. Due personaggi che si rispondono, due voci diverse
# dallo stesso modello a semitoni diversi — che e' il pregio del prodotto, e su
# una fila di battute dello stesso personaggio non si vedrebbe.
BATTUTE = (
    (361.0, "S4", "nicola-2_5", 1312, 1.00, "Eccola. Quella distesa disordinata. Los Santos."),
    (367.0, "S4", "nicola-2_5", 1026, 1.00, "Oh. Ci siamo! Ci siamo!"),
    (371.9, "S1", "nicola+2_5", 1105, 1.00, "Quindi questa è Los Santos?"),
    (374.5, "S4", "nicola-2_5", 948, 1.00, "Direi di sì."),
    (376.7, "S1", "nicola+2_5", 1080, 1.00, "Ho sempre voluto venire qui."),
    (378.9, "S4", "nicola-2_5", 1203, 1.00, "Ma sei rimasto bloccato nel deserto?"),
    (381.0, "S1", "nicola+2_5", 1705, 1.00, "E sempre San Andreas."),
)

# La ROI di quella sessione, dal suo `config.json`.
ROI = (0.232, 0.786, 0.599, 0.214)


def _vetrina(app, f, fuori: Path, sigla: str) -> int:
    """Il programma **mentre lavora**, senza niente di rotto addosso.

    Passa dalle stesse strade del vivo — `motore.barra_misura` per i numeri in
    fondo, `motore.fase_catena` per la parola in cima, `_scrivi_voce` e
    `ora.dillo` per le battute — perche' un secondo posto in cui decidere di che
    colore va un numero e' un posto che si scolla dal primo senza dare errore.
    Qui si scrivono i **dati**, non i verdetti.
    """
    from core.motore import ACCESA, barra_misura, fase_catena

    f.orologio_misura.stop()
    f._mostra_log()
    f._guscio_passi.setVisible(False)
    f.motore._stato = ACCESA
    f._dipingi_bottoni()
    f.scrivi("carico kokoro...")
    f.scrivi(f"! l'area e' alta {ROI[3]:.3f} dello schermo: tirala stretta "
             f"attorno alla riga")

    # I conteggi di prima si seminano **senza** scrivere le loro battute nel
    # log: il log e' scorrevole e a schermo se ne vedono le ultime, ma la fila
    # dei personaggi e' cumulativa dall'inizio della sessione. Le due cose
    # rispondono a due domande diverse e vanno riempite in due modi diversi.
    for sid, quante in PRIMA:
        f._conta[sid] = quante
        f._colore_voce(sid)
    f.personaggi.aggiorna(f._conta, f._colore_voce)

    for t, sid, voce, lat, fretta, testo in BATTUTE:
        f._scrivi_voce(sid, f"{t:6.1f}s · {sid} · {voce} · {lat:.0f} ms · {testo}")
        f._conta[sid] = f._conta.get(sid, 0) + 1
        f.ora.dillo(sid, voce, testo, f._colore_voce(sid), lat, fretta)
        f.personaggi.aggiorna(f._conta, f._colore_voce)

    battute = sum(f._conta.values())
    # `n` sono i fotogrammi catturati (`vision.read` a 15,9 Hz per 381 s), `p` le
    # identita' vive scritte nella battuta stessa (`identita_vive`: 15) e le voci
    # il `pool_size` di quella configurazione. La riga la compone `core/motore.py`
    # ogni trenta fotogrammi: qui si ricopia la sua forma, non se ne inventa una.
    f.stato(f"in corso  |  6060 frame  |  {battute} battute  |  15 personaggi  |"
            f"  6 voci")

    # **Le dissolvenze si lasciano finire prima di scattare.** Ogni tessera di
    # personaggio compare sfumando, e un velo che nessuno fa girare lascia il
    # widget a opacita' zero: la fila uscirebbe vuota sotto il suo titolo.
    _lascia_finire(app, 2 * tema.MS_CONTROLLO)

    f.ora.mostra_fase(f._fase_tradotta(fase_catena({"viva": True, "parla": True})),
                      f.tavolozza.accento, True)
    # I verdetti — quale numero va in ambra, quale in rosso — li da' la regola,
    # non questa funzione: qui si consegna il dizionario che `misure()`
    # consegnerebbe dal vivo.
    f.misura.mostra(barra_misura({
        "stato": f._stato_testo,
        "viva": True,
        "ocr_hz": 15.9,
        "battute": battute,
        "latenza_ms": 1949.0,
        "compressione": 1.00,
        "underrun": 0,
        "roi": ROI,
    }))
    app.processEvents()
    f.grab().save(str(fuori / f"{sigla}-vetrina.png"))
    return 1


def _elenco(app, fuori: Path, sigla: str, tavolozza) -> int:
    """I quattro stati di una riga d'elenco, **fotografati davvero**.

    E' il difetto da cui e' partita questa sessione: «passando sopra a quella
    gia' selezionata il testo non si legge». Il contrasto lo misura la suite
    (1,12:1 prima, 13,95 dopo, sul tema scuro), ma il numero non dice che la riga
    scelta smetteva anche di **sembrare** scelta — e quello si vede solo qui.

    Lo stato «sotto il mouse» sembra impossibile da fotografare senza un mouse, e
    non lo e': la vista tiene la riga sotto il puntatore in base agli eventi
    `QHoverEvent` che riceve, e un evento si puo' mandare. Con
    `WA_DontShowOnScreen` non c'e' nessun cursore vero, e l'immagine esce lo
    stesso — cioe' si puo' guardare un difetto di interazione dentro uno
    strumento che non interagisce con niente.

    Due immagini e non una: in una riga sola non si possono avere insieme
    «scelta» e «scelta sotto il mouse».
    """
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QHoverEvent
    from PySide6.QtWidgets import QListWidget, QVBoxLayout, QWidget

    scritti = 0
    for numero, (scelta, sopra) in enumerate(((2, 1), (1, 1)), start=1):
        w = QWidget()
        w.setStyleSheet(tema.foglio(tavolozza))
        L = QVBoxLayout(w)
        L.setContentsMargins(tema.S3, tema.S3, tema.S3, tema.S3)
        lista = QListWidget()
        for i, testo in enumerate(("normale", "sotto il mouse", "scelta", "normale")):
            lista.addItem(f"   riga {i} — {testo}")
        L.addWidget(lista)
        w.resize(460, 190)
        w.setAttribute(Qt.WA_DontShowOnScreen, True)
        w.show()
        app.processEvents()
        lista.setCurrentRow(scelta)
        p = QPointF(lista.visualItemRect(lista.item(sopra)).center())
        app.sendEvent(lista.viewport(), QHoverEvent(QEvent.HoverEnter, p, p, p))
        app.sendEvent(lista.viewport(), QHoverEvent(QEvent.HoverMove, p, p, p))
        app.processEvents()
        w.grab().save(str(fuori / f"{sigla}-elenco-{numero}.png"))
        scritti += 1
        w.close()
    return scritti


def _movimento(app, f, fuori: Path, sigla: str) -> int:
    """Le due animazioni, **a fotogrammi scelti**.

    Un'animazione non si vede in una schermata, e in questo progetto un pezzo che
    nessuno ha guardato non e' «scritto», e' «supposto». Provare a coglierla al
    volo con un `processEvents` darebbe un'immagine diversa a ogni giro — e una
    misura che non puo' esprimere la risposta risponde comunque. Qui il
    fotogramma si sceglie: `posa()` ferma la barra dove si vuole.

    Tre del velo, che copre il cambio di lingua: mentre entra, a coperta piena e
    mentre esce. Uno della barra dell'avvio, che e' indeterminata e sta dentro la
    tessera della battuta — l'unico movimento lungo della finestra, e l'unico che
    aspetta qualcosa invece di accompagnare un cambiamento.
    """
    scritti = 0
    for i, (velatura, avanzamento) in enumerate(
            ((0.35, 0.20), (1.00, 0.60), (0.45, 0.98))):
        f.velo.posa(velatura, avanzamento)
        app.processEvents()
        f.grab().save(str(fuori / f"{sigla}-velo-{i + 1}.png"))
        scritti += 1
    f.velo.hide()
    # **La barra dell'avvio si fotografa sulla tessera vuota**, che e' com'e'
    # davvero: fra Avvia e la prima battuta non c'e' ancora niente da dire. Con
    # sopra una battuta finta si vedrebbe una barra di caricamento accanto a una
    # cosa gia' caricata, cioe' un'immagine che non capita mai.
    from core.motore import fase_catena

    f._svuota_sessione(forza=True)
    # E la fase torna quella di una catena che non ha ancora parlato: «sta
    # parlando» sopra «in attesa della prima frase» sarebbe un'immagine che
    # dice due cose diverse nello stesso riquadro.
    f.ora.mostra_fase(f._fase_tradotta(fase_catena({"viva": True})),
                      f.tavolozza.accento, False)
    f.ora.barra.posa(0.30, pieno=False)
    app.processEvents()
    f.grab().save(str(fuori / f"{sigla}-avvio.png"))
    f.ora.barra.ferma()
    return scritti + 1


def _tutorial(app, f, fuori: Path, sigla: str) -> int:
    """I passi della guida iniziale, uno per PNG.

    Il dialogo si costruisce col suo padre vero — cosi' eredita il foglio di
    stile della finestra, che e' il modo in cui lo vedra' l'utente — e si sposta
    di passo chiamando i suoi bottoni invece di premerli: `exec()` aprirebbe un
    ciclo di eventi che questa funzione non potrebbe piu' lasciare.
    """
    from ui.tutorial import PASSI, Tutorial

    d = Tutorial(f)
    d.setAttribute(Qt.WA_DontShowOnScreen, True)
    d.show()
    scritti = 0
    try:
        for i in range(len(PASSI)):
            app.processEvents()
            d.grab().save(str(fuori / f"{sigla}-guida-{i + 1}.png"))
            scritti += 1
            # **Il passo del banco ha tre stati e due non si vedono scorrendo.**
            # Aperto dice cosa c'e' e quanto costa premere; mentre scarica e a
            # scaricamento fallito non ci si arriva senza aspettare una rete
            # vera, e quello a rete rotta e' l'unico in cui il riquadro passa in
            # ambra — cioe' proprio il caso per cui il passo esiste.
            if PASSI[i].vivo == "banco":
                for stato, nome in (("in corso", "carica"), ("finito", "rotto")):
                    d.posa_banco(stato)
                    app.processEvents()
                    d.grab().save(str(fuori / f"{sigla}-guida-banco-{nome}.png"))
                    scritti += 1
                d.posa_banco("")
            d._avanti() if i < len(PASSI) - 1 else None
    finally:
        # Senza `reject` il dialogo segnerebbe la guida come vista sulla
        # macchina di chi scatta: una fotografia non e' una lettura.
        d.reject()
    return scritti


def _installa(app, f, fuori: Path, sigla: str) -> int:
    """Il riquadro che offre di installare, nei suoi tre stati.

    Due dei tre non si vedono aprendolo: «sta scaricando» vuole una rete e un
    gigabyte di attesa, «non e' arrivato» vuole una rete rotta. Sono anche gli
    unici due in cui il riquadro dice qualcosa di diverso da «premi qui», quindi
    sono quelli che vale la pena guardare.
    """
    from ui.qt_installa import DialogoInstalla

    d = DialogoInstalla("tts.backend", "kokoro",
                        ("cuda", "kokoro", "voci_kokoro"), f.cfg, f,
                        congelato=False)
    d.setAttribute(Qt.WA_DontShowOnScreen, True)
    d.show()
    scritti = 0
    try:
        for stato, nome in (("", "offerta"), ("in corso", "carica"),
                            ("rotto", "rotto")):
            d.posa(stato)
            app.processEvents()
            d.grab().save(str(fuori / f"{sigla}-installa-{nome}.png"))
            scritti += 1
    finally:
        d.reject()

    # **Il quarto stato e' l'unico che non ha un bottone, ed e' quello che
    # l'utente ha fotografato al contrario.** Dentro il pacchetto congelato
    # «Installa» apriva una porta chiusa: si premeva e usciva un `RuntimeError`.
    # Adesso lo si dice prima, e questa e' l'immagine che lo prova — da sorgente,
    # perche' `congelato` arriva da fuori apposta.
    g = DialogoInstalla("translate.backend", "locale", ("argos", "traduzione"),
                        f.cfg, f, congelato=True)
    g.setAttribute(Qt.WA_DontShowOnScreen, True)
    g.show()
    try:
        app.processEvents()
        g.grab().save(str(fuori / f"{sigla}-installa-daquino.png"))
        scritti += 1
    finally:
        g.reject()
    return scritti


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
    # **Il tutorial e' un dialogo, quindi non lo si vede scattando le schede.**
    # Non esiste finche' non lo si apre, e la regola di questo progetto e' che un
    # pezzo che nessuno ha guardato non e' scritto, e' supposto. Qui si apre e si
    # fotografa passo per passo, nei due temi, con lo stesso metodo.
    ap.add_argument("--installa", action="store_true",
                    help="il riquadro che offre di installare una scelta")
    ap.add_argument("--tutorial", action="store_true",
                    help="fotografa i passi della guida iniziale invece delle schede")
    # **La scena di vetrina risponde a un'altra domanda** e per questo e' un'altra
    # scena: si veda il commento sopra `_vetrina`. Una sola scena che serva sia a
    # guardare i guasti sia a mostrare il prodotto finisce per fare male tutte e
    # due le cose.
    ap.add_argument("--vetrina", action="store_true",
                    help="una sola schermata: la sessione viva e sana, coi numeri "
                         f"di {SESSIONE}")
    ap.add_argument("--largo", type=int, default=tema.LARGO)
    ap.add_argument("--alto", type=int, default=tema.ALTO)
    args = ap.parse_args(argv)

    fuori = Path(args.fuori)
    fuori.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")

    # **Da qui in poi il registro e' quello di banco.** Le righe che riempiono
    # queste schermate — battute, avvisi, il guasto audio — passano da
    # `Finestra.scrivi`, che scrive anche su file: senza questa riga finivano nel
    # registro dell'utente, e ci sono finite 56 volte.
    registro.banco()

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
            if args.tutorial or args.vetrina or args.installa:
                scena = (_tutorial if args.tutorial
                         else _installa if args.installa else _vetrina)
                try:
                    scritti += scena(app, f, fuori, f"{sigla}{nome}")
                finally:
                    f.close()
                continue
            try:
                for i in range(f.schede.count()):
                    f.schede.setCurrentIndex(i)
                    app.processEvents()
                    etichetta = f.schede.tabText(i).split()[0].lower()
                    f.grab().save(str(fuori / f"{sigla}{nome}-{i}-{etichetta}.png"))
                    scritti += 1
                f.schede.setCurrentIndex(f.SESSIONE)
                _finta_sessione(app, f)
                app.processEvents()
                f.grab().save(str(fuori / f"{sigla}{nome}-viva.png"))
                scritti += 1
                scritti += _movimento(app, f, fuori, f"{sigla}{nome}")
                scritti += _elenco(app, fuori, f"{sigla}{nome}", tavolozza)
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
