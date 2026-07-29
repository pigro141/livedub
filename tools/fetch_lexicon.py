"""Scarica gli elenchi di parole italiane in `models/lexicon/`.

    python -m tools.fetch_lexicon

Serve al filtro sulla lingua di `vision/lexicon.py`, che e' l'ultimo cancello
fra l'OCR e le cuffie. Senza questi file il filtro **non c'e'** — e si dichiara
assente invece di far finta di lavorare — quindi la spazzatura di scena
(`'IIFIL'`, `'REEr'`, `"?1l'i1"`) torna a essere pronunciata.

Le due fonti fanno due lavori diversi e servono entrambe:

- `280000_parole_italiane` e' un elenco di **forme flesse**, comprese le
  parolacce. In un doppiaggio di GTA V non e' un dettaglio di colore: senza,
  `'Avevo rapinato banche,'` e `'protetto puttane,'` venivano scartate come non
  italiane, cioe' il filtro censurava invece di filtrare;
- `it_IT.dic` di LibreOffice sono i **lemmi**, e aggiunge una ventina di
  migliaia di parole che il primo non ha.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

DEST = Path("models/lexicon")

FONTI = {
    "280000_parole_italiane.txt": (
        "https://raw.githubusercontent.com/napolux/paroleitaliane/master/"
        "paroleitaliane/280000_parole_italiane.txt"
    ),
    "it_IT.dic": (
        "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/it_IT/it_IT.dic"
    ),
}


def main(argv: list[str] | None = None) -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    mancanti = 0
    for nome, url in FONTI.items():
        out = DEST / nome
        if out.exists() and out.stat().st_size > 1000:
            print(f"  {nome}: gia' presente ({out.stat().st_size/1024:.0f} KB)")
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "livedub"})
            with urllib.request.urlopen(req, timeout=120) as r:
                dati = r.read()
            out.write_bytes(dati)
            print(f"  {nome}: {len(dati)/1024:.0f} KB")
        except Exception as e:
            mancanti += 1
            print(f"  {nome}: FALLITO ({e})", file=sys.stderr)

    from vision.lexicon import carica

    lex = carica(DEST)
    if lex:
        print(f"\nlessico pronto: {len(lex)} parole")
        print(f"fonti: {lex.fonte}")
    else:
        print("\nlessico VUOTO: il filtro sulla lingua restera' spento.", file=sys.stderr)
    return 1 if mancanti else 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    raise SystemExit(main())
