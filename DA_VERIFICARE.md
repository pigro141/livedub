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

## 7. Una cosa su cui voglio il tuo permesso, non la tua verifica

Per la traduzione avevi detto «Google Translate via API oppure Gemma 3». **L'API
manda i sottotitoli a Google**, e nella tua stessa lista di step finali c'è
«valorizzazione dell'uso completamente locale ed estrema privacy». Sono due cose
che non stanno insieme, e la scelta è tua, non mia: non ho scritto niente né in
un verso né nell'altro.

---

## Quello che invece è verificato e non richiede niente

- lo streaming consegna **la stessa battuta** di `synthesize`, campione per
  campione, e le giunture non aggiungono errore (`bench_qwen --pezzi`);
- il ciclo autoregressivo srotolato è fedele all'originale (scarto: un passo di
  quantizzazione a 16 bit, cioè solo la scrittura del WAV);
- le guardie della correzione reggono anche con un correttore sconsiderato: una
  parola italiana non gli viene nemmeno proposta;
- 1039 verifiche verdi.
