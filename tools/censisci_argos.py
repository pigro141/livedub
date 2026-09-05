"""L'indice dei pacchetti Argos: si guarda una volta, e si scrive nel repo.

`translate/argos_lingue.py` e' un elenco **committato**, per la stessa ragione
delle 133 lingue di Google e delle 175 voci Piper: un elenco che dipende dalla
rete si svuota quando la rete non c'e', e un menu vuoto **non da' errore**. Un
elenco fermo invecchia, ma invecchia in modo visibile — e questo comando dice in
dieci secondi se e' invecchiato.

    .\\.venv\\Scripts\\python.exe -m tools.censisci_argos            # cosa c'e' nell'indice
    .\\.venv\\Scripts\\python.exe -m tools.censisci_argos --blocco   # il blocco da incollare
    .\\.venv\\Scripts\\python.exe -m tools.censisci_argos --controlla # e' cambiato qualcosa?

**Il file non si sovrascrive da qui**, ed e' la stessa scelta gia' presa per
`speak/backends/piper_voci.py`: quel file e' codice sorgente con dentro i
commenti che dicono *perche'*, e un generatore che riscrive codice sorgente e' il
modo di perderli. Si stampa il blocco e lo si incolla.

**`--controlla` e' la meta' che conta.** Senza, «l'elenco invecchia in modo
visibile» resta una frase: nessuno va a riguardare l'indice. Con, la differenza
si legge in due righe — quali coppie sono comparse e quali sono sparite — e la
data scritta nel commento del file diventa una data che qualcuno puo' smentire.
"""

from __future__ import annotations

import argparse
import datetime
import sys

# **Da qui e non da `argostranslate.package` direttamente**: `translate/locale.py`
# e' la porta da cui argostranslate si importa in questo progetto (ci mette lo
# spezza-frasi giusto prima). Importarlo altrove prende quello sbagliato senza
# nessun errore, e la verifica `traduzione` legge il sorgente per non lasciare
# nascere un secondo importatore.
from translate.locale import prepara_argos


def coppie_pubblicate() -> frozenset[tuple[str, str]]:
    """Le coppie dell'indice ufficiale. **Tocca la rete**, quindi sta qui e non
    in `translate/`: nessun modulo del programma deve poterle chiedere a caldo."""
    prepara_argos()
    import argostranslate.package as ap

    ap.update_package_index()
    return frozenset((p.from_code, p.to_code) for p in ap.get_available_packages())


def _blocco(coppie: frozenset[tuple[str, str]]) -> str:
    """Il letterale Python da incollare in `translate/argos_lingue.py`."""
    oggi = datetime.date.today().isoformat()
    righe = [
        "# Le coppie pubblicate nell'indice Argos, **in codici Argos**.",
        f"# Rigenerato il {oggi} con:",
        "#     .\\.venv\\Scripts\\python.exe -m tools.censisci_argos --blocco",
        "COPPIE: frozenset[tuple[str, str]] = frozenset({",
    ]
    da_codici = sorted({a for a, _ in coppie})
    for a in da_codici:
        # Una riga per lingua di partenza, a capo ogni cinque: se no il
        # `git diff` dice «una riga cambiata» dove sono cambiate due coppie.
        pezzi = [f'("{a}", "{b}")' for b in sorted(b for x, b in coppie if x == a)]
        for i in range(0, len(pezzi), 5):
            righe.append("    " + ", ".join(pezzi[i:i + 5]) + ",")
    righe.append("})")
    return "\n".join(righe)


def _censimento(coppie: frozenset[tuple[str, str]]) -> None:
    from translate.lingue import PER_CODICE, normalizza

    codici = sorted({a for a, _ in coppie} | {b for _, b in coppie})
    senza_perno = sorted(c for c in coppie if c[0] != "en" and c[1] != "en")
    print(f"indice Argos: {len(coppie)} coppie, {len(codici)} codici")
    print(f"  coppie che non toccano l'inglese: {len(senza_perno)} {senza_perno}")
    fuori = [c for c in codici if c not in PER_CODICE]
    print(f"  codici che NON sono codici Google: {len(fuori)}")
    for c in fuori:
        n = normalizza(c)
        print(f"    {c:4} -> normalizza -> {n:8} "
              f"{'(in tabella)' if n in PER_CODICE else '(fuori tabella)'}")


def _controlla(coppie: frozenset[tuple[str, str]]) -> int:
    """Confronta l'indice vero con quello committato. Torna 1 se sono diversi."""
    from translate.argos_lingue import COPPIE

    comparse = sorted(coppie - COPPIE)
    sparite = sorted(COPPIE - coppie)
    if not comparse and not sparite:
        print(f"l'elenco committato e' quello dell'indice ({len(COPPIE)} coppie)")
        return 0
    print(f"! l'elenco committato ha {len(COPPIE)} coppie, l'indice {len(coppie)}")
    if comparse:
        print(f"  comparse nell'indice: {comparse}")
    if sparite:
        print(f"  sparite dall'indice:  {sparite}")
    print("  -> rigenerare con --blocco e incollare in translate/argos_lingue.py")
    return 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--blocco", action="store_true",
                   help="stampa il letterale da incollare nel modulo")
    p.add_argument("--controlla", action="store_true",
                   help="dice se l'elenco committato e' invecchiato")
    a = p.parse_args(argv)

    try:
        coppie = coppie_pubblicate()
    except Exception as e:  # pragma: no cover - dipende dalla rete
        print(f"! non riesco a leggere l'indice Argos: {e}", file=sys.stderr)
        return 2

    if a.blocco:
        print(_blocco(coppie))
        return 0
    if a.controlla:
        return _controlla(coppie)
    _censimento(coppie)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
