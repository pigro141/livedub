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

## Cosa questo strumento **non** dice

Che il numero sia giusto *nel codice*: dice che quello pubblicato e' lo stesso
che il codice produce adesso. E non guarda la prosa attorno — se una frase
descrive male cio' che il numero conta, qui passa.
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

from tools.tabella_lingue import READMES, SITO  # noqa: E402

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
            testo = percorso.read_text(encoding="utf-8")
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
            testo = percorso.read_text(encoding="utf-8")
            dopo = testo
            for r in regex:
                dopo = _rifai(dopo, re.compile(r), nuovo)
            if dopo != testo:
                percorso.write_text(dopo, encoding="utf-8", newline="")
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
            for m in _STRINGA.finditer(percorso.read_text(encoding="utf-8"))]


def _coppie(percorso: Path) -> list[tuple[str, str]]:
    """Le voci `"chiave": "valore",` di un catalogo tradotto, una per riga.

    I cataloghi sono **generati** (`tools/traduci_ui.py` per la finestra, il
    generatore della vetrina qui), e il generatore scrive una voce per riga: si
    puo' quindi leggere una riga per volta invece di analizzare il JavaScript.
    Una riga che non ha quella forma non e' una voce e non interessa.
    """
    coppie: list[tuple[str, str]] = []
    for riga in percorso.read_text(encoding="utf-8").splitlines():
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


def controlla() -> list[str]:
    """Tutto insieme. Elenco vuoto = cio' che e' pubblicato dice il vero."""
    return numeri_scollati() + vetrina()


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
