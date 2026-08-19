"""**Menta** — il tema della finestra Qt: colori, geometria, corpi, materiale.

Tutto quello che c'e' qui dentro deriva da una cosa sola — i colori e la
geometria del logo (`assets/logo/livedub.png`) — e il resto e' conseguenza. Si
chiama Menta dal verde dell'onda che esce dalla bocca, `#43f1c1`, che in questo
disegno e' il colore di **tutto cio' che si puo' toccare**. Il documento intero
sta in `docs/interfaccia.md`; qui ci sono i numeri, e chi scrive un pezzo di
finestra li cerca qui invece di inventarli.

**Perche' un file e non delle costanti sparse.** I 3, 6, 8, 9, 10, 12, 14, 16,
18, 22, 24 che questo file sostituisce non erano sbagliati uno per uno: erano
scelti guardando quel pezzo e non la finestra, e insieme facevano
un'interfaccia senza scala. Con una scala a passi di quattro le distanze si
**confrontano** — due cose alla stessa distanza sono allo stesso livello, e
l'occhio lo legge senza saperlo.

**Perche' si e' cambiato motore (Tkinter -> Qt).** Gli angoli stondati in Tk si
ottenevano generando le immagini dei widget e registrandole come elementi a nove
fette, e ci sono voluti tre giri per scoprire che sostituendo il bordo di un
bottone sparisce la scritta, che riscrivendo il layout di un contatore il numero
si schiaccia, e che al menu a tendina spariva la freccia. Tre difetti in una cosa
che in Qt e' una riga: `border-radius: 8px`. **PySide6 e non PyQt**: e' il
binding ufficiale di The Qt Company ed e' LGPL-3, compatibile con la GPL-3 di
questo progetto (si veda `LICENZE.md`).

**Chiaro o scuro lo decide Windows, non noi.** Qt 6.5 in su espone il tema di
sistema (`QStyleHints.colorScheme`) e **avvisa quando cambia**
(`colorSchemeChanged`), quindi non serve leggere il registro ne' riavviare: si
riapplica il foglio di stile.

**Ma le due tavolozze non sono l'una l'inverso dell'altra**, ed e' la parte che
conta. I sei colori dei personaggi nel log sono l'informazione principale di
questa finestra — la domanda che ci si fa guardandola non e' «cosa ha detto» ma
«e' sempre lo stesso a parlare?» — e devono restare distinguibili **fra loro**
sul fondo su cui sono disegnati. Gli stessi sei che funzionano sul nero, messi
sul bianco, diventano pastelli che si confondono a coppie. Quindi ce ne sono sei
per il chiaro, piu' scuri e piu' saturi: stessi ruoli, colori diversi.

**Questo modulo non importa PySide6 al livello del modulo**, e non e' un
dettaglio: `R(h)`, le tavolozze, i contrasti e la scelta del colore sono
**regole**, non disegno, e una regola si verifica in una suite che gira senza
aprire niente. Qt entra solo dentro `attuale()` e dentro gli aiuti che toccano un
widget.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_RADICE = Path(__file__).resolve().parent.parent

# Le immagini generate (spunta e frecce) dipendono dal colore, quindi ce n'e' un
# giro per tavolozza. Si disegnano una volta e restano.
_DISEGNI = _RADICE / "models" / "ui"
LOGHI = _RADICE / "assets" / "logo"


# ============================================================ la tavolozza ====


@dataclass(frozen=True)
class Tavolozza:
    """I dodici ruoli piu' i due stati. Due istanze: `SCURA` e `CHIARA`.

    Un colore nuovo entra qui o non entra. Il `#39d353` scritto a mano nel
    selettore d'area e' l'esempio di come si comincia: funziona, si vede, e nel
    tema chiaro non l'ha mai guardato nessuno.
    """

    nome: str
    fondo: str
    superficie: str
    superficie_alta: str
    bordo: str
    bordo_forte: str
    testo: str
    testo_tenue: str
    testo_fioco: str
    accento: str
    accento_chiaro: str
    accento_scuro: str
    su_accento: str
    ambra: str
    rosso: str
    voci: tuple[str, ...]

    @property
    def scuro(self) -> bool:
        return self.nome == "scuro"


# **La menta e' un riempimento, non un testo**, ed e' il numero che avrebbe fatto
# sbagliare tutto: `#43f1c1` su bianco fa 1,44:1, ma sul tema scuro fa 12,9:1 —
# chi la prova li' conclude che funziona. Quindi sul chiaro `accento` e' una
# menta scurita (`#07785d`, 5,5:1) per testo e contorni, e questa costante resta
# il **riempimento** in tutti e due i temi.
#
# Il guadagno e' che il bottone Avvia e' letteralmente il colore dell'onda del
# logo sia sul chiaro sia sullo scuro, ed e' l'unico elemento della finestra che
# non cambia colore col tema. Chi lo cerca lo trova sempre nello stesso modo.
MENTA = "#43f1c1"

SCURA = Tavolozza(
    nome="scuro",
    fondo="#0f131b", superficie="#181e29", superficie_alta="#212836",
    bordo="#2c3444", bordo_forte="#3b4557",
    testo="#e4e9f2", testo_tenue="#808ba5", testo_fioco="#545e71",
    accento=MENTA, accento_chiaro="#95ffdf", accento_scuro="#1fb894",
    su_accento="#06231c",
    ambra="#f5b544", rosso="#ff6b5e",
    voci=("#ffb86b", "#79c0ff", "#ff8fb1", "#c9a0ff", "#f2d65c", "#9ee85f"),
)

CHIARA = Tavolozza(
    nome="chiaro",
    fondo="#f2f4f8", superficie="#ffffff", superficie_alta="#e9edf4",
    bordo="#d3dae6", bordo_forte="#b9c3d4",
    testo="#141922", testo_tenue="#5a6579", testo_fioco="#7e8aa2",
    accento="#07785d", accento_chiaro=MENTA, accento_scuro="#05614c",
    su_accento="#06231c",
    ambra="#a16207", rosso="#cc372c",
    voci=("#b45309", "#1e5fbf", "#b8286a", "#6d3ad6", "#8a6a00", "#3f7d1e"),
)


def attuale(app) -> Tavolozza:
    """La tavolozza che Windows sta chiedendo adesso.

    Se Qt non sa rispondere — versione vecchia, sistema che non lo espone — si
    resta sullo **scuro e non si indovina**: un default dichiarato vale piu' di
    una lettura che puo' sbagliare.
    """
    try:
        from PySide6.QtCore import Qt

        schema = app.styleHints().colorScheme()
        if schema == Qt.ColorScheme.Light:
            return CHIARA
        if schema == Qt.ColorScheme.Dark:
            return SCURA
    except Exception:
        pass
    return SCURA


# ============================================================== la geometria ==

# **Le distanze: passo di quattro, otto valori, e non se ne aggiungono.**
S0, S1, S2, S3, S4, S5, S6, S7 = 2, 4, 8, 12, 16, 24, 32, 48

# **I corpi: cinque misure, due pesi, e basta.** Una sesta misura non aggiunge un
# livello di gerarchia, aggiunge un dubbio.
C_NOME, C_STATO, C_TITOLO, C_TESTO, C_NOTA = 16, 13, 11, 10, 9

# Segoe UI Variable e Cascadia Mono ci sono su ogni Windows 11; i ripieghi sono
# il carattere di sistema di prima.
#
# **Il monospazio e' rimasto in un posto solo: il log.** Li' non e' uno stile, e'
# la cosa che rende leggibile la lista — ora, sigla, voce, latenza e testo sono
# colonne, e in proporzionale non si incolonnano. Dappertutto altrove era un
# vezzo: la barra della misura, i nomi dei campi, l'elenco delle finestre e le
# note in monospazio facevano sembrare l'interfaccia un terminale, e un numero
# nella barra in fondo non ha nessuna colonna con cui allinearsi.
UI = "Segoe UI Variable"
UI_RIPIEGO = "Segoe UI"
MONO = "Cascadia Mono"
MONO_RIPIEGO = "Consolas"

# Le altezze fisse della colonna. Il resto e' il contenuto, che si allunga.
H_TESTATA, H_BARRA, H_STRISCIA, H_LINGUETTE, H_MISURA = 56, 52, 40, 40, 28

# **La finestra.** Sotto il minimo la barra dei comandi non ci sta in una riga;
# la predefinita tiene il log e dodici righe di parametri.
MIN_LARGO, MIN_ALTO = 960, 640
LARGO, ALTO = 1280, 860

# Un elenco di parametri lungo 2400 px su un monitor grande e' illeggibile:
# l'occhio perde la riga fra l'etichetta e il controllo. Il log fa eccezione —
# quello usa tutta la larghezza, perche' e' fatto di colonne in monospazio.
MAX_CONTENUTO = 880

# **I punti di rottura sono rimasti uno.** Il disegno ne prevedeva tre; provati a
# schermo, due erano difetti. Nascondere la ROI dalla barra dei comandi sotto i
# 1000 px non serviva piu' — quella riga era scritta due volte, ed e' stata tolta
# dalla barra e basta. E ridurre la barra della misura a tre valori sotto i 720
# faceva **sparire i numeri uno dopo l'altro** mentre si rimpiccioliva la
# finestra, senza che niente dicesse perche': un'informazione che se ne va in
# silenzio e' peggio di una riga stretta.
ROTTURA_SESSIONE = 1120


def R(h: int) -> int:
    """Il raggio di un elemento alto `h`. Dal logo: **19,8% dell'altezza**.

    Il tetto c'e' perche' un pannello alto 600 px non e' una pillola; il
    pavimento perche' sotto i 4 px un angolo non si vede e si paga lo stesso.

    **Non si copia un raggio da un elemento di altezza diversa**: 8 px su un
    bottone alto 34 e 8 px su un pannello alto 400 non sono lo stesso angolo,
    sono due decisioni diverse travestite da una.
    """
    return max(4, min(18, round(0.20 * h)))


# Quelli che escono da `R(h)`, scritti una volta e chiamati per nome. Chi
# aggiunge un elemento applica `R(h)` e mette il risultato qui.
R_MARCA = R(16)        # marca nel margine, spunta                 -> 4
R_CAMPO = R(30)        # riga di elenco, campo, tendina, contatore  -> 6
R_BOTTONE = R(34)      # bottone                                    -> 7
R_LINGUETTA = R(40)    # linguetta, tessera del logo                -> 8
R_TESSERA = R(56)      # striscia, tessera d'errore, scheda         -> 11
R_PANNELLO = R(90)     # pannello, dialogo, pannello a tutto schermo-> 18

# I tre cerchi: raggio = meta' del lato. Stessa regola portata al limite.
LATO_SPIA, R_SPIA = 10, 5
# Il logo in testata: alto quanto la testata meno il respiro sopra e sotto. Non
# ha una tessera dietro, quindi non ha un raggio: ce l'ha gia' lui.
LATO_LOGO = H_TESTATA - 2 * S1
LATO_MANIGLIA, R_MANIGLIA = 14, 7
LATO_AIUTO, R_AIUTO = 28, 14
H_PILLOLA, R_PILLOLA = 28, 14

# **Quante voci si vedono in una tendina prima che si metta a scorrere**, e non
# e' un numero d'occhio: e' l'unico che sta in mezzo a due vincoli misurati.
#
# *Sotto*: censite le tendine della finestra, **ventotto su trentaquattro hanno
# sette voci o meno** e la successiva ne ha quarantatre. Fra 8 e 42 il
# comportamento di ogni singolo menu e' identico — quello e' l'altopiano, e una
# soglia si sceglie li' dentro.
#
# *Sopra*: una riga di tendina misura 25 px e la cornice 18, quindi la tendina
# aperta e' alta `25n + 18`. Non deve superare la finestra piu' piccola che il
# programma permette (`MIN_ALTO` = 640), se no si apre un menu piu' alto della
# sua stessa finestra: `n <= 24`.
#
# In mezzo a 8..24 c'e' **16** — che era gia' scritto a mano nel menu delle
# lingue, e adesso e' scritto una volta sola. Aperta fa 418 px, cioe' i due
# terzi della finestra minima e il 29% di uno schermo da 1440.
VOCI_TENDINA = 16


# ================================================================ il movimento =

# **Niente si muove in un angolo mentre il gioco gira.** Questa finestra sta
# accanto a una partita: qualunque cosa pulsi, rimbalzi o scorra in periferia si
# prende un'attenzione che appartiene al gioco, e se la prende proprio quando
# l'utente e' meno in grado di ignorarla. Il logo non si anima, la spia non
# lampeggia, e i numeri della barra della misura si aggiornano al massimo due
# volte al secondo — non trenta, che e' la frequenza a cui arrivano.
MS_CONTROLLO = 120   # colore, opacita', stato di un controllo
MS_PANNELLO = 200    # comparsa e scomparsa di un pannello o della striscia
MS_LOGO = 0          # sereno <-> guasto: istantaneo, se no lampeggia
MS_CARICO = 120      # meta' del velo che copre un rifacimento dell'interfaccia
HZ_MISURA = 2.0      # la barra della misura, in aggiornamenti al secondo

# **Il movimento e' sempre di transizione, mai di attesa.** La regola qui sopra
# — niente si muove in un angolo mentre il gioco gira — non vieta un'animazione:
# vieta una cosa che pulsa **da sola**. Un velo che copre il cambio di lingua
# comincia perche' l'hai chiesto tu, dura due decimi e finisce; una girandola
# che gira finche' la catena e' viva no, e sarebbe la stessa cosa che il
# documento chiama «prendersi un'attenzione che appartiene al gioco».
#
# Il solo movimento che dura piu' di un istante e' la barra dell'**avvio**, ed e'
# limitata dalla cosa che sta aspettando: parte con Avvia, si spegne alla prima
# riga di stato viva. Caricare Kokoro costa secondi, e una finestra che non dice
# niente per tre secondi si legge come una finestra bloccata.


def movimento_ridotto() -> bool:
    """Il sistema chiede meno movimento?

    Non e' una rifinitura: l'utente tipo di questo programma sta gia' guardando
    uno schermo che si muove molto. Su Windows la richiesta e'
    `SPI_GETCLIENTAREAANIMATION`; dove non si sa, si risponde «no» — cioe' il
    comportamento di prima — invece di indovinare.
    """
    try:
        import ctypes

        acceso = ctypes.c_bool(True)
        # 0x1042 = SPI_GETCLIENTAREAANIMATION
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(acceso), 0)
        return not acceso.value
    except Exception:
        return False


def durata(ms: int) -> int:
    """La durata di un'animazione, azzerata se il sistema chiede meno movimento."""
    return 0 if movimento_ridotto() else ms


def durata_carico(in_sessione: bool) -> int:
    """Quanto dura **mezzo** velo, e zero se la catena sta girando.

    Sta qui e non nella finestra perche' e' una regola, e la regola e' questa: il
    velo copre un rifacimento dell'interfaccia (596 stringhe riscritte in ~35 ms,
    misurato), che senza copertura si vede come uno scatto. Ma i due thread della
    catena non devono pagarlo: **a sessione accesa il velo non c'e'**, e il
    cambio torna a essere lo scatto di prima, che a quel punto e' il male minore.

    Torna la meta' perche' il velo ha due tempi uguali — entra, si fa il lavoro,
    esce — e chi lo chiama non deve rifare quella divisione a mente.
    """
    return 0 if in_sessione else durata(MS_CARICO)


# ================================================================== i colori ==


def _rgb(colore: str) -> tuple[int, int, int]:
    c = colore.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def rgba(colore: str, alfa: float) -> str:
    """`#43f1c1` piu' un'opacita' -> la forma che Qt sa leggere."""
    r, g, b = _rgb(colore)
    return f"rgba({r}, {g}, {b}, {alfa:.3f})"


def _lineare(v: float) -> float:
    v /= 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminanza(colore: str) -> float:
    """La luminanza relativa WCAG 2.1 di un colore."""
    r, g, b = (_lineare(x) for x in _rgb(colore))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# **Le due soglie di leggibilita', dichiarate qui e non ricordate a memoria.**
# Erano scritte solo nella docstring di `contrasto()`, cioe' in un posto che una
# verifica non puo' leggere: ogni gruppo che voleva controllare un contrasto si
# riscriveva il suo `4.5`, e un numero riscritto e' un numero che al primo
# ritocco diventa due numeri diversi.
CONTRASTO_TESTO = 4.5     # testo normale (WCAG AA)
CONTRASTO_GRANDE = 3.0    # testo grande e contorni che portano un significato


def contrasto(a: str, b: str) -> float:
    """Il rapporto di contrasto WCAG 2.1 fra due colori, da 1 a 21.

    Sta qui e non in una verifica perche' e' il modo di rispondere alla domanda
    «questo colore nuovo si legge?» **prima** di metterlo in tavolozza. Le soglie
    sono `CONTRASTO_TESTO` e `CONTRASTO_GRANDE`.
    """
    la, lb = luminanza(a), luminanza(b)
    chiaro, scuro = max(la, lb), min(la, lb)
    return (chiaro + 0.05) / (scuro + 0.05)


def stati_elenco(t: Tavolozza) -> dict[str, tuple[str, str]]:
    """I quattro stati di una riga d'elenco, come `(fondo, testo)`.

    **Esiste per un difetto che si vedeva solo tenendo il mouse fermo sulla riga
    giusta.** Il foglio di stile diceva

        QListWidget::item:selected {{ background: menta;         color: su_accento; }}
        QListWidget::item:hover    {{ background: superficie_alta; }}

    e Qt, davanti a due regole della **stessa** specificita', tiene l'ultima:
    passando sopra alla riga **gia' scelta** il fondo tornava grigio e il testo
    restava `su_accento`, che e' un verde quasi nero fatto per stare sulla menta.
    Sul tema scuro faceva **1,12:1** — cioe' invisibile — e sul chiaro 14,1:1,
    dove il difetto non era la leggibilita' ma la scelta: la riga scelta smetteva
    di sembrare scelta proprio mentre la si stava per premere. Un difetto che nel
    tema chiaro c'e' e non si vede e' esattamente la forma che questo progetto
    paga di piu'.

    La cura non e' una pezza di colore: e' che i quattro stati stiano **in una
    tabella**, che il foglio di stile si scriva da quella e che una verifica
    possa leggerla senza aprire Qt. Cosi' uno stato nuovo o e' qui — con il suo
    contrasto misurato — o non esiste.

    **La regola dello stato «scelta sotto il mouse»**: il riempimento fa un passo
    in piu' **lontano dal fondo della pagina**, e il testo lo segue. Sullo scuro
    la pagina e' scura, quindi la menta si schiarisce (`accento_chiaro`, 13,9:1
    con `su_accento`); sul chiaro la pagina e' chiara, quindi la menta si scurisce
    (`accento`, 5,5:1 con la superficie bianca). E' la stessa direzione nei due
    temi, non due scelte che si somigliano — e resta menta, quindi la riga non
    smette mai di dire «sono io quella scelta».
    """
    return {
        "normale": (t.superficie, t.testo),
        "sotto il mouse": (t.superficie_alta, t.testo),
        "scelta": (MENTA, t.su_accento),
        "scelta sotto il mouse": ((t.accento_chiaro, t.su_accento) if t.scuro
                                  else (t.accento, t.superficie)),
    }


def _lab(colore: str) -> tuple[float, float, float]:
    r, g, b = (_lineare(x) for x in _rgb(colore))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.00000
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    """La distanza fra due colori in CIELAB (CIE76).

    Serve per i sei colori delle voci: sopra 25 due colori si distinguono anche
    di sfuggita, che e' l'unico modo in cui si guarda un log mentre si gioca.
    """
    la, aa, ba = _lab(a)
    lb, ab, bb = _lab(b)
    return ((la - lb) ** 2 + (aa - ab) ** 2 + (ba - bb) ** 2) ** 0.5


# ============================================================== i disegnini ===
#
# Due cose che Qt **non sa disegnare** da un foglio di stile e vanno generate
# come PNG, un giro per tavolozza perche' dipendono dal colore.


def _baffo(colore: str) -> str:
    """Il segno di spunta come PNG.

    **Qt disegna lo stato «spuntato» con un'immagine, e un foglio di stile non sa
    tracciare una linea.** La prima versione puntava a un nome inventato e il
    risultato era un quadrato pieno: abbastanza chiaro da non accorgersene
    subito, e sbagliato.
    """
    percorso = _DISEGNI / f"baffo-{colore.lstrip('#')}.png"
    if not percorso.exists():
        from PIL import Image, ImageDraw

        S = 4  # si disegna grande e si rimpicciolisce: PIL non antialiasa le linee
        L = 16 * S
        img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.line([(L * 0.24, L * 0.52), (L * 0.42, L * 0.71), (L * 0.77, L * 0.29)],
               fill=colore, width=int(S * 1.9), joint="curve")
        percorso.parent.mkdir(parents=True, exist_ok=True)
        img.resize((16, 16), Image.LANCZOS).save(percorso)
    return percorso.as_posix()


def _freccia(verso: str, colore: str) -> str:
    """Il triangolino delle tendine e dei contatori, come PNG.

    **Il trucco dei tre bordi CSS qui non funziona.** Su una pagina web un
    triangolo si fa con tre bordi e uno colorato; Qt accetta quelle proprieta'
    senza lamentarsi e disegna un quadratino — precisamente il tipo di difetto
    che non da' errore e si vede solo guardando.
    """
    percorso = _DISEGNI / f"freccia-{verso}-{colore.lstrip('#')}.png"
    if not percorso.exists():
        from PIL import Image, ImageDraw

        S, L = 4, 9
        img = Image.new("RGBA", (L * S, L * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        a, b, c = (L * S * 0.12, L * S * 0.5, L * S * 0.88)
        punti = {
            "giu": [(a, b - L * S * 0.16), (c, b - L * S * 0.16), (b, b + L * S * 0.28)],
            "su": [(a, b + L * S * 0.16), (c, b + L * S * 0.16), (b, b - L * S * 0.28)],
        }[verso]
        d.polygon(punti, fill=colore)
        percorso.parent.mkdir(parents=True, exist_ok=True)
        img.resize((L, L), Image.LANCZOS).save(percorso)
    return percorso.as_posix()


# ==================================================================== il logo =


def logo(rotto: bool = False, taglia: int = 64) -> Path:
    """Il file del personaggio, sereno o guasto, alla taglia chiesta.

    **Sono due stati dello stesso personaggio, non due disegni**, e sono
    ritagliati sull'**unione** dei due riquadri: scambiando il sereno con
    l'arrabbiato — che e' precisamente quello che la finestra fa quando la catena
    cade — il riquadro non si sposta e non cambia taglia. Due loghi ritagliati
    stretti ciascuno sul suo contenuto **saltano** al cambio, e un logo che
    saltella chiede attenzione mentre l'utente sta giocando.

    Quello arrabbiato **sta ancora parlando**: l'onda esce, storta e a fatica.
    Copre gli stati in cui la catena e' in avaria *ma il programma e' vivo*, e
    **non e' il logo dello stato spento** — a programma fermo il personaggio e'
    quello sereno, perche' fermo non e' rotto.
    """
    nome = "livedub-guasto" if rotto else "livedub"
    p = LOGHI / (f"{nome}-{taglia}.png" if taglia in (64, 256) else f"{nome}.png")
    return p if p.exists() else LOGHI / f"{nome}.png"


def icona() -> Path | None:
    """`livedub.ico` multi-risoluzione per la barra delle applicazioni.

    Serve un `.ico` e non un PNG grande: Windows non ridimensiona bene un PNG
    nella barra delle applicazioni. Si genera una volta dalle taglie che ci sono
    e resta sul disco — e se PIL non c'e', si torna `None` invece di sollevare,
    perche' una finestra senza icona funziona e una finestra che non si apre no.
    """
    percorso = LOGHI / "livedub.ico"
    if percorso.exists():
        return percorso
    sorgente = LOGHI / "livedub.png"
    if not sorgente.exists():
        return None
    try:
        from PIL import Image

        Image.open(sorgente).save(
            percorso, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
        return percorso
    except Exception:
        return None


# ========================================================== il foglio di stile =


def _luce(t: Tavolozza) -> str:
    """Una sola luce, sempre dall'alto — e sul tema chiaro diventa **ombra**.

    Copiare la luce dall'alto sul tema chiaro non da' errore e da' pannelli che
    sembrano ritagliati male.
    """
    if t.scuro:
        return f"border-top: 1px solid {rgba('#ffffff', 0.05)};"
    return f"border-bottom: 1px solid {rgba('#000000', 0.04)};"


def foglio(t: Tavolozza = SCURA) -> str:
    """Il foglio di stile della finestra intera, per la tavolozza data.

    **I bordi non sono contorni.** `bordo` sta a 1,3:1 e `bordo_forte` a 1,8:1
    sulla superficie che separano: sono **fili**, e vanno bene per dividere due
    zone. Qualunque cosa debba essere *percepita come un contorno* — il fuoco, un
    campo in errore, la riga scelta in un elenco — usa `accento` o `rosso`, che
    stanno sopra 5:1. Un contorno che porta un significato e non si vede e'
    peggio di nessun contorno.
    """
    # Il riempimento menta e' lo stesso nei due temi (si veda `MENTA`), ma il
    # **contorno** menta no: sul chiaro va scurito, se no e' un filo invisibile.
    menta_testo = t.accento
    # I quattro stati di una riga d'elenco vengono dalla tabella, non da qui: si
    # veda `stati_elenco` per il difetto che quella tabella e' venuta a chiudere.
    elenco = stati_elenco(t)
    return f"""
* {{
    font-family: "{UI}", "{UI_RIPIEGO}"; font-size: {C_TESTO}pt;
    color: {t.testo}; outline: none;
}}
QWidget {{ background: {t.fondo}; }}
QMainWindow {{ background: {t.fondo}; }}
/* **Le etichette sono trasparenti una volta sola, e non per discendenza.**
   Erano `#pannello QLabel` e `#gruppo QLabel`: due regole a **due componenti**
   (identificatore + tipo), che in Qt battono qualunque regola a un
   identificatore solo — quindi il numero del passo perdeva il suo fondo menta e
   restava scuro su scuro, cioe' invisibile, ogni volta che finiva dentro un
   contenitore chiamato per nome. Con una regola a un solo tipo, `#passo` e
   `#pillola QLabel` la battono entrambi e non c'e' piu' niente da ricordarsi. */
QLabel, QCheckBox {{ background: transparent; }}
/* La pagina di una scheda e' `superficie`, cosi' la linguetta scelta **si salda
   al corpo**: e' quello che la fa leggere come una scheda invece che come un
   bottone acceso sopra un pannello diverso. */
#scheda {{ background: {t.superficie}; }}
QToolTip {{
    background: {t.superficie}; color: {t.testo};
    border: 1px solid {t.bordo_forte}; border-radius: {R_CAMPO}px;
    padding: {S1}px {S2}px;
}}

/* ---- la colonna: testata, barra dei comandi, barra della misura ---- */
#testata {{ background: {t.superficie}; {_luce(t)} }}
#barra {{ background: {t.fondo}; }}
#misura {{ background: {t.superficie}; border-top: 1px solid {t.bordo}; }}
#filo {{ background: {t.bordo}; max-width: 1px; min-width: 1px; }}
#filoOrizzontale {{ background: {t.bordo}; max-height: 1px; min-height: 1px; }}

/* ---- i corpi, per nome ---- */
#nomeApp {{ font-size: {C_NOME}pt; font-weight: 600; }}
#tenue  {{ color: {t.testo_tenue}; font-size: {C_NOTA}pt; }}
#mono   {{ color: {t.testo_tenue}; font-size: {C_NOTA}pt; }}
#valore {{ color: {t.testo}; font-size: {C_TESTO}pt; }}
#valoreAmbra {{ color: {t.ambra}; font-size: {C_TESTO}pt; }}
#valoreRosso {{ color: {t.rosso}; font-size: {C_TESTO}pt; }}
#sezione {{ color: {t.testo_tenue}; font-size: {C_TITOLO}pt; font-weight: 600;
            letter-spacing: 0.6px; }}
#nomeCampo {{ font-size: {C_NOTA}pt; color: {t.testo_tenue}; }}
#etichettaCampo {{ font-size: {C_TESTO}pt; }}
#titoloPasso {{ font-size: {C_TITOLO}pt; font-weight: 600; }}
#titoloPassoSpento {{ font-size: {C_TITOLO}pt; font-weight: 600;
                      color: {t.testo_tenue}; }}
#avviso {{ color: {t.ambra}; font-size: {C_NOTA}pt; }}
#spento {{ color: {t.testo_fioco}; font-size: {C_NOTA}pt; }}
#errore {{ color: {t.rosso}; font-size: {C_NOTA}pt; }}
#descrizione {{ color: {t.testo_tenue}; font-size: {C_NOTA}pt; }}
#vuoto {{ color: {t.testo_fioco}; font-size: {C_TESTO}pt; }}

/* ---- il logo in testata: **senza tessera dietro** ----
   Era 40x40 su un fondo `superficie_alta` con raggio 8: due angoli stondati uno
   dentro l'altro, e il quadratino faceva sembrare il personaggio piu' piccolo di
   quello che e'. Il logo ha gia' la sua sagoma, e il fondo tolto e' stato fatto
   apposta perche' stia su qualunque superficie. */
#logo {{ background: transparent; border: none; }}

/* ---- i bottoni: **uno solo e' quello che si preme, e si vede** ---- */
QPushButton {{
    background: {t.superficie_alta}; border: 1px solid {t.bordo_forte};
    border-radius: {R_BOTTONE}px; padding: {S2}px {S4}px; color: {t.testo};
}}
QPushButton:hover  {{ border: 1px solid {menta_testo}; }}
QPushButton:pressed {{ background: {t.accento_scuro}; color: {t.su_accento};
                       border: 1px solid {t.accento_scuro}; }}
QPushButton:focus {{ border: 2px solid {menta_testo};
                     padding: {S2 - 1}px {S4 - 1}px; }}
/* Un bottone spento e' `superficie` con testo `testo_fioco`: scompare senza
   sparire, cioe' resta leggibile che c'e' e non si puo' premere. */
QPushButton:disabled {{ background: {t.superficie}; color: {t.testo_fioco};
                        border: 1px solid {t.bordo}; }}
QPushButton#primario {{
    background: {MENTA}; color: {t.su_accento}; font-weight: 600;
    border: 1px solid {MENTA}; padding: {S2}px {S5}px;
}}
QPushButton#primario:hover {{ background: {t.accento_chiaro if t.scuro else MENTA};
                              border: 1px solid {menta_testo}; }}
QPushButton#primario:pressed {{ background: {t.accento_scuro}; }}
QPushButton#primario:disabled {{ background: {t.superficie}; color: {t.testo_fioco};
                                 border: 1px solid {t.bordo}; }}
/* Contornato e non riempito: il riempimento menta e' di Avvia, e due
   riempimenti menta che fanno cose diverse sono un riempimento di troppo. */
QPushButton#accento {{
    background: transparent; color: {menta_testo}; font-weight: 600;
    border: 1px solid {menta_testo};
}}
QPushButton#accento:hover {{ background: {rgba(MENTA, 0.12)}; }}
QPushButton#aiuto {{
    background: transparent; color: {menta_testo}; border: none;
    border-radius: {R_AIUTO}px; padding: 0px;
    min-width: {LATO_AIUTO}px; max-width: {LATO_AIUTO}px;
    min-height: {LATO_AIUTO}px; max-height: {LATO_AIUTO}px; font-size: {C_TITOLO}pt;
}}
QPushButton#aiuto:hover {{ background: {t.superficie_alta}; }}

/* ---- i campi ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {t.superficie_alta}; border: 1px solid {t.bordo_forte};
    border-radius: {R_CAMPO}px; padding: {S1}px {S2}px;
    selection-background-color: {MENTA}; selection-color: {t.su_accento};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 2px solid {menta_testo}; padding: {S1 - 1}px {S2 - 1}px;
}}
QLineEdit:disabled, QComboBox:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background: {t.superficie}; color: {t.testo_fioco}; border: 1px solid {t.bordo};
}}
QSpinBox, QDoubleSpinBox {{ padding-right: 20px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent; border: none; width: 16px; margin-right: 3px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{_freccia('su', t.testo_tenue)}"); width: 9px; height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{_freccia('giu', t.testo_tenue)}"); width: 9px; height: 9px;
}}
QSpinBox::up-arrow:hover {{ image: url("{_freccia('su', menta_testo)}"); }}
QSpinBox::down-arrow:hover {{ image: url("{_freccia('giu', menta_testo)}"); }}
/* **`combobox-popup: 0` e' la riga che fa vedere le voci.** Con un foglio di
   stile addosso Qt smette di aprire la tendina come tendina e la apre come un
   *menu*: mostra tutte le voci qualunque siano — quarantatre lingue fanno 1093
   px — le impagina a cavallo del controllo e le incastra nel rettangolo dello
   **schermo**, non in quello utile. Misurato con la finestra appoggiata in
   basso: `tts.backend` ha cinque voci e se ne vedevano **tre**, le altre due
   sotto la barra delle applicazioni. Da li' «il motore TTS ha tre voci».
   In quel modo `setMaxVisibleItems` non lo guarda nessuno (Qt lo dichiara: e'
   ignorato per le tendine non scrivibili quando lo stile chiede il menu), ed
   e' il motivo per cui `translate.target` — che e' scrivibile — si comportava
   bene mentre le altre no: due comportamenti diversi per caso, non per regola.
   Con questa riga la tendina torna a cadere sotto il controllo, a stare nello
   spazio utile e a fermarsi a `VOCI_TENDINA`. */
QComboBox {{ combobox-popup: 0; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: url("{_freccia('giu', t.testo_tenue)}"); width: 9px; height: 9px;
    margin-right: {S2}px;
}}
QComboBox::down-arrow:hover {{ image: url("{_freccia('giu', menta_testo)}"); }}
QComboBox QAbstractItemView {{
    background: {t.superficie_alta}; border: 1px solid {t.bordo_forte};
    border-radius: {R_CAMPO}px;
    selection-background-color: {MENTA}; selection-color: {t.su_accento};
    padding: {S1}px;
}}

QCheckBox {{ spacing: {S2}px; background: transparent; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: {R_MARCA}px;
    background: {t.superficie_alta}; border: 1px solid {t.bordo_forte};
}}
QCheckBox::indicator:hover {{ border: 1px solid {menta_testo}; }}
QCheckBox::indicator:checked {{
    background: {MENTA}; border: 1px solid {MENTA};
    image: url("{_baffo(t.su_accento)}");
}}
QCheckBox::indicator:disabled {{ background: {t.superficie};
                                 border: 1px solid {t.bordo}; }}
QCheckBox:disabled {{ color: {t.testo_fioco}; }}

/* ---- le linguette: h40, angoli alti a 8, 2 px di menta sotto quella scelta -- */
QTabWidget::pane {{ background: {t.superficie}; border: none;
                    border-top-left-radius: 0px; border-radius: {R_LINGUETTA}px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: {t.fondo}; color: {t.testo_tenue};
    padding: {S2}px {S5}px; margin-right: {S1}px;
    min-height: {H_LINGUETTE - 2 * S2}px;
    border-top-left-radius: {R_LINGUETTA}px;
    border-top-right-radius: {R_LINGUETTA}px;
}}
QTabBar::tab:hover {{ color: {t.testo}; }}
QTabBar::tab:selected {{ background: {t.superficie}; color: {t.testo};
                         border-bottom: 2px solid {MENTA}; }}
QTabBar::tab:disabled {{ color: {t.testo_fioco}; }}

/* ---- il log e gli elenchi, in monospazio ---- */
QPlainTextEdit, QTextEdit, QListWidget {{
    background: {t.superficie}; border: none; border-radius: {R_TESSERA}px;
    padding: {S3}px;
    selection-background-color: {MENTA}; selection-color: {t.su_accento};
}}
/* **I quattro stati di una riga d'elenco escono dalla tabella**, e l'ordine non
   e' estetico: `:selected:hover` ha due pseudo-stati, quindi batte gli altri
   due — che fra loro hanno la stessa specificita' e si risolvono per ordine.
   Era proprio quello il difetto: `:hover` scritto dopo `:selected` gli portava
   via il fondo menta e gli lasciava il testo fatto per la menta, 1,12:1. */
QListWidget::item {{ padding: {S1}px {S2}px; border-radius: {R_CAMPO}px;
                     color: {elenco['normale'][1]}; }}
QListWidget::item:hover {{ background: {elenco['sotto il mouse'][0]};
                           color: {elenco['sotto il mouse'][1]}; }}
QListWidget::item:selected {{ background: {elenco['scelta'][0]};
                              color: {elenco['scelta'][1]}; }}
QListWidget::item:selected:hover {{ background: {elenco['scelta sotto il mouse'][0]};
                                    color: {elenco['scelta sotto il mouse'][1]}; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: {S1}px {S0}px; }}
QScrollBar::handle:vertical {{ background: {t.bordo_forte}; border-radius: {R_MARCA}px;
                               min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {t.testo_fioco}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: {S0}px {S1}px; }}
QScrollBar::handle:horizontal {{ background: {t.bordo_forte}; border-radius: {R_MARCA}px;
                                 min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; width: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ border: none; background: {t.superficie}; }}
QScrollArea > QWidget > QWidget {{ background: {t.superficie}; }}

/* ---- pannelli e tessere: fondo `superficie` piu' una sola luce dall'alto --- */
#pannello {{ background: {t.superficie}; border-radius: {R_PANNELLO}px; {_luce(t)} }}
#gruppo {{ background: transparent; }}
#passo {{
    background: {MENTA}; color: {t.su_accento}; font-weight: 600;
    border-radius: {R_PILLOLA}px;
    min-width: {H_PILLOLA}px; max-width: {H_PILLOLA}px;
    min-height: {H_PILLOLA}px; max-height: {H_PILLOLA}px;
    qproperty-alignment: AlignCenter;
}}
#passoSpento {{
    background: {t.superficie_alta}; color: {t.testo_fioco}; font-weight: 600;
    border: 1px solid {t.bordo_forte}; border-radius: {R_PILLOLA}px;
    min-width: {H_PILLOLA}px; max-width: {H_PILLOLA}px;
    min-height: {H_PILLOLA}px; max-height: {H_PILLOLA}px;
    qproperty-alignment: AlignCenter;
}}
/* **La striscia: l'unico bordo colorato asimmetrico della finestra.** E' il
   segno che l'occhio legge come «questo blocco e' una cosa a parte» senza
   doverlo riquadrare. Ambra e non rosso, perche' non e' rotto niente: e' una
   cosa che aspetta. */
#striscia {{ background: {t.superficie_alta}; border-radius: {R_TESSERA}px;
             border-left: 3px solid {t.ambra}; }}
#striscia QLabel {{ color: {t.testo}; }}
/* La tessera del guasto: **dentro ci sta il bottone**, perche' un errore deve
   dire cosa fare e il comando che nomina dev'essere premibile. */
#tessera {{ background: {t.superficie_alta}; border-radius: {R_TESSERA}px;
            border-left: 3px solid {t.rosso}; }}
#tessera QLabel {{ color: {t.testo}; }}
#tesseraTitolo {{ font-size: {C_TITOLO}pt; font-weight: 600; }}
#tesseraMono {{ font-size: {C_NOTA}pt; color: {t.testo_tenue}; }}

/* ---- la scheda Sessione: **cosa sta succedendo adesso**, non cosa e' successo -
   Le tessere stanno su `superficie` come `#pannello`, e non su `superficie_alta`
   che sarebbe l'ovvio: dentro ci va la **sigla nel colore del personaggio**, e i
   sei colori delle voci sono tarati sulla superficie. Misurato: sul tema chiaro
   passano da 5,02:1 su `superficie` a **4,28:1** su `superficie_alta`, cioe'
   sotto la soglia. Una tessera piu' staccata sarebbe costata l'unica
   informazione che quella tessera porta. */
/* **Un filo e non una luce.** Le tessere di questa scheda stanno su `superficie`
   e la pagina e' `superficie`: la sola luce dall'alto di `#pannello` li' non si
   vede affatto — guardato a schermo, la tessera della battuta si leggeva come
   del testo sciolto in cima alla pagina. Un filo da 1 px la chiude senza
   cambiarle il fondo, che e' l'unica cosa che non si puo' toccare. */
#ora {{ background: {t.superficie}; border: 1px solid {t.bordo};
        border-radius: {R_TESSERA}px; }}
#registro {{ border: 1px solid {t.bordo}; }}
#fase {{ font-size: {C_TITOLO}pt; font-weight: 600; }}
#oraTesto {{ font-size: {C_STATO}pt; }}
#oraVuoto {{ font-size: {C_STATO}pt; color: {t.testo_fioco}; }}
/* La tessera di un personaggio e' un **filo**, non un riempimento: il colore che
   dice chi e' sta nella sigla, e riempirla o contornarla della sua tinta
   userebbe per le voci il canale che appartiene a menta, ambra e rosso. */
#personaggio {{ background: transparent; border: 1px solid {t.bordo};
                border-radius: {R_CAMPO}px; }}
#conta {{ color: {t.testo_tenue}; font-size: {C_NOTA}pt; }}

/* Il bordo sinistro trasparente che diventa menta sotto il mouse: si accende
   senza spostare niente, ed e' per questo che e' trasparente invece di assente. */
#riga {{ border-radius: {R_CAMPO}px; border-left: 2px solid transparent; }}
#riga:hover {{ border-left: 2px solid {MENTA}; }}

/* **La maniglia veniva tagliata**, e non era il raggio: era l'altezza. Un
   `QSlider` in una riga alta quanto il testo ha una decina di pixel utili, la
   maniglia ne chiedeva 14 e il margine negativo la spingeva fuori dal widget —
   quindi sopra e sotto le si mangiava una fetta. Adesso il cursore dichiara
   l'altezza che gli serve e la maniglia ci sta dentro intera. */
QSlider:horizontal {{ min-height: {LATO_MANIGLIA + 2 * S1}px; background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {t.superficie_alta};
                              border-radius: {S0}px; }}
QSlider::sub-page:horizontal {{ background: {MENTA}; border-radius: {S0}px; }}
QSlider::handle:horizontal {{
    background: {t.testo}; width: {LATO_MANIGLIA}px; height: {LATO_MANIGLIA}px;
    margin: -{(LATO_MANIGLIA - 4) // 2}px 0; border-radius: {R_MANIGLIA}px;
}}
QSlider::handle:horizontal:hover {{ background: {menta_testo}; }}

QDialog {{ background: {t.superficie}; }}
"""


def carattere_log():
    """Il carattere del log: quello dell'interfaccia, con le **cifre tabulari**.

    Il log era in monospazio, e non per vezzo: ora, sigla, voce e latenza erano
    colonne, e in proporzionale non si incolonnano. Ma un registro in Cascadia
    Mono in mezzo a una finestra fa sembrare tutto un terminale, ed e' l'unica
    cosa che si legge per lungo tempo — quindi e' proprio quella che vuole un
    carattere da leggere.

    La via d'uscita e' che **solo i numeri hanno bisogno di incolonnarsi**: le
    cifre tabulari (`tnum`) hanno tutte la stessa larghezza anche in un
    proporzionale, quindi `12.4s` e `120.0s` restano allineati. Il resto —
    sigla, voce, testo — si separa con dei punti invece che con degli spazi di
    riempimento, e non chiede niente al carattere.

    `setFeature` c'e' da Qt 6.7; dove non c'e', si torna al comportamento di
    prima invece di sollevare — al peggio le cifre ballano di un pixel.
    """
    from PySide6.QtGui import QFont

    f = QFont(UI, C_TESTO)
    f.setStyleHint(QFont.SansSerif)
    try:
        f.setFeature(QFont.Tag("tnum"), 1)
    except Exception:
        pass
    return f


def spia(colore: str) -> str:
    """La spia di stato: un cerchio da 10 px, raggio = meta' del lato."""
    return (
        f"background: {colore}; border: none; border-radius: {R_SPIA}px;"
        f" min-width: {LATO_SPIA}px; max-width: {LATO_SPIA}px;"
        f" min-height: {LATO_SPIA}px; max-height: {LATO_SPIA}px;"
    )


def pillola(colore: str) -> str:
    """La pillola di stato: fondo al 12% del colore, testo e spia pieni.

    Sostituisce il pallino piu' l'etichetta. Un pallino da 12 px isolato in una
    testata larga 1280 e' un dettaglio che nessuno guarda; una pillola colorata
    la si vede con la coda dell'occhio, che e' l'unico modo in cui la si
    guardera' mentre si gioca.
    """
    return (
        f"#pillola {{ background: {rgba(colore, 0.12)};"
        f" border-radius: {R_PILLOLA}px;"
        f" min-height: {H_PILLOLA}px; max-height: {H_PILLOLA}px; }}"
        f"#pillola QLabel {{ background: transparent; color: {colore};"
        f" font-size: {C_STATO}pt; font-weight: 600; }}"
    )


def alone(widget, colore: str | None) -> None:
    """L'alone menta sulla spia — **e su nient'altro**.

    E' l'elemento piu' facile da abusare di tutto il disegno: fa sembrare tutto
    piu' bello, e un bagliore su ogni cosa non vuol dire piu' niente. Uno solo, e
    vuol dire «sta parlando adesso». `colore=None` lo toglie.
    """
    try:
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
    except Exception:
        return
    if colore is None:
        widget.setGraphicsEffect(None)
        return
    effetto = QGraphicsDropShadowEffect(widget)
    effetto.setBlurRadius(12)
    effetto.setOffset(0, 0)
    c = QColor(colore)
    c.setAlphaF(0.35)
    effetto.setColor(c)
    widget.setGraphicsEffect(effetto)
