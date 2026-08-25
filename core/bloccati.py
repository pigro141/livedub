"""Quello che questa macchina non lascia caricare, **detto invece che scoperto**.

## Perche' esiste

Smart App Control — acceso di serie sulle installazioni pulite di Windows 11 —
rifiuta di caricare una libreria nativa di cui non conosce la reputazione. Non e'
un criterio sulla firma (numpy non e' firmato e passa) ne' sull'eta' (opencv 4.13
passa e la 4.14 no): e' la reputazione della **singola copia del file**, che una
macchina appena installata non ha ancora.

Quello che arriva a chi apre il programma e' questo:

    ImportError: DLL load failed while importing _winrt: Un criterio di
    controllo dell'applicazione ha bloccato il file.

cioe' una riga che non dice ne' **cosa** non funzionera' ne' **cosa fare**. E'
esattamente la forma che questo progetto paga piu' cara — *un ripiego che non si
dichiara e' peggio di un errore* — perche' chi la legge conclude che il programma
e' rotto, e chi non la legge (il pannello che offre la scelta) promette una
funzione che dara' errore.

Questo modulo e' l'unico posto che sa rispondere a «questo pezzo si carica su
questa macchina?», e risponde con **un codice piu' una frase**, non con
un'eccezione.

## Le due cose che non sono ovvie

**Importare non e' usare, e la differenza e' misurata.** `piper-tts` importa
benissimo e muore alla **prima sintesi**, perche' `espeakbridge.pyd` si apre
pigramente; `llama-cpp-python` importa il modulo Python e solleva un
`RuntimeError` — non un `ImportError` — quando `ctypes` prova ad aprire
`llama.dll`. Per questo `prova()` accetta un `usa`: una funzione che **fa
lavorare** il pezzo. Senza, si archivia un verde falso.

**La frase del blocco e' tradotta, quindi non si scrive a mano.** Su questa
macchina e' «Un criterio di controllo dell'applicazione ha bloccato il file», su
una inglese e' «An Application Control policy has blocked this file»: cercare la
prima nel testo dell'eccezione funzionerebbe **solo in italiano**, e altrove il
blocco tornerebbe a essere un errore incomprensibile — cioe' il difetto che
questo modulo esiste per togliere, riprodotto in quaranta lingue. La frase la si
chiede quindi **a Windows**, con `FormatMessageW` sul codice 4551, e la si
confronta con quella dell'eccezione: cosi' e' giusta per costruzione nella lingua
del sistema, qualunque sia.

Il codice si legge direttamente quando c'e' (`OSError.winerror`, cioe' un
`ctypes.CDLL` fallito); da un `import` fallito **non c'e'** — Python lascia solo
il testo — ed e' l'unico motivo per cui il confronto sulla frase serve.
"""

from __future__ import annotations

import ctypes
import importlib
from dataclasses import dataclass

# `ERROR_VIRUS_INFECTED`? No: 4551 e' «An Application Control policy has blocked
# this file», cioe' precisamente Smart App Control / WDAC. E' il numero che si
# vede in `OSError.winerror` quando a fallire e' un `ctypes.CDLL`.
CODICE_CRITERIO = 4551

# Gli stati che `prova()` puo' restituire. Sono quattro e non due perche' «non
# c'e'» e «c'e' e non si carica» chiedono all'utente due cose diverse: la prima
# si cura con un `pip install`, la seconda no.
OK = "ok"                # si carica e funziona
CRITERIO = "criterio"    # c'e', ma il criterio di Windows lo blocca
ASSENTE = "assente"      # non installato
GUASTO = "guasto"        # c'e', si carica, e si rompe per un altro motivo

# Quali stati sono **rinunce** e non conferme. Stessa distinzione di
# `core.banco.AVVISI`, e per la stessa ragione: dare lo stesso segno di spunta a
# «non l'hai installato» e a «funziona» e' il ripiego silenzioso messo in figura.
RINUNCE: frozenset[str] = frozenset({CRITERIO, ASSENTE, GUASTO})


def frase_di_sistema(codice: int = CODICE_CRITERIO) -> str:
    """La frase con cui **Windows** descrive quel codice, nella lingua di qui.

    Chiederla al sistema invece di scriverla e' tutto il punto: la stessa riga
    scritta a mano funzionerebbe solo sulle macchine italiane.
    """
    FORMAT_MESSAGE_FROM_SYSTEM = 0x1000
    FORMAT_MESSAGE_IGNORE_INSERTS = 0x0200
    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.FormatMessageW(
        FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        None, int(codice), 0, buf, len(buf), None,
    )
    return buf.value[:n].strip() if n else ""


def _normale(s: str) -> str:
    """Per confrontare due frasi di Windows senza inciampare sul punto finale."""
    return " ".join(str(s).split()).strip(" . ").casefold()


def e_criterio(exc: BaseException) -> bool:
    """Questa eccezione e' il criterio di Windows che blocca un file?

    Due strade, e servono tutte e due. Un `ctypes.CDLL` fallito porta il numero
    (`winerror`); un `import` fallito porta **solo il testo**, quindi li' si
    confronta con la frase che il sistema stesso da' per quel numero.
    """
    if getattr(exc, "winerror", None) == CODICE_CRITERIO:
        return True
    attesa = _normale(frase_di_sistema())
    if not attesa:
        return False
    return attesa in _normale(" ".join(str(a) for a in (exc.args or (exc,))))


@dataclass(frozen=True, slots=True)
class Esito:
    """Se quel pezzo si puo' usare qui, e — quando no — perche'.

    `dettaglio` e' il testo dell'eccezione vera: si tiene perche' la diagnosi che
    non lo aveva ha fatto perdere una sessione a scambiare un blocco per un
    pacchetto mancante.
    """

    nome: str
    stato: str = OK
    dettaglio: str = ""

    @property
    def ok(self) -> bool:
        return self.stato == OK

    @property
    def rinuncia(self) -> bool:
        return self.stato in RINUNCE


def perche(esito: Esito, serve_a: str = "", rimedio: str = "") -> str:
    """La riga da mettere nel registro: **cosa cade**, perche', e cosa si puo' fare.

    Una riga sola e in italiano, come tutto il registro. Le tre parti sono
    separate apposta: senza «cosa cade» il messaggio e' una curiosita' tecnica,
    senza «perche'» sembra un difetto del programma, e senza «cosa fare» e' una
    porta chiusa.
    """
    cade = f": cade {serve_a}" if serve_a else ""
    if esito.stato == CRITERIO:
        testo = (f"«{esito.nome}» e' bloccato da Smart App Control di Windows e "
                 f"non carica su questa macchina{cade}")
    elif esito.stato == ASSENTE:
        testo = f"«{esito.nome}» non e' installato{cade}"
    elif esito.stato == GUASTO:
        testo = f"«{esito.nome}» non si carica{cade}"
    else:
        return f"«{esito.nome}» e' disponibile"
    if rimedio:
        testo += f". {rimedio}"
    if esito.dettaglio:
        testo += f" ({esito.dettaglio})"
    return testo


class Rinuncia(RuntimeError):
    """Chiesto un pezzo che qui non c'e'. Porta l'esito, non solo una frase.

    E' un'eccezione e non un ripiego silenzioso perche' chi la solleva **non sa**
    cosa fare al posto suo: il correttore dell'OCR spento e' innocuo, un
    traduttore spento a meta' scena no. Chi la prende decide; ma la prende
    sapendo cosa e' successo, che e' l'unica cosa che l'`ImportError` grezzo non
    diceva.
    """

    def __init__(self, esito: Esito, serve_a: str = "", rimedio: str = "") -> None:
        super().__init__(perche(esito, serve_a, rimedio))
        self.esito = esito


# La memoria delle prove gia' fatte. Un import bloccato costa poco, ma `usa`
# puo' costare una sintesi vera: si chiede una volta per processo.
_fatte: dict[str, Esito] = {}


def prova(modulo: str, *, usa=None, nome: str = "") -> Esito:
    """Questo modulo si carica **e funziona** qui? Risposta in cache.

    `usa` riceve il modulo importato e deve **farlo lavorare**: e' la differenza
    fra un verde e un verde falso, e in questo progetto e' gia' costata una
    diagnosi intera. Un `usa` che solleva `Rinuncia` la lascia passare cosi'
    com'e'.
    """
    chiave = nome or modulo
    memo = _fatte.get(chiave)
    if memo is not None:
        return memo
    try:
        m = importlib.import_module(modulo)
        if usa is not None:
            usa(m)
        esito = Esito(chiave, OK)
    except ModuleNotFoundError as e:
        # **Solo se manca *questo* modulo.** Un `ModuleNotFoundError` su una sua
        # dipendenza e' un'altra storia, e chiamarlo «non installato» manderebbe
        # a reinstallare il pacchetto sbagliato.
        radice = modulo.split(".")[0]
        assente = (e.name or "").split(".")[0] == radice
        esito = Esito(chiave, ASSENTE if assente else GUASTO, str(e))
    except Exception as e:  # noqa: BLE001 - qui si classifica tutto, apposta
        esito = Esito(chiave, CRITERIO if e_criterio(e) else GUASTO, str(e))
    _fatte[chiave] = esito
    return esito


def dimentica(chiave: str = "") -> None:
    """Butta via la cache. Serve alle verifiche, e a chi installa senza riavviare."""
    if chiave:
        _fatte.pop(chiave, None)
    else:
        _fatte.clear()


# ============================================================ i pezzi noti ==

# **I pezzi opzionali, dichiarati qui e non indovinati da chi chiama.** Ognuno
# porta il modulo da provare, cosa cade se non c'e' e cosa si puo' fare. Sono
# qui e non sparsi perche' il pannello, il banco e la catena devono dare la
# **stessa** risposta: tre posti che si chiedono la stessa cosa in tre modi sono
# tre posti che possono contraddirsi, e in questo progetto l'hanno gia' fatto.
#
# `usa` c'e' dove importare non basta. Per `llama_cpp` non serve: la libreria
# nativa si apre gia' all'import del modulo, ed e' li' che solleva.
PEZZI: dict[str, dict] = {
    "llm": {
        "modulo": "llama_cpp",
        "serve_a": "la traduzione «llm» e il correttore dell'OCR",
        "rimedio": "usa «locale» (Argos) o «ollama», che non hanno questo vincolo",
    },
    "wgc": {
        "modulo": "windows_capture",
        "serve_a": "la cattura della sola finestra con Windows Graphics Capture",
        "rimedio": "si ripiega su PrintWindow, che cattura la stessa finestra "
                   "senza librerie in piu'",
    },
    "argos": {
        "modulo": "argostranslate.translate",
        "serve_a": "la traduzione «locale»",
        "rimedio": "rilancia tools\\installa_traduzione.ps1, oppure usa «google»",
    },
    # **`cv2` non e' opzionale come gli altri tre**: mezza catena lo usa, e qui
    # riguarda solo chi *dipinge* — sfocatura e cancellatura lo importano dentro
    # la funzione che disegna, cioe' dentro il ciclo video. Bloccato, il difetto
    # uscirebbe come un ImportError su un fotogramma qualunque, dove nessuno lo
    # collega alla riga che l'ha acceso.
    "opencv": {
        "modulo": "cv2",
        "serve_a": "coprire il sottotitolo originale sfocandolo o cancellandolo",
        "rimedio": "il riquadro pieno (`translate.background_mode=riquadro`) non "
                   "ne ha bisogno, e per costruzione non ha nemmeno il ritardo",
    },
}


def pezzo(chiave: str) -> Esito:
    """L'esito di uno dei pezzi dichiarati in `PEZZI`."""
    dati = PEZZI[chiave]
    return prova(dati["modulo"], nome=chiave, usa=dati.get("usa"))


def spiega(chiave: str) -> str:
    """La riga di registro per uno dei pezzi dichiarati."""
    dati = PEZZI[chiave]
    return perche(pezzo(chiave), dati.get("serve_a", ""), dati.get("rimedio", ""))


# **Quali scelte del pannello dipendono da quali pezzi.** Sta qui e non nella
# finestra per la regola gia' pagata: le regole stanno fuori da Qt, cosi' si
# verificano senza aprirlo — ed e' la parte del programma che non aveva nessuna
# verifica e in cui stavano quattro dei cinque difetti trovati rileggendo a
# freddo.
SCELTE: dict[str, dict[str, str]] = {
    "translate.backend": {"llm": "llm", "locale": "argos"},
    "correct.backend": {"llm": "llm"},
    "capture.backend": {"wgc": "wgc"},
}


# Quanto si e' disposti ad aspettare per marcare una voce di menu. Non e' un
# numero di prudenza: **una prova che riesce puo' costare piu' di una che
# fallisce**. Qui un pacchetto bloccato risponde in 49-157 ms — la DLL non si
# apre e basta — ma `argostranslate` che *funziona* tira dentro stanza e torch,
# cioe' secondi. Pagarli mentre si disegna una scheda vorrebbe dire una finestra
# che si apre lenta per scrivere un avviso che quasi sempre non serve.
ENTRO_MS = 400.0


def scelte_indisponibili(percorso: str, entro_ms: float = ENTRO_MS) -> dict[str, str]:
    """`{valore: perche' non va}` per un campo a scelta, o un dizionario vuoto.

    **Vuoto vuol dire «non ho niente da dichiarare», non «vanno tutte».** La
    differenza conta solo qui dentro: se la prova non risponde entro `entro_ms`
    la voce **non si marca**, e va bene — non marcare non promette niente,
    mentre marcare a torto sarebbe un avviso che nessuno puo' soddisfare, e
    quelli si spengono da soli nella testa di chi li legge. La prova intanto
    continua e finisce in cache, quindi la volta dopo che si disegna la scheda
    l'avviso c'e'.

    Chi invece **deve** sapere la verita' prima di partire — `make_traduttore`,
    `make_correttore`, il banco — chiama `pezzo()` e aspetta: li' mezzo secondo
    in piu' all'Avvia e' esattamente il prezzo giusto per non morire a meta'
    scena.
    """
    fuori: dict[str, str] = {}
    for valore, chiave in SCELTE.get(percorso, {}).items():
        dati = PEZZI[chiave]
        e = _entro(chiave, entro_ms)
        if e is not None and not e.ok:
            fuori[valore] = perche(e, dati.get("serve_a", ""), dati.get("rimedio", ""))
    return fuori


def _entro(chiave: str, entro_ms: float) -> Esito | None:
    """L'esito, se arriva in tempo. `None` = «non lo so ancora», e non e' un no.

    La prova gira in un thread che **non trattiene il programma** (`daemon`): se
    sfora, questa funzione lascia perdere e quella continua per conto suo fino a
    riempire la cache.
    """
    import threading

    memo = _fatte.get(chiave)
    if memo is not None or entro_ms <= 0:
        return memo if memo is not None else pezzo(chiave)
    t = threading.Thread(target=pezzo, args=(chiave,), daemon=True)
    t.start()
    t.join(entro_ms / 1000.0)
    return _fatte.get(chiave)


def esigi(chiave: str):
    """Il modulo, o una `Rinuncia` che dice perche' no. Mai un `ImportError` grezzo."""
    e = pezzo(chiave)
    if not e.ok:
        dati = PEZZI[chiave]
        raise Rinuncia(e, dati.get("serve_a", ""), dati.get("rimedio", ""))
    return importlib.import_module(PEZZI[chiave]["modulo"])
