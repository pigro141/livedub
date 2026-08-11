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


# ------------------------------------------------- l'ultima configurazione --


def ultima() -> Path:
    """Il profilo in cui finisce la configurazione all'uscita."""
    from core.config import PROFILES_DIR

    return PROFILES_DIR / "ultima.json"


def riprendi(profilo: str | None = None, overrides: Any = None):
    """Con che configurazione si riapre il programma, e **da dove viene**.

    **`ultima.json` veniva scritto all'uscita e non lo rileggeva nessuno.** Era
    la cura scritta per le domande 15 e 16 — «le impostazioni si perdono
    chiudendo», il difetto piu' grave di quell'elenco — e aveva la forma esatta
    di quello che questo progetto ha gia' pagato cinque volte: un valore
    prodotto, salvato e mai letto (`max_ocr_hz`, `tts.device`,
    `background_mode`, `overlay.ritardo`, `ui.save_mix`). L'utente regolava per
    un'ora, chiudeva, riapriva e ritrovava i default — con il file pieno dei
    valori giusti sul disco, li' accanto.

    L'ordine e' quello che l'utente si aspetta: **un profilo chiesto vince
    sempre** (chi scrive `--profile gtav` vuole gtav, non la sessione di ieri) e
    `--set` sta sopra tutti e due. Senza profilo si riprende l'ultima.

    Si torna anche **da dove viene**, perche' va scritto nel log: una finestra
    che si apre con valori che l'utente non riconosce, e non dice perche', e'
    peggio di una che li ha dimenticati.

    Sta qui e non nella finestra perche' e' una decisione sulla configurazione,
    non sul disegno: qui si puo' verificare senza aprire Qt, e infatti e' cosi'
    che il difetto e' venuto fuori.
    """
    from core.config import Config, load_profile

    if profilo:
        return load_profile(profilo, overrides), f"profilo {profilo}"
    f = ultima()
    if f.exists():
        try:
            cfg = Config.load(f)
            cfg.apply(overrides)
            return cfg, f"l'ultima configurazione usata ({f})"
        except Exception as guasto:
            # Un profilo scritto da una versione precedente puo' avere un campo
            # che non esiste piu': si riparte dai default **dicendolo**, se no
            # il programma si apre diverso da ieri e nessuno sa perche'.
            return (Config().apply(overrides),
                    f"default: {f.name} non si e' potuto leggere ({guasto})")
    return Config().apply(overrides), "default"
