# La tua prova, e cosa guardare

Questo file e' il foglio della **prova d'ascolto**: come si accende, cosa
guardare, e cosa mi serve nel tuo report. La suite e' verde (1112 verifiche) ma
la suite non sente niente: ogni difetto serio di questo progetto e' stato trovato
dal tuo orecchio, con la suite verde.

---

## Come si accende

```powershell
cd C:\Users\filde\Documents\!code\CLAUDE\livedub

# sottotitoli italiani -> voce italiana (il caso principale)
powershell -ExecutionPolicy Bypass -File tools\prova.ps1

# sottotitoli italiani -> voce inglese, con il sottotitolo tradotto a schermo
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci

# per vedere solo cosa farebbe, senza partire
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci -Prova
```

Lo script controlla **prima** le tre cose che altrimenti si scoprono a gioco
avviato: che il venv ci sia, che esista la scheda di cattura `voicemeeter`, e —
se traduci — che Ollama sia acceso e abbia `translategemma:4b` (se e' spento lo
accende lui). Poi stampa la configurazione per esteso, cosi' il report dice cosa
e' stato provato davvero.

Nella finestra: **Seleziona area** sui sottotitoli del gioco, poi **Avvia**. Alla
fine **Ferma**, e la sessione finisce in `runs\<data-ora>` con dentro l'audio,
gli eventi e il riepilogo.

**Il gioco deve stare in finestra senza bordi, non a schermo intero esclusivo.**
Sopra un fullscreen esclusivo nessuna finestra puo' comparire, e l'overlay non si
vedrebbe — senza che niente lo dica.

---

## 1. La grafica del sottotitolo tradotto — riscritta, e stavolta guardata

Era il punto aperto: scritta e mai vista a schermo. **L'ho guardata**, mettendo
un fotogramma della registrazione a tutto schermo e disegnandoci sopra l'overlay
vero, e aveva un difetto che nessuna verifica poteva prendere:

> la finestra veniva dimensionata sul testo **originale**, e dentro ci si
> disegnava quello **tradotto**. `"But if I had one, I'd want it to be like you,
> and that is the whole point of it."` compariva come `"be like you, and that is
> the"` — la riga di mezzo, tagliata sopra e sotto.

Adesso la finestra e' il **massimo fra i due**: l'inchiostro vecchio (per
coprirlo) e il testo nuovo (per leggerlo), e cresce verso l'alto restando
appoggiata dov'era la riga vecchia. La sfocatura e' passata da un velo che
lasciava leggere l'italiano sotto a una che lo cancella.

**Cosa guardare a schermo:**

- il riquadro cade **sul** sottotitolo del gioco, non altrove;
- dell'originale non si legge piu' niente, nemmeno ai lati del testo nuovo;
- una battuta lunga si legge **tutta**, anche quando va a capo;
- **dopo aver ridisegnato l'area con «Seleziona area»** il riquadro segue: era
  rotto, la finestra restava dove stava la ROI di partenza;
- che non dia fastidio giocando: non deve rubare i clic ne' il fuoco.

Puoi cambiare come copre senza toccare il codice:

    --set translate.background_mode=blur       (default adesso, sfoca)
    --set translate.background_mode=riquadro   (rettangolo pieno, stretto sul testo)
    --set translate.background_mode=nessuno    (niente sfondo, si vede il gioco)
    --set translate.blur_strength=20           (piu' alto = piu' sfocato)
    --set translate.font_frac=0.045            (testo piu' grande)

**Se il riquadro cade nel posto sbagliato** dimmi *dove* cade rispetto al
sottotitolo (sopra? spostato a destra? troppo largo?): la conversione ora passa
dalle coordinate normalizzate e ha una verifica sua, quindi un errore li'
significherebbe che la cattura non inquadra lo schermo intero.

## 2. La compressione — alzata la scusa, e serve il tuo giro per chiuderla

`dub.rate_x1000` restava a **1250 su tutti i percentili**: ogni battuta
schiacciata al massimo, con il parlato che riempiva meta' scena.

La causa e' quella che sospettavo, e adesso e' misurata. Il budget di una battuta
e' `finestra prevista - (tempo gia' passato - scusa)`. Con la traduzione sulla
strada critica il tempo gia' passato e' **1,6-1,7 s** (misurato dalle tue due
sessioni), e la scusa valeva **250 ms**: al budget venivano tolti quasi un
secondo e mezzo di una finestra che ne dura due.

Rigiocando la programmazione delle tue due sessioni con scuse diverse (stessi
tempi veri, stesse durate: cambia solo la scusa) — la peggiore delle due:

| scusa | compressione p50 | battute al tetto |
|---|---|---|
| 250 ms (com'era) | 1,250 | 100% |
| 900 ms | 1,250 | 62% |
| 1000 ms | 1,182 | 25% |
| **1250 ms (adesso)** | **1,000** | 17% |
| 1600 ms | 1,000 | 12%, ma la coda cresce |

Il controllo che rende credibile quel conto: alla scusa che quelle sessioni
avevano davvero, il conto riproduce esattamente quello che era stato registrato.

**Il numero che ti chiedo di guardare**, nel riepilogo a fine sessione:
`dub.rate_x1000` **deve staccarsi da 1250** almeno al p50. Se resta 1250 su tutti
i percentili anche adesso, la diagnosi era sbagliata e il vincolo sta altrove —
e lo scrivo qui prima della tua prova apposta, perche' una previsione fatta dopo
non puo' perdere.

E poi giudicalo a orecchio: la voce dovrebbe articolare invece di correre. In
cambio si accettano fino a ~370 ms in piu' sul ritardo peggiore.

**Senza traduzione non peggiora**, che era il rischio: misurato sulla
registrazione, la compressione mediana non si muove, quella al p95 migliora
(1,250 -> 1,133) e gli sfori si dimezzano.

## 3. Quello che resta aperto e non dipende da me

- **`translate.preserve_register`**: TranslateGemma ammorbidisce le parolacce.
  Con il registro chiesto esplicitamente fa 2-3 su 6, Google 6 su 6 ma manda
  ogni sottotitolo ai suoi server. Se traduci e ti sembra che dica un'altra
  cosa, e' questo, non l'OCR.
- **La correzione OCR resta spenta**, con i numeri in mano: `translategemma:4b`
  fa 5 su 8 ma **1784 ms per parola**, contro un guadagno massimo di una parola
  su settanta.
- **Il nome del parlante** (`label.form`) e' provato solo su testo sintetico:
  GTA V i nomi non li scrive. Il contatore `vision.label.hit` dira' subito se il
  formato dichiarato e' quello giusto, quando avrai un gioco che li scrive.
- **Le voci femminili**: la taratura del genere non e' mai stata provata su una
  donna, perche' nella registrazione non ce n'e' una.

---

## Cosa mi serve nel report

Per ogni cosa che non va, la sola informazione che vale piu' di tutte le altre e'
**il secondo in cui l'hai sentita**: `runs\<data-ora>` si riapre con

```powershell
.\.venv\Scripts\python.exe -m tools.reopen runs\<data-ora> <secondo>
```

e da li' si vede cosa aveva letto l'OCR, chi credeva che parlasse, che voce gli
aveva dato e quanta fretta gli aveva chiesto. Un'impressione senza il secondo
costa mezza sessione; il secondo la chiude in cinque minuti.
