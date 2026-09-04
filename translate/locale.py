"""Traduzione **in locale**: niente esce dalla macchina.

E' il default quando la traduzione si accende, e non per prestazioni: e' l'unica
delle due strade coerente con «uso completamente locale ed estrema privacy», che
questo progetto si e' messo fra gli obiettivi.

## Il motore viaggia col programma; la coppia di lingue si scarica da sola

Due cose diverse che questo file teneva insieme, e per tutte e due aveva scritto
il numero sbagliato.

**Il motore** sta in `requirements.txt` piu' `requirements-nodeps.txt`, e
**dentro l'eseguibile**: sono i cinque pacchetti misurati qui sotto, che con lo
spezza-frasi scelto in fondo a questo commento **non tirano piu' torch**.

| pacchetto | MB in `site-packages` |
|---|---|
| `ctranslate2` | 61,8 |
| `sentencepiece` | 2,0 |
| `sacremoses` | 1,7 |
| `argostranslate` | 0,2 |
| `minisbd` | 0,1 |
| **totale** | **65,8** |
| `torch`, che non entra piu' | **3037,5** |

I «tre giga» che questo file dichiarava erano **tutti** torch, e torch la
traduzione non lo usa mai: Argos gira su CTranslate2. Lo tirava dentro `stanza`,
che serve solo allo *spezza-frasi*.

**La coppia di lingue** e' un modello, cioe' dati, e si scarica **al primo uso**
come gia' fanno `vad=silero` e `ecapa-onnx` — che e' la regola di questo
progetto, non un'eccezione. Prima si sollevava con le istruzioni da digitare, e
l'utente finale non ha un prompt: aveva la finestra che diceva «traduco» e non
traduceva. Lo scaricamento **si dichiara** (una riga nel registro, prima di
partire) e succede ad Avvia, non a meta' battuta.

Resta vero il pezzo che contava: se non si riesce, **si solleva** invece di
ripiegare in silenzio su Google — che manderebbe fuori i dati proprio a chi
aveva chiesto di restare in locale.

## Questo modulo e' **la porta** da cui argostranslate si importa

Come `core/onnx.py` per `preload_dlls()`: la riga che va eseguita prima non e'
una cosa da ricordarsi, e' una cosa che non puo' non succedere. Chi importa
`argostranslate` senza passare di qui prende lo spezza-frasi sbagliato **senza
nessun errore** — e nel pacchetto congelato non parte affatto. La verifica
`traduzione` legge il sorgente con `ast` e non lascia nascere un secondo
importatore.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path


def prepara_argos() -> None:
    """Le due righe che vanno eseguite **prima** di importare argostranslate.

    ## Lo spezza-frasi: MiniSBD e non quello di serie

    Il modo di serie (`ARGOSTRANSLATE`) non e' uno spezza-frasi, e' una scelta
    fatta guardando **il pacchetto della coppia di lingue**
    (`argostranslate/translate.py`: `if "stanza" in str(pkg.packaged_sbd_path)`).
    Sia `en_it` sia `it_en` portano una cartella `stanza/`, quindi la scelta cade
    su Stanza a ogni battuta — e stanza importa torch, tre giga per una cosa che
    la traduzione non usa. MiniSBD fa lo stesso lavoro con un `.onnx` da **178
    KB**, su un onnxruntime che c'e' gia'.

    E non e' una rinuncia: misurato sulle stesse dodici battute, **12 uscite su
    12 identiche carattere per carattere**, prima battuta **201 ms invece di
    1422** e p50 **26,9 invece di 32,1** — cioe' `stanza.Pipeline` era la cosa
    lenta. (Le due che spezzano male le spezzano **uguale**: «Ehi. Ehi! Torna qui
    subito. Non scherzo.» perde tre frasi con tutti e due.)

    `os.environ` e non un parametro perche' `argostranslate/settings.py` legge
    `ARGOS_CHUNK_TYPE` **all'import del modulo**: metterlo dopo non fa niente, e
    non da' errore — che e' la forma peggiore.

    ## `ARGOS_STANZA_AVAILABLE` non esiste, e vale la pena saperlo

    Sembrerebbe la leva giusta — argos la offre per dire «stanza non c'e'» — ma
    nella 1.11.0 quella riga sta **dentro una stringa a tripli apici**, cioe' e'
    codice spento: misurato, `hasattr(argostranslate.settings,
    "stanza_available")` e' `False`. Scriverla sarebbe la decima volta della
    forma «dichiarato e mai letto», stavolta autoinflitta.

    ## Lo stub di `stanza`, e perche' **non vince** su quello vero

    `sbd.py` fa `import stanza` in cima al modulo anche quando non lo usa (su
    `master` e' gia' dentro un `try`, commit `17ed1a9b`: questo anticipa la
    1.11.1). Dentro il pacchetto congelato stanza non c'e', quindi senza un
    finto in `sys.modules` la traduzione non si importa affatto.

    Ma il finto si mette **solo se quello vero non si importa**, e sta in
    `sys.modules` e non in un file `stanza.py` del repo: uno stub che vince su un
    pacchetto vero e' un difetto silenzioso, e chi sviluppa stanza ce l'ha
    installato. E se qualcuno ha chiesto lo spezza-frasi di Stanza a mano
    (`ARGOS_CHUNK_TYPE=STANZA`) non si tocca niente.

    Il finto **solleva** invece di rispondere `None`: un attributo mancante
    diventerebbe un `TypeError` lontanissimo da qui. I dunder no — `__path__` e
    compagni li chiede l'importatore, e li' l'unica risposta giusta e'
    `AttributeError`.
    """
    # Prima di tutto, perche' e' cio' che `settings.py` legge all'import.
    os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
    try:
        import argostranslate.settings as st
    except Exception:
        # Argos non c'e' ancora (o e' bloccato): non c'e' niente da preparare, e
        # la riga di sopra vale gia' per quando ci sara'. Chi lo installa a
        # sessione accesa ripassa di qui, perche' `_motore()` e `prepara()`
        # richiamano questa funzione.
        return
    if st.chunk_type is st.ChunkType.STANZA or "stanza" in sys.modules:
        return
    try:
        import stanza  # noqa: F401 — quello vero vince, se c'e'
        return
    except ImportError:
        pass

    finto = types.ModuleType("stanza")
    finto.__doc__ = ("Segnaposto: argostranslate lo importa in cima a `sbd.py` "
                     "anche quando non lo usa. Si veda translate/locale.py.")

    def manca(nome: str):
        if nome.startswith("__"):
            raise AttributeError(nome)
        raise RuntimeError(
            f"stanza non e' installato e qualcuno ne ha chiesto «{nome}»: "
            f"lo spezza-frasi in uso e' {st.chunk_type.name}, che non lo usa. "
            "Se serve davvero Stanza, va installato (e si porta dietro torch).")

    finto.__getattr__ = manca
    sys.modules["stanza"] = finto


prepara_argos()


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
        prepara_argos()
        try:
            import argostranslate.package as ap
        except ImportError:
            return False
        if any(p.from_code == da and p.to_code == a for p in ap.get_installed_packages()):
            return self._spezza_frasi(da)
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
        return self._spezza_frasi(da)

    def _spezza_frasi(self, da: str) -> bool:
        """Il modello che spezza le frasi: **178 KB, presi adesso e non a meta' battuta**.

        MiniSBD se lo scarica da solo alla prima frase, e senza rete morirebbe
        **dopo** che questa funzione ha dichiarato «pronta» — che e' esattamente
        il ripiego silenzioso girato dall'altra parte. Cento megabyte di coppia e
        centosettantotto kilobyte di spezza-frasi sono la stessa attesa, e vanno
        pagati nello stesso posto: prima di cominciare.

        Torna `False` se non c'e', perche' senza di lui la prima battuta solleva.
        """
        try:
            from argostranslate import sbd  # imposta la cartella della cache
            from minisbd import models as mm
        except Exception as e:  # pragma: no cover - dipende dall'ambiente
            self.dillo(f"! lo spezza-frasi non si importa: {e}")
            return False
        lingua = sbd.MiniSBDSentencizer.LANGUAGE_CODE_MAPPING.get(da, da)
        if lingua not in mm.list_models():
            # Lo stesso ripiego che fa `MiniSBDSentencizer`: una lingua senza
            # modello si spezza con quello inglese. Scritto qui perche' se no si
            # scaricherebbe un file e se ne cercherebbe un altro.
            lingua = "en"
        if (Path(mm.cache_dir) / f"{lingua}.onnx").is_file():
            return True
        self.dillo(f"traduzione: prendo lo spezza-frasi {lingua} (178 KB)")
        try:
            mm.get_model_file(lingua)
        except Exception as e:  # pragma: no cover - dipende dalla rete
            self.dillo(f"! lo spezza-frasi {lingua} non e' arrivato: {e}")
            return False
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
        # Ripassa di qui anche chi ha installato argos a sessione accesa (il
        # passo 6 della guida lo fa): la prima volta, allora, non c'era niente da
        # preparare. E' idempotente.
        prepara_argos()
        try:
            import argostranslate.translate as at
        except ImportError as e:  # pragma: no cover - dipende dall'ambiente
            raise RuntimeError(
                "argostranslate non installato: l'ambiente non e' quello di "
                "`requirements.txt`. Ricostruirlo, oppure:\n"
                "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n"
                "  .\\.venv\\Scripts\\python.exe -m pip install -r "
                "requirements-nodeps.txt --no-deps\n"
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
    """Scarica la coppia di lingue **e il suo spezza-frasi**. A mano, una volta.

    Passa da `TraduttoreLocale.prepara()` invece di rifare le stesse chiamate:
    due strade per scaricare la stessa cosa sono due strade che si scollano — e
    questa si era gia' scollata, perche' non prendeva i 178 KB di MiniSBD.
    """
    tr = TraduttoreLocale(da=da, a=a, dillo=lambda riga: print(riga, file=sys.stderr))
    if not tr.prepara():
        return 1
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
