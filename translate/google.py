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

## La connessione si tiene aperta, e vale piu' di qualunque altra ottimizzazione

La prima versione apriva una connessione nuova a ogni battuta, e il banco
misurava **1002 ms** di mediana: abbastanza da far scartare questo backend come
"troppo lento per la strada critica". Ma quel numero non era di Google, era della
preparazione — DNS, TCP e stretta di mano TLS, rifatti ogni volta.

Separando le due cose:

    connessione nuova ogni volta   p50  337 ms   (fra 107 e 1095, instabile)
    una connessione tenuta aperta  p50   64 ms   (fra 42 e 91, stabile)
    apertura + TLS                       94 ms   una volta sola

**Google risponde in 64 ms.** Il resto era mio, e sarebbe stato archiviato come
una proprieta' del servizio. Da qui la connessione persistente — con la riapertura
al primo errore, perche' il server la chiude quando vuole e una connessione morta
non deve diventare una battuta persa.

## Ma quei 64 ms sono con la rete ferma, e il caso d'uso non lo e'

Misurati a riposo. Nel caso d'uso vero il gioco o il video sono in riproduzione
e si prendono la banda: con un video YouTube in corso la stessa chiamata impiega
**300-550 ms**. Con il tetto tarato sui 64 ms — 400 di margine, che sembravano
larghi — **una battuta su tre restava in italiano**: la traduzione riusciva,
arrivava tardi e veniva buttata via dal timeout del socket, e la catena teneva
l'originale senza dire niente.

E' la stessa forma di errore che questo progetto ha gia' pagato tre volte: una
soglia misurata su una distribuzione e applicata a un'altra. Il tetto di rete e'
adesso un numero suo (`translate.net_timeout_ms`), separato dalla soglia che
dice soltanto «questa e' stata lenta».
"""

from __future__ import annotations

import http.client
import json
import threading
import urllib.parse

HOST = "translate.googleapis.com"
PERCORSO = "/translate_a/single"


class TraduttoreGoogle:
    """Traduce con l'endpoint pubblico di Google Translate."""

    name = "google"

    def __init__(self, timeout_s: float = 2.0) -> None:
        self.timeout_s = timeout_s
        self._conn: http.client.HTTPSConnection | None = None
        # La traduzione avviene nel thread video, ma il lucchetto costa nulla e
        # toglie di mezzo la domanda: una connessione HTTP condivisa fra due
        # thread e' un difetto che si manifesta una volta ogni mille battute.
        self._lock = threading.Lock()

    def _richiedi(self, query: str) -> bytes:
        """Una richiesta sulla connessione aperta, riaprendola se e' morta."""
        for tentativo in (1, 2):
            try:
                if self._conn is None:
                    # **Aprire costa piu' che chiedere, quindi ha un tetto suo.**
                    # Misurato: la stretta di mano vale ~94 ms a caldo ma la
                    # primissima, con il DNS ancora da risolvere, e' arrivata a
                    # 1304 ms: piu' del tetto della richiesta, quindi la **prima
                    # battuta di ogni sessione** sarebbe fallita e sarebbe uscita
                    # nella lingua originale senza che nessuno capisse perche'.
                    self._conn = http.client.HTTPSConnection(
                        HOST, timeout=max(self.timeout_s, 5.0)
                    )
                    self._conn.connect()
                    if self._conn.sock is not None:
                        self._conn.sock.settimeout(self.timeout_s)
                self._conn.request(
                    "GET",
                    f"{PERCORSO}?{query}",
                    headers={
                        "User-Agent": "Mozilla/5.0 (livedub)",
                        "Connection": "keep-alive",
                    },
                )
                return self._conn.getresponse().read()
            except (http.client.HTTPException, OSError):
                # Connessione chiusa dall'altra parte, o rete andata via: si
                # butta e si riprova **una** volta. Al secondo fallimento e' un
                # problema vero e chi chiama tiene l'originale.
                try:
                    if self._conn is not None:
                        self._conn.close()
                finally:
                    self._conn = None
                if tentativo == 2:
                    raise
        return b""

    def traduci(self, testo: str, da: str, a: str) -> str | None:
        query = urllib.parse.urlencode(
            {
                "client": "gtx",
                "sl": da or "auto",
                "tl": a or "it",
                "dt": "t",
                "q": testo,
            }
        )
        with self._lock:
            grezzo = self._richiedi(query)
        dati = json.loads(grezzo.decode("utf-8", "replace"))

        # La risposta e' una lista di liste: il primo elemento raccoglie i pezzi
        # tradotti. Si ricuce senza fidarsi della forma, perche' e' un endpoint
        # non documentato e cambiare forma e' il suo diritto.
        try:
            pezzi = [p[0] for p in dati[0] if isinstance(p, list) and p and p[0]]
        except (IndexError, TypeError):
            return None
        fuori = "".join(pezzi).strip()
        return fuori or None
