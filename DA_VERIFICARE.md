# Cosa verificare a mano

Lavoro fatto in autonomia. Qui sotto **solo le cose che io non ho potuto
verificare**, in ordine di quanto costa sbagliarsi. La suite è verde (1039
verifiche) ma la suite non sente niente: ogni difetto serio di questo progetto è
stato trovato dall'orecchio, con la suite verde.

---

## 0. La prova live di Qwen: un comando, e il criterio scritto PRIMA

```powershell
.\.venv\Scripts\python.exe -m tools.ui --profile live --loopback voicemeeter `
    --set vision.ocr_backend=oneocr --set tts.backend=qwen `
    --set tts.device=cuda --set timing.rate_max=1.45
```

Gioca cinque minuti con dialogo fitto, poi chiudi e mandami la cartella
`runs\<timestamp>`.

**Il criterio, dichiarato adesso perché una previsione scritta dopo non può
perdere.** Qwen resta se e solo se, dal vivo su questa 4060:

| numero | soglia | cosa vuol dire se sfora |
|---|---|---|
| `mix.underrun` | **0** | sopra zero la voce si spezza a metà battuta: è il difetto che chiude la partita |
| latenza p50 | **< 2,5 s** | sopra, il doppiaggio arriva quando la scena è cambiata |
| `dub.rate_x1000` p50 | **< 1450** | al tetto significa che comprime sempre al massimo |

**Se `mix.underrun` è > 0 su questa scheda**, la domanda diventa quella che hai
posto tu: esiste hardware consumer che ce la fa? La risposta l'ho già misurata in
parte — il costo è **banda di memoria**, 6,12 GB riletti per ogni 80 ms di audio,
e il tempo segue i byte. Scalando: una 4070 Ti SUPER sta a ~0,30× tempo reale
contro lo 0,75× di questa, una 3090/4090 a ~0,21×. Cioè il margine passa dal 25%
al 70-79%, e **a quel punto il gioco acceso ci sta dentro**.

Quindi il piano è: se qui va male, non togliamo Qwen subito — la conclusione
onesta è «serve una scheda da ~670 GB/s in su». Lo togliamo se anche su quella
classe di hardware non regge, e per saperlo serve provarci sopra.

## 1. Qwen dal vivo — **non l'ho mai provato dal vivo, e va detto per primo**

Tutti i numeri di Qwen sono **di banco**. Sullo streaming c'è un motivo
strutturale: con l'orologio virtuale il produttore non può consegnare in tempo,
quindi sul banco gira dentro il thread. L'audio è identico; il tempo al primo
campione lì non esiste.

**Da fare**: una sessione dal vivo con `--set tts.backend=qwen`.

**Cosa guardare**, in ordine:

- `mix.underrun` nel riepilogo. **Se è maggiore di zero, lo streaming non sta
  dietro** e la voce si interrompe a metà battuta. Me lo aspetto > 0: il modello
  ha il 25% di margine su questa 4060 e il gioco gliene toglie di più.
- la latenza in `speaker.jsonl` contro i ~2,2 s del banco.
- **all'ascolto**: se la voce si spezza a metà parola, è l'underrun; se è
  impastata ma continua, è WSOLA a 1,45.

## 2. WSOLA a 1,45 — decide l'orecchio, non ho un numero

Per far stare Qwen nella scena ho alzato il tetto della compressione a 1,45 in
una prova (`--set timing.rate_max=1.45`), **ben oltre l'1,3 dove le consonanti
spariscono**. Il default resta 1,25 e non l'ho toccato.

**Da fare**: sentire l'MP4 che ti ho mandato. La domanda è una sola — a 1,45 la
voce articola ancora o si mangia le parole?

Se si mangia le parole, Qwen è chiuso e va lasciato spento: senza quel tetto non
ci sta nella scena.

## 3. Le voci di Qwen adesso sono in inglese e concitate

Due cambiamenti che si sentono e che nessun numero giudica:

- le descrizioni sono in **inglese** (il testo da dire resta italiano). Misurato:
  il sesso della voce esce giusto 7 volte su 8 invece di 4-5;
- tutte portano in coda «parla rapidissimo, sillabe fitte, nessuna pausa», che è
  l'unica leva di velocità che quel modello ha. **Costo dichiarato**: tutti i
  personaggi hanno una punta di concitazione che nell'originale non c'è.

**Da fare**: dire se quella concitazione è accettabile o se preferisci voci
naturali e Qwen fuori dai giochi.

## 4. Il nome del parlante — **provato solo su testo finto**

GTA V i nomi non li scrive, quindi le 31 verifiche girano su stringhe scritte da
me. Dicono che il codice fa quello che dichiara, **non** che funzioni su un gioco.

**Da fare**, quando hai una registrazione di un gioco che scrive i nomi:

```powershell
.\.venv\Scripts\python.exe -m tools.dub <video> --profile <gioco> `
    --set label.enabled=true --set label.form="nome:" `
    --set label.names="Nome1,Nome2,Nome3" --mp4
```

**Cosa guardare**:

- `vision.label.hit` nel riepilogo. **Se è zero, il formato dichiarato non è
  quello che il gioco scrive** — prova le altre forme (`[nome]`, `nome-`) o una
  regex.
- nell'MP4: il nome **non deve essere pronunciato**. Se senti «Franklin due punti
  come va», la rimozione non ha funzionato su quel formato.
- che due personaggi diversi prendano due voci diverse.
- la latenza: dovrebbe scendere di ~500 ms rispetto alla stessa scena senza
  etichetta. **È il motivo per cui la feature esiste**, ed è la cosa che vale la
  pena misurare due volte.

Compila sempre `label.names` se puoi: è la guardia che impedisce a un errore di
OCR di diventare un personaggio e di bruciargli addosso una voce del pool.

## 5. SuperTonic sui PC vecchi — cosa ho fatto, in parole semplici

**Il problema**: la lista chiedeva se il programma rallenta su un PC vecchio, e
c'era scritto «serve l'altro PC».

**Cosa ho capito**: un PC vecchio è lento per due motivi diversi — ha **meno
core**, e ogni core è **più lento**. Il primo si può simulare su questa macchina:
dico a Windows «questo programma può usare solo 4 processori» e misuro. Il
secondo no: non posso rendere lenti i core che ho.

**Cosa ho fatto**: ho misurato quanto costa sintetizzare una battuta con 8, 6, 4
e 2 core.

**Cosa è venuto fuori**: SuperTonic passa da mezzo secondo a **1,3 secondi** a
battuta su 4 core. Piper passa da 48 millisecondi a 261. Su un PC a 4 core,
SuperTonic non è usabile e Piper sì.

**Cosa NON ho provato**: core più lenti. Quindi i miei numeri sono il **caso
migliore** — un PC vero, con core anche più lenti dei miei, va peggio di così.

**Cosa ne faccio**: sotto i 6 core il programma dovrebbe usare Piper. Se hai
davvero l'altro PC, la prova vera è farci girare una sessione.

| core fisici | supertonic | piper |
|---|---|---|
| 8 (questa macchina) | 493-573 ms | ~48 ms |
| 4 | **1315 ms** | 261 ms |
| 2 | 3627 ms | 491 ms |

**Conclusione**: sotto i 6 core, `tts.backend=piper`. Se hai davvero l'altro PC a
disposizione, la verifica vera è una sessione lì.

## 4-bis. Il nome del parlante: cosa vuol dire «modulare», in concreto

Te l'avevo spiegato male. In concreto adesso puoi dire al programma **come quel
gioco scrive chi parla**, scegliendo fra sei forme già pronte:

| `label.form` | il gioco scrive |
|---|---|
| `nome:` | `Franklin: Come va` |
| `-nome:` | `- Franklin: Come va` |
| `[nome]` | `[Franklin] Come va`, `(Franklin)`, `<Franklin>` |
| `nome-` | `Franklin - Come va` |
| `nome>>` | `Franklin >> Come va`, `Franklin » Come va` |
| `nome(nota):` | `Franklin (arrabbiato): Come va` |
| `NOME` | `FRANKLIN Come va` (fragile: usare solo con l'elenco dei nomi) |

Se il gioco ne usa un'altra, `label.regex` accetta la tua.

**Oppure il colore**: `label.colors = {"Franklin": "#5ac8fa", "Lamar": "#ffcc00"}`
e ogni battuta va a chi ha il colore più vicino.

**E ogni personaggio ha sempre la stessa voce, per tutto il gioco.** Questo è il
pezzo che mancava e che ho aggiunto adesso: la voce assegnata a un nome viene
scritta in `runs/cast.json` e riletta alla sessione dopo. Senza, la voce non era
del personaggio — era del *turno*: chi apriva la scena prendeva la prima voce del
pool, quindi riaprendo il gioco da un altro punto Franklin ne prendeva un'altra.
Puoi anche deciderle tu: `label.voices = {"Franklin": "riccardo"}`, che vince su
tutto.

Scrivendo la verifica ho trovato un difetto: in due sessioni separate Lamar e
Franklin finivano **tutti e due sulla stessa voce**, perché ognuno era il primo a
parlare nella sua sessione. Ora le voci ricordate si prenotano all'avvio, anche
per chi in quella scena non parla.

## 6. La correzione OCR — è spenta, e ti serve una decisione

L'impalcatura c'è (`vision/correct.py`) con tutte le guardie, ed è **spenta**.
Manca il modello, e non l'ho scelto io di proposito: è una decisione
sull'ambiente — peso su disco e **contesa per la GPU**, che abbiamo appena
misurato essere la risorsa scarsa, con la correzione che gira sul thread video
dove il costo si amplifica.

**L'LLM ora c'è ed è montato** (Gemma 3 1B, `correct.backend=llm`), ma **l'ho
misurato e per il vivo è da lasciare spento**:

| | |
|---|---|
| risposte giuste | **1 su 6** casi veri |
| tempo | **p50 1564 ms** per parola |
| errori | `oulldozer → bulldozers`, `ciassico → biascico`, `uice → ice` (doveva astenersi) |

Contro un guadagno massimo di **una parola su settanta** (`bench_correct
--censimento`: delle 1230 parole «non italiane» su 19146, 527 sono nomi propri e
il resto è onomatopee, forme italiane vere non elencate e frammenti di HUD).

**E la tua idea del contesto l'ho provata con il caso nullo giusto** — stesse
frasi, stesso modello, unica differenza le dieci battute precedenti. Il contesto
**non ha migliorato nessuno dei nove casi e ne ha peggiorati due**, al doppio del
tempo: `ciassico` andava a `classico` senza contesto e a `biascico` con. Un
modello da un miliardo di parametri, con dieci righe davanti, ricopia invece di
ragionare — infatti in traduzione ha restituito parola per parola la traduzione
di due battute prima.

Quindi `context_lines` è a **zero** di default. Il codice resta, perché con un
modello più grande la risposta può cambiare — ma va rimisurata, non ereditata.

**La domanda per te**: vuoi che provi un modello più grande (Gemma 3 4B, ~2,5 GB)?
Su CPU costerebbe ~4 volte il tempo, quindi per il **vivo** è già escluso; avrebbe
senso solo se un giorno la correzione la facessimo fuori dalla catena.

## 7. La traduzione — funziona, ma **non l'ho mai provata con un traduttore vero**

Ho verificato tutto quello che sta *intorno* alla traduzione con un traduttore
finto (`translate.backend=prova`, che rimanda il testo in maiuscolo): il riquadro
che copre l'originale, la sfocatura, i tempi ricalcolati sulla lunghezza nuova.
**Nessuno dei due traduttori veri è mai stato eseguito**, per due motivi
deliberati: `locale` vuole un pacchetto e un modello che non ho installato senza
di te, e `google` avrebbe mandato i tuoi sottotitoli a Google.

**Il traduttore LLM invece l'ho provato**: 254 ms p50, qualità da modello piccolo
ma sensata («Oggi recuperiamo veicoli comprati da idioti a tassi esorbitanti»).
Sta sulla strada critica, quindi quei 254 ms si sommano a ogni battuta nuova — la
cache li paga una volta sola per battuta. Si accende con
`--set translate.backend=llm`.

**Per provare quello leggero (Argos)**:

```powershell
.\.venv\Scripts\python.exe -m pip install argostranslate
.\.venv\Scripts\python.exe -m translate.locale --scarica en it
.\.venv\Scripts\python.exe -m tools.dub <video-inglese> --profile <gioco> `
    --set translate.enabled=true --set translate.backend=locale `
    --set translate.source=en --set translate.target=it `
    --set translate.background_mode=blur --mp4
```

**Cosa guardare**:

- che il riquadro/la sfocatura cada **sul** sottotitolo del gioco. Se cade
  altrove, la ROI del profilo non è tarata per quel gioco: si rifà con
  `tools/calibrate.py`.
- che la voce dica il **tradotto** e non l'originale.
- il tempo: la traduzione sta sulla strada critica e ogni battuta ne paga il
  costo la prima volta. Se la latenza sale molto, quel backend non è adatto lì.

Prova anche `--set translate.background_mode=riquadro` per confrontare a occhio:
il blur è meno invadente ma copre meno; il riquadro copre tutto ma mette una
macchia in mezzo al gioco. **Non c'è un numero che lo decida.**

## 8. Il filtro blur — verificato, ma su GTA V è un caso degenere

L'ho misurato: nitidezza della ROI a **0,00** dentro gli intervalli e **1,00**
fuori, cioè sfoca dove deve e non tocca niente altrove. Ma l'ho provato
traducendo l'italiano in MAIUSCOLO, non da una lingua vera.

L'MP4 che ti mando è quello: serve a giudicare **la grafica**, non la traduzione.
Guarda se il testo bianco maiuscolo copre bene l'originale sfocato sotto, e se la
dimensione ti sembra giusta (`translate.font_frac`, oggi 0,038 dell'altezza).

---

## Quello che invece è verificato e non richiede niente

- lo streaming consegna **la stessa battuta** di `synthesize`, campione per
  campione, e le giunture non aggiungono errore (`bench_qwen --pezzi`);
- il ciclo autoregressivo srotolato è fedele all'originale (scarto: un passo di
  quantizzazione a 16 bit, cioè solo la scrittura del WAV);
- le guardie della correzione reggono anche con un correttore sconsiderato: una
  parola italiana non gli viene nemmeno proposta;
- la sfocatura è applicata **solo** negli istanti dichiarati (ROI a 0,00 dentro,
  1,00 fuori);
- se la traduzione fallisce o esplode, si dice l'originale invece di restare muti;
- 1064 verifiche verdi.

---

## La decisione che resta tua, e non è una verifica

**Google Translate manda ogni sottotitolo ai server di Google.** L'ho montato
perché me l'hai chiesto, ma è spento e il default è `locale`: nella tua stessa
lista di step finali c'è «valorizzazione dell'uso completamente locale ed estrema
privacy», e le due cose non stanno insieme. Quando accendi `google` il programma
te lo dice su stderr, così chi usa il tuo software lo sa senza leggere i
documenti.

Se il repo pubblico vuole vendere la privacy come punto di forza, la strada
onesta è tenere `locale` come default dichiarato e `google` come opzione che
l'utente accende sapendo cosa fa — che è esattamente com'è adesso.
