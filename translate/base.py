"""Tradurre il sottotitolo, se il gioco non e' gia' nella lingua che si vuole.

Finora questa catena non traduceva niente: i sottotitoli di GTA V sono gia' in
italiano e si leggono, si dicono e basta. Tradurre apre il prodotto a tutto il
resto — un gioco inglese doppiato in italiano — e cambia due cose che vanno dette
prima del codice.

## Cosa cambia, e non e' solo "una stringa diversa"

**La lunghezza cambia, quindi cambiano i tempi.** «I've never had a black son» sta
in 26 caratteri, «Non ho mai avuto un figlio nero» in 30: la durata prevista
`D = a + b*n` e il passo `chars_per_second` sono misurati sull'italiano, e vanno
applicati al testo **tradotto**, non all'originale. Tradurre dopo aver deciso i
tempi sarebbe come misurare il silenzio di SuperTonic e chiamarlo parlato.

**E la traduzione sta sulla strada critica.** Il testo serve prima di sintetizzare,
quindi il suo costo si somma a ogni battuta — e con un backend di rete si somma
un viaggio in rete. Da qui la cache (lo stesso sottotitolo torna) e il tetto di
tempo: **scaduto il tempo si tiene l'originale**, perche' una battuta detta nella
lingua sbagliata e' un difetto, una battuta non detta e' un buco.

## Le due strade, e la differenza non e' tecnica

- **`locale`**: nessun dato esce dalla macchina. E' coerente con quello che questo
  progetto dichiara di essere — tutto in locale, nessun servizio — ed e' il
  default quando la traduzione si accende.
- **`google`**: piu' comodo e spesso migliore, ma **manda ogni sottotitolo a
  Google**. Non e' un dettaglio di licenza: e' il contrario di «uso completamente
  locale ed estrema privacy», che sta nella lista degli obiettivi di questo stesso
  progetto. Quindi si puo' scegliere, ma la scelta e' esplicita, il default e' no,
  e il modulo lo dichiara a voce quando parte.

## Fallire non e' tradurre a caso

Un traduttore che non sa restituisce `None`, e chi chiama tiene l'originale. Non
esiste il ripiego silenzioso su una traduzione parziale o su un'altra lingua: e'
la stessa regola di `make_tts`, dove un nome sconosciuto solleva invece di
consegnare un doppiaggio plausibile fatto dal motore sbagliato.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Traduzione:
    """Il testo tradotto, con da dove viene."""

    testo: str
    originale: str
    backend: str = "?"
    da_cache: bool = False
    ms: float = 0.0

    @property
    def tradotto(self) -> bool:
        return self.testo != self.originale


class Traduttore(Protocol):
    """Chi traduce. `None` vuol dire "non ci sono riuscito", ed e' legittimo."""

    name: str

    def traduci(self, testo: str, da: str, a: str) -> str | None:
        ...


class NessunTraduttore:
    """Non traduce. E' il default, ed e' il comportamento di sempre."""

    name = "nessuno"

    def traduci(self, testo: str, da: str, a: str) -> str | None:
        return None


class TraduttoreProva:
    """Traduttore finto: rimanda il testo in maiuscolo. **Solo per il banco.**

    Serve a provare tutto cio' che sta *intorno* alla traduzione — il riquadro
    che copre l'originale, la sfocatura, i tempi ricalcolati sulla lunghezza
    nuova — senza mandare niente in rete e senza scaricare un modello. E' lo
    stesso ruolo di `ToneTts` per la sintesi: se qualcosa non torna con questo,
    il colpevole non e' il traduttore.

    Il maiuscolo non e' un vezzo: rende **visibile a colpo d'occhio** se a
    schermo si sta leggendo il testo sostituito o quello originale rimasto
    scoperto, che e' precisamente la domanda a cui l'MP4 deve rispondere.
    """

    name = "prova"

    def traduci(self, testo: str, da: str, a: str) -> str | None:
        return testo.upper()


@dataclass
class Traduzioni:
    """Il traduttore con la cache e il tetto di tempo addosso.

    **La cache non e' un'ottimizzazione, e' quello che rende l'idea praticabile.**
    Un sottotitolo che resta a schermo viene riletto a ogni frame, e la catena a
    monte lo deduplica ma non sempre in modo identico: la stessa frase torna. Con
    la cache il costo si paga una volta per battuta e non una volta per lettura.
    """

    traduttore: Traduttore
    da: str = "auto"
    a: str = "it"
    max_ms: float = 400.0
    _cache: dict[str, str] = field(default_factory=dict)
    n_ok: int = 0
    n_falliti: int = 0
    n_cache: int = 0
    n_lenti: int = 0

    def __call__(self, testo: str) -> Traduzione:
        t = (testo or "").strip()
        if not t or isinstance(self.traduttore, NessunTraduttore):
            return Traduzione(testo=testo, originale=testo, backend=self.traduttore.name)

        pronta = self._cache.get(t)
        if pronta is not None:
            self.n_cache += 1
            return Traduzione(pronta, testo, self.traduttore.name, da_cache=True)

        t0 = time.perf_counter()
        try:
            fuori = self.traduttore.traduci(t, self.da, self.a)
        except Exception as e:  # pragma: no cover - dipende dalla rete/modello
            print(f"traduzione: {e!r}", file=sys.stderr)
            fuori = None
        ms = (time.perf_counter() - t0) * 1000.0

        if not fuori:
            # **Si tiene l'originale.** Una battuta nella lingua sbagliata e' un
            # difetto; una battuta muta e' un buco, e questo progetto sfora, non
            # scarta.
            self.n_falliti += 1
            return Traduzione(testo, testo, self.traduttore.name, ms=ms)

        if ms > self.max_ms:
            # Riuscita ma tardi: si usa lo stesso (buttarla via sarebbe sprecare
            # il costo appena pagato) e si **conta**, perche' se succede spesso il
            # backend non e' adatto alla strada critica.
            self.n_lenti += 1
        self._cache[t] = fuori
        self.n_ok += 1
        return Traduzione(fuori, testo, self.traduttore.name, ms=ms)


def make_traduttore(cfg):
    """Il traduttore richiesto. Un nome sconosciuto **solleva**.

    E `google` lo dichiara: da quel momento ogni sottotitolo esce dalla macchina,
    e chi accende quella riga deve saperlo dal registro e non dalla
    documentazione.
    """
    if not cfg.enabled:
        return NessunTraduttore()
    nome = (cfg.backend or "").lower()
    if nome in ("nessuno", "none", ""):
        return NessunTraduttore()
    if nome == "prova":
        return TraduttoreProva()
    if nome in ("locale", "local", "argos"):
        from translate.locale import TraduttoreLocale

        return TraduttoreLocale(modello=cfg.local_model)
    if nome == "llm":
        from translate.llm import TraduttoreLlm

        return TraduttoreLlm(modello=cfg.llm_model, contesto=cfg.context_lines)
    if nome == "ollama":
        from translate.ollama import TraduttoreOllama

        return TraduttoreOllama(
            modello=cfg.ollama_model,
            host=cfg.ollama_host,
            timeout_s=max(1.0, cfg.timeout_ms / 1000.0 * 20),
            contesto=cfg.context_lines,
            registro=cfg.preserve_register,
        )
    if nome == "google":
        from translate.google import TraduttoreGoogle

        print(
            "traduzione: backend `google` acceso — **ogni sottotitolo viene "
            "inviato ai server di Google**. Per restare in locale: "
            "`--set translate.backend=locale`.",
            file=sys.stderr,
        )
        return TraduttoreGoogle(timeout_s=max(0.2, cfg.net_timeout_ms / 1000.0))
    raise ValueError(
        f"traduttore sconosciuto: {cfg.backend!r} (noti: locale, google, nessuno)"
    )
