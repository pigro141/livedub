"""La lingua della **finestra**, che non e' la lingua dei sottotitoli.

`translate.source` e `translate.target` sono le lingue del doppiaggio. Questo
modulo e' un'altra cosa: le parole della finestra — «Avvia», «Seleziona area»,
«non e' fra quelli disponibili» — per chi non legge l'italiano.

## L'italiano resta la lingua del sorgente, e i cataloghi ci stanno **sopra**

La convenzione del progetto non cambia: le stringhe si scrivono in italiano nei
sorgenti. Un catalogo e' `{stringa italiana -> stringa tradotta}`, cioe' la
chiave **e'** il testo che il codice contiene: non ci sono identificatori da
inventare, non c'e' un secondo elenco da tenere allineato, e una stringa nuova
nel codice compare da sola fra le chiavi mancanti invece di sparire.

## Non si traduce chiamando `T()` in quattrocento punti: si percorre la finestra

La strada classica — avvolgere ogni stringa in `tr()` — vorrebbe dire toccare
quattrocento righe di `tools/ui_qt.py`, e ogni riga dimenticata resta in italiano
**senza dare errore**. Qui invece si costruisce la finestra e poi la si
percorre (`applica`), mettendo a posto testi, titoli di scheda, suggerimenti e
segnaposto. E' la stessa scelta di `core/schema.py` per le impostazioni: l'elenco
non si scrive, si ricava — quindi non puo' scollarsi.

Il prezzo e' dichiarato: **si traduce quello che sta scritto sui widget**, non
quello che ci finisce dopo. Il registro, la barra della misura e i messaggi di
stato nascono da f-string con dentro numeri e nomi di file, e restano in
italiano — insieme alle spiegazioni dei parametri, per la ragione qui sotto.

## Le spiegazioni dei 166 campi **non si traducono**, ed e' una scelta

Vengono dai commenti di `core/config.py` cosi' come sono scritti, tabelle di
misure comprese, e `core/schema.py` esiste apposta per non riscriverle:
«riscriverli significherebbe perdere le misure e inventare rischi al loro
posto». Passarle a un traduttore automatico farebbe esattamente quello, su
centosessantasei campi per lingua, e un numero tradotto male in una tabella di
misure e' peggio di un numero in una lingua che non si legge. I widget che le
portano sono marcati `nontradurre`, e la finestra lo dichiara nella scheda.

## Una chiave che manca ricade sull'italiano, e si **conta**

Una finestra mezza tradotta senza che niente lo dica e' peggio di una finestra
in italiano: si crede che quella parola non esista invece che non sia stata
tradotta. `mancanti()` dice quali chiavi non ci sono, `applica()` torna quante
ne ha messe a posto, e la verifica `ui_lingua` tiene il conto sotto un tetto.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent / "lingue"

# Il file con l'elenco delle chiavi, scritto da `tools/traduci_ui.py`: e' la
# fotografia di cosa la finestra dice **adesso**, e serve a sapere quanto manca
# a un catalogo senza dover costruire la finestra.
CHIAVI = CARTELLA / "_chiavi.json"

# L'italiano non ha un catalogo: e' il sorgente.
SORGENTE = "it"

# **Le lingue che si scrivono da destra a sinistra.** Qt sa ribaltare il verso
# della finestra con `setLayoutDirection`, e senza quello una finestra in arabo
# esce con le etichette e i controlli nell'ordine sbagliato — leggibile parola
# per parola e incomprensibile come disposizione.
DA_DESTRA: frozenset[str] = frozenset({"ar", "iw", "he", "fa", "ur", "ps", "sd", "ug", "yi"})

# I widget marcati cosi', e tutto quello che sta sotto di loro, restano in
# italiano. Il valore e' una proprieta' Qt perche' deve viaggiare col widget: chi
# costruisce la spiegazione di un campo sa che non va tradotta, chi percorre
# l'albero mezz'ora dopo no.
MARCHIO = "nontradurre"

# **I pezzi che nessuna passeggiata puo' trovare**, perche' non stanno in nessun
# widget: sono le parole con cui `tools/ui_qt.py` **compone** una frase a
# runtime, e a schermo esistono solo gia' unite.
#
# Non sono un secondo elenco scritto a mano per comodita': sono la cura di un
# difetto misurato. La riga «da fare nella preparazione: …» era finita nel
# catalogo come **una combinazione sola** — quella che c'era nell'istante
# dell'estrazione — e corrispondeva a quell'istante e a nessun altro. Nelle
# schermate si vedeva: finestra in tedesco, quella riga in italiano.
#
# Divergere da quello che il codice chiede davvero e' il rischio ovvio di una
# lista cosi', ed e' per questo che la verifica `ui_lingua` legge il **sorgente**
# di `tools/ui_qt.py` e pretende che i due elenchi coincidano: un pezzo nuovo
# senza la sua voce qui rende la suite rossa, invece di uscire in italiano in
# mezzo a una finestra tradotta.
COMPOSTE: tuple[str, ...] = (
    "da fare nella preparazione:",
    "scegli la finestra del gioco",
    "sistema l'audio",
    "l'area e' troppo alta",
    "pronto",
    # Le quattro parole della fase (`core.motore.FASI`) e i due segnaposto della
    # scheda Sessione. La fase la sceglie una regola e la scrive la finestra:
    # nessuna passeggiata sui widget puo' vedere le tre che in quell'istante non
    # sono a schermo, quindi tre su quattro resterebbero in italiano per sempre —
    # e resterebbero in italiano **a turno**, cioe' senza che nessuno sappia
    # perche' a volte si vede e a volte no.
    "fermo",
    "sta leggendo",
    "sta parlando",
    "in ritardo",
    "in attesa della prima frase",
    "nessuno ancora",
)


# ------------------------------------------------------------- i cataloghi --


@lru_cache(maxsize=1)
def disponibili() -> tuple[str, ...]:
    """I codici per cui c'e' un catalogo nel repo, italiano compreso.

    Si guarda il **disco** e non un elenco scritto: aggiungere una lingua e'
    lanciare `tools/traduci_ui.py`, non ritoccare due file di cui il secondo si
    dimentica.
    """
    if not CARTELLA.is_dir():
        return (SORGENTE,)
    fuori = sorted(
        p.stem for p in CARTELLA.glob("*.json") if not p.stem.startswith("_"))
    return tuple([SORGENTE] + [x for x in fuori if x != SORGENTE])


@lru_cache(maxsize=None)
def carica(codice: str) -> dict[str, str]:
    """Il catalogo di quella lingua: `{italiano -> tradotto}`.

    Vuoto se non c'e', e non e' un errore: vuol dire «tutto in italiano», che e'
    esattamente il comportamento di prima di questo modulo.
    """
    if not codice or codice == SORGENTE:
        return {}
    percorso = CARTELLA / f"{codice}.json"
    if not percorso.is_file():
        return {}
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    voci = dati.get("voci", dati)
    return {str(k): str(v) for k, v in voci.items() if isinstance(v, str) and v}


@lru_cache(maxsize=1)
def chiavi() -> tuple[str, ...]:
    """Le stringhe che la finestra dice, come le ha viste l'ultima estrazione.

    In cache perche' `_lingue_finestra()` la chiede una volta per catalogo per
    dire quante parole mancano a ciascuno: quarantadue letture di file a ogni
    pannello costruito, e i pannelli sono sei.
    """
    if not CHIAVI.is_file():
        return ()
    try:
        return tuple(json.loads(CHIAVI.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return ()


def traduci(testo: str, codice: str) -> str:
    """Una stringa sola, per chi la compone invece di scriverla in un widget.

    La passeggiata di `applica` traduce quello che **c'e' gia' scritto** in un
    widget, e va bene per tutto tranne i testi che nascono uniti a runtime. La
    riga «da fare nella preparazione: …» e' l'esempio: e' un elenco di pezzi che
    cambia con lo stato, e finiva nel catalogo come **una combinazione sola**
    («scegli la finestra del gioco · l'area e' troppo alta»). Quella chiave
    corrisponde a un istante e a nessun altro: appena si sistema l'audio o si
    stringe l'area, la frase nuova non e' piu' nel catalogo e torna in italiano
    in mezzo al tedesco. Peggio, `applica` ricorderebbe la frase **composta**
    come originale italiano, e al cambio di lingua successivo se la terrebbe.

    Quindi chi compone traduce i pezzi e poi li unisce, e marca il proprio
    widget `nontradurre` perche' la passeggiata non ci torni sopra.
    """
    if not testo:
        return testo
    return carica(risolvi(codice)).get(testo, testo)


def fuori_dalla_passeggiata() -> tuple[str, ...]:
    """Tutto cio' che `raccogli()` non puo' vedere, e che va comunque tradotto.

    Sono due famiglie, e sono diverse:

    - **`COMPOSTE`** — le parole con cui la finestra *unisce* una frase a
      runtime: a schermo esistono solo gia' unite, quindi la passeggiata vede la
      combinazione di quell'istante e nessun'altra;
    - **il tutorial** (`ui/tutorial.py`) — una finestra che **non esiste**
      finche' non la si apre. Percorrendo la finestra principale non c'e' niente
      da trovare, e le sue parole resterebbero in italiano in mezzo a un
      programma tradotto — che e' peggio dell'italiano, perche' sembra una parola
      che non si traduce invece di una che nessuno ha tradotto.

    Il rischio di un elenco a mano e' che diverga da cio' che il codice dice
    davvero: per la prima famiglia lo prende la verifica `ui_lingua` leggendo il
    sorgente, per la seconda la verifica `tutorial`, che costruisce il dialogo e
    confronta le due liste.
    """
    from ui.tutorial import testi

    return tuple(dict.fromkeys([*COMPOSTE, *testi()]))


def cambia(w, testo: str) -> None:
    """Cambia il testo di un widget **e la memoria dell'originale italiano**.

    `applica` conserva su ogni widget il testo che c'era la prima volta
    (`__it_text`), perche' se no il secondo cambio di lingua tradurrebbe una
    traduzione. Il prezzo e' un tranello: da quel momento un `setText` normale
    **non tiene**, perche' la passeggiata successiva rimette la memoria. Visto a
    schermo: il bottone «Avanti» del tutorial diventava «Ho capito» all'ultimo
    passo e tornava «Avanti» un istante dopo, senza nessun errore.

    Chi cambia a runtime il testo di un widget che la passeggiata tocca passa da
    qui. Chi lo marca `nontradurre` non ne ha bisogno: quei widget la
    passeggiata non li guarda.
    """
    w.setProperty("__it_text", testo)
    w.setText(testo)


def mancanti(codice: str) -> tuple[str, ...]:
    """Le chiavi che quella lingua non ha, in ordine di estrazione."""
    if codice == SORGENTE:
        return ()
    catalogo = carica(codice)
    return tuple(k for k in chiavi() if k not in catalogo)


def scrivi(codice: str, voci: dict[str, str], backend: str) -> Path:
    """Salva un catalogo. Lo usa solo `tools/traduci_ui.py`."""
    CARTELLA.mkdir(parents=True, exist_ok=True)
    percorso = CARTELLA / f"{codice}.json"
    percorso.write_text(
        json.dumps(
            {"lingua": codice, "backend": backend, "voci": voci},
            ensure_ascii=False, indent=1, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    carica.cache_clear()
    chiavi.cache_clear()
    disponibili.cache_clear()
    return percorso


# --------------------------------------------------------- quale lingua --


def di_sistema() -> str:
    """La lingua di Windows, ridotta a un codice di questa tabella.

    Serve a `ui.lingua = auto`. Si passa da `translate.lingue.normalizza` perche'
    Windows dice `it_IT` e Google dice `it`: due modi di scrivere la stessa cosa,
    e un confronto secco fra i due non trova niente **senza dare errore**.
    """
    import locale as _locale

    from translate.lingue import normalizza

    try:
        etichetta = _locale.getlocale()[0] or ""
    except (ValueError, TypeError):  # pragma: no cover - dipende dal sistema
        etichetta = ""
    if not etichetta:
        try:
            etichetta = _locale.getdefaultlocale()[0] or ""
        except (ValueError, AttributeError, TypeError):  # pragma: no cover
            etichetta = ""
    if not etichetta:
        return SORGENTE
    # `Italian_Italy` e' la forma che Windows restituisce con `getlocale()`.
    if "_" in etichetta and len(etichetta.split("_")[0]) > 3:
        from translate.lingue import LINGUE

        inizio = etichetta.split("_")[0].lower()
        for x in LINGUE:
            if x.inglese.lower().split(" (")[0] == inizio:
                return x.codice
        return SORGENTE
    return normalizza(etichetta) or SORGENTE


def risolvi(codice: str) -> str:
    """Che lingua usare davvero, con `auto` sciolto e il ripiego dichiarato.

    **`auto` senza catalogo non e' un errore, e nemmeno un silenzio**: torna
    l'italiano, che e' la lingua del sorgente. Chi vuole sapere se e' successo
    guarda `disponibili()`: la finestra ci mette la riga che lo dice.
    """
    scelto = (codice or SORGENTE).strip()
    if scelto == "auto":
        scelto = di_sistema()
    if scelto in disponibili():
        return scelto
    return SORGENTE


def perche_italiano(codice: str) -> str:
    """Perche' la finestra e' rimasta in italiano. `""` se non lo e'.

    Tre esiti, e **due sono normali**:

        ""              non e' rimasta in italiano, e' in un'altra lingua
        "scelto"        l'italiano e' stato chiesto (`it`, o niente)
        "sistema"       `auto` su un Windows italiano: e' andata bene
        "senza catalogo" `auto` su una lingua che non abbiamo, o un codice
                         inventato — questo si', e' un ripiego da dichiarare

    **Esiste perche' la finestra li confondeva.** Diceva «! nessun catalogo per
    "auto": la finestra resta in italiano» su un Windows italiano, cioe' marcava
    come guasto il caso in cui `auto` aveva funzionato — visto nel registro di
    una prova vera, due volte. Un `!` speso dove non e' successo niente e' lo
    stesso difetto del ripiego silenzioso, girato dall'altra parte: la volta che
    conta, nessuno lo legge piu'.
    """
    scelto = (codice or SORGENTE).strip()
    if scelto in ("", SORGENTE):
        return "scelto"
    voluto = di_sistema() if scelto == "auto" else scelto
    if voluto in disponibili() and voluto != SORGENTE:
        return ""
    if voluto == SORGENTE:
        return "sistema" if scelto == "auto" else "scelto"
    return "senza catalogo"


def da_destra(codice: str) -> bool:
    """Questa lingua si scrive da destra a sinistra?"""
    from translate.lingue import normalizza

    return normalizza(codice) in DA_DESTRA


# ------------------------------------------------- percorrere la finestra --

# Una stringa senza nemmeno una lettera non e' testo: e' `—`, `2`, `✓`, `ⓘ`.
# Tradurla vorrebbe dire mandare a un traduttore automatico i numeri e i glifi
# della finestra, e riceverli indietro cambiati.
_HA_LETTERE = re.compile(r"[^\W\d_]", re.UNICODE)

# **Un identificatore non e' una frase, e tradurlo e' un difetto.** Il
# suggerimento di ogni riga di parametro e' il suo percorso (`vision.sat_max`), e
# l'etichetta di un campo senza nome umano e' il nome del campo (`roi_margin`):
# sono centosessantasei stringhe che un traduttore automatico riscriverebbe
# volentieri — «vision.sat_max» in tedesco — rendendo impossibile cercare un
# parametro per il nome con cui compare nei comandi e nei rapporti.
_IDENTIFICATORE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")


def _traducibile(testo: str) -> bool:
    testo = (testo or "").strip()
    if not testo or len(testo) > 400:
        return False
    if "<" in testo and ">" in testo:   # HTML: il log e le tessere lo usano
        return False
    if _IDENTIFICATORE.match(testo):
        return False
    return bool(_HA_LETTERE.search(testo))


def _marcato(w) -> bool:
    """Vero se questo widget, o uno dei suoi genitori, e' `nontradurre`."""
    nodo = w
    while nodo is not None:
        if nodo.property(MARCHIO):
            return True
        nodo = nodo.parentWidget()
    return False


def _campi(w) -> list[tuple[str, callable, callable]]:
    """I pezzi di testo di un widget: `(chiave-proprieta', leggi, scrivi)`.

    Le classi si guardano con `hasattr` e non con `isinstance` per non importare
    mezza `QtWidgets` qui dentro: questo modulo lo usa anche chi non ha aperto
    una finestra (l'estrattore, le verifiche), e un import di Qt al livello del
    modulo lo renderebbe impossibile — la stessa ragione per cui `ui/qt_tema.py`
    tiene PySide6 dentro le funzioni.
    """
    from PySide6.QtWidgets import QLineEdit

    fuori: list[tuple[str, callable, callable]] = []
    # **Il testo di una casella e' un valore, mai una parola dell'interfaccia.**
    # Li' dentro ci sono `models/lexicon`, `translategemma:4b`,
    # `http://127.0.0.1:11434`: tradurli vorrebbe dire riscrivere la
    # configurazione dell'utente in tedesco. Il segnaposto invece e' testo
    # nostro, e resta.
    if isinstance(w, QLineEdit):
        return [("placeholder", w.placeholderText, w.setPlaceholderText),
                ("tooltip", w.toolTip, w.setToolTip)]
    if hasattr(w, "text") and hasattr(w, "setText"):
        # **`Elidibile` mente su cosa dice.** `text()` torna il testo gia'
        # tagliato coi puntini, che dipende da quanto e' larga la finestra in
        # quel momento: preso come chiave, il catalogo si riempirebbe di
        # `«Un'altra zona da leggere e pron…»` — una chiave diversa a ogni
        # larghezza, che non corrispondera' mai a niente. Il testo intero ce
        # l'ha, si chiama `_intero`.
        leggi = (lambda b=w: b._intero) if hasattr(w, "_intero") else w.text
        fuori.append(("text", leggi, w.setText))
    if hasattr(w, "title") and hasattr(w, "setTitle"):
        fuori.append(("title", w.title, w.setTitle))
    if hasattr(w, "placeholderText") and hasattr(w, "setPlaceholderText"):
        fuori.append(("placeholder", w.placeholderText, w.setPlaceholderText))
    if hasattr(w, "toolTip") and hasattr(w, "setToolTip"):
        fuori.append(("tooltip", w.toolTip, w.setToolTip))
    return fuori


def _percorri(radice, fai) -> None:
    """Chiama `fai(originale, scrivi)` per ogni pezzo di testo della finestra."""
    from PySide6.QtWidgets import QComboBox, QTabWidget, QWidget

    for w in [radice, *radice.findChildren(QWidget)]:
        if _marcato(w):
            continue
        for chiave, leggi, metti in _campi(w):
            nome = f"__it_{chiave}"
            memoria = w.property(nome)
            testo = memoria if isinstance(memoria, str) else leggi()
            if not _traducibile(testo):
                continue
            if not isinstance(memoria, str):
                w.setProperty(nome, testo)
            fai(testo, metti)
        if isinstance(w, QComboBox):
            for i in range(w.count()):
                nome = f"__it_voce_{i}"
                memoria = w.property(nome)
                testo = memoria if isinstance(memoria, str) else w.itemText(i)
                if not _traducibile(testo):
                    continue
                if not isinstance(memoria, str):
                    w.setProperty(nome, testo)
                fai(testo, (lambda c, k=i, b=w: b.setItemText(k, c)))
        if isinstance(w, QTabWidget):
            for i in range(w.count()):
                nome = f"__it_scheda_{i}"
                memoria = w.property(nome)
                testo = memoria if isinstance(memoria, str) else w.tabText(i)
                if not _traducibile(testo):
                    continue
                if not isinstance(memoria, str):
                    w.setProperty(nome, testo)
                fai(testo, (lambda c, k=i, b=w: b.setTabText(k, c)))


def raccogli(radice) -> list[str]:
    """Tutte le stringhe traducibili della finestra, senza doppioni e in ordine.

    E' la **stessa** passeggiata che fa `applica`: l'estrattore e chi traduce
    non possono vedere due elenchi diversi, che e' il modo classico in cui un
    catalogo si riempie di chiavi che nessuno usera' mai e ne perde altre.
    """
    visti: dict[str, None] = {}
    _percorri(radice, lambda testo, _metti: visti.setdefault(testo, None))
    return list(visti)


def applica(radice, codice: str) -> tuple[int, int]:
    """Mette la finestra in quella lingua. Torna `(tradotte, lasciate in italiano)`.

    Rimettere `it` **rimette l'italiano**, e non e' scontato: senza la memoria
    dell'originale su ogni widget, il secondo cambio di lingua tradurrebbe una
    traduzione — e la terza volta si tradurrebbe quella, allontanandosi a ogni
    giro dal testo scritto nel sorgente. E' lo stesso motivo per cui `Pannello`
    rilegge da config invece di fidarsi di quello che ha appena scritto.
    """
    from PySide6.QtCore import Qt

    scelta = risolvi(codice)
    catalogo = carica(scelta)
    conto = [0, 0]

    def fai(testo: str, metti) -> None:
        tradotto = catalogo.get(testo)
        if tradotto:
            conto[0] += 1
        else:
            conto[1] += 1
        metti(tradotto or testo)

    _percorri(radice, fai)
    radice.setLayoutDirection(
        Qt.RightToLeft if da_destra(scelta) else Qt.LeftToRight)
    return conto[0], conto[1]
