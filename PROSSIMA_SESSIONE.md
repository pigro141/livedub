# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`), doppiaggio
italiano dal vivo dei sottotitoli dei videogiochi.

## Come si conosce questo progetto

**Il grafo è la memoria.** In `graphify-out/graph.json` c'è la mappa della
codebase. Per qualunque domanda architetturale si usa `graphify query "<domanda>"`
**prima** di partire a grep. Si riaggiorna con `graphify update` dopo modifiche
grosse, non a ogni task. (Da riaggiornare: `ui/overlay.py` è stato riscritto e
`tools/prova.ps1` è nuovo.)

Poi `CLAUDE.md`, che ha l'architettura e le regole di metodo. **Non leggere il
README per intero.**

## Come voglio che tu lavori

- **Scrivi solo quando hai finito.** Non commentare ogni passo.
- **Descrivi in modo semplicissimo ma dettagliato** cosa hai fatto.
- **Non sprecare token.**
- **Prima di azzardare, chiedi.**

## Dove siamo, e dove si è fermato il lavoro

**Feature: 14 su 14.** **Step finali: 3 su 18.**

Il lavoro è fermo **al cancello dell'utente**, che l'utente stesso ha messo:
prima la sua prova d'ascolto, con un report di cosa va e cosa no, e solo dopo
l'impacchettamento. Non si passa oltre senza quel report.

La prova si accende con `tools\prova.ps1` (`-Traduci` per il caso tradotto) e il
foglio è **`DA_VERIFICARE.md`**, che dice cosa guardare e cosa serve nel report.

Quello che resta dopo è **solo UI, impacchettamento e repo**, e nessuno dei punti
aspetta una misura:

| blocco | cosa | quanti |
|---|---|---|
| **UI** | interfaccia, selettore tecnologie, impostazioni avanzate con spiegazioni accanto, modifica a caldo | 4 |
| *(cancello)* | **la prova dell'utente** — è qui che siamo | — |
| **distribuzione** | installabile plug-and-play, exe, licenza | 3 |
| **repo** | il repo GitHub più i suoi sette punti | 8 |

## Le due cose che questa sessione ha cambiato

**1. La grafica dell'overlay: guardata, rotta, riparata.** Era l'unico pezzo che
nessuno aveva mai visto funzionare. Messa su un fotogramma a tutto schermo si
vedeva al primo sguardo che la finestra veniva dimensionata sul testo
**originale** mentre dentro ci si disegnava quello **tradotto** — una battuta di
tre righe usciva come la sua riga di mezzo, tagliata. Più: il riquadro nasceva
dall'ingombro grezzo della maschera invece che dalle righe lette dall'OCR, la
sfocatura lasciava leggere l'originale, `background_mode`/`blur_strength` non li
leggeva nessuno dal vivo, e il selettore d'area non spostava l'overlay. Tutto
corretto, tutto guardato a schermo, e la geometria è ora una funzione pura
(`ui.overlay.disposizione`) con il suo gruppo di verifiche.

**2. `accepted_delay_ms` da 250 a 1250, misurato.** La compressione restava a
1250 su *tutti* i percentili con la scena piena a metà. Non era il passo: era la
scusa, tarata quando la parte fissa della catena costava ~670 ms, applicata a una
catena che con la traduzione ne costa 1690. Rigiocando la programmazione di due
sessioni dal vivo archiviate, il precipizio sta fra 900 e 1200 ms e l'altopiano
comincia a 1200. Le due tabelle nuove — con e senza traduzione — stanno accanto
al campo in `core/config.py`.

**Il numero che chiude la questione non l'ho io**: `dub.rate_x1000` deve
staccarsi da 1250 nella prossima sessione dal vivo. È scritto in
`DA_VERIFICARE.md` **prima** della prova, apposta.

## Lo stato dei motori, misurato dal vivo

| | sintesi p50 | note |
|---|---|---|
| **piper** | ~50 ms | CPU. **L'unico sotto i 6 core** |
| **kokoro** (default della prova) | 198-257 ms | CUDA, 1128 MB di VRAM. Sei voci inglesi, due italiane |
| **supertonic** | 313 ms | CPU. A 4 core costa 1315 ms: non usabile |
| ~~qwen~~ | — | **tolto**, e la ragione sta in `CLAUDE.md` |

## Il banco

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                    # 1112 verifiche
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav `
    --start 1240 --end 1290 --set vision.ocr_backend=oneocr --mp4
.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella> [secondo]
.\.venv\Scripts\python.exe -m tools.bench_cpu --backend supertonic   # PC vecchi
.\.venv\Scripts\python.exe -m tools.bench_translate --parolacce      # i traduttori
```

Dal vivo:

```powershell
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci
```

## Le due lezioni di questa sessione

**Un pezzo di codice che nessuno ha guardato non è "scritto", è "supposto" — e
guardarlo costa venti minuti.** L'overlay è stato messo su un fotogramma a tutto
schermo, fotografato e guardato: il difetto era il primo che si vedeva. Nessuna
verifica lo prendeva perché **non esisteva nessuna verifica sull'overlay**, e la
suite verde è stata scambiata per una conferma. Adesso la geometria è una
funzione pura con un gruppo suo, e quel difetto farebbe rosso.

**Una soglia va rimisurata quando cambia la catena, non quando cambia il
sintomo.** `accepted_delay_ms = 250` era misurato bene, su una catena che costava
la metà. Aggiungendo la traduzione sulla strada critica quel numero è diventato
sbagliato senza che nessuno lo toccasse — la quinta volta in questo progetto che
un numero giusto viene applicato a una distribuzione diversa da quella su cui era
stato misurato.

**E il corollario sullo strumento**: la domanda non era rispondibile dal banco.
Con `--tempo-reale` e la traduzione accesa il costo fisso diventa 8,9 secondi, e
a quel punto **nessuna** scusa libera il budget (provato: 250 e 1250 danno la
stessa compressione al tetto). La risposta è venuta rigiocando due sessioni dal
vivo già archiviate, dove i tempi veri erano già scritti. Prima di credere a un
banco, chiedersi se quel banco può esprimere la risposta.

Fine del prompt.
