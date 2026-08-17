"""Traduzione **in locale**: niente esce dalla macchina.

E' il default quando la traduzione si accende, e non per prestazioni: e' l'unica
delle due strade coerente con «uso completamente locale ed estrema privacy», che
questo progetto si e' messo fra gli obiettivi.

## Il pacchetto e' installato; la coppia di lingue si scarica da sola

Due cose diverse che questo file teneva insieme, e per una di loro aveva torto.

**Il pacchetto pip** e' una scelta di architettura, e adesso e' fatta: sta in
`requirements.txt`. Non entra piu' di nascosto alla prima battuta — entra
ricostruendo l'ambiente, che e' l'unico posto in cui un venv resta
ricostruibile. Costa caro e va saputo: `argostranslate` importa `stanza`, che
tira **torch** (+712 MB), e `minisbd` chiede `onnxruntime` (CPU), che con
`onnxruntime-gpu` **non convive** — installarlo di serie spegnerebbe la CUDA di
Kokoro in silenzio, 207 ms a battuta contro 725. Per questo in
`requirements.txt` quei due stanno con `--no-deps` e le dipendenze vere sono
elencate a mano.

**La coppia di lingue** e' un modello, cioe' dati, e si scarica **al primo uso**
come gia' fanno `vad=silero` e `ecapa-onnx` — che e' la regola di questo
progetto, non un'eccezione. Prima si sollevava con le istruzioni da digitare, e
l'utente finale non ha un prompt: aveva la finestra che diceva «traduco» e non
traduceva. Lo scaricamento **si dichiara** (una riga nel registro, prima di
partire) e succede ad Avvia, non a meta' battuta.

Resta vero il pezzo che contava: se non si riesce, **si solleva** invece di
ripiegare in silenzio su Google — che manderebbe fuori i dati proprio a chi
aveva chiesto di restare in locale.
"""

from __future__ import annotations

import sys


def coppia(da: str, a: str) -> tuple[str, str]:
    """La coppia di lingue, con `auto` risolto — **una regola sola**.

    `auto` non esiste per i modelli offline: un modello e' *di* quella coppia. Si
    assume l'inglese, che e' la lingua di partenza di quasi tutto. Sta qui e non
    in due metodi perche' risolvere `auto` in un posto e non nell'altro vuol dire
    scaricare un modello e usarne un altro.
    """
    da = (da or "en").strip()
    return ("en" if da == "auto" else da, (a or "it").strip())


class TraduttoreLocale:
    """Argos Translate: modelli offline, CPU, nessuna rete."""

    name = "locale"

    def __init__(self, modello: str = "", da: str = "", a: str = "", dillo=None) -> None:
        self.modello = modello
        self.da = da
        self.a = a
        # Chi lo racconta a chi sta guardando. Scaricare cento megabyte in
        # silenzio e' come non scaricarli: la finestra sembra bloccata.
        self.dillo = dillo or (lambda riga: print(riga, file=sys.stderr))
        self._fn = None

    # -- il modello della coppia di lingue -----------------------------------

    def prepara(self) -> bool:
        """Si assicura che la coppia sia installata, scaricandola se manca.

        Si chiama **alla costruzione** (cioe' ad Avvia), non alla prima battuta:
        un fermo di un minuto fra un sottotitolo e il successivo sarebbe una
        sessione rovinata, mentre prima di cominciare e' un'attesa dichiarata.
        Torna `True` se la coppia c'e' o e' stata installata adesso.
        """
        da, a = self.coppia()
        # **Stessa lingua da una parte e dall'altra: non c'e' niente da
        # scaricare.** Senza questa riga si andava a cercare in rete un modello
        # `en->en` che non esiste e non puo' esistere — e succedeva anche dentro
        # la suite, che la rete non deve toccarla mai.
        if da == a:
            return True
        try:
            import argostranslate.package as ap
        except ImportError:
            return False
        if any(p.from_code == da and p.to_code == a for p in ap.get_installed_packages()):
            return True
        # 98 MB misurati per it->en: si dice, perche' un'attesa dichiarata e'
        # un'attesa e un'attesa muta e' un blocco.
        self.dillo(f"traduzione: scarico il modello {da}->{a} (una volta sola, "
                   f"~100 MB) — resta in locale, non esce niente dal PC.")
        try:
            ap.update_package_index()
            scelto = next(
                (p for p in ap.get_available_packages()
                 if p.from_code == da and p.to_code == a), None)
            if scelto is None:
                self.dillo(f"! nessun modello {da}->{a} fra quelli pubblicati")
                return False
            ap.install_from_path(scelto.download())
        except Exception as e:  # pragma: no cover - dipende dalla rete
            self.dillo(f"! non riesco a scaricare il modello {da}->{a}: {e}")
            return False
        self.dillo(f"traduzione: modello {da}->{a} pronto")
        return True

    def scalda(self) -> None:
        """Una traduzione a vuoto, per pagare il caricamento **prima**.

        Misurato: la prima battuta costa 3950 ms e la seconda 28. Quei quattro
        secondi non sono il traduttore, sono CTranslate2 che apre il modello — e
        pagarli sulla prima battuta vera vuol dire perderla, perche' la catena
        nel frattempo ha gia' deciso i tempi. Pagarli qui vuol dire quattro
        secondi in piu' fra Avvia e la prima riga, che nessuno nota.
        """
        try:
            da, a = self.coppia()
            self._motore()("Pronto.", da, a)
        except Exception:  # pragma: no cover - se non riesce lo dira' la battuta
            pass

    def coppia(self) -> tuple[str, str]:
        """La coppia dichiarata alla costruzione, con `auto` risolto."""
        return coppia(self.da, self.a)

    def _motore(self):
        if self._fn is not None:
            return self._fn
        try:
            import argostranslate.translate as at
        except ImportError as e:  # pragma: no cover - dipende dall'ambiente
            raise RuntimeError(
                "argostranslate non installato: l'ambiente non e' quello di "
                "`requirements.txt`. Ricostruirlo, oppure:\n"
                "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n"
                "Accettando invece che i sottotitoli escano dalla macchina:\n"
                "  --set translate.backend=google"
            ) from e
        self._fn = at.translate
        return self._fn

    def traduci(self, testo: str, da: str, a: str) -> str | None:
        # La coppia della battuta vince su quella dichiarata alla costruzione,
        # ma passa dalla stessa risoluzione di `auto`: due regole diverse per la
        # stessa domanda sono il modo in cui si scarica un modello e se ne usa
        # un altro.
        sorgente, arrivo = coppia(da, a)
        fuori = self._motore()(testo, sorgente, arrivo)
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
