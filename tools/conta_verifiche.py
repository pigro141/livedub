"""Quante verifiche ha la suite, **secondo quello che il repo pubblica**.

## Perche' esiste

README e vetrina dicono a chi decide se installare che c'e' una suite di *tante*
verifiche in *tanti* gruppi. E' l'unica cifra di quella pagina che non viene da
una misura archiviata: viene da qualcuno che ha guardato l'ultima riga della
suite e l'ha copiata a mano in quattordici file, in sette lingue.

Il risultato e' quello prevedibile, e c'era gia': **2085 in 78 gruppi**, quando
erano 2174 in 81 — e nel README giapponese e in quello cinese *76*, che vuol
dire che i quattordici avevano gia' cominciato a dire cose diverse fra loro. Un
numero vecchio non da' nessun errore: non c'e' niente che si rompa, si dice solo
il falso a chi legge.

Il conteggio dei **gruppi** una verifica ce l'ha (la suite confronta i quattordici
file con `len(GROUPS)`), e la puo' avere perche' quel numero si sa **prima** di
girare. Il conteggio delle **verifiche** no: mentre la suite conta, sta ancora
contando anche se stessa. Una verifica che non puo' esprimere la risposta e'
peggio di una che manca — quindi la risposta la da' uno strumento, che la suite
la fa **girare** e poi ne legge l'ultima riga.

## Come si usa

    python -m tools.conta_verifiche --controlla   # dice cosa si e' scollato
    python -m tools.conta_verifiche               # lo riscrive nei quattordici

Costa quanto una passata della suite: qualche minuto. Si lancia quando si e'
aggiunto o tolto qualcosa, non a ogni commit.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from tools.tabella_lingue import READMES, SITO


def posti() -> dict[str, Path]:
    """I quattordici file in cui quel numero e' scritto.

    Sette README e **sette** cataloghi della vetrina, non uno: nei sei tradotti
    la cifra compare **due volte**, perche' la chiave e' la frase inglese e il
    valore e' la sua traduzione. Riscrivere il solo `en.js` cambierebbe la chiave
    e lascerebbe indietro le sei copie — cioe' sei chiavi che non corrispondono
    piu' a niente, e la vetrina tornerebbe in inglese in quel paragrafo, in tutte
    le lingue, **senza dare errore**.
    """
    fuori = dict(READMES)
    for catalogo in sorted(SITO.parent.glob("*.js")):
        fuori[f"sito/{catalogo.stem}"] = catalogo
    return fuori

#: L'ultima riga della suite: «2202/2202 verifiche verdi.» Si legge da li' e non
#: si conta a mano nessuna `c.ok`, perche' molte stanno dentro dei cicli e il
#: loro numero dipende da quante lingue, quanti motori e quanti campi ci sono —
#: cioe' proprio dalle cose che cambiano.
RIGA = re.compile(r"(\d+)\s*/\s*(\d+)\s+verifiche verdi")

#: Dove il numero e' scritto, in ognuna delle sette lingue. Ogni voce e' una
#: regex con **un solo** gruppo, che e' la cifra: cosi' la sostituzione non deve
#: sapere niente della frase che ci sta intorno. La parola che precede o segue e'
#: quella che non si traduce mai allo stesso modo, quindi si ancora al numero
#: piu' la sua unita'.
DOVE: tuple[re.Pattern, ...] = (
    # `**2202 verifiche**`, `**2202 checks**`, `**2202 Prufungen**`, ...
    re.compile(r"(?<![\d.,])(\d{3,5})(?=\s*\n?\s*"
               r"(?:verifiche|checks|Prüfungen|comprobaciones|vérifications))"),
    # **Giapponese e cinese scrivono il numero prima del contatore**, e qui il
    # classificatore da solo non basta: in giapponese `170 個のパラメータ` sono i
    # campi di configurazione, e ancorarsi al solo `個の` riscriverebbe **quello**
    # con il numero delle verifiche. Si chiede quindi anche la parola dopo — che
    # in giapponese sta sulla riga successiva, perche' quel paragrafo va a capo.
    re.compile(r"(?<![\d.,])(\d{3,5})(?=\s*個の\s*検査)"),
    re.compile(r"(?<![\d.,])(\d{3,5})(?=\s*项检查)"),
)


def misura() -> int:
    """Fa girare la suite e legge quante verifiche ha contato. **Non le conta lei.**

    Contarle leggendo il sorgente non si puo': una buona parte delle `c.ok` sta
    dentro dei cicli sulle lingue, sui motori e sui campi di configurazione,
    quindi il loro numero dipende da cose che cambiano. L'unico posto che lo sa e'
    la suite mentre gira.
    """
    fuori = subprocess.run(
        [sys.executable, "-m", "tools.selftest"],
        cwd=str(Path(__file__).resolve().parent.parent),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    trovate = RIGA.findall(fuori.stdout or "")
    if not trovate:
        raise RuntimeError("la suite non ha stampato la riga del conteggio: "
                           + (fuori.stdout or fuori.stderr or "")[-300:])
    passate, totali = trovate[-1]
    if passate != totali:
        raise RuntimeError(f"la suite non e' verde ({passate}/{totali}): il numero "
                           f"pubblicato si aggiorna solo da una suite verde")
    return int(totali)


def dichiarati() -> dict[str, list[int]]:
    """I numeri scritti adesso in ognuno dei quattordici posti."""
    fuori: dict[str, list[int]] = {}
    for nome, percorso in posti().items():
        testo = percorso.read_text(encoding="utf-8")
        fuori[nome] = [int(m) for r in DOVE for m in r.findall(testo)]
    return fuori


def scrivi(quante: int) -> list[str]:
    """Mette `quante` dove c'era il numero vecchio. Torna i file cambiati.

    **Si riscrive solo la cifra**, non la frase: le sei traduzioni sono state
    fatte una volta e non devono ripassare da un traduttore per un numero. E' la
    stessa regola di `tools/tabella_lingue.py` — si rigenera il dato, si lascia
    stare la prosa.
    """
    cambiati: list[str] = []
    for nome, percorso in posti().items():
        testo = percorso.read_text(encoding="utf-8")
        nuovo = testo
        for r in DOVE:
            nuovo = r.sub(str(quante), nuovo)
        if nuovo != testo:
            percorso.write_text(nuovo, encoding="utf-8", newline="")
            cambiati.append(nome)
    return cambiati


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Il numero di verifiche pubblicato: controllarlo o rifarlo.")
    ap.add_argument("--controlla", action="store_true",
                    help="dice soltanto cosa si e' scollato, senza toccare niente")
    args = ap.parse_args(argv)

    prima = dichiarati()
    vuoti = [n for n, v in prima.items() if not v]
    if vuoti:
        # **Un file in cui la regex non trova niente e' un guasto, non uno zero.**
        # Senza questa riga il numero sparirebbe da un file e nessuno lo saprebbe:
        # e' la forma «una verifica che tace su cio' che nessuno le ha detto di
        # cercare», gia' pagata con i marcatori dei cataloghi.
        print(f"in questi file il numero non si trova affatto: {', '.join(vuoti)}")
        return 2

    print("sto facendo girare la suite (qualche minuto)…")
    quante = misura()
    print(f"la suite conta {quante} verifiche")

    fuori = {n: sorted(set(v)) for n, v in prima.items() if set(v) != {quante}}
    if not fuori:
        print("i quattordici posti lo dicono gia' giusto")
        return 0
    for nome, valori in sorted(fuori.items()):
        print(f"  {nome:10} dice {', '.join(map(str, valori))} invece di {quante}")
    if args.controlla:
        return 1
    cambiati = scrivi(quante)
    print(f"riscritto in {len(cambiati)}: {', '.join(cambiati)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
