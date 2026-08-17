"""Menta: le regole del disegno, provate **senza aprire una finestra**.

Il pezzo peggiore mai consegnato in questo progetto e' arrivato verde e con gli
import a posto, e il difetto era il primo che si vedeva mettendolo a schermo.
Quindi qui non si prova che «e' bello»: si prova quello che **non si vede
guardando**, e che rotto non da' errore.

| cosa | perche' proprio questa |
|---|---|
| `R(h)` | un raggio copiato da un elemento di altezza diversa e' plausibile |
| i contrasti | `#43f1c1` e' magnifico sul nero e fa **1,44:1** sul bianco |
| le ΔE fra le voci | sei colori che si confondono a coppie sembrano sei colori |
| la regola dei canali | il log smette di rispondere alla sua domanda **per gradi** |
| i colori fuori tavolozza | il `#39d353` scritto a mano funzionava, e si vedeva |
| i PNG generati | una `url()` a un nome inventato disegna un **quadrato** |
| `gravita` | avviso e guasto identici in mezzo a righe che scorrono |
| `barra_misura` | una soglia sbagliata li' non fa notare niente, che e' il punto |
| i due loghi | ritagliati stretti ciascuno sul suo, **saltano** al cambio |

Il resto — che il pannello dei passi si veda, che la pillola abbia un fondo —
si prova con uno screenshot, ed e' l'altra meta' del metodo.
"""

from __future__ import annotations

import re

from ui import qt_tema as tema

# Il bianco e il nero puri entrano solo dentro `rgba(...)`: sono la **luce** e
# l'**ombra** del materiale (§8), non colori d'interfaccia.
_AMMESSI_FUORI_TAVOLOZZA = {"#ffffff", "#000000"}


def _colori(t: tema.Tavolozza) -> set[str]:
    return {getattr(t, campo) for campo in
            ("fondo", "superficie", "superficie_alta", "bordo", "bordo_forte",
             "testo", "testo_tenue", "testo_fioco", "accento", "accento_chiaro",
             "accento_scuro", "su_accento", "ambra", "rosso")} | {tema.MENTA}


def test_menta(c) -> None:
    """La tavolozza, la geometria e il foglio di stile, come regole."""
    c.group("menta")

    # -- il raggio si ricava, non si sceglie -------------------------------
    # Dal logo: 19,8% dell'altezza, con un tetto perche' un pannello alto 600 px
    # non e' una pillola e un pavimento perche' sotto i 4 px un angolo si paga e
    # non si vede.
    for altezza, atteso in ((16, 4), (30, 6), (34, 7), (40, 8), (56, 11), (90, 18)):
        c.eq(tema.R(altezza), atteso, f"R({altezza}) = {atteso}")
    c.eq(tema.R(4), 4, "sotto il pavimento si resta a 4")
    c.eq(tema.R(600), 18, "sopra il tetto si resta a 18")
    c.ok(tema.R(34) != tema.R(400),
         "un bottone e un pannello non hanno lo stesso angolo: 8 px su 34 e 8 px "
         "su 400 sono due decisioni diverse travestite da una")
    for nome, valore, altezza in (("R_MARCA", tema.R_MARCA, 16),
                                  ("R_CAMPO", tema.R_CAMPO, 30),
                                  ("R_BOTTONE", tema.R_BOTTONE, 34),
                                  ("R_LINGUETTA", tema.R_LINGUETTA, 40),
                                  ("R_TESSERA", tema.R_TESSERA, 56),
                                  ("R_PANNELLO", tema.R_PANNELLO, 90)):
        c.eq(valore, tema.R(altezza), f"{nome} viene da R({altezza}), non da un'occhiata")
    # I tre cerchi: la stessa regola portata al limite, raggio = meta' del lato.
    for lato, raggio in ((tema.LATO_SPIA, tema.R_SPIA),
                         (tema.LATO_MANIGLIA, tema.R_MANIGLIA),
                         (tema.LATO_AIUTO, tema.R_AIUTO),
                         (tema.H_PILLOLA, tema.R_PILLOLA)):
        c.eq(raggio * 2, lato, f"un cerchio da {lato} ha raggio {lato // 2}")

    # -- le distanze: passo di quattro, otto valori ------------------------
    scala = (tema.S0, tema.S1, tema.S2, tema.S3, tema.S4, tema.S5, tema.S6, tema.S7)
    c.eq(scala, (2, 4, 8, 12, 16, 24, 32, 48), "la scala delle distanze e' quella dichiarata")
    c.ok(all(b > a for a, b in zip(scala, scala[1:])), "e cresce sempre")
    corpi = (tema.C_NOME, tema.C_STATO, tema.C_TITOLO, tema.C_TESTO, tema.C_NOTA)
    c.eq(corpi, (16, 13, 11, 10, 9), "cinque corpi, e non se ne aggiungono")
    c.ok(tema.MIN_LARGO < tema.LARGO and tema.MIN_ALTO < tema.ALTO,
         "la finestra predefinita e' piu' grande del minimo")
    # Un punto di rottura sotto il minimo della finestra **non scatta mai**: la
    # finestra non ci puo' arrivare.
    c.ok(tema.ROTTURA_SESSIONE > tema.MIN_LARGO,
         f"il punto di rottura ({tema.ROTTURA_SESSIONE}) e' raggiungibile sopra "
         f"il minimo ({tema.MIN_LARGO})")

    # -- i contrasti, misurati e non guardati ------------------------------
    for t in (tema.SCURA, tema.CHIARA):
        n = t.nome
        c.ok(tema.contrasto(t.testo, t.fondo) >= 7.0,
             f"[{n}] il testo sul fondo passa AAA "
             f"({tema.contrasto(t.testo, t.fondo):.1f}:1)")
        c.ok(tema.contrasto(t.testo_tenue, t.superficie) >= 4.5,
             f"[{n}] le note passano AA ({tema.contrasto(t.testo_tenue, t.superficie):.1f}:1)")
        c.ok(tema.contrasto(t.accento, t.superficie) >= 4.5,
             f"[{n}] l'accento come **testo** passa AA "
             f"({tema.contrasto(t.accento, t.superficie):.1f}:1)")
        for stato in ("ambra", "rosso"):
            r = tema.contrasto(getattr(t, stato), t.superficie)
            c.ok(r >= 4.5, f"[{n}] {stato} passa AA ({r:.1f}:1)")
        c.ok(tema.contrasto(t.su_accento, tema.MENTA) >= 4.5,
             f"[{n}] il testo sopra il riempimento menta passa AA "
             f"({tema.contrasto(t.su_accento, tema.MENTA):.1f}:1)")

    # **La regola che avrebbe fatto sbagliare tutto**, e che qui e' un caso
    # nullo: la menta e' magnifica sullo scuro (12,9:1) e chi la prova li'
    # conclude che funziona. Sul chiaro fa 1,44:1 — quindi il tema chiaro **non
    # puo'** usarla come testo, e questa verifica fallisce il giorno in cui
    # qualcuno «uniforma» le due tavolozze.
    c.ok(tema.contrasto(tema.MENTA, tema.CHIARA.superficie) < 3.0,
         f"la menta su bianco non si legge ({tema.contrasto(tema.MENTA, '#ffffff'):.2f}:1): "
         f"e' un riempimento, non un testo")
    c.ok(tema.CHIARA.accento != tema.MENTA,
         "quindi sul chiaro l'accento e' una menta scurita, e non la menta")
    c.eq(tema.SCURA.accento, tema.MENTA, "sullo scuro invece l'accento **e'** la menta")
    c.eq(tema.CHIARA.accento_chiaro, tema.MENTA,
         "e la menta resta nel tema chiaro come riempimento, cosi' Avvia e' lo "
         "stesso colore in tutti e due i temi")

    # -- le sei voci: distinguibili **fra loro**, non dal fondo ------------
    for t in (tema.SCURA, tema.CHIARA):
        c.eq(len(t.voci), 6, f"[{t.nome}] sei voci, come le voci del pool")
        peggiore = min(
            (tema.delta_e(a, b), a, b)
            for i, a in enumerate(t.voci) for b in t.voci[i + 1:])
        c.ok(peggiore[0] >= 25.0,
             f"[{t.nome}] due voci si distinguono anche di sfuggita "
             f"(ΔE minima {peggiore[0]:.1f} fra {peggiore[1]} e {peggiore[2]})")
        for v in t.voci:
            r = tema.contrasto(v, t.superficie)
            c.ok(r >= 4.5, f"[{t.nome}] la voce {v} si legge sul log ({r:.1f}:1)")
    c.ok(set(tema.SCURA.voci) != set(tema.CHIARA.voci),
         "le due file non sono l'una l'inverso dell'altra: i sei che si "
         "distinguono sul nero, sul bianco diventano pastelli")

    # -- la regola dei canali, che e' quella che tiene in piedi il sistema --
    # Sei voci piu' tre stati fanno nove tinte, e nove tinte non stanno sul
    # cerchio dei colori con margini comodi: la voce 1 e l'ambra distano **ΔE
    # 16**. La soluzione non e' cercare nove tinte perfette — non ci sono — e'
    # che le due famiglie non usino mai lo stesso canale. Le voci sono **colore
    # del testo** e vivono solo nel log; menta, ambra e rosso sono riempimenti,
    # marche e contorni. Quindi nessuna voce puo' comparire nel foglio di stile.
    for t in (tema.SCURA, tema.CHIARA):
        sheet = tema.foglio(t).lower()
        intruse = [v for v in t.voci if v.lower() in sheet]
        c.ok(not intruse,
             f"[{t.nome}] nessun colore delle voci entra nel foglio di stile "
             f"({intruse}): quelle sei tinte sono dei personaggi e di nessun altro")

    # -- un colore nuovo entra in Tavolozza o non entra --------------------
    # Il `#39d353` del selettore d'area e' l'esempio di come si comincia:
    # funziona, si vede, e nel tema chiaro non l'ha mai guardato nessuno.
    for t in (tema.SCURA, tema.CHIARA):
        sheet = tema.foglio(t)
        ammessi = {x.lower() for x in _colori(t)} | _AMMESSI_FUORI_TAVOLOZZA
        # I `#rrggbb` dentro un `url(...)` sono nomi di file generati, non colori
        # scritti nel foglio: si controllano piu' sotto, come file.
        senza_url = re.sub(r"url\([^)]*\)", "", sheet)
        trovati = {x.lower() for x in re.findall(r"#[0-9a-fA-F]{6}", senza_url)}
        c.ok(trovati <= ammessi,
             f"[{t.nome}] il foglio di stile non usa colori fuori tavolozza "
             f"({sorted(trovati - ammessi)})")

    # E lo stesso vale per la finestra: un colore scritto a mano li' e' come
    # quello di prima, solo piu' difficile da trovare.
    from pathlib import Path

    radice = Path(__file__).resolve().parent.parent
    for nome in ("tools/ui_qt.py", "ui/qt_pannello.py", "ui/qt_controlli.py",
                 "ui/qt_audio.py"):
        sorgente = (radice / nome).read_text(encoding="utf-8")
        # Via i commenti: li' un `#ff6b5e` e' una citazione, non un colore usato.
        codice = "\n".join(r.split("#", 1)[0] if r.lstrip().startswith("#") else r
                           for r in sorgente.splitlines())
        scritti = {x.lower() for x in re.findall(r'"(#[0-9a-fA-F]{6})"', codice)}
        c.ok(scritti <= {"#ffffff"},
             f"{nome} non scrive colori a mano: chiede la tavolozza ({sorted(scritti)})")

    # -- i due disegnini che Qt non sa fare da un foglio di stile ----------
    # Il trucco dei tre bordi CSS qui non funziona: Qt accetta quelle proprieta'
    # senza lamentarsi e disegna un **quadratino**. E una `url()` a un nome
    # inventato disegna un quadrato pieno — abbastanza chiaro da non accorgersene
    # subito, e sbagliato.
    for t in (tema.SCURA, tema.CHIARA):
        immagini = re.findall(r'url\("([^"]+)"\)', tema.foglio(t))
        c.ok(len(immagini) >= 6, f"[{t.nome}] il foglio punta a spunta e frecce "
                                 f"({len(immagini)} immagini)")
        mancanti = [p for p in immagini if not Path(p).exists()]
        c.ok(not mancanti,
             f"[{t.nome}] ogni immagine del foglio esiste davvero sul disco ({mancanti})")

    # -- i due loghi sono due **stati**, non due disegni -------------------
    for taglia in (64, 256):
        for rotto in (False, True):
            p = tema.logo(rotto=rotto, taglia=taglia)
            c.ok(p.exists(), f"c'e' {p.name}")
    c.ok(tema.icona() is not None and tema.icona().exists(),
         "e c'e' l'icona multi-risoluzione per la barra delle applicazioni")

    try:
        from PIL import Image
    except Exception:
        return
    # **Registrati sullo stesso rettangolo.** Scambiando il sereno con
    # l'arrabbiato — che e' precisamente quello che la finestra fa quando la
    # catena cade — il riquadro non deve spostarsi: due loghi ritagliati stretti
    # ciascuno sul suo contenuto **saltano**, e un logo che saltella chiede
    # attenzione mentre l'utente sta giocando.
    for taglia in (64, 256):
        sereno = Image.open(tema.logo(taglia=taglia)).convert("RGBA")
        guasto = Image.open(tema.logo(rotto=True, taglia=taglia)).convert("RGBA")
        c.eq(sereno.size, guasto.size, f"a {taglia} px i due loghi hanno la stessa tela")
        # Il riquadro del corpo e' la parte **opaca**: l'onda ha un alone che
        # sfuma, e confrontare i pixel non trasparenti confonderebbe il bagliore
        # col disegno.
        corpi = []
        for img in (sereno, guasto):
            alfa = img.getchannel("A").point(lambda v: 255 if v > 200 else 0)
            corpi.append(alfa.getbbox())
        scarto = max(abs(a - b) for a, b in zip(*corpi))
        c.ok(scarto <= max(2, taglia // 16),
             f"a {taglia} px il riquadro non si sposta al cambio di faccia "
             f"(scarto {scarto} px: {corpi[0]} contro {corpi[1]})")

    # **L'onda e' l'unica cosa che sfonda la sagoma.** A 64 px il riquadro con
    # dentro gli occhi e' un rettangolo qualunque; il rettangolo **con l'onda che
    # esce a destra** e' livedub. Un ritocco che la riportasse dentro perde il
    # logo, e lo perde **solo alle taglie piccole** — cioe' non si vede guardando
    # il file grande, che e' l'unico modo in cui si guarda un logo mentre lo si
    # disegna.
    # **E si misura sull'asse giusto.** La prima stesura di questa verifica
    # cercava l'onda a destra del riquadro e trovava 63 contro 63, cioe' la
    # tela: l'onda esce dalla bocca e scende **in basso** a destra, quindi la
    # domanda e' quanto sotto il fondo del corpo arriva. Una misura che non puo'
    # esprimere la risposta risponde comunque, e la risposta e' «no».
    piccolo = Image.open(tema.logo(taglia=64)).convert("RGBA")
    largo, alto = piccolo.size
    alfa = piccolo.getchannel("A").point(lambda v: 255 if v > 200 else 0)
    # Una striscia a sinistra vede **solo il corpo**: li' il fondo del riquadro
    # e' il fondo del personaggio. A destra c'e' anche l'onda.
    fondo_corpo = alfa.crop((largo // 6, 0, largo // 3, alto)).getbbox()[3]
    fondo_onda = alfa.crop((2 * largo // 3, 0, largo, alto)).getbbox()[3]
    c.ok(fondo_onda > fondo_corpo + 2,
         f"a 64 px l'onda sfonda la sagoma ({fondo_onda} contro {fondo_corpo}): "
         f"a quella taglia il riquadro con gli occhi e' un rettangolo qualunque, "
         f"e l'onda che esce e' l'unica cosa che lo rende livedub")


def test_regole_finestra(c) -> None:
    """Le regole della finestra che **non hanno bisogno della finestra**.

    Sono le due che nel documento hanno il ⚠: rotte non danno errore. La marca
    di gravita' sbagliata fa uscire un consiglio e la fine della sessione
    identici in mezzo a righe che scorrono; una soglia sbagliata nella barra
    della misura fa passare per normale un OCR a 12 Hz — cioe' toglie
    esattamente l'informazione per cui quella barra esiste.
    """
    from core.motore import (
        COMPRESSIONE_MASSIMA,
        LATENZA_MASSIMA_MS,
        OCR_MINIMO_HZ,
        barra_misura,
        gravita,
    )

    c.group("menta")

    # -- avviso e guasto non possono vedersi uguali ------------------------
    # I due esempi del documento, che cominciano tutti e due con «!».
    c.eq(gravita("! l'area e' alta 0,180 dello schermo"), "avviso",
         "un consiglio e' un avviso: marca ambra, e la sessione continua")
    c.eq(gravita("! l'audio si e' fermato: OSError"), "guasto",
         "la fine della sessione e' un guasto: marca rossa")
    c.eq(gravita("carico piper..."), "",
         "una nota non ha marca, e il testo resta allineato lo stesso")
    c.eq(gravita("! avvio fallito: OSError: device sparito"), "guasto",
         "anche l'avvio fallito, che chiude la sessione prima di aprirla")
    c.eq(gravita("audio interrotto"), "guasto",
         "e senza punto esclamativo, come per il colore della pillola: era la "
         "forma esatta con cui «audio interrotto» usciva verde")
    # **Il caso nullo del canale**: la gravita' non dice mai un colore di testo.
    # Se un giorno tornasse a dirlo, brucerebbe il canale delle voci.
    c.ok(set(gravita(x) for x in ("a", "! b", "guasto")) <= {"", "avviso", "guasto"},
         "la gravita' dice una marca, non un colore: le tinte del testo sono "
         "delle sei voci e di nessun altro")

    # -- la barra della misura ---------------------------------------------
    buono = {"stato": "in corso", "viva": True, "ocr_hz": 19.9, "battute": 34,
             "latenza_ms": 1150.0, "compressione": 1.23, "underrun": 0,
             "roi": (0.204, 0.884, 0.592, 0.070)}
    righe = barra_misura(buono)
    stati = {m.nome: m.stato for m in righe}
    c.ok(all(s == "" for s in stati.values()),
         f"una sessione che va non accende niente ({stati})")
    c.ok(any(m.nome == "ROI" for m in righe), "e la ROI c'e' sempre, per esteso")
    c.eq([m.testo for m in righe if m.nome == "latenza p50"], ["1150 ms"],
         "i millisecondi si scrivono interi: la seconda cifra non la guarda nessuno")

    lento = dict(buono, ocr_hz=OCR_MINIMO_HZ - 3)
    c.eq([m.stato for m in barra_misura(lento) if m.nome == "OCR"], ["avviso"],
         f"sotto {OCR_MINIMO_HZ:.0f} Hz l'OCR passa in ambra: e' la differenza fra "
         f"accorgersene adesso e leggerlo mezz'ora dopo in un file")
    # Ma a catena spenta 0 Hz e' **la verita'**, non un allarme: un ambra fisso
    # su una finestra appena aperta e' un ambra che nessuno guardera' piu'.
    c.eq([m.stato for m in barra_misura({"stato": "fermo", "viva": False}) if m.nome == "OCR"],
         [""], "ma a catena ferma non e' un avviso, e' semplicemente zero")

    stretto = dict(buono, compressione=COMPRESSIONE_MASSIMA + 0.15)
    c.eq([m.stato for m in barra_misura(stretto) if m.nome == "compress."], ["avviso"],
         f"oltre {COMPRESSIONE_MASSIMA} le consonanti spariscono, e si vede prima di sentirlo")
    tardi = dict(buono, latenza_ms=LATENZA_MASSIMA_MS + 500)
    c.eq([m.stato for m in barra_misura(tardi) if m.nome == "latenza p50"], ["avviso"],
         "e la latenza oltre la soglia dichiarata prima della prova")

    # L'unico che passa in **rosso**: un underrun non e' un numero fuori norma,
    # e' una battuta che non si e' sentita.
    secchi = dict(buono, underrun=3)
    c.eq([m.stato for m in barra_misura(secchi) if m.nome == "underrun"], ["guasto"],
         "un solo underrun e' rosso: e' un buco nell'audio, non una statistica")
    c.eq([m.stato for m in barra_misura(buono) if m.nome == "underrun"], [""],
         "e zero underrun non e' un allarme")

    # -- e non si accorcia mai ---------------------------------------------
    # Il disegno prevedeva che sotto i 720 px di altezza restassero tre valori.
    # Provato a schermo era un difetto: rimpicciolendo la finestra i numeri
    # sparivano uno dopo l'altro senza che niente dicesse perche', e i primi ad
    # andarsene — OCR, compressione, underrun — sono esattamente quelli che si
    # guardano quando qualcosa non va.
    c.eq([m.nome for m in barra_misura({"stato": "fermo"})],
         ["", "OCR", "battute", "latenza p50", "compress.", "underrun"],
         "senza ROI in config restano i cinque valori piu' lo stato…")
    c.eq(len(barra_misura(buono)), 7, "…e con la ROI sono sette, sempre")


def test_finestra_menta(c) -> None:
    """La finestra montata davvero, e le tre cose che a schermo non si notano.

    Gira offscreen: qui non si guarda come viene — quello lo dice uno screenshot
    — si guarda che le **regole arrivino ai widget**. Sono i punti in cui una
    riga giusta e una sbagliata si vedono uguali.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from core import preferenze
    from ui import qt_tema as tema

    c.group("menta")
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")

    import tools.ui_qt as U

    class FintiArgs:
        profile = None; loopback = "voicemeeter"; output = None; block = 480
        backend = "auto"; monitor = 1; tts = None; no_save = True; avvia = False
        overlay_catturabile = False; overrides = None

    cfg, _ = preferenze.riprendi(None, None)
    f = U.Finestra(cfg, FintiArgs())
    # **Mostrata davvero**, se no `resizeEvent` non arriva mai e i punti di
    # rottura si proverebbero contro una finestra che non e' mai stata
    # ridimensionata: una verifica che non puo' fallire. Offscreen non compare
    # niente a schermo.
    f.show()
    app.processEvents()
    try:
        # -- le schede si raggiungono per nome, non per numero --------------
        # `setCurrentIndex(3)` scritto a mano si scolla alla prima scheda
        # aggiunta in mezzo — **in silenzio**, portando l'utente altrove. E' gia'
        # successo con `p_tecnologie`, che non esisteva piu' e diventava «niente
        # da fare» invece che un errore.
        nomi = [f.schede.tabText(i) for i in range(f.schede.count())]
        c.eq(len(nomi), 6, f"sei schede: {nomi}")
        c.eq(nomi[f.TUTTE], "Tutte le impostazioni", "TUTTE punta all'albero intero")
        c.eq(nomi[f.SESSIONE], "Sessione", "SESSIONE punta al log")
        c.eq(nomi[f.AREE_], "Aree", "AREE_ punta alle zone da leggere")
        c.eq(nomi[f.PREPARAZIONE], "Preparazione", "PREPARAZIONE al primo passo")
        f._vai_a_cerca()
        c.eq(f.schede.currentIndex(), f.TUTTE, "Ctrl+F porta dove c'e' la ricerca")

        # -- i tre passi dicono quello che hai fatto **tu** -------------------
        # Il secondo si spuntava da solo perche' il profilo porta gia' una ROI: la
        # finestra si apriva dicendo «l'area l'hai tirata» a chi non aveva toccato
        # niente, e il primo passo — quello vero da fare — restava sotto una
        # spunta. Un indicatore che dice «fatto» per una cosa non fatta toglie al
        # pannello l'unica informazione che deve dare.
        c.ok(not f._area_scelta, "appena aperta, l'area non e' stata scelta da nessuno")
        c.eq(f.passi._numeri[1].text(), "2",
             "quindi il secondo passo e' un numero, non una spunta, anche col "
             "profilo che porta gia' una ROI")
        f._applica_roi((0.2, 0.88, 0.6, 0.07))
        c.ok(f._area_scelta, "tirandola, il passo si spunta")
        c.eq(f.passi._numeri[1].text(), "✓", "e si vede")

        # -- il logo cambia sulla **stessa** regola del colore ---------------
        f.stato("fermo")
        c.eq(f._colore_stato, f.tavolozza.testo_fioco, "a riposo la spia e' grigia")
        sereno = f.tessera_logo.accessibleDescription()
        f.stato(U.STATO_GUASTO)
        c.eq(f._colore_stato, f.tavolozza.rosso, "«! audio interrotto» accende il rosso")
        c.ok(f.tessera_logo.accessibleDescription() != sereno,
             "e il personaggio cambia faccia sulla stessa condizione, non su un "
             "elenco di stati scritto in testata")
        f.stato("in corso  |  120 frame")
        c.eq(f._colore_stato, f.tavolozza.accento, "una sessione viva prende la menta")
        c.eq(f.tessera_logo.accessibleDescription(), sereno,
             "e il personaggio torna sereno")

        # -- il tema cambia sotto i piedi, e il colore congelato va tradotto --
        # `rosso` e' `#ff6b5e` sullo scuro e `#cc372c` sul chiaro: e' il punto in
        # cui una condizione scritta su una stringa di colore vecchia smette di
        # funzionare **senza dare errore**, e con lei il logo.
        f.stato(U.STATO_GUASTO)
        vecchia = f.tavolozza
        altra = tema.CHIARA if vecchia.nome == "scuro" else tema.SCURA
        vero_attuale = tema.attuale
        try:
            tema.attuale = lambda _a: altra
            f._tema_cambiato()
        finally:
            tema.attuale = vero_attuale
        c.eq(f.tavolozza.nome, altra.nome, "il tema di sistema arriva alla finestra")
        c.eq(f._colore_stato, altra.rosso,
             "e il rosso congelato diventa il rosso **della tavolozza nuova**")

        # -- le marche di gravita' nel log ----------------------------------
        # Il testo resta del colore del testo: il canale del colore appartiene
        # alle voci, e colorare di rosso una riga di errore lo brucia.
        f.log.clear()
        f.scrivi("carico piper...")
        f.scrivi("! l'area e' alta 0,180 dello schermo")
        f.scrivi("! l'audio si e' fermato: OSError")
        html_log = f.log.document().toHtml().lower()
        c.ok(f.tavolozza.ambra.lower() in html_log, "l'avviso ha la sua marca ambra")
        c.ok(f.tavolozza.rosso.lower() in html_log, "il guasto ha la sua marca rossa")
        c.eq(f.log.toPlainText().count("▌"), 2,
             "due marche su tre righe: la nota non ne ha, e il testo resta allineato")
        c.ok(all(v.lower() not in html_log for v in f.tavolozza.voci),
             "e nessuna riga di sistema usa i colori dei personaggi")
        f._scrivi_voce("M1", "Lamar, che cazzo fai?")
        c.ok(f.tavolozza.voci[0].lower() in f.log.document().toHtml().lower(),
             "una battuta invece si', ed e' l'unica cosa colorata nel testo")

        # -- **al minimo della finestra non sfora niente** -------------------
        # Le tre schede di parametri sforavano in larghezza: la riga aveva un
        # minimo di 248 + 300 fissi piu' i marchi piu' una spiegazione di
        # centoventi caratteri, cioe' piu' della finestra. Il minimo di un widget
        # non si vede guardando: si vede quando la finestra si rifiuta di
        # stringersi, ed e' proprio quello che si chiede qui.
        f.resize(tema.MIN_LARGO, tema.MIN_ALTO)
        app.processEvents()
        for i in range(f.schede.count()):
            f.schede.setCurrentIndex(i)
            app.processEvents()
            pagina = f.schede.widget(i)
            largo = pagina.minimumSizeHint().width()
            c.ok(largo <= tema.MIN_LARGO,
                 f"la scheda «{f.schede.tabText(i)}» sta nel minimo della finestra "
                 f"({largo} <= {tema.MIN_LARGO})")
        c.ok(f.minimumSizeHint().width() <= tema.MIN_LARGO,
             f"e cosi' la finestra intera ({f.minimumSizeHint().width()})")

        # -- **e non sfora in nessuna lingua**, con la misura giusta ---------
        # «Alle Einstellungen» e' piu' lungo di «Tutte le impostazioni», e una
        # riga che sfora non si vede guardando: si vede quando la finestra si
        # rifiuta di stringersi. Applicare i quarantadue cataloghi e rifare
        # questa stessa misura era la strada ovvia, ed **e' sbagliata qui**: la
        # piattaforma offscreen non ha caratteri installati e il suo carattere
        # di ripiego e' molto piu' largo di quello vero. Provato: trentuno
        # lingue su quarantadue «sforavano» — tedesco 1353 px, tamil 1470 —
        # mentre con il carattere vero (`tools/traduci_ui.py --misura`) la piu'
        # larga e' il tamil a **934** su 960 e nessuna sfora. Una misura che
        # dichiara rotto cio' che funziona non e' prudente, e' inservibile: si
        # smette di guardarla.
        #
        # Quindi il pixel lo misura lo strumento, con la finestra vera e il
        # carattere vero, e va rilanciato quando si aggiunge una lingua. Qui
        # resta la parte che **questa** misura puo' esprimere: quanto cresce il
        # testo, in caratteri, che non dipende da nessun carattere tipografico.
        # Si veda `test_ui_lingua`.
        from ui import lingua as L

        L.applica(f, "it")
        app.processEvents()
        c.eq(f.schede.tabText(f.TUTTE), "Tutte le impostazioni",
             "e i cataloghi non lasciano la finestra in un'altra lingua")

        # -- lo stato sta in **un posto solo** -------------------------------
        # Era in testata (pillola), in fondo (barra della misura) e nella faccia
        # del logo: tre modi di dire una cosa in due angoli opposti della
        # finestra. Adesso il testo lo tiene la finestra e lo mostra chi lo mostra.
        c.ok(not hasattr(f, "pillola"), "la pillola in testata non c'e' piu'")
        c.ok(not hasattr(f, "l_roi"), "e nemmeno la ROI scritta due volte")
        f.stato("in corso")
        c.eq(f._stato_testo, "in corso", "il testo dello stato lo tiene la finestra")
        c.ok("in corso" in f.misura.testo.text(), "e la barra in fondo lo scrive")
    finally:
        f.close()
