"""Il tema della finestra Qt: due tavolozze, e Windows decide quale.

**Perche' si e' cambiato motore.** La finestra era in Tkinter, che non ha angoli
stondati: si ottenevano generando le immagini dei widget e registrandole come
elementi a nove fette, e ci sono voluti tre giri per scoprire che sostituendo il
bordo di un bottone sparisce la scritta, che riscrivendo il layout di un
contatore il numero si schiaccia, e che al menu a tendina spariva la freccia.
Tre difetti in una cosa che in Qt e' una riga: `border-radius: 8px`.

**PySide6 e non PyQt**: e' il binding **ufficiale** di The Qt Company, ed e'
LGPL-3 — compatibile con la GPL-3 di questo progetto (si veda `LICENZE.md`).

**Chiaro o scuro lo decide Windows, non noi.** Qt 6.5 in su espone il tema di
sistema (`QStyleHints.colorScheme`) e **avvisa quando cambia**
(`colorSchemeChanged`), quindi non serve leggere il registro ne' riavviare: si
riapplica il foglio di stile. Chi tiene Windows in chiaro si vedeva arrivare un
rettangolo nero in mezzo allo schermo.

**Ma le due tavolozze non sono l'una l'inverso dell'altra**, ed e' la parte che
conta. I sei colori dei personaggi nel log sono l'informazione principale di
questa finestra — la domanda che ci si fa guardandola non e' «cosa ha detto» ma
«e' sempre lo stesso a parlare?» — e devono restare distinguibili **fra loro**
sul fondo su cui sono disegnati. Gli stessi sei che funzionano sul nero, messi
sul bianco, diventano pastelli che si confondono a coppie. Quindi ce ne sono sei
per il chiaro, piu' scuri e piu' saturi: stessi ruoli, colori diversi.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Le immagini generate (spunta e frecce) dipendono dal colore, quindi ce n'e' un
# giro per tavolozza. Si disegnano una volta e restano.
_DISEGNI = Path(__file__).resolve().parent.parent / "models" / "ui"


@dataclass(frozen=True)
class Tavolozza:
    """I colori di un tema. Due istanze: `SCURA` e `CHIARA`."""

    nome: str
    fondo: str
    pannello: str
    campo: str
    bordo: str
    testo: str
    testo_tenue: str
    testo_fioco: str
    accento: str
    accento_scuro: str
    verde: str
    ambra: str
    rosso: str
    su_accento: str  # il testo scritto **sopra** un bottone colorato
    voci: tuple[str, ...]


SCURA = Tavolozza(
    nome="scuro",
    fondo="#14161c", pannello="#1b1e26", campo="#232732", bordo="#2f3542",
    testo="#e6e8ee", testo_tenue="#8b93a7", testo_fioco="#616b82",
    accento="#4c9aff", accento_scuro="#3d7fd6",
    verde="#43b581", ambra="#e8a33d", rosso="#e5534b",
    su_accento="#0d1117",
    voci=("#7ee787", "#79c0ff", "#ffa657", "#d2a8ff", "#ff7b72", "#f2cc60"),
)

CHIARA = Tavolozza(
    nome="chiaro",
    fondo="#f4f5f8", pannello="#ffffff", campo="#eceef3", bordo="#d6dae3",
    testo="#1c1f27", testo_tenue="#5b6478", testo_fioco="#8b93a7",
    accento="#2563c9", accento_scuro="#1d4fa3",
    verde="#1f8a5a", ambra="#a86a10", rosso="#c0392b",
    su_accento="#ffffff",
    voci=("#1a7f37", "#0a58ca", "#b45309", "#7c3aed", "#c0392b", "#8a6d00"),
)


def attuale(app) -> Tavolozza:
    """La tavolozza che Windows sta chiedendo adesso.

    Se Qt non sa rispondere — versione vecchia, sistema che non lo espone — si
    resta sullo scuro **e non si indovina**: era il tema di prima, e un default
    dichiarato vale piu' di una lettura del registro che puo' sbagliare.
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


# ------------------------------------------------------------- i disegnini --


def _baffo(t: Tavolozza) -> str:
    """Il segno di spunta come PNG.

    **Qt disegna lo stato «spuntato» con un'immagine, e un foglio di stile non sa
    tracciare una linea.** La prima versione puntava a un nome inventato e il
    risultato era un quadrato pieno: abbastanza chiaro da non accorgersene
    subito, e sbagliato.
    """
    percorso = _DISEGNI / f"baffo-{t.su_accento.lstrip('#')}.png"
    if not percorso.exists():
        from PIL import Image, ImageDraw

        S = 4  # si disegna grande e si rimpicciolisce: PIL non antialiasa le linee
        img = Image.new("RGBA", (17 * S, 17 * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        L = 17 * S
        d.line([(L * 0.24, L * 0.52), (L * 0.42, L * 0.71), (L * 0.77, L * 0.29)],
               fill=t.su_accento, width=int(S * 1.9), joint="curve")
        percorso.parent.mkdir(parents=True, exist_ok=True)
        img.resize((17, 17), Image.LANCZOS).save(percorso)
    return percorso.as_posix()


def _freccia(verso: str, colore: str) -> str:
    """Il triangolino delle tendine e dei contatori, come PNG.

    **Il trucco dei bordi CSS qui non funziona.** Su una pagina web un triangolo
    si fa con tre bordi e uno colorato; Qt accetta quelle proprieta' senza
    lamentarsi e disegna un quadratino — precisamente il tipo di difetto che non
    da' errore e si vede solo guardando.
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


UI = "Segoe UI"
MONO = "Consolas"
R = 8
R_PICCOLO = 6


def foglio(t: Tavolozza = SCURA) -> str:
    """Il foglio di stile della finestra intera, per la tavolozza data."""
    return f"""
* {{
    font-family: "{UI}"; font-size: 10pt; color: {t.testo}; outline: none;
}}
QWidget {{ background: {t.fondo}; }}
QToolTip {{
    background: {t.pannello}; color: {t.testo};
    border: 1px solid {t.bordo}; border-radius: {R_PICCOLO}px; padding: 6px 8px;
}}

#testata {{ background: {t.pannello}; }}
#nomeApp {{ font-size: 15pt; font-weight: 600; }}
#tenue  {{ color: {t.testo_tenue}; font-size: 9pt; }}
#mono   {{ color: {t.testo_tenue}; font-family: "{MONO}"; font-size: 9pt; }}
#sezione {{ color: {t.accento}; font-size: 9pt; font-weight: 600; }}
#nomeCampo {{ font-family: "{MONO}"; font-size: 9pt; }}
#avviso {{ color: {t.ambra}; font-size: 9pt; }}
#spento {{ color: {t.testo_fioco}; font-size: 9pt; }}
#errore {{ color: {t.rosso}; font-size: 9pt; }}

QPushButton {{
    background: {t.campo}; border: none; border-radius: {R}px;
    padding: 8px 16px; color: {t.testo};
}}
QPushButton:hover  {{ background: {t.bordo}; }}
QPushButton:pressed {{ background: {t.accento_scuro}; color: {t.su_accento}; }}
QPushButton:disabled {{ background: {t.pannello}; color: {t.testo_fioco}; }}
QPushButton#primario {{
    background: {t.verde}; color: {t.su_accento}; font-weight: 600; padding: 8px 24px;
}}
QPushButton#primario:disabled {{ background: {t.pannello}; color: {t.testo_fioco}; }}
QPushButton#accento {{ background: {t.accento}; color: {t.su_accento}; font-weight: 600; }}
QPushButton#accento:hover {{ background: {t.accento_scuro}; }}
QPushButton#aiuto {{
    background: transparent; color: {t.accento}; border-radius: 11px; padding: 0px;
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; font-size: 11pt;
}}
QPushButton#aiuto:hover {{ background: {t.campo}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {t.campo}; border: 1px solid transparent; border-radius: {R_PICCOLO}px;
    padding: 6px 9px; selection-background-color: {t.accento}; selection-color: {t.su_accento};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {t.accento};
}}
QLineEdit:disabled, QComboBox:disabled {{ background: {t.pannello}; color: {t.testo_fioco}; }}
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
QSpinBox::up-arrow:hover {{ image: url("{_freccia('su', t.accento)}"); }}
QSpinBox::down-arrow:hover {{ image: url("{_freccia('giu', t.accento)}"); }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: url("{_freccia('giu', t.testo_tenue)}"); width: 9px; height: 9px; margin-right: 8px;
}}
QComboBox::down-arrow:hover {{ image: url("{_freccia('giu', t.accento)}"); }}
QComboBox QAbstractItemView {{
    background: {t.campo}; border: 1px solid {t.bordo}; border-radius: {R_PICCOLO}px;
    selection-background-color: {t.accento}; selection-color: {t.su_accento}; padding: 4px;
}}

QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{
    width: 17px; height: 17px; border-radius: 5px;
    background: {t.campo}; border: 1px solid {t.bordo};
}}
QCheckBox::indicator:hover {{ border: 1px solid {t.accento}; }}
QCheckBox::indicator:checked {{
    background: {t.accento}; border: 1px solid {t.accento};
    image: url("{_baffo(t)}");
}}
QCheckBox::indicator:disabled {{ background: {t.pannello}; border: 1px solid {t.pannello}; }}

QTabWidget::pane {{ background: {t.pannello}; border: none; border-radius: {R}px; }}
QTabBar::tab {{
    background: {t.fondo}; color: {t.testo_tenue};
    padding: 10px 22px; margin-right: 3px;
    border-top-left-radius: {R}px; border-top-right-radius: {R}px;
}}
QTabBar::tab:hover {{ color: {t.testo}; }}
QTabBar::tab:selected {{ background: {t.pannello}; color: {t.testo}; }}

QPlainTextEdit, QTextEdit, QListWidget {{
    background: {t.pannello}; border: none; border-radius: {R}px;
    padding: 10px; font-family: "{MONO}";
    selection-background-color: {t.accento}; selection-color: {t.su_accento};
}}
QListWidget::item {{ padding: 4px 6px; border-radius: {R_PICCOLO}px; }}
QListWidget::item:selected {{ background: {t.accento}; color: {t.su_accento}; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {t.bordo}; border-radius: 5px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {t.testo_fioco}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ border: none; background: {t.pannello}; }}
QScrollArea > QWidget > QWidget {{ background: {t.pannello}; }}

#striscia {{ background: {t.campo}; border-radius: {R}px; }}
#striscia QLabel {{ background: transparent; color: {t.testo}; }}
#pannello {{ background: {t.pannello}; border-radius: {R}px; }}
#pannello QLabel, #pannello QCheckBox {{ background: transparent; }}
#riga:hover {{ background: {t.campo}; border-radius: {R_PICCOLO}px; }}
"""


def spia(colore: str) -> str:
    """Il pallino di stato, come foglio di stile per una QLabel tonda."""
    return (
        f"background: {colore}; border-radius: 6px; min-width: 12px; max-width: 12px;"
        f" min-height: 12px; max-height: 12px;"
    )
