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

## E c'e' uno stadio dopo, che oggi butta tutto cio' che non e' latino

Anche dove il riconoscitore legge benissimo, `vision/ocr.py::italian_only` —
che `vision/reader.py` applica a **ogni** riga, qualunque sia `translate.source`
— tiene solo lettere latine, cifre e punteggiatura. Misurato sulle stesse dieci
righe:

| | righe che sopravvivono al filtro |
|---|---|
| oneocr | **1 su 10** (la latina), dopo averle lette tutte e dieci a CER 0,00 |
| ppocr | 6 su 10 — e cinque delle sei sono la **translitterazione** |

Le due righe dicono la stessa cosa da due parti opposte: con OneOCR si butta
nove volte su dieci del testo letto bene, con ppocr si tiene cinque volte su
dieci del testo che non e' quello scritto. Quindi oggi la catena intera legge
**una** scrittura, la latina, e questo modulo lo dichiara invece di lasciarlo
scoprire a sessione accesa: si veda `NOTA_FILTRO_LATINO`.
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

NOTA_FILTRO_LATINO = (
    "e comunque la catena tiene solo le lettere latine "
    "(`vision/ocr.py::italian_only`): oggi il doppiaggio dal vivo legge una "
    "scrittura sola."
)


def scrittura(codice: str) -> str:
    """La scrittura di una lingua. Chi non e' fra le eccezioni e' latino."""
    from translate.lingue import normalizza

    return NON_LATINE.get(normalizza(codice), LATINA)


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
                f"potrebbe non leggersi affatto. {NOTA_FILTRO_LATINO}")
    if e.buono:
        return (f"«{nome}» legge la scrittura {s} (CER {e.cer:.2f} sul banco), "
                f"{NOTA_FILTRO_LATINO}")
    if e.modo == TRANSLITTERA:
        return (f"«{nome}» non legge la scrittura {s}: ne tira fuori lettere "
                f"latine plausibili (CER {e.cer:.2f}), che nessun filtro ferma "
                f"e che verrebbero pronunciate.")
    return (f"«{nome}» non legge la scrittura {s} (CER {e.cer:.2f}): "
            f"la riga resta vuota.")
