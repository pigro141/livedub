"""Un solo modello locale per due lavori: tradurre e ripulire l'OCR.

L'idea non e' mia ed e' quella giusta: se un LLM sta gia' caricato per tradurre,
la correzione degli artefatti dell'OCR e' **una riga in piu' nel prompt**, non un
secondo modello. Un modello solo vuol dire una sola attesa, una sola memoria
occupata e una sola cosa da tarare.

## Il modello, e perche' Gemma 3 1B

`gemma-3-1b-it` in Q4_K_M: ~800 MB su disco, gira su **CPU** in poche centinaia di
millisecondi, e conosce l'italiano. Su CPU e non su GPU di proposito — la GPU qui
serve alla sintesi, e la prova hardware di Qwen ha misurato quanto poco margine
ci sia (0,75x tempo reale a scheda libera, 9,6x a scheda occupata). Un secondo
inquilino li' dentro non ci sta.

Chi ha una macchina grossa puo' passare a un modello piu' grande cambiando
`llm_model`; chi ne ha una piccola resta su Argos o su Google.

## Il contesto: l'idea era buona, la misura dice di no

`vision/correct.py` aveva misurato il problema: `farto` ha **sedici** candidati
italiani veri — `fatto`, `parto`, `farlo`, `furto`, `sarto` — e la sola forma
della parola non puo' sceglierne uno. Le battute precedenti, in teoria, si'.

Provato con il caso nullo che condivide tutto tranne la risposta — stesse frasi,
stesso modello, unica differenza le dieci battute precedenti nel prompt:

    traduzione        senza contesto 254 ms p50    con contesto 457 ms
    "Knock knock!"    senza -> "Chi e'?"           con -> "Knock knock!"
    "Are you kidding me?"                          con -> ripete parola per
                                                          parola la traduzione
                                                          di due battute prima
    correzione        senza 3 giuste su 4          con 2 su 4
    "ciassico"        senza -> "classico"          con -> "biascico"

Su **nove confronti il contesto non ha migliorato nessun caso e ne ha peggiorati
due**, costando il doppio del tempo. Un modello da un miliardo di parametri, con
dieci righe davanti, ricopia invece di ragionare.

Quindi `translate.context_lines` sta a **zero** di default. Il codice per il
contesto resta — con un modello piu' grande la risposta puo' essere un'altra —
ma va rimisurato, non ereditato: e' esattamente il genere di conclusione che si
archivia come vera perche' suonava sensata.

## Cosa NON fa, e non e' una mancanza

**Non decide da solo se correggere.** Restituisce una proposta con una fiducia, e
a decidere e' `Revisore` in `vision/correct.py`, con le sue guardie: una parola
italiana non gli viene nemmeno mostrata, i nomi propri nemmeno, la proposta deve
essere una parola del lessico e vicina. Un LLM sbaglia **meglio** di una distanza
di edit, cioe' in modo piu' plausibile e piu' difficile da notare: le guardie
servono piu' con lui che senza.

**E sceglie fra candidati invece di generare.** Gli si danno le parole italiane
vicine e gli si chiede quale ci sta; cosi' non puo' inventare una non-parola, e
la fiducia esce dal fatto che abbia scelto o meno una delle opzioni offerte.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

MODELLO_DEFAULT = "models/llm/gemma-3-1b-it-Q4_K_M.gguf"
REPO_DEFAULT = ("ggml-org/gemma-3-1b-it-GGUF", "gemma-3-1b-it-Q4_K_M.gguf")


def _scarica(percorso: Path) -> Path:
    from huggingface_hub import hf_hub_download

    repo, file = REPO_DEFAULT
    return Path(hf_hub_download(repo, file, local_dir=str(percorso.parent)))


class MotoreLlm:
    """Il modello caricato una volta, condiviso da traduzione e correzione.

    **Una sola istanza per processo.** Il modello pesa quasi un gigabyte in RAM e
    caricarlo costa: due copie perche' due moduli lo hanno chiesto sarebbero due
    gigabyte e due attese, per lo stesso identico modello. E' lo stesso motivo per
    cui `speak.base.make_tts` e' un posto solo.
    """

    _condiviso: dict[str, "MotoreLlm"] = {}

    def __init__(self, modello: str = "", n_ctx: int = 2048, threads: int = 0) -> None:
        self.percorso = Path(modello or MODELLO_DEFAULT)
        self.n_ctx = n_ctx
        self.threads = threads
        self._llm = None

    @classmethod
    def condiviso(cls, modello: str = "", **kw) -> "MotoreLlm":
        chiave = str(modello or MODELLO_DEFAULT)
        if chiave not in cls._condiviso:
            cls._condiviso[chiave] = cls(modello, **kw)
        return cls._condiviso[chiave]

    def _motore(self):
        if self._llm is not None:
            return self._llm
        try:
            from llama_cpp import Llama
        except ImportError as e:  # pragma: no cover - dipende dall'ambiente
            raise RuntimeError(
                "llama-cpp-python non installato:\n"
                "  .\\.venv\\Scripts\\python.exe -m pip install llama-cpp-python "
                "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu "
                "--only-binary :all:\n"
                "(la ruota gia' compilata: da sorgente il build sbatte sul limite "
                "di lunghezza dei percorsi di Windows)"
            ) from e

        if not self.percorso.exists():
            print(f"llm: scarico {REPO_DEFAULT[1]}...", file=sys.stderr)
            self.percorso.parent.mkdir(parents=True, exist_ok=True)
            self.percorso = _scarica(self.percorso)

        import os

        self._llm = Llama(
            model_path=str(self.percorso),
            n_ctx=self.n_ctx,
            n_threads=self.threads or max(1, (os.cpu_count() or 4) // 2),
            verbose=False,
        )
        return self._llm

    def chiedi(self, istruzione: str, max_token: int = 128, temperatura: float = 0.0) -> str:
        """Una domanda, una risposta. `temperatura` zero: qui non si inventa.

        Il campionamento serve a rendere vario un testo creativo; qui la varieta'
        e' il difetto — la stessa battuta letta due volte deve dare la stessa
        traduzione, se no il doppiaggio cambia parole a ogni rilettura dell'OCR.
        """
        llm = self._motore()
        r = llm.create_chat_completion(
            messages=[{"role": "user", "content": istruzione}],
            max_tokens=max_token,
            temperature=temperatura,
        )
        return (r["choices"][0]["message"]["content"] or "").strip()


class TraduttoreLlm:
    """Traduce con il modello locale, tenendo il contesto delle battute prima."""

    name = "llm"

    def __init__(self, modello: str = "", contesto: int = 0) -> None:
        self.motore = MotoreLlm.condiviso(modello)
        self.contesto = contesto
        self._prima: list[str] = []

    def traduci(self, testo: str, da: str, a: str) -> str | None:
        lingua = {"it": "italiano", "en": "inglese", "es": "spagnolo",
                  "fr": "francese", "de": "tedesco"}.get(a, a)
        prima = "\n".join(self._prima[-self.contesto:])
        contesto = f"\nBattute precedenti (per il contesto):\n{prima}\n" if prima else ""
        istruzione = (
            f"Traduci in {lingua} la battuta di un videogioco.{contesto}\n"
            f"Rispondi SOLO con la traduzione, senza virgolette e senza spiegazioni.\n"
            f"Battuta: {testo}"
        )
        fuori = self.motore.chiedi(istruzione, max_token=160)
        fuori = _ripulisci(fuori)
        if not fuori:
            return None
        self._prima.append(fuori)
        if len(self._prima) > self.contesto * 2:
            del self._prima[: -self.contesto]
        return fuori


class CorrettoreLlm:
    """Sceglie fra i candidati quale parola ci sta, dato il contesto.

    Implementa il protocollo di `vision/correct.py`: **propone**, non decide.
    """

    name = "llm"

    def __init__(self, modello: str = "", lexicon=None, max_ms: float = 400.0) -> None:
        self.motore = MotoreLlm.condiviso(modello)
        self.lexicon = lexicon
        self.max_ms = max_ms
        self.n_scelte = 0
        self.n_astensioni = 0
        self.ms_totali = 0.0

    def proponi(self, parola: str, contesto: list[str]):
        from vision.correct import Proposta, candidati

        if self.lexicon is None:
            return None
        opzioni = candidati(parola, self.lexicon)
        if not opzioni:
            return None
        if len(opzioni) == 1:
            # Un candidato solo: non c'e' niente da scegliere e non serve il
            # modello. `oulldozer -> bulldozer` sta qui, e costa zero.
            return Proposta(opzioni[0], 0.95)

        prima = "\n".join(contesto[-10:])
        elenco = ", ".join(opzioni[:12])
        istruzione = (
            "Un sistema OCR ha letto male una parola nei sottotitoli di un "
            "videogioco.\n"
            + (f"Battute precedenti:\n{prima}\n\n" if prima else "")
            + f"La parola letta male e': {parola}\n"
            f"Le parole italiane possibili sono: {elenco}\n\n"
            "Rispondi SOLO con la parola corretta scelta da quell'elenco. "
            "Se nessuna e' chiaramente giusta, rispondi NON_SO."
        )
        t0 = time.perf_counter()
        r = _ripulisci(self.motore.chiedi(istruzione, max_token=16))
        self.ms_totali += (time.perf_counter() - t0) * 1000.0

        scelta = r.strip().strip(".,;:!?'\"").lower()
        if not scelta or scelta.upper().startswith("NON_SO"):
            self.n_astensioni += 1
            return None
        if scelta not in {o.lower() for o in opzioni}:
            # **Ha risposto qualcosa che non era fra le opzioni.** Non si prende:
            # e' esattamente il caso in cui un modello "aiuta" inventando, ed e'
            # il difetto che tutta questa impalcatura esiste per impedire.
            self.n_astensioni += 1
            return None
        self.n_scelte += 1
        # La fiducia e' alta perche' ha scelto *dentro* l'elenco: la scelta
        # sbagliata resta possibile, ma non puo' essere una non-parola.
        return Proposta(scelta, 0.95)


def _ripulisci(s: str) -> str:
    """Toglie le cortesie che i modelli piccoli aggiungono comunque."""
    s = (s or "").strip()
    for prefisso in ("Traduzione:", "Risposta:", "Output:"):
        if s.lower().startswith(prefisso.lower()):
            s = s[len(prefisso):].strip()
    return s.strip().strip('"').strip("'").strip()
