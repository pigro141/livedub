"""Le donazioni: **l'indirizzo, e la regola su quando si puo' chiedere**.

## Perche' sta in `core/` e non nella finestra

Sono due cose, e nessuna delle due e' disegno: *dove* si va a donare (un
indirizzo, che deve essere scritto **una volta sola** in tutto il programma) e
*se e quando* si chiede (una regola su tre numeri letti da un file). La lezione
piu' cara di questo repo e' che quattro dei cinque difetti trovati rileggendo le
cure a freddo stavano dentro Qt, l'unica parte del programma senza nessuna
verifica: qui invece si prova senza aprire una finestra, senza disco e senza
rete, compresi i casi limite che su questa macchina non capitano mai.

## L'indirizzo e' scritto qui e in nessun altro posto del codice

Il link vive gia' in fondo ai sette README, sulla vetrina e in
`.github/FUNDING.yml`. Quelli sono **testi**, e li' e' giusto che ci sia scritto
per esteso; nel **codice** c'e' `LINK` e basta. La verifica `dono` lo confronta
con `.github/FUNDING.yml` e pretende che nessun altro sorgente contenga
`ko-fi.com`: e' la forma «scritta due volte e la seconda non l'aggiorna nessuno»,
che in questo progetto e' gia' costata nove volte — e un indirizzo di donazione
sbagliato non da' errore, manda i soldi di qualcun altro da un'altra parte.

## Il criterio: **tre sessioni che hanno parlato, e cento battute in tutto**

La richiesta deve arrivare a chi il programma ha gia' servito. Le due meta' del
criterio rispondono a due domande diverse, ed e' per questo che ce ne vogliono
due:

- **cento battute dette** dice che ha *funzionato*. Una sessione puo' aprirsi,
  scegliere il loopback sbagliato e chiudersi in quattro secondi: contarla
  vorrebbe dire chiedere dei soldi a chi non e' ancora riuscito a sentire una
  voce. Misurato su `runs/2026-08-20_00-01-56`, una sessione vera ha fatto **146
  battute in 674,9 s**: cento battute sono percio' sette-otto minuti di dialogo
  doppiato, cioe' molto piu' di una prova;
- **tre sessioni** dice che ci e' *tornato*. Una passata sola, per quanto lunga,
  e' un tentativo riuscito; riaprire il programma una seconda e una terza volta
  e' l'unica cosa che distingue «ha funzionato» da «gli serve».

E una sessione conta **solo se ha detto qualcosa**: `conta_sessione` non scrive
niente quando le battute sono zero. Una catena che parte e muore non ha servito
nessuno, e contarla sarebbe far avvicinare la richiesta proprio a chi sta avendo
problemi.

## Chiesto una volta, e mai piu' — e questo e' un booleano apposta

`TUTORIAL` in `core/preferenze.py` e' un **numero** perche' la guida possa
riaprirsi il giorno in cui cresce un passo che conta. Qui e' il contrario, ed e'
una scelta e non una dimenticanza: sul bottone che chiude il riquadro c'e'
scritto «Non chiedermelo piu'», e alzare un numero vorrebbe dire rimangiarsi la
parola scritta sul bottone. Un programma che promette e poi ritorna insegna a non
credergli, e la volta che conta — un avviso vero — non lo legge piu' nessuno.

Quindi qualunque modo di chiudere quel riquadro vale come risposta: il bottone,
la X della finestra, e anche l'aver aperto la pagina. Non c'e' nessun modo di
farlo ricomparire, se non cancellando il file delle preferenze.

## E il bottone in testata non si nasconde mai

Il riquadro si chiude per sempre; la **porta** resta. E' il cuore accanto al `?`
e alla ⓘ, sempre nello stesso posto, e non dipende da nessuno di questi numeri:
chi ha detto «non chiedermelo piu'» ha chiesto di non essere interrotto, non di
non poter piu' donare.
"""

from __future__ import annotations

from typing import Any

# **L'indirizzo, e l'unico posto del codice in cui e' scritto.** Si veda la
# testata: la verifica `dono` lo confronta con `.github/FUNDING.yml`, che e'
# l'unico altro file che lo dichiara a una macchina invece che a un lettore.
LINK = "https://ko-fi.com/filippodebenedittis"

# Le chiavi nel file delle preferenze. Stanno qui e non scritte a mano nei punti
# che le usano: sono tre, e la terza e' quella che non si puo' sbagliare.
CHIAVE_CHIESTO = "dono_chiesto"
CHIAVE_SESSIONI = "dono_sessioni"
CHIAVE_BATTUTE = "dono_battute"

# Le due soglie. Il perche' di ciascuna, e perche' ce ne vogliono due, sta nella
# testata di questo file.
SESSIONI_MINIME = 3
BATTUTE_MINIME = 100


def _intero(dati: dict[str, Any], chiave: str) -> int:
    """Il valore di quella chiave come numero. **Quello che non si capisce vale 0.**

    Il file delle preferenze e' un JSON che qualcuno puo' aprire e ritoccare, e
    un carattere di troppo non deve cambiare il comportamento del programma.
    """
    try:
        return max(0, int(dati.get(chiave, 0)))
    except (TypeError, ValueError):
        return 0


def da_chiedere(pref: dict[str, Any]) -> bool:
    """Si puo' far comparire il riquadro? Funzione **pura**: solo il dizionario.

    **Il ripiego e' il silenzio, ed e' il contrario di `tutorial_da_mostrare`.**
    Li' un valore che non si capisce vale «mai vista», perche' mostrare la guida
    una volta di troppo e' un fastidio e nasconderla e' il difetto. Qui la
    direzione si rovescia: chiedere di nuovo dei soldi a chi ha gia' risposto e'
    molto peggio di non chiedere affatto, quindi tutto cio' che non si legge come
    un «no» pulito conta come un «no».
    """
    if pref.get(CHIAVE_CHIESTO):
        return False
    return (_intero(pref, CHIAVE_SESSIONI) >= SESSIONI_MINIME
            and _intero(pref, CHIAVE_BATTUTE) >= BATTUTE_MINIME)


def conta_sessione(battute: int, pref: dict[str, Any]) -> dict[str, int] | None:
    """Cosa scrivere nelle preferenze dopo una sessione. `None` se non c'e' niente.

    Pura anche questa: prende quello che c'e' e torna quello che ci andrebbe,
    cosi' il conteggio si prova senza toccare `%LOCALAPPDATA%`.

    **Una sessione muta non e' una sessione.** Con zero battute non si scrive
    niente — nemmeno il contatore delle sessioni — perche' una catena che parte e
    non dice una parola non ha servito nessuno: contarla vorrebbe dire avvicinare
    la richiesta proprio a chi sta ancora cercando di farlo funzionare.
    """
    try:
        dette = int(battute)
    except (TypeError, ValueError):
        return None
    if dette <= 0:
        return None
    return {
        CHIAVE_SESSIONI: _intero(pref, CHIAVE_SESSIONI) + 1,
        CHIAVE_BATTUTE: _intero(pref, CHIAVE_BATTUTE) + dette,
    }
