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
.\.venv\Scripts\python.exe -m tools.selftest              # suite completa (400 verifiche)
.\.venv\Scripts\python.exe -m tools.selftest ring config  # un gruppo solo
.\.venv\Scripts\python.exe -m tools.demo                  # scena finta completa -> runs\demo_mix.wav
.\.venv\Scripts\python.exe -m tools.demo --no-duck        # la stessa, per sentire cosa fa il duck
.\.venv\Scripts\python.exe -m tools.say --pool            # ascoltare le voci
.\.venv\Scripts\python.exe main.py --dump-config
```

Sulla registrazione, **in quest'ordine** — il primo comando non e' facoltativo:

```powershell
.\.venv\Scripts\python.exe -m tools.replay gameplay.mp4 --peek 8      # guardare la ROI
.\.venv\Scripts\python.exe -m tools.calibrate gameplay.mp4 --write profiles\gtav.json
.\.venv\Scripts\python.exe -m tools.replay gameplay.mp4 --profile gtav --start 1240 --end 1290
```

Per lavorare sullo **stabilizzatore** senza ri-pagare l'OCR a ogni tentativo, si
registra una volta il flusso di letture e poi lo si rigioca:

```powershell
.\.venv\Scripts\python.exe -m tools.replay gameplay.mp4 --profile gtav --start 1240 --end 1290 `
    --dump-reads runs\reads.jsonl                                    # una volta, ~55 s
.\.venv\Scripts\python.exe -m tools.retrack runs\reads.jsonl --profile gtav          # ~50 ms
.\.venv\Scripts\python.exe -m tools.retrack runs\reads.jsonl --profile gtav --raw 1269.5 1270.3
```

`--raw` elenca **ogni** alimentazione del tracker, comprese quelle che ha
scartato: giudicare lo stabilizzatore da cio' che ne esce e' chiedere
all'imputato di scegliere le prove.

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
regola sta nel `CLAUDE.md`: ancorare il testo con una maschera che pretende uno
stacco di 60 e poi *misurarne* lo stacco da' 60,15 — la misura non poteva
esprimere altro numero; ancorarlo invece su "bianco e acromatico" da' −2,3,
perche' nella ROI finiscono muri chiari e carrozzerie bianche. Serve il top-hat
morfologico, che vede la *sottigliezza* di un tratto e non la sua luminosita'.

## Stato

**F0 — scheletro misurabile** e **F1 — la catena parla**. Cattura dei
sottotitoli, OCR, pool di sei voci italiane, mixer con duck del centro,
tutto montato in `core/pipeline.py` e verificabile con `tools.demo`.

Il banco legge ora **anche il video vero**: `tools/replay.py` monta il dominio
video di F1 per intero su una registrazione, `tools/calibrate.py` ne ricava ROI
e soglie, e `profiles/gtav.json` le tiene. `tools/retrack.py` rigioca il solo
stabilizzatore su letture gia' registrate, mille volte al prezzo di zero.

Il dominio video produce ora durate credibili — mediana 1,32 s su una fetta dove
le battute vere sono ventisei — ed e' la condizione che mancava per iniziare F2:
la predizione `D̂ = a + b·n_caratteri` si tara su queste durate, e finche' erano
frammenti non c'era niente da tarare.

Non c'e' ancora: l'aggancio della durata al sottotitolo (F2), il riconoscimento
di *quale* personaggio parla (F3, per ora bianco e grigio ricevono due voci
fisse), l'emozione (F4) e la cattura dal vivo da schermo e scheda audio.

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

Piano completo: `C:\Users\filde\.claude\plans\progetto-so-che-ci-fancy-rossum.md`
