"""Quali **scritture** i riconoscitori sanno leggere, e chi le usa.

`translate.source` accetta una qualunque delle 133 lingue di Google. Nessuno dei
due backend OCR dichiarava che cosa sa leggere, e mettendone una che non sa
leggere **non succede niente di visibile**: la ROI resta muta e sembra tarata
male, oppure — peggio — escono parole latine che non vogliono dire niente e
vengono pronunciate. E' la stessa forma del ripiego silenzioso gia' pagata qui
nove volte, spostata di uno stadio a monte.

## Misurato, non dedotto

I numeri qui sotto vengono da `tools/censisci_ocr.py`, che disegna **la stessa
frase** in dieci scritture con Qt (che compone: senza, l'arabo esce in forme
isolate e il CER direbbe una cosa sul disegno invece che sull'OCR) e la passa ai
backend montati su questa macchina. Il controllo positivo e' la riga latina: se
quella non esce a CER 0, il banco e' rotto e nessun altro numero conta.

Misurato il 2026-09-05, una riga per scrittura, carattere di sistema in
grassetto a 36 px, bianco su nero:

| scrittura | ppocr (RapidOCR) | oneocr |
|---|---|---|
| latina | **0,00** | **0,00** |
| cinese | **0,00** | **0,00** |
| cirillica | 0,95 — translittera | **0,00** |
| greca | 0,95 — translittera | **0,00** |
| araba | 1,00 — translittera | **0,00** |
| ebraica | 1,00 — translittera | **0,00** |
| thai | 1,00 — translittera | **0,00** |
| giapponese | 0,93 — non legge | **0,00** |
| coreana | 0,91 — non legge | **0,00** |
| devanagari | 1,00 — non legge | **0,00** |

**La soglia non e' tarata, e' in mezzo a un altopiano.** Fra «letta» e «non
letta» non c'e' niente: 0,00 da una parte e 0,91 come minimo dall'altra. Un
numero scelto ovunque fra 0,1 e 0,9 dice la stessa cosa, quindi `CER_MAX` non e'
un parametro da difendere.

## I due modi di fallire non sono lo stesso, e il secondo e' peggio

`ppocr` sul giapponese, sul coreano e sul devanagari **non legge niente** — la
riga cade nel filtro dei caratteri minimi e non succede altro. Sul cirillico,
sul greco, sull'arabo, sull'ebraico e sul thai invece **translittera**:
`У меня нет времени` esce `Y MeHA Het BpeMeHH`, `ฉันไม่มีเวลา` esce
`Auluianananuuta`. Sono lettere latine vere, passano ogni filtro di questa
catena, ricevono una voce e **vengono pronunciate**. Il contatore delle righe
vuote resta a zero e il registro e' verde.

## Le scritture non misurate si dichiarano tali

Diciassette scritture (armena, georgiana, tamil, telugu, khmer, etiopica…) non
sono state provate: nessuno ha disegnato quelle righe. Sono marcate `None`, che
vuol dire **non misurato** e non «non funziona» — dedurre da «ppocr e' addestrato
su cinese e inglese» che non legge il tamil sarebbe plausibile e non sarebbe una
misura.

## Lo stadio dopo buttava tutto cio' che non era latino, e adesso no

Anche dove il riconoscitore leggeva benissimo, `vision/ocr.py::italian_only` —
che `vision/reader.py` applicava a **ogni** riga, qualunque fosse
`translate.source` — teneva solo lettere latine, cifre e punteggiatura. Quindi
la catena intera leggeva **una** scrittura, e la tabella qui sopra descriveva un
riconoscitore i cui risultati non arrivavano da nessuna parte.

Misurato attraverso il lettore vero, con un `EchoOcr` che legge perfettamente
(cosi' l'unica cosa che possa far sparire una riga sta *dopo* il
riconoscimento), una riga per scrittura:

| | battute che arrivano in fondo |
|---|---|
| filtro latino sempre (com'era) | **1 su 10** — la latina |
| alfabeto dalla lingua dichiarata (com'e') | **10 su 10**, intatte |

La cura non e' spegnere il filtro: e' legarlo a `translate.source` invece che
all'alfabeto latino, esattamente come si fa un gradino dopo per il lessico
italiano. Il filtro serviva e serve — l'OCR di serie e' addestrato su cinese e
inglese e sullo scenario inventa glifi CJK, che finivano in bocca al
sintetizzatore — ma «non e' latino» non e' «non e' della lingua che il gioco
scrive». Si veda `ALFABETI` qui sotto e `vision/ocr.py::solo_alfabeti`.

**Il prezzo e' dichiarato**: su un gioco *giapponese* quei glifi CJK dello
scenario tornano a passare, perche' li' sono indistinguibili dal dialogo. La
scrittura la dichiara l'utente, e nessun filtro puo' saperne di piu' di lui.
"""

from __future__ import annotations

from dataclasses import dataclass

# Sopra questo CER la riga letta non e' la riga scritta. Non e' un numero tarato:
# le misure stanno a 0,00 o sopra 0,91, e in mezzo non c'e' niente (si veda la
# tabella nel commento in cima).
CER_MAX = 0.10

# Il modo in cui una scrittura viene sbagliata. `TRANSLITTERA` e' il caso
# pericoloso: esce testo latino plausibile, che passa i filtri e viene detto.
LEGGE = "legge"
TRANSLITTERA = "translittera"
MUTA = "muta"


@dataclass(frozen=True, slots=True)
class Esito:
    """Come e' andata su questa scrittura con questo backend.

    `cer is None` vuol dire **non misurato**, e non e' la stessa cosa di un CER
    alto: dedurre un fallimento da come e' stato addestrato un modello sarebbe
    plausibile, e non sarebbe una misura.
    """

    cer: float | None
    modo: str = ""

    @property
    def misurato(self) -> bool:
        return self.cer is not None

    @property
    def buono(self) -> bool:
        return self.cer is not None and self.cer <= CER_MAX


NON_MISURATO = Esito(None)

# Le dieci scritture provate, per backend. Rigenerabile con
# `.\.venv\Scripts\python.exe -m tools.censisci_ocr`.
MISURE: dict[str, dict[str, Esito]] = {
    "ppocr": {
        "latina": Esito(0.00, LEGGE),
        "cinese": Esito(0.00, LEGGE),
        "cirillica": Esito(0.95, TRANSLITTERA),
        "greca": Esito(0.95, TRANSLITTERA),
        "araba": Esito(1.00, TRANSLITTERA),
        "ebraica": Esito(1.00, TRANSLITTERA),
        "thai": Esito(1.00, TRANSLITTERA),
        "giapponese": Esito(0.93, MUTA),
        "coreana": Esito(0.91, MUTA),
        "devanagari": Esito(1.00, MUTA),
    },
    "oneocr": {
        "latina": Esito(0.00, LEGGE),
        "cinese": Esito(0.00, LEGGE),
        "cirillica": Esito(0.00, LEGGE),
        "greca": Esito(0.00, LEGGE),
        "araba": Esito(0.00, LEGGE),
        "ebraica": Esito(0.00, LEGGE),
        "thai": Esito(0.00, LEGGE),
        "giapponese": Esito(0.00, LEGGE),
        "coreana": Esito(0.00, LEGGE),
        "devanagari": Esito(0.00, LEGGE),
    },
}

# I nomi che `vision/ocr.py::make_ocr` accetta per lo stesso motore. Sta qui e
# non in un `if` sparso: `ppocr` e `rapidocr` sono la stessa cosa, e una tabella
# indicizzata su uno dei due nomi risponderebbe «non misurato» all'altro.
ALIAS_BACKEND: dict[str, str] = {
    "rapidocr": "ppocr",
    "ppocr": "ppocr",
    "oneocr": "oneocr",
}

# **Chi non sta qui usa l'alfabeto latino.** Elencare le centoventi lingue latine
# sarebbe un elenco che nessuno rilegge; elencare le eccezioni e' un elenco che
# si controlla a occhio, e la verifica `scritture` pretende che ogni chiave sia
# un codice vero della tabella di Google — se no un refuso diventa in silenzio
# «questa lingua e' latina».
NON_LATINE: dict[str, str] = {
    # arabo e le lingue che ne usano la scrittura
    "ar": "araba", "fa": "araba", "ps": "araba", "ur": "araba",
    "sd": "araba", "ckb": "araba", "ug": "araba",
    # cirillico
    "ru": "cirillica", "uk": "cirillica", "be": "cirillica", "bg": "cirillica",
    "mk": "cirillica", "sr": "cirillica", "mn": "cirillica", "kk": "cirillica",
    "ky": "cirillica", "tg": "cirillica", "tt": "cirillica",
    # le due cinesi e le vicine
    "zh-CN": "cinese", "zh-TW": "cinese",
    "ja": "giapponese", "ko": "coreana",
    # devanagari
    "hi": "devanagari", "mr": "devanagari", "ne": "devanagari",
    "sa": "devanagari", "bho": "devanagari", "doi": "devanagari",
    "mai": "devanagari", "gom": "devanagari",
    # le altre indiane, una scrittura ciascuna
    "bn": "bengalese", "as": "bengalese",
    "gu": "gujarati", "pa": "gurmukhi", "kn": "kannada", "ml": "malayalam",
    "or": "oriya", "ta": "tamil", "te": "telugu", "si": "sinhala",
    "mni-Mtei": "meitei",
    # sud-est asiatico
    "th": "thai", "lo": "lao", "km": "khmer", "my": "birmana",
    # medio oriente e Caucaso
    "iw": "ebraica", "yi": "ebraica", "dv": "thaana",
    "hy": "armena", "ka": "georgiana",
    "am": "etiopica", "ti": "etiopica",
    # greco
    "el": "greca",
}

LATINA = "latina"

# **Quali lettere puo' contenere una battuta scritta in questa scrittura.**
#
# I valori sono prefissi del *nome Unicode* del carattere, non intervalli di
# codici: `unicodedata.name('ж')` e' `'CYRILLIC SMALL LETTER ZHE'`. Il nome e'
# gia' la tabella — scriverne una seconda con gli intervalli vorrebbe dire
# tenerne allineate due, che qui e' gia' costato sette volte, e sbagliare un
# intervallo non da' errore: fa sparire una lettera su venti.
#
# Il prefisso si confronta col nome **intero**, non col primo pezzo: `ー`, il
# segno di allungamento che in giapponese sta dappertutto, si chiama
# `KATAKANA-HIRAGANA PROLONGED SOUND MARK`, e un confronto sul primo pezzo lo
# butterebbe.
#
# **Il latino sta in tutte.** In un sottotitolo russo o giapponese ci sono nomi
# propri, sigle e marchi scritti in latino, e toglierli sarebbe la stessa forma
# di danno che questa tabella esiste per riparare, girata dall'altra parte.
ALFABETI: dict[str, tuple[str, ...]] = {
    LATINA: ("LATIN",),
    "cirillica": ("CYRILLIC", "LATIN"),
    "greca": ("GREEK", "LATIN"),
    "araba": ("ARABIC", "LATIN"),
    "ebraica": ("HEBREW", "LATIN"),
    "thaana": ("THAANA", "LATIN"),
    "armena": ("ARMENIAN", "LATIN"),
    "georgiana": ("GEORGIAN", "LATIN"),
    "etiopica": ("ETHIOPIC", "LATIN"),
    # Il cinese ha gli ideogrammi; il giapponese gli stessi ideogrammi **piu'**
    # i due sillabari; il coreano l'hangul piu' gli ideogrammi, che restano nei
    # nomi propri.
    "cinese": ("CJK", "LATIN"),
    "giapponese": ("CJK", "HIRAGANA", "KATAKANA", "LATIN"),
    "coreana": ("HANGUL", "CJK", "LATIN"),
    "devanagari": ("DEVANAGARI", "LATIN"),
    "bengalese": ("BENGALI", "LATIN"),
    "gujarati": ("GUJARATI", "LATIN"),
    "gurmukhi": ("GURMUKHI", "LATIN"),
    "kannada": ("KANNADA", "LATIN"),
    "malayalam": ("MALAYALAM", "LATIN"),
    "oriya": ("ORIYA", "LATIN"),
    "tamil": ("TAMIL", "LATIN"),
    "telugu": ("TELUGU", "LATIN"),
    "sinhala": ("SINHALA", "LATIN"),
    "meitei": ("MEETEI", "LATIN"),
    "thai": ("THAI", "LATIN"),
    "lao": ("LAO", "LATIN"),
    "khmer": ("KHMER", "LATIN"),
    "birmana": ("MYANMAR", "LATIN"),
}

# Due forme della stessa cosa: una mezza frase che segue una virgola, e una che
# sta in piedi da sola dopo un punto. Ce n'era una sola, e usciva «potrebbe non
# leggersi affatto. e comunque la catena…» — una nota che si legge male e' una
# nota che non si legge.
NOTA_FILTRO = (
    "e la catena tiene le lettere di quella scrittura piu' le latine, "
    "perche' `translate.source` dice quale"
)
NOTA_FILTRO_SOLA = (
    "La catena tiene le lettere di quella scrittura piu' le latine, "
    "perche' `translate.source` dice quale."
)


def scrittura(codice: str) -> str:
    """La scrittura di una lingua. Chi non e' fra le eccezioni e' latino."""
    from translate.lingue import normalizza

    return NON_LATINE.get(normalizza(codice), LATINA)


def alfabeti(codice: str) -> tuple[str, ...]:
    """Che lettere tenere in una riga letta con il gioco scritto in `codice`.

    **Il ripiego e' il latino, e non e' un ripiego prudente per caso.** Una
    lingua che non si riconosce — `auto` compreso, che non e' una lingua ma
    «chiedilo al traduttore» — torna al filtro con cui questa catena e' stata
    misurata per intero: nessun comportamento nuovo dove non c'e' una risposta.
    """
    return ALFABETI.get(scrittura(codice), ALFABETI[LATINA])


def esito(backend: str, codice: str) -> Esito:
    """Come va **questo** backend su **questa** lingua.

    Un backend che non si conosce e una scrittura che non e' stata provata danno
    tutti e due `NON_MISURATO`: sono due ignoranze diverse, ma la cosa da dire
    all'utente e' la stessa — «di questo non si sa», che non e' «non funziona».
    """
    nome = ALIAS_BACKEND.get((backend or "").strip().lower(), "")
    if not nome:
        return NON_MISURATO
    return MISURE.get(nome, {}).get(scrittura(codice), NON_MISURATO)


def nota_ocr(backend: str, codice: str) -> str:
    """La frase da mettere sotto la casella della lingua **letta**, o vuota.

    E' una regola, quindi sta qui e non in Qt — la lezione gia' pagata quattro
    volte su cinque difetti. Dice tre cose diverse e le distingue: «non e' stato
    misurato», «non legge e basta», «legge un'altra cosa e la fa pronunciare».
    """
    s = scrittura(codice)
    if s == LATINA:
        return ""
    e = esito(backend, codice)
    nome = (backend or "?").strip() or "?"
    if not e.misurato:
        return (f"La scrittura {s} con «{nome}» non e' stata misurata: "
                f"potrebbe non leggersi affatto. {NOTA_FILTRO_SOLA}")
    if e.buono:
        return (f"«{nome}» legge la scrittura {s} (CER {e.cer:.2f} sul banco), "
                f"{NOTA_FILTRO}.")
    if e.modo == TRANSLITTERA:
        return (f"«{nome}» non legge la scrittura {s}: ne tira fuori lettere "
                f"latine plausibili (CER {e.cer:.2f}), che nessun filtro ferma "
                f"e che verrebbero pronunciate.")
    return (f"«{nome}» non legge la scrittura {s} (CER {e.cer:.2f}): "
            f"la riga resta vuota.")
