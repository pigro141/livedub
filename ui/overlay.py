"""Il sottotitolo tradotto, disegnato **sopra il gioco**.

La sostituzione grafica esisteva solo per l'MP4 (`tools/dub.py`), dove ffmpeg
disegna sul fotogramma. Dal vivo il fotogramma non passa da noi: il gioco lo
manda direttamente allo schermo. L'unico modo di coprirlo e' **una finestra
sopra**, senza bordi, sempre in primo piano, piazzata sul sottotitolo.

## La cosa che veniva prima di tutte, e che non era stata vista

**La nostra finestra sta sullo schermo, e lo schermo e' cio' che catturiamo.**
La catena prende un fotogramma a 30 Hz per darlo all'OCR: dentro quel fotogramma
c'era anche l'overlay. Misurato — non supposto — mettendo a schermo una finestra
verde e guardando i pixel catturati: **il 100%** dei suoi pixel finiva nella
cattura, con `mss` e con `dxcam`. Da li' l'OCR non leggeva piu' il sottotitolo del
gioco: leggeva noi, e le righe sparivano.

Il rimedio e' una riga di Windows: `WDA_EXCLUDEFROMCAPTURE`. La finestra resta
sul monitor e sparisce da qualunque cattura — e' la stessa funzione con cui le
applicazioni nascondono le password dalla condivisione schermo. Verificato dopo:
**0%**. Non e' un'ottimizzazione, e' la condizione perche' il resto funzioni.

## Un rettangolo, sfocato, con sopra il testo

La forma finale e' la piu' semplice, ed e' quella che l'utente ha proposto dopo
aver visto fallire le altre: si prende il **rettangolo che circoscrive il
sottotitolo** letto dall'OCR, lo si sfoca sui pixel di **questo** fotogramma, e
ci si scrive sopra la traduzione.

Le due strade tentate prima sono un promemoria di cosa costa complicare. La
prima sfocava tutta la ROI: una fascia larga mezzo schermo per coprire una riga.
La seconda cancellava riga per riga ricostruendo lo sfondo con la morfologia, e
inseguiva l'inchiostro fotogramma per fotogramma per restare aggiornata: da li'
venivano toppe accanto al testo, macchie sull'asfalto, e righe cancellate che
non erano righe — perche' su una scena luminosa dell'inchiostro si trova sempre.

**Geometria ferma, pixel vivi.** Il rettangolo si calcola una volta alla
comparsa e non si muove piu' (se no il sottotitolo balla); la sfocatura dentro
si rifa' a ogni giro sul fotogramma corrente (se no e' una toppa di immagine
vecchia incollata su una scena che si muove).

**E sparisce quando sparisce l'originale**, che e' cosa sa il lettore di
sottotitoli e non i pixel: `DubPipeline.a_schermo(t_on)`. Chiedendolo
all'inchiostro, la stessa frase inglese e' rimasta a schermo **diciotto
secondi** mentre il gioco era gia' a tre battute dopo.

## E il testo copia quello del gioco

Il carattere non e' una scelta di gusto: **misura e colore si prendono dal
sottotitolo che si sta coprendo**. L'altezza della banda dice quanto e' grande il
carattere del gioco, il colore medio dell'inchiostro dice di che colore e'. Cosi'
la battuta tradotta si posa dove stava quella originale, della stessa taglia e
dello stesso colore, e sembra il sottotitolo del gioco invece di un cartello
appiccicato sopra. L'utente puo' sempre forzare `translate.font_frac` e
`translate.color`; a zero e vuoto valgono "come il gioco".

## Un solo pittore per due usi

`dipingi()` e' puro: prende i pixel e torna un'immagine RGBA con la sua
posizione. La usa la finestra dal vivo **e** la usa `tools/overlay_mp4.py` per
montare un video di come verrebbe. Se fossero due disegnatori diversi, il video
mostrerebbe una cosa e il vivo un'altra — che e' esattamente com'e' nato il
difetto precedente, con ffmpeg che disegnava per l'MP4 e nessuno che avesse mai
guardato il vivo.
"""

from __future__ import annotations

import sys
from functools import lru_cache

# Il colore che Windows rende trasparente. Quasi nero, e non magenta: i pixel di
# bordo del testo sfumano verso di lui, e devono sfumare verso qualcosa che
# assomigli a un contorno.
CHIAVE = "#010203"
CHIAVE_RGB = (1, 2, 3)

# Da nome a file, per PIL. Il nome basta a Tk ma non a Pillow, che vuole un file.
FONT_FILE = {
    "arial": "arialbd.ttf",
    "verdana": "verdanab.ttf",
    "tahoma": "tahomabd.ttf",
    "segoe ui": "seguisb.ttf",
    "calibri": "calibrib.ttf",
    "impact": "impact.ttf",
}


@lru_cache(maxsize=64)
def carica_font(nome: str, corpo: int):
    """Il font di sistema alla misura chiesta, con un ripiego che non esplode.

    In cache perche' `corpo_del_gioco` ne apre fino a otto per battuta cercando
    la misura giusta, e questo gira **nel thread video**: li' un costo si
    amplifica invece di sommarsi, che e' la lezione piu' cara di questo progetto.
    """
    from PIL import ImageFont

    for candidato in (FONT_FILE.get((nome or "").lower().strip()), "arialbd.ttf", "arial.ttf"):
        if not candidato:
            continue
        try:
            return ImageFont.truetype(candidato, corpo)
        except OSError:
            continue
    return ImageFont.load_default()


def corpo_del_gioco(bande, testo_originale: str, scala: float, nome_font: str) -> int:
    """Quanto e' grande, in punti, il carattere che il gioco sta usando.

    **Si misura sulla larghezza, non sull'altezza, e la differenza e' un
    quarto.** Il primo tentativo confrontava l'altezza della banda con l'altezza
    dell'inchiostro di `Ag`: ma `Ag` occupa dall'ascendente al discendente,
    mentre una riga come `Ciao, Lamar!` non ha nessun discendente e la sua banda
    e' alta solo quanto le maiuscole. Confrontare le due voleva dire chiedere un
    carattere alto quanto una riga intera per ottenere delle sole maiuscole —
    circa il 40% troppo grande, che e' esattamente quello che si vedeva.

    La larghezza invece si confronta con se' stessa: si prende **il testo che
    l'OCR ha letto**, lo si disegna col carattere scelto e si cerca il corpo in
    cui occupa la stessa larghezza che occupa a schermo. Stesse lettere, stessa
    grandezza — nessuna conversione fra due misure diverse. In piu' funziona con
    un carattere di forma diversa da quello del gioco: GTA V ne usa uno stretto,
    e chiedere la stessa **altezza** ad Arial avrebbe dato una riga molto piu'
    larga dell'originale.

    Senza il testo (non dovrebbe capitare) si ricade sull'altezza, dichiarando
    il rapporto fra inchiostro maiuscolo e corpo invece di far finta che sia 1.
    """
    larghezza = sum(x1 - x0 for x0, _, x1, _ in bande) * scala
    # **La banda piu' bassa, non la piu' alta.** Da qui esce il tetto
    # sull'altezza dell'inchiostro (`sta_dentro`), che e' l'unica cosa che
    # impedisce a un compromesso mal posto di scegliere un carattere gonfio.
    # Prendendo il massimo, una banda che non e' testo alzava il tetto insieme a
    # se' stessa: la guardia si allargava proprio nel caso per cui esiste.
    # Su righe vere le due misure coincidono — le righe di una battuta sono alte
    # uguale — quindi la scelta si vede solo quando c'e' qualcosa da togliere.
    altezza = min(y1 - y0 for _, y0, _, y1 in bande) * scala
    testo = " ".join((testo_originale or "").split())
    if not testo or larghezza <= 0:
        import statistics

        alta = statistics.median(sorted(y1 - y0 for _, y0, _, y1 in bande)) * scala
        return max(8, int(round(alta / 0.72)))  # inchiostro maiuscolo / corpo

    from PIL import Image, ImageDraw

    misura = ImageDraw.Draw(Image.new("L", (1, 1)))

    def errore(corpo: int) -> float:
        """Quanto quel corpo sbaglia, **su tutti e due i lati**.

        La sola larghezza basterebbe se il carattere fosse quello del gioco, e
        non lo e': GTA V ne usa uno stretto, Arial no. Con la sola larghezza il
        testo viene giusto di lunghezza e **piu' alto** dell'originale; con la
        sola altezza viene giusto di altezza e molto piu' lungo. Si cerca quindi
        il corpo che sbaglia meno su entrambi, con l'altezza pesata la meta'
        perche' la larghezza e' misurata su una riga intera e l'altezza su un
        glifo — la prima e' la misura piu' affidabile delle due.
        """
        f = carica_font(nome_font, corpo)
        w = misura.textlength(testo, font=f)
        a, b, cx, d = f.getbbox("Ag")
        h = max(1, d - b)
        return abs(w - larghezza) / larghezza + 0.5 * abs(h - altezza) / max(1.0, altezza)

    # Si parte dalla stima sulla sola larghezza — poche iterazioni, converge —
    # e poi si cerca il minimo attorno, che e' dove i due lati si accordano.
    corpo = max(8, int(larghezza / max(1, len(testo)) * 2.0))
    for _ in range(10):
        w = misura.textlength(testo, font=carica_font(nome_font, corpo))
        if w <= 0:
            break
        if abs(w - larghezza) <= max(2.0, 0.01 * larghezza):
            break
        corpo = max(8, int(round(corpo * larghezza / w)))
    # **Un tetto duro sull'altezza, e non e' pignoleria.** Il compromesso e' un
    # minimo, e un minimo su una banda dalle proporzioni impossibili — dodici
    # lettere larghe 700 px e alte 30, cioe' non il testo che dice di essere —
    # puo' cadere su un carattere alto il triplo della riga che deve coprire. A
    # schermo si vede un sottotitolo gonfio, che e' il difetto da cui e' partito
    # tutto questo. Sopra la riga si puo' sconfinare di un filo, non di piu'.
    def sta_dentro(corpo: int) -> bool:
        a, b, cc, d = carica_font(nome_font, corpo).getbbox("Ag")
        return (d - b) <= altezza * 1.35

    candidati = [c for c in range(max(8, corpo - 8), corpo + 9) if sta_dentro(c)]
    if not candidati:
        candidati = [max(8, int(round(altezza / 0.72)))]
    return min(candidati, key=errore)


class MisuraCarattere:
    """Ricorda quanto e' grande il carattere del gioco. **Uno, sempre lo stesso.**

    Un gioco scrive i sottotitoli sempre della stessa taglia, quindi una taglia
    che cambia da una battuta all'altra e' rumore della misura, non un fatto — e
    a schermo si vede benissimo.

    Le fonti del rumore sono tre, tutte viste dal vivo:

    - la **dissolvenza** con cui il sottotitolo compare: a meta' sfumatura la
      maschera prende solo il cuore dei glifi;
    - l'OCR che legge **una parte** della riga (`RecupeSenti, amico`): pochi
      caratteri su molti pixel di inchiostro, e la stima esplode;
    - le battute su **due righe**, dove basta che il testo letto sia di una riga
      sola perche' il rapporto salti del doppio.

    Da qui due regole. La prima: si scartano le stime **incoerenti**, cioe'
    quelle troppo lontane da quanto si e' gia' visto. La seconda: dopo un po' di
    stime d'accordo fra loro **la taglia si blocca** e non si muove piu'. Un
    sottotitolo non cambia corpo a meta' partita, e continuare a rimisurarlo puo'
    solo peggiorare una risposta che si e' gia' avuta.
    """

    def __init__(self, quante: int = 25, bastano: int = 6) -> None:
        self.viste: list[int] = []
        self.quante = quante
        self.bastano = bastano
        self.corpo = 0
        self.bloccata = False
        # **Questo gioco centra i sottotitoli?** Si impara, non si decide su una
        # battuta sola. Una lettura parziale — `Recupe`, `that youTL` — e' stretta
        # e spostata, e centrandoci sopra la traduzione finisce decentrata; ma un
        # gioco che allinea a sinistra esiste, e ricentrare d'ufficio sarebbe
        # sbagliato per lui. Chi risponde e' la maggioranza delle battute viste.
        # **Dove sta l'asse dei sottotitoli**, in frazione della larghezza del
        # pezzo. Si impara dalle battute viste e non si prende dalla ROI: la ROI
        # la disegna l'utente col mouse e non e' centrata sul testo del gioco.
        # Misurato su un fotogramma vero: centrando sulla ROI il tradotto
        # finiva **72 pixel** a destra del sottotitolo (95 sullo schermo
        # dell'utente), sistematicamente, sempre dalla stessa parte.
        self._assi: list[float] = []

    def azzera(self) -> None:
        self.viste.clear()
        self.corpo = 0
        self.bloccata = False
        self._assi.clear()

    def _non_torna(self, bande, testo_originale, scala, nome_font) -> bool:
        """La lettura non torna: c'e' molto piu' inchiostro del testo letto.

        **Non lo si chiede alla taglia**, e la ragione e' istruttiva: la taglia
        ha gia' un tetto sull'altezza che la rende robusta, quindi su una riga
        letta a meta' non esplode piu' — e proprio per questo non si accorge di
        niente. Una misura resa robusta smette di essere un rivelatore.

        Lo si chiede invece al confronto diretto: quanto e' largo l'inchiostro a
        schermo, contro quanto sarebbe largo il testo che l'OCR dice di aver
        letto, scritto alla taglia gia' nota. Se la banda e' il doppio, meta'
        riga non e' stata letta — e allora anche il **centro** di quella banda
        non e' il centro della battuta.
        """
        if not self.corpo or not bande:
            return False
        testo = " ".join((testo_originale or "").split())
        if not testo:
            return False
        from PIL import Image, ImageDraw

        misura = ImageDraw.Draw(Image.new("L", (1, 1)))
        atteso = misura.textlength(testo, font=carica_font(nome_font, self.corpo))
        visto = sum(x1 - x0 for x0, _, x1, _ in bande) * scala
        if atteso <= 1 or visto <= 1:
            return False
        return not (0.7 <= visto / atteso <= 1.45)

    @property
    def asse(self) -> float | None:
        """Dove il gioco scrive i suoi sottotitoli, in frazione del pezzo.

        La **mediana** dei centri visti, non l'ultimo e non il centro dell'area:
        una lettura parziale sposta il proprio centro ma non la mediana di tutte
        le altre, e la ROI non c'entra niente — e' un rettangolo tirato a mano,
        largo a piacere e non centrato su nulla in particolare.

        `None` finche' non ci sono abbastanza battute: prima di allora comanda
        cio' che si e' letto adesso, che e' l'unica cosa che si ha.
        """
        if len(self._assi) < 3:
            return None
        import statistics

        return statistics.median(self._assi)

    def guarda_asse(self, bande, larghezza: int) -> None:
        """Registra dove stava il centro di questa battuta."""
        if not bande or larghezza <= 0:
            return
        cx = (min(b[0] for b in bande) + max(b[2] for b in bande)) / 2.0
        self._assi.append(cx / larghezza)
        del self._assi[: -self.quante]

    def aggiorna(self, bande, testo_originale, scala: float, nome_font: str) -> int:
        self.sospetta = self._non_torna(bande, testo_originale, scala, nome_font)
        if self.bloccata:
            return self.corpo
        c = corpo_del_gioco(bande, testo_originale, scala, nome_font)
        if c <= 0:
            return self.corpo or 8
        # **Una stima molto lontana dalle altre non e' una taglia nuova, e' una
        # lettura sbagliata.** Senza questa riga, una riga letta a meta' fa
        # scrivere la battuta successiva al doppio.
        if self.corpo and not (0.6 * self.corpo <= c <= 1.6 * self.corpo):
            return self.corpo
        self.viste.append(c)
        del self.viste[: -self.quante]

        import statistics

        self.corpo = int(round(statistics.median(self.viste)))
        # Bloccata quando ci sono abbastanza stime **e sono d'accordo**: se
        # ballano ancora, il gioco non e' quello che si crede e si continua a
        # guardare.
        if len(self.viste) >= self.bastano:
            recenti = self.viste[-self.bastano:]
            if max(recenti) - min(recenti) <= max(1, int(0.12 * self.corpo)):
                self.bloccata = True
        return self.corpo


def colore_del_gioco(rgb) -> tuple[int, int, int]:
    """Il colore dell'inchiostro, riportato alla sua luminosita' vera.

    La media sui pixel mascherati comprende i bordi scuri dei glifi e viene
    quindi sempre piu' scura del colore vero: un bianco misurato 180 e' un bianco
    255 con dentro l'antialiasing. Si tiene la **tinta** e si rialza la
    luminosita' portando il canale piu' alto al massimo — cosi' il giallo di un
    personaggio resta giallo e il bianco torna bianco.
    """
    r, g, b = (max(0.0, float(v)) for v in rgb)
    picco = max(r, g, b)
    if picco < 1.0:
        return (255, 255, 255)
    k = 255.0 / picco
    return tuple(int(min(255, round(v * k))) for v in (r, g, b))


def _sembra_testo(r) -> bool:
    """La banda ha l'inchiostro distribuito come una riga di testo?

    Due misure sui pixel **gia' mascherati** (`LineBand.crop`), quindi gratis:

    - **il riempimento**: quanta parte del riquadro della banda e' inchiostro.
      Una riga di glifi ne ha una frazione; una banda aperta da qualche pixel di
      scenario quasi niente;
    - **le righe piene**: su quante delle sue righe-pixel c'e' inchiostro. I
      glifi attraversano la banda da cima a fondo, quindi il testo ne accende
      quasi tutte; un bordo di scenario ne accende poche e lascia il resto vuoto.

    Le soglie vengono dai fotogrammi di una sessione dal vivo dell'utente. Bande
    di sottotitolo: riempimento 0,036-0,27, righe piene 0,48-0,94. Bande di
    scenario: riempimento 0,014-0,015, righe piene 0,06-0,13.

    **Non separa tutto, e va detto**: una banda di scenario alta 186 px misurava
    righe piene 0,484, cioe' dentro l'intervallo del testo. A togliere quella e'
    l'altezza (`_gruppo_di_righe`), non questa funzione. Qui cadono le bande
    sottili e sparse, che sono le piu' numerose.
    """
    crop = getattr(r, "crop", None)
    if crop is None or crop.size == 0:
        return True  # senza pixel non si giudica: decide chi guarda l'altezza
    import numpy as np

    acceso = crop > 0
    riempimento = float(acceso.mean())
    prof = acceso.sum(axis=1)
    righe_piene = float((prof > 0.02 * crop.shape[1]).mean())
    return riempimento >= 0.025 and righe_piene >= 0.30


def _gruppo_di_righe(righe, larghezza: int, centro_roi: int):
    """Fra le bande trovate, quelle che sono **il sottotitolo**.

    `classify_lines` risponde a "dove c'e' del chiaro che stacca dal fondo", che
    su una scena luminosa e' molto piu' del sottotitolo: misurato sui fotogrammi
    dell'utente, un'auto bianca al sole apriva una banda alta **186 px** accanto
    a una riga di testo alta 64.

    Il filtro che c'era guardava **solo la sovrapposizione orizzontale** con la
    banda piu' larga. Una banda alta e larga la supera per definizione, quindi
    passava — e da li' il riquadro si allargava a tutta la fascia (misurato nel
    log dell'utente: `1515x390`, cioe' l'intera striscia d'analisi per una riga
    da 45 px) e il raggio della sfocatura saliva a 55,8 invece di 12.

    Si aggiungono le due guardie che mancavano, le stesse che usa
    `BlockDetectionManager` di RSTGameTranslation: **somiglianza di altezza** e
    **vicinanza verticale**. Le righe di una battuta sono alte uguale e stanno
    attaccate; cio' che non lo e' non e' testo suo.

    L'**ancora e' la banda piu' vicina al centro dell'area**, e ci sono volute
    tre risposte sbagliate per arrivarci. La piu' larga (com'era) elegge proprio
    la macchia, che e' larga per definizione. La piu' bassa di statura sbaglia
    all'opposto: su una scena chiara la riga di testo si **salda** al chiaro che
    ha attorno — misurato, una banda alta 186 px che *conteneva* il sottotitolo —
    e scartarla per la sua altezza vuol dire scartare il sottotitolo e tenere il
    riflesso sul tetto dell'auto. A schermo si vedeva: riquadro stretto, messo
    dove il testo non c'era, e l'italiano rimasto scoperto sotto.

    Il centro dell'area invece e' una cosa che **si sa**: l'area la disegna
    l'utente attorno ai sottotitoli, quindi e' la dichiarazione di dove stanno.
    Verificato contro la posizione vera del sottotitolo (la `row_band` della
    calibrazione) su due fotogrammi dell'utente: la banda giusta e' a 13 e 17 px
    dal centro dell'area, le altre a 117 e 180.
    """
    if not righe:
        return []
    candidate = [r for r in righe if _sembra_testo(r)] or list(righe)
    larga = max(r.x1 - r.x0 for r in candidate)
    # Le schegge non fanno testo: una banda molto piu' stretta della piu' larga
    # e' una macchia, e non deve poter fare da ancora.
    grosse = [r for r in candidate if (r.x1 - r.x0) >= 0.25 * larga] or candidate
    centro = larghezza // 2
    passanti = [r for r in grosse if r.x0 <= centro <= r.x1] or grosse
    ancora = min(passanti, key=lambda r: abs((r.top + r.bottom) // 2 - centro_roi))
    h = max(1, ancora.height)

    # **La finestra e' stretta perche' le righe vere sono alte uguale.** Misurato
    # su una battuta a due righe dell'utente: 35 e 42 px, cioe' un rapporto di
    # 1,2. Tenendo 0,6-1,6 passava anche una banda da 22 accanto a una da 36, e
    # bastava lei ad abbassare l'altezza di riferimento — quindi il raggio della
    # sfocatura — fino a lasciare leggibile l'italiano sotto.
    tenute = [
        r for r in candidate
        if 0.7 * h <= r.height <= 1.5 * h
        and min(r.x1, ancora.x1) - max(r.x0, ancora.x0)
        >= 0.3 * min(r.x1 - r.x0, ancora.x1 - ancora.x0)
    ]
    if ancora not in tenute:
        tenute.append(ancora)
    # **La vicinanza si misura sul gruppo che cresce, non sull'ancora.** Una
    # battuta su tre righe ha la terza a due altezze dalla prima: chiedendo la
    # distanza dall'ancora si perderebbe proprio la riga piu' lontana.
    tenute.sort(key=lambda r: r.top)
    i = tenute.index(ancora)
    gruppo = [ancora]
    for r in reversed(tenute[:i]):
        if gruppo[0].top - r.bottom <= 1.5 * h:
            gruppo.insert(0, r)
        else:
            break
    for r in tenute[i + 1:]:
        if r.top - gruppo[-1].bottom <= 1.5 * h:
            gruppo.append(r)
        else:
            break
    return gruppo


def inchiostro(frame, cfg):
    """Dove sta il sottotitolo del gioco in questo fotogramma.

    Torna `(pezzo, bande, rett, tinta)`:

    - `pezzo`: **copia** di una fascia del fotogramma attorno ai sottotitoli
      (copia e non vista: dxcam riusa il suo buffer, e il pezzo viaggia in una
      coda e viene disegnato fino a un decimo di secondo dopo);
    - `bande`: `(x0, y0, x1, y1)` **di ciascuna riga**, in pixel del pezzo. Una
      per riga, ognuna larga quanto la sua riga: e' cio' che va cancellato, e non
      un pixel di piu';
    - `rett`: dove sta il pezzo nel fotogramma, normalizzato;
    - `tinta`: il colore medio dei glifi, in RGB.

    **La fascia e' piu' alta della ROI, ed e' una correzione misurata.** La ROI e'
    tarata su *dove leggere*, e su GTA V taglia la riga di sopra dei sottotitoli
    su due righe: a `t=1255,7` la banda trovata era alta 13 pixel, cioe' il fondo
    di un `Ciao, Lamar!` che cominciava sopra il bordo. Il risultato a schermo era
    mezza riga italiana rimasta visibile sopra quella inglese. Non si puo'
    cancellare cio' che non si guarda.

    **Le righe sono quelle che l'OCR legge** (`classify_lines`), non l'ingombro
    della maschera: la maschera accesa da un riflesso in un angolo allargherebbe
    il riquadro a tutto lo schermo, e le righe colorate — che l'OCR scarta perche'
    non sono dialogo — lo allargherebbero verso pezzi di HUD.

    Tutto `None` se non si capisce dove sia il testo: si rinuncia a disegnare,
    invece di piazzare un riquadro a caso.
    """
    from vision.lines import LineClass, classify_lines

    pezzo, rett, dy, rh = _fascia(frame, cfg)
    if pezzo.size == 0:
        return None, None, None, None
    righe = [r for r in classify_lines(pezzo, cfg.vision) if r.cls is not LineClass.COLORED]
    if not righe:
        return None, None, None, None
    # **Solo le righe che sono il sottotitolo**: somiglianza di altezza e
    # vicinanza verticale, oltre alla sovrapposizione orizzontale che c'era gia'.
    righe = _gruppo_di_righe(righe, pezzo.shape[1], dy + rh // 2)
    if not righe:
        return None, None, None, None
    bande = [(r.x0, r.top, r.x1, r.bottom + 1) for r in righe]
    # **Il colore si media sulle sole righe tenute.** Prima si mediava su tutte
    # quelle trovate, scenario compreso: la tinta dell'inchiostro veniva tirata
    # verso il colore di cio' che si era appena deciso di non coprire, e il
    # tradotto usciva di un colore che nel sottotitolo non c'era.
    peso = float(sum(r.x1 - r.x0 for r in righe)) or 1.0
    canali = [sum(r.rgb[i] * (r.x1 - r.x0) for r in righe) / peso for i in range(3)]
    return pezzo, bande, rett, (canali[2], canali[1], canali[0])


def _fascia(frame, cfg, roi=None):
    """La fascia attorno ai sottotitoli e dove sta nel fotogramma.

    Un posto solo a deciderla, perche' la usano in due — `inchiostro()`, che
    cerca l'inchiostro da se', e `inchiostro_da_box()`, che se lo fa dire — e
    devono ritagliare **esattamente** la stessa cosa: `ritaglia()` e
    `Overlay.aggiorna()` confrontano la forma del pezzo con quella salvata, e uno
    scarto di un pixel spegne il rinfresco della sfocatura senza dire niente.

    **`roi` serve alle aree in piu'.** I rettangoli di `SpokenLine.boxes` sono in
    coordinate dell'area che ha letto quella battuta, non della ROI principale:
    con due aree dichiarate, prendere sempre `cfg.vision.roi` vorrebbe dire
    disegnare la traduzione di un cartello dentro la fascia del dialogo — cioe'
    nel posto sbagliato, senza nessun errore. Vuoto vuol dire «la ROI», che e' il
    caso di sempre.
    """
    import numpy as np

    from vision.roi import roi_pixels

    h_f, w_f = frame.shape[:2]
    rx, ry, rw, rh = roi_pixels(frame.shape, tuple(roi) if roi else cfg.vision.roi)
    respiro = int(max(0.6 * rh, 0.03 * h_f))
    ay0, ay1 = max(0, ry - respiro), min(h_f, ry + rh + respiro)
    pezzo = np.ascontiguousarray(frame[ay0:ay1, rx : rx + rw])
    rett = (rx / w_f, ay0 / h_f, rw / w_f, (ay1 - ay0) / h_f)
    return pezzo, rett, ry - ay0, rh


def inchiostro_da_box(frame, cfg, boxes, ink, roi=None):
    """Come `inchiostro()`, ma i rettangoli sono **quelli che l'OCR ha letto**.

    E' la differenza fra chiedere "dov'e' il testo?" a dei pixel vecchi di due
    secondi e saperlo gia'. Dal vivo passano piu' di due secondi fra la lettura
    del sottotitolo e la battuta doppiata (misurato: 2310 ms); `inchiostro()`
    veniva chiamata alla **fine** di quell'attesa, su un fotogramma in cui la
    scena si e' mossa e l'originale spesso e' gia' sparito. Cercando testo dove
    non ce n'e' si trova scenario — ed e' cosi' che il riquadro finiva a coprire
    l'intera fascia.

    Qui i rettangoli arrivano da `SpokenLine.boxes`, cioe' dalle bande che il
    riconoscitore aveva accettato come dialogo e su cui aveva letto delle parole,
    sul fotogramma in cui il sottotitolo **c'era**. Il colore idem: si porta
    dietro la tinta misurata allora, invece di rimisurarla su pixel in cui il
    sottotitolo non e' piu'.

    Dei pixel di **adesso** resta cio' che deve essere di adesso: il `pezzo` da
    sfocare, che e' la scena viva sotto la toppa.

    `None` se non ci sono rettangoli: chi chiama torna a `inchiostro()`.
    """
    if not boxes:
        return None, None, None, None
    pezzo, rett, dy, _rh = _fascia(frame, cfg, roi)
    if pezzo.size == 0:
        return None, None, None, None
    h_pezzo, w_pezzo = pezzo.shape[:2]
    bande = []
    for x, y, w, h in boxes:
        # I box sono in coordinate della ROI; la fascia comincia `dy` pixel
        # sopra di lei.
        x0, y0 = max(0, int(x)), max(0, int(y) + dy)
        x1, y1 = min(w_pezzo, x0 + int(w)), min(h_pezzo, y0 + int(h))
        if x1 > x0 and y1 > y0:
            bande.append((x0, y0, x1, y1))
    if not bande:
        return None, None, None, None
    return pezzo, bande, rett, tuple(ink or (255.0, 255.0, 255.0))


def ritaglia(frame, rett):
    """La stessa fascia di prima, presa da un fotogramma nuovo.

    Serve ad aggiornare la cancellatura **senza ricalcolare dove sta il
    sottotitolo**: se si ricercassero le bande, il riquadro si sposterebbe di un
    pixel per fotogramma e il sottotitolo tremerebbe. La geometria si decide una
    volta; qui si prendono solo pixel nuovi dentro lo stesso rettangolo.
    """
    import numpy as np

    h, w = frame.shape[:2]
    x0, y0 = int(round(rett[0] * w)), int(round(rett[1] * h))
    x1, y1 = x0 + int(round(rett[2] * w)), y0 + int(round(rett[3] * h))
    fetta = frame[max(0, y0) : min(h, y1), max(0, x0) : min(w, x1)]
    return np.ascontiguousarray(fetta) if fetta.size else None


def _sfoca(fetta, raggio: float):
    """Sfocatura forte, pagata poco: si rimpicciolisce, si sfoca, si ringrandisce.

    Una gaussiana costa con il raggio, e qui il raggio e' grande per forza —
    deve rendere illeggibile una riga di testo. Ma una sfocatura forte **non ha
    bisogno della piena risoluzione**: i dettagli che si perderebbero
    rimpicciolendo sono esattamente quelli che la sfocatura cancella comunque.

    Misurato sul ritaglio vero di una battuta a due righe: **13,5 ms** contro
    3, e a occhio la stessa cosa. Non e' un'ottimizzazione da manuale: e' la
    differenza fra rinfrescare la macchia a ogni fotogramma e non poterlo fare,
    e quel ritardo a schermo si vede quando la telecamera si muove.
    """
    import cv2

    if raggio <= 4.0:
        return cv2.GaussianBlur(fetta, (0, 0), sigmaX=raggio, sigmaY=raggio)
    f = min(6.0, raggio / 3.0)
    h, w = fetta.shape[:2]
    pw, ph = max(4, int(w / f)), max(4, int(h / f))
    piccolo = cv2.resize(fetta, (pw, ph), interpolation=cv2.INTER_AREA)
    piccolo = cv2.GaussianBlur(piccolo, (0, 0), sigmaX=raggio / f, sigmaY=raggio / f)
    return cv2.resize(piccolo, (w, h), interpolation=cv2.INTER_LINEAR)


@lru_cache(maxsize=32)
def _peso_bordo(w: int, h: int, quota: float = 0.18):
    """Quanto vale la sfocatura in ogni punto: 1 al centro, 0 sul bordo.

    **Spenta di default (`sfuma=0`), e la ragione e' che curava il difetto
    sbagliato.** Il bordo era il posto dove la macchia si notava, quindi si e'
    sfumato li'; ma sfumare verso i pixel del gioco vuol dire, sul bordo,
    rimettere il sottotitolo che si sta nascondendo. La fascia nitida era il 18%
    del lato corto — cioe' l'altezza del riquadro, 45-80 px — quindi 8-14 px
    tutt'intorno a un rettangolo che sta stretto al testo: le cime e le code dei
    glifi italiani riaffioravano. La cucitura non si vedeva piu', si vedeva
    l'originale.

    Resta qui perche' la strada e' buona e il difetto era **dove** si sfumava,
    non che si sfumasse: allargando la toppa oltre il testo, la sfumatura
    cadrebbe su scena senza scritte e non riporterebbe indietro niente. Non e'
    stato provato.

    **La sfumatura non si fa sull'opacita', e il perche' e' costato una prova
    dal vivo.** La finestra e' trasparente per *colore-chiave*, che e' binario:
    un pixel o vale esattamente la chiave e sparisce, o non la vale e si vede.
    Un'opacita' intermedia non esiste — diventa un pixel quasi-nero, e il
    risultato a schermo era una **cornice nera** attorno al sottotitolo, cioe'
    l'opposto esatto di quello che la sfumatura doveva fare.

    Si sfuma invece **fra due immagini**: al centro i pixel sfocati, sul bordo i
    pixel del gioco cosi' come sono. La patch resta opaca dappertutto — niente
    alfa parziale, niente cornice — e ai bordi e' identica a cio' che c'e'
    sotto, quindi non si vede il punto in cui finisce.

    La sfumatura e' una **quota** del lato corto e non un numero di pixel: su un
    sottotitolo grande dev'essere piu' larga, se no si nota lo stesso.
    """
    import numpy as np

    b = max(2.0, quota * min(w, h))
    gx = np.minimum(np.arange(w), np.arange(w)[::-1]).astype(np.float32)
    gy = np.minimum(np.arange(h), np.arange(h)[::-1]).astype(np.float32)
    mx = np.clip(gx / b, 0.0, 1.0)
    my = np.clip(gy / b, 0.0, 1.0)
    # Il prodotto e non il minimo: negli angoli le due sfumature si sommano, ed
    # e' li' che uno stacco si nota di piu'.
    return (mx[None, :] * my[:, None])[:, :, None]


def _righe(disegno, testo: str, font, larghezza_max: int) -> list[str]:
    """Il testo mandato a capo alla larghezza del sottotitolo del gioco."""
    parole, righe, corrente = testo.split(), [], ""
    for p in parole:
        prova = f"{corrente} {p}".strip()
        if corrente and disegno.textlength(prova, font=font) > larghezza_max:
            righe.append(corrente)
            corrente = p
        else:
            corrente = prova
    if corrente:
        righe.append(corrente)
    return righe or [testo]


class Sostituzione:
    """Il sottotitolo tradotto: **geometria decisa una volta, pixel aggiornati**.

    E' la divisione che risolve i due difetti opposti visti a schermo.

    Ridisegnando tutto a ogni fotogramma, il riquadro veniva ricalcolato da bande
    leggermente diverse: il testo tremava, cambiava taglia e nei fotogrammi in
    cui la dissolvenza nascondeva i glifi spariva del tutto. Un sottotitolo non
    fa niente di tutto questo — compare, sta fermo, sparisce.

    Congelando invece anche i pixel, la toppa che cancella la riga italiana
    restava quella del primo fotogramma: la scena dietro si muove, e resta un
    rettangolo di immagine vecchia in mezzo allo schermo.

    Quindi: **taglia, colore, posizione, a-capo e rettangoli si decidono
    all'inizio e non si toccano piu'**; solo la cancellatura viene rifatta sui
    pixel nuovi, e costa 0,15 ms a riga proprio per poterlo fare.
    """

    def __init__(
        self,
        pezzo,
        bande,
        testo: str,
        *,
        scala: float = 1.0,
        nome_font: str = "Arial",
        colore=None,
        corpo: int = 0,
        contorno: float = 2.0,
        blur: float = 12.0,
        inchiostro_rgb=None,
        modo: str = "cancella",
        fondo_rgb=None,   # None = si campiona dalla scena, e non puo' invecchiare
        testo_originale: str = "",
        larghezza_schermo: int = 0,
        asse: float | None = None,
        sospetta: bool = False,
        sfuma: float = 0.0,
        stringi: bool = False,
        corpo_min: int = 11,
    ) -> None:
        from PIL import Image, ImageDraw

        self.bande = list(bande)
        # **Quanto e' alta una riga di questo gioco.** Al rinfresco arrivano le
        # bande di adesso, e li' dentro puo' esserci di tutto: dal vivo un dito
        # chiaro contro una camicia scura e' passato per una riga di testo, e la
        # cancellatura ci e' passata sopra lasciando un rettangolo grigio. Una
        # riga di sottotitolo e' alta quanto le altre; il resto no.
        self.modo = (modo or "blur").lower()
        self.blur = blur
        self.fondo_rgb = None if fondo_rgb is None else tuple(int(v) for v in fondo_rgb)
        self.scala = scala
        self.sfuma = max(0.0, min(0.45, sfuma))
        self.forma = pezzo.shape[:2]
        h_pezzo, w_pezzo = self.forma

        self.corpo = corpo or corpo_del_gioco(bande, testo_originale, scala, nome_font)

        # -- quanto e' alta **una riga**, e non e' l'altezza delle bande -------
        #
        # Da qui escono il raggio della sfocatura (`blur * alta / 40`), il
        # margine del riquadro e il suo tetto: sbagliarla per eccesso vuol dire
        # una fascia sfocata in mezzo al gioco.
        #
        # Si prende la **mediana** delle bande tenute: le righe di una battuta
        # sono alte uguale, quindi su un gruppo pulito mediana, minimo e massimo
        # sono lo stesso numero. La mediana e' quella che regge se una banda
        # sbagliata si infila nel gruppo — il minimo la seguirebbe verso il
        # basso (e un raggio troppo piccolo lascia leggibile l'italiano sotto),
        # il massimo verso l'alto.
        #
        # **Ma nessuna statistica sulle altezze basta, e il perche' e' il difetto
        # piu' istruttivo di
        # questa sessione.** Su una scena chiara la riga non si affianca al
        # chiaro che ha intorno: ci si **salda**. Misurato sul fotogramma
        # dell'utente, una banda sola alta 186 px che *conteneva* il sottotitolo
        # da 45. Non c'e' nessun minimo da prendere — la banda giusta e' anche
        # quella sbagliata.
        #
        # Il tetto viene allora da una misura che **non guarda l'altezza**: il
        # corpo del carattere, che si ricava dalla larghezza dell'inchiostro
        # confrontata col testo che l'OCR ha letto. Un carattere da `c` punti
        # non fa righe di inchiostro piu' alte di ~1,3·c, discendenti compresi.
        # Cosi' una banda saldata alza il riquadro ma non il raggio.
        import statistics

        tipica = statistics.median(y1 - y0 for _, y0, _, y1 in bande)
        tetto = max(1, int(round(self.corpo * 1.3 / max(1e-6, scala))))
        self.alta = max(1, min(int(round(tipica)), tetto))
        self.colore = colore or colore_del_gioco(inchiostro_rgb or (255, 255, 255))
        self.font = carica_font(nome_font, self.corpo)
        self.contorno = max(1, int(round(contorno * scala)))

        su = lambda v: int(round(v * scala))  # noqa: E731
        self.su = su
        rett = [(su(x0), su(y0), su(x1), su(y1)) for x0, y0, x1, y1 in bande]
        bx0, by0 = min(r[0] for r in rett), min(r[1] for r in rett)
        bx1, by1 = max(r[2] for r in rett), max(r[3] for r in rett)

        # L'a-capo alla larghezza a cui va a capo il gioco, e **mai oltre lo
        # schermo**: una battuta piu' larga dello schermo non e' un sottotitolo,
        # e' un difetto che esce dall'immagine.
        misura = ImageDraw.Draw(Image.new("L", (1, 1)))
        limite = su(w_pezzo) - 8
        if larghezza_schermo:
            limite = min(limite, larghezza_schermo - 16)
        limite = max(80, limite)

        # **Una traduzione lunga va a capo, e se non basta rimpicciolisce.**
        # Nell'ordine, perche' l'ordine e' quello che tiene la resa piu' vicina
        # all'originale: prima si mandano a capo le parole (il gioco fa lo
        # stesso), e solo se cosi' occuperebbe piu' di `righe_max` si stringe il
        # carattere. Non c'e' un terzo passo perche' non serve: a quel punto ci
        # sta. Quello che **non** si fa mai e' lasciarla uscire dai lati o
        # tagliarla — un sottotitolo illeggibile e' peggio di uno un po' piccolo.
        testo = (testo or "").strip()
        self.stringi = bool(stringi)
        self.corpo_min = max(6, int(corpo_min))
        # **E c'e' un secondo modo di stare, che e' l'opposto del primo.**
        #
        # Per un sottotitolo la cosa giusta e' quella qui sopra: la traduzione
        # cresce quanto le serve e il riquadro la segue, perche' sotto c'e'
        # mezzo schermo di scena e nessuno si accorge se la fascia si allarga di
        # una riga.
        #
        # Per una scritta in mezzo allo schermo no. Li' il riquadro **e'**
        # l'oggetto — un cartello, una voce di menu, un contatore — e attorno
        # c'e' altra roba: allargarsi vuol dire coprire cio' che sta accanto, che
        # e' spesso un'altra scritta che si sta traducendo nello stesso
        # fotogramma. Quindi la larghezza e l'altezza dell'inchiostro originale
        # comandano, e a cedere e' il corpo del carattere.
        #
        # **Il pavimento e' dichiarato e si vede.** Sotto `corpo_min` non si
        # stringe piu' e si lascia sforare: illeggibile e' peggio di sforare —
        # una scritta un po' larga si legge, e si capisce anche cos'e'
        # successo. `self.stretto` dice che e' capitato, se no il caso peggiore
        # sarebbe l'unico muto.
        self.stretto = False
        if self.stringi:
            # In coordinate gia' scalate, come `limite`.
            largo_orig = max(1, bx1 - bx0)
            alto_orig = max(1, by1 - by0)
            limite = max(1, largo_orig)
            righe_max = max(1, len(bande))
        else:
            righe_max = 3
        self.righe = _righe(misura, testo, self.font, limite)

        def _sta(corpo: int, righe: list[str]) -> bool:
            """Il testo a questo corpo ci sta nel riquadro dell'originale?"""
            passo = corpo * 1.22
            largo = max(misura.textlength(r, font=carica_font(nome_font, corpo))
                        for r in righe)
            # Il 5% di tolleranza su tutti e due i lati: il contorno e
            # l'antialiasing sbordano di un pixel o due, e inseguire quel pixel
            # costerebbe due punti di corpo per niente.
            return largo <= 1.05 * largo_orig and passo * len(righe) <= 1.05 * alto_orig

        if self.stringi:
            while self.corpo > self.corpo_min and not _sta(self.corpo, self.righe):
                self.corpo = max(self.corpo_min, int(self.corpo * 0.94))
                self.font = carica_font(nome_font, self.corpo)
                self.righe = _righe(misura, testo, self.font, limite)
            self.stretto = not _sta(self.corpo, self.righe)
        else:
            while len(self.righe) > righe_max and self.corpo > 10:
                self.corpo = max(10, int(self.corpo * 0.92))
                self.font = carica_font(nome_font, self.corpo)
                self.righe = _righe(misura, testo, self.font, limite)
        self.passo = int(round(self.corpo * 1.22))
        largh = int(max(misura.textlength(r, font=self.font) for r in self.righe))

        # -- dove va scritto, e la risposta e' «dove c'e' scritto» -----------
        #
        # **Il testo tradotto si sovrappone a quello originale, riga su riga.**
        # Sembra ovvio e per due giri non lo era: si calcolava il centro di un
        # rettangolo e ci si metteva dentro il blocco di testo, e lo scarto fra
        # le due cose e' quello che si vedeva come «decentrato, si sposta».
        #
        # Lo scarto piu' grosso non era nemmeno nel calcolo: e' che `text()`
        # posiziona il testo dalla **linea tipografica**, non dall'inchiostro.
        # Fra il punto che si passa e la prima riga di pixel accesi ci sono gli
        # ascendenti, che per un carattere da 40 punti sono una decina di pixel
        # — sempre nella stessa direzione, quindi il tradotto stava
        # sistematicamente piu' in basso dell'originale. Si disegna adesso con
        # `anchor="mm"`, cioe' passando il **centro** dell'inchiostro: e' l'unico
        # modo di dire «qui in mezzo» senza dover sapere come e' fatto il font.
        rett_b = [(su(x0), su(y0), su(x1), su(y1)) for x0, y0, x1, y1 in bande]
        bx0 = min(r[0] for r in rett_b)
        by0 = min(r[1] for r in rett_b)
        bx1 = max(r[2] for r in rett_b)
        by1 = max(r[3] for r in rett_b)

        # **Il testo va dove sta il testo, e basta.**
        #
        # Ci sono voluti tre tentativi. Centrare sul rettangolo dell'area lo
        # spostava di quanto l'area e' disassata — 72 pixel misurati, sempre
        # dalla stessa parte, perche' l'area la disegna l'utente col mouse e non
        # e' centrata su niente. Centrare sulla mediana dei centri visti azzerava
        # l'errore su una battuta e lo lasciava a 72 sulla successiva, perche'
        # una mediana e' giusta in media e sbagliata su ognuna.
        #
        # La verita' e' il centro dell'inchiostro **di questa battuta**: e' li'
        # che il giocatore vede la riga da coprire. L'asse imparato serve a una
        # cosa sola — quando la lettura e' **sospetta**, cioe' quando dai suoi
        # pixel esce una taglia che non torna con quelle gia' viste. Li' non e'
        # il centro a essere sbagliato: e' tutta la lettura, e conviene
        # appoggiarsi a dove il gioco scrive di solito.
        centro_letto = (bx0 + bx1) // 2
        self.cx = (int(round(asse * su(w_pezzo)))
                   if (sospetta and asse is not None) else centro_letto)

        # **E dentro i bordi, sempre.** `text()` con `anchor="mm"` disegna meta'
        # riga a sinistra di `cx`: se il centro dell'inchiostro sta vicino al
        # bordo dell'area e la traduzione e' piu' larga dell'originale, quella
        # meta' finisce a coordinate negative e viene **tagliata dalla tela**.
        # Spostare la finestra dopo non rimedia — sposta anche il testo, che si
        # scollerebbe dal sottotitolo. Si rientra qui, prima di decidere
        # qualunque geometria: una battuta un po' fuori asse si legge, una
        # battuta tagliata no.
        mezza = largh // 2 + self.contorno + 3
        limite_dx = max(mezza, su(w_pezzo) - mezza)
        self.cx = max(mezza, min(limite_dx, self.cx))

        # I centri verticali. Se le righe tradotte sono tante quante quelle
        # lette, ognuna si posa **sulla sua**; se no si distribuisce il blocco
        # sul centro di quello originale, che e' il meglio che si possa fare
        # quando il gioco ne scrive due e la traduzione ne chiede una.
        if len(self.righe) == len(rett_b):
            ordinate = sorted((r[1] + r[3]) // 2 for r in rett_b)
        else:
            cy = (by0 + by1) // 2
            n = len(self.righe)
            primo = cy - (n - 1) * self.passo // 2
            ordinate = [primo + i * self.passo for i in range(n)]
        self.centri = [(self.cx, y) for y in ordinate]

        # -- il rettangolo da sfocare: l'originale **e** il tradotto ---------
        #
        # Non solo l'inchiostro vecchio: anche l'area dove finira' il nostro.
        # Una traduzione piu' lunga sborda dal rettangolo dell'originale, e li'
        # si troverebbe a scrivere su pixel nitidi — il contorno regge, ma il
        # testo si legge peggio e si vede che e' appiccicato.
        pad = self.contorno + 3
        m = max(4, int(0.35 * su(self.alta)))
        alt_testo = self.passo * len(self.righe)
        tx0 = self.cx - largh // 2 - pad
        tx1 = self.cx + largh // 2 + pad
        ty0 = min(ordinate) - alt_testo // (2 * len(self.righe)) - pad
        ty1 = max(ordinate) + alt_testo // (2 * len(self.righe)) + pad

        kx0 = max(0, min(bx0 - m, tx0))
        ky0 = max(0, min(by0 - m, ty0))
        kx1 = min(su(w_pezzo), max(bx1 + m, tx1))
        ky1 = min(su(h_pezzo), max(by1 + m, ty1))

        # **Un tetto duro, perche' il filtro a monte puo' sempre sbagliare.**
        # Il riquadro serve a coprire delle righe di testo: piu' alto di quanto
        # quelle righe occupano, sta sfocando scena. Il filtro di
        # `_gruppo_di_righe` toglie quasi tutto, ma una guardia che dipende da
        # un'euristica non e' una guardia — e il difetto che questo tetto
        # impedisce e' il piu' visibile del prodotto: una fascia sfocata larga
        # mezzo schermo in mezzo al gioco.
        #
        # Si contano le righe **tradotte** oltre a quelle lette: la traduzione
        # puo' occuparne piu' dell'originale, e li' il nostro testo va scritto su
        # pixel sfocati come gli altri.
        # Il tetto non puo' mai tagliare **il nostro** testo: sotto ci va
        # scritta la traduzione, e scriverla su pixel nitidi si legge peggio.
        # Quindi si prende il piu' grande fra quanto serve alle righe lette e
        # quanto serve a quelle tradotte.
        n_righe = max(len(bande), len(self.righe))
        serve = max(float(ty1 - ty0), n_righe * su(self.alta) * 1.6)
        alt_max = int(round(serve)) + 2 * pad
        if ky1 - ky0 > alt_max:
            centro_y = (min(by0, ty0) + max(by1, ty1)) // 2
            ky0 = max(0, centro_y - alt_max // 2)
            ky1 = min(su(h_pezzo), ky0 + alt_max)
        self.taglio = (max(0, int(kx0 / scala)), max(0, int(ky0 / scala)),
                       min(w_pezzo, int(kx1 / scala) + 1),
                       min(h_pezzo, int(ky1 / scala) + 1))

        self.ox = int(kx0)
        self.oy = int(min(ky0, ty0))
        self.larg = max(1, int(max(kx1, tx1)) - self.ox)
        self.alt = max(1, int(max(ky1, ty1)) - self.oy)
        self.misura = misura

    # -- i pixel, che invece si rifanno ------------------------------------

    def disegna(self, pezzo, bande=None, opaco: bool = False):
        """La tela di adesso: il rettangolo sfocato **sui pixel di questo
        fotogramma**, e sopra il testo tradotto.

        Il *live* e' il punto. La geometria e' decisa una volta e non si muove —
        se no il sottotitolo balla — ma i pixel si riprendono a ogni giro dal
        fotogramma corrente: una toppa congelata mentre la scena si muove
        diventa un rettangolo di immagine vecchia, e si vede.

        `bande` non serve piu' e resta per compatibilita': inseguire l'inchiostro
        fotogramma per fotogramma era proprio cio' che lasciava macchie dove un
        sottotitolo non c'era mai stato.
        """
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw

        h_pezzo, w_pezzo = pezzo.shape[:2]
        x0, y0, x1, y1 = self.taglio
        x1, y1 = min(x1, w_pezzo), min(y1, h_pezzo)

        tela = Image.new("RGBA", (self.larg, self.alt),
                         (0, 0, 0, 255) if opaco else (0, 0, 0, 0))
        if opaco:
            # **Il buco riempito col gioco invece che con il colore-chiave.**
            # Serve quando la finestra non puo' essere trasparente: il posto di
            # cio' che sarebbe trasparente lo prendono i pixel veri, che
            # abbiamo. Si prende dal pezzo la porzione che corrisponde alla
            # tela, replicando il bordo dove la tela sporge — una striscia nera
            # in mezzo allo schermo si vede, la continuazione di cio' che c'e'
            # gia' no.
            a = max(0, int(self.ox / self.scala))
            b = max(0, int(self.oy / self.scala))
            c_ = min(w_pezzo, a + int(self.larg / self.scala) + 1)
            d_ = min(h_pezzo, b + int(self.alt / self.scala) + 1)
            sotto = np.ascontiguousarray(pezzo[b:d_, a:c_, :3][:, :, ::-1])
            if sotto.size:
                sotto = np.array(Image.fromarray(sotto).resize(
                    (max(1, int(round((c_ - a) * self.scala))),
                     max(1, int(round((d_ - b) * self.scala))))))
                giu = max(0, self.alt - sotto.shape[0])
                dx = max(0, self.larg - sotto.shape[1])
                if giu or dx:
                    sotto = np.pad(sotto, ((0, giu), (0, dx), (0, 0)), mode="edge")
                tela.paste(Image.fromarray(
                    np.ascontiguousarray(sotto[: self.alt, : self.larg])), (0, 0))

        if self.modo != "nessuno" and x1 > x0 and y1 > y0:
            fetta = np.ascontiguousarray(pezzo[y0:y1, x0:x1, :3])
            w = max(1, int(round((x1 - x0) * self.scala)))
            h = max(1, int(round((y1 - y0) * self.scala)))
            if self.modo == "riquadro":
                # **Il colore si prende dalla scena, se non e' stato imposto.**
                # Un riquadro non puo' andare in ritardo — non ha struttura da
                # mostrare in ritardo — ma un rettangolo nero in mezzo al gioco
                # si vede da un chilometro. Prendendo la **mediana** dei pixel
                # che sta coprendo, la toppa e' del colore di cio' che c'era, si
                # aggiorna a ogni fotogramma come il blur, e non puo' mai
                # sembrare vecchia: un colore piatto non ha niente da datare.
                # La mediana e non la media: la riga di testo bianca tirerebbe la
                # media verso il chiaro proprio perche' e' cio' che si vuole
                # togliere.
                if self.fondo_rgb is None:
                    med = np.median(fetta.reshape(-1, 3), axis=0)
                    tinta = tuple(int(v) for v in med[::-1])  # BGR -> RGB
                else:
                    tinta = self.fondo_rgb
                patch = Image.new("RGB", (w, h), tinta)
            else:
                # **Il raggio segue l'altezza dei glifi.** `blur_strength` e'
                # dichiarato su un inchiostro alto 40 px (GTA V a 1080p): cosi'
                # lo stesso numero rende illeggibile una riga a 1080p, a 1440p e
                # su un gioco che scrive piu' grande.
                raggio = max(2.0, self.blur * self.alta / 40.0)
                sfocato = _sfoca(fetta, raggio)
                # **Sfocato fino al bordo, e la sfumatura e' spenta.** Sfumare
                # verso i pixel del gioco vuol dire, sul bordo, rimettere cio'
                # che c'e' sotto — e sotto c'e' il sottotitolo che si sta
                # nascondendo. Con la quota vecchia (0,18 del lato corto) la
                # fascia nitida era di 8-14 px su un riquadro alto 45-80, che sta
                # stretto al testo: le cime e le code dei glifi italiani
                # riaffioravano tutt'intorno. Vista dall'utente a schermo, non da
                # un contatore: nessuna delle misure sulla macchia guarda cosa
                # c'e' **dentro** ai suoi bordi.
                if self.sfuma > 0.0:
                    peso = _peso_bordo(fetta.shape[1], fetta.shape[0], self.sfuma)
                    sfocato = (sfocato.astype(np.float32) * peso
                               + fetta.astype(np.float32) * (1.0 - peso))
                patch = Image.fromarray(
                    np.ascontiguousarray(sfocato.astype(np.uint8)[:, :, ::-1])
                ).resize((w, h))
            tela.paste(patch, (int(self.su(x0)) - self.ox,
                               int(self.su(y0)) - self.oy))

        d = ImageDraw.Draw(tela)
        for riga, (cx, cy) in zip(self.righe, self.centri):
            # `anchor="mm"` = il punto passato e' il **centro** del testo, in
            # orizzontale e in verticale. E' l'unico modo di posarlo esattamente
            # dove stava l'altro senza dover sapere dove il font mette la linea
            # di base.
            d.text((cx - self.ox, cy - self.oy), riga, font=self.font,
                   fill=(*self.colore, 255), anchor="mm",
                   stroke_width=self.contorno, stroke_fill=(0, 0, 0, 255))
        return tela, (self.ox, self.oy)


def dipingi(pezzo, bande, testo: str, opaco: bool = False, **kw):
    """Decide e disegna in un colpo solo. `None` se non c'e' niente da coprire."""
    if not bande:
        return None
    return Sostituzione(pezzo, bande, testo, **kw).disegna(pezzo, opaco=opaco)


def su_chiave(tela):
    """La tela RGBA appiattita sul colore-chiave, per una finestra Windows.

    Tk non sa fare finestre con trasparenza per pixel: sa fare un colore che
    sparisce. Quindi il trasparente diventa `CHIAVE`, e i pixel opachi che per
    caso valessero esattamente `CHIAVE` vengono spostati di uno — se no si
    aprirebbero buchi neri dentro il testo.
    """
    import numpy as np
    from PIL import Image

    fondo = Image.new("RGB", tela.size, CHIAVE_RGB)
    fondo.paste(tela, (0, 0), tela)
    arr = np.array(fondo)
    alfa = np.array(tela.getchannel("A"))
    collisione = (alfa > 0) & np.all(arr == np.array(CHIAVE_RGB), axis=2)
    arr[collisione] = (4, 4, 4)
    return Image.fromarray(arr)


class OverlayBase:
    """Il sottotitolo tradotto: **tutto quello che non e' una finestra**.

    Geometria, misura del carattere, cosa disegnare e quando sparire stanno qui;
    chi eredita mette solo i pixel a schermo. E' la stessa ragione per cui
    `dipingi()` e' puro e lo usano la finestra dal vivo **e** `tools/overlay_mp4`:
    due disegnatori diversi mostrano due cose diverse, ed e' esattamente cosi'
    che sono nati i difetti di questo pezzo. Adesso i front-end sono due — Tk e
    Qt — e la tentazione di scriverne un secondo era la stessa.

    Chi eredita implementa cinque cose: `_dipingi`, `_apri`, `_chiudi`,
    `geometria` ed `esclusione`. Tutto il resto e' gia' qui e non si riscrive.
    """

    def __init__(
        self,
        roi: tuple[float, float, float, float],
        *,
        schermo: tuple[int, int],
        colore: str = "",
        fondo: str = "#000000",
        font: str = "Arial",
        font_frac: float = 0.0,
        opacita: float = 1.0,
        modo: str = "cancella",
        blur: float = 12.0,
        contorno: float = 2.0,
        escludi_cattura: bool = True,
        trasparente: bool = True,
    ) -> None:
        self.blur = max(0.0, blur)
        # **Spegnere l'esclusione serve solo a fotografarla.** La finestra e'
        # esclusa dalla cattura, e uno screenshot *e'* una cattura: con
        # l'esclusione accesa l'overlay non compare in nessuna immagine, nemmeno
        # nelle nostre. Per guardarlo si spegne, e si riaccende — non e'
        # un'opzione da config, perche' spenta l'OCR ricomincia a leggere noi.
        self.escludi_cattura = escludi_cattura
        # `trasparente` = il buco e' un colore-chiave (Tk) o vero alfa (Qt).
        # Spento, la finestra e' opaca e il buco lo riempiono i pixel del gioco:
        # piu' rozzo (la scena dietro e' ferma fra un rinfresco e l'altro) ma
        # **si vede sempre**.
        self.trasparente = trasparente
        self.opacita = max(0.1, min(1.0, opacita))
        self.modo = (modo or "cancella").lower()
        self.nome_font = font
        self.contorno = contorno
        # Vuoto e zero vogliono dire «come il gioco», e sono i default: un colore
        # e una misura scelti da noi sarebbero un cartello appiccicato sopra il
        # sottotitolo invece del sottotitolo.
        self.colore = self._rgb(colore) if colore else None
        self.misura = MisuraCarattere()
        self.sost = None     # la battuta a schermo adesso, con la sua geometria
        self.t_on = -1.0     # quale sottotitolo del gioco sta traducendo
        self._vuoti = 0      # giri di seguito senza inchiostro del gioco
        # L'ultima tela disegnata e dove sta sullo schermo. La legge la
        # telecamera virtuale: **gli stessi pixel** che sono a schermo, non una
        # seconda composizione che divergerebbe al primo ritocco.
        self.ultima = None
        self.vision = None   # le soglie con cui ritrovare l'inchiostro
        self.rett = None
        # Vuoto = «come la scena», e adesso e' il default: si campiona il colore
        # sotto la toppa a ogni rinfresco. Un `#rrggbb` esplicito vince.
        self.fondo_rgb = self._rgb(fondo) if fondo else None
        self.font_frac = font_frac
        self.schermo = (int(schermo[0]), int(schermo[1]))
        # **Dove sta il gioco.** Catturando una finestra, le coordinate del
        # fotogramma sono le sue, non quelle dello schermo: senza questo
        # rettangolo l'overlay cadrebbe sulla stessa *frazione* di schermo invece
        # che sulla stessa frazione di finestra, cioe' quasi sempre altrove.
        # `None` = si cattura lo schermo intero, ed e' come prima.
        self.ancora = None
        # `geom` e' il ripiego dalla ROI (dove andrebbe la finestra se non
        # avesse ancora disegnato niente); `_geom_ora` e' dove sta davvero
        # adesso. Tenerli separati evita che un `riposiziona` a battuta accesa
        # sposti una toppa gia' calcolata.
        self.geom = self._geom_roi(roi)
        self._geom_ora = self.geom
        self._visibile = False

    def ristila(
        self,
        *,
        colore: str | None = None,
        fondo: str | None = None,
        font: str | None = None,
        font_frac: float | None = None,
        opacita: float | None = None,
        modo: str | None = None,
        blur: float | None = None,
        contorno: float | None = None,
    ) -> None:
        """Cambia l'aspetto **a finestra aperta**, senza ricostruirla.

        Il colore del testo, il carattere, il blur e il modo di coprire non sono
        in `FREDDI`, cioe' la finestra dichiara che si possono cambiare a
        sessione accesa e non ci mette il marchio «all'avvio». Non era vero:
        `OverlayBase.__init__` se li **copia** dentro, e la sessione continuava
        con quelli di partenza. Una promessa scritta nella UI e non mantenuta e'
        peggio di un campo assente — l'utente cambia il colore, non vede niente,
        e non ha modo di sapere se ha sbagliato lui o il programma.

        La battuta **gia' a schermo** non cambia, ed e' voluto: la sua geometria
        e' congelata apposta (rifarla a meta' riga faceva tremare e sparire il
        testo). Il nuovo aspetto parte dalla battuta dopo, e chi chiama lo dice.
        """
        if colore is not None:
            self.colore = self._rgb(colore) if colore else None
        if fondo is not None:
            self.fondo_rgb = self._rgb(fondo) if fondo else None
        if font is not None:
            self.nome_font = font
        if font_frac is not None:
            self.font_frac = font_frac
        if opacita is not None:
            self.opacita = max(0.1, min(1.0, opacita))
        if modo is not None:
            self.modo = (modo or "cancella").lower()
        if blur is not None:
            self.blur = max(0.0, blur)
        if contorno is not None:
            self.contorno = contorno

    # -- quello che il front-end deve saper fare ----------------------------

    def _dipingi(self, tela, geom) -> None:
        """Mette la tela RGBA a schermo. `geom` `None` = non muovere niente."""
        raise NotImplementedError

    def _apri(self) -> None:
        """La finestra compare (senza rubare il fuoco)."""
        raise NotImplementedError

    def _chiudi(self) -> None:
        """La finestra sparisce, senza essere distrutta."""
        raise NotImplementedError

    def geometria(self) -> str:
        """Dove sta e quanto e' grande, in chiaro.

        **La riga che divide in due il problema**: se qui c'e' scritto un
        riquadro e a schermo non si vede niente, il difetto e' della finestra e
        non nostro (traduzione, OCR, geometria). Senza, le due ipotesi si
        confondono e si cerca per ore dalla parte sbagliata.
        """
        w, h, x, y = self._geom_ora
        return f"{w}x{h}+{x}+{y}"

    def esclusione(self, attiva: bool) -> None:
        """Accende o spegne `WDA_EXCLUDEFROMCAPTURE` a finestra gia' aperta.

        **Serve solo a chi cattura lo schermo intero.** Li' la nostra finestra
        rientra nel fotogramma dato all'OCR — misurato, il 100% dei suoi pixel —
        e va nascosta. Scegliendo la finestra del gioco non rientra affatto
        (misurato: zero righe lette che fossero nostre su quattro), e allora
        nasconderla a **tutte** le catture e' un prezzo pagato per niente: e'
        quello che la rende invisibile anche a OBS.
        """
        self.escludi_cattura = bool(attiva)

    def distruggi(self) -> None:
        raise NotImplementedError

    # -- geometria ----------------------------------------------------------

    @staticmethod
    def _rgb(s: str) -> tuple[int, int, int]:
        s = s.lstrip("#")
        return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))

    def _geom_roi(self, roi) -> tuple[int, int, int, int]:
        ax, ay, aw, ah = self.ancora or (0, 0, *self.schermo)
        x, y, w, h = roi
        return (max(1, int(aw * w)), max(1, int(ah * h)), ax + int(aw * x), ay + int(ah * y))

    def riposiziona(self, roi) -> None:
        """La ROI e' cambiata (il selettore d'area): il ripiego deve seguirla."""
        self.geom = self._geom_roi(roi)

    def aggancia(self, rett_px) -> None:
        """Il gioco sta li'. Si richiama quando la finestra si sposta.

        Costa una chiamata a Windows e va rifatta spesso: una finestra che si
        sposta senza che l'overlay la segua e' un sottotitolo tradotto in mezzo
        al desktop.
        """
        self.ancora = tuple(int(v) for v in rett_px) if rett_px else None

    def _dichiara_esclusione(self) -> None:
        """Applica l'esclusione decisa alla nascita, e dice se non ci riesce.

        Un ripiego che non si dichiara e' peggio di un errore: senza esclusione,
        chi cattura lo schermo ci legge, e il difetto sembra dell'OCR.
        """
        self.esclusione(self.escludi_cattura)
        if not self.escludi_cattura:
            print("overlay: non escluso dalla cattura — giusto se si cattura una "
                  "finestra, sbagliato se si cattura lo schermo", file=sys.stderr)

    # -- uso ---------------------------------------------------------------

    def mostra(self, testo: str, pezzo=None, bande=None, rett=None, inchiostro=None,
               originale: str = "") -> None:
        """Mostra il testo tradotto sopra il sottotitolo del gioco.

        `pezzo` e' il ritaglio del fotogramma attorno al sottotitolo, `bande` i
        rettangoli dei glifi da coprire (pixel del pezzo), `rett` dove sta il
        pezzo nel fotogramma in coordinate normalizzate, `inchiostro` il colore
        medio dei glifi. Senza, non si disegna niente: meglio nessun sottotitolo
        tradotto che un cartello piazzato a caso.
        """
        testo = (testo or "").strip()
        if not testo:
            self.nascondi()
            return
        if pezzo is None or not bande or rett is None:
            return  # non si sa dove sta il sottotitolo: non si disegna a caso
        try:
            fatto = self._prepara(testo, pezzo, bande, rett, inchiostro, originale)
        except Exception as exc:  # pragma: no cover - meglio zoppicare che cadere
            print(f"overlay: {type(exc).__name__}: {exc}", file=sys.stderr)
            fatto = None
        if fatto is None:
            return
        tela, geom = fatto
        self._dipingi(tela, geom)
        if not self._visibile:
            self._apri()
            self._visibile = True

    def aggiorna(self, pezzo) -> None:
        """Rifa' **la sfocatura** sui pixel nuovi, senza muovere niente.

        Arriva gia' ritagliato: mandare tutto il fotogramma trenta volte al
        secondo vorrebbe dire copiare 11 MB a giro per usarne mezzo.

        La geometria non si tocca — se no il sottotitolo balla — ma i pixel sotto
        sono quelli di adesso, se no la macchia sfocata resta indietro rispetto
        alla scena che scorre.
        """
        if self.sost is None or not self._visibile or pezzo is None:
            return
        if pezzo.shape[:2] != self.sost.forma:
            return
        try:
            tela, _ = self.sost.disegna(pezzo, opaco=not self.trasparente)
        except Exception:  # pragma: no cover - meglio una toppa vecchia che un crollo
            return
        self._dipingi(tela, None)
        self.ultima = (tela, self._geom_ora[2], self._geom_ora[3])

    def _prepara(self, testo, pezzo, bande, rett, inchiostro, originale=""):
        sw, sh = self.schermo
        ax, ay, aw, ah = self.ancora or (0, 0, sw, sh)
        h_pezzo, w_pezzo = pezzo.shape[:2]
        scala = (rett[2] * aw) / max(1, w_pezzo)
        self.misura.guarda_asse(bande, pezzo.shape[1])
        corpo = (int(sh * self.font_frac) if self.font_frac > 0
                 else self.misura.aggiorna(bande, originale, scala, self.nome_font))
        self.sost = Sostituzione(
            pezzo, bande, testo,
            scala=scala, nome_font=self.nome_font, colore=self.colore,
            corpo=corpo, contorno=self.contorno, blur=self.blur,
            inchiostro_rgb=inchiostro, modo=self.modo, fondo_rgb=self.fondo_rgb,
            testo_originale=originale, larghezza_schermo=min(aw, sw),
            asse=self.misura.asse, sospetta=self.misura.sospetta,
        )
        self.rett = rett
        self._vuoti = 0
        tela, (ox, oy) = self.sost.disegna(pezzo, opaco=not self.trasparente)
        x = ax + int(rett[0] * aw) + ox
        y = ay + int(rett[1] * ah) + oy
        geom = (tela.width, tela.height,
                max(0, min(sw - tela.width, x)), max(0, min(sh - tela.height, y)))
        self._geom_ora = geom
        self.ultima = (tela, geom[2], geom[3])
        return tela, geom

    def nascondi(self) -> None:
        self.sost = None
        self.ultima = None
        self.t_on = -1.0
        if self._visibile:
            self._chiudi()
            self._visibile = False


class Overlay(OverlayBase):
    """La finestra senza bordi sopra il gioco, in **Tkinter**.

    Il buco trasparente e' un **colore-chiave**: Tk non sa fare l'alfa per
    pixel, quindi si dichiara un colore che sparisce e si sta attenti che il
    disegno non lo contenga per caso (`su_chiave`).
    """

    def __init__(self, root, roi: tuple[float, float, float, float], **kw) -> None:
        import tkinter as tk

        super().__init__(
            roi, schermo=(root.winfo_screenwidth(), root.winfo_screenheight()), **kw
        )
        self._foto = None
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=CHIAVE)
        try:
            self.top.attributes("-alpha", self.opacita)
        except tk.TclError:  # pragma: no cover - dipende dal window manager
            pass
        self.etichetta = tk.Label(self.top, bd=0, highlightthickness=0, bg=CHIAVE,
                                  padx=0, pady=0)
        self.etichetta.pack(expand=True, fill="both")

        self.top.geometry("%dx%d+%d+%d" % self.geom)
        self._passante()
        self.top.withdraw()

    # -- le cinque cose che il front-end deve fare --------------------------

    def _dipingi(self, tela, geom) -> None:
        from PIL import ImageTk

        piatta = su_chiave(tela) if self.trasparente else tela.convert("RGB")
        self._foto = ImageTk.PhotoImage(piatta, master=self.top)
        self.etichetta.configure(image=self._foto)
        if geom is not None:
            self.top.geometry("%dx%d+%d+%d" % geom)

    def _apri(self) -> None:
        self.top.deiconify()
        self.top.attributes("-topmost", True)

    def _chiudi(self) -> None:
        self.top.withdraw()

    def geometria(self) -> str:
        return self.top.geometry()

    def distruggi(self) -> None:
        import tkinter as tk

        try:
            self.top.destroy()
        except tk.TclError:  # pragma: no cover
            pass

    # -- Windows ------------------------------------------------------------

    def _passante(self) -> None:
        """Tre proprieta' di Windows, e nessuna e' una rifinitura.

        **Fuori dalla cattura** (`WDA_EXCLUDEFROMCAPTURE`): senza, la finestra
        finisce nel fotogramma che diamo all'OCR — misurato, il 100% dei suoi
        pixel — e l'OCR smette di leggere il gioco per leggere noi.

        **Trasparente ai clic** (`WS_EX_TRANSPARENT`): una finestra sopra il
        gioco che intercetta il mouse rende ingiocabile il gioco.

        **Incapace di prendere il fuoco** (`WS_EX_NOACTIVATE`): comparendo,
        toglierebbe il fuoco al gioco, che in molti giochi vuol dire mettere in
        pausa o perdere il puntatore.
        """
        import tkinter as tk

        if sys.platform != "win32":
            print("overlay: clic passanti ed esclusione dalla cattura non "
                  "disponibili qui — l'OCR leggera' il nostro testo", file=sys.stderr)
            return
        import ctypes
        from ctypes import wintypes

        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080

        self.top.update_idletasks()
        u32 = ctypes.windll.user32
        hwnd = u32.GetParent(self.top.winfo_id())
        u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.GetWindowLongW.restype = ctypes.c_long
        u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        stile = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(
            hwnd, GWL_EXSTYLE,
            stile | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
        )
        # Il colore che sparisce. Va messo **dopo** WS_EX_LAYERED.
        if self.trasparente:
            try:
                self.top.attributes("-transparentcolor", CHIAVE)
            except tk.TclError:  # pragma: no cover
                print("overlay: colore trasparente non disponibile", file=sys.stderr)
        self._dichiara_esclusione()

    def esclusione(self, attiva: bool) -> None:
        """Si rimette a `WDA_NONE` invece di omettere la chiamata: l'affinita' e'
        una proprieta' della finestra, e ometterla lascia quella di prima.
        """
        super().esclusione(attiva)
        if sys.platform != "win32":
            return
        import ctypes

        WDA_EXCLUDEFROMCAPTURE = 0x00000011
        u32 = ctypes.windll.user32
        hwnd = u32.GetParent(self.top.winfo_id()) or self.top.winfo_id()
        u32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE if attiva else 0)
