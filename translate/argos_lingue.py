"""Le coppie di lingue che Argos pubblica, **scritte nel repo e non chieste alla rete**.

## Perche' un elenco committato

E' la stessa scelta gia' fatta per le 133 lingue di Google (`translate/lingue.py`)
e per le 175 voci Piper (`speak/backends/piper_voci.py`): un elenco che dipende
dalla rete si svuota quando la rete non c'e', e un menu vuoto **non da' errore**
— da' una finestra in cui la lingua non si puo' scegliere e nessuno sa perche'.
Un elenco fermo invecchia, ma invecchia in modo visibile:
`tools/censisci_argos.py --controlla` dice in dieci secondi se e' invecchiato, e
`--blocco` rifa' il letterale qui sotto.

## Cosa cambia rispetto a prima

`translate.lingue.copertura("locale")` tornava `codici=None`, cioe' «non c'e' un
elenco chiuso». Non era vero: l'elenco **si calcola**. L'indice dice quali coppie
esistono, e `translate.locale.catena()` passa dall'inglese quando la diretta non
c'e' — quindi da `x` si raggiunge ogni `y` per cui esistono `x->en` e `en->y`.
Sono **45 lingue su 133**, e le altre 88 il traduttore locale non le fa: dirlo
e' l'unica differenza fra un menu che sceglie e un menu che promette.

## Le coppie sono due, il perno e' l'inglese

Delle 100 coppie pubblicate, **98 toccano l'inglese**: le uniche due che non lo
fanno sono `es<->pt`. Non e' una curiosita', e' il motivo per cui `catena()`
esiste e cerca il perno invece della sola diretta — cercando solo `it->es` si
concludeva «non pubblicata» per una coppia che si traduce benissimo.

## I cinque codici che Argos scrive in un altro modo, e la conseguenza

Argos usa i suoi codici, che non sono quelli di Google. Cinque non combaciano:

| Argos | vuol dire | codice Google |
|---|---|---|
| `he` | ebraico | `iw` |
| `nb` | norvegese bokmal | `no` |
| `zh` | cinese semplificato | `zh-CN` |
| `zt` | cinese tradizionale | `zh-TW` |
| `pb` | portoghese brasiliano | `pt` (Google non lo distingue) |

**E qui c'e' un difetto vero, dichiarato e non curato da questo file.**
`translate/locale.py::coppia()` passa ad Argos il codice **cosi' com'e'**, cioe'
il codice Google: chi sceglie l'ebraico manda `iw` a un indice che ha `he`, e si
sente dire «nessun modello» per una coppia che esiste. Quindi quelle cinque
lingue **non** compaiono fra le raggiungibili: dichiararle sarebbe promettere una
traduzione che questa catena non fa. Sta scritto in `SOLO_CON_UN_ALTRO_CODICE`,
che e' l'elenco di cio' che si guadagnerebbe convertendo i codici prima di
consegnarli — misurato, **quattro lingue in piu'** (`iw`, `no`, `zh-CN`,
`zh-TW`; il brasiliano `pb` no, perche' `pt` si raggiunge gia'), cioe' da 45 a
49. La cura sta in `translate/locale.py::coppia()`, che e' l'unico posto che
parla con Argos, e non qui.
"""

from __future__ import annotations

from functools import lru_cache

# Le coppie pubblicate nell'indice Argos, **in codici Argos**.
# Rigenerato il 2026-09-05 con:
#     .\.venv\Scripts\python.exe -m tools.censisci_argos --blocco
COPPIE: frozenset[tuple[str, str]] = frozenset({
    ("ar", "en"),
    ("az", "en"),
    ("bg", "en"),
    ("bn", "en"),
    ("ca", "en"),
    ("cs", "en"),
    ("da", "en"),
    ("de", "en"),
    ("el", "en"),
    ("en", "ar"), ("en", "az"), ("en", "bg"), ("en", "bn"), ("en", "ca"),
    ("en", "cs"), ("en", "da"), ("en", "de"), ("en", "el"), ("en", "eo"),
    ("en", "es"), ("en", "et"), ("en", "eu"), ("en", "fa"), ("en", "fi"),
    ("en", "fr"), ("en", "ga"), ("en", "gl"), ("en", "he"), ("en", "hi"),
    ("en", "hu"), ("en", "id"), ("en", "it"), ("en", "ja"), ("en", "ko"),
    ("en", "ky"), ("en", "lt"), ("en", "lv"), ("en", "ms"), ("en", "nb"),
    ("en", "nl"), ("en", "pb"), ("en", "pl"), ("en", "pt"), ("en", "ro"),
    ("en", "ru"), ("en", "sk"), ("en", "sl"), ("en", "sq"), ("en", "sv"),
    ("en", "sw"), ("en", "th"), ("en", "tl"), ("en", "tr"), ("en", "uk"),
    ("en", "ur"), ("en", "vi"), ("en", "zh"), ("en", "zt"),
    ("eo", "en"),
    ("es", "en"), ("es", "pt"),
    ("et", "en"),
    ("eu", "en"),
    ("fa", "en"),
    ("fi", "en"),
    ("fr", "en"),
    ("ga", "en"),
    ("gl", "en"),
    ("he", "en"),
    ("hi", "en"),
    ("hu", "en"),
    ("id", "en"),
    ("it", "en"),
    ("ja", "en"),
    ("ko", "en"),
    ("ky", "en"),
    ("lt", "en"),
    ("lv", "en"),
    ("ms", "en"),
    ("nb", "en"),
    ("nl", "en"),
    ("pb", "en"),
    ("pl", "en"),
    ("pt", "en"), ("pt", "es"),
    ("ro", "en"),
    ("ru", "en"),
    ("sk", "en"),
    ("sl", "en"),
    ("sq", "en"),
    ("sv", "en"),
    ("sw", "en"),
    ("th", "en"),
    ("tl", "en"),
    ("tr", "en"),
    ("uk", "en"),
    ("ur", "en"),
    ("vi", "en"),
    ("zh", "en"),
    ("zt", "en"),
})

# Tutti i codici che compaiono nell'indice, da una parte o dall'altra.
CODICI: frozenset[str] = frozenset(
    {a for a, _ in COPPIE} | {b for _, b in COPPIE})

# I cinque codici Argos che non sono codici Google, con dentro il codice Google
# che vorrebbero dire. **Non e' una tabella di conversione da usare**: e'
# l'elenco di cosa si guadagnerebbe convertendo, e la conversione andrebbe fatta
# in `translate/locale.py::coppia()`, che e' l'unico posto che parla con Argos.
# Scriverla anche qui vorrebbe dire due posti che dicono la stessa cosa, e il
# secondo non lo aggiorna nessuno — la forma che in questo repo e' gia' costata
# nove volte.
SOLO_CON_UN_ALTRO_CODICE: dict[str, str] = {
    "he": "iw",       # ebraico: Google usa il codice vecchio
    "nb": "no",       # bokmal -> il norvegese di Google
    "zh": "zh-CN",    # cinese semplificato
    "zt": "zh-TW",    # cinese tradizionale
    "pb": "pt",       # portoghese brasiliano: Google non lo distingue
}


def ha(da: str, a: str) -> bool:
    """C'e' un pacchetto pubblicato per questa coppia? **In codici Argos.**"""
    return (da, a) in COPPIE


@lru_cache(maxsize=None)
def _catena():
    """`translate.locale.catena`, presa **da li'** e non riscritta qui.

    La regola «diretta, se no dall'inglese» decide sia cosa si scarica sia cosa
    si dichiara: due copie si scollerebbero, e il modo in cui si scollano e'
    che si scarica un modello e se ne usa un altro.

    L'import e' pigro e messo in cache perche' costa: misurato in questo venv,
    `import translate.locale` prende **1587 ms**, quasi tutti di `stanza` che si
    porta dietro torch (nel pacchetto congelato stanza non c'e' e sono ~20 ms).
    Pagarlo alla costruzione della finestra vorrebbe dire un secondo e mezzo di
    avvio per una domanda che riguarda un backend su quattro.
    """
    from translate.locale import catena

    return catena


@lru_cache(maxsize=None)
def _coppia():
    """`translate.locale.coppia`: risolve `auto`, e lo risolve **una volta sola**.

    Senza, `raggiungibili("auto")` tornava **zero** lingue: nessun pacchetto si
    chiama `auto->x`, e la risposta sembrava «Argos non fa niente» proprio nel
    caso di serie (`translate.source` nasce `auto`). Rifare la regola qui —
    «auto vuol dire en» — sarebbe la stessa unita' sbagliata di sempre: si
    dichiarerebbe una lingua di partenza e se ne scaricherebbe un'altra.
    """
    from translate.locale import coppia

    return coppia


def via(da: str, a: str) -> list[tuple[str, str]] | None:
    """I passaggi pubblicati per andare da `da` ad `a`, **in codici Argos**.

    `auto` viene risolto come lo risolve la catena vera (cioe' in `en`): la
    domanda «Argos ci arriva?» deve essere fatta sulla coppia che verra' davvero
    chiesta, non su quella scritta nel menu.
    """
    da, a = _coppia()(da, a)
    return _catena()(da, a, ha)


@lru_cache(maxsize=None)
def raggiungibili(da: str) -> frozenset[str]:
    """Le lingue d'arrivo che Argos sa raggiungere partendo da `da`.

    **In codici Google**, perche' e' quello che il menu mostra e quello che
    `translate/locale.py` consegna ad Argos senza toccarlo — quindi una lingua
    il cui codice Argos e' diverso (si veda `SOLO_CON_UN_ALTRO_CODICE`) qui non
    c'e', ed e' giusto: quella traduzione, oggi, non parte.
    """
    return frozenset(x for x in _google() if via(da, x) is not None)


@lru_cache(maxsize=None)
def partenze_per(a: str) -> frozenset[str]:
    """L'altra meta': da quali lingue Argos sa arrivare ad `a`.

    Serve alla casella della lingua **di partenza**, dove la domanda e'
    rovesciata. Non e' lo stesso insieme per costruzione — l'indice potrebbe
    pubblicare `x->en` senza `en->x` — quindi non si deduce, si calcola.
    """
    return frozenset(x for x in _google() if via(x, a) is not None)


def _google() -> frozenset[str]:
    """I codici del menu. Import pigro: `translate.lingue` importa questo modulo
    dentro `copertura()`, e al livello del modulo sarebbe un ciclo."""
    from translate.lingue import PER_CODICE

    return frozenset(PER_CODICE)
