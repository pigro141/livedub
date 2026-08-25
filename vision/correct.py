"""Correggere gli artefatti dell'OCR, se e solo se si sa di poterlo fare.

`vision/lexicon.py` ha gia' bocciato la correzione automatica, e con una misura:
la distanza di edit ha dato **due risposte giuste su otto**, e le sei sbagliate
erano dei due tipi peggiori — `'rapinato'` -> `'rovinato'` (una parola vera al
posto di un'altra parola vera) e `'IIFIL'` -> `'infila'` (spazzatura promossa a
italiano credibile). Oggi, quando l'OCR sbaglia, **si sente**; con la correzione
si sentirebbe una frase pulita che dice un'altra cosa.

Questo modulo non contraddice quella conclusione: la prende come specifica. Un
correttore qui dentro puo' agire solo dove il rischio e' basso, e quando non lo e'
**dichiara di non sapere** invece di provarci.

## Cosa c'e' davvero da correggere, misurato

Su 4280 battute archiviate in `runs/`, 19146 parole di almeno tre lettere:

    fuori dal lessico                              1230   6,4%
      maiuscole a meta' frase (nomi propri)         527   2,75%
      minuscole (i candidati)                       703   3,67%

E dentro le 703 minuscole, la maggioranza **non e' un errore**: `toc` da solo vale
118 occorrenze, poi altri nomi propri (`magellan`, `michael`, `trevor`, `lester`),
forme italiane vere che il dizionario non elenca (`trascinarti`, `sposartelo`,
`ammazzarti`, `cambierò` — le stesse che il docstring del lessico gia' citava), e
frammenti di HUD (`scorriqeaccount`, `menutab`, `sxscorri`), che non sono un
problema di lingua ma di ritaglio.

Gli errori veri — `farto`, `oulldozer`, `andiamu`, `fratelio`, `ciassico`,
`simeot` — sono circa **l'1-1,5% delle parole**, cioe' una parola ogni settanta.

**Da qui due conseguenze che vengono prima di qualunque modello.** La prima e' che
l'insieme su cui un correttore lavora e' fatto in maggioranza di cose **da non
toccare**: chiedere a un LLM di «sistemare le parole non italiane» significa
consegnargli i nomi dei personaggi, ed e' il difetto `rapinato -> rovinato` in un
costume peggiore, perche' un personaggio rinominato rompe anche l'assegnazione
della voce. La seconda e' che il guadagno massimo possibile e' piccolo, quindi non
vale nessun rischio: **un correttore che sbaglia una volta su dieci fa piu' danno
di quanto ripari.**

## Le guardie, in ordine di importanza

1. **Le parole che il lessico conosce non si toccano mai.** Uccide il caso
   `rapinato -> rovinato` alla radice: `rapinato` e' italiano, quindi e' fuori
   discussione per costruzione, non per bravura del modello.
2. **I nomi propri non si toccano mai.** Maiuscola a meta' frase, oppure presenza
   nell'elenco dichiarato in `label.names` — che l'utente ha gia' compilato se usa
   il nome del parlante, e qui torna utile gratis.
3. **La proposta deve essere una parola italiana** e stare vicina all'originale
   (distanza di edit limitata, e proporzionale alla lunghezza).
4. **Sotto la fiducia dichiarata non si corregge.** E' la condizione che il
   docstring del lessico poneva — «ha senso solo se dichiara quando non e'
   sicuro» — ed e' l'unica che rende la cosa diversa da quella gia' bocciata.

## Il contesto, che e' l'idea nuova

Un correttore per distanza di edit non sa niente della frase: `farto` e' vicino a
`fatto`, `farfo`, `parto`, `tarto` e sceglie a caso fra quelle vere. Con le
battute precedenti — di chi si sta parlando, di che cosa — la scelta smette di
essere cieca. E' il motivo per cui vale la pena riprovare, e `Correttore.proponi`
riceve il **contesto** apposta.

Ma il contesto non e' una licenza: un modello con contesto sbaglia **meglio**, cioe'
in modo piu' plausibile e piu' difficile da notare. Per questo la fiducia
dichiarata non e' un di piu' ed e' obbligatoria nell'interfaccia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

_SEGNI = ".,;:!?'\"()[]-–—…«»‘’“”%€$"

# Parole che l'OCR legge bene, che il lessico non ha, e che non sono errori.
# Tenerle qui costa nulla e toglie rumore a monte di qualunque correttore.
SEMPRE_BUONE = frozenset(
    {"toc", "hmm", "mmh", "ehi", "eh", "ah", "oh", "beh", "boh", "ok", "okay"}
)


@dataclass(frozen=True, slots=True)
class Proposta:
    """Una parola da sostituire, con quanta fiducia."""

    parola: str
    fiducia: float  # 0..1


@dataclass
class Correzione:
    """Il risultato: il testo, e cosa e' stato toccato."""

    testo: str
    cambi: list[tuple[str, str]] = field(default_factory=list)
    # Parole che erano candidate e che si e' scelto di **non** toccare. Non e'
    # una curiosita': e' la misura di quanto spesso il correttore si astiene, che
    # e' la sola cosa che distingue questo da quello gia' bocciato.
    astenuto: list[str] = field(default_factory=list)

    @property
    def cambiato(self) -> bool:
        return bool(self.cambi)


class Correttore(Protocol):
    """Chi propone una sostituzione, o dice di non sapere.

    `contesto` sono le ultime battute gia' dette, dalla piu' vecchia alla piu'
    recente. Restituire `None` e' una risposta legittima e dev'essere quella di
    default: chi non sa, tace.
    """

    name: str

    def proponi(self, parola: str, contesto: list[str]) -> Proposta | None:
        ...


class NessunCorrettore:
    """Non corregge niente. E' il default, e resta il comportamento di sempre."""

    name = "nessuno"

    def proponi(self, parola: str, contesto: list[str]) -> Proposta | None:
        return None


def distanza(a: str, b: str, tetto: int = 3) -> int:
    """Distanza di Levenshtein, che si ferma appena supera `tetto`."""
    a, b = a.lower(), b.lower()
    if abs(len(a) - len(b)) > tetto:
        return tetto + 1
    prec = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prec[j] + 1, cur[j - 1] + 1, prec[j - 1] + (ca != cb)))
        if min(cur) > tetto:
            return tetto + 1
        prec = cur
    return prec[-1]


class Revisore:
    """Applica un correttore al testo, con tutte le guardie addosso.

    Il correttore propone; **questa classe decide**, ed e' qui che stanno le
    regole che rendono la cosa accettabile. Un correttore nuovo non puo'
    indebolirle: puo' solo proporre meglio.
    """

    def __init__(
        self,
        lexicon,
        correttore: Correttore | None = None,
        *,
        min_fiducia: float = 0.9,
        max_distanza: int = 2,
        contesto_battute: int = 10,
        nomi: tuple[str, ...] = (),
    ) -> None:
        self.lex = lexicon
        self.correttore = correttore or NessunCorrettore()
        self.min_fiducia = min_fiducia
        self.max_distanza = max_distanza
        self.contesto_battute = contesto_battute
        self.nomi = {n.strip().lower() for n in nomi}
        self._contesto: list[str] = []

    # -- chi non si tocca --------------------------------------------------

    def intoccabile(self, parola: str, primo: bool) -> bool:
        """La parola e' fuori discussione, senza nemmeno chiedere al correttore.

        `primo` dice se sta a inizio frase, dove la maiuscola non significa nome
        proprio ma solo inizio.
        """
        pulita = parola.strip(_SEGNI)
        if len(pulita) < 3 or not pulita.isalpha():
            return True
        basso = pulita.lower()
        if basso in SEMPRE_BUONE or basso in self.nomi:
            return True
        if self.lex.nota(pulita):
            return True  # e' italiano: non si tocca, e questa e' la regola 1
        if pulita[0].isupper() and not primo:
            return True  # maiuscola a meta' frase: nome proprio
        return False

    # -- la revisione ------------------------------------------------------

    def rivedi(self, testo: str) -> Correzione:
        """Il testo con le sole sostituzioni che superano tutte le guardie."""
        parole = testo.split()
        fuori = []
        cambi: list[tuple[str, str]] = []
        astenuto: list[str] = []

        for i, w in enumerate(parole):
            primo = i == 0 or parole[i - 1].endswith((".", "!", "?"))
            if self.intoccabile(w, primo):
                fuori.append(w)
                continue

            pulita = w.strip(_SEGNI)
            p = self.correttore.proponi(pulita, list(self._contesto))
            if p is None or p.fiducia < self.min_fiducia:
                astenuto.append(pulita)
                fuori.append(w)
                continue
            if not self.lex.nota(p.parola):
                # Regola 3: non si sostituisce con una non-parola. Senza,
                # `'IIFIL' -> 'infila'` diventa `'IIFIL' -> qualunque cosa`.
                astenuto.append(pulita)
                fuori.append(w)
                continue
            limite = min(self.max_distanza, max(1, len(pulita) // 3))
            if distanza(pulita, p.parola, limite) > limite:
                astenuto.append(pulita)
                fuori.append(w)
                continue

            fuori.append(w.replace(pulita, p.parola, 1))
            cambi.append((pulita, p.parola))

        nuovo = " ".join(fuori)
        self.ricorda(nuovo)
        return Correzione(testo=nuovo, cambi=cambi, astenuto=astenuto)

    def ricorda(self, testo: str) -> None:
        """Aggiunge una battuta al contesto, tenendone le ultime `n`."""
        t = testo.strip()
        if not t:
            return
        self._contesto.append(t)
        if len(self._contesto) > self.contesto_battute:
            del self._contesto[: -self.contesto_battute]


def candidati(parola: str, lexicon, max_distanza: int = 2, tetto: int = 30) -> list[str]:
    """Le parole italiane abbastanza vicine. **Il correttore sceglie fra queste.**

    E' la differenza fra generare e scegliere, e non e' un dettaglio di
    implementazione: un modello che *genera* la parola giusta puo' produrre
    qualunque stringa, e la regola «la proposta dev'essere una parola italiana»
    diventa un filtro applicato dopo, che scarta e basta. Un modello che *sceglie*
    fra questi candidati non puo' sbagliare in quel modo — al massimo sceglie il
    candidato sbagliato, che e' un errore molto piu' piccolo e molto piu' visibile.

    E da qui esce anche la fiducia, gratis e ben definita: **quanto il primo
    candidato stacca il secondo**. Un correttore che deve inventarsi un numero di
    fiducia se lo inventa; uno che sceglie fra alternative ce l'ha per costruzione.
    """
    p = parola.strip(_SEGNI).lower()
    if not p:
        return []
    limite = min(max_distanza, max(1, len(p) // 3))
    # **Si scandisce tutto il lessico, senza fermarsi ai primi trovati.** La prima
    # versione usciva dopo N candidati: siccome un `set` non ha ordine, l'insieme
    # dipendeva da come Python aveva disposto le parole in memoria — e infatti per
    # `farto` la risposta giusta (`fatto`, distanza 1) restava fuori, tagliata
    # prima di essere vista. Un candidato mancante non da' errore: da' una
    # correzione plausibile e sbagliata, oppure nessuna, e in tutti e due i casi
    # nessuno se ne accorge. Trecentomila confronti con il filtro sulla lunghezza
    # costano pochi millisecondi, che e' meno di quanto costa sbagliare.
    fuori = []
    for w in getattr(lexicon, "parole", ()):
        if abs(len(w) - len(p)) > limite:
            continue
        d = distanza(p, w, limite)
        if d <= limite:
            fuori.append((d, w))
    fuori.sort()
    # **A parita' di distanza l'ordine e' alfabetico, cioe' arbitrario**, e il
    # tetto va tenuto largo per questo. Con dodici candidati, `farto` non arrivava
    # a `fatto`: le parole a distanza 1 sono una ventina e `fatto` cadeva
    # tredicesima per pura fortuna alfabetica. Ordinare cosi' non e' un difetto da
    # sistemare qui — **e' precisamente il buco che il contesto deve riempire**, ed
    # e' l'argomento per cui un correttore con le battute precedenti puo' fare
    # meglio di uno che guarda solo la forma della parola.
    return [w for _, w in fuori[:tetto]]


def make_correttore(cfg, traduzione=None):
    """Il correttore richiesto. Un nome sconosciuto **solleva**.

    Come `make_tts` e `make_ocr`: ripiegare in silenzio su "nessuno" vorrebbe dire
    misurare una correzione che non e' mai avvenuta, che in questo progetto e' gia'
    costato due letture pulite e false.
    """
    nome = (cfg.backend or "nessuno").lower()
    if nome in ("", "nessuno", "none"):
        return NessunCorrettore()
    if nome == "llm":
        # **Il peggiore dei tre, misurato.** Su otto casi veri: una giusta, con
        # gli errori peggiori possibili — `oulldozer -> bulldozers`,
        # `ciassico -> biascico`, `uice -> ice` dove doveva astenersi. Chi vuole
        # correggere usi `ollama`.
        # E si guarda **adesso** se quella libreria si carica: `CorrettoreLlm`
        # la apre pigramente, quindi senza questa riga la rinuncia uscirebbe
        # sulla prima parola da correggere invece che all'Avvia.
        from core import bloccati

        esito = bloccati.pezzo("llm")
        if not esito.ok:
            raise bloccati.Rinuncia(
                esito, "il correttore dell'OCR",
                "usa «ollama», che su otto casi veri ne prende cinque contro uno")
        from translate.llm import CorrettoreLlm
        from vision.lexicon import carica

        # **Lo stesso modello che traduce.** `MotoreLlm.condiviso` restituisce
        # l'istanza gia' caricata: un gigabyte in RAM e un'attesa di caricamento
        # valgono per tutti e due i lavori, non uno ciascuno.
        return CorrettoreLlm(
            modello=cfg.llm_model, lexicon=carica(), max_ms=cfg.llm_max_ms
        )
    if nome == "ollama":
        # **Il migliore dei tre, e non di poco.** Su otto casi veri presi dalle
        # sessioni archiviate:
        #
        #     translategemma:4b     5/8   p50 1784 ms
        #     translategemma:12b    5/8   p50 2451 ms
        #     gemma-3-1b            1/8   p50 1892 ms
        #
        # Il 12b non aggiunge niente e costa il 40% in piu': si resta sul 4b.
        #
        # **Ma 1784 ms per parola restano tanti**, e la correzione sta sul thread
        # video dove il costo si amplifica. Quindi: buono per il banco
        # (`tools/dub.py`), da lasciare spento dal vivo — che e' anche il motivo
        # per cui questa sezione ha `nessuno` come default.
        #
        # **Lo stesso modello che traduce**, come chiesto: se una sessione
        # traduce e corregge, Ollama ne tiene caricato uno solo. I default
        # ricadono sulla sezione `translate` proprio per non poterli disallineare
        # — due sorgenti per lo stesso numero sono la garanzia che prima o poi
        # divergano, e a divergere e' sempre quella che nessuno legge.
        from translate.ollama import CorrettoreOllama
        from vision.lexicon import carica

        modello = cfg.ollama_model or getattr(traduzione, "ollama_model", "translategemma:4b")
        host = cfg.ollama_host or getattr(
            traduzione, "ollama_host", "http://127.0.0.1:11434"
        )
        return CorrettoreOllama(
            modello=modello, host=host, lexicon=carica(),
            timeout_s=max(1.0, cfg.llm_max_ms / 1000.0 * 20),
        )
    raise ValueError(
        f"correttore sconosciuto: {cfg.backend!r} (noti: nessuno, llm, ollama)"
    )
