"""Traduzione via Ollama, e in particolare **TranslateGemma**.

Ollama e' gia' installato su molte macchine da gioco e tiene i modelli fuori dal
venv: si parla con lui in HTTP sulla porta 11434, senza pacchetti e senza toccare
l'ambiente. E' la strada piu' comoda per provare un modello grosso senza montare
niente.

## Il prompt di TranslateGemma non e' un prompt qualunque

Il modello e' addestrato su **un** formato, e usarne un altro non da' errore: da'
una traduzione peggiore, che e' molto piu' difficile da notare. Il template, come
lo pubblica la scheda del modello:

    You are a professional {LINGUA} ({codice}) to {LINGUA} ({codice}) translator.
    Your goal is to accurately convey the meaning and nuances of the original
    {LINGUA} text while adhering to {LINGUA} grammar, vocabulary, and cultural
    sensitivities.
    Produce only the {LINGUA} translation, without any additional explanations or
    commentary. Please translate the following {LINGUA} text into {LINGUA}:


    {TESTO}

**Due righe vuote prima del testo**, e lo dice la scheda a parole. Un dettaglio
del genere e' esattamente il tipo di cosa che si sbaglia in silenzio: la
traduzione esce lo stesso, un po' peggio, e si finisce per concludere che il
modello non e' un granche'.

## Le taglie

    translategemma:4b     3,3 GB    la piu' veloce
    translategemma:12b    8,1 GB
    translategemma:27b     17 GB    la migliore

Su una scheda da 8 GB solo la 4b sta in VRAM insieme al gioco; le altre girano
comunque, spostando i livelli in RAM, ma piano.

## E c'e' una domanda che su questo materiale viene prima della qualita'

I sottotitoli di GTA V sono pieni di parolacce e di insulti. Un modello allineato
che le **ammorbidisce** — o che si rifiuta di tradurre — non e' inadatto a
questo progetto per una questione di gusto: consegnerebbe un doppiaggio che dice
un'altra cosa rispetto a quello che c'e' scritto a schermo, e il difetto
sembrerebbe dell'OCR. `tools/bench_translate.py --parolacce` lo misura, e va
guardato prima di qualunque numero sulla qualita'.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

# Le lingue che il template nomina per esteso. TranslateGemma vuole **il nome e
# il codice**, non solo il codice.
LINGUE: dict[str, str] = {
    "it": "Italian",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "zh-Hans": "Chinese",
    "ko": "Korean",
    "ar": "Arabic",
    "nl": "Dutch",
    "pl": "Polish",
}


# **La riga che serve a non farsi riscrivere i dialoghi.** Misurata: senza,
# TranslateGemma 4b tiene il registro volgare in **0 casi su 6**; con, in 3.
# Sostituisce «cultural sensitivities» del template originale, che e'
# probabilmente proprio la frase che invita ad ammorbidire.
REGISTRO = (
    "This is dialogue from a crime videogame: profanity and vulgar register are "
    "part of the meaning and MUST be preserved literally in {LINGUA}. Do not "
    "soften, censor or paraphrase them."
)


def prompt_translategemma(testo: str, da: str, a: str, registro: bool = True) -> str:
    """Il template della scheda del modello, incluse le due righe vuote.

    Con `registro` la frase sulle «cultural sensitivities» viene sostituita da
    una che chiede di **non** ammorbidire. Toccare il template di un modello
    addestrato su quel template peggiora la traduzione in generale — ma su questo
    materiale una traduzione un po' peggiore e fedele vale piu' di una elegante
    che dice un'altra cosa.
    """
    l_da, l_a = LINGUE.get(da, da), LINGUE.get(a, a)
    coda = (
        REGISTRO.replace("{LINGUA}", l_a)
        if registro
        else f"{l_a} grammar, vocabulary, and cultural sensitivities."
    )
    inizio = (
        f"You are a professional {l_da} ({da}) to {l_a} ({a}) translator. "
        f"Your goal is to accurately convey the meaning and nuances of the "
        f"original {l_da} text while adhering to "
    )
    if registro:
        inizio += f"{l_a} grammar and vocabulary. "
    return (
        f"{inizio}{coda}\n"
        f"Produce only the {l_a} translation, without any additional explanations "
        f"or commentary. Please translate the following {l_da} text into {l_a}:\n"
        f"\n\n{testo}"
    )


class TraduttoreOllama:
    """Parla con Ollama in HTTP. Nessun pacchetto, nessun modello nel venv."""

    name = "ollama"

    def __init__(
        self,
        modello: str = "translategemma:4b",
        host: str = "http://127.0.0.1:11434",
        timeout_s: float = 30.0,
        contesto: int = 0,
        registro: bool = True,
    ) -> None:
        self.modello = modello
        self.host = host.rstrip("/")
        self.timeout_s = timeout_s
        self.contesto = contesto
        self.registro = registro
        self._prima: list[str] = []

    def _genera(self, prompt: str, max_token: int = 256) -> str | None:
        corpo = json.dumps(
            {
                "model": self.modello,
                "prompt": prompt,
                "stream": False,
                # **Temperatura zero.** La stessa battuta riletta due volte
                # dall'OCR deve dare la stessa traduzione: se no il doppiaggio
                # cambia parole da solo, e sembra un difetto del riconoscimento.
                "options": {"temperature": 0.0, "num_predict": max_token},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=corpo,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            dati = json.loads(r.read().decode("utf-8", "replace"))
        return (dati.get("response") or "").strip() or None

    def traduci(self, testo: str, da: str, a: str) -> str | None:
        if "translategemma" in self.modello:
            prompt = prompt_translategemma(testo, da or "en", a or "it", self.registro)
        else:
            # Un modello generico non conosce quel template: gli si parla in
            # chiaro, e lo si dichiara invece di far finta che sia lo stesso.
            prima = "\n".join(self._prima[-self.contesto:]) if self.contesto else ""
            ctx = f"\nBattute precedenti:\n{prima}\n" if prima else ""
            prompt = (
                f"Traduci in {LINGUE.get(a, a)} la battuta di un videogioco.{ctx}\n"
                f"Rispondi SOLO con la traduzione.\nBattuta: {testo}"
            )
        try:
            fuori = self._genera(prompt)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(
                f"Ollama non risponde su {self.host}: {e}. "
                "Avviare `ollama serve`, oppure usare un altro backend."
            ) from e
        if fuori:
            fuori = _ripulisci(fuori)
            self._prima.append(fuori)
        return fuori or None


class CorrettoreOllama:
    """Sceglie fra i candidati usando **lo stesso modello che traduce**.

    Implementa il protocollo di `vision/correct.py`: propone, non decide. Le
    guardie restano tutte a valle — una parola italiana non gli viene nemmeno
    mostrata, i nomi propri nemmeno, e la proposta deve essere una parola del
    lessico.

    **Non genera, sceglie.** Gli si danno le parole italiane vicine e gli si
    chiede quale ci sta: cosi' non puo' inventare una non-parola, e la fiducia
    esce dall'aver scelto dentro l'elenco invece di essere un numero inventato.

    Un modello solo per due lavori vuol dire una sola attesa e una sola memoria
    occupata; con Ollama vuol dire anche che il modello sta **fuori dal venv** e
    si cambia senza reinstallare niente.
    """

    name = "ollama"

    def __init__(
        self,
        modello: str = "translategemma:4b",
        host: str = "http://127.0.0.1:11434",
        lexicon=None,
        timeout_s: float = 10.0,
    ) -> None:
        self._tr = TraduttoreOllama(modello=modello, host=host, timeout_s=timeout_s)
        self.lexicon = lexicon
        self.n_scelte = 0
        self.n_astensioni = 0

    def proponi(self, parola: str, contesto: list[str]):
        from vision.correct import Proposta, candidati

        if self.lexicon is None:
            return None
        opzioni = candidati(parola, self.lexicon)
        if not opzioni:
            return None
        if len(opzioni) == 1:
            # Un candidato solo: non c'e' niente da scegliere e il modello non
            # serve. `oulldozer -> bulldozer` sta qui, e costa zero.
            return Proposta(opzioni[0], 0.95)

        prima = "\n".join(contesto[-10:])
        istruzione = (
            "Un sistema OCR ha letto male una parola nei sottotitoli di un "
            "videogioco.\n"
            + (f"Battute precedenti:\n{prima}\n\n" if prima else "")
            + f"La parola letta male e': {parola}\n"
            f"Le parole italiane possibili sono: {', '.join(opzioni[:12])}\n\n"
            "Rispondi SOLO con la parola corretta scelta da quell'elenco. "
            "Se nessuna e' chiaramente giusta, rispondi NON_SO."
        )
        try:
            r = _ripulisci(self._tr._genera(istruzione, max_token=16) or "")
        except Exception:
            self.n_astensioni += 1
            return None

        scelta = r.strip().strip(".,;:!?'\"").lower()
        if not scelta or scelta.upper().startswith("NON_SO"):
            self.n_astensioni += 1
            return None
        if scelta not in {o.lower() for o in opzioni}:
            # Ha risposto qualcosa che non era fra le opzioni: non si prende. E'
            # il caso in cui un modello "aiuta" inventando, ed e' il difetto che
            # tutta questa impalcatura esiste per impedire.
            self.n_astensioni += 1
            return None
        self.n_scelte += 1
        return Proposta(scelta, 0.95)


def _ripulisci(s: str) -> str:
    s = (s or "").strip()
    for p in ("Translation:", "Traduzione:", "Output:"):
        if s.lower().startswith(p.lower()):
            s = s[len(p):].strip()
    return s.strip().strip('"').strip("'").strip()


def modelli(host: str = "http://127.0.0.1:11434") -> list[str]:
    """I modelli che Ollama ha gia' scaricato. Lista vuota se non risponde."""
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=3.0) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        return []
