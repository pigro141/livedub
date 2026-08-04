"""Traduzione **in locale**: niente esce dalla macchina.

E' il default quando la traduzione si accende, e non per prestazioni: e' l'unica
delle due strade coerente con «uso completamente locale ed estrema privacy», che
questo progetto si e' messo fra gli obiettivi.

## Il modello non si scarica da qui

`argostranslate` (che sotto usa CTranslate2, CPU, offline) va installato e la
coppia di lingue va scaricata **una volta**, esplicitamente:

    .\\.venv\\Scripts\\python.exe -m pip install argostranslate
    .\\.venv\\Scripts\\python.exe -m translate.locale --scarica en it

Non lo fa questo modulo all'avvio, e la ragione e' la stessa per cui
`requirements.txt` monta `onnxruntime-gpu` e non `onnxruntime`: cosa entra
nell'ambiente e' una scelta di architettura, non un effetto collaterale della
prima battuta. Un pacchetto tirato dentro di nascosto la prima volta che serve e'
il modo in cui un venv smette di essere ricostruibile.

**Se manca, si solleva con le istruzioni** invece di ripiegare in silenzio su
Google — che manderebbe fuori i dati proprio a chi aveva chiesto di restare in
locale, ed e' esattamente il ripiego che questo progetto considera peggiore di un
errore.
"""

from __future__ import annotations

import sys


class TraduttoreLocale:
    """Argos Translate: modelli offline, CPU, nessuna rete."""

    name = "locale"

    def __init__(self, modello: str = "") -> None:
        self.modello = modello
        self._fn = None

    def _motore(self):
        if self._fn is not None:
            return self._fn
        try:
            import argostranslate.translate as at
        except ImportError as e:  # pragma: no cover - dipende dall'ambiente
            raise RuntimeError(
                "argostranslate non installato. In locale:\n"
                "  .\\.venv\\Scripts\\python.exe -m pip install argostranslate\n"
                "  .\\.venv\\Scripts\\python.exe -m translate.locale --scarica en it\n"
                "Oppure, accettando che i sottotitoli escano dalla macchina:\n"
                "  --set translate.backend=google"
            ) from e
        self._fn = at.translate
        return self._fn

    def traduci(self, testo: str, da: str, a: str) -> str | None:
        # `auto` non esiste per i modelli offline: la coppia va dichiarata, perche'
        # un modello e' *di* quella coppia. Si assume l'inglese, che e' la lingua
        # di partenza di quasi tutto, e lo si dice.
        sorgente = "en" if (da or "auto") == "auto" else da
        fuori = self._motore()(testo, sorgente, a or "it")
        fuori = (fuori or "").strip()
        return fuori or None


def _scarica(da: str, a: str) -> int:
    """Scarica la coppia di lingue. Si invoca a mano, una volta."""
    try:
        import argostranslate.package as ap
    except ImportError:
        print("argostranslate non installato: `pip install argostranslate`", file=sys.stderr)
        return 1
    ap.update_package_index()
    disponibili = ap.get_available_packages()
    scelto = next((p for p in disponibili if p.from_code == da and p.to_code == a), None)
    if scelto is None:
        print(f"nessun pacchetto {da}->{a}", file=sys.stderr)
        return 1
    ap.install_from_path(scelto.download())
    print(f"installato {da}->{a}")
    return 0


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Modelli di traduzione offline.")
    p.add_argument("--scarica", nargs=2, metavar=("DA", "A"))
    args = p.parse_args()
    if args.scarica:
        raise SystemExit(_scarica(*args.scarica))
    p.print_help()
