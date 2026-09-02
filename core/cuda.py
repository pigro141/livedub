"""Le DLL CUDA: **si scaricano, non si impacchettano**.

`onnxruntime-gpu` sa gia' parlare con la scheda video — il provider CUDA e i suoi
265 MB di `onnxruntime_providers_cuda.dll` viaggiano dentro il pacchetto — ma non
sa **caricarlo** finche' sul disco non ci sono le librerie di NVIDIA. Nel venv
arrivano dai pacchetti pip `nvidia-*`: 1,6 GB di DLL, misurati qui, che
porterebbero l'eseguibile da 1,14 a oltre 2,5 GB.

**Quindi non ci entrano.** E' la stessa scelta gia' presa per i 541 MB di
modelli, e per la stessa ragione: paga il peso chi usa la funzione. Il motore che
vuole la GPU **resta fra le opzioni anche su una macchina senza scheda** —
sceglierlo scarica quello che serve, con la barra, come ogni altro pezzo di
`core/banco.py`.

## Perche' non `pip`

Il confine e' gia' scritto in `core/banco.py` e qui vale il doppio:
`requirements.txt` monta `onnxruntime-gpu` e **non** `onnxruntime`, i due non
convivono, e un `pip install` ingenuo tira dentro il secondo spegnendo la CUDA in
silenzio. In piu' dentro l'eseguibile `pip` non c'e' affatto: un rimedio che
funziona solo da sorgente non e' il rimedio di questo file.

Si prendono quindi le **ruote** da PyPI e se ne estraggono le DLL. Non e' un
gestore di pacchetti: non risolve conflitti, non installa niente, non tocca il
venv. Scrive dei file in `models/cuda/`, che e' materiale della macchina come
tutto il resto di `models/`.

## Una cartella piatta, e non e' un dettaglio estetico

`onnxruntime.preload_dlls(directory=...)` cerca **il solo nome del file** dentro
la cartella che gli si passa (`os.path.join(base_directory, relative_path[-1])`):
e' scritto nel suo sorgente, e vuol dire che a lui la disposizione delle ruote non
interessa. Copiare la gerarchia `nvidia/cu13/bin/x86_64/` servirebbe solo a
riprodurre un albero che nessuno guarda — e a doverlo indovinare di nuovo il
giorno che NVIDIA lo cambia, come lo ha appena cambiato passando da CUDA 12 a 13.

## Quali DLL, e chi lo decide

**Non un elenco scritto qui.** Le distribuzioni vengono dai requisiti di
`onnxruntime-gpu` (gli extra `cuda` e `cudnn` della sua stessa metadata), i nomi
dei file che devono arrivare vengono da `onnxruntime._get_nvidia_dll_paths()`,
cioe' dalla funzione che ORT usa per caricarli. Una seconda tabella qui sarebbe
l'ottava volta della forma «scritta due volte, e la seconda non l'aggiorna
nessuno» — e diverge nel modo peggiore, verso il verde: un nome vecchio da'
«scaricato» su una cartella incompleta.

Delle ruote invece si estraggono **tutte** le DLL e non le quattro che ORT nomina:
`cublas64` ha bisogno di `nvJitLink`, `cudnn_graph64` di `nvrtc`, e una dipendenza
che manca non da' un errore leggibile — da' un provider che non si carica, cioe'
esattamente il ripiego muto che tutto questo file esiste per togliere. Il prezzo
sono 1,6 GB sul disco invece di 1,0, ed e' dichiarato.
"""

from __future__ import annotations

import json
import urllib.request
import zipfile
from pathlib import Path

from core.percorsi import radice

#: L'indice da cui si prendono le ruote. Una costante e non una riga scritta due
#: volte: e' anche il posto da cambiare per uno specchio interno.
PYPI = "https://pypi.org/pypi"

#: Il pacchetto di cui si seguono i requisiti, e i suoi due extra. `cuda` porta
#: runtime, nvrtc, cufft e curand; `cudnn` porta cuDNN — e da li' cublas, che
#: nessuno dei due nomina ma che arriva come dipendenza.
PACCHETTO = "onnxruntime-gpu"
EXTRA = ("cuda", "cudnn")

#: Quanto occupa sul disco, misurato: 20 DLL per 1601 MB in
#: `.venv/Lib/site-packages/nvidia`. Serve a **dirlo prima**: un'attesa
#: dichiarata e' un'attesa, un'attesa muta e' una finestra bloccata.
MB_DISCO = 1601

#: Quanti se ne scaricano — le ruote sono compresse. Misurato il 24 agosto
#: sommando le dimensioni che PyPI dichiara per le sette ruote `win_amd64`
#: risolte da `piano()`: cudnn 412, cublas 395, cufft 184, curand 55, nvrtc 45,
#: nvjitlink 38, cuda-runtime 3.
MB_RETE = 1132


def cartella() -> Path:
    """Dove finiscono le DLL: `models/cuda`, piatta.

    Sotto `models/` e non accanto all'eseguibile perche' e' materiale della
    macchina — gitignorato, pesante, riscaricabile — e perche' `core/percorsi.py`
    esiste apposta per avere **una radice sola**: chi apre il programma da
    un'altra cartella non deve ritrovarsi due copie di 1,6 GB.
    """
    return radice() / "models" / "cuda"


# ============================================== quello che si puo' provare ====
#
# Da qui alla riga di mezzo non si tocca ne' la rete ne' il disco: sono funzioni
# pure che prendono cio' che PyPI ha risposto e dicono cosa farne. E' la stessa
# separazione di `core/banco.py`, e per la stessa ragione — i casi che contano
# (una ruota che non c'e', una versione di prova, un requisito nuovo) su questa
# macchina non capitano mai, quindi si provano con dati finti o non si provano.


def distribuzioni(requisiti, extra=EXTRA) -> tuple[tuple[str, str], ...]:
    """Le distribuzioni `nvidia-*` chieste dagli extra, con il loro vincolo.

    `requisiti` e' quello che `importlib.metadata.requires()` restituisce:
    `nvidia-cudnn-cu13~=9.0; extra == "cudnn"`. Si tiene solo cio' che un extra
    chiesto attiva, e si ignora tutto il resto — `numpy`, `protobuf` e compagnia
    sono gia' dentro il pacchetto.
    """
    from packaging.requirements import Requirement

    fuori: list[tuple[str, str]] = []
    for riga in requisiti or ():
        try:
            r = Requirement(riga)
        except Exception:
            continue
        if r.marker is None:
            continue
        if not any(r.marker.evaluate({"extra": e}) for e in extra):
            continue
        fuori.append((r.name, str(r.specifier)))
    return tuple(fuori)


def dipendenze(requisiti) -> tuple[tuple[str, str], ...]:
    """Le dipendenze `nvidia-*` **sempre** attive di una ruota, col loro vincolo.

    Senza marcatore, cioe' quelle che si installerebbero comunque: sono le sole
    da seguire. Un requisito condizionato (`; extra == "..."`, `; sys_platform
    == "linux"`) qui non si valuta — valutarlo vorrebbe dire riscrivere un
    risolutore, che e' il confine dichiarato in testata.
    """
    from packaging.requirements import Requirement

    fuori: list[tuple[str, str]] = []
    for riga in requisiti or ():
        try:
            r = Requirement(riga)
        except Exception:
            continue
        if r.marker is None and r.name.lower().startswith("nvidia"):
            fuori.append((r.name, str(r.specifier)))
    return tuple(fuori)


def versioni_buone(versioni, specifica: str) -> tuple[str, ...]:
    """Le versioni che soddisfano il vincolo, **dalla piu' recente in giu'**.

    Un elenco e non una sola, e non e' prudenza generica: misurato oggi,
    `nvidia-cudnn-cu13` ha pubblicato la 9.25.0.15 **senza la ruota Windows** —
    esiste per Linux e per aarch64 e per x64 no. Chi si fermasse alla piu' alta
    direbbe «per questa macchina non c'e' CUDA» il giorno in cui NVIDIA pubblica
    una riga per un'altra piattaforma, con la 9.24 li' accanto che va benissimo.
    La ruota giusta fa parte della scelta, non e' un controllo che viene dopo.

    **Le versioni di prova si scartano.** PyPI le pubblica accanto alle altre —
    `nvidia-cudnn-cu13` ne ha cinque `.devN` piu' recenti dell'ultima stabile — e
    prendere il numero piu' alto vorrebbe dire scaricare 400 MB di una build
    interna di NVIDIA a chi ha premuto un bottone che diceva «usa la scheda
    video».
    """
    from packaging.specifiers import SpecifierSet
    from packaging.version import InvalidVersion, Version

    regola = SpecifierSet(specifica or "")
    buone = []
    for v in versioni or ():
        try:
            n = Version(v)
        except InvalidVersion:
            continue
        if n.is_prerelease or n.is_devrelease:
            continue
        if n in regola:
            buone.append(n)
    return tuple(str(n) for n in sorted(buone, reverse=True))


def ruota(file_del_rilascio) -> dict:
    """La ruota Windows a 64 bit fra quelle di un rilascio. `{}` se non c'e'.

    Non si ripiega su un'altra piattaforma, e non e' pignoleria: una ruota
    `manylinux` si scarica benissimo, si spacchetta benissimo e dentro non ha
    nessuna DLL — cioe' consegnerebbe 550 MB e una cartella che *sembra* pronta.
    Meglio dire «per questa macchina non c'e'».
    """
    for f in file_del_rilascio or ():
        nome = f.get("filename", "")
        if nome.endswith(".whl") and "win_amd64" in nome and not f.get("yanked"):
            return f
    return {}


def dll_dentro(nomi) -> tuple[str, ...]:
    """I membri di una ruota che sono DLL da tenere.

    Si guarda il **nome del file**, non la cartella: le ruote di NVIDIA hanno
    spostato le DLL da `nvidia/<pezzo>/bin/` a `nvidia/cu13/bin/x86_64/` fra CUDA
    12 e 13, e una regola scritta sul percorso sarebbe gia' scaduta una volta in
    un anno.
    """
    return tuple(n for n in nomi or () if n.lower().endswith(".dll"))


def nomi_dll() -> tuple[str, ...]:
    """I nomi che devono trovarsi nella cartella, **chiesti a chi li carica**.

    Li elenca `onnxruntime._get_nvidia_dll_paths()`, che e' la stessa funzione da
    cui `preload_dlls` prende i suoi: cosi' la domanda «e' arrivato tutto?» e la
    domanda «cosa carico?» non possono rispondere due cose diverse.

    Se quella funzione non c'e' (ORT solo CPU, o una versione che l'ha
    rinominata) si torna una tupla vuota, e chi chiama lo tratta come «non lo so»
    — che e' diverso da «non c'e' niente» e va detto invece che dedotto.
    """
    try:
        import onnxruntime as rt

        percorsi = rt._get_nvidia_dll_paths(True, True, True)  # noqa: SLF001
    except Exception:
        return ()
    return tuple(p[-1] for p in percorsi if p)


def manca(nomi, presenti) -> tuple[str, ...]:
    """Quali dei nomi chiesti non sono nella cartella. **Pura.**

    Il confronto e' senza maiuscole perche' Windows non le distingue e le ruote
    non sono coerenti fra loro (`nvJitLink_130_0.dll`).
    """
    ci_sono = {n.lower() for n in presenti or ()}
    return tuple(n for n in nomi or () if n.lower() not in ci_sono)


# ============================================== quello che tocca la macchina ==


def presente() -> bool:
    """Le DLL sono gia' nella nostra cartella, **tutte**.

    Non «la cartella esiste»: un archivio a meta' e' precisamente il difetto che
    e' costato un `KeyError` dentro `kokoro_onnx` lontanissimo da dove stava —
    chi mette qualcosa in cache controlli **cosa** c'e' dentro, non che ci sia.
    Con un elenco vuoto (ORT non sa dirci i nomi) la risposta e' `False`: meglio
    riscaricare che dichiarare pronto cio' che non si e' potuto guardare.
    """
    chiesti = nomi_dll()
    if not chiesti:
        return False
    dove = cartella()
    if not dove.is_dir():
        return False
    return not manca(chiesti, [p.name for p in dove.glob("*.dll")])


def _json(url: str, timeout: float = 30.0):
    with urllib.request.urlopen(url, timeout=timeout) as risposta:
        return json.loads(risposta.read().decode("utf-8"))


def piano(dillo=None) -> tuple[tuple[str, str, int], ...]:
    """Cosa si scaricherebbe: `(nome, url, byte)` per ogni ruota. Tocca la rete.

    Cammina sulle dipendenze `nvidia-*` invece di fermarsi a quelle che ORT
    nomina: `nvidia-cudnn-cu13` chiede `nvidia-cublas`, che chiede
    `nvidia-nvjitlink`, e nessuno dei due compare nei requisiti di ORT. Fermarsi
    al primo livello darebbe una cartella che sembra completa fino al momento in
    cui il provider non si carica.

    Si sale **solo** su `nvidia-*`: qualunque altra dipendenza che spuntasse
    sarebbe un pacchetto Python, cioe' esattamente il confine che questo file non
    passa.
    """
    import importlib.metadata as md

    dillo = dillo or (lambda *_: None)
    try:
        requisiti = md.requires(PACCHETTO)
    except md.PackageNotFoundError as guasto:
        raise RuntimeError(
            f"{PACCHETTO} non e' installato: senza i suoi requisiti non si sa "
            "quali librerie CUDA servono"
        ) from guasto

    da_fare = list(distribuzioni(requisiti))
    viste: set[str] = set()
    fuori: list[tuple[str, str, int]] = []

    while da_fare:
        nome, vincolo = da_fare.pop(0)
        chiave = nome.lower().replace("_", "-")
        if chiave in viste or not chiave.startswith("nvidia-"):
            continue
        viste.add(chiave)
        dillo(nome)

        dati = _json(f"{PYPI}/{nome}/json")
        rilasci = dati.get("releases") or {}
        candidate = versioni_buone(list(rilasci), vincolo)
        if not candidate:
            raise RuntimeError(f"{nome}: nessuna versione soddisfa {vincolo!r}")
        # La prima che ha una ruota per questa macchina. L'elenco dei file sta
        # gia' in questa risposta, quindi provarle tutte non costa una richiesta
        # in piu' — e quella per i requisiti si paga una volta sola, sulla
        # versione scelta.
        versione, scelta = "", {}
        for v in candidate:
            scelta = ruota(rilasci.get(v) or [])
            if scelta:
                versione = v
                break
        if not versione:
            raise RuntimeError(
                f"{nome}: nessuna ruota per Windows x64 fra le versioni che "
                f"soddisfano {vincolo!r}")
        fuori.append((f"{nome} {versione}", scelta["url"], int(scelta.get("size") or 0)))
        rilascio = _json(f"{PYPI}/{nome}/{versione}/json")

        # Le dipendenze **vere** di questa ruota, cioe' quelle senza marcatore:
        # `distribuzioni()` guarda gli extra e qui di extra non se ne chiede
        # nessuno. `nvidia-cudnn-cu13` dichiara cosi' `nvidia-cublas`.
        da_fare += list(dipendenze((rilascio.get("info") or {}).get("requires_dist")))

    return tuple(fuori)


def scarica(dillo=None, fermati=None) -> None:
    """Prende le ruote e ne versa le DLL in `models/cuda`. Solleva se non ce la fa.

    `dillo(cosa, fatti, quanti)` e' lo **stesso canale** dell'avanzamento di
    `core/banco.py`: un secondo canale vorrebbe dire due posti in cui aggiornare
    la stessa riga a schermo, e il secondo non lo aggiorna mai nessuno.

    `fermati()` si chiede **fra una ruota e l'altra** e non dentro, come per gli
    altri pezzi: annullare vuol dire «non cominciare la prossima».

    **Si scrive in una cartella accanto e si sposta alla fine.** Una rete che
    cade a meta' lascerebbe altrimenti dieci DLL su venti — cioe' una cartella
    che `presente()` deve poi dichiarare incompleta, con 800 MB gia' scaricati e
    nessun modo di riprenderli. Cosi' invece l'unica cartella che esiste e' o
    intera o inesistente.
    """
    import shutil
    import tempfile

    dillo = dillo or (lambda *_: None)
    fermati = fermati or (lambda: False)

    ruote = piano(lambda nome: dillo(nome, 0, 0))
    dove = cartella()
    dove.parent.mkdir(parents=True, exist_ok=True)
    lavoro = Path(tempfile.mkdtemp(prefix="cuda-", dir=str(dove.parent)))

    try:
        for i, (nome, url, _byte) in enumerate(ruote):
            if fermati():
                raise RuntimeError("annullato")
            dillo(nome, i, len(ruote))
            archivio = lavoro / "ruota.whl"
            with urllib.request.urlopen(url, timeout=120) as rete, \
                    open(archivio, "wb") as f:
                shutil.copyfileobj(rete, f, 1 << 20)
            with zipfile.ZipFile(archivio) as z:
                for membro in dll_dentro(z.namelist()):
                    with z.open(membro) as dentro, \
                            open(lavoro / Path(membro).name, "wb") as fuori:
                        shutil.copyfileobj(dentro, fuori, 1 << 20)
            archivio.unlink()

        # **Si controlla prima di consegnare.** Una cartella incompleta messa al
        # suo posto e' peggio di nessuna cartella: la prossima apertura la
        # troverebbe e proverebbe a caricarla, e il difetto tornerebbe a essere
        # un provider che non parte senza dire perche'.
        chiesti = nomi_dll()
        assenti = manca(chiesti, [p.name for p in lavoro.glob("*.dll")])
        if chiesti and assenti:
            raise RuntimeError(
                "le ruote non contenevano tutto quello che serve: "
                + ", ".join(assenti))

        if dove.exists():
            shutil.rmtree(dove, ignore_errors=True)
        lavoro.replace(dove)
    finally:
        if lavoro.exists():
            shutil.rmtree(lavoro, ignore_errors=True)


# ============================================ c'e' una scheda, si' o no? ======

# La risposta, tenuta da parte. Non cambia mentre il programma e' aperto: una
# scheda video non si infila nel PC a sessione accesa, e il driver nemmeno.
_scheda: bool | None = None


def scheda_nvidia() -> bool:
    """C'e' una scheda NVIDIA **con il suo driver** su questa macchina?

    E' la domanda che rompe un giro che si chiudeva su se stesso. `vuole_cuda()`
    guarda la configurazione, e la configurazione di serie dice `tts.backend =
    piper`: quindi le librerie CUDA non si scaricavano mai, quindi la sonda
    trovava «niente CUDA», quindi si sceglieva Piper — su una macchina con una
    4060 dentro. Il motore migliore non era escluso da una misura: era escluso
    **dal fatto che nessuno aveva ancora chiesto di misurarlo**.

    Qui non si chiede a `onnxruntime` (che senza le ruote `nvidia-*` risponde di
    no anche dove la scheda c'e'), e non si guarda la cartella `models/cuda`
    (che e' quello che si sta decidendo se riempire). Si apre **`nvcuda.dll`**,
    che e' del driver NVIDIA e sta in `System32`: c'e' se e solo se qualcuno ha
    installato una scheda NVIDIA. Poi la si fa lavorare — `cuInit` e
    `cuDeviceGetCount` — perche' **aprire non e' usare**, che in questo progetto
    e' gia' costata una diagnosi intera: una DLL c'e' e si carica anche quando il
    driver e' rotto o la scheda e' spenta.

    Zero dispositivi e' `False`, non «boh»: 1,1 GB non si scaricano per una
    scheda che non risponde. E qualunque cosa vada storta e' `False` per la
    stessa ragione — qui il costo dello sbaglio non e' simmetrico. Dire di no
    dove ci sarebbe una GPU lascia il motore leggero, che funziona; dire di si'
    dove non c'e' fa scaricare un gigabyte a chi non ne fara' mai niente.
    """
    global _scheda
    if _scheda is not None:
        return _scheda
    _scheda = _chiedi_al_driver()
    return _scheda


def _chiedi_al_driver() -> bool:
    """La prova vera, senza cache. Separata perche' la cache si possa verificare."""
    import ctypes

    try:
        driver = ctypes.WinDLL("nvcuda.dll")
    except OSError:
        # Il caso normale su una macchina senza NVIDIA: la DLL non esiste.
        return False
    try:
        # `cuInit(0)`: 0 e' `CUDA_SUCCESS`. Qualunque altro numero vuol dire che
        # il driver c'e' come file e non funziona — che per noi e' un no.
        if driver.cuInit(0) != 0:
            return False
        quante = ctypes.c_int(0)
        if driver.cuDeviceGetCount(ctypes.byref(quante)) != 0:
            return False
        return quante.value > 0
    except Exception:  # pragma: no cover - un driver che si comporta male
        return False


def dimentica_scheda() -> None:
    """Butta via la risposta tenuta da parte. Serve alle verifiche."""
    global _scheda
    _scheda = None
