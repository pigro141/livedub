Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`),
doppiaggio italiano dal vivo dei sottotitoli dei videogiochi.

## Dove siamo, in tre righe

**Il repo è pubblicato**: <https://github.com/pigro141/livedub>, sito su
<https://pigro141.github.io/livedub/>. `main` è pulito e spinto.

**Il difetto aperto più grave**: Smart App Control di Windows 11 — acceso di
serie sulle installazioni pulite — blocca alcune DLL. **L'eseguibile non parte
affatto**, e due funzioni restano rotte con un errore grezzo invece di una
rinuncia dichiarata. Vedi «Cosa è rotto adesso».

**La suite su questa macchina dà 12 fallite su 1753** (invece di 1936 verdi), ed
è quel blocco, **non una regressione del codice**: misurato su HEAD da solo, con
l'albero pulito. Quindi finché SAC morde, il criterio è **«non aggiungere fallite
rispetto a HEAD»**, non «tutto verde».

---

## La cosa che va capita prima di toccare qualunque cosa

**`.venv` non può dire cosa succede a chi installa adesso, e ogni verde letto lì
dentro è falso.** Misurato: `ctranslate2/_ext.pyd` carica dentro `.venv` mentre
la sua copia **byte-identica** (stesso sha256) è bloccata. Il verdetto di Smart
App Control sta in cache **sulla singola copia del file**, non sul contenuto.

Un ambiente che ha quei file da mesi ha la reputazione già maturata; una macchina
appena installata no. È la sesta volta in questo progetto della forma **«una
misura che non può esprimere la risposta che le si chiede»** — e qui è costata la
prima diagnosi intera, che diceva «piper OK» solo perché `espeakbridge.pyd` si
apre **pigramente alla prima sintesi**.

Quindi: **qualunque prova su cosa passa o non passa si fa in un venv nuovo**, mai
in `.venv`.

E il criterio non è «non firmato» — numpy e ctranslate2 non lo sono e passano — è
la **reputazione del singolo file** (ISG). Non è nemmeno «vecchio passa, nuovo
no»: opencv **4.14 è bloccata e la 4.13 no**, windows-capture 1.4.4 è bloccata
come la 2.0.1.

---

## Cosa è successo il 19-24 agosto

### Il bug delle «battute in ritardo» erano **tre bug**

Chiuso e **verificato dal vivo dall'utente** («torna tutto e va bene»).

1. **`b2a6557` + `4d0ce52` — ogni Avvia lasciava accesa la cattura di quello
   prima.** I callback di WGC sono chiusure su se stessi e il ciclo video non
   chiamava mai `close()`: cinque Avvia = **5 catture accese, 285 copie/s invece
   di 57**. Sintesi da 162,9 a 180,4 ms, `classify_lines` da 30 a 47.

   | | prima | dopo (dal vivo) |
   |---|---|---|
   | 1ª passata | 962 ms | 908 ms |
   | 4ª-5ª passata | **8580 · 9453 ms** | **1984 · 1290 ms** |
   | peggior caso | **46938 ms** | 5346 ms |
   | `vision.classify` | 30 → 47 ms | **33-37 ms, piatto** |

2. **`a15ae1b` — `Motore.acceso` mentiva durante la partenza.** Valeva
   `bool(self.threads)`, e i thread nascono in fondo a `_prepara`: un Ferma o un
   RIPROVA in quei secondi faceva salire una **seconda catena**. Ora
   `Motore.stato` + `core.motore.bottoni()` sono la fonte unica, fuori da Qt.

3. **Il cancello del diff normalizzava sull'area, e l'utente aveva ragione.** Un
   sottotitolo occupa **lo stesso numero di pixel** che l'area sia stretta o
   larga, quindi dividere per l'area era la **sesta** volta della forma «soglia
   misurata su una distribuzione e applicata a un'altra». Con l'area a 0,95 le
   comparse viste passano da **33 a 42 su 44**. Vale il criterio dell'utente:
   **area più larga = meno precisione, ma legge sempre**.

### La traduzione dentro l'attesa, e Argos

`5a569b8` — la traduzione avviene **durante** i 500 ms di `decide_after_ms`
invece che dopo (`core/anticipa.py`). Dal vivo con Argos: **65 battute su 65
anticipate**, `translate.attesa` a 0,01 ms, latenza da 1828 a **962 ms**.

Argos era già il default; il commento di `translate.backend` adesso porta la
misura che lo sceglie, ed è il **p95 e non il p50** (Argos 67 ms, google 1188).

### Altri difetti chiusi

- **`659c1c7`** — la barra mostrava `vision.ocr` con una soglia misurata su
  `vision.read`: fattore 2,7, e teneva l'OCR **in ambra per undici minuti** nella
  sessione più sana della giornata. Settima volta della stessa forma.
- **`e7b647a`** — un separatore di sezione (`# -- titolo ---`) finiva dentro
  l'aiuto del campo successivo. La prima cura (una riga vuota) **non funzionava**:
  la risalita salta le righe vuote. Adesso riconosce il titolo e si ferma lì.
- **`d9601b7`** — la guida insegnava una regola **eliminata il giorno prima** («un
  area grande non legge: non legge») e la soglia sbagliata (0,30 invece di 0,12).
- **`608c177`** — 122 righe di guasto **finte** nel registro dell'utente, scritte
  da `tools/scatta.py` e dalla suite. Zero venivano dalla catena viva.
- **`bdd9ffd`** — **PySide6 non era nei requisiti**: da un clone pulito il
  programma non si apriva.

### La vetrina, e la storia git ripulita

- **La storia è stata ripulita**: 192 commit, zero trailer `Co-Authored-By`,
  autore sempre e solo l'utente. Backup nel ramo locale **`backup-pre-pulizia`**.
- **`menta-anteprima.png` non era scaduta: era un disegno**, con dentro la
  linguetta Aree (rimossa), la pillola di stato (tolta) e un errno impossibile.
  Rifatta fotografando la finestra vera, insieme a tutte le altre.
- **README e sito riscritti**, con tre diagrammi mermaid **resi e guardati** (due
  erano rotti sulla carta: le due attese in parallelo si impilavano, quindi il
  diagramma non mostrava la cosa che doveva mostrare).
- **Video**: GIF nel README (GitHub le anima senza cliccare), MP4 sul sito (hanno
  l'audio, e questo programma parla), ogni GIF è un link al video. 13 MB in
  `assets/vetrina/`, con l'eccezione in `.gitignore`.
- **`d7f9d65`** — le versioni dei pacchetti fissate a quelle che SAC lascia
  caricare: da 17 pacchetti bloccati a 7. Nel venv di prova la suite passa da 14
  fallite su 1754 a **3 su 1891** (137 verifiche in più, perché i gruppi che
  esplodevano ora girano).

---

## Cosa è rotto adesso, e aspetta una decisione

### 1. L'eseguibile non parte, e non è colpa del pacchetto

**Verificato**: `dist\livedub\livedub.exe` dà `Permission denied`, e il registro
Code Integrity ha gli eventi **3077 e 3033** all'istante esatto. Compilando un
`ciao.py` di **una riga** con PyInstaller: **bloccato anche quello**. Ogni build è
un file unico, quindi **reputazione zero per costruzione**.

Corollario che morde: **tutti gli exe-guscio generati da pip sono bloccati**,
`pip.exe` compreso. Salva il progetto il fatto che la convenzione sia già
`python.exe -m pip`, e che `vision/ocr.py` lanci il figlio con
`sys.executable -m vision.oneocr_worker`.

**Firmarlo forse basta, forse no**: SAC valuta anche la reputazione del
certificato, e uno nuovo può restare sconosciuto per un po'. È l'unica cosa non
verificata di tutta questa indagine, ed è dichiarata come ipotesi apposta.

**Per ora il README pubblicato indica `installa.ps1` e non l'exe**, quindi chi
scarica ha una strada che funziona. Non promettere l'exe finché non parte.

### 2. `windows_capture` non ha nessuna versione che passi

Provate 2.0.1 / 2.0.0 / 1.5.0 / 1.4.4: tutte bloccate. Cade la cattura di **una
finestra sola**, che in `CLAUDE.md` è «la scelta che viene prima di tutte le
altre». Il ripiego su `MssSource` funziona (provato) ma **si riporta dietro tutto
ciò che quella scelta aveva risolto**: il programma può rileggere il proprio
overlay (torna necessario `WDA_EXCLUDEFROMCAPTURE`, al prezzo che chi registra non
vede più l'overlay), la ROI non segue più il gioco se si sposta, il costo di
cattura risale.

**Oggi il ripiego non è pulito**: chiedendo `backend='finestra'` l'utente si
prende un `ImportError: DLL load failed` grezzo. **Va trasformato in una rinuncia
dichiarata**, sulla falsariga di `core.banco.AVVISI`.

### 3. `llama-cpp-python` idem

Provate 0.3.35 / 0.3.34 / 0.3.2: tutte bloccate. Muoiono il backend di traduzione
`llm` e il `Revisore` di `vision/correct.py`. Sono **spenti di serie** entrambi,
quindi il danno è contenuto — ma il pannello li offre, e sceglierli darà errore.

**Il minimo da fare per 2 e 3 è la stessa cosa**: una rinuncia dichiarata invece
di un errore grezzo. È la regola più costosa di questo repo — *un ripiego che non
si dichiara è peggio di un errore*.

---

## Il lavoro a metà, che è su un ramo suo

**`lavoro-exe-a-meta`** (locale, non spinto). Dentro: `core/cuda.py` e
`core/percorsi.py` nuovi, più l'inizio di due cure in `core/onnx.py` e
`core/versione.py`. **Non è finito**: nel venv di prova due verifiche dei gruppi
`banco` e `cuda` falliscono. `main` è pulito apposta.

Cosa doveva fare, ed è la **decisione dell'utente del 24 agosto**:

- **CUDA non si impacchetta nell'exe**: il banco la **scarica alla prima
  richiesta con la barra**, come già fa coi 541 MB di modelli. Il pacchetto resta
  leggero (1,14 GiB invece di ~2,5). Il motore che vuole la GPU **resta fra le
  opzioni anche senza scheda**: chi lo sceglie, se lo scarica.
- **Il banco deve dichiarare la GPU *ottenuta*, non quella compilata**
  (`core/onnx.verifica_provider()`). Difetto trovato e non ancora chiuso: al passo
  6 la guida dice «scheda video: CUDA» leggendo l'elenco compilato dentro, mentre
  la sessione vera dichiara CPU — **due righe dello stesso pannello che si
  contraddicono**, e quella che mente è la riga che l'utente legge *prima di
  decidere*.
- **`models/` in un posto solo**: sta in `_internal\` mentre `runs/`, `cast.json` e
  `lexicon_dir` sono relativi alla cartella di lancio. Chi apre l'exe da altrove
  riscarica 541 MB senza capire perché.
- **La versione cotta alla costruzione**: fuori dal repo l'exe scrive `(non da
  git)`, quindi non si sa da quale commit viene una segnalazione.

---

## Due decisioni prese, da non riaprire

**Smart App Control non si spegne.** È irreversibile (per riaccenderlo serve
reinstallare Windows) e soprattutto **non risolverebbe niente per chi scarica**:
il vincolo dell'utente è *«deve essere tutto plug and play»*.

**Torch non si può togliere**, contrariamente all'ipotesi di partenza:
argostranslate importa `stanza` incondizionatamente in tutte e due le versioni
utili (1.11.0 in `sbd.py`, 1.9.6 in `translate.py`). Si fissa a **2.8.0** e basta.

---

## Cose minori, segnalate e non curate

- **`docs/interfaccia.md:37`** rimanda a `menta-anteprima.png` e la descrive come
  un disegno: quel paragrafo va rifatto.
- **La barra della misura scrive «battute» due volte**, a dieci centimetri di
  distanza (dentro `_stato_testo` e poi come `Misura` a sé). Stessa forma già
  curata una volta per la ROI.
- **`testo_fioco` fa 2,85:1** sul fondo scuro, sotto il 3:1 che il progetto
  pretende anche per il testo grande.
- **Nessuna sessione dal vivo ha la ROI sotto 0,12**, la più stretta è 0,147 —
  quindi quell'avviso ambra c'era in tutte. O il consiglio è troppo severo, o
  l'area la si disegna sempre più grande di quanto il programma vorrebbe: in
  entrambi i casi è **un avviso che nessuno può soddisfare**, e quelli si
  spengono da soli nella testa di chi li legge.
- **`backup-pre-pulizia` va cancellato prima o poi**, ma **non è mai stato
  spinto** (verificato: sul remoto c'è solo `main`).

---

## Decisioni d'orecchio, ferme da mesi

- **`line_pad` a 0,2 come default**: misurato meglio su tutti e due i giochi, ma
  cambia il gioco principale (130 → 123 battute aperte).
- **`speaker.decide_after_ms` sotto i 500 ms**: adesso è il pezzo più grosso della
  latenza, il doppio della sintesi. Il prezzo è sbagliare più spesso chi parla.
- **`translate.misura_originale`** acceso su una frase molto più lunga
  dell'originale: sta nella scheda Traduzione, spento di serie. Il tradotto resta
  nel riquadro ma il carattere si stringe, e **dove sta il punto in cui si legge
  peggio dell'originale che copre** nessuna misura lo può dire.

---

## Come si prova quello che scrivi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest       # oggi: 12 fallite su 1753, per SAC
.\.venv\Scripts\python.exe -m tools.ui_qt --profile live --loopback voicemeeter `
    --set vision.ocr_backend=oneocr --set tts.backend=kokoro --set tts.device=cuda `
    --set timing.rate_max=1.25 --set translate.enabled=true --set translate.backend=locale
.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella>
.\.venv\Scripts\python.exe -m tools.scatta runs\g --profile gtav [--tutorial] [--lingua de]
```

⚠ **Senza `--no-save`** dal vivo, se no la sessione non finisce in `runs/`.

Sessioni buone per i numeri: `runs/2026-08-20_00-01-56` (Kokoro/CUDA, 146 battute,
latenza p50 **1290 ms**, `mix.underrun` 0, compressione 1,00, OCR 15,9 letture/s),
`runs/2026-08-11_18-31-55` (Piper, 44 battute, **665 ms**).

## Come voglio che tu lavori

- **Scrivi solo quando hai finito.** Non commentare ogni passo.
- **Descrivi in modo semplicissimo ma dettagliato** cosa hai fatto.
- **Non sprecare token.**
- **Prima di azzardare, chiedi.**
- **Interroga il grafo prima di grep** (aggiornato il 20 agosto: 2765 nodi), e
  aggiornalo a fine sessione con `/graphify . --update`.
- **Nei commit non compare mai Claude**, in nessuna forma. L'autore è sempre e
  solo l'utente.

## Le regole di metodo

`CLAUDE.md` le ha per esteso. Le tre che hanno morso di più in questa sessione:

**Controllare che la misura possa esprimere la risposta.** `.venv` diceva «piper
OK» perché quel `.pyd` si apre solo alla prima sintesi, e «ctranslate2 OK» per una
cache legata alla copia del file. Due falsi verdi nella stessa diagnosi.

**Una cura è quasi sempre più stretta del difetto, e la suite verde non lo dice.**
Tre volte in questa sessione: la riga vuota che doveva staccare il separatore (la
risalita salta le righe vuote), `_svuota_sessione(forza=True)` che pulisce solo la
tessera della battuta, e `Motore.acceso` che copriva il caso opposto a quello già
curato. La domanda che le prende è sempre **«cosa faceva prima che adesso non fa
più?»**.

**L'orecchio e l'occhio dell'utente trovano ciò che la suite non può.** L'alt-tab
che «faceva ripartire la lettura» non era un rimedio a caso: era la **firma** del
difetto, perché cambia tutti i pixel in una volta e riapriva il cancello.
