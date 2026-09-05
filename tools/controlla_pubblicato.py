"""I numeri e i cataloghi **pubblicati**, contro quello che il codice sa.

    .\\.venv\\Scripts\\python.exe -m tools.controlla_pubblicato --controlla
    .\\.venv\\Scripts\\python.exe -m tools.controlla_pubblicato            # riscrive le cifre

## Perche' esiste, e cosa non copriva nessuno

`tools/tabella_lingue.py` controlla le lingue parlate; `tools/conta_verifiche.py`
il numero di verifiche della suite. Restavano fuori tutti gli **altri** numeri che
i sette README e i sette cataloghi della vetrina dichiarano a chi decide se
installare, e che nessuno ricava: quante stringhe ha un catalogo della finestra,
quante prove fa l'eseguibile su se stesso. Erano gia' scollati tutti e due —
«258 stringhe su 258» quando sono **281**, «dodici prove» quando sono **13** — e
sono scollati nel modo che questo repo ha gia' pagato nove volte: un numero
vecchio non da' nessun errore, si dice soltanto il falso a chi legge.

Qui il numero **non si scrive**: si chiede a `ui.lingua` e a `tools.autoprova`,
che sono i posti che lo sanno. Chi aggiunge una stringa alla finestra o una prova
al pacchetto non deve ricordarsi di niente.

## Le due meta', e rispondono a due domande diverse

**I numeri** (`NUMERI`) si ancorano alla loro *unita'* — «281 stringhe», «13
prove» — perche' e' l'unica parola che sopravvive alla traduzione in un posto
prevedibile. Ogni regex ha un gruppo che si chiama `n` ed **e' la sola cifra**:
cosi' la sostituzione non deve sapere niente della frase che ci sta intorno, e le
sei traduzioni non ripassano da un traduttore per un numero. E' la stessa regola
di `tools/conta_verifiche.py`.

**I cataloghi della vetrina** (`vetrina`) non hanno bisogno di nessuna regex, ed
e' il controllo piu' forte dei due. Un catalogo e' `{stringa inglese ->
tradotta}`, quindi:

- una chiave che **non esiste piu'** in `en.js` non da' errore: quella voce non
  risponde piu' a niente e la pagina torna in inglese in quel paragrafo, in tutte
  e sei le lingue. E' successo davvero, su un «82 gruppi» rimasto indietro
  mentre l'inglese diceva 83;
- e **ogni cifra della chiave deve ricomparire nella traduzione**. Se l'inglese
  dice 281 e il tedesco 258, la pagina mostra due numeri diversi per la stessa
  cosa a seconda della lingua che si legge. Questo confronto non sa niente di
  nessuna lingua: guarda i gruppi di cifre e basta.

  **Il confronto e' in una direzione sola**, e non e' pigrizia: una traduzione
  puo' *aggiungerne* — il giapponese scrive «carattere per carattere» come «1
  文字ずつ» — e pretendere l'uguaglianza darebbe un elenco di falsi allarmi lungo
  quanto il catalogo, cioe' un controllo che nessuno rilegge. Quello che non puo'
  succedere e' che un numero della chiave **sparisca o cambi**: e' li' che sta il
  difetto, ed e' li' che questo guarda.

## La terza meta', ed e' quella che le prime due non potevano vedere

Le due sopra guardano **le cifre che qualcuno ha ancorato**. Restava fuori tutto
il resto della prosa, e li' e' successo: correggendo il conteggio di piper da 50
a 49, il paragrafo che lo racconta e' stato riscritto **nella vetrina e non nei
sette README**, che hanno continuato a dire «l'indice ne elenca 51 e questo
programma ne offre 50, la differenza e' il giapponese» — un numero vecchio e una
frase falsa (le differenze sono due), senza che niente diventasse rosso.

Tre regole nuove, e nessuna delle tre ha bisogno di un'ancora scritta a mano.

**`allineamento`** — `README.md` e `site/i18n/en.js` sono **due impaginazioni
delle stesse frasi**, e lo stesso vale per ognuna delle altre sei lingue. Quindi
si prendono le frasi che contengono una cifra, si toglie la cifra, e le due
meta' si accoppiano da sole: dove la frase **senza numeri** e' identica e i
numeri no, uno dei due file e' rimasto indietro. Non serve sapere di che numero
si tratta ne' in che lingua e' scritta la frase — oggi accoppia 54 frasi in
inglese e da 10 a 55 nelle altre sei, e questa e' la regola che avrebbe preso il
paragrafo.

**`unione_in_prosa`** — un pezzo di testo che nomina **tutti e tre** i motori con
i **tre conteggi** sta dichiarando l'elenco delle lingue parlate, e in quel pezzo
l'unione deve esserci. Il nome di un motore non si traduce, e nemmeno una cifra:
la stessa regola vale sui quattordici file senza una riga di lingua. E' il caso
che `tools/tabella_lingue.py` non copriva, perche' li' l'unione si controlla
nella **cella** della tabella e non nella frase — che infatti diceva 53 mentre la
cella diceva 52, nello stesso file.

**`misurate`** — la riga di una tabella che comincia con il nome di un motore
parla di **quel** motore: il numero piu' grande della cella accanto e' il suo
conteggio di lingue. Prende sia `| **piper** | **49** |` sia il «N su M» della
tabella delle lingue misurate, che diceva `1 su 50` — cioe' una misura fatta su
una lingua (l'ebraico) che il programma non offre piu', contraddetta dal
paragrafo tre righe sotto.

## Cosa questo strumento **non** dice

Che il numero sia giusto *nel codice*: dice che quello pubblicato e' lo stesso
che il codice produce adesso. E `allineamento` dice che le due impaginazioni
concordano, non che abbiano ragione: se il numero e' sbagliato in tutti e due,
qui passa — e' per questo che le altre regole partono dal codice.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from tools.tabella_lingue import READMES, SITO, leggi_disco, scrivi_disco  # noqa: E402

#: I quattordici posti in cui un numero pubblicato e' scritto: i sette README e i
#: **sette** cataloghi della vetrina. Sette e non uno: nei sei tradotti la cifra
#: compare due volte, perche' la chiave e' la frase inglese e il valore la sua
#: traduzione. Riscrivere il solo `en.js` lascerebbe indietro sei chiavi che non
#: corrispondono piu' a niente. E' la stessa lista di `tools/conta_verifiche.py`,
#: e sta scritta li' per esteso il perche'.
def posti() -> dict[str, Path]:
    fuori = dict(READMES)
    for catalogo in sorted(SITO.parent.glob("*.js")):
        fuori[f"sito/{catalogo.stem}"] = catalogo
    return fuori


# ============================================================ i numeri =====
#
# Ogni voce e' `(nome, come si ricava, le regex)`. Le regex hanno **un gruppo
# solo, che si chiama `n`**, e quel gruppo e' la cifra: tutto il resto e'
# contesto e non si tocca. Ce n'e' una per lingua perche' l'unita' e' l'unica
# parola che si puo' ancorare — e per la stessa ragione per cui in
# `tools/tabella_lingue.py` `vicino` non e' una regex sola: il giapponese e il
# cinese mettono il classificatore dopo il numero, e una regex sola avrebbe
# smesso di **trovare** la frase invece di trovarla sbagliata.


def _quante_stringhe() -> int:
    """Le stringhe della finestra, cioe' cio' che un catalogo deve contenere."""
    from ui import lingua

    return len(lingua.chiavi())


def _quante_prove() -> int:
    """Le prove che l'eseguibile fa su se stesso (`livedub.exe --autoprova`).

    Si legge il **sorgente** con `ast` invece di importare `tools.autoprova`:
    quel modulo tira dentro Qt, ONNX e i backend, e questo strumento deve poter
    girare anche dove non ci sono. La forma e' quella di `ui.lingua.COMPOSTE`
    letta dalla verifica che la controlla.
    """
    albero = ast.parse((RADICE / "tools" / "autoprova.py").read_text(encoding="utf-8"))
    for nodo in albero.body:
        if isinstance(nodo, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PROVE" for t in nodo.targets
        ):
            if not isinstance(nodo.value, ast.List):
                break
            return len(nodo.value.elts)
    raise RuntimeError("in tools/autoprova.py non trovo piu' l'elenco `PROVE`")


#: «281 stringhe su 281», nelle sette lingue. Due regex per lingua perche' il
#: numero compare **due volte** nella stessa frase — «X su X» — e la seconda non
#: si prende con la stessa ancora della prima.
_STRINGHE = (
    r"(?P<n>\d+)(?=\s+strings\s+out\s+of)",
    r"strings\s+out\s+of\s*\n?\s*(?P<n>\d+)",
    r"(?P<n>\d+)(?=\s+stringhe\s+su)",
    r"stringhe\s+su\s*\n?\s*(?P<n>\d+)",
    r"(?P<n>\d+)(?=\s+von\s+\d+\s*\n?\s*Zeichenketten)",
    r"von\s+(?P<n>\d+)(?=\s*\n?\s*Zeichenketten)",
    r"(?P<n>\d+)(?=\s+cadenas\s+de)",
    r"cadenas\s+de\s*\n?\s*(?P<n>\d+)",
    r"(?P<n>\d+)(?=\s+chaînes)",
    r"chaînes\s*\n?\s*sur\s+(?P<n>\d+)",
    r"(?P<n>\d+)(?=\s*個中)",
    r"個中\s*(?P<n>\d+)",
    r"(?P<n>\d+)(?=\s*条中的)",
    r"条中的\s*(?P<n>\d+)",
)

#: «13 prove», nelle sette lingue. **Erano scritte in lettere** — twelve, dodici,
#: zwölf, doce, douze, 十二 — e una parola non si confronta con `len(PROVE)`:
#: sono state messe in cifre apposta, che e' la stessa scelta gia' fatta per il
#: numero delle verifiche. Una parola scritta in sei lingue non e' un dato.
#:
#: **E l'unita' da sola qui non basta**, che e' il difetto che questa tupla ha
#: gia' avuto: la suite si dichiara con le stesse parole — «2460 vérifications»,
#: «2460 個の検査», «2460 项检查» — quindi un'ancora sulla sola unita' leggeva il
#: numero delle verifiche e lo confrontava con quello delle prove. Ci vuole anche
#: la parola davanti («ces», «quelle», «esas», «その», «这»), che e' il
#: dimostrativo con cui ogni lingua rimanda alle tre righe qui sopra.
_PROVE = (
    r"(?P<n>\d+)(?=\s+of\s+those\s+checks)",
    r"quelle\s+(?P<n>\d+)(?=\s+prove\b)",
    r"alle\s+(?P<n>\d+)(?=\s+dieser\s+Prüfungen)",
    r"esas\s+(?P<n>\d+)(?=\s+pruebas\b)",
    r"ces\s+(?P<n>\d+)(?=\s+vérifications\b)",
    r"その\s*(?P<n>\d+)(?=\s*個の検査)",
    r"这\s*(?P<n>\d+)(?=\s*项检查)",
)

NUMERI: tuple[tuple[str, object, tuple[str, ...]], ...] = (
    ("le stringhe della finestra", _quante_stringhe, _STRINGHE),
    ("le prove dentro l'eseguibile", _quante_prove, _PROVE),
)


def _rifai(testo: str, rx: re.Pattern, nuovo: str) -> str:
    """Rimette `nuovo` **solo** dove sta il gruppo `n`, e lascia il resto."""
    pezzi: list[str] = []
    ultimo = 0
    for m in rx.finditer(testo):
        pezzi.append(testo[ultimo:m.start("n")])
        pezzi.append(nuovo)
        ultimo = m.end("n")
    pezzi.append(testo[ultimo:])
    return "".join(pezzi)


def numeri_scollati() -> list[str]:
    """Cosa dicono i quattordici file, contro cio' che il codice conta adesso."""
    guai: list[str] = []
    for nome, ricava, regex in NUMERI:
        atteso = ricava()
        trovato_da_qualche_parte = False
        for dove, percorso in posti().items():
            testo, _ = leggi_disco(percorso)
            for r in regex:
                for m in re.finditer(r, testo):
                    trovato_da_qualche_parte = True
                    if int(m.group("n")) != atteso:
                        guai.append(
                            f"{dove}: {nome} dice {m.group('n')} "
                            f"ma il codice ne conta {atteso}"
                        )
        if not trovato_da_qualche_parte:
            # **Zero trovati e' un guasto, non uno zero.** Senza questa riga il
            # numero potrebbe sparire da tutti e quattordici i file e nessuno lo
            # saprebbe: e' la forma «una verifica che tace su cio' che nessuno le
            # ha detto di cercare», gia' pagata con i marcatori dei cataloghi.
            guai.append(f"{nome}: la frase non si trova piu' in nessuno dei "
                        f"quattordici file — le ancore vanno rifatte")
    return sorted(set(guai))


def riscrivi_numeri() -> list[str]:
    """Mette le cifre giuste dove c'erano quelle vecchie. Torna i file cambiati."""
    cambiati: list[str] = []
    for _nome, ricava, regex in NUMERI:
        nuovo = str(ricava())
        for dove, percorso in posti().items():
            testo, _ = leggi_disco(percorso)
            dopo = testo
            for r in regex:
                dopo = _rifai(dopo, re.compile(r), nuovo)
            if dopo != testo:
                scrivi_disco(percorso, dopo)
                cambiati.append(dove)
    return sorted(set(cambiati))


# ========================================================= la vetrina =====
#
# Qui non c'e' nessuna regex di lingua, ed e' il punto: un catalogo e' un
# dizionario `{inglese -> tradotto}`, quindi le domande si fanno sui dati.

_STRINGA = re.compile(r'"((?:[^"\\]|\\.)*)"')
_CIFRE = re.compile(r"\d[\d.,]*")


def _pulisci(cifre: list[str]) -> list[str]:
    """`1,6` e `1.6` sono lo stesso numero con la virgola decimale di un'altra lingua."""
    return [c.replace(",", ".").rstrip(".") for c in cifre]


def _dis(grezza: str) -> str:
    """Una stringa JavaScript come la legge il browser, non come sta sul disco.

    **Le due cose differiscono, e la differenza si legge come un guasto.** Dentro
    una voce del catalogo ci puo' stare un `<a href=\\"...\\">`, quindi sul disco
    ci sono delle virgolette scappate: confrontare la forma grezza di un file con
    quella disfatta di un altro fa risultare *orfane* tre chiavi che ci sono —
    che e' peggio di non controllare, perche' e' un allarme che insegna a non
    guardare.
    """
    try:
        return ast.literal_eval('"' + grezza.replace("'", "\\'") + '"')
    except (SyntaxError, ValueError):
        return grezza


def _stringhe_di(percorso: Path) -> list[str]:
    """Tutte le stringhe fra virgolette doppie di un file JavaScript.

    Si legge cosi' e non con un analizzatore JS perche' `en.js` **e' insieme la
    struttura della pagina e il suo testo**: qui serve solo l'insieme delle
    stringhe che ci compaiono, e un elenco piu' largo del vero non puo' produrre
    falsi allarmi — puo' solo lasciar passare una chiave che nessuno usa.
    """
    return [_dis(m.group(1))
            for m in _STRINGA.finditer(leggi_disco(percorso)[0])]


def _coppie(percorso: Path) -> list[tuple[str, str]]:
    """Le voci `"chiave": "valore",` di un catalogo tradotto, una per riga.

    I cataloghi sono **generati** (`tools/traduci_ui.py` per la finestra, il
    generatore della vetrina qui), e il generatore scrive una voce per riga: si
    puo' quindi leggere una riga per volta invece di analizzare il JavaScript.
    Una riga che non ha quella forma non e' una voce e non interessa.
    """
    coppie: list[tuple[str, str]] = []
    for riga in leggi_disco(percorso)[0].splitlines():
        riga = riga.strip()
        if not riga.startswith('"'):
            continue
        pezzi = _STRINGA.findall(riga)
        if len(pezzi) < 2 or '": "' not in riga:
            continue
        # La chiave e' la prima stringa; il valore e' tutto il resto della riga
        # dopo il separatore — dentro puo' esserci un `<a href="...">`, che di
        # stringhe ne aggiunge un'altra.
        valore = riga.split('": "', 1)[1].rsplit('"', 1)[0]
        coppie.append((_dis(pezzi[0]), _dis(valore)))
    return coppie


def vetrina() -> list[str]:
    """I sei cataloghi contro `en.js`: chiavi orfane e cifre rimaste indietro."""
    guai: list[str] = []
    universo = set(_stringhe_di(SITO)) | set(_stringhe_di(SITO.parent.parent / "livedub.js"))
    for catalogo in sorted(SITO.parent.glob("*.js")):
        if catalogo == SITO:
            continue
        coppie = _coppie(catalogo)
        if not coppie:
            guai.append(f"sito/{catalogo.stem}: non ci leggo nessuna voce")
            continue
        for chiave, valore in coppie:
            if chiave not in universo:
                guai.append(
                    f"sito/{catalogo.stem}: la chiave «{chiave[:60]}…» non sta piu' "
                    f"in en.js — quella voce non traduce piu' niente")
            # Le cifre si confrontano **normalizzate**: `1.6` e `1,6` sono lo
            # stesso numero scritto con la virgola decimale di un'altra lingua, e
            # segnalarlo vorrebbe dire un elenco di falsi allarmi lungo quanto il
            # catalogo — cioe' un controllo che nessuno rilegge.
            atteso = Counter(_pulisci(_CIFRE.findall(chiave)))
            dette = Counter(_pulisci(_CIFRE.findall(valore)))
            perse = sorted((atteso - dette).elements())
            if perse:
                guai.append(
                    f"sito/{catalogo.stem}: «{chiave[:50]}…» dichiara "
                    f"{', '.join(perse)} e la traduzione non lo dice "
                    f"(li' ci sono {', '.join(sorted(dette.elements())) or 'nessun numero'})")
    return guai


# ======================================= le due impaginazioni della stessa cosa =====
#
# `README.md` e `site/i18n/en.js` raccontano le stesse cose con la stessa prosa,
# e cosi' ognuna delle altre sei coppie. Da qui un confronto che **non ha bisogno
# di ancore**: si toglie la cifra da una frase e quello che resta e' la chiave con
# cui la frase si ritrova nell'altro file. Dove le due frasi senza numeri sono
# identiche e i numeri no, uno dei due e' rimasto indietro.

_TAG = re.compile(r"<[^>]+>")
_SEGNI = re.compile(r"[`*_>#—– «»’']")
_UN_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")


def _liscia(s: str) -> str:
    """Il testo senza il vestito: niente tag, niente asterischi, spazi normali."""
    s = _TAG.sub(" ", s).replace('\\"', '"').replace("\\n", " ")
    return re.sub(r"\s+", " ", _SEGNI.sub(" ", s)).strip()


def _frasi(pezzo: str):
    """Le frasi di un pezzo che hanno una cifra dentro e almeno sette parole.

    Sette e non una: una frase corta («52 lingue») si ripete uguale in posti che
    non c'entrano niente fra loro, e accoppiarli darebbe allarmi falsi. Sul
    giapponese e sul cinese, che non spaziano le parole, questa soglia lascia
    passare poche frasi — dieci invece di cinquanta — e va bene cosi': meglio
    dieci accoppiamenti veri che cinquanta accostamenti a caso.
    """
    for f in re.split(r"(?<=[.:;!?])\s+", _liscia(pezzo)):
        f = f.strip()
        if len(f.split()) >= 7 and _UN_NUMERO.search(f):
            yield f


def _pezzi_markdown(testo: str) -> list[str]:
    """Le celle delle tabelle una per una, i paragrafi ricuciti.

    Ricucire le righe e' la parte che decide: il Markdown va a capo a settanta
    colonne e la vetrina no, quindi una frase spezzata non somiglia a nessuna
    frase della vetrina. Senza questa riga si accoppiano otto frasi invece di
    cinquantaquattro, e le altre quarantasei non le guarda nessuno.
    """
    testo = re.sub(r"```.*?```", " ", testo, flags=re.S)
    fuori: list[str] = []
    for blocco in re.split(r"\n\s*\n", testo):
        righe = [r.strip().lstrip("> ").strip() for r in blocco.splitlines()]
        if any(r.startswith("|") for r in righe):
            for r in righe:
                fuori.extend(r.split("|"))
        else:
            fuori.append(" ".join(righe))
    return fuori


def _per_frase(pezzi) -> dict[str, set[str]]:
    d: dict[str, set[str]] = {}
    for p in pezzi:
        for f in _frasi(p):
            d.setdefault(_UN_NUMERO.sub("•", f).lower(), set()).add(f)
    return d


def _cifre(f: str) -> tuple[str, ...]:
    return tuple(_pulisci(_UN_NUMERO.findall(f)))


def allineamento() -> list[str]:
    """Le stesse frasi nel README e nella vetrina, con dentro numeri diversi."""
    guai: list[str] = []
    for sigla, readme in READMES.items():
        catalogo = SITO.parent / f"{sigla}.js"
        if not catalogo.exists():
            guai.append(f"{sigla}: manca il catalogo della vetrina {catalogo.name}")
            continue
        a = _per_frase(_stringhe_di(catalogo))
        b = _per_frase(_pezzi_markdown(leggi_disco(readme)[0]))
        for chiave in sorted(set(a) & set(b)):
            if {_cifre(x) for x in a[chiave]} != {_cifre(x) for x in b[chiave]}:
                guai.append(
                    f"{sigla}: la stessa frase dice due cose — "
                    f"vetrina «{sorted(a[chiave])[0][:90]}» / "
                    f"README «{sorted(b[chiave])[0][:90]}»")
    return guai


# ============================ i motori nominati, e i numeri che gli stanno accanto =====

MOTORI = ("piper", "supertonic", "kokoro")


def _quante_lingue() -> tuple[dict[str, int], int]:
    """Quante lingue parla ogni motore, e quante ne parla l'unione dei tre."""
    from speak.pool import lingue_con_voce

    per_motore = {m: set(lingue_con_voce(m)) for m in MOTORI}
    unione = set().union(*per_motore.values())
    return {m: len(v) for m, v in per_motore.items()}, len(unione)


def _righe_di_tutti(percorso: Path):
    return enumerate(leggi_disco(percorso)[0].splitlines(), 1)


def unione_in_prosa() -> list[str]:
    """Dove si nominano i tre motori con i tre conteggi, ci va anche l'unione.

    Il pezzo si riconosce **dai dati e non dalla lingua**: i nomi dei motori non
    si traducono e le cifre nemmeno. La seconda guardia — nessun numero
    nell'intervallo in cui un'unione puo' stare che non sia l'unione — serve al
    caso in cui il numero vecchio e quello nuovo convivano: un 53 accanto a un 52
    e' un residuo, non una seconda quantita'.
    """
    per_motore, unione = _quante_lingue()
    conti = set(per_motore.values())
    minima, massima = max(conti), sum(conti)
    guai: list[str] = []
    for dove, percorso in posti().items():
        for n, riga in _righe_di_tutti(percorso):
            if not all(m in riga for m in MOTORI):
                continue
            numeri = {int(x) for x in re.findall(r"\d+", riga)}
            if not conti <= numeri:
                continue  # non e' la frase dei tre cataloghi
            if unione not in numeri:
                guai.append(
                    f"{dove}:{n}: la frase elenca {sorted(conti)} lingue per i tre "
                    f"motori e non dice l'unione, che il codice conta {unione}")
            for x in sorted(numeri - conti - {unione}):
                if minima < x <= massima:
                    guai.append(
                        f"{dove}:{n}: accanto ai tre conteggi c'e' {x}, che ha la "
                        f"forma di un'unione ma l'unione e' {unione}")
    return guai


#: Una riga di tabella che comincia con il nome di un motore. Il nome puo' avere
#: una parola dietro (`**piper** (default)`), e la cella che interessa e' quella
#: subito dopo: `**49**` nella tabella dei motori, `**0 su 49**` in quella delle
#: lingue misurate — e in giapponese `**49 中 0**`, che e' il motivo per cui si
#: guarda il numero **piu' grande** della cella e non il primo.
_RIGA_MOTORE = re.compile(
    r"\|\s*\*\*(" + "|".join(MOTORI) + r")\*\*[^|]*\|([^|]*)\|")


def misurate() -> list[str]:
    """Il numero accanto al nome di un motore e' il suo conteggio di lingue."""
    per_motore, _ = _quante_lingue()
    guai: list[str] = []
    for sigla, readme in READMES.items():
        for n, riga in _righe_di_tutti(readme):
            m = _RIGA_MOTORE.match(riga.strip())
            if not m:
                continue
            motore, cella = m.group(1), m.group(2)
            numeri = [int(x) for x in re.findall(r"\d+", cella)]
            if not numeri:
                continue  # una cella senza cifre non dichiara niente
            if max(numeri) != per_motore[motore]:
                guai.append(
                    f"{sigla}:{n}: la riga «{motore}» dichiara {max(numeri)} "
                    f"lingue e il codice ne conta {per_motore[motore]} "
                    f"(cella: «{cella.strip()[:40]}»)")
    return guai


# ============================== l'indirizzo delle donazioni, e dove non si guardava =====
#
# La verifica `dono` della suite confronta `core.dono.LINK` con
# `.github/FUNDING.yml`, pretende che l'indirizzo non stia scritto in nessun
# altro `.py`, e che i **sette README** puntino li'. La vetrina no — e li'
# l'indirizzo compare due volte, il bottone della donazione e la riga in fondo,
# cioe' nei due punti che vede **chiunque apra la pagina**: molti piu' di quanti
# aprano un README. Un indirizzo sbagliato non da' errore: da' la pagina di
# qualcun altro, o un 404, e i soldi non arrivano senza che niente lo dica.

#: **Il nome del sito non si scrive nemmeno qui**, e non e' scrupolo: scritto a
#: mano in questo file, la suite e' diventata rossa su `dono` — quella verifica
#: pretende che l'indirizzo non compaia in nessun `.py` che non sia
#: `core/dono.py`, e ha ragione, perche' questa regola nasce proprio contro
#: «scritto due volte e la seconda non l'aggiorna nessuno». Quindi l'ospite si
#: **ricava** da `core.dono.LINK`, e resta un posto solo.
def _indirizzo_atteso() -> tuple[str, re.Pattern]:
    from urllib.parse import urlsplit

    from core.dono import LINK

    ospite = urlsplit(LINK).netloc.removeprefix("www.")
    return LINK, re.compile(r"https?://(?:www\.)?" + re.escape(ospite) + r"/[\w-]+")


def donazioni() -> list[str]:
    """Ogni indirizzo di donazione della vetrina e' quello che il codice dichiara."""
    dichiarato, forma = _indirizzo_atteso()

    guai: list[str] = []
    dove = {"index.html": RADICE / "index.html",
            "sito/livedub.js": SITO.parent.parent / "livedub.js"}
    for catalogo in sorted(SITO.parent.glob("*.js")):
        dove[f"sito/{catalogo.stem}"] = catalogo

    trovato = False
    for nome, percorso in dove.items():
        if not percorso.exists():
            guai.append(f"{nome}: il file non c'e' piu'")
            continue
        for n, riga in _righe_di_tutti(percorso):
            for m in forma.finditer(riga):
                trovato = True
                if m.group(0) != dichiarato:
                    guai.append(
                        f"{nome}:{n}: l'indirizzo delle donazioni e' "
                        f"«{m.group(0)}» e il codice dichiara «{dichiarato}»")
    if not trovato:
        # **Zero trovati e' un guasto**, come per le ancore dei numeri: se il
        # bottone sparisse dalla vetrina questa regola tacerebbe per sempre.
        guai.append(
            "nella vetrina non c'e' nessun indirizzo di donazione: o il bottone e' "
            "sparito, o l'indirizzo e' passato a un altro sito")
    return guai


# ================================= i comandi che la pagina dice di incollare =====
#
# **Un comando che non esiste piu' e' peggio di un comando che manca**: chi lo
# incolla riceve `No module named tools.x` e conclude che il programma e' rotto.
# E la strada per cui succede e' gia' passata di qui — il commit «Il repo
# pubblicava anche il laboratorio» ha tolto dall'indice sette strumenti con una
# riga di `.gitignore`, e nessuna verifica lega quell'elenco a cio' che i sette
# README dicono di lanciare.
#
# Quindi non basta che il file **ci sia**: sul disco di chi sviluppa ci sono
# anche quelli non versionati, e leggere li' e' esattamente la misura che non
# puo' esprimere la risposta alla domanda «cosa trova chi scarica». Si chiede a
# `git ls-files`, che e' l'elenco di cio' che e' **pubblicato**.

_COMANDO = re.compile(r"-m\s+(tools\.[\w]+)")


def _pubblicati() -> set[str] | None:
    """I file che il repo pubblica. `None` se qui non c'e' git (uno zip)."""
    import subprocess

    try:
        fuori = subprocess.run(
            ["git", "ls-files"], cwd=RADICE, capture_output=True, text=True,
            timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return {r.strip() for r in fuori.stdout.splitlines() if r.strip()}


def comandi() -> list[str]:
    """Ogni `python -m tools.x` che i README e la vetrina dicono di incollare."""
    pubblicati = _pubblicati()
    guai: list[str] = []
    for dove, percorso in posti().items():
        for n, riga in _righe_di_tutti(percorso):
            for m in _COMANDO.finditer(riga):
                modulo = m.group(1)
                rel = modulo.replace(".", "/") + ".py"
                if pubblicati is None:
                    if not (RADICE / rel).exists():
                        guai.append(f"{dove}:{n}: «{modulo}» non c'e' su questo disco")
                elif rel not in pubblicati:
                    guai.append(
                        f"{dove}:{n}: la pagina dice di lanciare «{modulo}», e "
                        f"{rel} non e' fra i file che il repo pubblica"
                        + (" (c'e' solo su questo disco, quindi qui sembra a posto)"
                           if (RADICE / rel).exists() else ""))
    return guai


def controlla() -> list[str]:
    """Tutto insieme. Elenco vuoto = cio' che e' pubblicato dice il vero."""
    return (numeri_scollati() + vetrina() + allineamento()
            + unione_in_prosa() + misurate() + donazioni() + comandi())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="I numeri pubblicati e i cataloghi della vetrina, contro il codice.")
    ap.add_argument("--controlla", action="store_true",
                    help="non tocca niente: dice soltanto cosa si e' scollato")
    args = ap.parse_args(argv)

    for flusso in (sys.stdout, sys.stderr):
        try:
            flusso.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    for nome, ricava, _ in NUMERI:
        print(f"{nome}: {ricava()}")

    if not args.controlla:
        cambiati = riscrivi_numeri()
        print("riscritti: " + (", ".join(cambiati) if cambiati else "niente da cambiare"))

    guai = controlla()
    if guai:
        print(f"\n{len(guai)} cose scollate:")
        for g in guai:
            print(f"  - {g}")
        return 1
    print("\nREADME e vetrina dicono quello che dice il codice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
