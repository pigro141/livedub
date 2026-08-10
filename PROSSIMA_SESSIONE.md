# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`), doppiaggio
italiano dal vivo dei sottotitoli dei videogiochi.

## Il secondo gioco: fatto, e la risposta è metà sì

Il test c'è (gruppo `gioco2`, 78 verifiche, suite a **1346**) e le due passate a
confronto sono state fatte. Il gioco è **Mafia: The Old Country** in italiano.

**Un solo parametro dei due va bene a tutti e due i giochi.** La verità è
misurata *fuori* dalla catena — OCR sull'area intera a 2 Hz — perché «la catena
non l'ha letta» e «non c'era niente da leggere» sono due cose diverse:

| configurazione | GTA V (105 battute vere) | Mafia (18 vere) |
|---|---|---|
| com'è oggi (`line_pad=0`, `sat_max=37`) | 87 → 83% | **0 → 0%** |
| `line_pad=0,2` | 88 → 84% | 2 → 11% |
| `line_pad=0,2` + `sat_max=255` | 90 → 86% | **12 → 67%** |

- **`line_pad=0,2` è compatibile con tutti e due**, e su GTA V il guadagno non è
  nel conteggio ma nella frammentazione: il grappolo `Sali sul Mia / 3eo,ar /
  Joo,c / sigr;ta / ...` (quattordici righe di spazzatura) diventa `Sali sul
  furgone.` più quattro frammenti, `Torna sul fu re` diventa `Torna sul
  furgone.`, e tornano gli accenti. Fuori lessico 8,2% → 8,0%. Due passate di
  controllo **identiche carattere per carattere**, quindi non è fortuna.
  Resta a 0 di default: cambia il gioco principale (130 → 123 battute aperte) e
  quel giudizio è dell'orecchio. **Serve una prova d'ascolto per promuoverlo.**
- **Il filtro del colore non è compatibile, e non è una soglia da trovare.** Su
  GTA V spegnerlo butta giù l'intera difesa dall'HUD (1349 righe scartate → 0) e
  le due righe che *guadagna* sono `'Andiamo a Vinewood Boulevard.'` e
  `'Vinewood Boul'`: obiettivi di missione pronunciati. Fuori lessico 8,0% → 9,4%.
  *(E il metro «quante battute vere ritrova» **non può** esprimere questa
  risposta, perché conta l'HUD come testo vero: saliva da 88 a 90 mentre le cose
  peggioravano. È la regola del controllare che la misura possa rispondere.)*

**Ed è per questo che è diventato un comando dell'utente**, deciso il 7
agosto. Nella barra della UI ci sono due cose accanto: la casella **«Ignora i
sottotitoli colorati»** (`vision.exclude_colored`) e la sua manopola fine,
**«soglia»** (`vision.sat_max`), che dice quanto acceso debba essere un colore
per contare come colore — perché il criterio è **cieco alla tinta**: misurato su
sette colori, giallo, rosso, ciano, verde, viola e arancio si comportano
identici, e un azzurro pallido (saturazione 50) passa comunque. La soglia si
spegne insieme alla casella, perché a difesa spenta quel numero non lo guarda
nessuno. I due giochi lo vogliono al contrario e nessun valore li concilia,
quindi la scelta è di chi il gioco lo sta guardando — non un default da
indovinare. Si cambia **a caldo**: la casella scrive nella config viva che il
lettore rilegge a ogni fotogramma, e c'è una verifica che lo prova su un lettore
già costruito (mutando la riga che legge il campo, il gruppo diventa rosso in sei
punti — è la classe di difetto che questo progetto ha già pagato quattro volte).
Sul banco l'interruttore dà un risultato **identico carattere per carattere** a
`sat_max=255`, quindi tutte le misure archiviate continuano a parlare di lui.

Quello che resta aperto è quindi **la terza posizione dell'interruttore**: saper
dire «il colore è del **nome**, non di scenario», così che nessuno dei due giochi
debba rinunciare a niente. Il nome sta all'inizio della riga, finisce con i due
punti, e si ripete identico fra le battute — tre indizi che una soglia sulla
saturazione non ha. `vision/label.py` esiste già e fa metà del lavoro.

Il materiale: `mafia_scena.mp4` (150 s dall'Atto 3 «Pizzu», gitignorato) e le due
schermate dell'utente in `assets/gioco2/`. `yt-dlp` va installato **fuori dal
venv** (`pip install --target`, il venv monta `onnxruntime-gpu` e non si tocca) e
si scarica solo la finestra che serve con `--download-sections`.

## Il blocco UI e la distribuzione: fatti

`SviluppoProgetto.md` è la roadmap. **16 step su 19 sono chiusi**, e tutto il
blocco UI più tutta la distribuzione sono stati fatti l'8 agosto 2026:

- **la finestra** ha quattro schede (Sessione, Tecnologie, Aree, Impostazioni
  avanzate) e la barra di prima sopra;
- **le impostazioni si generano dall'albero** (`core/schema.py` + `ui/pannello.py`):
  166 campi, il `?` di ognuno apre il commento di `core/config.py` *così com'è
  scritto*, misure comprese. Non è un elenco a mano: aggiungere un campo lo fa
  comparire da solo;
- **142 campi su 166 si applicano a caldo**, i 24 che non possono lo dicono;
- **le aree multiple** ci sono fino in fondo — config, catena, finestra — con i
  due modi e le sovrapposizioni sottratte prima di leggere;
- **licenza GPL-3.0-or-later**, obbligata da Piper (default) ed eSpeak NG. Il
  conto sta in `LICENZE.md`;
- **`installa.ps1`** verifica invece di dire «fatto»; **`livedub.spec`** produce
  l'exe, ed è stato aperto e fotografato;
- **README** rifatto per chi arriva da fuori, col diagramma Mermaid, la lista di
  cosa esce dal computer e i requisiti misurati. Il vecchio è
  `docs/architettura.md`.

## Cosa resta davvero: tre voci, tutte in attesa dell'utente

1. **creare il repo GitHub** — l'utente ha detto «aspetta». Tutto il materiale è
   pronto in locale; manca solo `gh repo create` e il push.
2. **il sito GitHub Pages** — dipende dalla prima.
3. **il link per le donazioni** — l'utente ha detto «dopo».

**Una cosa da decidere prima di pubblicare**: 156 commit su 159 hanno il trailer
`Co-Authored-By: Claude`. L'autore git è sempre e solo `filde`, quindi su GitHub
non comparirebbe nessun collaboratore — ma il trailer si legge nei messaggi.
Toglierlo significa riscrivere la storia (`git-filter-repo`), e va deciso.

**E una decisione d'orecchio ancora aperta**: promuovere `line_pad` a 0,2 come
default. Misurato meglio su tutti e due i giochi (vedi sopra), ma cambia il gioco
principale — 130 → 123 battute aperte — e quello lo giudica l'ascolto, non il
lessico. Basta una prova con `tools/dub.py --mp4` affiancata.

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

Suite verde a **1346 verifiche**. La catena dal vivo funziona: ultima sessione
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
.\.venv\Scripts\python.exe -m tools.selftest                    # 1346 verifiche

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
*(Il secondo gioco è **fatto**, e sta in cima a questo file: test verde, due
passate misurate. Di lì resta aperta una cosa sola — il criterio della parola
colorata contro un nome colorato per progetto — e una decisione d'orecchio:
promuovere `line_pad` a 0,2 come default. Che il margine giovi anche a GTA V
adesso è misurato, e la risposta è sì.)*

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
