# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`), doppiaggio
italiano dal vivo dei sottotitoli di GTA V.

## Come si conosce questo progetto

**Il grafo è la memoria.** In `graphify-out/graph.json` c'è la mappa della
codebase, già costruita. Per qualunque domanda architetturale — dove sta X, cosa
rompo se tocco Y, chi chiama cosa — si usa

```
graphify query "<domanda>"
```

**prima** di partire a grep. Costruirlo è caro, interrogarlo no. Si aggiorna con
`/graphify . --update` dopo modifiche grosse, non a ogni task.

Poi `CLAUDE.md`, che contiene l'architettura e le regole di metodo. **Non leggere
il README per intero**: costa e non serve.

## Come voglio che tu lavori

- **Scrivi solo quando hai finito.** Non commentare ogni passo.
- **Descrivi in modo semplicissimo ma dettagliato** cosa hai fatto. Poche righe,
  concrete, senza gergo inutile.
- **Non sprecare token.** Niente riassunti di cose che ho già letto, niente
  elenchi di opzioni che non seguirai.
- **Prima di azzardare, chiedi.** Se una scelta cambia il risultato e non è
  ovvia, fermati e chiedimi. Meglio una domanda che mezza giornata sbagliata.

## L'obiettivo

**Fare tutte le voci di `SviluppoProgetto.md` e completare il progetto.** Quel
file è la lista, con spuntate quelle già fatte e una riga di esito per ognuna.

## Cosa resta, in ordine di quanto vale

**1. Lo streaming di Qwen3-TTS.** È il pezzo più grosso e il più promettente.
Misurato: il modello gira a **0,66× tempo reale**, quindi in streaming la latenza
al primo campione sarebbe **320-430 ms** contro i 174 di Kokoro — vivibile su GPU
consumer, con voci **illimitate** (si descrivono a parole) invece delle due
italiane di Piper e Kokoro. Il backend c'è già (`speak/backends/qwen.py`) e
funziona, ma **senza streaming costa 3,1 s a battuta**, cioè non è usabile dal
vivo. Lo streaming non si aggiunge nel backend: la catena sintetizza, *poi* misura
la durata, *poi* calcola la fretta WSOLA, *poi* programma, e il mixer tiene un
array fisso — quindi tocca `mix/mixer.py` e `fuse/timing.py`. Prezzo dichiarato:
**4,2 GB di VRAM** contro i 1128 MB di Kokoro.

**2. Il nome del parlante scritto dal gioco.** Se un gioco scrive chi parla, lo si
legge e si spengono i **500 ms** di `decide_after_ms` — che oggi costano *il doppio
della sintesi*. Non misurabile su questa registrazione (GTA V i nomi non li
scrive), quindi serve materiale di un altro gioco. Va sulla UI come interruttore.

**3. La traduzione con riquadro grafico.** La feature più grande, e apre il
prodotto ad altre lingue.

**4. L'LLM per gli artefatti OCR.** Leggere **prima** il docstring di
`vision/lexicon.py`: la correzione automatica è già stata provata e bocciata (2
risposte giuste su 8, e gli errori erano `rapinato` → `rovinato`, cioè una parola
vera al posto di un'altra). Un LLM sbaglia allo stesso modo, meglio e quindi più
pericolosamente. Ha senso solo se **dichiara quando non è sicuro**.

**5. Gli step finali**: UI, impostazioni live, exe, licenza, repo.

## Cose sospese che vanno chiuse

- **La taratura del genere non è mai stata provata su una donna**: nella
  registrazione non ce n'è una. Serve materiale nuovo.
- **`tokenizers` è installato nel `.venv` e non è in `requirements.txt`**. Serve
  al backend Qwen. Va messo o tolto.
- **`preload_dlls()` vive solo dentro `speak/backends/kokoro.py`.** Senza quella
  riga ORT non trova le DLL CUDA dei pacchetti `nvidia-*` e ripiega sulla CPU
  **in silenzio**. Chiunque aggiunga un backend ONNX ci cade — è già successo due
  volte. Va spostata dove la vede chiunque apra una sessione ONNX.
- **Un terzo delle battute dal vivo esce con la voce neutra** (18 su 66
  nell'ultima sessione). Non è un difetto della voce neutra, che sta dicendo la
  verità: è che il riconoscitore non arriva a `name_min_score` abbastanza spesso.
  Nessuno lo sta guardando.

## Lo stato, in numeri veri

Motori, misurati **dal vivo** (non sul banco):

|  | sintesi p50 | latenza totale p50 | dove gira |
|---|---|---|---|
| **piper** (default) | ~50 ms | ~670 ms | CPU |
| **kokoro** | 174-257 ms | ~1150 ms | CUDA |
| **supertonic** | 313 ms | ~1300 ms | CPU — il livello senza GPU |
| **qwen** | 3,1 s | non usabile | CUDA, manca lo streaming |
| chatterbox | 3,4 s | non usabile | solo offline |

Ultima sessione dal vivo: **69 battute in 153 s**, 14 con voce neutra.

## Il banco, che è lo strumento di tutto

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                  # 952 verifiche
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav `
    --start 1240 --end 1340 --set vision.ocr_backend=oneocr --mp4
.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella> [secondo]
.\.venv\Scripts\python.exe -m tools.ui --profile live --loopback voicemeeter `
    --set vision.ocr_backend=oneocr --set tts.backend=kokoro
```

## La lezione di questa sessione, che vale più di tutto il resto

**Il banco non può vedere i difetti che esistono solo dal vivo, e io ho dichiarato
morta una cura che funzionava.**

Il criterio della parola colorata era stato bocciato su una simulazione — le
soglie del vivo applicate alla registrazione del banco. Là non si vedeva niente,
perché gli obiettivi di missione interi erano già scartati e passava solo una
scritta a metà dissolvenza, che nessun criterio sul colore può prendere.

Dal vivo, due passate a confronto, il guadagno era **da un'altra parte**:

```
'Rec.Lavoriamo insieme gia da qualche mese, giusto?'  ->  'Lavoriamo insieme gia da...'
"Sì, era lui.Adam'a App"                              ->  'Sì, era lui.'
'ma devo dare una : olta alla mia vita.'              ->  'ma devo dare una svolta alla mia vita.'
```

Non righe **saltate**: righe **sporcate**. Frammenti di HUD colorata incollati
dentro il sottotitolo e pronunciati — e togliendo i pixel colorati dal ritaglio
l'OCR legge meglio **anche il resto**.

Nessun contatore lo mostrava, perché la riga risultante conteneva parole italiane
vere e passava ogni filtro. **Quando l'utente offre una prova dal vivo, quella è
la prova. Il surrogato non è un ripiego accettabile: è il modo in cui si
archiviano conclusioni false con la suite verde.**

Fine del prompt.
