"""Quello che la finestra deve ricordarsi fra un avvio e l'altro.

**Perche' esiste.** Chiudendo la finestra si perdeva ogni regolazione: un'ora di
lavoro sulle soglie buttata, e la volta dopo si ricominciava dai default. Era il
difetto piu' grave della lista di produzione, e non e' un dettaglio
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


# ------------------------------------------------------- il tutorial iniziale --

# **La versione del tutorial, e non un «l'ho visto» acceso o spento.** Un
# booleano sa dire una cosa sola e per sempre: il giorno in cui la guida cresce
# un passo che cambia qualcosa — un pezzo nuovo da installare, una scelta che
# prima non c'era — nessuno di quelli che l'hanno gia' vista lo vedra' mai.
# Alzando questo numero lo rivedono tutti, e chi non lo alza non ha cambiato
# niente di importante.
# **2 dal 20 agosto 2026**: la guida ha guadagnato il passo che misura questa
# macchina, sceglie i motori e scarica i modelli mancanti. E' esattamente il caso
# per cui questo campo e' un numero — chi aveva gia' visto la guida non ha mai
# visto quel passo, e senza questo scatto non lo vedrebbe mai: continuerebbe a
# sentire il ripiego leggero senza sapere che c'e' di meglio, che e' il difetto
# che quel passo esiste per chiudere.
# **3 dal 4 settembre 2026**: la guida ha guadagnato l'ultimo passo, quello che
# dice che il programma e' gratis, che e' GPL e dove sta la porta delle
# donazioni. Chi la guida l'aveva gia' vista non ha mai letto quella riga da
# nessuna parte — nel programma non c'era — e senza questo scatto non la
# leggerebbe mai.
TUTORIAL = 3

# La chiave nel file. Sta qui e non scritta a mano nei due punti che la usano.
_CHIAVE_TUTORIAL = "tutorial_visto"


def tutorial_da_mostrare(pref: dict[str, Any] | None = None) -> bool:
    """Va aperto il tutorial? **Si', la prima volta e mai piu'.**

    Sta in `core/` e non nella finestra perche' e' una regola, non un disegno:
    «va mostrato?» si risponde con un numero letto da un file, e la lezione gia'
    pagata di questo progetto e' che quattro dei cinque difetti trovati rileggendo
    le cure a freddo stavano in Qt o al suo confine — l'unica parte del programma
    che nessuna verifica toccava. Qui si prova senza aprire niente.

    **Un valore che non si capisce vale «mai visto».** Se qualcuno apre il file e
    ci scrive dentro, mostrare la guida una volta di troppo e' un fastidio;
    nasconderla a chi non l'ha mai vista e' il difetto che questa funzione esiste
    per impedire.
    """
    dati = leggi() if pref is None else pref
    try:
        return int(dati.get(_CHIAVE_TUTORIAL, 0)) < TUTORIAL
    except (TypeError, ValueError):
        return True


def tutorial_visto() -> None:
    """Segna la guida come vista. **Finito e saltato sono la stessa cosa.**

    Se saltarlo non lo segnasse, si riaprirebbe a ogni avvio: saltarlo
    lascerebbe il programma peggio di non averlo mai aperto, cioe' toglierebbe
    valore all'unica via d'uscita che gli si e' data.
    """
    aggiorna(**{_CHIAVE_TUTORIAL: TUTORIAL})


# ------------------------------------------------ il riquadro delle donazioni --
#
# **Qui c'e' solo il disco.** Quanto si debba aver usato il programma prima di
# poter chiedere qualcosa, e cosa valga come «ha gia' risposto», sono regole e
# stanno in `core/dono.py`, dove si provano senza toccare `%LOCALAPPDATA%` e
# senza aprire una finestra. Queste due funzioni sono la meta' che scrive.


def dono_sessione_finita(battute: int) -> None:
    """Segna una sessione finita, **se ha detto qualcosa**.

    La chiama la finestra quando la catena si e' fermata, non mentre gira: e' la
    stessa ragione per cui il riquadro non compare mai in mezzo a una sessione.
    Con zero battute non scrive niente — si veda `core.dono.conta_sessione`.
    """
    from core import dono

    dati = leggi()
    nuovi = dono.conta_sessione(battute, dati)
    if nuovi:
        aggiorna(**nuovi)


def dono_da_chiedere() -> bool:
    """Il riquadro va aperto adesso? La regola sta in `core/dono.py`."""
    from core import dono

    return dono.da_chiedere(leggi())


def dono_chiesto() -> None:
    """«Chiesto»: e non si chiede piu', in nessun modo e per sempre.

    **Un booleano e non un numero**, che e' il contrario di `TUTORIAL` e lo e'
    apposta: sul bottone che chiude quel riquadro c'e' scritto «Non chiedermelo
    piu'», e alzare un numero per farlo ricomparire vorrebbe dire rimangiarsi la
    parola che il programma ha appena dato.
    """
    from core import dono

    aggiorna(**{dono.CHIAVE_CHIESTO: True})


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
