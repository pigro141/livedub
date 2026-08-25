# La vetrina: cosa si costruisce prima di pubblicare

Piano per il lavoro delle 5 del mattino. Quattro agenti, tre in parallelo piu'
uno che aspetta. La pubblicazione vera e propria **non e' qui**: avviene solo
dopo che l'utente consegna le credenziali e dice di procedere.

**Regola che vale su tutto**: nei commit, nel README, nel sito e in qualunque
metadato **Claude non compare mai**, in nessuna forma. L'autore e' sempre e solo
l'utente. La storia e' gia' stata ripulita (192 commit, zero trailer).

---

## Una cosa da non sbagliare sui video

`tools/dub.py` fa girare **la stessa identica catena** su una registrazione:
stesso `DubPipeline`, OCR vero, audio vero, impronta vera, sintesi vera, mixer
vero, causalita' rispettata. **Non e' una simulazione**, quindi un video fatto
cosi' mostra il prodotto che funziona davvero, e non c'e' nessun bisogno di
dichiarare da dove viene.

**Ma il banco regala il tempo**: con l'orologio virtuale la sintesi costa zero e
nessun frame viene saltato. Quindi da un video di banco si puo' mostrare
**tutto** — l'OCR che legge, la voce assegnata al personaggio, la traduzione, il
mix — **tranne una cosa: quanto e' veloce.** Nessuna scritta, nessuna didascalia
e nessuna riga di README deve dichiarare o far intendere una latenza a partire da
quel materiale.

Se serve un numero di latenza, si prende da una sessione **dal vivo** in `runs/`,
dove e' misurato davvero. Ce ne sono di buone del 19-20 agosto.

---

## Agente A — i video

Tre clip corte, senza audio di commento, senza scritte inventate.

1. **Il doppiaggio italiano su GTA V.** `tools/dub.py --mp4` monta gia' gioco +
   traccia doppiata + in alto su fondo nero il testo **letto dall'OCR** con la
   voce assegnata. E' la prova d'ascolto standard del progetto.
2. **La traduzione in azione**, italiano -> inglese, con l'overlay disegnato
   sopra il gioco. `tools/overlay_mp4.py` usa **lo stesso pittore** della
   finestra dal vivo, quindi mostra cio' che si vedrebbe davvero.
3. **Il programma**, cioe' la finestra Menta mentre lavora.

Scegli tratti di scena con **dialogo vero e piu' personaggi**, non inseguimenti
muti: il pregio del prodotto e' che voci diverse vanno a persone diverse, e su
una scena senza parlato non si vede.

Formato: MP4, ragionevolmente corti (20-40 s), pesati per stare in un README di
GitHub — e se sono troppo pesanti, una GIF o un MP4 ridotto. Metti tutto in
`assets/vetrina/` e dimmi peso e durata di ognuno.

---

## Agente B — immagini e logo

- **`menta-anteprima.png` va rifatta**: mostra **quattro** schede, oggi sono
  **sei** (Preparazione, Sessione, Voce, Volumi, Traduzione, Tutte). Si rigenera
  con `tools/scatta.py`, che fotografa la finestra vera — **non si disegna a
  mano e non si ritocca**, e **mai** con `QT_QPA_PLATFORM=offscreen`, che ha zero
  caratteri installati e restituisce una finestra di quadratini.
- Le schermate della **guida iniziale**, che adesso ha **sette** passi (e' stato
  aggiunto quello del banco): `tools/scatta.py --tutorial`.
- Una schermata della **scheda Volumi** e una del **banco che misura**, che sono
  le due cose nuove.
- Il **logo** e' gia' nel repo ed e' la fonte di sei dei quattordici colori del
  tema e della regola del raggio. Usalo per l'immagine sociale del repo
  (`og:image`) e come icona. Non ridisegnarlo.

Guarda ogni immagine prima di consegnarla: in questo progetto **ogni** difetto
grafico e' uscito da uno screenshot e **nessuno** da una rilettura del codice.

---

## Agente C — l'eseguibile

Indipendente dagli altri due, quindi parte insieme.

`livedub.spec` c'e' ed e' aggiornato, ma l'unico exe mai costruito e' del **10
agosto** — prima della finestra Menta, delle 41 lingue, della guida, dei Volumi e
del banco. Non e' «gia' fatto»: e' **supposto**.

Il posto in cui guardare per primo sono i **dati**, non il codice:

- `core/config.py` deve viaggiare fra i dati, se no il pannello resta **senza
  spiegazioni** (166 campi muti);
- `ui/lingue/*.json` (41 cataloghi) devono viaggiare, se no l'exe e' **solo
  italiano, e senza dirlo**;
- `core/banco.py` e la guida scaricano modelli: verifica che l'exe sappia dove
  metterli e che dichiari cosa manca invece di ripiegare in silenzio;
- cerca **qualunque altro file che il programma legge dal disco** e non e'
  codice. Interroga il grafo, non fidarti dello spec.

Poi **provalo davvero**: aprilo, guarda che il pannello abbia le spiegazioni,
cambia lingua in tedesco e in arabo, apri la guida. Un exe che parte non e' un
exe che funziona. Se puoi, provalo in una cartella dove il repo non c'e': e'
l'unico modo per accorgersi di un file letto dal sorgente invece che da dentro.

Riporta peso e tempo di avvio.

---

## Agente D — README e sito (aspetta A e B)

Parte quando A e B hanno consegnato, perche' usa il loro materiale.

- **Il README va riscritto**, non ritoccato: non nomina le **41 lingue** della
  finestra, la **guida iniziale**, la scheda **Volumi**, il **banco** che sceglie
  i motori. E qualunque punto che prometta le **aree multiple** va tolto: sono
  state rimosse.
- L'ordine giusto e' quello che incontra chi apre il programma: si apre, sceglie
  la lingua, la guida lo porta per mano, il banco misura e sceglie i motori.
- **Il sito e' su GitHub Pages** e usa le immagini e i video rifatti oggi, mai
  quelli vecchi.
- Il link donazioni e' gia' deciso: Ko-fi, «Buy me a token!».
- `LICENZE.md` e `installa.ps1` ci sono: rileggili e dimmi se sono ancora veri.

Nessuna affermazione sulla velocita' che non venga da una sessione **dal vivo**
misurata. Se scrivi un numero, dimmi da quale cartella di `runs/` viene.

---

## Cosa **non** si fa senza l'utente

- **Nessun push, nessuna creazione di repo, nessun login.** L'utente consegnera'
  le credenziali e dira' quando. Fino ad allora tutto resta locale.
- **`backup-pre-pulizia` va cancellato prima di pubblicare.** Se resta, porta su
  GitHub la vecchia storia con dentro tutto cio' che e' stato tolto — cioe'
  vanifica la pulizia. Ma si cancella **quando l'utente e' sicuro**, non prima.
- Prima di spingere: `git status --ignored` e un'occhiata a cosa entrerebbe.
  `models/` (1,3 GB), `runs/` e le registrazioni sono materiale della macchina.
  «Gitignorato» va **verificato**, non creduto.

---

# Le decisioni dell'utente, prese il 24 agosto

## Smart App Control: **non si spegne**

Blocca le DLL non firmate del venv (`torch\lib\shm.dll`), e da li' cade
`argostranslate` -> `stanza` e con lei mezza suite: **12 fallite su 1753** invece
di 1936 verdi, misurato su HEAD **senza** il lavoro non committato, quindi non e'
una regressione del codice.

Spegnerlo funzionerebbe, ma **e' irreversibile**: Smart App Control non si
riaccende, per rimetterlo serve reinstallare Windows. L'utente ha scelto l'altra
strada.

**La strada e' togliere torch dal venv, non spegnere la protezione.** Torch sta
li' solo perche' `argostranslate/sbd.py` importa `stanza` in cima e stanza lo
tira: sono **~700 MB di peso morto gia' documentati in `requirements.txt`**, per
una traduzione che gira su **CTranslate2** e non usa torch per niente. Quindi
questa non e' una rinuncia: e' la cura che l'ambiente aspettava da mesi, e
adesso ha anche un motivo urgente.

⚠️ Chi ci mette le mani: `requirements.txt` monta **`onnxruntime-gpu` e non
`onnxruntime`**, i due **non convivono**, e il blocco su `minisbd --no-deps`
esiste apposta. Non si tocca l'ambiente senza chiedere.

## CUDA nell'eseguibile: **si scarica, non si impacchetta**

Parole dell'utente: mettere CUDA nell'exe **solo se la macchina ha una GPU
adeguata**; lo decide il **banco all'avvio**; se non trova niente, il motore che
vuole la GPU **resta comunque fra le opzioni**, e scegliendolo si scaricano CUDA
e il modello **con una barra di avanzamento**.

Quindi il pacchetto resta **leggero** (1,14 GB) e le DLL `nvidia-*` (1,28 GB, che
lo porterebbero a ~2,5) **non** ci entrano: le prende `core/banco.py` alla prima
richiesta, esattamente come gia' fa con i 541 MB di modelli. E' anche la strada
piu' coerente col resto del programma.

Da non sbagliare: il banco deve dichiarare **la GPU ottenuta e non quella
compilata** (`core/onnx.verifica_provider()`), se no si ricade nel difetto gia'
trovato — il passo 6 che dice «CUDA» mentre la sessione dice CPU.

## I video: **sulla repo e sul sito**, e devono far capire il prodotto

L'utente non ha preferenze sul formato — GIF, MP4 o un caricamento con link:
**si fa nel modo in cui i video si mettono su GitHub**, e il risultato deve
vedersi **sia sulla pagina della repo sia sul sito**.

Ma sul **contenuto** e' stato preciso, e sono due vincoli:

1. **Niente video della traduzione senza i sottotitoli tradotti a schermo.** Un
   video della traduzione in cui la traduzione non si vede non dimostra niente.
2. Il video deve far capire **che legge i sottotitoli e li dice a voce alta con
   la voce del personaggio giusto**. E' cio' che il prodotto fa, ed e' la cosa
   che uno screenshot non puo' mostrare.

Vale sempre la regola di sopra: il materiale e' genuino e non serve dichiarare da
dove viene, **ma da li' non esce nessun numero di latenza**.
