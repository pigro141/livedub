"""Il tema della finestra Qt: un foglio di stile, e basta.

**Perche' si e' cambiato motore.** La finestra era in Tkinter, che non ha angoli
stondati: si ottenevano generando le immagini dei widget e registrandole come
elementi a nove fette, e ci sono voluti tre giri per scoprire che sostituendo il
bordo di un bottone sparisce la scritta, che riscrivendo il layout di un
contatore il numero si schiaccia, e che al menu a tendina spariva la freccia.
Tre difetti in una cosa che in Qt e' una riga:

    border-radius: 8px;

Non e' una questione di gusto per un toolkit: e' che in Tkinter ogni rifinitura
grafica costa un giro di prove a schermo, e il costo si paga di nuovo alla
prossima. Qui la grafica si dichiara.

**PySide6 e non PyQt**: e' il binding **ufficiale** di The Qt Company, ed e'
LGPL-3 — compatibile con la GPL-3 di questo progetto (si veda `LICENZE.md`).
PyQt e' GPL-3 o commerciale, quindi avrebbe funzionato lo stesso, ma la scelta
fra i due si fa una volta e conviene farla su quello che il progetto Qt
mantiene.

**La tavolozza e' la stessa di prima**, e non per pigrizia: era stata scelta su
un vincolo che non cambia col toolkit — questa finestra sta sopra un gioco,
spesso di notte, e i sei colori dei personaggi devono restare distinguibili fra
loro sul fondo su cui sono disegnati.
"""

from __future__ import annotations

from pathlib import Path

# **Il baffo della spunta e' un file, e non c'e' modo di evitarlo.** Qt disegna
# lo stato "spuntato" con un'immagine (`image:`), e un foglio di stile non sa
# tracciare una linea. La prima versione puntava a un nome inventato e il
# risultato era un quadrato blu pieno: chiaro abbastanza da non accorgersene
# subito, e sbagliato. Si genera una volta in `models/` — che e' gia' la cartella
# della roba che il programma si costruisce da solo — e si riusa.
_BAFFO = Path(__file__).resolve().parent.parent / "models" / "ui" / "baffo.png"


def _baffo() -> str:
    """Il segno di spunta come PNG, disegnato una volta. Torna il percorso."""
    if not _BAFFO.exists():
        from PIL import Image, ImageDraw

        S = 4  # si disegna grande e si rimpicciolisce: PIL non antialiasa le linee
        img = Image.new("RGBA", (17 * S, 17 * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        L = 17 * S
        d.line([(L * 0.24, L * 0.52), (L * 0.42, L * 0.71), (L * 0.77, L * 0.29)],
               fill="#0d1117", width=int(S * 1.9), joint="curve")
        _BAFFO.parent.mkdir(parents=True, exist_ok=True)
        img.resize((17, 17), Image.LANCZOS).save(_BAFFO)
    return _BAFFO.as_posix()


def _freccia(verso: str, colore: str) -> str:
    """Il triangolino delle tendine e dei contatori, come PNG.

    **Il trucco dei bordi CSS qui non funziona.** Su una pagina web un triangolo
    si fa con tre bordi e uno colorato; Qt accetta quelle proprieta' senza
    lamentarsi e disegna un quadratino — che e' precisamente il tipo di difetto
    che non da' errore e si vede solo guardando. Un'immagine e' quattro righe e
    non ha stati d'animo.
    """
    percorso = _BAFFO.parent / f"freccia-{verso}-{colore.lstrip('#')}.png"
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


# -- la tavolozza -------------------------------------------------------------
FONDO = "#14161c"
PANNELLO = "#1b1e26"
CAMPO = "#232732"
BORDO = "#2f3542"

TESTO = "#e6e8ee"
TESTO_TENUE = "#8b93a7"
TESTO_FIOCO = "#616b82"

ACCENTO = "#4c9aff"
ACCENTO_SCURO = "#3d7fd6"
VERDE = "#43b581"
AMBRA = "#e8a33d"
ROSSO = "#e5534b"

VOCI = ("#7ee787", "#79c0ff", "#ffa657", "#d2a8ff", "#ff7b72", "#f2cc60")

UI = "Segoe UI"
MONO = "Consolas"

# Il raggio in un posto solo: cambiarlo qui cambia tutta la finestra, che era
# esattamente la cosa che in Tkinter richiedeva di rigenerare dieci immagini.
R = 8
R_PICCOLO = 6


def foglio() -> str:
    """Il foglio di stile della finestra intera."""
    return f"""
* {{
    font-family: "{UI}";
    font-size: 10pt;
    color: {TESTO};
    outline: none;
}}
QWidget {{ background: {FONDO}; }}
QToolTip {{
    background: {PANNELLO}; color: {TESTO};
    border: 1px solid {BORDO}; border-radius: {R_PICCOLO}px; padding: 6px 8px;
}}

/* -- testata ----------------------------------------------------------- */
#testata {{ background: {PANNELLO}; }}
#nomeApp {{ font-size: 15pt; font-weight: 600; }}
#tenue  {{ color: {TESTO_TENUE}; font-size: 9pt; }}
#mono   {{ color: {TESTO_TENUE}; font-family: "{MONO}"; font-size: 9pt; }}
#sezione {{ color: {ACCENTO}; font-size: 9pt; font-weight: 600; }}
#nomeCampo {{ font-family: "{MONO}"; font-size: 9pt; }}
#avviso {{ color: {AMBRA}; font-size: 9pt; }}
#spento {{ color: {TESTO_FIOCO}; font-size: 9pt; }}
#errore {{ color: {ROSSO}; font-size: 9pt; }}

/* -- bottoni ----------------------------------------------------------- */
QPushButton {{
    background: {CAMPO}; border: none; border-radius: {R}px;
    padding: 8px 16px; color: {TESTO};
}}
QPushButton:hover  {{ background: {BORDO}; }}
QPushButton:pressed {{ background: {ACCENTO_SCURO}; }}
QPushButton:disabled {{ background: {PANNELLO}; color: {TESTO_FIOCO}; }}
QPushButton#primario {{
    background: {VERDE}; color: #0d1117; font-weight: 600; padding: 8px 24px;
}}
QPushButton#primario:hover {{ background: #4fc994; }}
QPushButton#primario:disabled {{ background: {PANNELLO}; color: {TESTO_FIOCO}; }}
QPushButton#accento {{ background: {ACCENTO}; color: #0d1117; font-weight: 600; }}
QPushButton#accento:hover {{ background: {ACCENTO_SCURO}; }}
QPushButton#aiuto {{
    background: transparent; color: {ACCENTO};
    border-radius: 11px; padding: 0px; min-width: 22px; max-width: 22px;
    min-height: 22px; max-height: 22px; font-size: 11pt;
}}
QPushButton#aiuto:hover {{ background: {CAMPO}; }}

/* -- campi ------------------------------------------------------------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {CAMPO}; border: 1px solid transparent; border-radius: {R_PICCOLO}px;
    padding: 6px 9px; selection-background-color: {ACCENTO}; selection-color: #0d1117;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENTO};
}}
QLineEdit:disabled, QComboBox:disabled {{ background: {PANNELLO}; color: {TESTO_FIOCO}; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 20px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent; border: none; width: 16px; margin-right: 3px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{_freccia('su', TESTO_TENUE)}"); width: 9px; height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{_freccia('giu', TESTO_TENUE)}"); width: 9px; height: 9px;
}}
QSpinBox::up-arrow:hover {{ image: url("{_freccia('su', ACCENTO)}"); }}
QSpinBox::down-arrow:hover {{ image: url("{_freccia('giu', ACCENTO)}"); }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: url("{_freccia('giu', TESTO_TENUE)}"); width: 9px; height: 9px; margin-right: 8px;
}}
QComboBox::down-arrow:hover {{ image: url("{_freccia('giu', ACCENTO)}"); }}
QComboBox QAbstractItemView {{
    background: {CAMPO}; border: 1px solid {BORDO}; border-radius: {R_PICCOLO}px;
    selection-background-color: {ACCENTO}; selection-color: #0d1117; padding: 4px;
}}

/* -- caselle di spunta -------------------------------------------------- */
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{
    width: 17px; height: 17px; border-radius: 5px;
    background: {CAMPO}; border: 1px solid {BORDO};
}}
QCheckBox::indicator:hover {{ border: 1px solid {ACCENTO}; }}
QCheckBox::indicator:checked {{
    background: {ACCENTO}; border: 1px solid {ACCENTO};
    image: url("{_baffo()}");
}}
QCheckBox::indicator:disabled {{ background: {PANNELLO}; border: 1px solid {PANNELLO}; }}

/* -- schede ------------------------------------------------------------ */
QTabWidget::pane {{
    background: {PANNELLO}; border: none;
    border-top-left-radius: 0px; border-radius: {R}px;
}}
QTabBar::tab {{
    background: {FONDO}; color: {TESTO_TENUE};
    padding: 10px 22px; margin-right: 3px;
    border-top-left-radius: {R}px; border-top-right-radius: {R}px;
}}
QTabBar::tab:hover {{ color: {TESTO}; }}
QTabBar::tab:selected {{ background: {PANNELLO}; color: {TESTO}; }}

/* -- liste, log, barre ------------------------------------------------- */
QPlainTextEdit, QTextEdit, QListWidget {{
    background: {PANNELLO}; border: none; border-radius: {R}px;
    padding: 10px; font-family: "{MONO}";
    selection-background-color: {ACCENTO}; selection-color: #0d1117;
}}
QListWidget::item {{ padding: 4px 6px; border-radius: {R_PICCOLO}px; }}
QListWidget::item:selected {{ background: {ACCENTO}; color: #0d1117; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{
    background: {BORDO}; border-radius: 5px; min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {TESTO_FIOCO}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ border: none; background: {PANNELLO}; }}
QScrollArea > QWidget > QWidget {{ background: {PANNELLO}; }}

/* -- la striscia delle modifiche in attesa ------------------------------ */
#striscia {{ background: {CAMPO}; border-radius: {R}px; }}
#striscia QLabel {{ background: transparent; color: {TESTO}; }}

/* -- le zone di contenuto ---------------------------------------------- */
#pannello {{ background: {PANNELLO}; border-radius: {R}px; }}
#pannello QLabel, #pannello QCheckBox {{ background: transparent; }}
#riga:hover {{ background: {CAMPO}; border-radius: {R_PICCOLO}px; }}
"""


def spia(colore: str) -> str:
    """Il pallino di stato, come foglio di stile per una QLabel tonda."""
    return (
        f"background: {colore}; border-radius: 6px; min-width: 12px; max-width: 12px;"
        f" min-height: 12px; max-height: 12px;"
    )
