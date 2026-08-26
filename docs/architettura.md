# livedub

Doppiaggio italiano **live** dei sottotitoli di un videogioco: voci diverse per
personaggi diversi, tono e volume guidati dall'emozione, durata agganciata al
parlato originale. Nessuna battuta viene scartata.

## Come funziona

Due domini scorrono in parallelo e si incontrano in un punto solo.

```
VIDEO   ROI → righe → classe colore → OCR → SubtitleEvent(testo, bianco|grigio)
                                                        │
AUDIO   loopback → center → VAD → embedding → tracker → SpeakerEvent(chi, come)
                                                        │
                                                    FUSIONE
                                                        ▼
                                    voce assegnata → TTS → prosodia → filtri
                                                        ▼
                        audio gioco → duck del centro → MIX → uscita
```

**L'audio non dice mai *cosa* si dice** — quello viene dall'OCR. Dice solo *chi*
e *come*. Questo toglie dalla catena il riconoscimento vocale, e con lui la sua
latenza.

### La grammatica dei sottotitoli

Il colore del testo porta informazione, e si legge **per riga**:

| | |
|---|---|
| riga con glifi **saturi** | non e' dialogo: suggerimento o obiettivo → **si scarta la riga intera** |
| riga **bianca** | battuta dello speaker principale |
| riga **grigia** | battuta di un *secondo* speaker che parla quasi in contemporanea |

Due righe della stessa luminanza sono una frase andata a capo. Due righe di
luminanza diversa sono **due battute distinte**, con due voci diverse — ed e'
anche l'unico indizio su chi parla disponibile *nell'istante* in cui il
sottotitolo compare, quando l'embedding audio e' ancora incerto.

## Comandi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest              # suite completa (2085 verifiche)
.\.venv\Scripts\python.exe -m tools.selftest ring config  # un gruppo solo
.\.venv\Scripts\python.exe -m tools.demo                  # scena finta completa -> runs\demo_mix.wav
.\.venv\Scripts\python.exe -m tools.demo --no-duck        # la stessa, per sentire cosa fa il duck
.\.venv\Scripts\python.exe -m tools.say --pool            # ascoltare le voci
.\.venv\Scripts\python.exe main.py --dump-config
.\.venv\Scripts\python.exe -m tools.fetch_lexicon             # il filtro sulla lingua
```

Dal vivo, e per riaprire cio' che si e' sentito:

```powershell
.\.venv\Scripts\python.exe -m tools.live --profile live --loopback voicemeeter --seconds 150
.\.venv\Scripts\python.exe -m tools.reopen runs\<data>          # il quadro d'insieme
.\.venv\Scripts\python.exe -m tools.reopen runs\<data> 95.4     # cosa succedeva li'
```

Su una cattura nuova la ROI va rifatta: e' del **setup**, non del gioco. Il
profilo del file non vale per lo stesso video riprodotto a schermo — misurato,
il ritaglio taglia i glifi a meta' e l'OCR restituisce testo plausibile e falso.

Sulla registrazione, **in quest'ordine** — il primo comando non e' facoltativo:

```powershell
.\.venv\Scripts\python.exe -m tools.replay gameplay.mp4 --peek 8      # guardare la ROI
.\.venv\Scripts\python.exe -m tools.calibrate gameplay.mp4 --write profiles\gtav.json
.\.venv\Scripts\python.exe -m tools.replay gameplay.mp4 --profile gtav --start 1240 --end 1290
.\.venv\Scripts\python.exe -m tools.replay gameplay.mp4 --profile gtav --start 1240 --end 1290 `
    --dump-reads runs\reads.jsonl        # il flusso di letture, per studiarlo dopo
```

`--dump-reads` registra **ogni** alimentazione del tracker, comprese quelle che
ha scartato: giudicare lo stabilizzatore da cio' che ne esce e' chiedere
all'imputato di scegliere le prove.

### I banchi di misura non stanno nel repo pubblicato

I commenti di questo progetto citano per nome lo strumento con cui una misura e'
stata fatta — `tools/bench_onset.py`, `tools/bench_speaker.py`,
`tools/bench_memoria.py`, `tools/bench_translate.py`, `tools/recluster.py`,
`tools/retrack.py` e gli altri. Sono **banchi di sviluppo**: restano sulla
macchina di chi li ha scritti e non vengono pubblicati, perche' chi scarica il
programma vuole la finestra, l'installazione e la suite di verifica, non il
laboratorio. La citazione resta lo stesso, perche' dice **da dove viene un
numero** — che e' l'unica cosa che lo rende leggibile. Il file, no.

## Cosa e' stato misurato

Ogni numero qui sotto viene dal banco, non da una stima. Le sorprese sono
segnate perche' sono quelle che hanno cambiato il disegno.

| | |
|---|---|
| OCR, sola recognition | 8–60 ms per riga **su CPU**, contro 985 ms del det+rec completo |
| OCR, det+rec vs ritaglio stretto | CER 5,6% → **0%**: era l'ingresso a essere sbagliato, non il modello |
| OCR, costo | scala con la **larghezza**; ingrandire in altezza raddoppia il costo a parita' di accuratezza |
| OCR, ritaglio | grigio mascherato invece che binario: CER 4,4% → 2,9% |
| Piper, primo campione | 36–70 ms, RTF 0,024–0,037, zero VRAM |
| Piper, `length_scale` | **non proporzionale**: chiedendo 0,8 si sbaglia del 14% |
| Latenza end-to-end | **135 ms** p95 (sottotitolo → prima voce italiana), budget 350 |
| Soglia di luminanza assoluta | si rompe su fondo chiaro da 120 in su; col contrasto locale regge fino a 180 |

Conseguenza grossa: **la GPU non serve a niente di tutto questo** e resta
interamente al gioco.

### Cosa ha detto la registrazione vera

I numeri qui sopra vengono da frame sintetici. Il primo contatto con due
registrazioni di GTA V (9 e 28 minuti, 1080p) ne ha cambiati alcuni.

| | |
|---|---|
| **Il grigio esiste** | `Ciao, Lamar!` a luma **253** e `Che succede, Simeon?` a **142**, nello stesso frame. La grammatica regge, e i due gruppi sono lontanissimi |
| **Ma e' raro** | un solo passaggio netto in 28 minuti. Il vincolo bianco/grigio di F3 arrivera' di rado: e' un segnale forte e sporadico, non continuo |
| **La ROI cambia da registrazione a registrazione** | stesso gioco, stessa risoluzione, sottotitoli a 0,965 dell'altezza in una e a 0,914 nell'altra. La ROI e' del *setup*, non del gioco: `tools/calibrate.py` va rifatto a ogni cambio di cattura |
| ROI di default | inquadrava il tappeto. Zero battute — che somiglia moltissimo a "il modello non regge" |
| OCR con ROI sbagliata | **223 ms** mediani contro i 15 sul sintetico: la banda di riga si allargava sulla texture della scena, e il costo scala con la larghezza |
| `contrast_min` | misurato **29**; il default 30 era gia' giusto. La spazzatura veniva dalla ROI, non da questa soglia |
| Righe di un carattere | `'1'`, `'—'`, `'?'` letti da cordoli e strisce bianche. Passano ogni soglia di colore perche' sono davvero bianchi: li ferma `min_ocr_chars`, cioe' la lingua — e conta **lettere**, perche' una riga letta `'·..··'` di caratteri ne ha cinque e di lingua nessuna |
| **La saturazione puniva il dialogo** | 863 righe scartate in 20 minuti perche' un oggetto colorato entrava nella ROI. Erano quasi tutte battute bianche a luminanza 249 |

**Due misure sbagliate prese in flagrante**, che sono il motivo per cui la
regola vale per ogni misura di questo progetto: ancorare il testo con una maschera che pretende uno
stacco di 60 e poi *misurarne* lo stacco da' 60,15 — la misura non poteva
esprimere altro numero; ancorarlo invece su "bianco e acromatico" da' −2,3,
perche' nella ROI finiscono muri chiari e carrozzerie bianche. Serve il top-hat
morfologico, che vede la *sottigliezza* di un tratto e non la sua luminosita'.

### SuperTonic 3: provato dal vivo, scartato dall'orecchio

Dieci voci italiane native contro le due di Piper, su CPU e in ONNX — sulla
carta chiudeva il limite che il piano dava per insuperabile senza GPU. Sul
banco i numeri erano difendibili: RTF 0,095, ritmo pareggiato a Piper con
`speed` 1,50 (17,1 caratteri al secondo contro 17,4), arretrato mediano **zero**
grazie alla compressione, cioe' migliore di Piper.

**All'ascolto era inservibile**: battute mezze tagliate, in ritardo, non si
capiva niente. E la ragione sta in un numero che sul banco sembrava innocuo —
`dub.rate_x1000` a **1350 al p50**, cioe' *ogni* battuta detta al massimo
dell'accelerazione, con 20 sforamenti su 23 contro i 10 su 24 di Piper. I 323 ms
di sintesi non facevano piu' coda: mangiavano la finestra della battuta, e cio'
che restava andava detto di corsa.

| | Piper | SuperTonic 3 |
|---|---|---|
| sintesi p50 | 59 ms | 323 ms |
| latenza p50 | 367 ms | 588 ms |
| compressione applicata, p50 | 1,246 | **1,350 (satura)** |
| sforamenti | 10 su 24 | **20 su 23** |
| voci italiane | 2 | 10 |

Il backend resta in `speak/backends/supertonic.py`, scegliibile da config: non
e' codice morto, e' un'opzione per scene meno fitte. Ma il tier A resta Piper,
e il motivo per cui vince non e' la qualita' della voce — e' che costa
sessanta millisecondi invece di trecento, e in una catena live quello decide
tutto il resto.

**Quello che si perde tenendo Piper**, e va scritto perche' e' il prossimo
problema: `riccardo` e' un modello `x_low`, sbaglia qualche accento, alcune
parole non le pronuncia bene, e l'espressivita' e' quella che e'. E' un
compromesso accettato con cognizione di causa, non una scelta soddisfacente.
La strada da esplorare resta un TTS piu' veloce di SuperTonic e piu' fedele di
Piper — Qwen3-TTS e simili, misurati **su CPU** e con la stessa griglia usata
qui: sintesi p50, compressione applicata, sforamenti.

### L'aggancio all'onset: l'ipotesi non regge su GTA V

Il piano dava per buono che sottotitolo e voce non coincidano — *«il sottotitolo
compare quando il gioco decide di mostrarlo, la voce comincia quando il
personaggio apre la bocca»* — e ne faceva il secondo dei tre pilastri di F2.
Il banco dell'onset misura quello sfasamento sulla registrazione vera, e la
premessa cade:

| | rec1 (160 s) | rec2 (340 s) |
|---|---|---|
| sfasamento mediano onset − sottotitolo | **−33 ms** | **−20 ms** |
| dispersione (p90−p10) | 0,32 s | 0,38 s |
| eccesso sul caso, alla finestra migliore | +18,8% a ±0,20 s | +10,7% a ±0,50 s |

**I due istanti coincidono**, quindi non c'e' niente da correggere; e l'onset e'
comunque *disponibile* sopra il caso per una battuta su cinque nella prima
registrazione e su nove nella seconda. Agganciarcisi sposterebbe l'attacco di
poche decine di millisecondi quando ci azzecca, e di mezzo secondo quando
l'accoppiamento e' casuale. `timing.use_vad_onset` resta quindi **spento per
misura, non per pigrizia**, e il banco esiste per rifare la domanda sul prossimo
gioco — dove la premessa puo' benissimo tornare vera.

Due avvertenze sulla portata di questo risultato, perche' non sono la stessa
cosa: la **disponibilita'** e' confusa da due difetti del materiale (sotto), la
**coincidenza** no. Un rilevatore migliore troverebbe piu' onset, ma li
troverebbe sempre nello stesso posto — ed e' il posto a togliere valore
all'aggancio.

#### Due cose viste guardando l'ingresso del VAD

**Il rilevatore era acceso, non stava rilevando.** Dichiarava parlato l'**87% del
tempo** con otto aperture al minuto. Il fondo si stimava solo mentre si tace —
giusto, perche' una battuta lunga alzerebbe il fondo fino a coprirsi da sola —
ma quella regola da sola si avvita: un fondo fermo tiene acceso il rilevatore, e
un rilevatore acceso impedisce al fondo di muoversi. Sui segnali sintetici della
suite non si vedeva, perche' li' il parlato alterna sempre col silenzio. Con la
guardia (`floor_hold_ms`: oltre quella durata non e' piu' una battuta, e' una
scena diventata rumorosa) si passa a 55,9% e da 22 a 38 prese di parola.

L'eccesso sul caso a ±0,2 s, pero', va da **+16,1% a +18,8%**: il difetto era
vero e andava corretto, ma non era lui a nascondere l'aggancio. Vale la pena
scriverlo perche' l'ordine dei fatti invitava alla conclusione opposta — trovato
un difetto grosso nello strumento, la tentazione e' dare a lui la colpa del
risultato scomodo. La conclusione sull'aggancio e' la stessa **prima e dopo**, ed
e' piu' solida per questo.

**Le registrazioni sono quasi mono.** `corr(L,R)` vale **0,997** su rec1 e 0,932
su rec2, con i lati 23 dB sotto il centro: l'estrazione mid/side non isola
niente, e il VAD riceve l'intero mix invece del solo dialogo. Vale per il banco —
in gioco la cattura loopback e' un'altra sorgente — ma finche' il materiale e'
questo, ogni misura che poggia sulla separazione del centro va letta sapendolo.
Riguarda anche il duck: su un segnale quasi mono, abbassare il centro abbassa
tutto.

### La sessione d'ascolto dal vivo, e i sette difetti che ha trovato

Una giornata di prove su GTA V riprodotto a schermo. Ogni difetto qui sotto e'
stato trovato **dall'orecchio** e poi confermato da un numero: nessuno era
visibile nella suite, e due erano invisibili *per costruzione*.

| difetto | come si sentiva | causa |
|---|---|---|
| profilo sbagliato | testo storpiato, `'Oaai'`, `'Drmrc.Miinzl'` | ROI del file su una cattura da schermo: il ritaglio tagliava i glifi a meta' |
| riquadro stretto | frasi lunghe mozzate in testa **e** in coda | la ROI copriva il 37% della larghezza; il calibratore aveva visto solo battute corte |
| simboli pronunciati | *«va bene barra»* | `/ & + = * @ #` stavano nella lista "serve alla prosodia" |
| voci fantasma | una voce femminile senza sottotitolo | `'11'` passava il filtro sulla lingua: contava gli alfanumerici |
| prima battuta persa | un buco all'ingresso del secondo personaggio | `start_live` scaldava solo `pool.voices[0]`: 1826 ms sulla prima riga di `paola` |
| il mix pompava | *«quando parlano veloce si tagliuzza tutto»* | il duck risaliva e riscendeva nei 120 ms fra due battute: +5,8 dB ogni 160 ms |
| l'ultima parola | *«si ferma a "questa roba stia" e non dice "funzionando"»* | WSOLA perdeva la fine di cio' che comprimeva |

**Il piu' istruttivo e' l'ultimo**, e vale piu' della sua correzione. Il puntatore
di analisi di WSOLA insegue la periodicita' e a ogni passo puo' arretrare; quegli
arretramenti si **sommano**, e a fine corsa non ha mai letto l'ultimo tratto
dell'ingresso. L'overlap-add riempiva il buco con cio' che stava intorno, quindi
la fine non mancava: era **sostituita**. Durata esatta al campione, ampiezza
esatta, intonazione ferma, giro identita' a 0,9999 — ogni misura esistente
guardava *quanto* e nessuna guardava *cosa*.

E il giro identita' non era solo cieco: **premiava il difetto**. Tornava quasi
perfetto perche' la deriva della compressione veniva annullata da quella
dell'allungamento, cioe' un'inversa esatta ottenuta da due errori che si
compensano. Quella prova, da sola, sceglieva l'algoritmo che cancella le parole.
Oggi la prova principale sullo stiramento e' il gruppo `coda`, che mette un tono
riconoscibile in fondo e chiede di ritrovarlo.

Fra spettro e contenuto vince il contenuto: 0,043 su una distanza spettrale
normalizzata resta un numero piccolo, mentre `0,00` vuol dire che una parola non
c'e'.

#### E due cose che si chiedevano senza guardare la risposta

**La fretta si chiedeva a occhi chiusi.** `length_scale` di Piper non e'
proporzionale — sta scritto nel suo stesso modulo — quindi chiedere 1,45 dava
molto meno, e nessuno controllava. Ora l'anello e' chiuso: si misura
l'accelerazione **ottenuta** (`stima / durata`) e il divario corregge la
richiesta successiva. Dal vivo il guadagno impara a chiedere fino a 1,75 per
ottenere 1,39.

**E la pausa si pagava anche in ritardo.** I 120 ms di respiro fra due battute
esistono perche' due battute attaccate suonano come una frase sola; venivano
aggiunti anche quando la successiva era gia' in coda, cioe' silenzio deliberato
mentre si e' indietro di un secondo.

| | inizio giornata | fine |
|---|---|---|
| latenza p50 | 2208 ms | **263 ms** |
| latenza p95 | 8301 ms | **811 ms** |
| arretrato p95 | 7919 ms | **445 ms** |
| compressione WSOLA p50 | 1,350 *(satura)* | **1,067** |
| sforamenti | 39 su 39 | 10 su 39 |

La riga che riassume la direzione presa e' la penultima: **WSOLA e' passato da
fare tutto a fare quasi niente**. La fretta la fa il sintetizzatore, che articola;
lo stiramento resta per la correzione fine, dove non si sente.

## Stato

**F0 — scheletro misurabile** e **F1 — la catena parla**. Cattura dei
sottotitoli, OCR, pool di sei voci italiane, mixer con duck del centro,
tutto montato in `core/pipeline.py` e verificabile con `tools.demo`.

Il banco legge ora **anche il video vero**: `tools/replay.py` monta il dominio
video di F1 per intero su una registrazione, `tools/calibrate.py` ne ricava ROI
e soglie, e `profiles/gtav.json` le tiene. Il banco dello stabilizzatore lo
rigioca su letture gia' registrate, mille volte al prezzo di zero.

Il dominio video produce ora durate credibili — mediana 1,32 s su una fetta dove
le battute vere sono ventisei — ed e' la condizione che mancava per iniziare F2:
la predizione `D̂ = a + b·n_caratteri` si tara su queste durate, e finche' erano
frammenti non c'era niente da tarare.

**F2 — il tempo** e' chiusa. La durata si prevede da `D = a + b·n`, la battuta si
stringe con WSOLA per stare nella finestra del suo sottotitolo, e oltre il limite
si sfora senza mai scartare. Il terzo pilastro previsto dal piano — l'aggancio
all'onset del parlato — e' stato misurato e **non serve su questo gioco**: vedi
sopra.

**La catena gira dal vivo e si ascolta.** `tools/live.py` cattura schermo e
loopback, `tools/session.py` lascia `mix.wav` + `events.jsonl` + `config.json` in
`runs/<data>/`, e `tools/reopen.py` fa il percorso inverso: da un secondo del
WAV alla riga con tutti i suoi numeri. E' quello che ha reso analizzabile ogni
lamentela della sessione d'ascolto invece di lasciarla un'impressione.

Non c'e' ancora: il riconoscimento di *quale* personaggio parla (F3, per ora
bianco e grigio ricevono due voci fisse), l'emozione (F4), e il tasto che marca
una battuta *mentre* la sessione gira — con il gioco a schermo intero il
terminale non ha il fuoco, e `Session.mark` aspetta un modo di premerlo.

Lo stabilizzatore riapriva la stessa battuta piu' volte, e andava sciolto
**prima** di misurare le durate: una battuta riaperta quattro volte da' quattro
durate corte invece di una giusta. Su una fetta di 50 secondi, dove le battute
vere sono ventisei:

| | aperture | letture OCR vuote | OCR p50 |
|---|---|---|---|
| ROI di partenza | 55 | 1109 su 2768 | 223 ms |
| ROI calibrata | 52 | 92 su 1066 | 24 ms |
| abbinamento per somiglianza invece che per posizione | 52 | 92 | 24 ms |
| nucleo del contrasto locale a 11 invece di 63 | 44 | 3 su 1168 | 25 ms |
| due soglie in `find_bands` (il testo decapitato) | 46 | 2 | 17 ms |
| confronto sulle sole lettere | 40 | 2 | 17 ms |
| l'inchiostro saturo non e' testo | 36 | 4 | 16 ms |
| scarto in caratteri invece che in percentuale | **30** | 4 | 17 ms |

Le durate, che sono il dato che serve a F2, passano da una mediana di 0,70 s —
cioe' frammenti — a **1,32 s**, e i frammenti sotto 0,6 s da 19 a 3.

Due ipotesi cadute per strada, e vale la pena averle scritte: la riga *non*
sfugge al classificatore (viene trovata nel 100% dei frame con sottotitolo, a
ogni nucleo provato), e il nucleo del contrasto locale non serviva a trovarla —
serviva a **non trovare le altre**, cioe' le bande di texture, che a 63 erano
0,79 per frame vuoto e a 11 sono 0,08.

### Il riconoscitore non sfarfallava: leggeva testo decapitato

Sembrava rumore dell'OCR. Guardando **ogni singola lettura** invece di quelle
che arrivavano in fondo, si e' visto che le letture della stessa battuta erano
gia' stabili — ed erano stabilmente *sbagliate*, sempre sulle stesse lettere:

| letto | vero | cosa mancava |
|---|---|---|
| `Oaai`, `acauistati`, `fialio`, `near!` | Oggi, acquistati, figlio, negri! | la coda di **g** e **q** |
| `avessl`, `vorrel`, `insleme` | avessi, vorrei, insieme | il punto della **i** |
| `cne` | che | l'asta della **h** |
| `succede.` | succede, | la coda della **virgola** |

Una `g` senza coda **e'** una `a`: il modello non sbagliava, rispondeva
correttamente a un'immagine diversa. Le righe-pixel sotto la linea di base
contengono solo le code di due o tre lettere — tre o quattro pixel — e non
superavano `min_line_fill`, che su una ROI larga 1136 px vale 11 pixel. La
banda si chiudeva sopra le code e il ritaglio arrivava tagliato.

`find_bands` usa ora **due soglie**: la prima apre la banda (robusta al
rumore), la seconda la estende finche' c'e' inchiostro, con un limite che
impedisce a due righe vicine di saldarsi.

| | prima | dopo |
|---|---|---|
| `Oggi recuperiamo veicoli acquistati…` | 0 letture su 61 | **54 su 61** |
| `ma se ne avessi uno vorrei che fosse come te.` | 0 su 66 | **56 su 64** |
| `Toc toc, negri!` | 0 su 29 | **25 su 44** |

### La riga non spariva: veniva scartata perche' passava una macchia viola

`Franklin ha ottenuto il titolo di dipendente del mese.` si riapriva a meta',
con testo **identico** — quindi non era la soglia di somiglianza. Guardando le
letture grezze, otto passate consecutive senza candidate; guardando la ROI in
quelle passate, il sottotitolo era li', perfetto. A rispondere e' stato il
classificatore:

```
t=1260.70  [white  ] luma=253.7  sat=10.0
t=1260.75  [colored] luma=253.7  sat=42.0   <- stessa riga, stesso testo bianco
t=1260.95  [colored] luma=253.7  sat=47.0
t=1261.00  [white  ] luma=253.3  sat=25.0
```

La banda veniva trovata ogni frame, con luminanza da bianco puro; era la
**saturazione di picco** a superare `sat_max` — per via di un oggetto di scena
entrato nella ROI, non di un glifo. La regola "riga con glifi saturi ⇒ scarta la
riga" e' giusta per i suggerimenti, dove il testo *e'* colorato; applicata al
picco puniva il dialogo per colpa dello scenario. In venti minuti scartava **863
righe**, e rileggendole senza i pixel saturi erano quasi tutte dialogo:
`Ehi fratello, che succede?`, `Pensavi che ti avrei preso a calci in culo, eh?`,
`Cazzo, siamo a Vespucci Beach`.

Due ipotesi provate e cadute, che vale la pena aver scritto: le colonne sature
**non** formano una fascia contigua (`run_frac` 0,04 in entrambi i gruppi), e non
stanno **fuori** dalla fila dei glifi (640 righe su 863 le hanno dentro — la fila
di una frase e' larga quasi quanto la ROI, quindi tutto ci cade dentro).

Quello che separa e' la **quota**: ordinando le righe scartate per frazione di
inchiostro saturo, sopra ~0,25 ci sono solo righe-obiettivo — `Scegli una delle
auto`, `Raggiungi ...`, `Segui ...`, dove la parola colorata e' una fetta grossa
di una riga corta — e sotto c'e' il dialogo. Ora i pixel saturi escono dalla
maschera (non sono glifi, e nel ritaglio danno solo fastidio) e la riga e'
`COLORED` solo se erano tanti: `vision.lines.colored` passa da 135 a 6 sulla
fetta.

### Due lettere sbagliate costano il doppio su una battuta corta

`piantaladawwero` contro `piantaladavvero` fa 0,867 e cadeva sotto la soglia di
0,88; le stesse due lettere su una frase di quarantacinque caratteri fanno 0,955
e non la sfioravano. La battuta corta veniva riaperta e quella lunga no, per un
motivo che non ha niente a che vedere con quanto sono diverse: una soglia in
percentuale tollera un numero di errori proporzionale alla lunghezza, mentre
l'OCR sbaglia **una lettera ogni tanto**. Il confronto ora e' in caratteri
(`max_wrong_chars`), e prima ancora sulle sole lettere e cifre — la
punteggiatura a larghezza intera (`！`, `，`) e i glifi spurii in testa (`I`,
`——`, `→`) sono cio' che l'OCR riproduce meno volentieri, e contavano quanto una
lettera vera.

Restano le battute lette in pochi frame: una comparsa in dissolvenza da'
`'Ciau, Lalliai:'` per `'Ciao, Lamar!'`, e li' il testo e' davvero diverso — tre
delle 30 aperture sono quella sola battuta.

### Le soglie non generalizzano alla seconda registrazione

Tutti i numeri qui sopra vengono da **una** registrazione. La seconda, calibrata
col suo profilo (`profiles/gtav2.json`), dice che non bastano:

| | rec1 (27 min) | rec2 (9 min) |
|---|---|---|
| frammenti sulle aperture | 26% | **63%** |
| letture OCR vuote | 0,3% | **49%** |
| righe scartate come colorate | 6 | **2021** |

La ROI e' giusta — i ritagli mostrano il testo perfettamente leggibile — quindi
non e' il caso della moquette. A produrre il disastro e' la **scena dentro la
banda dei sottotitoli**: in rec2 una striatura luminosa attraversa quella fascia
e fa due danni distinti. Da sola apre bande alte 12-17 px che l'OCR paga (16 ms)
per non leggere niente; sopra il testo si salda alla sua banda e ne corrompe il
ritaglio, ed e' il motivo per cui la prima lettura e' giusta
(`'E questi li consideri obiettivi raggiunti?'`) e quella che le subentra e'
storpiata (`'1、Eequestliconsiderobietiragiunt?'`).

Due rimedi provati e misurati, **nessuno dei due adottato**:

- ROI piu' bassa: toglie bande spurie ma anche testo vero (frame con dialogo dal
  68% al 65%), quindi non e' l'altezza della ROI;
- `min_line_height` piu' alto: a 20 px ferma il 29% delle bande vuote di rec2 ma
  perde il 5,2% del testo di rec1. Con "nessuna battuta scartata" fra i requisiti,
  e' un cambio che costa piu' di quanto rende.

La pista buona e' un'altra, e viene dal guardare le bande vuote *alte*: sono
macchie di scena che occupano **l'intera altezza della ROI** (77 px su 77),
mentre una riga di testo li' ne misura 38. Una banda alta quanto tutta la ROI
non e' una riga — e' la maschera che ha trovato qualcosa che attraversa tutto.
Il tetto pero' va misurato insieme al caso delle due righe fuse in una banda
sola, che e' alto uguale ma il testo ce l'ha.

Piano completo: `C:\Users\filde\.claude\plans\progetto-so-che-ci-fancy-rossum.md`
