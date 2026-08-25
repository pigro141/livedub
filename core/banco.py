"""Il mini banco della guida: **cosa ce la fa su questo PC, e cosa manca**.

Chi apre questo programma la prima volta si trova davanti tre motori di sintesi e
quattro traduttori, e non ha modo di sapere quale regga sulla sua macchina. Le
misure che decidono stanno gia' scritte in `CLAUDE.md` — sono state fatte qui,
una volta, su una macchina sola — e questo file le mette al lavoro sulla macchina
di chi legge.

**Ma la ragione vera per cui esiste non e' la comodita': e' che un modello
mancante non da' errore.** I pacchetti stanno in `requirements.txt` e si
installano una volta; i modelli no — si scaricano alla *prima richiesta* dentro
`models/`, e se non ci si riesce la catena **ripiega su un backend piu' leggero e
continua**. Un ripiego che non si dichiara e' peggio di un errore: chi apre il
programma la prima volta non sa di stare ascoltando il ripiego, e il difetto
sembra della sintesi. La stessa forma di `preload_dlls()` — ORT che non trova le
DLL CUDA, torna sulla CPU in silenzio, e 708 ms stavano per essere riportati come
«il numero della GPU».

## Misurare e decidere sono due cose, e stanno separate apposta

Sopra la riga di mezzo c'e' solo aritmetica: `Sonda` e' quello che si e' trovato,
`scegli()` e' **quali motori ne conseguono**. Non tocca il disco, non apre una
sessione ONNX, non guarda l'ora — quindi si verifica con numeri finti, compresi i
casi che su questa macchina non capitano mai: niente CUDA, rete assente, modello
gia' presente, macchina lentissima. E' la stessa scelta di `core.motore.
colore_stato` e di `core.preferenze.riprendi`, e il motivo e' pagato: rileggendo
a freddo le cure di una sessione, **quattro difetti su cinque stavano in Qt o al
suo confine**, l'unica parte del programma che nessuna verifica toccava.

Sotto la riga c'e' quello che tocca la macchina, e non decide niente: misura e
consegna dei numeri.

## Il confine che questo file non passa: **niente `pip`**

Si scaricano **modelli e coppie di lingue**. Non si installano pacchetti, e non
e' prudenza generica: `requirements.txt` monta `onnxruntime-gpu` e **non**
`onnxruntime`, i due non convivono, e un `pip install argostranslate` ingenuo
tira dentro il secondo — spegnendo la CUDA di Kokoro **in silenzio**, 725 ms a
battuta invece di 207, con i log verdi. Un'interfaccia che installa pacchetti puo'
rompere l'ambiente da dentro. Se un pacchetto manca, qui si **dichiara** e si
consegna la riga di comando esatta.

## Le tre soglie, e nessuna e' nuova

Sono tutte gia' misurate altrove in questo progetto, e sono citate con la loro
provenienza: una soglia inventata qui sarebbe la sesta volta della forma «una
tabella scritta due volte, e la seconda non l'aggiorna nessuno».
"""

from __future__ import annotations

from dataclasses import dataclass, field

# =============================================================== le soglie ====

# **La sintesi che si accetta da una GPU.** Kokoro costa 299 ms al banco e 257
# dal vivo quando la CUDA c'e' davvero, 725 quando ricade sulla CPU. 500 sta in
# mezzo e non tocca nessuno dei due casi veri: sopra, quella GPU non sta dando
# quello che una GPU da'. Non e' una soglia di gusto — e' il confine fra i due
# numeri gia' misurati.
SINTESI_MAX_MS = 500.0

# **Quanto parlato produce per secondo di scena.** E' la domanda che ha tolto il
# quarto motore, e la latenza non c'entrava: Qwen faceva 8,4-10,6 caratteri al
# secondo contro i 14,8 di Piper, quindi produceva il 157% del parlato che la
# scena aveva tempo di contenere e ogni battuta usciva compressa al tetto — su
# ogni percentile, su qualunque scheda video. I tre motori montati stanno fra
# 12,9 e 14,8; sotto 10 non ci arriva nessuno di loro, e chi ci arriva sta
# rispondendo di qualcos'altro.
PASSO_MINIMO = 10.0

# **La traduzione si paga solo se sfora l'attesa.** Sta *dentro* i
# `speaker.decide_after_ms` (500) in cui la catena aspetta di sapere chi parla
# (`core/anticipa.py`): sotto quella soglia e' gratis, sopra si paga intera. Per
# questo il numero che conta e' il **p95** e non il p50 — un traduttore che di
# solito e' svelto e ogni tanto no fa arrivare tardi proprio le battute in cui
# succede qualcosa. Misurato su 120 sottotitoli veri: locale 39/67/97 ms
# (p50/p95/max), google 491/1188/2496, llm 589/869/1062.
TRADUZIONE_MAX_MS = 500.0

# La riga da incollare quando manca il **pacchetto** della traduzione offline.
# Non la si esegue: si veda il confine dichiarato in testata.
#
# **Ed e' lo script, non `pip install -r requirements.txt`.** Quella riga stava
# qui e dal 25 agosto non installa piu' la traduzione affatto: argostranslate non
# e' in `requirements.txt` e non ci puo' stare, perche' va messo con `--no-deps`
# — `pip install argostranslate` ingenuo tira dentro `minisbd` e con lui
# `onnxruntime` (CPU), che accanto a `onnxruntime-gpu` spegne la CUDA in
# silenzio. Consegnare la riga sbagliata e' peggio che non consegnarne nessuna:
# chi la incolla ottiene un errore che non capisce, o peggio un successo che gli
# rompe la sintesi.
RIGA_PIP = "powershell -ExecutionPolicy Bypass -File tools\\installa_traduzione.ps1"

# **Quanto pesa, detto prima.** E' il numero su cui uno decide, quindi non puo'
# arrivare a scaricamento iniziato: 3038 MB sono di **solo torch**, misurati sul
# venv completo, e torch la traduzione non lo usa mai — Argos gira su
# CTranslate2. Lo tira dentro `stanza`, che `argostranslate/sbd.py` importa in
# cima al modulo in tutte e due le versioni utili.
#
# E' un numero a se' e non un `Pezzo`, perche' i `Pezzi` li scarica il banco e
# questo no: sono **pacchetti**, e il banco non fa `pip`.
TRADUZIONE_MB = 3100


# =================================================== quello che si e' trovato =


@dataclass(frozen=True)
class Sonda:
    """Cosa c'e' su questa macchina. **Solo dati**: nessuno di questi campi sa
    cosa farsene di se stesso.

    I campi a zero vogliono dire «non misurato», e non «misurato zero»: la sonda
    veloce risponde in un secondo e non sintetizza niente, la misura vera arriva
    dopo lo scaricamento. `scegli()` deve reggere tutte e due, ed e' il motivo
    per cui si verifica con numeri finti.
    """

    # Il provider CUDA e' **dichiarato disponibile** da ORT. Dichiarato, non
    # ottenuto: si veda `provider`.
    cuda: bool = False
    # Cosa la sessione ha **davvero** preso, quando una sessione e' stata aperta
    # (`core.onnx.verifica_provider`). Vuoto finche' non si e' provato.
    provider: str = ""
    sintesi_ms: float = 0.0    # p50 misurato del motore candidato
    passo: float = 0.0         # caratteri di parlato al secondo, misurati
    traduzione_ms: float = 0.0  # p95 misurato
    argos: bool = False        # il pacchetto della traduzione locale e' importabile
    # **Se l'utente la traduzione la vuole.** Non e' una misura di questa
    # macchina come gli altri campi, ed e' qui lo stesso perche' senza di lei
    # `scegli` non puo' sapere se «manca il pacchetto» sia una notizia o rumore.
    traduzione_accesa: bool = False
    llm: bool = False          # llama-cpp-python e' importabile
    # I pezzi gia' sul disco, per codice (si veda `PEZZI`). E' un elenco di
    # **contenuti verificati**, non di file esistenti: la differenza e' costata
    # un `KeyError` dentro una libreria, lontanissimo da dove stava il difetto.
    presenti: frozenset[str] = frozenset()
    rete: bool = True


# ================================================================ il perche' ==


@dataclass(frozen=True)
class Motivo:
    """Perche' si e' scelto cosi': un **codice** e i suoi valori, non una frase.

    Le frasi stanno in `ui/tutorial.py`, dove c'e' il catalogo che le traduce in
    quarantuno lingue. Scriverle qui vorrebbe dire una stringa italiana dentro
    `core/`, cioe' una riga che resta in italiano in mezzo a una finestra
    tedesca — ed e' anche la ragione per cui questo modulo si verifica senza
    aprire Qt.
    """

    codice: str
    valori: tuple = ()


# **Tutti i codici che `scegli()` puo' produrre.** Dichiarati, perche' la
# verifica confronta questo elenco con i modelli di `ui/tutorial.py`: un codice
# nuovo e non tradotto uscirebbe come una riga vuota, che e' il difetto peggiore
# dei due — nessun errore, e la spiegazione sparita.
MOTIVI: tuple[str, ...] = (
    "cuda_si",
    "cuda_no",
    "cuda_persa",
    "sintesi_ok",
    "sintesi_lenta",
    "passo_corto",
    "traduzione_locale",
    "traduzione_llm",
    "traduzione_manca",
    "traduzione_lenta",
    "motore_mancante",
)

# **Quali motivi sono rinunce, e non conferme.** Un motivo dice *perche'* si e'
# scelto cosi', e i due casi sono diversi: «nessuna scheda video» e' un fatto e
# Piper e' la risposta giusta, mentre «chiesta la GPU e ottenuta la CPU» e' una
# cosa andata storta che si e' potuta aggirare. Metterli allo stesso segno di
# spunta vorrebbe dire una schermata tutta verde sopra un ripiego — cioe' il
# ripiego silenzioso con l'aria di aver funzionato, che e' il difetto peggiore
# di questo progetto messo in una figura.
AVVISI: frozenset[str] = frozenset({
    "cuda_persa",
    "sintesi_lenta",
    "passo_corto",
    "motore_mancante",
    "traduzione_manca",
    "traduzione_lenta",
})


@dataclass(frozen=True)
class Scelta:
    """I due motori scelti e perche'.

    `traduzione` puo' essere **vuota**, e non e' una svista: se manca il
    pacchetto della traduzione locale, l'unica alternativa che funzionerebbe
    sempre e' `google`, che manda ogni sottotitolo fuori dal PC. Ripiegarci
    sopra da soli sarebbe il contrario di quello che questo programma dichiara di
    essere, quindi qui non si sceglie: si dice cosa manca e si lascia decidere.
    """

    tts: str = "piper"
    traduzione: str = ""
    motivi: tuple[Motivo, ...] = field(default_factory=tuple)


def scegli(s: Sonda) -> Scelta:
    """Dati i numeri, quali motori. **Funzione pura**: si prova con numeri finti.

    L'ordine dei rami e' l'ordine in cui le prove diventano affidabili, ed e' il
    punto di tutto il file:

    1. il provider **dichiarato** propone (CUDA -> Kokoro, se no Piper);
    2. il provider **ottenuto** puo' smentirlo — chiedere un acceleratore non e'
       ottenerlo, ed e' la riga che `core/onnx.py` esiste per rendere
       impossibile da dimenticare;
    3. i **millisecondi** misurati possono smentire tutti e due, perche' una
       sessione puo' dire «CUDA» e andare lo stesso come una CPU.

    Una misura qui puo' solo **retrocedere** la scelta, mai promuoverla: se
    Kokoro non ce la fa si torna a Piper, che e' il default storico e non chiede
    niente a nessuno. Il contrario — promuovere Piper a Kokoro perche' un numero
    e' venuto bello — vorrebbe dire scegliere il motore che compete con il gioco
    per la GPU sulla base di una misura fatta a gioco spento.
    """
    motivi: list[Motivo] = []

    if s.cuda:
        tts = "kokoro"
        motivi.append(Motivo("cuda_si"))
    else:
        tts = "piper"
        motivi.append(Motivo("cuda_no"))

    # Il provider **ottenuto**, se una sessione e' stata davvero aperta.
    if tts == "kokoro" and s.provider and "CUDA" not in s.provider:
        tts = "piper"
        motivi.append(Motivo("cuda_persa", (s.provider,)))

    # I millisecondi veri. Valgono per il motore che si stava provando, quindi
    # si guardano solo finche' quel motore e' ancora in piedi.
    if tts == "kokoro" and s.sintesi_ms:
        if s.sintesi_ms > SINTESI_MAX_MS:
            tts = "piper"
            motivi.append(Motivo("sintesi_lenta",
                                 (round(s.sintesi_ms), round(SINTESI_MAX_MS))))
        else:
            motivi.append(Motivo("sintesi_ok", (round(s.sintesi_ms),)))

    # **Il passo si dichiara sempre, anche quando non cambia niente.** Su Piper
    # non c'e' dove retrocedere — e' gia' il motore che non chiede niente — ma un
    # motore che produce meno parlato di quanto la scena ne contenga fa uscire
    # ogni battuta compressa al tetto, e quel difetto non ha nessun altro
    # contatore che lo mostri.
    if s.passo and s.passo < PASSO_MINIMO:
        motivi.append(Motivo("passo_corto", (f"{s.passo:.1f}",
                                             f"{PASSO_MINIMO:.0f}")))
        tts = "piper"

    if s.argos:
        traduzione = "locale"
        motivi.append(Motivo("traduzione_locale"))
    elif s.llm:
        traduzione = "llm"
        motivi.append(Motivo("traduzione_llm"))
    else:
        traduzione = ""
        # **Lo si dice a chi la traduzione l'ha accesa, e a nessun altro.** Da
        # quando argostranslate non e' piu' in `requirements.txt`, *tutti* si
        # troverebbero questo avviso ambra addosso — e su GTA V in italiano non
        # c'e' niente da tradurre. Un avviso che quasi nessuno deve soddisfare e'
        # gia' scritto qui come il difetto che si spegne da solo nella testa di
        # chi lo legge: la ROI sotto 0,12, che c'era in tutte le sessioni.
        if s.traduzione_accesa:
            motivi.append(Motivo("traduzione_manca", (TRADUZIONE_MB, RIGA_PIP)))

    if traduzione and s.traduzione_ms > TRADUZIONE_MAX_MS:
        motivi.append(Motivo("traduzione_lenta",
                             (round(s.traduzione_ms), round(TRADUZIONE_MAX_MS))))

    return Scelta(tts=tts, traduzione=traduzione, motivi=tuple(motivi))


def dopo_lo_scarico(scelta: Scelta, presenti) -> Scelta:
    """Il motore scelto non e' arrivato: **non lo si sceglie**. Pura.

    E' la meta' che manca a ogni cura scritta guardando il difetto. Senza questa
    riga, una rete che cade a meta' dello scaricamento lascia scritto
    `tts.backend = kokoro` in configurazione con i pesi non sul disco: alla prima
    battuta il backend prova a scaricarli, non ci riesce, e la sessione parte
    lo stesso con un motore che non c'e'. Qui invece si retrocede a Piper e si
    dice perche' — che e' l'unica cosa che distingue un ripiego da un guasto.
    """
    if scelta.tts != "kokoro":
        return scelta
    avuti = set(presenti or ())
    if {"kokoro", "voci_kokoro"} <= avuti:
        return scelta
    return Scelta(
        tts="piper",
        traduzione=scelta.traduzione,
        motivi=scelta.motivi + (Motivo("motore_mancante"),),
    )


# ======================================================== i pezzi da scaricare =


@dataclass(frozen=True)
class Pezzo:
    """Un pezzo che deve stare sul disco: quanto pesa e da dove viene.

    `mb` e' misurato su questa macchina, non stimato, e serve a una cosa sola: a
    dire **prima** quanto si sta per aspettare. Un'attesa dichiarata e'
    un'attesa; un'attesa muta e' una finestra bloccata.
    """

    codice: str
    mb: int
    # Vero se il pezzo si prende dalla rete. `oneocr` no: si copia dallo
    # Strumento di cattura di Windows, quindi manca la rete e c'e' lo stesso.
    dalla_rete: bool = True


PEZZI: dict[str, Pezzo] = {
    # Le due voci italiane di Piper: 63,5 + 28,1 MB, misurati.
    "piper": Pezzo("piper", 92),
    # I pesi fp32 di Kokoro (325,5 MB) e gli otto stili (8 x 0,5 MB).
    "kokoro": Pezzo("kokoro", 326),
    "voci_kokoro": Pezzo("voci_kokoro", 5),
    # L'impronta della voce, cioe' chi parla. Serve a **tutti** i motori.
    "ecapa": Pezzo("ecapa", 25),
    # Il lettore di Windows. Non si scarica: si copia da un pacchetto gia'
    # installato, e senza di lui la catena legge con PP-OCR — che sul testo
    # bordato dei giochi legge peggio, senza dirlo.
    "oneocr": Pezzo("oneocr", 115, dalla_rete=False),
    # La coppia di lingue di Argos, 98 MB misurati per it->en.
    "traduzione": Pezzo("traduzione", 98),
}


def serve(scelta: Scelta, *, traduzione: bool = False,
          oneocr: bool = True) -> tuple[str, ...]:
    """I pezzi che questa scelta ha bisogno di trovare sul disco. **Pura.**

    **Non tutti quelli che esistono**: scaricare Kokoro su una macchina senza
    CUDA sarebbe 326 MB per un motore che non verra' acceso. E la coppia di
    lingue entra solo se la traduzione e' accesa — con la traduzione spenta
    sarebbero cento megabyte per una funzione che l'utente non ha chiesto, e
    quando la accendera' `make_traduttore` la scarica da solo dichiarandolo, che
    e' gia' il comportamento di adesso.
    """
    fuori: list[str] = ["ecapa"]
    if scelta.tts == "kokoro":
        fuori += ["kokoro", "voci_kokoro"]
    else:
        fuori.append("piper")
    if oneocr:
        fuori.append("oneocr")
    if traduzione and scelta.traduzione == "locale":
        fuori.append("traduzione")
    return tuple(fuori)


def da_scaricare(codici, presenti) -> tuple[str, ...]:
    """Quello che manca davvero, nell'ordine chiesto. **Pura.**"""
    avuti = set(presenti or ())
    return tuple(c for c in codici if c not in avuti)


def peso_mb(codici) -> int:
    """Quanti megabyte si sta per aspettare. **Pura.**"""
    return sum(PEZZI[c].mb for c in codici if c in PEZZI)


# ============================================== quello che tocca la macchina ==
#
# Da qui in giu' si misura e basta: nessuna di queste funzioni decide niente, e
# tutte consegnano numeri a `scegli()`. E' la riga che separa cio' che si
# verifica con numeri finti da cio' che ha bisogno di un disco, di una rete e di
# una scheda video.


# **Battute vere, e corte come lo sono davvero.** Misurare la sintesi su «hello
# world» darebbe il costo fisso del motore e non il suo passo; misurarla su un
# paragrafo darebbe una battuta che a schermo non compare mai. Queste vengono
# dalla registrazione su cui e' stato misurato tutto il resto di questo progetto.
BATTUTE: tuple[str, ...] = (
    "Lamar, che cazzo stai facendo?",
    "Niente, fratello. Sto solo guardando.",
    "Oggi recuperiamo veicoli acquistati da idioti.",
    "Non ci credo neanche un po'.",
    "Ma devo dare una svolta alla mia vita.",
    "Voglio vedere i soldi, adesso.",
)


def presenti(cfg) -> frozenset[str]:
    """Quali pezzi ci sono gia', chiedendolo **a chi li usa**.

    Nessun `Path.exists()` scritto qui dentro, ed e' la lezione che e' costata
    piu' cara di quanto sembri: l'archivio delle voci di Kokoro si considerava
    buono perche' il file c'era, e aggiungendo le voci inglesi il file vecchio —
    con dentro le sole due italiane — e' rimasto «buono» agli occhi di quella
    funzione. La prima voce inglese e' morta con un `KeyError` dentro
    `kokoro_onnx`, lontanissimo dal difetto. Chi mette qualcosa in cache
    controlli **cosa** c'e' dentro, non che ci sia — e chi lo controlla dopo
    chieda a lui, invece di scriverne una seconda versione che al primo pezzo
    nuovo dira' un'altra cosa.
    """
    fuori: set[str] = set()

    try:
        from speak.backends.piper import KNOWN, model_path

        if all(model_path(n, download=False) for n in KNOWN):
            fuori.add("piper")
    except Exception:
        pass

    try:
        from speak.backends.kokoro import model_path as kokoro_path

        kokoro_path(cfg.tts.kokoro_weights, download=False)
        fuori.add("kokoro")
    except Exception:
        pass

    try:
        from speak.backends.kokoro import voices_path

        voices_path(download=False)
        fuori.add("voci_kokoro")
    except Exception:
        pass

    try:
        from listen.embed import EcapaOnnxEmbedder

        EcapaOnnxEmbedder._fetch(False)
        fuori.add("ecapa")
    except Exception:
        pass

    try:
        from tools.fetch_oneocr import DESTINAZIONE, FILE

        if all((DESTINAZIONE / f).is_file() for f in FILE):
            fuori.add("oneocr")
    except Exception:
        pass

    try:
        import argostranslate.package as ap

        from translate.locale import coppia

        da, a = coppia(cfg.translate.source, cfg.translate.target)
        if da == a or any(p.from_code == da and p.to_code == a
                          for p in ap.get_installed_packages()):
            fuori.add("traduzione")
    except Exception:
        pass

    return frozenset(fuori)


def sonda_veloce(cfg) -> Sonda:
    """Cosa c'e' su questa macchina, **senza aprire un modello**. Circa un secondo.

    Il provider CUDA si chiede a ORT dopo il precaricamento delle DLL, che e' la
    riga senza la quale ORT ripiega sulla CPU senza dirlo. Ma qui e' ancora una
    **dichiarazione**: si sapra' se e' vera quando una sessione sara' aperta
    davvero, ed e' per questo che `Sonda.provider` esiste separato da
    `Sonda.cuda`.
    """
    from core import bloccati

    try:
        from core.onnx import preload

        preload()
        import onnxruntime as rt

        cuda = "CUDAExecutionProvider" in rt.get_available_providers()
    except Exception:  # onnxruntime assente o rotto: si dira' altrove
        cuda = False

    # **`find_spec` diceva di si' su un pacchetto che non si carica**, ed e' la
    # forma di verde falso piu' cara di questo progetto. Il file c'e' sul disco,
    # quindi `find_spec` lo trova; poi Windows si rifiuta di caricare la libreria
    # nativa che ci sta dentro. Il passo 6 concludeva percio' «traduzione: llm»,
    # scriveva `translate.backend = llm` e consegnava una sessione che muore alla
    # prima battuta — cioe' esattamente la cosa che questo modulo esiste per non
    # fare: `applica()` scrive quello che ha **verificato**, non quello che ha
    # scelto, e per verificarlo bisogna **caricarlo**.
    #
    # Il costo e' un import per pacchetto, pagato una volta (`core.bloccati` ha
    # la cache) e dentro un passo che gia' apre modelli veri.
    return Sonda(
        cuda=cuda,
        argos=bloccati.pezzo("argos").ok,
        llm=bloccati.pezzo("llm").ok,
        traduzione_accesa=cfg.translate.enabled,
        presenti=presenti(cfg),
    )


def misura_sintesi(cfg, backend: str) -> tuple[float, float, str]:
    """Quanto costa una battuta con quel motore, e quanto parlato produce.

    Torna `(p50 in ms, caratteri di parlato al secondo, provider ottenuto)`.

    **Il primo colpo non entra nella mediana.** Costruire il motore carica il
    modello — 1,7 s per Piper, di piu' per Kokoro su CUDA dove vanno compilati i
    kernel — e quel costo si paga una volta per sessione, non una volta per
    battuta. Includerlo qui vorrebbe dire scartare il motore migliore perche' ci
    mette due secondi ad accendersi; ed e' l'errore che `tools/bench_translate.py`
    fa ancora, mettendo la prima chiamata dentro la mediana.

    **E il passo si misura al netto del silenzio**, cioe' su quello che i
    backend consegnano dopo `taglia_silenzio`: SuperTonic imbottiva il 39%
    dell'uscita, e misurare il passo su quella imbottitura fa credere lento un
    motore che parla normale.
    """
    import time
    from dataclasses import replace

    import numpy as np

    from fuse.timing import spoken_length
    from speak.base import make_tts
    from speak.pool import build_pool

    # **La lingua di arrivo, non quella del gioco**, ed e' la stessa a tutti e
    # due: costruire il motore per l'inglese e poi misurarlo con una voce
    # italiana e' come chiedere a un modello di parlare con lo stile di un
    # altro — su Kokoro non e' nemmeno un difetto di accento, e' un `KeyError`.
    uscita = cfg.translate.target if cfg.translate.enabled else "it"
    tts = make_tts(replace(cfg.tts, backend=backend), lingua=uscita)
    pool = build_pool(backend=backend, lingua=uscita)
    if not pool:
        raise RuntimeError(f"nessuna voce per {backend} in {uscita!r}")
    voce = pool[0]

    # Il colpo a vuoto: paga il caricamento delle sessioni e si butta.
    tts.synthesize(BATTUTE[0], voce)

    tempi: list[float] = []
    caratteri = 0
    secondi = 0.0
    for testo in BATTUTE:
        t0 = time.perf_counter()
        fuori = tts.synthesize(testo, voce)
        tempi.append((time.perf_counter() - t0) * 1000.0)
        caratteri += spoken_length(testo)
        secondi += fuori.duration

    passo = caratteri / secondi if secondi > 0 else 0.0
    return (float(np.median(tempi)), float(passo),
            str(getattr(tts, "_provider", "") or ""))


def misura_traduzione(cfg, backend: str) -> float:
    """Il **p95** di una traduzione su questa macchina, in millisecondi.

    Il p95 e non il p50 perche' la traduzione sta dentro l'attesa di
    `speaker.decide_after_ms`: fin che ci sta dentro non costa niente, e a
    contare e' quante volte ne esce.

    Come in `translate/diagnosi.py`, il primo giro si butta — Argos paga 3937 ms
    di caricamento a freddo che dal vivo non si pagano mai, perche'
    `make_traduttore` fa gia' `prepara()` e `scalda()` prima della prima battuta.
    E le frasi sono **tutte diverse**: ripetendone una, argostranslate risponde
    dalla sua cache in 0 ms, che non e' la velocita' di traduzione di nessuno.
    """
    import time
    from dataclasses import replace

    import numpy as np

    from translate.base import make_traduttore

    tr = make_traduttore(replace(cfg.translate, enabled=True, backend=backend))
    tr.traduci(BATTUTE[0], "it", "en")  # a freddo: si butta

    tempi: list[float] = []
    for testo in BATTUTE[1:]:
        t0 = time.perf_counter()
        tr.traduci(testo, "it", "en")
        tempi.append((time.perf_counter() - t0) * 1000.0)
    if not tempi:
        return 0.0
    return float(np.percentile(tempi, 95))


def scarica(codici, cfg, *, dillo=None, fermati=None) -> dict[str, str]:
    """Prende i pezzi che mancano. Torna **quelli che non ce l'hanno fatta**.

    `dillo(codice, fatti, quanti)` viene chiamato prima di ogni pezzo, cosi' chi
    guarda vede a che punto siamo — sono fino a mezzo gigabyte, e mezzo gigabyte
    in silenzio e' una finestra che sembra bloccata.

    `fermati()` viene chiesto **fra un pezzo e l'altro** e non dentro: un
    trasferimento di `huggingface_hub` non si interrompe a meta' senza lasciare
    un file troncato, e un file troncato e' precisamente il difetto che
    `voices_path` esiste per non avere. Annullare quindi vuol dire «non
    cominciare il prossimo», ed e' quello che si dichiara a chi preme.

    **Un pezzo che fallisce non ferma gli altri, e non sparisce.** Senza rete si
    scarica quello che si puo' — niente e' gia' scaricabile da un disco locale —
    e cio' che manca torna indietro con il suo motivo, perche' chi ha chiamato
    possa dirlo. Continuare in silenzio con meno modelli di quelli chiesti e'
    esattamente il ripiego muto che questo file esiste per togliere.
    """
    dillo = dillo or (lambda *_: None)
    fermati = fermati or (lambda: False)
    codici = tuple(codici)
    falliti: dict[str, str] = {}

    for i, codice in enumerate(codici):
        if fermati():
            for restante in codici[i:]:
                falliti[restante] = "annullato"
            break
        dillo(codice, i, len(codici))
        try:
            _prendi(codice, cfg)
        except Exception as guasto:
            falliti[codice] = f"{type(guasto).__name__}: {guasto}".splitlines()[0]
    return falliti


# Le due fasi che non sono uno scaricamento, mandate sullo **stesso canale** di
# avanzamento dei pezzi. Un secondo canale vorrebbe dire due posti in cui
# aggiornare la stessa riga a schermo, e il secondo non lo aggiorna mai nessuno.
MISURA_SINTESI = "misura_sintesi"
MISURA_TRADUZIONE = "misura_traduzione"


@dataclass(frozen=True)
class Referto:
    """Com'e' andato il giro intero: cosa si e' scelto, cosa si e' trovato, cosa manca."""

    scelta: Scelta
    sonda: Sonda
    falliti: dict[str, str] = field(default_factory=dict)
    mb: int = 0


def esegui(cfg, *, passo=None, fermati=None) -> Referto:
    """Il giro intero: guarda, sceglie, scarica, **rimisura e semmai ricrede**.

    L'ordine e' l'unica cosa importante di questa funzione, e non e' quello che
    verrebbe naturale. Verrebbe naturale misurare i motori e poi scaricare il
    vincitore; ma i motori non si possono misurare finche' non sono sul disco, e
    scaricarli tutti sarebbe mezzo gigabyte per buttarne meta'. Quindi:

    1. si guarda cosa c'e' (un secondo, nessun modello aperto) e si sceglie;
    2. si scarica **solo quello che la scelta ha bisogno di trovare**;
    3. si misura per davvero, adesso che c'e';
    4. si rifa' la scelta con i numeri veri. Se cambia, si scarica il ripiego.

    Il quarto punto e' quello che rende onesto il resto: fino a li' si e' deciso
    su una dichiarazione — «ORT dice che il provider CUDA c'e'» — e chiedere un
    acceleratore non e' ottenerlo. Il giro si ferma comunque, perche' `scegli()`
    puo' solo retrocedere: da Kokoro si torna a Piper, e da Piper non si va da
    nessuna parte.
    """
    from dataclasses import replace

    passo = passo or (lambda *_: None)
    fermati = fermati or (lambda: False)

    sonda = sonda_veloce(cfg)
    scelta = scegli(sonda)
    falliti: dict[str, str] = {}
    mb = 0

    def prendi_il_necessario(sc: Scelta) -> tuple[Scelta, frozenset[str]]:
        """Scarica quello che serve a `sc`, e torna la scelta dopo lo scarico."""
        nonlocal falliti, mb
        avuti = presenti(cfg)
        manca = da_scaricare(
            serve(sc, traduzione=cfg.translate.enabled), avuti)
        if manca:
            mb += peso_mb(manca)
            falliti.update(scarica(manca, cfg, dillo=passo, fermati=fermati))
            avuti = presenti(cfg)
        return dopo_lo_scarico(sc, avuti), avuti

    scelta, avuti = prendi_il_necessario(scelta)
    if scelta.tts != "kokoro":
        # Il ripiego ha bisogno dei suoi pezzi, che il primo giro non ha preso.
        scelta, avuti = prendi_il_necessario(scelta)

    if fermati():
        return Referto(scelta, replace(sonda, presenti=avuti), falliti, mb)

    # -- adesso i modelli ci sono, quindi si puo' misurare --------------------
    try:
        passo(MISURA_SINTESI, 0, 0)
        ms, andatura, provider = misura_sintesi(cfg, scelta.tts)
        sonda = replace(sonda, sintesi_ms=ms, passo=andatura, provider=provider)
    except Exception as guasto:
        falliti[MISURA_SINTESI] = f"{type(guasto).__name__}: {guasto}".splitlines()[0]

    # **La traduzione si misura solo se il suo modello e' gia' qui.** Con la
    # traduzione spenta — che e' il default — scaricare cento megabyte per
    # cronometrarli sarebbe pagare una funzione che l'utente non ha chiesto.
    if scelta.traduzione and "traduzione" in avuti:
        try:
            passo(MISURA_TRADUZIONE, 0, 0)
            sonda = replace(
                sonda, traduzione_ms=misura_traduzione(cfg, scelta.traduzione))
        except Exception as guasto:
            falliti[MISURA_TRADUZIONE] = (
                f"{type(guasto).__name__}: {guasto}".splitlines()[0])

    # -- e con i numeri veri si rifa' la scelta -------------------------------
    sonda = replace(sonda, presenti=avuti)
    nuova = dopo_lo_scarico(scegli(sonda), avuti)
    if nuova.tts != scelta.tts:
        nuova, avuti = prendi_il_necessario(nuova)
        sonda = replace(sonda, presenti=avuti)
    return Referto(nuova, sonda, falliti, mb)


def applica(cfg, esito: Referto) -> tuple[str, ...]:
    """Scrive in configurazione quello che si e' deciso. Torna i campi toccati.

    **Solo quello che si e' verificato**, e non quello che si e' scelto: il
    traduttore entra solo se e' stato scelto davvero (vuoto vuol dire «manca il
    pacchetto, decidi tu»), e il lettore di Windows solo se i suoi file sono
    finiti sul disco. Scrivere `vision.ocr_backend = oneocr` con OneOCR non
    copiato darebbe una catena che non parte, e la scusa sarebbe che il banco
    aveva promesso.
    """
    toccati: list[str] = []

    def metti(percorso: str, valore) -> None:
        if getattr_percorso(cfg, percorso) != valore:
            cfg.set(percorso, valore)
            toccati.append(percorso)

    metti("tts.backend", esito.scelta.tts)
    # **`tts.device` lo legge solo Kokoro**, quindi si scrive solo scegliendo
    # Kokoro: metterlo sugli altri sarebbe un campo cambiato che non fa niente,
    # e questo progetto ne ha gia' contati sei. E si scrive `cuda` e non `auto`
    # perche' a questo punto la GPU e' stata **ottenuta** su una sessione vera:
    # da qui in poi un ripiego sulla CPU deve sollevare invece di succedere in
    # silenzio, che e' esattamente cosa distingue i due valori.
    if esito.scelta.tts == "kokoro":
        metti("tts.device", "cuda")
    if esito.scelta.traduzione:
        metti("translate.backend", esito.scelta.traduzione)
    if "oneocr" in esito.sonda.presenti:
        metti("vision.ocr_backend", "oneocr")
    return tuple(toccati)


def getattr_percorso(cfg, percorso: str):
    """Il valore di `sezione.campo`, per non riscrivere due volte lo `split`."""
    nodo = cfg
    for pezzo in percorso.split("."):
        nodo = getattr(nodo, pezzo)
    return nodo


def _prendi(codice: str, cfg) -> None:
    """Il singolo pezzo. Ogni riga chiama **la strada normale** del suo modulo.

    Nessun `hf_hub_download` scritto qui: il percorso, il nome del file dentro il
    repo e il controllo di completezza sono gia' scritti una volta in casa di chi
    li usa, e riscriverli qui sarebbe la nona volta della forma «una tabella
    scritta due volte». Il prezzo di questa scelta e' che questo file non sa
    quanti byte sono arrivati; il prezzo dell'altra sarebbe un pezzo che si
    scarica in un modo e si controlla in un altro.
    """
    if codice == "piper":
        from speak.backends.piper import KNOWN, model_path

        for nome in KNOWN:
            model_path(nome, download=True)
        return
    if codice == "kokoro":
        from speak.backends.kokoro import model_path

        model_path(cfg.tts.kokoro_weights, download=True)
        return
    if codice == "voci_kokoro":
        from speak.backends.kokoro import voices_path

        voices_path(download=True)
        return
    if codice == "ecapa":
        from listen.embed import EcapaOnnxEmbedder

        EcapaOnnxEmbedder._fetch(True)
        return
    if codice == "oneocr":
        from tools.fetch_oneocr import main as copia

        if copia([]) != 0:
            # Il modulo ha gia' scritto **perche'** su stderr; qui serve una
            # frase corta da mettere accanto alla riga, non la spiegazione
            # intera.
            raise RuntimeError("lo Strumento di cattura di Windows non c'e'")
        return
    if codice == "traduzione":
        from translate.locale import TraduttoreLocale

        tr = TraduttoreLocale(da=cfg.translate.source, a=cfg.translate.target)
        if not tr.prepara():
            raise RuntimeError("la coppia di lingue non si e' potuta installare")
        return
    raise ValueError(f"pezzo sconosciuto: {codice!r}")
