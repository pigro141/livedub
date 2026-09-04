"""L'ambiente della traduzione offline e' a posto **e la GPU e' ancora accesa**.

Esiste perche' il modo naturale di installare Argos rompe la sintesi in silenzio:
`argostranslate` tira `minisbd`, che dipende da `onnxruntime` (CPU), che scrive
nella stessa cartella di `onnxruntime-gpu`. Da quel momento Kokoro costa 725 ms
a battuta invece di 207 e **nessun errore lo dice** — e' il ripiego silenzioso
che questo progetto ha gia' pagato con `preload_dlls()`.

Le tre domande, in ordine di quanto fanno male:

1. c'e' il pacchetto `onnxruntime` (CPU) accanto a `onnxruntime-gpu`?
2. ORT vede ancora la CUDA?
3. `argostranslate` si importa davvero? (`--no-deps` puo' lasciarne fuori una)

Si usa da riga di comando (esce con 1 se qualcosa non va, cosi' lo script di
installazione se ne accorge) e dalla suite, che chiama `controlla()`.
"""

from __future__ import annotations

import importlib.metadata as md

# **La porta, e sta in cima al modulo apposta.** `translate.locale` mette
# `ARGOS_CHUNK_TYPE` nell'ambiente e il segnaposto di `stanza` in `sys.modules`
# prima che argostranslate venga importato; aprirla piu' in basso di un import di
# argos non farebbe niente e non darebbe errore. La verifica `argos` legge questo
# file con `ast` e guarda i numeri di riga, non la presenza.
import translate.locale  # noqa: F401,E402


def _spezza_frasi() -> str:
    """Quale spezza-frasi e' in uso, detto invece che supposto.

    Non e' una curiosita': quello di serie sceglie **Stanza** — che tira torch,
    tre giga per una cosa che la traduzione non usa — e la differenza non da'
    nessun errore. Si veda `translate.locale.prepara_argos`.
    """
    try:
        from argostranslate import settings

        return f"spezza-frasi {settings.chunk_type.name}"
    except Exception as e:  # pragma: no cover - dipende dall'ambiente
        return f"spezza-frasi ignoto ({e})"


def controlla(vuole_cuda: bool = True) -> tuple[bool, list[str]]:
    """`(va_bene, righe)`. Le righe si stampano cosi' come sono."""
    righe: list[str] = []
    bene = True

    nomi = {
        (d.metadata["Name"] or "").lower()
        for d in md.distributions()
        if d.metadata["Name"]
    }
    if "onnxruntime" in nomi:
        bene = False
        righe.append(
            "! e' installato il pacchetto `onnxruntime` (CPU) accanto a "
            "`onnxruntime-gpu`: i due non convivono e la sintesi Kokoro e' "
            "tornata su CPU (725 ms invece di 207). Toglierlo:\n"
            "    pip uninstall onnxruntime\n"
            "    pip install onnxruntime-gpu[cuda,cudnn]==1.28.0"
        )
    else:
        righe.append("onnxruntime: solo il pacchetto GPU, com'e' giusto")

    try:
        import onnxruntime as ort

        provider = ort.get_available_providers()
        if vuole_cuda and "CUDAExecutionProvider" not in provider:
            bene = False
            righe.append(f"! ORT non vede piu' la CUDA: {provider}")
        else:
            righe.append(f"provider: {', '.join(provider)}")
    except ImportError as e:
        bene = False
        righe.append(f"! onnxruntime non si importa: {e}")

    try:
        import argostranslate.translate  # noqa: F401

        righe.append(f"argostranslate {md.version('argostranslate')}: si importa "
                     f"({_spezza_frasi()})")
    except Exception as e:
        bene = False
        righe.append(
            f"! argostranslate non si importa ({e}). Manca una dipendenza: "
            "rilanciare tools\\installa_traduzione.ps1"
        )

    # La coppia di lingue non e' un errore se manca: si scarica da sola alla
    # prima sessione. Ma saperlo prima evita di attribuire l'attesa a un difetto.
    try:
        import argostranslate.package as ap

        coppie = [f"{p.from_code}->{p.to_code}" for p in ap.get_installed_packages()]
        quali = ", ".join(coppie) if coppie else "nessuno (si scarica al primo Avvia)"
        righe.append(f"modelli installati: {quali}")
    except Exception:
        pass

    return bene, righe


def main() -> int:
    bene, righe = controlla()
    for r in righe:
        print(r)
    return 0 if bene else 1


if __name__ == "__main__":
    raise SystemExit(main())
