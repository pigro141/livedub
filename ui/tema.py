"""Il tema della finestra: un solo posto dove stanno colori, spazi e caratteri.

**Perche' un file e non degli attributi sparsi.** Finora la finestra era mezza
chiara e mezza scura: i bottoni col grigio di Windows, il log nero. Non e' brutto
per gusto — e' brutto perche' due meta' della stessa finestra dicono che nessuno
l'ha guardata intera. E qui la cosa costa piu' che altrove: questa finestra sta
**sopra un gioco**, spesso di notte, e il grigio chiaro di sistema in mezzo a una
scena scura e' una lampada in faccia.

**Perche' scuro.** Non e' una moda: e' l'unico fondo che non lampeggia quando la
finestra passa davanti al gioco, ed e' quello su cui i sei colori dei personaggi
— che sono l'informazione principale del log — restano distinguibili. Su fondo
bianco l'arancione e il giallo delle due voci si confondono.

**Come si applica.** ttk lavora a stili nominati, quindi qui si configurano una
volta e i widget li chiedono per nome. I widget classici di Tk (`Listbox`,
`Canvas`, `Text`) non passano da ttk e vanno colorati a mano: per quelli ci sono
le costanti.

**Il carattere.** Segoe UI per l'interfaccia, Consolas per tutto cio' che e'
misura o testo letto dall'OCR. Non e' estetica: un numero in proporzionale non si
incolonna, e questa finestra e' piena di numeri che si confrontano fra loro.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# -- la tavolozza -------------------------------------------------------------
# Tre fondi e non uno: la profondita' e' l'unico modo di raggruppare senza
# disegnare bordi dappertutto, e i bordi su schermo piccolo diventano rumore.
FONDO = "#14161c"  # la finestra
PANNELLO = "#1b1e26"  # le zone di contenuto
CAMPO = "#232732"  # le caselle su cui si scrive
BORDO = "#2f3542"

TESTO = "#e6e8ee"
TESTO_TENUE = "#8b93a7"  # le spiegazioni accanto alle manopole
TESTO_FIOCO = "#616b82"

ACCENTO = "#4c9aff"  # ci si clicca
ACCENTO_SCURO = "#3d7fd6"
VERDE = "#43b581"  # va tutto bene, oppure: Avvia
AMBRA = "#e8a33d"  # serve un riavvio perche' faccia effetto
ROSSO = "#e5534b"  # rifiutato

# I colori dei personaggi nel log. Sei, come le voci del pool, e scelti per
# restare distinguibili **fra loro** su questo fondo: la domanda che ci si fa
# guardando il log non e' "cosa ha detto" ma "e' sempre lo stesso a parlare?".
VOCI = ("#7ee787", "#79c0ff", "#ffa657", "#d2a8ff", "#ff7b72", "#f2cc60")

# -- i caratteri --------------------------------------------------------------
UI = ("Segoe UI", 10)
UI_PICCOLO = ("Segoe UI", 9)
UI_TITOLO = ("Segoe UI Semibold", 11)
UI_TESTATA = ("Segoe UI Semibold", 14)
MONO = ("Consolas", 10)
MONO_PICCOLO = ("Consolas", 9)


# -- gli angoli stondati -------------------------------------------------------
#
# **Tkinter non ha angoli stondati, e non e' una limitazione da aggirare a
# meta'.** Un widget ttk si disegna con degli *elementi*, e un elemento puo'
# essere un'immagine tagliata a **nove fette**: i quattro angoli restano fissi, i
# quattro lati e il centro si stirano. Quindi si genera una volta la pillola con
# gli angoli tondi e ttk la ridimensiona da sola per ogni bottone, campo e
# linguetta, a qualunque larghezza.
#
# Le immagini si disegnano a **quattro volte** la misura e si rimpiccioliscono:
# PIL non antialiasa gli archi, e un angolo tondo a scalini si vede piu' di un
# angolo quadrato. Costa qualche millisecondo all'avvio e una decina di immagini
# in memoria.
#
# **Le immagini vanno tenute vive.** Tk non possiede le `PhotoImage`: se il
# riferimento Python muore, il garbage collector le libera e i widget si
# disegnano vuoti — un difetto che sembra un problema di stile e non lo e'. Per
# questo `_VIVE`.
_VIVE: list = []
_RAGGIO = 7  # angolo dei bottoni e dei campi, in pixel
_SCALA = 4  # quanto si disegna piu' grande, prima di rimpicciolire


def _pillola(w: int, h: int, riempimento: str, bordo: str | None = None,
             raggio: int = _RAGGIO, solo_sopra: bool = False):
    """Un rettangolo con gli angoli tondi, come immagine per un elemento ttk."""
    from PIL import Image, ImageDraw, ImageTk

    S = _SCALA
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = raggio * S
    box = (0, 0, w * S - 1, h * S - 1)
    d.rounded_rectangle(box, radius=r, fill=riempimento,
                        outline=bordo, width=S if bordo else 0)
    if solo_sopra:
        # Le linguette del blocco schede sono tonde sopra e diritte sotto, se no
        # sembrano staccate dal pannello che aprono.
        d.rectangle((0, h * S - r, w * S - 1, h * S - 1), fill=riempimento)
        if bordo:
            d.line((0, h * S - r, 0, h * S - 1), fill=bordo, width=S)
            d.line((w * S - 1, h * S - r, w * S - 1, h * S - 1), fill=bordo, width=S)
    foto = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))
    _VIVE.append(foto)
    return foto


def _spunta(lato: int, fondo: str, segno: str | None, bordo: str | None = None,
            gap: int = 8):
    """La casella di spunta: quadrato stondato, col baffo dentro se e' accesa.

    **Il vuoto fra la casella e la scritta e' disegnato dentro l'immagine.** Il
    `padding` di un elemento ttk registrato come immagine viene ignorato in
    parte, e la prima versione aveva l'etichetta appiccicata al quadratino.
    Facendo l'immagine piu' larga di quanto sia il quadrato, lo spazio non
    dipende piu' da come ttk decide di distribuire i margini.
    """
    from PIL import Image, ImageDraw, ImageTk

    S = _SCALA
    img = Image.new("RGBA", ((lato + gap) * S, lato * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, lato * S - 1, lato * S - 1), radius=4 * S,
                        fill=fondo, outline=bordo, width=S if bordo else 0)
    if segno:
        L = lato * S
        d.line([(L * 0.26, L * 0.52), (L * 0.44, L * 0.70), (L * 0.76, L * 0.30)],
               fill=segno, width=int(S * 1.8), joint="curve")
    foto = ImageTk.PhotoImage(img.resize((lato + gap, lato), Image.LANCZOS))
    _VIVE.append(foto)
    return foto


def _radice(stile: ttk.Style, widget: str, elemento: str) -> None:
    """Cambia **solo** il pezzo che disegna il bordo, lasciando il resto com'e'.

    E' la differenza fra stondare un widget e riscriverlo. La prima versione
    ricostruiva a mano l'albero di ogni widget, e il contatore della soglia ne e'
    uscito col numero schiacciato e le frecce sovrapposte: quell'albero ha
    dentro dettagli (dove vanno le frecce, quanto si allarga la casella) che non
    c'entrano niente con gli angoli. Qui si prende il layout vero e si sostituisce
    la **radice**, che e' l'unica cosa che disegna il rettangolo squadrato.
    """
    try:
        vecchio = stile.layout(widget)
    except tk.TclError:
        return
    if not vecchio:
        return
    _, opzioni = vecchio[0]
    stile.layout(widget, [(elemento, opzioni)])


def _stonda(stile: ttk.Style) -> None:
    """Sostituisce i bordi squadrati di `clam` con le pillole.

    **Due strade, e servono tutte e due.** Per i bottoni si riscrive il layout
    per intero: il loro albero e' tre nodi e si conosce. Per i campi si
    sostituisce **solo la radice** lasciando dentro quello che c'e' — l'albero di
    un menu a tendina o di un contatore ha dettagli (dove va la freccia, quanto
    si allarga la casella) che non c'entrano niente con gli angoli, e
    riscriverli a mano ha prodotto un contatore col numero schiacciato.

    E il contrario e' altrettanto vero: sostituendo la radice di un **bottone**
    sparisce la scritta. Sono due difetti opposti, visti tutti e due a schermo,
    ed e' il motivo per cui qui non c'e' una regola sola.
    """

    def elemento(nome: str, *stati, **kw) -> bool:
        try:
            stile.element_create(nome, "image", *stati,
                                 border=kw.pop("border", _RAGGIO + 2),
                                 sticky=kw.pop("sticky", "nsew"), **kw)
            return True
        except tk.TclError:
            return False  # gia' registrato: la finestra e' stata aperta due volte

    # -- bottoni: layout riscritto, perche' la scritta va tenuta ---------------
    for nome, widget, colore, sopra in (
        ("Piatto", "TButton", CAMPO, BORDO),
        ("Verde", "Primario.TButton", VERDE, "#4fc994"),
        ("Blu", "Accento.TButton", ACCENTO, ACCENTO_SCURO),
        ("Aiutino", "Aiuto.TButton", PANNELLO, CAMPO),
    ):
        if elemento(
            f"{nome}.bottone",
            _pillola(60, 34, colore),
            ("disabled", _pillola(60, 34, PANNELLO)),
            ("pressed", _pillola(60, 34, sopra)),
            ("active", _pillola(60, 34, sopra)),
        ):
            stile.layout(widget, [(f"{nome}.bottone", {"sticky": "nsew", "children": [
                ("Button.padding", {"sticky": "nsew", "children": [
                    ("Button.label", {"sticky": "nsew"})]})]})])

    # -- campi: solo la radice, il dentro resta quello di clam -----------------
    if elemento("campo.sfondo",
                _pillola(60, 30, CAMPO),
                ("disabled", _pillola(60, 30, PANNELLO)),
                ("focus", _pillola(60, 30, CAMPO, ACCENTO))):
        _radice(stile, "TEntry", "campo.sfondo")
        _radice(stile, "TSpinbox", "campo.sfondo")
    # Il menu a tendina ha la freccia dentro la radice: sostituendola sparisce.
    # Si riscrive quindi con la freccia dichiarata, che e' l'unico pezzo che
    # serve sapere.
    if elemento("tendina.sfondo",
                _pillola(60, 30, CAMPO),
                ("disabled", _pillola(60, 30, PANNELLO)),
                ("focus", _pillola(60, 30, CAMPO, ACCENTO))):
        stile.layout("TCombobox", [("tendina.sfondo", {"sticky": "nsew", "children": [
            ("Combobox.padding", {"sticky": "nsew", "children": [
                ("Combobox.downarrow", {"side": "right", "sticky": "ns"}),
                ("Combobox.textarea", {"sticky": "nsew"})]})]})])

    # -- le linguette delle schede --------------------------------------------
    if elemento("scheda.sfondo",
                _pillola(60, 34, FONDO, solo_sopra=True),
                ("selected", _pillola(60, 34, PANNELLO, solo_sopra=True))):
        stile.layout("TNotebook.Tab", [("scheda.sfondo", {"sticky": "nsew", "children": [
            ("Notebook.padding", {"side": "top", "sticky": "nsew", "children": [
                ("Notebook.label", {"side": "top", "sticky": ""})]})]})])

    # -- la casella di spunta --------------------------------------------------
    if elemento("spunta.indicatore",
                _spunta(16, CAMPO, None, BORDO),
                ("selected", _spunta(16, ACCENTO, "#0d1117")),
                ("active", "!selected", _spunta(16, BORDO, None, ACCENTO)),
                border=0, sticky=""):
        for nome in ("TCheckbutton", "Pannello.TCheckbutton"):
            stile.layout(nome, [("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("spunta.indicatore", {"side": "left", "sticky": ""}),
                ("Checkbutton.label", {"side": "left", "sticky": "nswe"})]})])

    # -- la barra di scorrimento, sottile e stondata --------------------------
    if elemento("barra.cursore",
                _pillola(12, 40, BORDO, raggio=5),
                ("pressed", _pillola(12, 40, ACCENTO, raggio=5)),
                ("active", _pillola(12, 40, TESTO_FIOCO, raggio=5)),
                border=6, sticky="ns"):
        stile.layout("Vertical.TScrollbar",
                     [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                         ("barra.cursore", {"sticky": "ns"})]})])
        stile.configure("Vertical.TScrollbar", troughcolor=FONDO, borderwidth=0, width=12)


def applica(root: tk.Misc) -> ttk.Style:
    """Configura gli stili ttk e il fondo della finestra. Si chiama una volta."""
    stile = ttk.Style(root)
    # `clam` e' l'unico tema ttk di serie che lascia cambiare davvero i colori:
    # con `vista` e `xpnative` i bottoni restano quelli di Windows qualunque cosa
    # gli si dica, e meta' finestra resterebbe chiara.
    stile.theme_use("clam")
    root.configure(bg=FONDO)

    stile.configure(".", background=FONDO, foreground=TESTO, font=UI,
                    fieldbackground=CAMPO, bordercolor=BORDO, focuscolor=ACCENTO)
    stile.configure("TFrame", background=FONDO)
    stile.configure("Pannello.TFrame", background=PANNELLO)
    stile.configure("Testata.TFrame", background=PANNELLO)

    stile.configure("TLabel", background=FONDO, foreground=TESTO)
    stile.configure("Pannello.TLabel", background=PANNELLO, foreground=TESTO)
    stile.configure("Tenue.TLabel", background=FONDO, foreground=TESTO_TENUE, font=UI_PICCOLO)
    stile.configure("TenueP.TLabel", background=PANNELLO, foreground=TESTO_TENUE, font=UI_PICCOLO)
    stile.configure("Titolo.TLabel", background=FONDO, foreground=TESTO, font=UI_TITOLO)
    stile.configure("Testata.TLabel", background=PANNELLO, foreground=TESTO, font=UI_TESTATA)
    stile.configure("Mono.TLabel", background=FONDO, foreground=TESTO_TENUE, font=MONO_PICCOLO)

    # I bottoni: uno solo e' quello che si preme (Avvia), gli altri no. Se sono
    # tutti uguali, l'occhio deve leggerli tutti per trovarlo.
    stile.configure("TButton", background=CAMPO, foreground=TESTO, borderwidth=0,
                    focusthickness=0, padding=(14, 7), font=UI)
    stile.map("TButton",
              background=[("active", BORDO), ("disabled", PANNELLO)],
              foreground=[("disabled", TESTO_FIOCO)])
    stile.configure("Primario.TButton", background=VERDE, foreground="#0d1117",
                    font=("Segoe UI Semibold", 10), padding=(20, 7))
    stile.map("Primario.TButton",
              background=[("active", "#4fc994"), ("disabled", PANNELLO)],
              foreground=[("disabled", TESTO_FIOCO)])
    stile.configure("Accento.TButton", background=ACCENTO, foreground="#0d1117",
                    font=("Segoe UI Semibold", 10), padding=(16, 7))
    stile.map("Accento.TButton", background=[("active", ACCENTO_SCURO)])
    # Il bottoncino dell'aiuto: tondo non si puo', ma piccolo e discreto si'.
    stile.configure("Aiuto.TButton", background=PANNELLO, foreground=ACCENTO,
                    borderwidth=0, padding=(4, 2), font=("Segoe UI", 10))
    stile.map("Aiuto.TButton", background=[("active", CAMPO)])

    # **La casella di spunta va disegnata a mano.** Con `clam` l'indicatore
    # prende i colori da `indicatorbackground`/`indicatorforeground` e non da
    # `indicatorcolor`: lasciandolo al default veniva un quadrato nero pieno su
    # fondo scuro, cioe' una casella di cui non si capisce se e' spuntata. E'
    # esattamente il tipo di difetto che si vede solo guardando la finestra.
    for nome, fondo in (("TCheckbutton", FONDO), ("Pannello.TCheckbutton", PANNELLO)):
        stile.configure(nome, background=fondo, foreground=TESTO, font=UI,
                        focusthickness=0, borderwidth=0,
                        indicatorbackground=CAMPO, indicatorforeground=ACCENTO,
                        indicatormargin=(0, 0, 8, 0), padding=(2, 3))
        stile.map(nome,
                  background=[("active", fondo)],
                  indicatorbackground=[("selected", ACCENTO), ("active", BORDO)],
                  indicatorforeground=[("selected", "#0d1117")])

    stile.configure("TEntry", fieldbackground=CAMPO, foreground=TESTO,
                    insertcolor=TESTO, borderwidth=0, padding=(8, 6))
    stile.map("TEntry", fieldbackground=[("disabled", PANNELLO)],
              foreground=[("disabled", TESTO_FIOCO)])
    stile.configure("TSpinbox", fieldbackground=CAMPO, foreground=TESTO,
                    background=CAMPO, arrowcolor=TESTO_TENUE, borderwidth=0, padding=(8, 5))
    stile.configure("TCombobox", fieldbackground=CAMPO, background=CAMPO,
                    foreground=TESTO, arrowcolor=TESTO_TENUE, borderwidth=0, padding=(8, 5))
    stile.map("TCombobox", fieldbackground=[("readonly", CAMPO)],
              selectbackground=[("readonly", CAMPO)],
              selectforeground=[("readonly", TESTO)])
    # La tendina aperta e' una Listbox di Tk, non un widget ttk: si colora da qui,
    # se no si apre bianca sopra una finestra scura.
    root.option_add("*TCombobox*Listbox.background", CAMPO)
    root.option_add("*TCombobox*Listbox.foreground", TESTO)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENTO)
    root.option_add("*TCombobox*Listbox.selectForeground", "#0d1117")

    stile.configure("TNotebook", background=FONDO, borderwidth=0, tabmargins=(2, 4, 2, 0))
    stile.configure("TNotebook.Tab", background=FONDO, foreground=TESTO_TENUE,
                    padding=(20, 9), borderwidth=0, font=UI)
    stile.map("TNotebook.Tab",
              background=[("selected", PANNELLO)],
              foreground=[("selected", TESTO)],
              expand=[("selected", (0, 0, 0, 0))])

    stile.configure("Vertical.TScrollbar", background=CAMPO, troughcolor=FONDO,
                    borderwidth=0, arrowcolor=TESTO_FIOCO)
    stile.map("Vertical.TScrollbar", background=[("active", BORDO)])
    stile.configure("TSeparator", background=BORDO)
    stile.configure("Orizzontale.TScale", background=PANNELLO, troughcolor=CAMPO)

    # Per ultimo, perche' riscrive i layout costruiti sopra.
    _stonda(stile)
    return stile


def pallino(canvas: tk.Canvas, colore: str) -> None:
    """Il pallino di stato: fermo, in ascolto, guasto.

    Un colore dice lo stato prima di qualunque parola, e questa finestra viene
    guardata di sfuggita mentre si gioca — che e' esattamente la condizione in
    cui una parola non si legge.
    """
    canvas.delete("all")
    canvas.create_oval(3, 3, 13, 13, fill=colore, outline="")
