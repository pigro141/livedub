"""Quello che la finestra deve ricordarsi fra un avvio e l'altro.

**Perche' esiste.** Chiudendo la finestra si perdeva ogni regolazione: un'ora di
lavoro sulle soglie buttata, e la volta dopo si ricominciava dai default. Era il
difetto piu' grave dell'elenco in `DOMANDE_PRODUZIONE.md`, e non e' un dettaglio
di comodita' — un programma che dimentica insegna all'utente a non toccare
niente.

**Due cose separate, di proposito.**

- **Le preferenze della finestra** (dov'era, quanto era grande, che scheda era
  aperta) stanno qui, in `%LOCALAPPDATA%`, perche' sono della *macchina* e non
  del progetto: copiando la cartella su un altro PC non ha senso portarsi dietro
  la posizione di una finestra su uno schermo che non c'e'.
- **La configurazione** invece resta un profilo in `profiles/`, con il formato
  che aveva gia': un file che si legge, si diffa e si manda a qualcuno. Salvare
  166 campi dentro un file di preferenze opaco vorrebbe dire perdere l'unica
  cosa che rende riproducibile una prova.

**E l'ultima configurazione usata si ricorda comunque**, come profilo
`profiles/ultima.json`: non e' la stessa cosa di un salvataggio con un nome,
serve solo a non perdere quello che si stava facendo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def cartella() -> Path:
    """Dove Windows vuole che stiano i dati di un programma per utente."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "livedub"


def _file() -> Path:
    return cartella() / "preferenze.json"


def leggi() -> dict[str, Any]:
    """Le preferenze salvate, o un dizionario vuoto.

    **Un file rotto non deve impedire al programma di partire.** Se qualcuno lo
    apre e ci scrive dentro, o se un crash lo lascia a meta', la finestra deve
    aprirsi lo stesso con i valori di serie: perdere la posizione di una finestra
    e' un fastidio, non partire e' un guasto.
    """
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def scrivi(dati: dict[str, Any]) -> None:
    """Salva, e se non ci riesce **non solleva**: e' in chiusura."""
    try:
        f = _file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(dati, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def aggiorna(**valori: Any) -> dict[str, Any]:
    """Cambia alcune chiavi lasciando le altre."""
    dati = leggi()
    dati.update(valori)
    scrivi(dati)
    return dati
