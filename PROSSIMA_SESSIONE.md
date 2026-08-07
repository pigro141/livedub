# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`), doppiaggio
italiano dal vivo dei sottotitoli dei videogiochi.

## Il lavoro di questa sessione, e nient'altro

**Si lavora su `SviluppoProgetto.md`, blocco UI.** Quel file è la roadmap: 14
feature su 14 chiuse, 4 step finali su 19, e il cancello che diceva *«prima di
iniziare la fase seguente fammi fare una prova»* è stato passato il 7 agosto 2026
— l'utente ha provato dal vivo, ha consegnato il report in forma di video, e i
quattro difetti che ne sono usciti sono corretti.

**Da qui in poi non si misura più: si costruisce l'interfaccia.** È il contrario
di tutto quello che è venuto prima, ed è scritto nella roadmap. Se ti viene la
tentazione di aprire un banco, rileggi *«Cosa NON si fa»* in fondo.

Le cinque voci del blocco, in ordine:

1. **UI, interfaccia chiara e funzionale**
2. **Selettore delle tecnologie da usare** (motore TTS, OCR, traduttore, impronta)
3. **Impostazioni avanzate**: *tutti* i parametri regolabili, ognuno con l'icona
   che spiega cosa fa e cosa si rischia a cambiarlo — comprese le frequenze
   maschio/femmina
4. **Cambiamento dei settings a caldo**, applicati dal vivo
5. **Selettore di aree multiple**: solo testo, oppure testo+audio; e se due aree
   si sovrappongono quel punto **non va lavorato due volte**

Finito il blocco UI si passa a distribuzione (installabile, exe, licenza) e poi
al repo. Sono già scritti in `SviluppoProgetto.md`; non riscriverli qui.

## Le quattro cose da sapere prima di scrivere una riga di UI

**1. La UI non va inventata, va generata.** In `core/config.py` c'è **un solo
albero di dataclass**, e ogni campo è già raggiungibile con
`--set sezione.campo=valore`. Le impostazioni avanzate si costruiscono
**percorrendo quell'albero**, non elencando i campi a mano: un elenco scritto a
mano diverge al primo campo aggiunto, e questo progetto ha già quattro campi
dichiarati in config che *non li leggeva nessuno* (`max_ocr_hz`, `tts.device`,
`background_mode`, `overlay.ritardo`).

**2. Le spiegazioni che l'utente chiede sono già scritte.** Quasi ogni campo di
`core/config.py` ha sopra un commento che dice **cosa fa, quanto è stato
misurato e cosa succede a cambiarlo** — spesso con la tabella della misura. Sono
esattamente il testo dell'icona. Vanno estratti, non riscritti: riscriverli
significa perdere le misure e inventare rischi.

**3. Non tutti i parametri si possono cambiare a caldo, e la differenza è
sostanziale.** Alcuni si leggono a ogni fotogramma (colori, soglie, dimensioni);
altri si leggono **una volta sola alla costruzione** — il backend TTS, il backend
OCR, il dispositivo, la frequenza dell'anello audio. Cambiare i secondi a caldo
non dà errore: dà una sessione che gira con una configurazione diversa da quella
che la UI mostra, che è il difetto peggiore possibile per uno strumento di
misura. **La UI deve sapere quali sono quali** e, per i secondi, dire che serve
un riavvio invece di fingere.

**4. Il meccanismo di due voci spuntate c'è già, manca solo la faccia.** Colore e
dimensione dei sottotitoli (`translate.color`, `background`, `background_opacity`,
`background_mode`, `blur_strength`, `font`, `font_frac`, `outline`) e la scelta
delle lingue (`translate.source` / `target`) funzionano già da `--set`. Il blocco
UI in buona parte consiste nel dare una faccia a cose che girano.

## Come si conosce questo progetto

**Il grafo è la memoria.** In `graphify-out/graph.json` c'è la mappa della
codebase, aggiornata al 7 agosto (1688 nodi, 3273 archi). Per qualunque domanda
architetturale si usa `graphify query "<domanda>"` **prima** di partire a grep.
Si riaggiorna con `/graphify . --update` dopo modifiche grosse, non a ogni task.

Poi `CLAUDE.md`, che ha l'architettura e le regole di metodo. **Non leggere il
README per intero.**

## Come voglio che tu lavori

- **Scrivi solo quando hai finito.** Non commentare ogni passo.
- **Descrivi in modo semplicissimo ma dettagliato** cosa hai fatto.
- **Non sprecare token.**
- **Prima di azzardare, chiedi.**

## Dove siamo

Suite verde a **1172 verifiche**. La catena dal vivo funziona: ultima sessione
(`runs/2026-08-07_03-34-36`, 58 battute in 3 minuti, area stretta a 0,080):

| | |
|---|---|
| punteggio riconoscimento p50 | 0,414 |
| voci neutre | 38% |
| battute con HUD incollata | 0% |
| latenza p50 | 1239 ms |
| WSOLA p50 | 1,000 |

Il confronto è con `runs/2026-08-07_01-40-16`, la sessione **prima** delle
correzioni: punteggio 0,136, neutre 97%, HUD 11%, latenza 1693 ms.

## Come si prova quello che scrivi

La UI si prova accendendola. Il resto serve solo a controllare che una modifica
non abbia rotto la catena sotto.

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                    # 1172 verifiche

# la UI dal vivo, con i controlli fatti prima e la configurazione stampata
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci -Traduttore google

# la catena su una registrazione, senza gioco (yt_scena.mp4 e' la scena archiviata)
.\.venv\Scripts\python.exe -m tools.dub yt_scena.mp4 --profile gtav `
    --start 29 --end 315 --set vision.ocr_backend=oneocr
```

`DA_VERIFICARE.md` è il foglio della prova d'ascolto.

## Cosa NON si fa in questa sessione

Queste sono aperte, **misurate**, e **non sono il lavoro di adesso**. Stanno qui
perché non vadano perse, non perché vadano fatte. Non aprirle senza che l'utente
lo chieda:

- **`native_rate_max` è un numero solo per tutti i motori** (1,55) mentre i tetti
  di integrità misurati sono 1,10 per SuperTonic e 1,30 per Kokoro. Decisione
  dell'orecchio, non del codice: due MP4 affiancati e l'utente sceglie.
- **`speaker.ring_lag` mente**: dice 5543 ms mentre `ritardo_anello` per battuta
  dice 7 ms. Ha già sviato una diagnosi. Va aggiustato o tolto — ma dopo la UI.
- **La parola colorata corta in frase lunga** («Premi **E** per entrare») resta
  scoperta: quota 0,025, sotto qualunque soglia che non butti via dialogo.
- **`line_gap_split` sull'area larga** non è mai stato verificato fino in fondo:
  la passata di controllo era andata in timeout. L'11% è la misura del difetto,
  non del rimedio.
- **`decide_after_ms`** vale 500 ms dei 1239 di latenza, il doppio della sintesi.
  Abbassarlo guadagna tempo e costa attribuzioni sbagliate: altro scambio da
  orecchio.

Il banco `yt_scena.mp4` (282 MB, gitignorato) resta lì per quando serviranno: è
la scena della sessione dell'utente, avanti di 29,5 s rispetto ai suoi tempi.

## Le regole di metodo che valgono anche sulla UI

Sono in `CLAUDE.md` per esteso. Le due che mordono qui:

**Un pezzo che nessuno ha guardato non è «scritto», è «supposto».** L'overlay è
stato consegnato verde e con gli import a posto; messo a schermo e fotografato,
il difetto era il primo che si vedeva. Una UI si giudica **guardandola**, e la
suite verde non è una conferma.

**Quando l'utente deve accendere il gioco per giudicare, lo strumento è
sbagliato.** Se una schermata si può provare senza una sessione intera
dell'utente, va fatta in modo che si possa.

Fine del prompt.
