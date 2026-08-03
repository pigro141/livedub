"""La porta unica per aprire una sessione ONNX.

Esiste per una riga sola, e quella riga e' costata due volte la stessa
conclusione sbagliata.

`onnxruntime-gpu` trova le DLL CUDA dei pacchetti pip `nvidia-*` **solo** se
qualcuno chiama `preload_dlls()` prima di costruire la sessione. Se nessuno la
chiama, ORT non solleva: ripiega sulla CPU **senza dirlo**. La prima volta 708 ms
di CPU stavano per essere archiviati come «il numero della GPU» di Kokoro; la
seconda e' successo misurando Qwen, entro un'ora dall'aver letto il commento che
lo spiegava.

Finche' quella riga viveva dentro `speak/backends/kokoro.py` era una proprieta'
del backend che la chiamava, cioe' una cosa da ricordarsi. Qui e' una cosa che
non puo' non succedere: chi vuole i provider passa da `provider_voluti()`, e chi
passa di li' ha gia' pagato il precaricamento.

**E chiedere un acceleratore non e' ottenerlo.** `verifica_provider()` guarda cosa
la sessione ha davvero preso (`get_providers()`) e lo dichiara a chi ascolta,
perche' un ripiego silenzioso vale meno di un errore: produce numeri plausibili
con la conclusione opposta a quella vera.
"""

from __future__ import annotations

import sys

_precaricato = False


def preload() -> None:
    """Fa trovare a ORT le DLL CUDA dei pacchetti `nvidia-*`. Una volta sola.

    Idempotente di proposito: la chiamano tutti i backend, in qualunque ordine, e
    ripeterla e' inutile ma non deve essere un problema. Sulle versioni di ORT che
    non hanno la funzione (la CPU-only) non fa nulla.
    """
    global _precaricato
    if _precaricato:
        return
    _precaricato = True
    try:
        import onnxruntime as rt
    except ImportError:  # pragma: no cover - dipende dall'ambiente
        return
    if hasattr(rt, "preload_dlls"):
        rt.preload_dlls()


def provider_voluti(device: str = "auto", *, chi: str = "onnx", costo: str = "") -> list[str]:
    """I provider da chiedere, con il precaricamento gia' fatto.

    `device` vale `cpu | cuda | auto`. Con `cuda` esplicito e nessuna GPU si
    **solleva**: chi ha scritto `cuda` in config voleva la GPU, e dargli la CPU in
    silenzio sarebbe la cosa che questo modulo esiste per impedire. Con `auto` si
    ripiega, ma lo si dice — `chi` e `costo` servono solo a rendere leggibile il
    messaggio ("kokoro", "~725 ms a battuta invece di ~207").
    """
    preload()
    import onnxruntime as rt

    vuole = (device or "auto").lower()
    if vuole == "cpu":
        return ["CPUExecutionProvider"]
    if "CUDAExecutionProvider" in rt.get_available_providers():
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if vuole == "cuda":
        raise RuntimeError(
            f"{chi}: tts.device=cuda ma CUDAExecutionProvider non e' disponibile: "
            "`.\\.venv\\Scripts\\python.exe -m pip install onnxruntime-gpu[cuda,cudnn]`"
        )
    print(
        f"{chi}: CUDA non disponibile, si ripiega sulla CPU"
        + (f" ({costo})" if costo else ""),
        file=sys.stderr,
    )
    return ["CPUExecutionProvider"]


def verifica_provider(sess, chi: str, voluti: list[str]) -> str:
    """Cosa la sessione ha **davvero** preso, dichiarato se non e' quello chiesto.

    Restituisce il provider attivo. Non solleva: a questo punto il modello e' gia'
    caricato e funziona, il difetto e' nella *lettura* del risultato — quindi la
    cura giusta e' che chi legge lo sappia.
    """
    attivi = list(sess.get_providers()) if sess is not None else []
    attivo = attivi[0] if attivi else "?"
    if "CUDAExecutionProvider" in voluti and "CUDAExecutionProvider" not in attivi:
        print(
            f"{chi}: chiesto CUDA, ottenuto {attivo}. I tempi che seguono sono "
            "quelli della CPU.",
            file=sys.stderr,
        )
    return attivo
