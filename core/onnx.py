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

**E l'elenco dei provider non e' cio' che si e' ottenuto.**
`get_available_providers()` elenca quelli con cui `onnxruntime` e' stato
**compilato**, e nel pacchetto congelato risponde `Tensorrt, CUDA, CPU` mentre il
registro dello stesso avvio dice `Failed to load cublasLt64_13.dll`. Chi vuole la
risposta vera passa da `cuda_ottenuta()`, che apre una sessione e guarda.
"""

from __future__ import annotations

import base64 as _base64
import sys

_precaricato = False


def preload() -> None:
    """Fa trovare a ORT le DLL CUDA. Una volta sola. **Due posti, non uno.**

    Da sorgente le DLL arrivano dai pacchetti pip `nvidia-*` e ORT le trova da
    solo. Nell'eseguibile quei pacchetti non ci sono — sono 1,6 GB che
    porterebbero il pacchetto da 1,14 a oltre 2,5, ed e' una scelta dichiarata —
    e chi vuole la GPU se le scarica in `models/cuda` (`core/cuda.py`). Se quella
    cartella e' **completa** si passa quella a `preload_dlls`, che li' dentro
    cerca i file per nome: e' scritto nel suo sorgente, ed e' il motivo per cui la
    cartella e' piatta.

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
    if not hasattr(rt, "preload_dlls"):
        return
    try:
        from core.cuda import cartella, presente

        # **Completa o niente.** Con una cartella a meta' `preload_dlls` carica
        # cio' che trova e tace su cio' che non trova: il provider poi non si
        # apre, e il difetto sembra della scheda video. Meglio la strada normale,
        # che almeno da sorgente funziona.
        nostre = str(cartella()) if presente() else ""
    except Exception:  # pragma: no cover - dipende dall'ambiente
        nostre = ""
    if nostre:
        rt.preload_dlls(directory=nostre)
    else:
        rt.preload_dlls()


def dimentica() -> None:
    """Butta via le risposte tenute da parte. **Solo per chi cambia la macchina.**

    Serve dopo aver scaricato le DLL CUDA: `preload()` e `cuda_ottenuta()`
    rispondono una volta sola apposta, e senza questa riga il programma
    continuerebbe a dire «CPU» con 1,6 GB di librerie appena arrivate sul disco.
    Non e' un `reset` generico e non va chiamata a caso: le DLL gia' caricate nel
    processo non si scaricano, quindi questa funzione puo' far cambiare idea da
    «no» a «si'», mai il contrario.
    """
    global _precaricato, _cuda
    _precaricato = False
    _cuda = None


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


# Un modello ONNX di settanta byte: un nodo `Identity` su un float. Serve solo
# ad **aprire una sessione**, che e' l'unico modo di sapere se un provider si
# carica davvero. Sta qui come byte e non come file perche' un file in piu' e' un
# file in piu' da impacchettare — e questo progetto ha appena passato una
# sessione a rincorrere i dati che non viaggiavano.
_MODELLO_MINIMO = _base64.b64decode(
    "CAhCAhANOj4KEwoBeBIBeRoBbiIISWRlbnRpdHkSBXByb3ZhWg8KAXgSCgoICAESBAoCCAFi"
    "DwoBeRIKCggIARIECgIIAQ=="
)

_cuda: "tuple[bool, str] | None" = None


def cuda_ottenuta(chi: str = "prova") -> tuple[bool, str]:
    """CUDA **ottenuta**, non CUDA compilata dentro. Una volta sola.

    `get_available_providers()` elenca i provider con cui `onnxruntime` e' stato
    **costruito**: dice `CUDAExecutionProvider` anche quando le DLL CUDA non ci
    sono, e la sessione ripiega poi sulla CPU. Sono due domande diverse, e finche'
    si e' risposto alla prima credendo di rispondere alla seconda, la guida
    scriveva «scheda video: CUDA» due righe sopra il banco che scriveva «chiesto
    CUDA, ottenuto CPUExecutionProvider» — misurato sul pacchetto costruito in CI,
    dove le DLL `nvidia-*` non viaggiano e il registro dice `Failed to load
    cublasLt64_13.dll`. Due righe dello stesso pannello che si contraddicono, e
    quella che mente e' quella che l'utente legge **prima** di decidere.

    La risposta si prende come si prende ogni risposta vera in questo file:
    aprendo una sessione e guardando cosa ha preso (`verifica_provider`). Costa
    qualche centinaio di millisecondi la prima volta, zero le successive.

    Torna `(ottenuta, com'e' andata)`, e i tre esiti sono **tre** e non due:

        (True,  "CUDA")                    la sessione l'ha presa
        (False, "CPU")                     non c'e' nemmeno nel pacchetto
        (False, "CPU (CUDA non caricata)") c'e' e non si carica: mancano le DLL

    Il terzo e' l'unico che dice a chi legge che **prendere le DLL cambierebbe
    qualcosa**, e con due soli esiti era indistinguibile dal secondo.

    Non solleva mai: chi la chiama vuole **descrivere** la macchina, e un errore
    qui diventerebbe una guida che non si apre invece di una riga che dice «CPU».
    """
    global _cuda
    if _cuda is not None:
        return _cuda
    try:
        preload()
        import onnxruntime as rt

        if "CUDAExecutionProvider" not in rt.get_available_providers():
            # Nemmeno compilata dentro: non c'e' niente da provare, e aprire una
            # sessione per scoprirlo sarebbe mezzo secondo buttato.
            _cuda = (False, "CPU")
            return _cuda
        voluti = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        sess = rt.InferenceSession(_MODELLO_MINIMO, providers=voluti)
        attivo = verifica_provider(sess, chi, voluti)
        if attivo == "CUDAExecutionProvider":
            _cuda = (True, "CUDA")
        else:
            _cuda = (False, "CPU (CUDA non caricata)")
    except Exception as guasto:  # pragma: no cover - dipende dall'ambiente
        _cuda = (False, f"CPU ({type(guasto).__name__})")
    return _cuda


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
