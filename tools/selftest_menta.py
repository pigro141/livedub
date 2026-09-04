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

    # -- i quattro stati di una riga d'elenco ------------------------------
    # **Il difetto che ha fatto scrivere questa verifica si vedeva solo tenendo
    # il mouse fermo sulla riga gia' scelta.** Due regole di pari specificita' —
    # `::item:selected` e `::item:hover` — e Qt tiene l'ultima: il fondo tornava
    # grigio e il testo restava `su_accento`, che e' fatto per stare sulla menta.
    # Misurato: **1,12:1** sul tema scuro. Sul chiaro faceva 14,1 e non si
    # vedeva niente, che e' il modo in cui in questo progetto si archiviano
    # difetti — e infatti li' il difetto c'era lo stesso, solo di un altro tipo:
    # la riga scelta smetteva di sembrare scelta.
    for t in (tema.SCURA, tema.CHIARA):
        stati = tema.stati_elenco(t)
        c.eq(len(stati), 4, f"[{t.nome}] quattro stati di riga, dichiarati in tabella")
        for nome, (fondo, testo) in stati.items():
            r = tema.contrasto(testo, fondo)
            c.ok(r >= tema.CONTRASTO_TESTO,
                 f"[{t.nome}] una riga «{nome}» si legge ({r:.2f}:1 su {fondo}), "
                 f"soglia {tema.CONTRASTO_TESTO}")
        # **E la riga scelta resta scelta anche sotto il mouse.** Il contrasto da
        # solo non lo direbbe: il fondo grigio dell'hover col testo normale
        # sarebbe leggibilissimo e avrebbe perso l'unica cosa che quella riga
        # doveva dire. Quindi si chiede che i due stati «scelta» non condividano
        # il fondo con i due stati «non scelta».
        scelti = {stati["scelta"][0], stati["scelta sotto il mouse"][0]}
        altri = {stati["normale"][0], stati["sotto il mouse"][0]}
        c.ok(not (scelti & altri),
             f"[{t.nome}] passandoci sopra, la riga scelta non prende il fondo di "
             f"una riga qualunque ({sorted(scelti)} contro {sorted(altri)})")
        # E fa un passo **lontano dal fondo della pagina**, nella stessa
        # direzione nei due temi: sullo scuro schiarisce, sul chiaro scurisce.
        piu_lontano = tema.contrasto(stati["scelta sotto il mouse"][0], t.superficie)
        c.ok(piu_lontano > tema.contrasto(stati["scelta"][0], t.superficie),
             f"[{t.nome}] e stacca di piu' dalla pagina ({piu_lontano:.2f}:1)")
        # La regola a due pseudo-stati **deve esserci scritta**: senza, Qt torna
        # a risolvere per ordine ed e' esattamente il difetto di partenza.
        c.ok("QListWidget::item:selected:hover" in tema.foglio(t),
             f"[{t.nome}] il foglio dichiara `::item:selected:hover`, che ha due "
             f"pseudo-stati e quindi batte le altre due regole invece di "
             f"dipendere dall'ordine in cui sono scritte")

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
            c.ok(r >= tema.CONTRASTO_TESTO,
                 f"[{t.nome}] la voce {v} si legge sul log ({r:.1f}:1)")
    # **Le voci sono tarate su `superficie` e su nient'altro**, e adesso non
    # vivono piu' nel solo log: la sigla del personaggio sta anche nella tessera
    # della battuta di adesso e nella fila dei personaggi. Quelle due tessere
    # stanno su `superficie` per questo motivo e non per gusto — su
    # `superficie_alta`, che sarebbe la scelta ovvia per staccarle, sul tema
    # chiaro le voci scendono a 4,28:1. Un fondo piu' bello che costa l'unica
    # informazione che quella tessera porta.
    peggio = min(tema.contrasto(v, tema.CHIARA.superficie_alta) for v in tema.CHIARA.voci)
    c.ok(peggio < tema.CONTRASTO_TESTO,
         f"e su `superficie_alta` non ci starebbero ({peggio:.2f}:1): e' la misura "
         f"per cui le tessere della scheda Sessione stanno su `superficie`")
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

    # -- la fase: **una parola sola**, e solo quelle che si misurano ---------
    from core.motore import FASI, fase_catena

    c.eq(fase_catena({"viva": False}).testo, "fermo",
         "a catena spenta si dice fermo, non si tace")
    c.eq(fase_catena(dict(buono, parla=True)).testo, "sta parlando",
         "che stia parlando batte tutto: e' l'unico momento in cui il programma "
         "sta facendo il suo mestiere")
    tardi = dict(buono, latenza_ms=LATENZA_MASSIMA_MS + 500)
    c.eq(fase_catena(tardi).testo, "in ritardo",
         "oltre la soglia dichiarata prima della prova di Qwen, si dice")
    c.eq(fase_catena(tardi).stato, "avviso",
         "ed e' un avviso, cioe' ambra: la catena gira lo stesso")
    c.eq(fase_catena(dict(tardi, parla=True)).testo, "sta parlando",
         "ma mentre esce audio si dice quello: il ritardo lo dice la barra in fondo")
    c.eq(fase_catena(buono).testo, "sta leggendo",
         "e per il resto sta leggendo lo schermo")
    # **Quattro e non cinque.** «Sintetizza» sarebbe la parola che tutti si
    # aspettano, e non c'e' modo di misurarla da qui: la sintesi accade dentro
    # `on_frame`, cioe' nel thread video, e il thread della finestra quella
    # finestra di tempo non la vede mai. Una parola che indovina in una riga che
    # si guarda di sfuggita e' peggio di una parola in meno.
    c.eq(len(FASI), 4, f"quattro fasi, tutte misurabili: {FASI}")
    detti = {fase_catena(d).testo for d in (
        {"viva": False}, buono, tardi, dict(buono, parla=True))}
    c.eq(sorted(detti), sorted(FASI),
         "e `FASI` elenca esattamente quelle che la regola sa dire, se no sarebbe "
         "un elenco che si scolla dalla funzione in silenzio")

    # **E le quattro parole hanno un catalogo.** Nessuna passeggiata sui widget
    # puo' vedere le tre che in quell'istante non sono a schermo: senza questa
    # riga tre su quattro resterebbero in italiano dentro una finestra tradotta,
    # e resterebbero in italiano **a turno**.
    from ui.lingua import COMPOSTE

    c.eq(sorted(set(FASI) - set(COMPOSTE)), [],
         "ogni fase sta in `COMPOSTE`, cioe' viene tradotta dalla finestra")

    # -- il velo del cambio di lingua, che e' una regola e non un disegno ---
    c.eq(tema.durata_carico(True), 0,
         "a sessione accesa non c'e' velo: i due thread della catena non pagano "
         "un'animazione")
    c.ok(tema.durata_carico(False) in (0, tema.MS_CARICO),
         "e a catena ferma dura mezzo `MS_CARICO` per parte — o zero, se il "
         "sistema chiede meno movimento")
    c.ok(2 * tema.MS_CARICO <= 300,
         f"il velo intero sta nei tre decimi dichiarati ({2 * tema.MS_CARICO} ms): "
         f"piu' lungo si aspetterebbe, e coprire 35 ms di lavoro con mezzo "
         f"secondo di animazione e' un'attesa inventata")


def test_finestra_menta(c) -> None:
    """La finestra montata davvero, e le tre cose che a schermo non si notano.

    Gira offscreen: qui non si guarda come viene — quello lo dice uno screenshot
    — si guarda che le **regole arrivino ai widget**. Sono i punti in cui una
    riga giusta e una sbagliata si vedono uguali.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from core import preferenze
    from ui import qt_tema as tema

    c.group("menta")
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")

    from core import registro

    # **Prima di costruire la finestra**, se no il registro si apre su quello
    # dell'utente e ci restano le righe di questo gruppo — 64 volte, contate.
    registro.banco()

    import tools.ui_qt as U

    class FintiArgs:
        profile = None; loopback = "voicemeeter"; output = None; block = 480
        backend = "auto"; monitor = 1; tts = None; no_save = True; avvia = False
        overlay_catturabile = False; overrides = None

    cfg, _ = preferenze.riprendi(None, None)
    # **La lingua si fissa, se no questo gruppo misura una finestra diversa su
    # ogni macchina.** `ui.lingua` sta su `auto`: su una Windows inglese la
    # finestra nasce in inglese e sette verifiche di qui sotto — che confrontano
    # stringhe italiane — cadono senza che niente sia rotto. E' successo su un
    # runner. Le lingue si provano tutte poco piu' avanti, apposta.
    cfg.ui.lingua = "it"
    f = U.Finestra(cfg, FintiArgs())
    # **Mostrata davvero**, se no `resizeEvent` non arriva mai e i punti di
    # rottura si proverebbero contro una finestra che non e' mai stata
    # ridimensionata: una verifica che non puo' fallire. Offscreen non compare
    # niente a schermo.
    #
    # **Ma dichiarata «non a schermo»**, che e' un'altra cosa e non e' pleonastica:
    # una finestra puo' aprire un dialogo modale mentre nasce, e `exec()` dentro
    # una suite non torna **mai**. E' successo — la suite restava ferma senza una
    # riga, cioe' il peggior modo possibile di fallire — ed e' la stessa guardia
    # che usano `tools/scatta.py` e `tools/traduci_ui.py`, che questa finestra la
    # costruiscono senza mostrarla. Gli eventi di taglia arrivano lo stesso: e'
    # esattamente per questo che quei due strumenti funzionano.
    f.setAttribute(Qt.WA_DontShowOnScreen, True)
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
        c.eq(nomi[f.PREPARAZIONE], "Preparazione", "PREPARAZIONE al primo passo")
        c.eq(nomi[f.VOLUMI_], "Volumi", "VOLUMI_ alla scheda dei volumi")

        # **E la guida racconta le schede che ci sono davvero.** `tutorial.SCHEDE`
        # e' un elenco scritto a mano di nome + due righe, e si e' scollato in
        # silenzio: diceva «le sei schede» in testata elencandone cinque, e
        # spiegava che il volume sta dentro «Voce» quando non ci stava piu'. Chi
        # legge la guida la legge una volta, la prima, e va dove gli si dice.
        from ui.tutorial import SCHEDE

        c.eq([n for n, _ in SCHEDE], nomi,
             "la guida elenca le stesse schede della finestra, nello stesso ordine")

        # **La scheda Volumi mostra tutti i `mix.` tranne i due dichiarati.**
        # Scritta come «l'elenco meno le eccezioni» e non come un elenco a mano:
        # un campo nuovo in `MixConfig` deve comparire li' o essere escluso
        # apposta, non sparire perche' nessuno se n'e' ricordato.
        from core.schema import campi as _campi

        tutti_mix = {x.percorso for x in _campi(f.cfg) if x.sezione == "mix"}
        c.eq(sorted(tutti_mix - set(U.VOLUMI)),
             ["mix.output_device", "mix.prebuffer_ms"],
             "fuori dalla scheda restano solo il cuscino dello streaming (che coi "
             "tre motori di oggi non muove niente) e il dispositivo, che nessuno legge")
        c.eq(sorted(set(U.VOLUMI) - tutti_mix), [],
             "e non c'e' nessun percorso inventato nell'elenco")
        # E i volumi non stanno **anche** in Voce: due manopole per lo stesso
        # campo in due schede sono due viste che si possono contraddire.
        c.eq(sorted(set(U.VOCE) & set(U.VOLUMI)), [],
             "Voce e Volumi non condividono nessun campo")
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

        # -- i bottoni senza fondo della testata sono **tre**, e sono una fila --
        # Il cuore delle donazioni si e' aggiunto al `?` e alla ⓘ, e la fila
        # regge per una ragione sola: sono tutti e tre lo stesso oggetto
        # (`#aiuto`, un cerchio da 28 px senza fondo, colore menta) con dentro
        # un **glifo**. In `ui/tutorial.py` sta scritto da quando erano due che
        # un terzo con dentro una parola la romperebbe: qui lo si misura, invece
        # di ricordarselo. Un bottone con del testo dentro passerebbe
        # `_traducibile`, e a schermo sarebbe una pillola larga in mezzo a due
        # cerchi.
        from PySide6.QtWidgets import QPushButton, QWidget

        from ui import lingua as _lingua
        from ui import qt_dono as QD

        # **Solo quelli della testata.** `#aiuto` lo porta anche il `?` di ogni
        # riga di parametro — sono 223 in tutta la finestra — e contarli tutti
        # farebbe una verifica che non risponde alla domanda che si sta facendo.
        testata = f.findChild(QWidget, "testata")
        c.ok(testata is not None, "la testata si raggiunge per nome")
        tondi = [b for b in testata.findChildren(QPushButton)
                 if b.objectName() == "aiuto"]
        c.eq(len(tondi), 3, "tre bottoni senza fondo: la guida, le informazioni, il cuore")
        parlanti = sorted(b.text() for b in tondi if _lingua._traducibile(b.text()))
        c.eq(parlanti, [],
             "e dentro ognuno c'e' un glifo e non una parola: una parola li' "
             "romperebbe la fila, ed e' anche l'unica cosa che il catalogo "
             "tradurrebbe")
        c.ok(QD.GLIFO in [b.text() for b in tondi],
             "il cuore delle donazioni e' uno dei tre")
        c.ok(all(b.isVisible() for b in tondi),
             "e non se ne nasconde nessuno: la porta delle donazioni non dipende "
             "da quanto hai usato il programma — quello che dipende dai contatori "
             "e' il riquadro, che si apre una volta sola")

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
        #
        # **E queste tre righe non devono finire nel registro dell'utente.**
        # `Finestra.scrivi` scrive anche su file: prima di `registro.banco()` ce
        # ne sono finite 64 come la terza, indistinguibili da un guasto vero, e
        # sono costate una sessione d'indagine su un guasto mai esistito. Si
        # misura il **file vero** e non un modello di file, perche' la cosa da
        # provare e' proprio che quel file non cresca.
        import datetime as _dt

        from core import registro

        vero = registro.cartella_log() / registro.nome(_dt.date.today(), False)
        quanto_era = vero.stat().st_size if vero.exists() else -1
        f.log.clear()
        f.scrivi("carico piper...")
        f.scrivi("! l'area e' alta 0,180 dello schermo")
        f.scrivi("! l'audio si e' fermato: OSError")
        c.eq(vero.stat().st_size if vero.exists() else -1, quanto_era,
             "tre righe scritte dal banco, e il registro dell'utente non cresce "
             "di un byte")
        c.ok(registro.di_banco(),
             "perche' questo processo ha dichiarato di simulare")
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

        # -- **e non sfora in nessuna delle quarantadue lingue** ------------
        # Questa misura per un po' non e' stata fatta qui, e il motivo era buono:
        # la piattaforma offscreen non ha caratteri installati e il suo ripiego e'
        # molto piu' largo di quello vero, quindi dichiarava rotte trentuno lingue
        # su quarantadue (tedesco 1353, tamil 1470) mentre col carattere vero la
        # piu' larga stava a 872. Una misura che dichiara rotto cio' che funziona
        # non e' prudente, e' inservibile.
        #
        # **Adesso ci sta anche con quel carattere**, perche' la riga dei
        # conteggi e il bottone dei default hanno smesso di imporre la larghezza
        # del loro testo intero: il peggiore passa da 1366 a 728. Quindi il
        # ripiego largo torna utile — e' un limite piu' stretto del vero, e
        # passarlo con quaranta lingue e' una notizia migliore che passarlo con
        # una. Il pixel esatto lo dice comunque `tools/traduci_ui.py --misura`,
        # che costruisce la finestra col carattere vero.
        #
        # E l'inglese e' la lingua che questo gruppo **non poteva** misurare:
        # `ui.lingua` sta su `auto`, quindi si vede solo su una Windows inglese —
        # cioe' quasi solo su chi scarica il programma, e mai qui.
        from ui import lingua as L

        peggiore = ("it", 0)
        for codice in L.disponibili():
            L.applica(f, codice)
            app.processEvents()
            for i in range(f.schede.count()):
                f.schede.setCurrentIndex(i)
                app.processEvents()
                largo = f.schede.widget(i).minimumSizeHint().width()
                if largo > peggiore[1]:
                    peggiore = (codice, largo)
                if largo > tema.MIN_LARGO:
                    c.ok(False,
                         f"la scheda «{f.schede.tabText(i)}» in «{codice}» non "
                         f"sta nel minimo della finestra ({largo} > "
                         f"{tema.MIN_LARGO})")
        c.ok(peggiore[1] <= tema.MIN_LARGO,
             f"nessuna delle {len(L.disponibili())} lingue sfora il minimo della "
             f"finestra: la piu' larga e' «{peggiore[0]}» a {peggiore[1]} px su "
             f"{tema.MIN_LARGO}")
        c.ok(len(L.disponibili()) > 40,
             f"e sono {len(L.disponibili())}, non solo quella di questa macchina")

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

        # -- la scheda Sessione: **prima cosa che parla, poi il log** --------
        # Era un registro a tutta pagina. Il log resta, e resta intero, ma la
        # prima cosa che arriva all'occhio adesso e' la battuta di adesso.
        # La scheda va portata davanti: `isVisible()` di un widget su una pagina
        # non scelta e' **falso** anche quando il widget e' a posto, e una
        # verifica che lo ignora prova la linguetta invece del pannello.
        f.schede.setCurrentIndex(f.SESSIONE)
        app.processEvents()
        c.ok(not f._guscio_vivo.isVisible(),
             "a catena ferma la scheda Sessione mostra i tre passi e nient'altro")
        f._mostra_log()
        app.processEvents()
        c.ok(f._guscio_vivo.isVisible(), "e partendo compare il blocco vivo")
        c.ok(f.log.isVisible(), "col log dentro, che non si butta: e' il posto "
                                "dove si va a leggere quando qualcosa non va")
        c.ok(f.ora.vuota, "la tessera parte vuota, con un segnaposto e non un buco")
        c.ok(f.ora.testo.text(), "e il segnaposto e' scritto, non e' una riga vuota")

        # **Il colore del personaggio arriva dove deve, e come deve.** Le sei
        # tinte sono *colore del testo* e vivono nel log: portarle su una tessera
        # e' lecito solo finche' restano testo. Un riempimento — che sarebbe la
        # cosa piu' bella da guardare — userebbe per le voci il canale di menta,
        # ambra e rosso, e il log smetterebbe di rispondere alla sua unica
        # domanda **per gradi**, senza che niente dia errore.
        f._conta.clear()
        for sid, voce, testo in (("M1", "it_riccardo", "Lamar, che fai?"),
                                 ("M2", "it_paola", "Niente, fratello."),
                                 ("M1", "it_riccardo", "Non ci credo.")):
            f._conta[sid] = f._conta.get(sid, 0) + 1
            f.ora.dillo(sid, voce, testo, f._colore_voce(sid), 620.0, 1.12)
            f.personaggi.aggiorna(f._conta, f._colore_voce)
        app.processEvents()
        c.ok(not f.ora.vuota, "detta una battuta, la tessera non e' piu' vuota")
        c.ok("Non ci credo." in f.ora.testo.toolTip(),
             "e porta l'ultima, per intero nel suggerimento anche se accorciata")
        c.ok(f._colore_voce("M1").lower() in f.ora.chi.text().lower(),
             "la sigla ha il colore del suo personaggio")
        c.ok("1.12" in f.ora.chi.text() and "620" in f.ora.chi.text(),
             "insieme a fretta e latenza di **quella** battuta, non ai percentili")
        c.eq(f._colore_voce("M1") == f._colore_voce("M2"), False,
             "due personaggi, due tinte, assegnate in un posto solo")
        c.eq(len(f.personaggi._tessere), 2, "e due tessere nella fila, in ordine "
                                            "di comparsa e non di conteggio")
        for _tessera, _quante, w in f.personaggi._tessere.values():
            foglio_sigla = w.styleSheet().lower()
            c.ok(any(v.lower() in foglio_sigla for v in f.tavolozza.voci),
                 "la tessera del personaggio porta la sua tinta…")
            c.ok("background" not in foglio_sigla,
                 "…e **solo come colore del testo**: un riempimento colorato li' "
                 "romperebbe la regola dei canali, e la romperebbe in silenzio")
        c.ok(all(v.lower() not in tema.foglio(f.tavolozza).lower()
                 for v in f.tavolozza.voci),
             "e infatti nessuna delle sei entra nel foglio di stile, nemmeno ora "
             "che le voci hanno lasciato il log")

        # -- il velo: c'e', sta zitto, e non allarga la finestra -------------
        # Sta **fuori dai layout** apposta: dentro imporrebbe una taglia minima a
        # tutto quello che copre, cioe' cambierebbe il minimo della finestra —
        # una cosa che non si vede guardando e che si scopre quando la finestra
        # si rifiuta di stringersi.
        c.ok(not f.velo.isVisible(), "il velo a riposo non c'e'")
        prima = f.minimumSizeHint().width()
        f.velo.copri(0, lambda: None)
        c.eq(f.minimumSizeHint().width(), prima,
             f"e non tocca il minimo della finestra ({prima})")
        # `copri` con durata zero — sistema che chiede meno movimento, o sessione
        # accesa — **fa il lavoro lo stesso**: un velo spento non deve voler dire
        # una lingua che non cambia. E' la meta' che si dimentica.
        fatto = []
        f.velo.copri(0, lambda: fatto.append(True))
        c.eq(fatto, [True], "e senza animazione il lavoro si fa comunque")

        # -- **le tendine: si vede tutto finche' sono corte** ----------------
        # Con un foglio di stile addosso Qt apre la tendina come un *menu*:
        # mostra tutte le voci — quarantatre lingue fanno 1093 px — e ignora
        # `setMaxVisibleItems`, ma solo per quelle non scrivibili. Cosi'
        # `translate.target` si fermava a sedici e `ui.lingua` no: due
        # comportamenti diversi per caso e non per regola. La riga che lo
        # riporta a una regola sola sta nel foglio, e qui si controlla che ci
        # sia — senza, il numero qui sotto non lo guarda nessuno.
        from PySide6.QtWidgets import QComboBox

        foglio = tema.foglio(f.tavolozza)
        c.ok("combobox-popup: 0" in foglio,
             "il foglio dichiara `combobox-popup: 0`, se no `VOCI_TENDINA` e' "
             "un numero scritto e mai letto")

        tendine = [w for w in f.findChildren(QComboBox) if w.count()]
        c.ok(len(tendine) >= 30, f"le tendine della finestra sono {len(tendine)}")
        senza = [w.accessibleName() or w.objectName() or "(senza nome)"
                 for w in tendine if w.maxVisibleItems() != tema.VOCI_TENDINA]
        c.eq(senza, [], "e tutte passano da `allarga_tendina`: una tendina nuova "
                        "che se ne dimentica si apre con il numero di serie di Qt")

        # **La soglia sta in mezzo a un altopiano, e questa e' la prova.**
        # Spostandola di quattro in su o in giu' l'elenco delle tendine che
        # scorrono non cambia di una: fra le sette voci di `label.form` e le
        # quarantatre di `ui.lingua` non c'e' niente. Se un giorno nascesse un
        # menu da quindici voci questa verifica diventerebbe rossa — ed e'
        # esattamente il momento in cui il numero andrebbe riscelto.
        conteggi = sorted(w.count() for w in tendine)

        def _scorrono(soglia):
            return [n for n in conteggi if n > soglia]

        c.eq(_scorrono(tema.VOCI_TENDINA - 4), _scorrono(tema.VOCI_TENDINA + 4),
             f"a {tema.VOCI_TENDINA} ± 4 scorrono le stesse tendine: la soglia "
             f"non sta sull'orlo (voci: {sorted(set(conteggi))})")
        # E il tetto: una riga misura 25 px e la cornice 18, quindi la tendina
        # aperta non deve superare la finestra piu' piccola che si puo' avere.
        c.ok(tema.VOCI_TENDINA * 25 + 18 <= tema.MIN_ALTO,
             f"aperta e' alta {tema.VOCI_TENDINA * 25 + 18} px, dentro i "
             f"{tema.MIN_ALTO} della finestra minima")
    finally:
        f.close()
