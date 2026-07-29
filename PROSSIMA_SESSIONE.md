# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`), doppiaggio
italiano live dei sottotitoli di GTA V. Leggi `CLAUDE.md` e basta: **non leggere
il README per intero**, costa e non serve.

## Usa il grafo come memoria, non grep

`graphify-out/graph.json` contiene anche le misure e i difetti, non solo il
codice. Per qualunque domanda su architettura, dipendenze, "dove sta X", "cosa
rompo se tocco Y", o su un difetto già trovato:

```powershell
graphify query "la tua domanda"
graphify explain "nome-nodo"
graphify path "NodoA" "NodoB"
```

Nodi utili: `wsola-deriva-puntatore`, `giro-identita-premia-difetto`,
`duck-pompaggio`, `onset-vad-falsificato`, `mis-roi-per-setup`,
`ocr-glifi-decapitati`, `anello-chiuso-accelerazione`.

**Attenzione**: `graphify.exe` è bloccato da un criterio di controllo
applicazioni su questa macchina (`ApplicationFailedException` sia da PowerShell
sia da bash). Se serve, o si sblocca, o si legge `graph.json` direttamente.

Ricostruisci il grafo a fine sessione con `graphify update` (codice, gratis) o
`/graphify` se ho toccato README/CLAUDE.md. **La sessione appena chiusa non l'ha
fatto**: il grafo non conosce ancora `listen/embed.py` né `tools/bench_speaker.py`.

## Stato

F0, F1, F2 chiuse. **F3 misurata, e la misura ha chiuso due strade invece di
aprirle.** La catena gira dal vivo e si ascolta.

| | |
|---|---|
| latenza sottotitolo→voce | p50 263 ms, p95 811 ms (budget 350 al p50) |
| compressione WSOLA | p50 1,067 |
| accelerazione del TTS | p50 1,39 |

### Cosa ha detto `tools/bench_speaker.py`

**1. Il codice è giusto.** Su voci sintetiche di identità nota, EER 0% da 1 s in
su. Il modello ECAPA, la fbank in scala Kaldi, il ricampionamento: tutto regge.

**2. La decisione a 300 ms non esiste, nemmeno nel caso facile.** Pulito: 23% di
EER a 0,3 s, 5% a 0,5 s, 0% a 1 s. Il ginocchio è a mezzo secondo. Rinviare
l'attacco e partire con una voce provvisoria non è il ripiego, è la strada.

**3. Sull'audio del gioco non si riconosce nessuno.** EER mai sotto il 27%, e
**tre casi nulli indipendenti lo pareggiano**: i lati del segnale stereo (dove il
dialogo per costruzione non c'è) danno 25,0% dove il centro dà 25,0; il silenzio
e il backend `mfcc` idem. Due prese di parola *diverse* a meno di dieci secondi si
somigliano più di due metà della *stessa*. Non è un riconoscitore debole: sta
datando l'audio, non identificandolo.

La causa è misurata, non ipotizzata: il parlato stacca dal fondo di **+3 dB**, e
le stesse voci note sommate al fondo vero del gioco fanno 0% di EER a +24 dB, 2%
a +12, **18% a 0 dB**, 48% a −6. Il gioco cade dove cade la curva. E non è la
selezione dei ritagli: 84 prese di parola su 94 cadono sotto un sottotitolo, e
restringersi a quelle **peggiora**.

**4. Il grigio non è un secondo personaggio.** Su 675 battute bianche registrate
dal vivo in 17 sessioni, le grigie sono **15, e nessuna è dialogo**: `'11111'`,
`"Tr'"`, `'IIFIL'`, `'er-s.'`, e una volta l'interfaccia di un terminale entrata
nella ROI. Il filtro del lessico ne ferma tredici; le due che passano vengono
pronunciate con la voce del secondo personaggio. Il vincolo di colore sul tracker
non ha su cosa appoggiarsi.

## Comandi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                 # 672 verifiche
.\.venv\Scripts\python.exe -m tools.bench_speaker --clean
.\.venv\Scripts\python.exe -m tools.bench_speaker testGameplayFattoDaMe.mp4 --profile gtav --audio-only --start 300 --end 900
.\.venv\Scripts\python.exe -m tools.live --profile live --loopback voicemeeter --seconds 150 --delay 15
.\.venv\Scripts\python.exe -m tools.reopen runs\<data> [secondo]
```

Le prove dal vivo si fanno sul **video di GTA V riprodotto in Chrome a schermo
intero**, audio su VoiceMeeter, uscita sulle cuffie. Profilo `live`. Chiedimi di
far ripartire il video prima di lanciare, e lascia 15 secondi.

## Cosa fare, in ordine

0. **Ascolta `runs\speaker_peek\*.wav`** (dodici file, un secondo l'uno). Sono i
   ritagli che il modello riceve davvero, salvati da `--peek`. Confermano o
   smentiscono a orecchio la storia dei +3 dB in trenta secondi, e la sessione
   scorsa sette difetti su sette li ha trovati l'orecchio.

1. **Estrarre meglio il parlato, prima di toccare l'identità.** Il mid/side
   attenua di 3 dB ciò che è decorrelato e basta: musica e motori restano quasi
   interi. La curva dice quanto serve guadagnare — **da +3 a +12 dB** porterebbe
   l'EER da 30% a 2%. Da provare, e da misurare con lo stesso banco (la riga
   `parlato` deve staccarsi dai casi nulli, altrimenti non è successo niente):
   separazione spettrale del centro, oppure un denoiser leggero in ONNX.
   Se non si guadagnano quei decibel, **l'identità dall'audio non si fa** e F3
   diventa un'altra cosa: due voci fisse, o l'identità dedotta dal testo.

2. **La voce.** `riccardo` è `x_low`, sbaglia accenti. Ora che il tempo regge è
   il collo di bottiglia della qualità. SuperTonic ha dieci voci native italiane
   (`speak/backends/supertonic.py`) e i modelli **non sono ancora scaricati**:
   ~398 MB. Griglia: sintesi p50, compressione applicata, sforamenti, su CPU.

3. **La riparazione vera di WSOLA.** Il gruppo `coda` registra dove siamo (28,2 a
   rate 1,25, crollo da 1,30). Se il puntatore di analisi viene sistemato senza
   rovinare lo spettro, quella verifica lo confermerà salendo.

4. **Il tasto per marcare una battuta dal vivo.** `Session.mark` è scritto, manca
   un modo di premerlo col gioco a schermo intero.

Non ricostruire il tracker di F3 finché il punto 1 non ha una risposta: con
questi numeri assegnerebbe voci a caso e sembrerebbe un problema di soglia.

## Le due lezioni di metodo, che valgono più del codice

**Il caso nullo migliore condivide tutto tranne la risposta.** Il silenzio e il
backend stupido dicevano già "stai misurando la scena", ma lasciavano aperta
l'obiezione "lì era diverso". I **lati** del segnale la chiudono: stesso istante,
stessa scena, stessa energia, e nessuna voce da riconoscere. Quando un caso nullo
pareggia la misura vera, non c'è soglia da aggiustare — non c'è segnale.

**Un sì/no diventa una diagnosi col gradino di mezzo.** "Le voci pulite si
separano, quelle del gioco no" ha quattro spiegazioni e un solo numero. Sommare
le *stesse* voci pulite al fondo *vero* della registrazione a SNR decrescenti ne
lascia in piedi una, e dice pure quanti decibel servono per uscirne.

E quella della sessione prima, che resta: **prima di credere a una misura verde,
chiediti se può esprimere la risposta sbagliata.** In questa sessione ne ha
beccata un'altra — l'anti-alias di `resample` era `[0, 1, 0]`, cioè l'identità,
per *tutti* i rapporti che il progetto usa, e la verifica era un giro identità su
un tono a 120 Hz che torna uguale con qualunque filtro, o senza.

---

Fine del prompt.
