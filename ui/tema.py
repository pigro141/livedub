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
                    focusthickness=0, padding=(12, 6), font=UI)
    stile.map("TButton",
              background=[("active", BORDO), ("disabled", PANNELLO)],
              foreground=[("disabled", TESTO_FIOCO)])
    stile.configure("Primario.TButton", background=VERDE, foreground="#0d1117",
                    font=("Segoe UI Semibold", 10), padding=(18, 6))
    stile.map("Primario.TButton",
              background=[("active", "#4fc994"), ("disabled", PANNELLO)],
              foreground=[("disabled", TESTO_FIOCO)])
    stile.configure("Accento.TButton", background=ACCENTO, foreground="#0d1117",
                    font=("Segoe UI Semibold", 10), padding=(14, 6))
    stile.map("Accento.TButton", background=[("active", ACCENTO_SCURO)])
    # Il bottoncino dell'aiuto: tondo non si puo', ma piccolo e discreto si'.
    stile.configure("Aiuto.TButton", background=PANNELLO, foreground=ACCENTO,
                    borderwidth=0, padding=(2, 0), font=("Segoe UI", 10))
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
                    insertcolor=TESTO, borderwidth=0, padding=5)
    stile.map("TEntry", fieldbackground=[("disabled", PANNELLO)],
              foreground=[("disabled", TESTO_FIOCO)])
    stile.configure("TSpinbox", fieldbackground=CAMPO, foreground=TESTO,
                    background=CAMPO, arrowcolor=TESTO_TENUE, borderwidth=0, padding=4)
    stile.configure("TCombobox", fieldbackground=CAMPO, background=CAMPO,
                    foreground=TESTO, arrowcolor=TESTO_TENUE, borderwidth=0, padding=4)
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
                    padding=(16, 8), borderwidth=0, font=UI)
    stile.map("TNotebook.Tab",
              background=[("selected", PANNELLO)],
              foreground=[("selected", TESTO)],
              expand=[("selected", (0, 0, 0, 0))])

    stile.configure("Vertical.TScrollbar", background=CAMPO, troughcolor=FONDO,
                    borderwidth=0, arrowcolor=TESTO_FIOCO)
    stile.map("Vertical.TScrollbar", background=[("active", BORDO)])
    stile.configure("TSeparator", background=BORDO)
    stile.configure("Orizzontale.TScale", background=PANNELLO, troughcolor=CAMPO)

    return stile


def pallino(canvas: tk.Canvas, colore: str) -> None:
    """Il pallino di stato: fermo, in ascolto, guasto.

    Un colore dice lo stato prima di qualunque parola, e questa finestra viene
    guardata di sfuggita mentre si gioca — che e' esattamente la condizione in
    cui una parola non si legge.
    """
    canvas.delete("all")
    canvas.create_oval(3, 3, 13, 13, fill=colore, outline="")
