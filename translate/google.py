"""Traduzione via Google. **I sottotitoli escono dalla macchina.**

Non serve una chiave ne' un pacchetto: si parla con l'endpoint pubblico che usa
l'estensione del browser, con la sola libreria standard. Comodo, spesso migliore
del locale, e in contrasto diretto con quello che questo progetto dichiara di
essere — quindi spento di default e annunciato quando si accende.

**Il tetto di tempo e' la parte seria.** Questa chiamata sta sulla strada critica
del doppiaggio: la battuta non si puo' sintetizzare finche' non c'e' il testo. Un
timeout di rete senza tetto vorrebbe dire una battuta che aspetta trenta secondi,
cioe' un buco nel doppiaggio causato dalla rete di qualcun altro. Scaduto il
tempo si torna `None` e chi chiama tiene l'originale.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

ENDPOINT = "https://translate.googleapis.com/translate_a/single"


class TraduttoreGoogle:
    """Traduce con l'endpoint pubblico di Google Translate."""

    name = "google"

    def __init__(self, timeout_s: float = 0.4) -> None:
        self.timeout_s = timeout_s

    def traduci(self, testo: str, da: str, a: str) -> str | None:
        params = urllib.parse.urlencode(
            {
                "client": "gtx",
                "sl": da or "auto",
                "tl": a or "it",
                "dt": "t",
                "q": testo,
            }
        )
        req = urllib.request.Request(
            f"{ENDPOINT}?{params}",
            headers={"User-Agent": "Mozilla/5.0 (livedub)"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            dati = json.loads(r.read().decode("utf-8", "replace"))

        # La risposta e' una lista di liste: il primo elemento raccoglie i pezzi
        # tradotti. Si ricuce senza fidarsi della forma, perche' e' un endpoint
        # non documentato e cambiare forma e' il suo diritto.
        try:
            pezzi = [p[0] for p in dati[0] if isinstance(p, list) and p and p[0]]
        except (IndexError, TypeError):
            return None
        fuori = "".join(pezzi).strip()
        return fuori or None
