# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`), doppiaggio
italiano dal vivo dei sottotitoli dei videogiochi.

## Come si conosce questo progetto

**Il grafo è la memoria.** In `graphify-out/graph.json` c'è la mappa della
codebase. Per qualunque domanda architetturale si usa `graphify query "<domanda>"`
**prima** di partire a grep. **È aggiornato** a fine sessione (1476 nodi, 3651
archi, 97 comunità): ci sono dentro `translate/`, `ui/overlay.py`,
`vision/label.py`, `vision/correct.py`, `core/onnx.py`, e non c'è più
`speak/backends/qwen.py`. Si riaggiorna con `graphify update` dopo modifiche
grosse, non a ogni task.

Poi `CLAUDE.md`, che ha l'architettura e le regole di metodo. **Non leggere il
README per intero.**

## Come voglio che tu lavori

- **Scrivi solo quando hai finito.** Non commentare ogni passo.
- **Descrivi in modo semplicissimo ma dettagliato** cosa hai fatto.
- **Non sprecare token.**
- **Prima di azzardare, chiedi.**

## Dove siamo

**Feature: 14 su 14.** Tutte chiuse, comprese quelle chiuse con un "no" misurato.
**Step finali: 2 su 18**, più una scritta e mai vista funzionare (la grafica
dell'overlay).

Quello che resta è **solo UI, impacchettamento e repo** — e nessuno dei punti
aspetta una misura. È il contrario di tutto il lavoro precedente.

| blocco | cosa | quanti |
|---|---|---|
| **UI** | interfaccia, selettore tecnologie, impostazioni avanzate con spiegazioni accanto, modifica a caldo | 4 |
| *(cancello)* | **la prova dell'utente, con report di cosa va e cosa no** | — |
| **distribuzione** | installabile plug-and-play, exe, licenza | 3 |
| **repo** | il repo GitHub più i suoi sette punti | 8 |

Il cancello in mezzo l'ha messo l'utente e va rispettato: la sua prova viene
prima di impacchettare.

## Lo stato dei motori, misurato dal vivo

| | sintesi p50 | note |
|---|---|---|
| **piper** (default) | ~50 ms | CPU. **L'unico sotto i 6 core** |
| **kokoro** | 198-257 ms | CUDA, 1128 MB di VRAM. Sei voci inglesi, due italiane |
| **supertonic** | 313 ms | CPU. A 4 core costa 1315 ms: non usabile |
| ~~qwen~~ | — | **tolto**, e la ragione sta in `CLAUDE.md` |

## LEGGI PRIMA `DA_VERIFICARE.md`

La sessione precedente si e' chiusa con il PC spento e non e' piu' riapribile.
Tutto quello che andava detto sta nei file, e l'ordine giusto e':

1. **`DA_VERIFICARE.md`** — cosa non e' stato provato e come provarlo. La prima
   voce e' la grafica dell'overlay, **scritta e mai vista a schermo**.
2. **`SviluppoProgetto.md`** — la lista, con l'esito di ogni voce.
3. Questo file, per il contesto.

## Le due cose che l'ultima sessione ha lasciato aperte

**1. La prova dal vivo con traduzione, giudicata a orecchio.** I numeri dicono
che va: 18 battute, zero underrun, sintesi 198 ms, traduzione pulita
(`'Ehi, come va, Simeon?'` → `"Hey, how's it going, Simeon?"`). L'ultima passata
girava con il passo dell'inglese appena corretto, e nessuno ha ancora detto **come
suonava** — in particolare se l'overlay cade sul sottotitolo e non dà fastidio.

**2. La correzione OCR resta spenta**, ed è una decisione già presa con i numeri
in mano: `translategemma:4b` fa 5 su 8, ma **1784 ms per parola**, contro un
guadagno massimo di una parola su settanta. Buona per il banco, non per il vivo.

## Le tre cose da fare per prime, in ordine

1. **Guardare l'overlay a schermo.** E' l'unico pezzo di codice di quella sessione
   che nessuno ha mai visto funzionare. `DA_VERIFICARE.md` dice dove guardare se
   cade nel posto sbagliato.
2. **Alzare `accepted_delay_ms` e rimisurare.** La compressione resta al tetto
   (1250 su *tutti* i percentili) con il parlato che riempie il 41% della scena:
   non e' il passo, e' la traduzione sulla strada critica che mangia il budget.
   La cura e' quel campo — che esiste apposta per «la parte che torna identica a
   ogni battuta» — ma la tabella di `fuse/timing.py` va rifatta a traduzione
   accesa, perche' quella dice 250 ms misurati **senza**.
3. **Poi la UI**, che e' l'unico blocco rimasto prima del cancello dell'utente.

## Il banco

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                    # 1098 verifiche
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav `
    --start 1240 --end 1290 --set vision.ocr_backend=oneocr --mp4
.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella> [secondo]
.\.venv\Scripts\python.exe -m tools.bench_cpu --backend supertonic   # PC vecchi
.\.venv\Scripts\python.exe -m tools.bench_translate --parolacce      # i traduttori
.\.venv\Scripts\python.exe -m tools.bench_correct --censimento       # l'OCR
```

Dal vivo, con traduzione grafica e audio:

```powershell
.\.venv\Scripts\python.exe -m tools.ui --profile live --loopback voicemeeter `
    --set vision.ocr_backend=oneocr --set tts.backend=kokoro --set tts.device=cuda `
    --set translate.enabled=true --set translate.backend=ollama `
    --set translate.source=it --set translate.target=en
```

## La lezione di questa sessione, che vale più del resto

**La stessa unità sbagliata, per la quarta volta.**

Dopo `chars_per_second` contato in due unità diverse, dopo `merge_similarity`
misurata su una distribuzione e applicata a un'altra, dopo il passo di un motore
applicato a un altro — questa volta è stato **il passo di una lingua applicato a
un'altra**. Tradotto in inglese, la catena usava i 12,9 car/s misurati
sull'italiano: credeva ogni battuta più lunga di quanto fosse, e comprimeva al
tetto una scena piena **al 49%**. Compressione autoinflitta, con tutto il tempo
del mondo a disposizione.

Il sintomo era `dub.rate_x1000` a 1250 su *tutti* i percentili. Un numero
inchiodato al tetto su ogni percentile non è mai una coincidenza: è sempre un
vincolo che morde da un'altra parte.

**E la seconda: il banco non può vedere i difetti che esistono solo dal vivo — di
nuovo, due volte.** Lo streaming partiva a suonare prima di aver generato
(invisibile sul banco, dove il produttore genera tutto e poi ritorna), e la
sostituzione grafica non esisteva affatto dal vivo perché sul banco la disegna
ffmpeg. Ogni volta che una cosa "funziona sul banco", la domanda successiva è
**cosa fa il vivo che il banco non fa**.

Fine del prompt.
