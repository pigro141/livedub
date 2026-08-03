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
`/graphify . --update` dopo modifiche grosse, non a ogni task. **Va aggiornato
adesso**: lo streaming ha cambiato `mix/mixer.py`, `core/pipeline.py` e
`speak/backends/qwen.py`, e ha aggiunto `core/onnx.py` e `tools/bench_qwen.py`.

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

## Cosa è successo nella sessione scorsa

**Lo streaming di Qwen è fatto, verificato, e non è servito a renderlo usabile.**

Funziona: primo campione a **257 ms** invece di 4820, regge il tempo reale
(0,83×, zero `mix.underrun` su 25 battute), e i blocchi concatenati sono campione
per campione la battuta che darebbe `synthesize`. Il mixer adesso sa tenere una
battuta **aperta** — programmata prima di esistere — e quel pezzo lo eredita
chiunque scriva un altro motore autoregressivo.

**Il muro è un altro, e la misura è nuova.** Stessa scena da 49 s, stesse 25
battute:

| | parlato prodotto | passo | WSOLA p50 | latenza p50 |
|---|---|---|---|---|
| piper | 35 s (72% della scena) | 18,3 car/s | 1,024 | 533 ms |
| **qwen** | **77 s (157%)** | **8,4 car/s** | **1,250 (al tetto)** | 3,6-6,7 s |

Qwen parla la metà di Piper, quindi produce più audio di quanto la scena abbia
tempo, e comprimendo al massimo resta al 125%. La coda non rientra più. E **non
c'è leva**: il modello ignora `rate`, quindi la fretta può chiederla solo WSOLA,
che è già al tetto.

## Cosa resta, in ordine di quanto vale

**1. Decidere che fare di Qwen, con la misura in mano.** Tre strade, e la prima
è la mia raccomandazione:

- **lasciarlo dov'è** — backend completo, in streaming, usabile sul banco e per
  battute isolate, non default. È già così. Costo: zero;
- provare a farlo parlare più in fretta **dentro il modello**: non ha un
  parametro di velocità, ma l'istruzione della voce è testo libero
  (`"...parla svelto"` nella descrizione). Va misurato, non supposto: se porta
  8,4 car/s sopra 13-14 il motore torna in gioco, altrimenti è chiuso. È
  un'ora di lavoro e scioglie la domanda per sempre;
- alzare `timing.rate_max` sopra 1,25 solo per questo backend. **Sconsigliato**:
  sopra 1,3 WSOLA mangia le consonanti, ed è scritto in tre punti di `CLAUDE.md`.

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

**5. Gli step finali**: UI, impostazioni live, exe, licenza, repo. Sono la maggior
parte delle caselle vuote rimaste, e nessuna richiede altre misure.

## Cose sospese che vanno chiuse

- **La taratura del genere non è mai stata provata su una donna**: nella
  registrazione non ce n'è una. Serve materiale nuovo.
- **Un terzo delle battute dal vivo esce con la voce neutra** (11 su 25
  nell'ultima passata di banco, 14 su 66 dal vivo). Non è un difetto della voce
  neutra, che sta dicendo la verità: è che il riconoscitore non arriva a
  `name_min_score` abbastanza spesso. **Nessuno lo sta ancora guardando**, ed è
  la cosa più visibile all'ascolto dopo la latenza.
- **`chatterbox` e `qwen` non sono in `requirements.txt`** perché non sono pip
  del venv principale (Chatterbox sta nei venv sorelle). Se Qwen resta, va detto
  come si scarica il modello — oggi lo dice solo un messaggio d'errore.

*(Chiusi nella sessione scorsa: `tokenizers` in `requirements.txt`;
`preload_dlls()` spostato in `core/onnx.py` dove ci passa chiunque apra una
sessione ONNX, con `verifica_provider()` accanto.)*

## Lo stato, in numeri veri

Motori, misurati **dal vivo** dove indicato:

|  | sintesi p50 | latenza totale p50 | dove gira |
|---|---|---|---|
| **piper** (default) | ~50 ms | ~670 ms | CPU |
| **kokoro** | 174-257 ms | ~1150 ms | CUDA |
| **supertonic** | 313 ms | ~1300 ms | CPU — il livello senza GPU |
| **qwen** | 257 ms al primo campione | 3,6-6,7 s (banco) | CUDA, streaming fatto |
| chatterbox | 3,4 s | non usabile | solo offline |

La riga di Qwen va letta con la tabella del parlato prodotto qui sopra: la
latenza non è di sintesi, è la coda che non rientra.

## Il banco, che è lo strumento di tutto

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                  # 989 verifiche
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav `
    --start 1240 --end 1340 --set vision.ocr_backend=oneocr --mp4
.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella> [secondo]
.\.venv\Scripts\python.exe -m tools.ui --profile live --loopback voicemeeter `
    --set vision.ocr_backend=oneocr --set tts.backend=kokoro

# nuovo: il banco di Qwen. Le quattro prove sono indipendenti.
.\.venv\Scripts\python.exe -m tools.bench_qwen --riferimento   # il ciclo srotolato e' fedele?
.\.venv\Scripts\python.exe -m tools.bench_qwen --vocoder       # si puo' vocodare un pezzo?
.\.venv\Scripts\python.exe -m tools.bench_qwen --streaming     # passo a caldo, costo, latenza
.\.venv\Scripts\python.exe -m tools.bench_qwen --pezzi         # i blocchi rifanno la battuta?
```

## La lezione di questa sessione, che vale più di tutto il resto

**Un ramo nuovo non eredita le cure di quello vecchio, e la suite resta verde.**

Il ramo in streaming ha ripetuto, nello stesso pomeriggio, due difetti che il ramo
normale aveva risolto da tempo:

- **non ricampionava** da 22050 a 48000 — una riga che `_speak` ha da sempre.
  Risultato: doppiaggio a 2,2×, voce da scoiattolo, WAV prodotto, suite verde,
  nessun contatore in allarme. A smascherarlo è stato un numero **impossibile**:
  il passo misurato del motore risultava di 30 caratteri al secondo, che non è
  una velocità di parlato di nessuno;
- **non toglieva il silenzio in coda** — che `taglia_silenzio` toglie da sempre,
  ed è scritto in quel docstring che costò mezza notte su SuperTonic. Metà
  dell'uscita era imbottitura, la catena la misurava come parlato e chiedeva
  fretta per starci dentro. *Si accelerava del silenzio, pagandolo in parole*: la
  stessa frase già scritta in `CLAUDE.md`, un motore più tardi.

Quando si apre una strada parallela a una che funziona, la domanda giusta non è
«cosa serve a questa» ma **«cosa fa quella vecchia che questa non fa»**. E un
numero fuori scala va inseguito anche — soprattutto — quando tutto il resto è
verde: è l'unica traccia che lascia un'unità sbagliata.

**E la previsione dichiarata prima ha funzionato di nuovo.** Prima di scrivere una
riga di streaming era scritto che *se `vocoder(codici[:k])` non avesse coinciso con
l'intero, lo streaming di questo motore non era il lavoro che si credeva*. Ha
coinciso (corr 1,0000), e il blocco interno no (corr 0,95) — che ha deciso
l'architettura al posto mio: si vocoda il prefisso, non il blocco.

Fine del prompt.
