Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`),
doppiaggio italiano dal vivo dei sottotitoli dei videogiochi.

## Dove siamo, in tre righe

**Il repo è pubblicato**: <https://github.com/pigro141/livedub>, sito su
<https://pigro141.github.io/livedub/>. `main` è pulito e spinto.

**Il difetto aperto più grave**: Smart App Control di Windows 11 — acceso di
serie sulle installazioni pulite — blocca alcune DLL. **L'eseguibile non parte
affatto**; la cattura per finestra e il modello locale non hanno più un errore
grezzo ma una **rinuncia dichiarata**, e la cattura per finestra ha di nuovo una
strada che funziona. Vedi «Cosa è rotto adesso» e «Il ramo
`sac-rinunce-dichiarate`».

**La suite su questa macchina dà 12 fallite**, ed è quel blocco, **non una
regressione del codice**: misurato su `main` da solo, con l'albero pulito (12 su
1753) e poi sul ramo (12 su **1795**, cioè quarantadue verifiche in più e **le
stesse dodici**). Finché SAC morde il criterio è **«non aggiungere fallite
rispetto a HEAD»**, non «tutto verde».

Le dodici, per non ricercarle: `argostranslate` non si importa (torch/`shm.dll`
bloccata) e con lei cadono `traduzione`, `etichetta`, `velocita`, `memoria`,
`coerenza`, `audio_source`; `cv2` bloccata e con lei `ocr`, `overlay`, `gioco2`,
`lines` (due) e `diff`.

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

**«Firmarlo forse basta» adesso ha una risposta, e sono tre**, tutte da
documentazione Microsoft e non da intuizione:

1. **Il self-signed non serve a niente.** La tabella di
   [SmartScreen reputation][ss] mette *Self-signed Certificate* e *No signature*
   sulla stessa riga, e la pagina [Sign your app for Smart App Control][sac] dice
   che «Code can be signed with any certificate, but Smart App Control **only
   considers certificates issued by trusted providers**». Chiuso: non è una
   strada.
2. **Un certificato vero (OV o EV) non sblocca subito**, e l'EV non compra più
   niente: «EV certificates no longer bypass SmartScreen». Quello che compra la
   firma è **un'altra cosa e più importante**: «Signing files using a trusted
   certificate can allow certificate reputation to build… Unsigned files must
   build reputation anew with **every** update». Cioè la firma è l'unica cosa
   che rompe il giro «ogni build è un file nuovo, quindi reputazione zero per
   costruzione».
3. **La sottomissione a WDSI non è una strada, ed è scritto.** «There is no need
   (or mechanism) to manually submit a file for SmartScreen reputation review
   **for consumer endpoints**. Reputation builds organically through download
   volume.» È riservata agli amministratori d'impresa.

**La strada che costa zero e che non era stata cercata: il Microsoft Store.**
«Apps published through the Microsoft Store are re-signed by Microsoft and carry
**full reputation**», e dal 2026 la registrazione dello sviluppatore
**individuale è gratuita** in circa 200 mercati (Italia compresa) — bastano
documento e selfie, e il negozio accetta app Win32 impacchettate in MSIX «without
modifying existing code». È l'unica opzione che non chiede né una partita IVA né
un abbonamento.

**Azure Artifact Signing (ex Trusted Signing) non è disponibile a un privato
italiano.** La pagina ufficiale, aggiornata l'11 agosto 2026: «Public Trust
certificates are available to organizations in the United States, Canada, the
European Union… **Individual developers must be located in the United States or
Canada**». Da un'impresa UE sì: 9,99 $/mese, validazione d'identità da **1 a 20
giorni lavorativi**. I tre anni di storia non servono più.

**SignPath Foundation** firma gratis i progetti open source (licenza approvata
OSI, nessun componente proprietario, progetto mantenuto e già rilasciato, build
verificabile dal sorgente, doppia autenticazione e una *code signing policy*
pubblicata sul sito del progetto). Il certificato però è **intestato a SignPath
Foundation**, non all'utente. Nessun requisito dichiarato di popolarità o età.

[ss]: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation
[sac]: https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/code-signing-for-smart-app-control

**Per ora il README pubblicato indica `installa.ps1` e non l'exe**, quindi chi
scarica ha una strada che funziona. Non promettere l'exe finché non parte.

### 2. `windows_capture` non ha nessuna versione che passi — **e non serve più**

Provate 2.0.1 / 2.0.0 / 1.5.0 / 1.4.4: tutte bloccate. Provato anche **l'unico
altro pacchetto che espone la stessa API**, `winrt-Windows.Graphics.Capture` di
pywinrt, in tutte e cinque le versioni pubblicate (3.2.1 / 3.1.0 / 3.0.0 / 2.3.0
/ 2.0.1): bloccato pure lui, e con lui `winrt-runtime`. Non è quella libreria: è
**ogni file nuovo**.

**La strada che funziona non ha nessun file da far accettare**: `PrintWindow`
con `PW_RENDERFULLCONTENT`, che sta in `user32.dll`. Cattura **la stessa
finestra**, quindi tornano tutte e tre le cose che quella scelta aveva risolto —
l'overlay non rientra nella cattura, la ROI segue il gioco, non c'è niente da
ritagliare. Sta in `capture/printwindow.py`, e `capture.screen.apri_finestra`
prova WGC e ci ripiega **dicendolo**.

Costo misurato, dieci passate per riga, finestra 1278x1391: **17,6 ms** intera,
**6,2 ms** la sola fascia che si legge (la fascia si prende spostando l'origine
del DC, ed è la stessa idea di `capture.solo_roi` applicata a una finestra).
Verificato sull'immagine che il contenuto sia vero e non la sola cornice: la
pagina di Chrome — contenuto composto in GPU — arriva intera.

**Il difetto che resta è dichiarato, non nascosto.** Su un gioco Direct3D con
una catena di scambio *flip model* non c'è una superficie di redirezione, e
`PrintWindow` **riesce e restituisce nero** — che non è un errore: la sessione
resta accesa, i contatori restano verdi e sembra rotto l'OCR.
`PrintWindowSource.nero` guarda i primi otto fotogrammi e lo dice, e il ciclo
video scrive nel registro cosa fare.

⚠️ **Quello che nessuno ha ancora potuto provare è proprio GTA V.** Il nero o
non-nero su un gioco vero si vede in trenta secondi accendendolo: è la prima
cosa da fare la prossima sessione, e la risposta decide se serve riscrivere WGC
in `ctypes` (mezza giornata, si veda «Le decisioni che restano»).

### 3. `llama-cpp-python` idem, e il pezzo non era nemmeno un `.pyd`

Provate 0.3.35 / 0.3.34 / 0.3.2 da PyPI **più la ruota dell'indice CPU di
abetlen**, che è un file diverso e meritava una prova a sé: bloccata pure quella.
Qui il pezzo nativo è `llama_cpp/lib/llama.dll`, aperta con `ctypes` — cioè il
criterio non guarda **come** si carica una libreria, guarda **quale**.

**E la guardia scritta apposta non poteva scattare.** `translate/llm.py`
prendeva `ImportError`; quello che esce è un **`RuntimeError`**, perché a
sollevare è `ctypes` dentro il modulo. Ottava volta della forma «una verifica che
non può fallire proprio nel caso per cui esiste». Adesso passa da
`core/bloccati.py`.

### E c'è un quarto blocco che il passaggio di consegne non aveva

**Su questa macchina, oggi, sono bloccati anche `cv2` e `torch/shm.dll`** — e
quest'ultimo porta giù `argostranslate`, cioè **il default** di
`translate.backend`. Il banco della guida prometteva `locale` lo stesso, perché
la sonda usava `find_spec`: il file c'è sul disco, quindi trovato; poi Windows
si rifiuta di caricare quello che ci sta dentro. Adesso `sonda_veloce` **carica**
invece di cercare, e dice `traduzione_manca`.

E `cv2` bloccato non è innocuo: sfocatura e cancellatura lo importano **dentro la
funzione che dipinge**, cioè dentro il ciclo video, quindi il difetto sarebbe
uscito come un `ImportError` su un fotogramma qualunque — dove nessuno lo collega
alla riga che l'ha acceso. Adesso lo si guarda quando si costruisce l'overlay e
si dice cosa non si potrà fare; il tradotto si disegna lo stesso, con
`translate.background_mode=riquadro`, che quel pezzo non lo usa (e per
costruzione non ha nemmeno il ritardo).

---

## Il ramo `sac-rinunce-dichiarate`, e cosa ci sta dentro

Locale, parte da `main`, non spinto. Quattro pezzi, e tutti e quattro rispondono
alla stessa domanda: **come si dice che qualcosa non si può fare qui.**

**`core/bloccati.py`** — l'unico posto che sa rispondere a «questo pezzo si
carica su questa macchina?», e risponde con un codice più una frase invece che
con un'eccezione. Quattro stati (`ok`, `criterio`, `assente`, `guasto`) e non
due, perché «non l'hai installato» e «c'è e Windows non lo carica» chiedono
all'utente due cose diverse: la prima si cura con un `pip install`, la seconda
no. `RINUNCE` è la stessa distinzione di `core.banco.AVVISI`.

Due cose che non si vedono leggendo il codice in fretta:

- **la frase del blocco non è scritta a mano.** È tradotta — «Un criterio di
  controllo dell'applicazione ha bloccato il file» qui, «An Application Control
  policy has blocked this file» su una macchina inglese — e cercarne una scritta
  a mano avrebbe riconosciuto il blocco **solo in italiano**, cioè avrebbe
  ricreato l'errore incomprensibile in quaranta lingue. La si chiede a Windows
  con `FormatMessageW(4551)` e la si confronta. Il numero si legge quando c'è
  (`OSError.winerror`, cioè un `ctypes.CDLL` fallito); da un `import` fallito
  **non c'è**, e quello è l'unico motivo per cui il confronto sulla frase serve;
- **`prova()` accetta un `usa`**, perché importare non è usare: `piper` importa
  e muore alla prima sintesi, `llama_cpp` apre la sua DLL con `ctypes`. È la
  stessa lezione già pagata con `.venv` che diceva «piper OK».

**`capture/printwindow.py`** — la cattura di una finestra sola senza niente da
installare. Si veda il punto 2 qui sopra.

**Il pannello non offre più una scelta che darà un errore.**
`core.bloccati.SCELTE` mappa i campi ai pezzi (`translate.backend=llm` → `llm`,
`translate.backend=locale` → `argos`, `correct.backend=llm`, `capture.backend=wgc`)
e `SceltaFra` marca quelle voci con un `⚠`. Il perché sta **sulla casella
chiusa** e non solo sulla voce in elenco, che è il dettaglio che rende l'avviso
utile: il valore che non funziona è quasi sempre quello **già scritto in
configurazione**, e quello lo si vede senza aprire niente — un segno senza
spiegazione è metà dell'avviso, e la metà che serve è l'altra.

**Si marca, non si toglie**: togliere una voce nasconderebbe che il programma la
sa fare e che il difetto è di questa macchina. La regola sta in `core/` e non in
Qt, per la ragione già scritta in `CLAUDE.md`.

**Il banco carica invece di cercare.** `sonda_veloce` usava `find_spec`, che
trova il file sul disco e non sa che Windows si rifiuterà di caricarlo: il passo
6 concludeva «traduzione: llm», scriveva `translate.backend = llm` e consegnava
una sessione che muore alla prima battuta. È esattamente ciò che `applica()`
esiste per non fare — *scrive quello che ha verificato, non quello che ha
scelto* — e per verificarlo bisogna caricarlo.

**E la sonda del pannello ha un tetto** (`ENTRO_MS`, 400 ms), che non è
prudenza: **una prova che riesce può costare più di una che fallisce.** Qui un
pacchetto bloccato risponde in 49-157 ms — la DLL non si apre e basta — ma
`argostranslate` che *funziona* tira dentro stanza e torch, cioè secondi.
Pagarli mentre si disegna una scheda vorrebbe dire una finestra lenta per
scrivere un avviso che quasi sempre non serve. Sforato il tetto **non si marca**:
non marcare non promette niente, marcare a torto sarebbe un avviso che nessuno
può soddisfare. La prova intanto continua e finisce in cache. Chi invece *deve*
sapere prima di partire — `make_traduttore`, `make_correttore`, il banco — chiama
`pezzo()` e aspetta.

**Due gruppi nuovi nella suite**: `bloccati` e `finestra-gdi`, 85 verifiche, più
quattro nel gruppo `manopole`. Girano senza rete.

**E una riga in `livedub.spec`.** `capture.printwindow` si importa **dentro una
funzione**, quindi l'analisi statica di PyInstaller non lo vede: senza
`hiddenimports`, il pacchetto verrebbe su lo stesso e morirebbe all'Avvia
proprio sulla macchina che ne ha bisogno.

---

## Le decisioni che restano all'utente

**Prima di tutto, una misura che costa trenta secondi**: accendere GTA V e
guardare se la cattura per finestra dà nero. Il registro lo dice da solo
(«questo gioco non si lascia catturare per finestra»). Da quella riga dipende
tutto il resto di questo elenco.

1. **Se PrintWindow su GTA V non dà nero**: non c'è altro da fare per il punto 2.
2. **Se dà nero**: l'unica strada che resta senza file nuovi è **riscrivere WGC
   in `ctypes`** — `RoGetActivationFactory` di `combase.dll`,
   `IGraphicsCaptureItemInterop::CreateForWindow`, `Direct3D11CaptureFramePool`,
   e i pixel via `IDirect3DDxgiInterfaceAccess` + una texture di staging. Sono
   tutte DLL di Windows, quindi fuori dal criterio per costruzione. **Cercata:
   non esiste già fatta** — le implementazioni Python che si trovano
   (`py-windows-graphics-capture`, `wincam`, D3DShot) usano tutte o `winsdk`
   (bloccato) o una DLL C++ propria (un file nuovo). È mezza giornata di lavoro
   e va autorizzata.
3. **Per l'eseguibile**, in ordine di costo:
   - **Microsoft Store**, 0 €: registrazione individuale gratuita dal 2026 in
     ~200 mercati, documento e selfie, accetta Win32 in MSIX senza cambiare
     codice, e Microsoft **rifirma il pacchetto** dandogli reputazione piena.
     È anche l'unica strada che potrebbe sistemare i punti 2 e 3 insieme, perché
     riguarda il pacchetto intero e non il solo `.exe`;
   - **SignPath Foundation**, 0 €: certificato intestato a SignPath, condizioni
     nel punto 1 qui sopra;
   - **Azure Artifact Signing**, 9,99 $/mese: **serve un'impresa** — a un privato
     italiano è chiuso, e questo è documentato, non dedotto.

   E le due cose da sapere prima di scegliere. **Firmare non sblocca subito**,
   ma è l'unica cosa che fa accumulare reputazione **al certificato** invece che
   al singolo file: senza firma ogni build riparte da zero, per sempre. E un
   certificato **non serve solo all'`.exe`** — un `.pyd` è un PE come gli altri,
   quindi la costruzione potrebbe rifirmare anche le librerie bloccate che
   impacchetta (sono tutte MIT). Non è una cosa provata, è una cosa da provare
   il giorno che un certificato ci sarà; ma è il motivo per cui il punto 3 non
   riguarda solo il punto 1.

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
- **Il grafo non è stato aggiornato, e il motivo è il difetto stesso**:
  `graphify.exe` è uno degli exe-guscio di pip, e Smart App Control lo blocca —
  `Permission denied`, come `pip.exe`. Non è raggiungibile nemmeno come modulo
  Python da qui. Due moduli nuovi (`core/bloccati.py`, `capture/printwindow.py`)
  aspettano quindi un `/graphify . --update` fatto da un ambiente che lo possa
  lanciare.
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
.\.venv\Scripts\python.exe -m tools.selftest       # oggi: 12 fallite su 1795, per SAC
.\.venv\Scripts\python.exe -m tools.selftest bloccati finestra-gdi   # le rinunce dichiarate
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

`CLAUDE.md` le ha per esteso. Tre nuove, dalla sessione sulle rinunce:

**«Non c'è una versione che passi» non è «non si può fare».** La domanda su cui
ci si era fermati era *quale versione di `windows_capture` carica*, e la risposta
è «nessuna», per tutte e due le librerie che esistono. Ma la domanda giusta era
un'altra: **cosa mi dà quella dipendenza che Windows non mi dia già**. La cattura
di una finestra sola sta in `user32.dll` da vent'anni. È la stessa forma già
scritta in `CLAUDE.md` — *prima di dire che una cosa non si può fare, guardare
cosa si ha già in mano* — e stavolta è costata una funzione dichiarata morta.

**Una guardia scritta per un caso può non poterlo prendere.** `translate/llm.py`
aveva un `except ImportError` con dentro il messaggio giusto, e il blocco esce
come `RuntimeError` perché a sollevare è `ctypes`. Ottava volta: la verifica c'è,
dice a parole la cosa giusta, e **non può fallire proprio nel caso per cui
esiste**.

**`find_spec` risponde «c'è il file», non «si carica».** Il banco lo usava per
decidere quale traduttore promettere all'utente. Su una macchina con SAC acceso
sono due cose diverse, e la seconda è l'unica che conta: *si scrive quello che si
è verificato, non quello che si è scelto*.

E le tre della sessione precedente, che valgono ancora:

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
