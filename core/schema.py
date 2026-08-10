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
    "correct.backend",
    "correct.model",
    "correct.host",
    # l'anello audio e la cattura: flussi aperti all'avvio
    "audio.",
    "capture.",
    # i lettori si costruiscono uno per area all'avvio
    "vision.aree",
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

        **Non tutti i campi sono manopole**, e fingere che lo siano e' peggio
        che ometterli: `label.colors` e' un dizionario nome->colore e
        `_coerce` non lo tratta, quindi una casella di testo che lo mostra
        accetterebbe una modifica che non arriva da nessuna parte. Il pannello
        lo mostra spento, con scritto perche'. Trovato dal giro di andata e
        ritorno della verifica, non leggendo il codice.
        """
        return self.tipo != "dict"

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
    righe = [r for r in aiuto.splitlines() if r.strip()]
    for riga in ({righe[0], righe[-1]} if righe else ()):
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
