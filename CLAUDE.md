# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Cos'e'

Doppiaggio italiano **dal vivo** dei sottotitoli di un videogioco. I sottotitoli
di GTA V sono gia' in italiano — **non c'e' nessuna traduzione in questa
catena**: si legge il testo a schermo con l'OCR, si capisce chi sta parlando
dall'audio, si sintetizza con una voce assegnata a quel personaggio e si mixa
sopra il gioco abbassando l'originale.

`docs/architettura.md` ha l'architettura estesa e la grammatica dei sottotitoli. **Non
leggerlo per intero**: costa e quasi mai serve.

## La memoria di questo progetto e' il grafo

In `graphify-out/graph.json` c'e' la mappa della codebase, gia' costruita. Per
qualunque domanda architetturale — dove sta X, cosa rompo se tocco Y, chi chiama
cosa — si interroga quello **prima** di partire a grep:

```
graphify query "<domanda>"
```

Costruirlo e' caro (estrazione su tutti i file), interrogarlo no. Si aggiorna con
`/graphify . --update` dopo modifiche grosse, **non a ogni task**.

## Le due cartelle sorelle non si guardano

`..\gta-redub-live` e `..\gta-redub-v2` sono **bozze fallite**, dichiarate tali
dall'utente. Non si leggono, non si copiano, non si citano le loro misure. Se
serve una logica che li' esisteva, si riscrive e si rimisura qui. (I loro venv
sono un'altra cosa: `.venv-f5` ha torch e torchaudio ed e' utile per un
esperimento GPU buttato via, senza avvicinare torch a questo venv.)

## Comandi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest              # 1164 verifiche
.\.venv\Scripts\python.exe -m tools.selftest speaker pool # gruppi scelti
.\.venv\Scripts\python.exe -m tools.selftest -v           # con i verdi in chiaro

# la catena intera su una registrazione, senza gioco. Scrive dub.wav,
# events.jsonl, speaker.jsonl (la traccia) e con --mp4 il video montato.
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav `
    --start 1240 --end 1340 --set vision.ocr_backend=oneocr --mp4

.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella> [secondo]
.\.venv\Scripts\python.exe -m tools.recluster runs\<cartella>\speaker.jsonl --profile gtav
.\.venv\Scripts\python.exe -m tools.ui --profile live --loopback voicemeeter --set vision.ocr_backend=oneocr
# Nella finestra: **Scegli finestra** (il gioco) -> Seleziona area -> Avvia.

# la prova d'ascolto, con i controlli fatti prima (venv, cattura, Ollama e il suo
# modello) e la configurazione stampata: la riga sotto e' lunga otto opzioni, e
# copiarla male non da' errore — da' una prova fatta con un'altra configurazione.
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 [-Traduci] [-Motore piper] `
    [-Set translate.background_mode=riquadro]   # -Set e' ripetibile, e viene stampato

# come si vedrebbe l'overlay, senza accendere il gioco: stesso pittore del vivo.
# `--frames N` sputa N PNG invece del video, e si guardano subito.
.\.venv\Scripts\python.exe -m tools.overlay_mp4 testGameplayFattoDaMe.mp4 runs\<passata> `
    --profile gtav --offset 1240 --start 1240 --end 1285 --out runs\ov\overlay.mp4

# dal vivo con traduzione, grafica e audio (serve `ollama serve` acceso)
.\.venv\Scripts\python.exe -m tools.ui --profile live --loopback voicemeeter `
    --set vision.ocr_backend=oneocr --set tts.backend=kokoro --set tts.device=cuda `
    --set translate.enabled=true --set translate.backend=ollama `
    --set translate.source=it --set translate.target=en

# i banchi specializzati, ognuno risponde a una domanda sola
.\.venv\Scripts\python.exe -m tools.bench_cpu --backend supertonic    # rallenta sui PC vecchi?
.\.venv\Scripts\python.exe -m tools.bench_translate --parolacce       # il traduttore dice cio' che c'e' scritto?
.\.venv\Scripts\python.exe -m tools.bench_correct --censimento        # cosa c'e' davvero da correggere nell'OCR?
```

- venv: `.venv` (Python 3.11.9), **sempre invocato per esteso**. Si ricostruisce
  con `pip install -r requirements.txt`, e quel file va letto prima di toccare
  l'ambiente: monta **`onnxruntime-gpu` e non `onnxruntime`**, che e' una scelta
  di architettura (senza GPU, Kokoro non e' vivibile) e i due pacchetti **non
  convivono**. Non c'e' `pyproject.toml` e non c'e' linter.
- **Non c'e' pytest.** La suite e' `tools/selftest.py` (piu' `selftest_audio.py` e
  `selftest_vision.py`); un gruppo si esegue anche da codice:
  `from tools.selftest import test_ring, Check; c=Check(); test_ring(c); c.report()`.
  Un gruppo nuovo si aggiunge al dizionario `GROUPS` in fondo a `selftest.py`.
- `models/`, `runs/` e le registrazioni sono materiale della macchina: gitignorati.

## L'architettura, nei pezzi che non si capiscono da un file solo

**Due domini, due thread, un solo punto di incontro** (`core/pipeline.py`). Il
dominio video (30 Hz) decide *cosa* si dira' e *quando*; il dominio audio (blocchi
da 10 ms) versa cio' che e' stato programmato e mixa. `on_frame` legge, decide,
sintetizza e **programma**; `on_audio` esegue. Il mixer non chiama mai il
sintetizzatore.

**Due tempi, mai uno.** `Stage.clock` e' il tempo del *media* (virtualizzabile,
serve a timbrare gli eventi); il *costo* si misura sempre a muro con
`perf_counter`. Confonderli fa risultare gratis ogni stadio durante il replay —
la misura non diventa imprecisa, diventa incapace di esprimere la risposta.

**Chi parla ha due porte, e non e' un'ottimizzazione** (`listen/speaker.py`).
`scegli` e' la porta veloce: la usa chi deve parlare adesso, con il poco parlato
disponibile, e **non crea mai un personaggio**. `impara` e' la porta lenta: a
battuta finita, sul ritaglio intero, aggiorna il centroide e semmai iscrive
qualcuno. Una soglia sola non esiste — quella che non inventa personaggi a 0,3 s
non ne riconosce di nuovi a 2 s. Le identita' si **fondono** quando due centroidi
si avvicinano abbastanza (vince chi ha piu' battute, cosi' non cambia voce chi ha
gia' parlato molto), e sotto `name_min_score` non si fa nessun nome: si parla con
una voce neutra fuori dal pool, che dichiara "non lo so ancora" invece di
mentire.

**L'anello audio ha una linea temporale sua** (`_marche` in `core/pipeline.py`).
Ogni blocco lascia una marca `(campioni scritti, che ora era)`, e il tempo si
converte in campioni interpolando fra le marche. Non e' un dettaglio: dal vivo il
thread audio perde campioni, e qualunque schema che deduca la posizione dal solo
conteggio deriva — misurato, 11 ms al secondo, fino a spostare di sette decimi la
finestra con cui si riconosce chi parla.

**Il tempo della battuta** (`fuse/timing.py`): `D = a + b*n` prevede quanto
restera' a schermo il sottotitolo, e da li' esce il budget. La previsione e'
debole per costruzione (la durata la decide il ritmo della conversazione, non la
lunghezza del testo), quindi chi la usa deve essere pronto a essere smentito a
meta' battuta — ed e' per questo che la correzione in volo con WSOLA e' la parte
portante e non un ornamento. **Il ritardo costante non e' un debito**:
`accepted_delay_ms` e' quanto se ne accetta senza rincorrerlo, perche' chiedere a
ogni riga di recuperare un ritardo che tornera' identico significa comprimerle
tutte.

**Chi accelera cosa.** Il sintetizzatore che parla piu' svelto **articola**;
WSOLA schiaccia e mangia le fini delle parole. Quindi la fretta si chiede prima
al motore (`tts.native_rate_max`) e solo il residuo va a WSOLA
(`timing.rate_max`). Ogni backend dichiara il **proprio** passo
(`chars_per_second`, nell'unita' di `spoken_length()`) e il proprio tetto: un
numero solo per tutti i motori e' gia' costato due sessioni.

**Tre motori, un solo posto dove si costruiscono** (`speak.base.make_tts`). Prima
la costruzione era ripetuta in sei file e ognuno passava un sottoinsieme diverso
dei parametri: `dub.py` non passava `steps` e `speed`, quindi il banco misurava
una configurazione diversa da quella che diceva di misurare mentre il vivo ne
usava un'altra. La factory prende la sezione `tts` **intera**, e un nome
sconosciuto **solleva** invece di ripiegare in silenzio su Piper — perche' un
ripiego silenzioso li' vuol dire consegnare un doppiaggio plausibile fatto dal
motore sbagliato, con i log verdi.

|  | sintesi p50 | latenza p50 (banco) | car/s | tetto integro | dove gira |
|---|---|---|---|---|---|
| **piper** (default) | 45 ms | 589 ms | 14,8 | — | CPU |
| **supertonic** | 210 ms | 752 ms | 14,3 | 1,10 | CPU |
| **kokoro** | 299 ms | 932 ms | 12,9 | **1,30** | **CUDA** |
| **qwen** | 3,1 s | non usabile | 10,6 | — | CUDA |

**Il quarto motore e' stato tolto, e la misura che lo ha tolto va tenuta.**
`speak/backends/qwen.py` non c'e' piu'. Aveva la cosa che nessun altro motore qui
ha — le voci come **descrizioni** a parole, quindi un pool illimitato — e lo
streaming funzionava davvero: primo campione a 257 ms invece di 4820, blocchi
concatenati identici alla battuta intera, zero underrun sul banco.

Dal vivo, su questa 4060, tre soglie dichiarate **prima** della prova e tutte e
tre sfondate:

| criterio | soglia | misurato dal vivo |
|---|---|---|
| `mix.underrun` | 0 | **5415** |
| latenza p50 | < 2,5 s | **26,7 s** al primo campione |
| compressione | < 1,450 | **1,450 a ogni percentile** |

Su 65 battute lette, **25 hanno prodotto audio**: quaranta non hanno mai parlato,
e la coda arrivava a settantacinque secondi. All'ascolto: parole sminuzzate e
contenuto scollegato dal video.

**Perche' non e' un problema di hardware, ed e' la parte che conta.** Il costo per
frame e' banda di memoria, quindi una scheda da ~670 GB/s in su farebbe rientrare
la coda — quello si compra. Ma `dub.rate_x1000` stava a **1450 al p50, al p95, al
p99 e al massimo**: ogni singola battuta compressa al tetto, e 1,45 e' ben oltre
l'1,3 dove le consonanti spariscono. Quel numero non dipende dalla GPU: dipende
dal fatto che il motore parla **la meta'** di Piper (8,4 car/s contro 18,3) e
produce il 157% del parlato che la scena ha tempo di contenere. Su una 4090
sarebbe identico, solo puntuale. Si comprerebbe una scheda per sentire la stessa
voce schiacciata.

**Cosa resta, ed e' parecchio.** Lo streaming non era sprecato: il protocollo sta
in `speak/base.py`, il mixer sa tenere una battuta **aperta** con il suo cuscino
(`mix.prebuffer_ms`), la catena sa programmare prima di avere l'audio, e la
verifica `streaming` gira su un motore finto. Chi montera' il prossimo motore
autoregressivo eredita tutto invece di riscriverlo — e trova gia' scritto il
difetto che il banco non puo' vedere: **una battuta non si comincia a suonare
finche' non ha un cuscino di campioni pronti**, se no si sente a goccia.

E la lezione sul come si sceglie un motore: la domanda decisiva non era la
latenza, era **quanto parlato produce per secondo di scena**. Quella si misura
sul banco in un minuto, e avrebbe risparmiato tutto il resto.

**Ma il riferimento vero e' il vivo, ed e' gia' in `runs/`.** Una quarantina di
sessioni, rilette con `tools/reopen runs\<timestamp>` — quel comando legge le
sessioni dal vivo, non solo le prove di banco, e nessuno se lo ricorda mai:

| dal vivo | sintesi p50 | attesa in coda | **totale p50** | compressione |
|---|---|---|---|---|
| piper | ~50 ms | ~620 ms | **~670 ms** | 1,00–1,05 |
| supertonic | 315–586 ms | 900–1245 ms | **1280–1873 ms** | 1,250 (**al tetto**) |
| kokoro | 257 ms | 887 ms | **1150 ms** | 1,226 |

Due cose che solo questa tabella dice. SuperTonic sta **incollato al tetto di
compressione** in quattordici sessioni su sedici, cioe' WSOLA lavora sempre al
massimo; Kokoro no, e infatti articola. E la sintesi dal vivo di Kokoro costa
**meno** che sul banco (257 contro 299), il che da solo basta a diffidare di
qualunque preventivo fatto senza il gioco acceso.

**Kokoro ha senso solo su GPU, e questo riapre un vincolo dichiarato.** Su CPU
costa 725 ms a battuta contro i 207 su CUDA — non vivibile. Quindi `.venv` monta
`onnxruntime-gpu` (superset: ECAPA e rapidocr restano su CPU), e la sintesi
adesso **compete con il gioco per la GPU**, che era esattamente il motivo per cui
Piper e' default. Il prezzo e' 1128 MB di VRAM su una 4060 da 8 GB. `tts.device`
vale `cpu | cuda | auto` e **lo legge solo Kokoro**; era un campo dichiarato e
non letto da nessuno, come `max_ocr_hz` prima di lui.

Kokoro ha **due sole voci italiane**, come Piper: oltre il secondo personaggio si
torna comunque a spostare i semitoni. E il quantizzato (92 MB) e' **quattro volte
piu' lento** del fp32 su CPU, non piu' veloce.

**Con un motore veloce, il collo di bottiglia si e' spostato.** I 1150 ms di
Kokoro dal vivo si scompongono in **500 ms di `speaker.decide_after_ms`** (l'attesa
per sapere chi parla), ~390 ms di coda e 257 ms di sintesi: il riconoscimento
costa **il doppio della sintesi**. Con SuperTonic a 586 ms non era vero, ed e' il
motivo per cui la tabella che sconsiglia di abbassare quei 500 ms — misurata su
SuperTonic e sul banco — non risponde piu' alla domanda di adesso. Chi vuole
guadagnare latenza guardi **li'**, non il sintetizzatore. Il prezzo dichiarato di
abbassarli e' che si sbagli piu' spesso a dire chi parla, e quello lo giudica
l'orecchio.

## I pezzi aggiunti dopo, e cosa fa ciascuno

Quattro moduli che non c'erano quando questo file e' stato scritto. Sono tutti
**spenti di default**, perche' nessuno serve a GTA V in italiano: servono a farci
girare un altro gioco o un'altra lingua.

**`translate/`** — tradurre il sottotitolo. Quattro backend: `locale` (Argos,
leggero), `llm` (Gemma 3 1B in-process su CPU), `ollama` (TranslateGemma, fuori
dal venv) e `google`. Due cose non ovvie: **si traduce prima di stimare i tempi**,
perche' `chars_per_second` va applicato al testo che verra' *detto*; e se la
traduzione fallisce **si tiene l'originale**, perche' una battuta nella lingua
sbagliata e' un difetto e una battuta muta e' un buco.

E la domanda che su questo materiale viene **prima della qualita'**: il modello
dice cio' che c'e' scritto? Misurato su sei battute volgari — google 6/6,
TranslateGemma **0/6** col suo template, 2-3/6 chiedendo esplicitamente di non
ammorbidire. Un modello che riscrive «Get the fuck out of my car, asshole» in
«Esci immediatamente dalla mia macchina, idiota» consegna un doppiaggio che dice
un'altra cosa, e nessun contatore lo mostra.

**`vision/label.py`** — chi parla, quando lo scrive il gioco. Sette formati
pronti piu' una regex. Vale mezzo secondo: cadono sia l'attesa di
`decide_after_ms` sia il calcolo dell'impronta. Il nemico sono i falsi positivi,
perche' ognuno **crea un personaggio** e gli brucia una voce del pool: la guardia
forte e' l'elenco dichiarato dei nomi. E con un nome stabile la voce si puo'
ricordare fra sessioni (`runs/cast.json`) — senza, la voce non e' del personaggio,
e' del *turno*.

**`vision/correct.py`** — correggere gli artefatti dell'OCR. Il correttore
**propone**, il `Revisore` decide: una parola italiana non gli viene nemmeno
mostrata, i nomi propri nemmeno, e si sceglie **fra candidati** invece di
generare. Spento, e con ragione misurata: il guadagno massimo e' **una parola su
settanta** (delle 1230 fuori dal lessico su 19146, 527 sono nomi propri e il
resto e' onomatopee, forme vere non elencate e frammenti di HUD).

**`capture/finestre.py` + il backend `finestra`** — si cattura **una finestra
sola**, non lo schermo. E' la scelta che viene prima di tutte le altre:
catturando lo schermo, nel fotogramma che va all'OCR finisce anche cio' che sta
davanti al gioco — comprese le nostre finestre — e il programma legge se stesso
(misurato: il 100% dei pixel dell'overlay). Con `CreateForWindow` no: verificato
mettendo sopra alla finestra catturata una finestra rossa che la copriva a
meta', nel fotogramma ne e' arrivato lo **0,000**; e con la catena intera, zero
righe lette che fossero nostre su quattro.

Da qui discendono tre cose che prima erano problemi separati: l'overlay non ha
piu' bisogno di essere nascosto alle catture (quindi **chi registra lo vede**);
la ROI e' relativa alla finestra, quindi se il gioco si sposta il sottotitolo lo
segue; e non c'e' niente da ritagliare. Il rettangolo e' quello **cliente**
(`GetClientRect` + `ClientToScreen`) e non quello della finestra: WGC consegna il
contenuto senza bordi, e i sette pixel di differenza sono di quanto l'overlay
cadrebbe spostato.

**E se si cattura lo schermo, se ne prende solo la fascia che si legge**
(`capture.solo_roi`, acceso di serie). Di un fotogramma 2560x1440 si guarda una
striscia alta il 5% e si paga tutto il resto: `mss` costa **32,4 ms** per lo
schermo intero contro **11,7** per la fascia col margine di serie, e a 30 Hz il
giro dura 33. Non e' un risparmio astratto — provato sulla stessa scena, 60
secondi per parte:

| | letture | sottotitoli | battute |
|---|---|---|---|
| schermo intero | 884 (**14,7 Hz**) | 30 | 28 |
| solo la fascia | 1193 (**19,9 Hz**) | **35** | **34** |

Cinque sottotitoli in piu' letti, perche' il lettore ha bisogno di frame
**consecutivi** per confermare una riga: meta' del ritmo non costa meta' delle
letture, costa le righe corte.

Tre cose che questo pezzo non poteva sbagliare, e che sono tutte di
**posizione**. I pixel si reincollano in una tela grande come lo schermo, perche'
ROI, aree e ritaglio dell'overlay sono in coordinate del fotogramma intero e
consegnarne uno piu' piccolo vorrebbe dire cambiare quel sistema in cinque posti
— dove il primo che se ne dimentica legge il punto sbagliato **senza errore**.
Si prende **l'unione** delle aree e non la prima, se no le altre diventano nere
in silenzio. E la fascia **segue l'area**: spostando il rettangolo col mouse a
sessione accesa la cattura si riapre, se no si leggerebbe il nero e a schermo non
succederebbe piu' niente.

Il margine attorno (`capture.roi_margin`, 0,08) non e' prudenza: l'overlay sfoca
i pixel intorno alla riga e **cresce verso l'alto** quando il tradotto occupa piu'
righe dell'originale. Fuori dalla fascia troverebbe nero.

E il campo `region` di `make_screen` c'era **da sempre e non lo passava
nessuno**: ottavo campo di questa forma in questo progetto.

**`ui/overlay.py`** — il sottotitolo tradotto disegnato sopra il gioco. Dal vivo
il fotogramma non passa da noi, quindi serve una finestra: senza bordi, sempre in
primo piano, con i clic che la attraversano e senza rubare il fuoco — che in molti
giochi vuol dire mettere in pausa.

**E fuori dalla cattura, che viene prima di tutto il resto.** La nostra finestra
sta sullo schermo, e lo schermo e' cio' che diamo all'OCR: misurato, **il 100%**
dei suoi pixel finiva nel fotogramma catturato, con `mss` e con `dxcam`. L'OCR
smetteva di leggere il gioco per leggere noi, e le righe sparivano.
`WDA_EXCLUDEFROMCAPTURE` porta quel numero a **0%**. Non e' una rifinitura: senza,
niente di quello che c'e' a monte funziona, e il difetto sembra dell'OCR.

**Si cancella la scrittina, non il riquadro.** Si tocca solo l'inchiostro delle
righe che l'OCR ha letto, una per riga; tutto il resto della finestra e' un buco
trasparente (colore-chiave) da cui si vede il gioco intatto. E la domanda giusta
non era «rendere illeggibile» ma **«far sembrare che quel sottotitolo non ci sia
mai stato»**, perche' sopra ci va il nostro: confrontati sulla stessa riga vera,
sfocare la striscia lascia una fascia grigia, sfocare i soli glifi li lascia
leggibili, il rettangolo e' una macchia — **ricostruire lo sfondo** (il modo
`cancella`) la fa sparire.

E il come conta quanto il cosa: si ricostruisce con **un'apertura e una
chiusura**, non con `inpaint`. Stesso risultato all'occhio, **0,15 ms contro
16,3** — e quei sedici millisecondi sono esattamente cio' che permette di rifare
la cancellatura a ogni fotogramma invece di congelarla. L'apertura toglie il
chiaro sottile (l'asta del glifo), la chiusura toglie lo scuro sottile (il
contorno nero, che l'apertura lascia indietro e che da solo si legge ancora).

**Misura e colore del testo si copiano dal gioco**, e nessun numero e' scritto a
mano: `font_frac=0` e `color=""` vogliono dire «come il gioco» e sono i default.
Un carattere scelto da noi e' sbagliato per costruzione, perche' ogni gioco
scrive i sottotitoli come vuole.

**E la misura e' sulla larghezza, non sull'altezza — la differenza e' un
quarto.** Confrontare l'altezza della banda con l'altezza dell'inchiostro di
`Ag` chiede un carattere alto quanto una riga intera per ottenere delle sole
maiuscole: circa il 40% troppo grande, e a schermo si vedeva. Si prende invece
**il testo che l'OCR ha letto**, lo si disegna e si cerca il corpo in cui occupa
la stessa larghezza — stesse lettere, stessa grandezza, nessuna conversione fra
due misure diverse. In piu' regge con un carattere di forma diversa da quello
del gioco: GTA V ne usa uno stretto, e chiedere la stessa *altezza* ad Arial
darebbe una riga molto piu' larga dell'originale. La verifica e' un andata e
ritorno: si disegna un sottotitolo finto a 26 punti e si devono ritrovare 26.

Della taglia si tiene la **mediana** delle battute viste (`MisuraCarattere`): un
gioco non cambia taglia da solo, quindi una taglia che balla e' rumore della
misura — la dissolvenza con cui il sottotitolo compare, e l'OCR che legge una
parola in piu' o in meno.

**Geometria decisa una volta, pixel aggiornati** (`Sostituzione`). Sono due
difetti opposti, visti tutti e due a schermo. Ridisegnando tutto a ogni
fotogramma il riquadro veniva ricalcolato da bande leggermente diverse: il testo
tremava, cambiava taglia e nei fotogrammi di dissolvenza spariva del tutto — un
sottotitolo compare, sta fermo, sparisce. Congelando anche i pixel, la toppa che
cancella la riga italiana restava quella del primo fotogramma e diventava un
rettangolo di immagine vecchia mentre la scena si muove. Quindi taglia, colore,
posizione e a-capo si decidono all'inizio; la cancellatura si rifa' a 10 Hz, e la
tela copre **tutta la fascia** perche' mentre la nostra battuta e' a schermo il
gioco e' spesso gia' passato alla riga dopo (la voce arriva un secondo e mezzo
dopo il sottotitolo, sempre).

**Dove sta scritto il sottotitolo lo dice il lettore, non chi disegna.** Il
riquadro si ricercava nei pixel (`inchiostro()`) **nell'istante in cui esce la
battuta doppiata**, cioe' 2310 ms dopo la lettura: la scena si e' mossa e
l'originale spesso non c'e' piu'. Cercando testo dove non ce n'e' si trova
scenario, e nel log dell'utente il riquadro passava da `1233x60` a **`1515x390`**
— l'intera fascia d'analisi per una riga da 45 px — col raggio della sfocatura a
55,8 invece di 12. Adesso `SpokenLine.boxes`/`ink` portano a valle i rettangoli e
la tinta delle righe **che l'OCR ha letto**, misurati sul fotogramma in cui il
sottotitolo c'era; `inchiostro_da_box()` li usa e `inchiostro()` resta il ripiego.
Gli stessi campi finiscono in `events.jsonl`, quindi **vivo e MP4 prendono la
geometria dalla stessa fonte** invece di avere ognuno il suo rilevatore.

**E una riga di testo si salda a cio' che ha attorno.** Su una scena chiara
`find_bands` non affianca la riga al chiaro vicino: ci si fonde — misurato, una
banda alta **186 px che conteneva** un sottotitolo da 45. Da qui tre cose. La
banda ancora si sceglie per **vicinanza al centro dell'area** e non per larghezza
(elegge la macchia) ne' per altezza minima (scarta il sottotitolo e tiene il
riflesso: provato, riquadro stretto messo dove il testo non c'era). L'altezza di
riferimento — da cui escono raggio, margine e tetto del riquadro — e' la mediana
delle bande tenute **limitata dal corpo del carattere**, che si ricava dalla
larghezza e quindi non guarda l'altezza: cosi' una saldatura alza il riquadro ma
non il raggio. E il tetto sul riquadro e' duro, perche' una guardia che dipende
da un'euristica non e' una guardia.

**Ma la causa a monte e' l'area disegnata a mano.** Con `respiro = 0.6*rh`, un
rettangolo alto un sesto dello schermo da' una fascia di 391 px per una riga da
45, e in quello spazio ci sta mezza scena. Nessun filtro disfa una saldatura;
stringere l'area si' — la UI adesso lo dice sopra 0,12.

**Il blur non puo' essere a ritardo zero, e la modalita' che lo e' esisteva
gia'.** Far vedere pixel del gioco vuol dire **copiarli** — cattura, nostro
processo, Tk, compositore — e quella catena ha un pavimento. Verificato che il
compositore non lo puo' fare al posto nostro: su Windows 11 26200
`ACCENT_ENABLE_BLURBEHIND` e `ACCENT_ENABLE_ACRYLICBLURBEHIND` **tingono e
basta**. La misura che lo dice mette dietro righe da un pixel **piu'** uno
scalino chiaro/scuro — una sfocatura toglie le prime e conserva il secondo, un
riempimento distrugge tutti e due: lo scalino passa da 99,9 a 3,8 e 9,5, col
colore-chiave e senza.

`background_mode="riquadro"` invece il ritardo non ce l'ha **per costruzione**:
una tinta piatta non ha struttura da mostrare in ritardo. Con
`translate.background` vuoto (il default) il colore e' la **mediana** dei pixel
coperti, ripresa a ogni rinfresco — la mediana e non la media, perche' la riga
bianca da coprire tirerebbe la media proprio verso cio' che si vuole togliere.
E' la stessa scelta di RSTGameTranslation ("Auto Set Overlay Background Color").

**E il ritardo che resta si misura**: `overlay.ritardo` dice quanto e' vecchio il
ritaglio quando arriva a schermo. Misurato dal vivo, **p50 20-23 ms, p95 39,
max 70**.

**`core/onnx.py`** — la porta unica per aprire una sessione ONNX, che esiste per
la riga `preload_dlls()`. Si veda la regola piu' sotto.

## Banco e vivo: la cosa che costa di piu' capire

`tools/dub.py` fa girare **la stessa identica catena** su una registrazione:
stesso `DubPipeline`, OCR vero, audio vero nell'anello, impronta vera, sintesi
vera, mixer vero, e la causalita' e' rispettata — la pipeline non vede mai il
futuro. Non e' una simulazione.

**Ma il banco regala il tempo.** Con l'orologio virtuale la sintesi costa zero e
nessun frame viene mai saltato. Da qui una lista di difetti che il banco **non
puo' esprimere**, e che sono stati trovati tutti dal vivo:

- il ritaglio veloce finiva a `clock.now()`, un istante per cui l'audio non era
  ancora stato catturato; `RingBuffer.read_from` **tronca in silenzio**, quindi
  l'impronta si calcolava su 150 ms creduti 700. Sul banco impossibile, perche'
  `dub.py` versa l'audio di un pacchetto **prima** di passarne il frame;
- l'attesa prima di decidere era sull'orologio invece che sull'audio: le due cose
  coincidono sul banco e divergono dal vivo;
- la sintesi dentro il thread video (300-600 ms con SuperTonic) rende irregolare
  il flusso di frame, e il lettore di sottotitoli e' costruito su frame
  *consecutivi*: da li' battute non lette e doppioni da frammento.

`--tempo-reale` somma il costo del lavoro al tempo del media e salta i frame
arretrati. **Serve a confrontare, non a preventivare**, e la differenza e'
misurata: sul tempo **assoluto** sovrastima di circa il doppio (Piper 1372 ms
contro i ~670 veri, Kokoro 1949 contro 1150, SuperTonic 2414 contro 1300). Il
motivo e' che li' decodifica, OCR e sintesi si contendono lo stesso processo
mentre dal vivo l'OCR sta in un processo figlio e il thread audio e'
indipendente. Il **divario fra due motori** invece lo predice bene: +577 ms
previsti fra Kokoro e Piper, +480 misurati. Anche sul riconoscimento e'
pessimista, per la stessa ragione.

*(Una versione precedente di questa riga diceva che sul tempo era fedele, «842 ms
contro 951». Quel confronto e' stato rifatto su tutti e due i motori e non
regge: chi ci si e' fidato ha preventivato Kokoro al doppio del suo costo vero.)*

**Ma «predice bene i divari» vale per i motori, non per le architetture, e la
differenza e' esattamente il meccanismo della modalita'.** `--tempo-reale`
addebita all'orologio del media il tempo speso dentro `on_frame`. Un cambiamento
che *sposta lavoro fuori da `on_frame`* si vede quindi premiato due volte: una
perche' il thread video torna libero, e una perche' quel costo smette di essere
addebitato — e la seconda meta' dal vivo non esiste. Misurato spostando la
sintesi in un thread suo: il banco prometteva **-745 ms** su SuperTonic e -612 su
Piper; dal vivo, stessa scena, **1300 -> 1410 ms**, cioe' niente. Prima di
credere a un divario misurato qui, chiedersi se il trattamento tocca proprio la
quantita' che la modalita' manipola.

Il controllo che lo aveva gia' detto, e che non era stato ascoltato: **Piper
guadagnava il 43%** con 51 ms di sintesi da nascondere, piu' di SuperTonic che ne
ha 398. Un rimedio che giova di piu' a chi ha meno da guadagnare non sta agendo
per il motivo che gli si attribuisce.

**Gli strumenti per confrontarli.** Ogni prova — banco e vivo — scrive
`speaker.jsonl` con una riga per battuta e venticinque campi: chi parla, con che
punteggio, quanto durava il ritaglio, che voce, quanta fretta chiesta e quanta
ottenuta, WSOLA, sintesi, coda, latenza. E' per battuta e **non per frame** di
proposito: scrivere dentro il dominio audio farebbe perdere campioni, cioe'
ricreerebbe il difetto che si sta misurando.

`tools/recluster.py` rigioca il raggruppamento offline in millisecondi invece che
in una passata di OCR, e `--shuffle` — le stesse impronte permutate fra le
battute — e' il caso nullo che fissa le soglie.

**Come si confrontano due passate**: allineando le battute per testo e
**risolvendo la permutazione delle etichette**, perche' non conta se Lamar prende
M1 o M2, conta che la tenga. Chiedere "quante voci diverse" invece di "quante
coppie di battute sono d'accordo sull'essere la stessa persona" ha fatto
sembrare rotto per mezza giornata un riconoscimento che era al 100%.

## Config

Un solo albero di dataclass in `core/config.py`, ogni campo raggiungibile con
`--set sezione.campo=valore`. Un percorso inesistente e' un errore all'avvio, non
un refuso silenzioso. I default sono **punti di partenza dichiarati o misure
scritte**: dove c'e' una tabella nel commento, quel numero e' stato misurato e la
tabella dice come. ROI, soglie di colore e coefficienti di durata si ricavano con
`tools/calibrate.py` e si scrivono in `profiles/<gioco>.json` — e sono **del
setup di cattura, non del gioco**.

## Convenzioni

- **Codice in italiano**: commenti, docstring, messaggi di log, help della CLI,
  stringhe dell'interfaccia. **Identificatori in inglese.**
- Windows + PowerShell.
- I messaggi git multi-riga da PowerShell si rompono (le here-string vengono
  ri-analizzate e si mangiano le virgolette): scrivere il messaggio su file e
  usare `git commit -F file`.
- Commit solo dopo una suite verde. Commit piccoli e logici. Solo in locale.
- **Le prove d'ascolto si consegnano in MP4** (`tools/dub.py --mp4`): gioco,
  traccia doppiata e in alto su fondo nero il testo **letto dall'OCR** con la
  voce assegnata. Senza, non si distingue "ha sbagliato a leggere" da "ha
  sbagliato a dire" — e difetti che sembravano del sintetizzatore si sono
  rivelati frasi spezzate fra due sottotitoli.

## Le regole di metodo, che valgono piu' del codice

**Verificare una trasformata contro la propria inversa** prima di accusare un
modello: una trasformata sbagliata produce spazzatura plausibile, non un errore.

**Guardare l'ingresso del modello prima di accusare il modello.** L'OCR leggeva
`Oaai recuperiamo veicoli acauistati` e sembrava scadente sull'italiano: il
ritaglio che riceveva aveva le code di `g` e `q` tagliate, e una `g` senza coda
**e'** una `a`.

**Il caso nullo migliore condivide tutto tranne la risposta.** Le impronte
permutate fra le battute lasciano identiche scena, tempi e alternanza e tolgono
solo *chi e' chi*: sono loro ad aver fissato la soglia della fusione, dove il
conteggio delle identita' da solo ne avrebbe scelta una che fondeva a caso.

**Controllare che la misura possa esprimere la risposta.** Un caso: selezionare i
pixel di testo con una maschera che pretende uno stacco maggiore di 60 e poi
misurare lo stacco — risposta 60,15, cioe' la soglia che si guarda allo specchio.
Un altro, di oggi: `ritardo_anello` era la differenza fra l'orologio e una
quantita' **definita come l'orologio**, quindi valeva zero anche dove un terzo
dei frame veniva saltato.

**Un'unita' di misura e' un operatore come un altro.** `chars_per_second` valeva
17,4, misurato contando *tutti* i caratteri, ed era diviso per `spoken_length()`,
che conta **solo lettere e cifre**: un quarto di errore su ogni durata prevista,
per anni, senza che nessun numero fosse sbagliato — sbagliato era che i due si
incontrassero.

**La stessa unita' sbagliata, tre volte.** Dopo `chars_per_second`, la soglia
della fusione: `merge_similarity` era misurata **fra due centroidi maturi** e
veniva applicata anche a un'identita' da una battuta sola — dove un "centroide"
e' un ritaglio, cioe' l'altra distribuzione. Con 0,70 quel confronto non passava
mai, quindi la cura scritta per la frammentazione non partiva **proprio nel caso
per cui esiste**. Prima di riusare una soglia altrove, chiedersi su quale
distribuzione e' stata misurata.

**Una taratura si giudica sul minimo fra le passate, non sul massimo.** Tre
passate della stessa scena davano 30, 22 e 15 battute giuste con lo stesso
codice: a 0,54 sono d'accordo, a 0,55 si separano. Il valore in config stava
sull'orlo di un precipizio, e la passata fortunata sembrava la prova che
funzionasse. Una soglia va cercata **in mezzo a un altopiano**; se il vicino di
un centesimo da' un risultato molto diverso, il numero non e' tarato, e' vinto.

**Un parametro dichiarato in config puo' non essere letto da nessuno.**
`max_ocr_hz` esisteva da mesi, e l'OCR girava a 25 Hz consumando 52 secondi di
lavoro per 60 di scena — piu' di tutto il resto della catena messo insieme.
Nessun numero lo diceva, perche' nessuno aveva mai sommato i timer per stadio.
Prima di spostare un costo su un thread, sommare i costi.

**Due errori che si compensano sono piu' pericolosi di un errore solo.** La stima
delle durate era corta di un quarto e l'anello di correzione la compensava
alzando il guadagno: il risultato finale era ragionevole. Correggendo *solo* la
stima tutto e' peggiorato di colpo. Quando una correzione giusta peggiora le
cose, il difetto non era uno.

**Un rimedio che funziona non conferma la diagnosi.** Il percentile basso sulla
f0 curava il difetto, quindi la spiegazione che lo accompagnava — "c'e' del fondo
tonale che contamina" — e' rimasta in piedi senza essere verificata. Era
sbagliata: quelle frequenze erano un uomo che urla, e si vede perche' salgono con
l'energia della finestra invece di stare nelle pause.

**Verificare che il trattamento sia stato applicato prima di leggere il
risultato.** La prova del separatore vocale dava un risultato pulito e falso: il
raggruppamento non migliorava perche' l'audio non era cambiato (correlazione
0,983 con l'originale). Bastavano una correlazione e un istogramma.

**Isolare una taratura con un motore deterministico.** SuperTonic e' a diffusione:
cambiando la voce cambia la sintesi, cambiano i tempi, cambiano le decisioni. Due
misure di seguito hanno detto il contrario del vero. Le tarature si isolano con
Piper e si verificano dopo con SuperTonic. **Ma Piper non e' deterministico**:
misurato, la stessa battuta nello stesso processo da' 95314 e 99075 campioni —
e' VITS, il predittore di durata ha del rumore dentro. Kokoro invece e'
deterministico campione per campione, ed e' l'unico dei tre che lo sia.

**Un caso nullo puo' essere mal posto quanto una misura.** Per verificare che
scambiare `onnxruntime` con `onnxruntime-gpu` non rompesse Piper, si e'
confrontata la sua uscita prima e dopo, campione per campione: risultato
«diverso», due volte. Ma anche **due passate consecutive senza cambiare niente**
davano lunghezze diverse. Il confronto chiedeva stabilita' a una quantita' che
non ce l'ha. La domanda giusta era l'aggregato — passo in car/s, picco, suite —
che infatti non si e' mosso. Prima di concludere che un trattamento ha cambiato
qualcosa, misurare **quanto varia quella quantita' da sola**.

**Un ripiego che non si dichiara e' peggio di un errore.** ORT non trovava le DLL
CUDA ed e' ricaduto sulla CPU senza dire niente: 708 ms stavano per essere
riportati come «il numero della GPU», con la conclusione opposta a quella vera.
Chi chiede un acceleratore deve **verificare che l'abbia ottenuto**
(`sess.get_providers()`), non che la chiamata non abbia sollevato.

**Il costo di uno stadio non si somma, si amplifica.** Kokoro costa 229 ms di
sintesi in piu' di Piper, ma in `--tempo-reale` la latenza cresce di **577**: la
sintesi sta nel thread video, i frame arretrati si saltano (883 contro 649), e il
lettore di sottotitoli e' costruito su frame *consecutivi*. Preventivare un
motore piu' lento sommando il suo costo alla latenza sottostima di piu' del
doppio.

**Dire prima della prova quale numero la smentirebbe.** Il banco prometteva -745
ms spostando la sintesi fuori dal thread video, e prima della prova dal vivo era
scritto che «se resta a 1300 il guadagno era un artefatto». E' rimasto a 1300 —
anzi 1410. Con la previsione scritta prima non c'e' stato niente da discutere;
scritta dopo, quegli stessi numeri si sarebbero potuti raccontare come «il vivo e'
rumoroso». Una previsione dichiarata prima e' l'unica che puo' perdere.

**La quantizzazione dinamica di questi TTS e' una pessimizzazione, e ora sono
due.** Kokoro int8 era quattro volte piu' lento del fp32; lo stimatore di
diffusione di SuperTonic quantizzato (256 MB -> 65) e' passato da 629 a 2845 ms,
**+352%**, con il trattamento verificato applicato e la durata dell'audio
identica al campione. Due modelli diversi, stessa ORT, stesso segno: non e' un
caso del singolo modello.

**Prima di attribuire una differenza al pezzo nuovo, rigirare il vecchio.** La
passata Kokoro dava 43 battute invece delle 44 archiviate e il 95,6% di accordo
sulle identita' — sembrava che il motore toccasse il riconoscimento, che sta a
monte. Rigirando Piper **adesso**: 43 battute e lo stesso 95,6%, e Piper-oggi
contro Kokoro-oggi al **100%**. Lo scarto stava fra le passate archiviate e HEAD,
non fra i motori, ed era l'OCR (`Esteban Jimenez.` contro `Esteban Jimenez.7`).

**Quando l'utente offre una prova dal vivo, quella e' la prova.** Il criterio
della parola colorata era stato dichiarato «innocuo ma inutile» su un surrogato —
le soglie del vivo applicate alla registrazione del banco. Li' non si vedeva
niente, perche' gli obiettivi interi erano gia' scartati e passava solo una
scritta a meta' dissolvenza, che nessun criterio sul colore puo' prendere. Dal
vivo, due passate a confronto, il guadagno era **da un'altra parte**:
`'Rec.Lavoriamo insieme...'` -> `'Lavoriamo insieme...'`,
`"Si, era lui.Adam'a App"` -> `'Si, era lui.'`. Non righe **saltate**: righe
**sporcate** da frammenti di HUD colorata, che venivano pronunciati. Nessun
contatore lo mostrava, perche' la riga risultante conteneva parole italiane vere
e passava ogni filtro. **Il surrogato non e' un ripiego accettabile: e' il modo
in cui si archiviano conclusioni false con la suite verde.**

**Togliere lo sporco dall'ingresso migliora anche cio' che non si stava
correggendo.** Nella stessa prova, `'ma devo dare una : olta alla mia vita.'` e'
diventata `'ma devo dare una svolta alla mia vita.'` — i pixel colorati non
sporcavano solo la parola che occupavano, disturbavano il riconoscimento intorno.

**`preload_dlls()` non e' del backend che lo chiama.** ORT non trova le DLL CUDA
dei pacchetti pip `nvidia-*` finche' qualcuno non chiama `preload_dlls()`, e
ripiega sulla CPU **senza dirlo**. Quella riga viveva dentro
`speak/backends/kokoro.py`, ed era una cosa da ricordarsi: misurando Qwen ci si e'
ricascati entro un'ora dall'aver letto quel commento, riportando 4-7 s a battuta
come «il numero della GPU». **Adesso sta in `core/onnx.py`**, che e' la porta da
cui passa chi vuole i provider — quindi non e' piu' una cosa da ricordarsi, e'
una cosa che non puo' non succedere. Li' c'e' anche `verifica_provider()`, perche'
chiedere un acceleratore non e' ottenerlo.

**Un numero impossibile e' piu' utile di un numero sbagliato.** Il ramo in
streaming non ricampionava da 22050 a 48000 — la riga che il ramo normale ha da
sempre — e versava campioni nel mixer a piu' del doppio della velocita': voce da
scoiattolo. Nessun contatore lo diceva, la suite era verde, il WAV usciva. A
smascherarlo e' stato che il passo misurato del motore risultava **30 caratteri al
secondo**, che non e' una velocita' di parlato di nessuno. Un numero fuori scala
va inseguito anche quando tutto il resto e' verde: e' l'unica traccia che lascia
un'unita' sbagliata.

**Lo stesso difetto non si eredita, e i rami nuovi non ereditano nemmeno le
cure.** Nella stessa sessione, due volte: il ricampionamento e il taglio del
silenzio in coda. `synthesize` toglieva l'imbottitura da sempre (`taglia_silenzio`,
scritto per SuperTonic dopo mezza notte di conclusioni sbagliate); `stream` no, e
consegnava **100 secondi di parlato per 49 di scena**, meta' dei quali silenzio,
con la catena che chiedeva fretta per starci dentro. Si accelerava del silenzio,
pagandolo in parole — la stessa frase gia' scritta in questo file, un anno e un
motore piu' tardi. Quando si apre una strada parallela a una che funziona, la
domanda non e' «cosa serve» ma **«cosa fa quella vecchia che questa non fa»**.

**In streaming il silenzio in coda non si taglia: si trattiene.** Quello che e'
uscito e' uscito. Il silenzio in fondo al prefisso resta indietro e, se il modello
riprende a parlare, esce insieme al resto (era una pausa); se il modello chiude,
non esce affatto (era imbottitura). Le due si distinguono solo dopo, ed e'
esattamente per questo che la decisione va rimandata invece che presa bene.

**Un motore autoregressivo si incanta, e il tetto non e' una rifinitura.**
Misurato: `'Toc toc, negri!'` — quindici caratteri — ha prodotto **9,12 secondi**
di audio. `max_new_tokens` valeva 2048, cioe' due minuti e mezzo: come rete di
sicurezza dal vivo non e' una rete. Nove secondi di voce su una battuta da uno
tengono occupata l'unica voce disponibile, e tutto cio' che arriva intanto o si
accavalla o slitta. Il taglio e' un difetto piccolo al posto di uno grosso.

**E quando la prenotazione si fa su una previsione, va corretta su cio' che
arriva.** In streaming `_free_at` nasce da `chars_per_second`; se la battuta vera
e' piu' lunga, la successiva e' gia' stata programmata **sopra** di lei — due voci
italiane insieme, il difetto peggiore del prodotto. Il produttore la rialza a ogni
blocco leggendo `mixer.finisce_a`, che e' l'unico posto che sa la verita'.

**La stessa unita' sbagliata, per la quarta volta — stavolta era una lingua.**
Dopo `chars_per_second` contato in due unita', dopo `merge_similarity` misurata su
una distribuzione e applicata a un'altra, dopo il passo di un motore applicato a
un altro: traducendo in inglese, la catena usava i 12,9 car/s misurati
sull'italiano. Credeva ogni battuta piu' lunga di quanto fosse, e comprimeva **al
tetto** una scena piena al 49%. Compressione autoinflitta, con tutto il tempo del
mondo a disposizione.

Il sintomo era `dub.rate_x1000` a 1250 **su tutti i percentili**. Un numero
inchiodato al tetto su ogni percentile non e' mai una coincidenza: e' sempre un
vincolo che morde da un'altra parte.

**Un artefatto in cache che non sa di essere scaduto.** L'archivio delle voci di
Kokoro si costruiva una volta e poi bastava che il file esistesse. Aggiungendo le
voci inglesi, quello vecchio — con dentro le sole due italiane — e' rimasto
«buono» agli occhi di quella funzione, e la prima voce inglese e' morta con un
`KeyError` dentro la libreria, lontanissimo da dove stava il difetto. Chi mette
qualcosa in cache controlli **cosa** c'e' dentro, non che ci sia.

**Un rimedio che stringe puo' stringere sul posto sbagliato, e sembra comunque un
progresso.** Il riquadro sfocato passava da 1516x391 a 670x108: tutti i numeri
miglioravano. Guardando il fotogramma dipinto, quel riquadro stava **dove il
sottotitolo non c'era** e l'italiano era rimasto scoperto sotto — cioe' peggio di
prima, perche' prima almeno lo copriva. Nessuna delle misure che stavo guardando
(altezza, larghezza, raggio) poteva dirlo: sono tutte misure di *quanto*, e lo
sbaglio era *dove*. Su una correzione geometrica, la verifica e' l'immagine.

**E il modo per non dipendere dall'occhio e' avere una posizione vera con cui
confrontarsi.** Le tre ancore candidate si sono decise in un minuto mettendo in
tabella la distanza di ciascuna banda dal punto dove il sottotitolo sta davvero —
la `row_band` della calibrazione, che era gia' scritta nel profilo e non l'aveva
mai riletta nessuno: la banda giusta a 13 e 17 px, le altre a 117 e 180.

**Prima di dire che una cosa non si puo' fare, guardare cosa si ha gia' in mano.**
Avevo scritto che dal vivo la sfocatura del sottotitolo era impossibile, perche'
avrebbe richiesto una seconda cattura dello schermo. Falso: la catena cattura gia'
il fotogramma a 30 Hz per darlo all'OCR. Quei pixel erano nostri, e prenderli
costava un ritaglio.

**Un anello di reazione non lascia tracce nel pezzo che rompe.** L'overlay dal
vivo veniva catturato dallo screenshot che alimenta l'OCR: il programma leggeva
il proprio testo, e il sintomo — righe saltate — sembrava a tutti gli effetti un
difetto dell'OCR. Nessun contatore poteva dirlo, perche' per la catena quel
fotogramma era un fotogramma. La domanda che lo scioglie in un minuto e'
**«quello che scriviamo puo' rientrare da dove leggiamo?»**, e si risponde
mettendo a schermo un colore che nel gioco non esiste e cercandolo nei pixel
catturati.

**Quando l'utente deve accendere il gioco per giudicare, lo strumento e'
sbagliato.** Ogni giro di correzione sulla grafica costava a lui una sessione
intera — Voicemeeter, la selezione dell'area, la partita — e dopo due giri si
consegna una cosa sbagliata perche' nessuno ne fa un terzo. `tools/overlay_mp4.py`
monta un video con **lo stesso pittore** che usa la finestra dal vivo, quindi
la grafica si guarda da soli in trenta secondi. Un MP4 disegnato da ffmpeg no:
sarebbe un secondo disegnatore, e mostrerebbe una cosa mentre il vivo ne fa
un'altra — che e' esattamente com'era nato il difetto.

**Una cura puo' rompere qualcosa che nessuno stava guardando, e a volte la cura
giusta e' non averne bisogno.** L'overlay veniva nascosto a *tutte* le catture
per non rientrare nell'OCR: giusto, e con due prezzi — non lo vedeva nemmeno chi
registra, e non era piu' fotografabile, quindi nemmeno diagnosticabile. La
risposta non era una seconda cura (una telecamera virtuale che rimettesse il
tradotto in una sorgente video): era **togliere la causa**. Catturando la sola
finestra del gioco l'overlay non rientra affatto, e la cura — con i suoi due
prezzi — si puo' buttare. Prima di curare un difetto, chiedersi se esiste per
una scelta che si puo' disfare.

**Un ottimo algoritmo nel posto sbagliato e' un difetto.** `inpaint` cancellava
la riga meglio di tutto il resto, e per questo e' stato scelto: 16 ms sembravano
niente perche' si pagavano una volta per battuta. Ma quel costo **decideva
l'architettura** — a 16 ms si puo' solo congelare la toppa, e una toppa congelata
mentre la scena si muove e' un rettangolo di immagine vecchia. Con apertura e
chiusura a 0,15 ms la si puo' rifare trenta volte al secondo, e il difetto
sparisce da solo. Prima di scegliere il pezzo migliore, chiedersi **quale
architettura consente**.

**Un pezzo che nessuno ha guardato non e' «scritto», e' «supposto».** L'overlay
e' stato consegnato verde e con gli import a posto; messo su un fotogramma a
tutto schermo e fotografato, il difetto era **il primo che si vedeva** — la
finestra dimensionata sul testo originale con dentro quello tradotto. Nessuna
verifica lo prendeva perche' non esisteva **nessuna** verifica sull'overlay, e la
suite verde e' stata scambiata per una conferma. Un modo di guardarlo costava
venti minuti: fotogramma a schermo intero, overlay vero sopra, screenshot.

**E la quinta volta della stessa unita' sbagliata e' stata una catena.**
`accepted_delay_ms = 250` era misurato bene — su una catena in cui la parte fissa
costava ~670 ms. Aggiungendo la traduzione sulla strada critica quella parte e'
diventata 1690 ms, e il numero e' diventato sbagliato **senza che nessuno lo
toccasse**: `dub.rate_x1000` a 1250 su tutti i percentili con la scena piena a
meta'. Una soglia si rimisura quando cambia la catena, non quando cambia il
sintomo. (Il corollario sullo strumento: la domanda **non era rispondibile dal
banco**. Con `--tempo-reale` e la traduzione accesa il costo fisso diventa 8,9 s,
e li' nessuna scusa plausibile libera il budget — 250 e 1250 danno la stessa
compressione al tetto. La risposta e' venuta rigiocando la programmazione di due
sessioni **dal vivo** archiviate, dove gli `elapsed` veri erano gia' scritti in
`events.jsonl`.)

**E la sesta e' stata una lingua, di nuovo — ma stavolta ha spento un
cancello.** `_gia_detta` riceve la battuta **prima** che `_speak` la traduca,
quindi in italiano; le battute gia' dette conservano cio' che si e' *detto*, che
traducendo e' inglese. Si confrontava `abbracciami` con `hugme`: con la
traduzione accesa il cancello anti-doppioni non poteva scattare **mai**.
Misurato: `dub.repeated` a **0** con due doppioni identici a schermo, e 6 dopo
la cura, sulla stessa scena. Il gruppo `non_ripetere` era verde perche' provava
una catena che **non traduce** — e il traduttore finto che ora usa deve
**cambiare davvero** il testo, se no le due lingue coincidono e la verifica
torna a non poter fallire.

**Una misura puo' essere raccolta a ogni giro e non arrivare da nessuna parte.**
`overlay.ritardo` — quanto e' vecchio il ritaglio quando arriva a schermo —
esisteva, girava, e veniva buttato: `ferma()` scriveva solo il rapporto della
catena, e le metriche della finestra morivano con lei. Quando l'utente ha detto
«il blur va in differita», la risposta era gia' stata raccolta e mai letta, ed
e' stata cercata con un banco. E' il quarto campo di questo progetto misurato o
dichiarato e mai letto, dopo `max_ocr_hz`, `tts.device` e `background_mode`.
Prima di misurare qualcosa, guardare se e' gia' misurato.

**Un costo si paga dove sta, non dove serve.** Il ritaglio dei pixel da sfocare
stava in fondo al giro video, dopo `on_frame`: per spedire dei pixel aspettava
che l'OCR avesse finito di leggere — `vision.ocr` a **84 ms al p50 e 137 al
massimo**, cioe' quattro fotogrammi di ritardo che non erano suoi. Per sfocare
non serve sapere cosa c'e' scritto. Misurato prima di toccare niente: il
ridisegno costa **10,5 ms**, quindi il difetto non e' mai stato nel disegno, era
nell'attesa. Quando qualcosa arriva tardi, guardare **cosa aspetta**, non quanto
costa.

**Una cura e' quasi sempre piu' stretta del difetto, e la suite verde non lo
dice.** Rilette a freddo, cinque delle correzioni scritte per chiudere le cento
domande erano **meta'**: `profiles/ultima.json` scritto uscendo e mai riletto
aprendo (sesta volta della forma «dichiarato e mai letto», stavolta con il file
gia' pieno dei valori giusti accanto a una finestra che ripartiva dai default);
il guasto dell'audio che fermava i due thread ma lasciava **Avvia spento**, la
sessione aperta e lo stato **verde**; `save_mix=false` che spegneva l'orologio
insieme alla registrazione, e quindi ogni `t_wav` nullo — cioe' `tools/reopen
<secondo>`, che e' il metodo intero di questo progetto; il tetto alla memoria
messo su `spoken` e non su `closed`. Tutte scritte guardando il difetto, tutte
verdi, tutte incomplete. La domanda che le prende e' gia' scritta qui sopra per i
rami paralleli — **«cosa fa la strada vecchia che questa non fa?»** — e vale
anche per una cura: *fermare i thread non e' fermare la sessione, spegnere la
registrazione non e' spegnere l'orologio, salvare non e' rileggere*.

**E il posto dove guardare per primo e' quello che nessuna verifica tocca.**
Quattro di quei cinque stavano nella finestra Qt o al suo confine, che era
l'unica parte del programma senza **nessuna** verifica. Il rimedio non e'
verificare Qt: e' che la parte che si puo' provare senza aprirlo **stia fuori da
Qt** — `core.preferenze.riprendi` (con che configurazione si riapre) e
`tools.ui.colore_stato` (di che colore va il pallino) sono regole, non disegno, e
adesso si verificano in una suite che gira senza hardware.

**Due passate della stessa scena non sono la stessa scena se non sono lo stesso
tratto.** Provando il vivo contro il banco ho concluso tre volte una cosa falsa
per la stessa ragione: la prima perche' il video era **finito** a meta' prova (e
uno schermo fermo, per la catena, e' uno schermo senza sottotitoli); le altre
perche' confrontavo il vivo su 0-70 s col banco su 30-125. Da li' erano usciti
«dal vivo si perde il 60% delle righe» e «dal vivo riconosce molto peggio»,
tutti e due **falsi**: allineando i tratti, 31 battute contro 33 (94%) e voce
neutra 81% contro 78%. La differenza era la scena — la prima meta' e' fatta di
battute corte di personaggi che non parlano mai abbastanza da essere confermati.
Prima di leggere un confronto, verificare che le due passate abbiano visto le
**stesse immagini**: `riparti.py` di quella sessione lo faceva rifiutandosi di
misurare se due catture a un secondo di distanza erano identiche.

**E la piu' importante: l'orecchio dell'utente trova cio' che la suite non puo'.**
E' successo a ogni difetto serio di questo progetto, con la suite verde. Quando
l'utente dice "non funziona" e i numeri dicono di si', **sono i numeri a essere
sotto esame** — e la risposta giusta e' chiedergli *il secondo* in cui l'ha
sentito, non un'altra impressione.

## Dove sta il lavoro

`PROSSIMA_SESSIONE.md` e' il passaggio di consegne: stato, cosa e' aperto e con
quale misura si scioglie. Va aggiornato a fine sessione, e vale piu' di questo
file per sapere *cosa* fare adesso.
