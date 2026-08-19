"""L'elenco dei parametri, **ricavato** dall'albero di config invece che scritto.

E' la fondamenta del pannello delle impostazioni: la UI non elenca i campi a
mano, li percorre. Un elenco scritto a mano diverge al primo campo aggiunto, e
questo progetto ha gia' pagato quattro volte per un campo dichiarato in config
che non leggeva nessuno (`max_ocr_hz`, `tts.device`, `background_mode`,
`overlay.ritardo`) — un campo che la UI non mostra e' lo stesso difetto visto
dall'altra parte.

**Le spiegazioni non si riscrivono, si estraggono.** Quasi ogni campo di
`core/config.py` ha sopra un commento che dice cosa fa, quanto e' stato misurato
e cosa succede a cambiarlo, spesso con la tabella della misura. Sono esattamente
il testo che l'utente vuole vedere accanto alla manopola. Riscriverli
significherebbe perdere le misure e inventare rischi al loro posto — quindi si
legge il **sorgente** con `ast` e si prendono quelli.

**E ogni campo deve dichiarare se si puo' cambiare a caldo.** Alcuni si leggono a
ogni fotogramma (colori, soglie, dimensioni); altri **una volta sola alla
costruzione** — il backend TTS, quello OCR, il dispositivo, la frequenza
dell'anello audio. Cambiare i secondi a sessione accesa non da' errore: da' una
sessione che gira con una configurazione diversa da quella che la UI mostra, che
e' il difetto peggiore possibile per uno strumento di misura.

Questo non si puo' dedurre guardando il tipo, quindi e' **dichiarato** qui sotto
in `FREDDI` — e c'e' una verifica che ogni campo sia classificato: aggiungerne
uno senza decidere rende la suite rossa, invece di lasciarlo scivolare nel
gruppo sbagliato in silenzio.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, fields, is_dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

SORGENTE = Path(__file__).resolve().parent / "config.py"

# **I campi che si leggono una volta sola.** Un prefisso che finisce con `.`
# vale per tutta la sezione; senza, e' il singolo percorso.
#
# La regola per stabilirlo non e' un'opinione: un campo e' freddo se il suo
# valore viene letto **nel costruttore** di qualcosa (una sessione ONNX, un
# flusso audio, un processo figlio) e quell'oggetto non si ricostruisce a
# sessione accesa. E' l'unica cosa che conta per l'utente: dopo averlo cambiato,
# serve o no ripremere Avvia?
FREDDI: tuple[str, ...] = (
    # il motore e dove gira: sessione ONNX costruita una volta
    "vision.ocr_backend",
    "vision.ocr_device",
    "tts.backend",
    "tts.device",
    "tts.samplerate",
    "tts.kokoro_weights",
    "tts.model_dir",
    "tts.voices",
    "tts.pool_size",
    "speaker.backend",
    "speaker.model_dir",
    "emotion.backend",
    "vad.backend",
    "translate.backend",
    "translate.model",
    "translate.model_dir",
    "translate.host",
    # **Tutta la traduzione si decide ad Avvia**, e finora undici campi
    # dichiaravano il contrario. `Traduzioni(make_traduttore(cfg.translate),
    # da=…, a=…, max_ms=…)` si costruisce nel costruttore della pipeline: la
    # coppia di lingue, i tempi, il registro e il modello finiscono **dentro**
    # quell'oggetto, che non si rilegge piu'. Peggio: con la traduzione spenta
    # `self.traduci` resta `None`, quindi accenderla a sessione avviata non
    # faceva assolutamente niente — e la finestra, non mettendoci il marchio
    # «all'avvio», prometteva che funzionasse. E' il difetto che l'utente ha
    # descritto come «l'applicazione del traduttore si bugga».
    #
    # Freddo non vuol dire «alla partenza del programma»: vuol dire «premi
    # Avvia». Accendere la traduzione **prima** di avviare funziona, ed e' il
    # caso normale.
    "translate.enabled",
    "translate.source",
    "translate.target",
    "translate.timeout_ms",
    "translate.net_timeout_ms",
    "translate.preserve_register",
    "translate.context_lines",
    "translate.llm_model",
    "translate.ollama_model",
    "translate.ollama_host",
    "translate.local_model",
    # E la finestra del tradotto si costruisce li' pure. Il suo **aspetto** no:
    # colore, carattere, blur e modo di coprire si cambiano a sessione accesa
    # (`OverlayBase.ristila`), e restano caldi perche' adesso e' vero.
    "translate.overlay",
    "translate.transparent",
    "correct.backend",
    "correct.model",
    "correct.host",
    # l'anello audio e la cattura: flussi aperti all'avvio
    "audio.",
    "capture.",
    # **Il cuscino dello streaming, e solo lui.** Gli altri sei campi di `mix.`
    # sono caldi davvero da quando `Mixer.ritara` li rilegge a ogni blocco;
    # questo no, perche' diventa un numero di campioni nel costruttore e la
    # battuta aperta ci sta gia' dentro. Cambiarlo a meta' sessione vorrebbe
    # dire spostare la soglia sotto una battuta che sta suonando.
    "mix.prebuffer_ms",
    # i lettori si costruiscono uno per area all'avvio
    # il lessico si carica una volta
    "vision.use_lexicon",
    "vision.lexicon_dir",
)


@dataclass(slots=True)
class Campo:
    """Un parametro, con tutto quello che serve a disegnargli una manopola."""

    percorso: str  # "vision.sat_max"
    sezione: str  # "vision"
    nome: str  # "sat_max"
    valore: Any
    default: Any
    tipo: str  # "bool" | "int" | "float" | "str" | "tuple" | "dict"
    aiuto: str  # il commento sopra il campo, cosi' com'e' scritto
    caldo: bool  # si puo' cambiare a sessione accesa?
    scelte: tuple[str, ...] = ()  # se il commento elenca `a | b | c`

    @property
    def modificabile(self) -> bool:
        """Se `Config.set` sa scrivere questo tipo.

        **Non tutti i campi sono manopole**, e fingere che lo siano e' peggio che
        ometterli: una casella di testo che accetta una modifica che non arriva
        da nessuna parte e' il difetto contro cui esiste il pannello. Era il caso
        dei due dizionari (`label.colors`, `label.voices`), che `_coerce` non
        trattava — trovato dal giro di andata e ritorno della verifica, non
        leggendo il codice.

        **Adesso li tratta**, ed era il difetto piu' grosso di tutti: quei due
        *sono* la tabella dei personaggi, cioe' «chi ha quale voce, deciso da
        te». Restava dichiarabile solo aprendo un file di profilo a mano. Il
        pannello ci mette una tabella vera (`ui.qt_controlli.Tabella`), non una
        casella di testo: una voce che non sta nel pool viene **ignorata** dal
        motore con un messaggio su stderr, cioe' un ripiego silenzioso — e
        l'unico modo di non poterla scrivere e' non poterla nemmeno digitare.
        """
        return True

    @property
    def sommario(self) -> str:
        """La prima frase dell'aiuto: quello che sta su una riga sola."""
        testo = " ".join(self.aiuto.split())
        if not testo:
            return ""
        taglio = testo.find(". ")
        return testo if taglio < 0 else testo[: taglio + 1]


# ------------------------------------------------------- i commenti, dal sorgente --


@lru_cache(maxsize=1)
def _commenti() -> dict[tuple[str, str], str]:
    """`(NomeDataclass, campo) -> commento`, letto dal sorgente di config.

    Si usa `ast` per sapere **dove** sta ogni campo, e le righe grezze per
    prendere il commento: l'albero sintattico i commenti li butta via, ed erano
    proprio loro il motivo per cui si guarda il sorgente.

    Si raccoglie il blocco di righe `#` contigue **sopra** il campo, piu' il
    commento in coda sulla stessa riga. Un blocco separato da una riga vuota
    appartiene ancora al campo che segue: e' cosi' che sono scritti.
    """
    if not SORGENTE.exists():
        # **Manca il sorgente: le spiegazioni non ci sono, e va detto.** Succede
        # in un pacchetto costruito senza `core/config.py` fra i dati. Morire
        # qui vorrebbe dire un programma che non parte per colpa dei testi
        # d'aiuto; tacere vorrebbe dire un pannello che sembra completo e ha
        # perso tutte le misure. Si torna vuoto **dopo averlo dichiarato**, e il
        # pannello mostra la riga che lo dice.
        import sys as _sys

        print(
            f"livedub: {SORGENTE} non c'e': le impostazioni saranno senza spiegazioni",
            file=_sys.stderr,
        )
        return {}
    testo = SORGENTE.read_text(encoding="utf-8")
    righe = testo.splitlines()
    albero = ast.parse(testo)
    fuori: dict[tuple[str, str], str] = {}

    for nodo in albero.body:
        if not isinstance(nodo, ast.ClassDef):
            continue
        for voce in nodo.body:
            if not isinstance(voce, ast.AnnAssign) or not isinstance(voce.target, ast.Name):
                continue
            campo = voce.target.id
            i = voce.lineno - 1  # 0-based: la riga del campo

            pezzi: list[str] = []
            in_coda = righe[i].partition("#")[2].strip() if "#" in righe[i] else ""

            j = i - 1
            sopra: list[str] = []
            while j >= 0:
                riga = righe[j].strip()
                if riga.startswith("#"):
                    sopra.append(riga.lstrip("#").strip())
                elif riga == "" and sopra:
                    # una riga vuota dentro un blocco di commento lo continua,
                    # ma solo se sopra c'e' ancora commento
                    k = j - 1
                    while k >= 0 and righe[k].strip() == "":
                        k -= 1
                    if k >= 0 and righe[k].strip().startswith("#"):
                        sopra.append("")
                        j = k + 1
                    else:
                        break
                else:
                    break
                j -= 1
            pezzi.extend(reversed(sopra))
            if in_coda:
                if pezzi:
                    pezzi.append("")
                pezzi.append(in_coda)
            testo_aiuto = "\n".join(pezzi).strip()
            if testo_aiuto:
                fuori[(nodo.name, campo)] = testo_aiuto
    return fuori


def _scelte(aiuto: str) -> tuple[str, ...]:
    """I valori ammessi, se il commento li elenca come `a | b | c`.

    E' la convenzione gia' usata in tutto `config.py` (`auto | wgc | dxcam |
    mss`), quindi non c'e' niente da aggiungere ai commenti: si legge quello che
    c'e'.

    Si guardano **la prima riga e l'ultima**, e non tutte. L'elenco sta in cima
    al blocco (`cpu | cuda | auto. Lo legge solo Kokoro`) oppure e' il commento
    in coda alla riga del campo (`ocr_backend: str = "ppocr"  # ppocr | oneocr |
    none`), che finisce in fondo all'aiuto. Nel mezzo una barra verticale e'
    quasi sempre il bordo di una tabella di misure, e prenderla darebbe un menu
    a tendina con dentro `---`.
    """
    # **In ordine, e non in un insieme.** Erano `{righe[0], righe[-1]}`: un
    # insieme di due stringhe si percorre nell'ordine dei loro hash, che Python
    # rimescola a ogni processo. Finche' una sola delle due righe e' un elenco
    # non si vede; il giorno in cui un commento ne avesse due diverse, lo stesso
    # campo avrebbe menu diversi da un avvio all'altro — un difetto che si
    # riproduce una volta su due e sembra stregoneria. Oggi non capita in nessun
    # campo (verificato), e per questo si corregge adesso che costa una riga.
    righe = [r for r in aiuto.splitlines() if r.strip()]
    for riga in ((righe[0], righe[-1]) if righe else ()):
        trovate = _elenco(riga)
        if trovate:
            return trovate
    return ()


def _elenco(riga: str) -> tuple[str, ...]:
    """`a | b | c` -> le tre alternative, o niente se quella riga non lo e'."""
    if "|" not in riga:
        return ()
    pezzi: list[str] = []
    for grezzo in riga.split("|"):
        # Ogni alternativa e' la **prima parola** del pezzo: dopo l'ultima c'e'
        # quasi sempre il resto della frase (`4b | 12b | 27b, o un altro
        # modello`), e prendere il pezzo intero perdeva l'elenco per colpa della
        # spiegazione che lo accompagna. Backtick e asterischi si tolgono: nei
        # commenti i nomi sono scritti `cosi'`.
        testo = grezzo.strip().strip("`*").strip()
        if ":" in testo:  # `backend: auto`
            testo = testo.rpartition(":")[2].strip().strip("`*")
        m = re.match(r"[A-Za-z0-9_+-]+(?:\.[A-Za-z0-9_+-]+)*", testo)
        if not m or not any(ch.isalnum() for ch in m.group(0)):
            return ()
        pezzi.append(m.group(0))
    if len(pezzi) < 2 or any(len(p) > 24 for p in pezzi):
        return ()
    return tuple(pezzi)


def e_caldo(percorso: str) -> bool:
    """Si puo' cambiare a sessione accesa?"""
    for freddo in FREDDI:
        if freddo.endswith("."):
            if percorso.startswith(freddo):
                return False
        elif percorso == freddo:
            return False
    return True


# --------------------------------------------------------------- l'albero intero --


def campi(cfg: Any, prefisso: str = "") -> list[Campo]:
    """Tutti i parametri di `cfg`, in ordine di dichiarazione.

    L'ordine e' quello del sorgente e non alfabetico: i campi di una sezione
    sono scritti nell'ordine in cui la catena li usa, e quell'ordine e' gia' una
    spiegazione.
    """
    fuori: list[Campo] = []
    commenti = _commenti()
    classe = type(cfg).__name__
    default = type(cfg)()
    for f in fields(cfg):
        valore = getattr(cfg, f.name)
        percorso = f"{prefisso}{f.name}"
        if is_dataclass(valore):
            fuori.extend(campi(valore, f"{percorso}."))
            continue
        aiuto = commenti.get((classe, f.name), "")
        # **Il valore vero e' la prova che quella riga sia un elenco di valori.**
        # `translate.ollama_model` vale `translategemma:4b` e il suo commento
        # dice `4b | 12b | 27b`: sono le **taglie**, non i valori del campo, e un
        # menu costruito su di loro scriverebbe `4b` dentro il nome del modello.
        # La regola vale in generale — se ne' il valore ne' il default stanno
        # nell'elenco, quell'elenco non parla di questo campo — e si corregge da
        # sola al prossimo commento scritto in modo ambiguo.
        trovate = _scelte(aiuto)
        if trovate and str(valore) not in trovate and str(getattr(default, f.name)) not in trovate:
            trovate = ()
        sezione, _, nome = percorso.rpartition(".")
        fuori.append(
            Campo(
                percorso=percorso,
                sezione=sezione or "generale",
                nome=nome,
                valore=valore,
                default=getattr(default, f.name),
                tipo=_tipo(valore),
                aiuto=aiuto,
                caldo=e_caldo(percorso),
                scelte=trovate,
            )
        )
    return fuori


def _tipo(valore: Any) -> str:
    if isinstance(valore, dict):
        return "dict"
    if isinstance(valore, bool):
        return "bool"
    if isinstance(valore, int):
        return "int"
    if isinstance(valore, float):
        return "float"
    if isinstance(valore, tuple):
        return "tuple"
    return "str"


def sezioni(cfg: Any) -> dict[str, list[Campo]]:
    """Gli stessi campi raggruppati per sezione, nell'ordine dell'albero."""
    fuori: dict[str, list[Campo]] = {}
    for campo in campi(cfg):
        fuori.setdefault(campo.sezione, []).append(campo)
    return fuori


# **Il nome umano di ogni sezione.** Non e' una traduzione del nome tecnico: e'
# la domanda a cui quella sezione risponde, che e' cio' che l'utente sta
# cercando quando apre il pannello.
TITOLI: dict[str, str] = {
    "generale": "Generale",
    "capture": "Cattura — da dove arrivano i fotogrammi",
    "vision": "Lettura — trovare e leggere il sottotitolo",
    "label": "Nome a schermo — chi parla, quando lo scrive il gioco",
    "correct": "Correzione — rattoppare gli artefatti dell'OCR",
    "translate": "Traduzione — e il sottotitolo disegnato sopra il gioco",
    "audio": "Audio — l'anello che raccoglie il suono del gioco",
    "vad": "Parlato — quando qualcuno sta parlando",
    "speaker": "Chi parla — l'impronta della voce e le identita'",
    "repeat": "Doppioni — non ridire due volte la stessa battuta",
    "emotion": "Emozione — quanto scaldare la voce",
    "tts": "Voce — il sintetizzatore e il pool di voci",
    "timing": "Tempi — quanto dura una battuta e quanta fretta si puo' chiedere",
    "mix": "Mixer — come la voce si versa sopra il gioco",
    "ui": "Sessione — cosa si tiene di una passata",
}

# **Quanti campi non hanno ancora una spiegazione scritta.** E' un numero da far
# scendere, mai salire: la verifica lo tiene come tetto, quindi un campo nuovo
# senza commento rende la suite rossa e chi lo aggiunge deve dire cosa fa. Non e'
# un difetto da correggere in blocco, e' un cricchetto.
SENZA_AIUTO_MAX = 50


# ---------------------------------------------------------------- i livelli --
#
# **Centosessantasei manopole sono la risposta giusta a una domanda che quasi
# nessuno fa.** Chi apre il programma per la prima volta vuole sentire il
# doppiaggio; chi ci ha giocato una settimana vuole cambiare la voce; solo chi
# sta tarando vuole `merge_similarity`. Mostrarli tutti allo stesso modo non e'
# neutrale: e' scegliere l'ultimo dei tre e far pagare agli altri due.
#
# I tre elenchi sono **dichiarati** e non dedotti, perche' non c'e' niente nel
# tipo di un campo che dica quanto conta. E c'e' una verifica che ogni percorso
# esista davvero: un elenco scritto a mano che si scolla dall'albero e' lo stesso
# difetto contro cui esiste `core/schema.py`.

# Quello che serve per far funzionare il programma, e nient'altro.
BASE: tuple[str, ...] = (
    # La lingua della finestra e' l'essenziale degli essenziali: e' l'unica
    # scelta che si possa fare **prima** di saper leggere le altre.
    "ui.lingua",
    "vision.roi",
    "vision.exclude_colored",
    "vision.sat_max",
    "tts.backend",
    "tts.device",
    "mix.duck_db",
    "mix.dub_gain_db",
    "translate.enabled",
    "translate.source",
    "translate.target",
)

# Quello che si tocca quando si e' capito come funziona: la qualita' della
# lettura, chi parla, i tempi.
MEDIO: tuple[str, ...] = BASE + (
    "capture.fps",
    "vision.ocr_backend",
    "vision.ocr_device",
    "vision.line_pad",
    "vision.white_min_luma",
    "vision.grey_min_luma",
    "vision.contrast_min",
    "vision.max_ocr_hz",
    "speaker.backend",
    "speaker.decide_after_ms",
    "speaker.similarity",
    "speaker.max_speakers",
    "speaker.gender_fallback",
    "tts.pool_size",
    "tts.voices",
    "tts.native_rate_max",
    "timing.rate_max",
    "timing.accepted_delay_ms",
    "translate.backend",
    "translate.background_mode",
    "translate.overlay",
    "mix.duck_hold_ms",
)

LIVELLI = ("base", "medio", "esperto")


def livello(percorso: str) -> str:
    """Da che livello in su questo campo si mostra."""
    if percorso in BASE:
        return "base"
    if percorso in MEDIO:
        return "medio"
    return "esperto"


def visibile_a(percorso: str, livello_scelto: str) -> bool:
    """Se `percorso` va mostrato a chi ha scelto `livello_scelto`."""
    ordine = {"base": 0, "medio": 1, "esperto": 2}
    return ordine[livello(percorso)] <= ordine.get(livello_scelto, 2)


# ------------------------------------------------------------- gli intervalli --
#
# **`Config.set` controlla il tipo, non il senso.** `capture.fps = -5` passa,
# `speaker.decide_after_ms = 99999` pure: il primo ferma la cattura, il secondo
# rende il programma muto, e nessuno dei due da' errore. Sono le domande 27 e 28
# di `DOMANDE_PRODUZIONE.md`.
#
# Gli intervalli sono **dichiarati** e non dedotti, perche' non c'e' niente nel
# tipo che dica che una frequenza non puo' essere negativa. Dove il limite e' una
# proprieta' fisica (una saturazione sta fra 0 e 255, una frazione fra 0 e 1) e'
# ovvio; dove e' una scelta, il numero e' scritto qui e la ragione accanto.
#
# **Non si correggono in silenzio.** Un valore fuori scala viene rifiutato e
# **detto**: correggerlo di nascosto darebbe una sessione che gira con un numero
# diverso da quello scritto, che e' il difetto contro cui tutta questa UI esiste.
LIMITI: dict[str, tuple[float, float]] = {
    # fisici: oltre non vuol dire niente
    "vision.sat_max": (0, 255),
    "vision.white_min_luma": (0, 255),
    "vision.grey_min_luma": (0, 255),
    "vision.luma_percentile": (0, 100),
    "vision.sat_percentile": (0, 100),
    "vad.floor_percentile": (0, 100),
    # frazioni
    "vision.min_line_fill": (0.0, 1.0),
    "vision.sat_ink_max": (0.0, 1.0),
    "vision.min_color_word_frac": (0.0, 1.0),
    "vision.ink_min_columns": (0.0, 1.0),
    "vision.diff_threshold": (0.0, 1.0),
    "speaker.similarity": (0.0, 1.0),
    "speaker.merge_similarity": (0.0, 1.0),
    "speaker.name_min_score": (0.0, 1.0),
    "repeat.similarity": (0.0, 1.0),
    "repeat.containment": (0.0, 1.0),
    "vision.continue_similarity": (0.0, 1.0),
    "vision.continue_containment": (0.0, 1.0),
    "vision.max_wrong_frac": (0.0, 1.0),
    # scelte, col perche' accanto
    "capture.fps": (1, 240),          # sotto 1 la cattura si ferma
    "capture.roi_margin": (0.0, 0.5),  # oltre meta' schermo non e' piu' una fascia
    "vision.max_ocr_hz": (0, 60),     # 0 = nessun tetto
    "vision.line_pad": (0.0, 2.0),    # oltre il doppio della banda e' un'altra riga
    "vision.line_grow": (0.0, 4.0),
    "vision.stable_reads": (1, 20),   # zero letture concordi vuol dire nessuna conferma
    "vision.min_ocr_chars": (0, 100),
    "vision.min_line_height": (1, 500),
    # **Sopra i due secondi il programma sembra rotto.** L'attesa per decidere chi
    # parla vale 500 ms dei 1239 di latenza: a 99999 non parla piu' nessuno, e
    # l'utente non ha modo di collegare le due cose.
    "speaker.decide_after_ms": (0, 2000),
    "speaker.max_wait_ms": (0, 5000),
    "speaker.min_clip_ms": (0, 5000),
    "speaker.lead_ms": (0, 2000),
    "speaker.max_speakers": (1, 64),
    "tts.pool_size": (1, 32),
    "tts.samplerate": (8000, 48000),
    # **Il tetto della fretta: sopra 1,5 le consonanti spariscono.** Misurato:
    # l'integrita' cade a 1,10 su SuperTonic e 1,30 su Kokoro.
    #
    # **L'intervallo arriva a 3,0 su richiesta, e non e' la stessa cosa del
    # default.** Il gradino di WSOLA sta dove stava — la fine della battuta
    # sopravvive fino a 1,25 e crolla da 1,30 in su — quindi `timing.rate_max`
    # resta 1,25 e chi lo alza sa cosa compra: sopra il gradino WSOLA non
    # accelera, **butta via**, e a 3,0 butta via due terzi. Il limite serve a
    # rendere possibile la prova, non a consigliarla.
    "timing.rate_max": (1.0, 3.0),
    # **La velocita' del parlato non aveva un intervallo, quindi restava una
    # casella di testo** — proprio il campo che la gente vuole toccare per primo.
    # I capi sono quelli oltre cui non e' piu' parlato: sotto 0,7 e' un disco
    # rallentato, sopra 1,5 le consonanti spariscono (misurato sul tetto di WSOLA).
    "tts.speed": (0.7, 1.5),
    "tts.kokoro_speed": (0.7, 1.5),
    "tts.gap_seconds": (0.0, 2.0),
    "translate.overlay_min_s": (0.0, 10.0),
    "translate.outline": (0.0, 8.0),
    "translate.context_lines": (0, 8),
    "vision.hold_frames": (0, 120),
    "speaker.name_min_score": (0.0, 1.0),
    "timing.rate_min": (0.3, 1.0),
    # **Fino a 3,0, ma chi consegna quel numero e' uno solo.** Questa e' la
    # fretta che si **chiede** al motore, e ogni motore la taglia al proprio
    # tetto di integrita' prima di parlare: SuperTonic a 1,10, Kokoro a 1,30
    # (`velocita_effettiva` nei due backend), Piper non ha tetto e la esegue
    # tutta. Il residuo non si perde — cade su WSOLA, che a sua volta si ferma a
    # `timing.rate_max`. Alzare questo campo da solo non fa quindi correre
    # SuperTonic e Kokoro: sposta soltanto piu' lavoro sul motore quando il
    # motore lo sa fare.
    #
    # Il tetto duro della catena resta 3,0 anche a monte: `core/pipeline.py`
    # chiude la richiesta con `min(nativo * gain, 3.0)`, e i due numeri sono lo
    # stesso numero apposta.
    "tts.native_rate_max": (1.0, 3.0),
    "timing.accepted_delay_ms": (0, 5000),
    "audio.samplerate": (8000, 192000),
    "audio.blocksize": (32, 4800),
    "audio.ring_seconds": (1.0, 120.0),
    "mix.duck_db": (-60.0, 0.0),      # positivo alzerebbe il gioco invece di abbassarlo
    "mix.dub_gain_db": (-40.0, 20.0),
    "mix.prebuffer_ms": (0, 2000),
    # **I tre tempi del duck.** Il pavimento e' 1 ms e non 0 perche' un salto di
    # guadagno istantaneo si sente come un clic — l'inviluppo esiste per quello.
    # Il tetto dell'attacco e' mezzo secondo perche' l'attacco e' anche
    # l'anticipo con cui il mixer abbassa il gioco (`_starts_soon`): piu' in
    # la', il gioco si abbassa mezzo secondo prima che qualcuno parli.
    "mix.duck_attack_ms": (1, 500),
    "mix.duck_release_ms": (1, 3000),
    # Zero e' un valore vero: vuol dire «non aspettare, rilascia e basta».
    "mix.duck_hold_ms": (0.0, 5000.0),
    "translate.background_opacity": (0.0, 1.0),
    "translate.font_frac": (0.0, 0.5),
    "translate.blur_strength": (0.0, 100.0),
}


def limiti(percorso: str) -> tuple[float, float] | None:
    """L'intervallo ammesso per un campo, se ne ha uno dichiarato."""
    return LIMITI.get(percorso)


def fuori_scala(percorso: str, valore) -> str:
    """Perche' quel valore non va bene, o stringa vuota se va bene.

    Torna un **messaggio per l'utente** e non un booleano: «fra 0 e 255» dice
    cosa fare, `False` dice solo che c'e' stato un rifiuto.
    """
    coppia = LIMITI.get(percorso)
    if coppia is None:
        return ""
    try:
        n = float(valore)
    except (TypeError, ValueError):
        return ""
    basso, alto = coppia
    if n < basso or n > alto:
        def _f(x: float) -> str:
            return f"{x:g}"
        return f"deve stare fra {_f(basso)} e {_f(alto)}"
    return ""
