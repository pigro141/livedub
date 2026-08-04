# Cosa verificare a mano

Lavoro fatto in autonomia. Qui sotto **solo le cose che io non ho potuto
verificare**, in ordine di quanto costa sbagliarsi. La suite è verde (1039
verifiche) ma la suite non sente niente: ogni difetto serio di questo progetto è
stato trovato dall'orecchio, con la suite verde.

---

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

## 5. SuperTonic sui PC vecchi — misurato, ma con un limite dichiarato

Ho simulato il PC vecchio riducendo i core. **Non ho simulato core più lenti**,
quindi i numeri sono un limite inferiore: un PC vero sta peggio.

| core fisici | supertonic | piper |
|---|---|---|
| 8 (questa macchina) | 493-573 ms | ~48 ms |
| 4 | **1315 ms** | 261 ms |
| 2 | 3627 ms | 491 ms |

**Conclusione**: sotto i 6 core, `tts.backend=piper`. Se hai davvero l'altro PC a
disposizione, la verifica vera è una sessione lì.

## 6. La correzione OCR — è spenta, e ti serve una decisione

L'impalcatura c'è (`vision/correct.py`) con tutte le guardie, ed è **spenta**.
Manca il modello, e non l'ho scelto io di proposito: è una decisione
sull'ambiente — peso su disco e **contesa per la GPU**, che abbiamo appena
misurato essere la risorsa scarsa, con la correzione che gira sul thread video
dove il costo si amplifica.

**Prima di decidere, guarda questo**:

```powershell
.\.venv\Scripts\python.exe -m tools.bench_correct --censimento
```

Dice che gli errori davvero correggibili sono **circa una parola su settanta**:
delle 1230 parole «non italiane» su 19146, 527 sono nomi propri e il resto è in
buona parte onomatopee, forme italiane vere non elencate e frammenti di HUD.

**La domanda per te**: con un guadagno di una parola su settanta, quanto sei
disposto a pagare in latenza e in rischio? Io un modello sulla GPU non ce lo
metterei finché la GPU serve alla sintesi.

*(Se lo vuoi comunque, la forma giusta è un modello che **ordina i candidati** di
`candidati()` dato il contesto, non che genera testo libero: così non può
inventare una non-parola e la fiducia esce dal distacco fra i primi due.)*

## 7. La traduzione — funziona, ma **non l'ho mai provata con un traduttore vero**

Ho verificato tutto quello che sta *intorno* alla traduzione con un traduttore
finto (`translate.backend=prova`, che rimanda il testo in maiuscolo): il riquadro
che copre l'originale, la sfocatura, i tempi ricalcolati sulla lunghezza nuova.
**Nessuno dei due traduttori veri è mai stato eseguito**, per due motivi
deliberati: `locale` vuole un pacchetto e un modello che non ho installato senza
di te, e `google` avrebbe mandato i tuoi sottotitoli a Google.

**Per provare quello locale**:

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
