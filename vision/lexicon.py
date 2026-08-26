"""Una riga letta e' italiano, o e' la scena?

L'OCR non sa dire di no. Su una banda di texture restituisce `'IIFIL'`, `'REEr'`,
`"?1l'i1"` con la stessa faccia con cui restituisce `'Un'altra brillante ideona
di Lamar Davis.'`, e cio' che esce di li' va dritto in bocca al sintetizzatore.
Le soglie di colore e di contrasto hanno gia' fatto quello che potevano: quelle
righe **sono** bianche e **sono** sottili, perche' un cordolo bianco e' bianco.

L'ultimo filtro non puo' che essere la lingua. Una battuta italiana contiene
almeno una parola italiana; una banda di asfalto no.

## Perche' basta UNA parola

La regola e' volutamente generosa, e la generosita' e' misurata. L'OCR sbaglia
una lettera ogni tanto: `'Propric qui, cazzo!'` ha una parola rotta e due buone,
e chiedere che siano tutte buone la scarterebbe. Chiedendone una sola si perde
quasi solo cio' che di parole non ne ha nessuna — che e' esattamente la
spazzatura di scena.

Il prezzo, misurato su 173 battute vere: restano fuori le forme che i dizionari
non elencano (`'accoglilo'`, imperativo piu' pronome) e le parole che l'OCR
incolla (`'Vabene..'`). Per le seconde c'e' `separa`; per le prime il filtro non
puo' essere un cancello, e infatti `conta` restituisce un **numero** e chi
chiama decide.

## Correggere no, separare si'

La tentazione e' correggere: `'tunziona'` -> `'funziona'` funziona davvero. Ma
provata sui casi veri, la correzione per distanza di edit ha dato due risposte
giuste su otto, e le sei sbagliate erano dei due tipi peggiori — `'rapinato'` ->
`'rovinato'` cambia una parola vera in un'altra parola vera, e `'IIFIL'` ->
`'infila'` promuove la spazzatura a italiano credibile. Oggi, quando l'OCR
sbaglia, si **sente** che ha sbagliato; con la correzione si sentirebbe una
frase pulita che dice un'altra cosa, e non ci sarebbe modo di accorgersene.

`separa` invece non puo' inventare: divide `'Vabene'` in `'va bene'` solo se
**entrambe** le meta' sono parole vere, altrimenti si arrende e lascia tutto
com'era. Una correzione che fallisce da sola e' un'altra cosa da una che sceglie
per te.
"""

from __future__ import annotations

import re
from pathlib import Path

from core import percorsi

_SEGNI = ".,;:!?'\"()[]-–—…«»‘’“”%€$"
_PAROLA = re.compile(r"[^\W\d_]+", re.UNICODE)


class Lexicon:
    """Le parole italiane, in memoria, per la sola domanda "esiste?"."""

    def __init__(self, parole: set[str], fonte: str = "") -> None:
        self.parole = parole
        self.fonte = fonte

    def __len__(self) -> int:
        return len(self.parole)

    def __bool__(self) -> bool:
        return bool(self.parole)

    def nota(self, parola: str) -> bool:
        return parola.strip(_SEGNI).lower() in self.parole

    def conta(self, testo: str, min_lettere: int = 2) -> int:
        """Quante parole del testo sono italiane. Zero e' il segnale forte.

        **Le parole di una lettera non contano.** `'i'`, `'e'`, `'a'`, `'o'`
        sono italiano vero e stanno in qualunque dizionario, ma l'OCR le produce
        da ogni tratto verticale della scena: `'I ler!'` e' passato per la sola
        `'I'`, ha preso la voce del secondo personaggio, ed e' uscito dalle
        cuffie mentre a schermo non c'era nessun sottotitolo. Una parola di una
        lettera non e' una prova che qualcuno stia parlando.
        """
        return sum(
            1
            for w in testo.split()
            if len(w.strip(_SEGNI)) >= min_lettere and self.nota(w)
        )

    def separa(self, parola: str, min_pezzo: int = 2, prima: bool = True) -> str | None:
        """`'Vabene'` -> `'va bene'`, ma solo se entrambe le meta' esistono.

        L'OCR si mangia lo spazio, e due parole vere diventano una falsa che
        nessun dizionario contiene. La divisione si prova in un punto solo — due
        pezzi, non n — perche' con tre o piu' tagli si trova sempre *qualcosa*
        che sta nel dizionario, e la ricomposizione smetterebbe di essere una
        prova che le parole c'erano davvero.
        """
        # La punteggiatura attorno si mette da parte e si rimette: separare
        # `'Vabene,'` in `'va bene'` perderebbe la virgola, cioe' la pausa che
        # il sintetizzatore ci mette. Una riparazione che rompe un'altra cosa
        # non e' una riparazione.
        testa = len(parola) - len(parola.lstrip(_SEGNI))
        coda = len(parola) - len(parola.rstrip(_SEGNI))
        prefisso = parola[:testa]
        suffisso = parola[len(parola) - coda :] if coda else ""
        pulita = parola[testa : len(parola) - coda] if coda else parola[testa:]
        if len(pulita) < 2 * min_pezzo or self.nota(pulita):
            return None
        # **I nomi propri non si separano.** `'Lamar'` diventava `'La mar'` e
        # `'Davis'` diventava `'Da vis'`: entrambe le meta' sono parole italiane
        # vere, quindi la regola "solo se esistono tutt'e due" non bastava a
        # fermarla. Il segnale che li distingue e' la maiuscola **in mezzo alla
        # frase** — a inizio riga la maiuscola non dice niente, perche' ce
        # l'hanno tutte le battute.
        if not prima and pulita[:1].isupper():
            return None
        bassa = pulita.lower()
        tagli = [
            i
            for i in range(min_pezzo, len(pulita) - min_pezzo + 1)
            if bassa[:i] in self.parole and bassa[i:] in self.parole
        ]
        # Un taglio solo, o nessuno. Se i punti buoni sono due o piu' la parola
        # e' ambigua e sceglierne uno sarebbe indovinare: `separa` esiste per
        # riconoscere una struttura che c'era gia', non per costruirne una.
        if len(tagli) != 1:
            return None
        i = tagli[0]
        return f"{prefisso}{pulita[:i]} {pulita[i:]}{suffisso}"

    def scolla(self, testo: str) -> str:
        """Applica `separa` a ogni parola sconosciuta della riga."""
        fuori = []
        for k, w in enumerate(testo.split()):
            sep = self.separa(w, prima=(k == 0))
            fuori.append(sep if sep is not None else w)
        return " ".join(fuori)


_CACHE: dict[str, Lexicon] = {}


def carica(cartella: str | Path = "models/lexicon") -> Lexicon:
    """Legge gli elenchi da disco. Un lessico vuoto e' **dichiarato**, non finto.

    Se la cartella non c'e' si torna un lessico vuoto, e chi lo usa deve
    accorgersene: `bool(lex)` e' `False`. Un lessico vuoto che rispondesse
    "conosciuta" a tutto spegnerebbe il filtro in silenzio, e un filtro spento in
    silenzio e' peggio di un filtro assente — si continuerebbe a misurare
    credendo che stia lavorando.
    """
    chiave = str(cartella)
    if chiave in _CACHE:
        return _CACHE[chiave]

    # **Il default e' relativo, e un percorso relativo non dice dove.** Da
    # sorgente `models/lexicon` e la cartella di lancio coincidono; nel pacchetto
    # no, e il lessico risultava vuoto senza un errore — cioe' il filtro spento
    # in silenzio contro cui il resto di questa funzione e' scritto.
    base = percorsi.dato(cartella)
    parole: set[str] = set()
    fonti: list[str] = []
    for path in sorted(base.glob("*.txt")) + sorted(base.glob("*.dic")):
        try:
            testo = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        prima = len(parole)
        for riga in testo.splitlines():
            # I `.dic` di hunspell sono `parola/CODICI`: i codici sono regole di
            # affisso, non parte della parola.
            w = riga.split("/")[0].strip().lower()
            if w and _PAROLA.fullmatch(w):
                parole.add(w)
        if len(parole) > prima:
            fonti.append(f"{path.name} (+{len(parole)-prima})")

    lex = Lexicon(parole, ", ".join(fonti))
    _CACHE[chiave] = lex
    return lex
