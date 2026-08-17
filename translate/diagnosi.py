"""Quali traduttori funzionano **su questa macchina**, e quanto costano.

Cinque opzioni in un menu a tendina sembrano cinque opzioni. Misurate qui il 16
agosto 2026, **dopo** aver installato Argos di serie
(`tools/installa_traduzione.ps1`):

| backend | qui | p50 a caldo | i sottotitoli escono dal PC? |
|---|---|---|---|
| `nessuno` | — | — | no |
| `locale` (Argos) | **funziona** | **38 ms** | no |
| `llm` (Gemma in-process) | funziona | 444 ms | no |
| `ollama` | server spento | — | no |
| `google` | funziona | 781 ms | **si'** |

Il default di `core/config.py` e' `locale`, ed e' il piu' veloce dei tre di un
ordine di grandezza — dieci volte meno di `llm`, venti di Google. La mattina
prima non traduceva affatto: mancava il pacchetto, e non traducendo si teneva
l'originale **in silenzio**, cioe' un default che non funzionava.

Tre misure che questo file ha gia' evitato di archiviare sbagliate.

**Il caricamento del modello non e' il costo di una battuta.** La prima chiamata
a `llm` costa 3273 ms e la seconda 359; ad Argos, 3950 contro 24. Preso per buono
il primo numero, si sarebbe escluso il traduttore migliore. Per questo la prova
fa due giri e riporta il secondo — e per questo `TraduttoreLocale.scalda()` paga
quel caricamento ad Avvia invece che sulla prima riga del gioco.

**E il secondo giro deve dire una frase diversa.** Ripetendo la stessa,
argostranslate rispondeva dalla sua cache: **0 ms**, che non e' una velocita' di
traduzione di nessuno. Un numero fuori scala si insegue anche quando e' bello.
Nello stesso giro Google dava 67 ms, che era il suo keep-alive: 781 e' il numero
vero.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

# La frase di prova non e' «hello»: e' una battuta di gioco, con il registro che
# questo progetto ha gia' misurato essere il primo a essere riscritto.
FRASE = "Voglio vedere i soldi, adesso."

# **La seconda frase non e' un di piu': e' cio' che rende la misura una misura.**
# Il primo giro serve a pagare il caricamento del modello, e ripetere *la stessa*
# frase misurerebbe una cache — argostranslate ne tiene una sua, e il risultato
# era `0 ms`, cioe' un numero che nessun traduttore puo' fare. Un numero fuori
# scala si insegue anche quando e' bello.
FRASE_2 = "Esci dalla mia macchina, e non tornare."

BACKEND = ("nessuno", "locale", "llm", "ollama", "google")

# Cosa comporta ciascuno, detto prima di provarlo: la prova dice **se** va, non
# **cosa costa** sceglierlo.
FUORI_DAL_PC = ("google",)


@dataclass(frozen=True)
class Esito:
    backend: str
    ok: bool
    ms: float
    testo: str      # cosa ha prodotto, se ha prodotto
    motivo: str     # perche' no, se no

    @property
    def riservato(self) -> bool:
        return self.backend not in FUORI_DAL_PC


def prova(nome: str, cfg, frase: str = FRASE, da: str = "it", a: str = "en") -> Esito:
    """Prova un backend **due volte** e riporta il secondo giro.

    Il primo giro paga il caricamento del modello, che si paga una volta per
    sessione e non una volta per battuta: riportarlo vorrebbe dire scartare un
    traduttore vivibile perche' ci mette tre secondi ad accendersi.
    """
    if nome in ("nessuno", "none", ""):
        return Esito(nome, True, 0.0, "", "non traduce, per scelta")
    try:
        from translate.base import make_traduttore

        tr = make_traduttore(replace(cfg, enabled=True, backend=nome))
        tr.traduci(frase, da, a)  # a freddo: si butta
        t0 = time.perf_counter()
        fuori = tr.traduci(FRASE_2 if frase == FRASE else frase, da, a)
        ms = (time.perf_counter() - t0) * 1000.0
        # Si mostra la traduzione della **prima** frase, che e' quella dichiarata
        # nella tabella; il tempo e' della seconda, che e' quella non in cache.
        fuori = tr.traduci(frase, da, a) or fuori
    except Exception as e:
        return Esito(nome, False, 0.0, "", str(e).splitlines()[0])
    if not fuori:
        return Esito(nome, False, ms, "", "ha risposto vuoto")
    return Esito(nome, True, ms, str(fuori), "")


def tutti(cfg, frase: str = FRASE, da: str = "it", a: str = "en") -> list[Esito]:
    return [prova(n, cfg, frase, da, a) for n in BACKEND]


def riga(e: Esito) -> str:
    """Una riga leggibile, per il registro e per la finestra."""
    if not e.ok:
        return f"{e.backend:9s} non funziona qui — {e.motivo}"
    if not e.testo:
        return f"{e.backend:9s} {e.motivo}"
    dove = "" if e.riservato else "   ⚠ i sottotitoli escono dal PC"
    return f"{e.backend:9s} {e.ms:5.0f} ms   «{e.testo}»{dove}"
