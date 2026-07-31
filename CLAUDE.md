# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Cos'e'

Doppiaggio italiano **dal vivo** dei sottotitoli di un videogioco. I sottotitoli
di GTA V sono gia' in italiano — **non c'e' nessuna traduzione in questa
catena**: si legge il testo a schermo con l'OCR, si capisce chi sta parlando
dall'audio, si sintetizza con una voce assegnata a quel personaggio e si mixa
sopra il gioco abbassando l'originale.

`README.md` ha l'architettura estesa e la grammatica dei sottotitoli. **Non
leggerlo per intero**: costa e quasi mai serve.

## Le due cartelle sorelle non si guardano

`..\gta-redub-live` e `..\gta-redub-v2` sono **bozze fallite**, dichiarate tali
dall'utente. Non si leggono, non si copiano, non si citano le loro misure. Se
serve una logica che li' esisteva, si riscrive e si rimisura qui. (I loro venv
sono un'altra cosa: `.venv-f5` ha torch e torchaudio ed e' utile per un
esperimento GPU buttato via, senza avvicinare torch a questo venv.)

## Comandi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest              # 828 verifiche
.\.venv\Scripts\python.exe -m tools.selftest speaker pool # gruppi scelti
.\.venv\Scripts\python.exe -m tools.selftest -v           # con i verdi in chiaro

# la catena intera su una registrazione, senza gioco. Scrive dub.wav,
# events.jsonl, speaker.jsonl (la traccia) e con --mp4 il video montato.
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav `
    --start 1240 --end 1340 --set vision.ocr_backend=oneocr --mp4

.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella> [secondo]
.\.venv\Scripts\python.exe -m tools.recluster runs\<cartella>\speaker.jsonl --profile gtav
.\.venv\Scripts\python.exe -m tools.ui --profile live --loopback voicemeeter --set vision.ocr_backend=oneocr
```

- venv: `.venv` (Python 3.11.9), **sempre invocato per esteso**.
- **Non c'e' pytest.** La suite e' `tools/selftest.py` (piu' `selftest_audio.py` e
  `selftest_vision.py`); un gruppo si esegue anche da codice:
  `from tools.selftest import test_ring, Check; c=Check(); test_ring(c); c.report()`.
  Un gruppo nuovo si aggiunge al dizionario `GROUPS` in fondo a `selftest.py`.
- `models/`, `runs/` e le registrazioni sono materiale della macchina: gitignorati.

## L'architettura, nei pezzi che non si capiscono da un file solo

**Due domini, due thread, un solo punto di incontro** (`core/pipeline.py`). Il
dominio video (30 Hz) decide *cosa* si dira' e *quando*; il dominio audio (blocchi
da 10 ms) versa cio' che e' stato programmato e mixa. `on_frame` legge, decide,
sintetizza e **programma**; `on_audio` esegue. Il mixer non chiama mai il
sintetizzatore.

**Due tempi, mai uno.** `Stage.clock` e' il tempo del *media* (virtualizzabile,
serve a timbrare gli eventi); il *costo* si misura sempre a muro con
`perf_counter`. Confonderli fa risultare gratis ogni stadio durante il replay —
la misura non diventa imprecisa, diventa incapace di esprimere la risposta.

**Chi parla ha due porte, e non e' un'ottimizzazione** (`listen/speaker.py`).
`scegli` e' la porta veloce: la usa chi deve parlare adesso, con il poco parlato
disponibile, e **non crea mai un personaggio**. `impara` e' la porta lenta: a
battuta finita, sul ritaglio intero, aggiorna il centroide e semmai iscrive
qualcuno. Una soglia sola non esiste — quella che non inventa personaggi a 0,3 s
non ne riconosce di nuovi a 2 s. Le identita' si **fondono** quando due centroidi
si avvicinano abbastanza (vince chi ha piu' battute, cosi' non cambia voce chi ha
gia' parlato molto), e sotto `name_min_score` non si fa nessun nome: si parla con
una voce neutra fuori dal pool, che dichiara "non lo so ancora" invece di
mentire.

**L'anello audio ha una linea temporale sua** (`_marche` in `core/pipeline.py`).
Ogni blocco lascia una marca `(campioni scritti, che ora era)`, e il tempo si
converte in campioni interpolando fra le marche. Non e' un dettaglio: dal vivo il
thread audio perde campioni, e qualunque schema che deduca la posizione dal solo
conteggio deriva — misurato, 11 ms al secondo, fino a spostare di sette decimi la
finestra con cui si riconosce chi parla.

**Il tempo della battuta** (`fuse/timing.py`): `D = a + b*n` prevede quanto
restera' a schermo il sottotitolo, e da li' esce il budget. La previsione e'
debole per costruzione (la durata la decide il ritmo della conversazione, non la
lunghezza del testo), quindi chi la usa deve essere pronto a essere smentito a
meta' battuta — ed e' per questo che la correzione in volo con WSOLA e' la parte
portante e non un ornamento. **Il ritardo costante non e' un debito**:
`accepted_delay_ms` e' quanto se ne accetta senza rincorrerlo, perche' chiedere a
ogni riga di recuperare un ritardo che tornera' identico significa comprimerle
tutte.

**Chi accelera cosa.** Il sintetizzatore che parla piu' svelto **articola**;
WSOLA schiaccia e mangia le fini delle parole. Quindi la fretta si chiede prima
al motore (`tts.native_rate_max`) e solo il residuo va a WSOLA
(`timing.rate_max`). Ogni backend dichiara il **proprio** passo
(`chars_per_second`, nell'unita' di `spoken_length()`) e il proprio tetto: un
numero solo per tutti i motori e' gia' costato due sessioni.

## Banco e vivo: la cosa che costa di piu' capire

`tools/dub.py` fa girare **la stessa identica catena** su una registrazione:
stesso `DubPipeline`, OCR vero, audio vero nell'anello, impronta vera, sintesi
vera, mixer vero, e la causalita' e' rispettata — la pipeline non vede mai il
futuro. Non e' una simulazione.

**Ma il banco regala il tempo.** Con l'orologio virtuale la sintesi costa zero e
nessun frame viene mai saltato. Da qui una lista di difetti che il banco **non
puo' esprimere**, e che sono stati trovati tutti dal vivo:

- il ritaglio veloce finiva a `clock.now()`, un istante per cui l'audio non era
  ancora stato catturato; `RingBuffer.read_from` **tronca in silenzio**, quindi
  l'impronta si calcolava su 150 ms creduti 700. Sul banco impossibile, perche'
  `dub.py` versa l'audio di un pacchetto **prima** di passarne il frame;
- l'attesa prima di decidere era sull'orologio invece che sull'audio: le due cose
  coincidono sul banco e divergono dal vivo;
- la sintesi dentro il thread video (300-600 ms con SuperTonic) rende irregolare
  il flusso di frame, e il lettore di sottotitoli e' costruito su frame
  *consecutivi*: da li' battute non lette e doppioni da frammento.

`--tempo-reale` somma il costo del lavoro al tempo del media e salta i frame
arretrati. Sul **tempo** e' fedele (predice il vivo: 842 ms contro 951); sul
**riconoscimento e' pessimista**, perche' li' l'audio si versa al ritmo dei
pacchetti mentre dal vivo il thread audio e' indipendente.

**Gli strumenti per confrontarli.** Ogni prova — banco e vivo — scrive
`speaker.jsonl` con una riga per battuta e venticinque campi: chi parla, con che
punteggio, quanto durava il ritaglio, che voce, quanta fretta chiesta e quanta
ottenuta, WSOLA, sintesi, coda, latenza. E' per battuta e **non per frame** di
proposito: scrivere dentro il dominio audio farebbe perdere campioni, cioe'
ricreerebbe il difetto che si sta misurando.

`tools/recluster.py` rigioca il raggruppamento offline in millisecondi invece che
in una passata di OCR, e `--shuffle` — le stesse impronte permutate fra le
battute — e' il caso nullo che fissa le soglie.

**Come si confrontano due passate**: allineando le battute per testo e
**risolvendo la permutazione delle etichette**, perche' non conta se Lamar prende
M1 o M2, conta che la tenga. Chiedere "quante voci diverse" invece di "quante
coppie di battute sono d'accordo sull'essere la stessa persona" ha fatto
sembrare rotto per mezza giornata un riconoscimento che era al 100%.

## Config

Un solo albero di dataclass in `core/config.py`, ogni campo raggiungibile con
`--set sezione.campo=valore`. Un percorso inesistente e' un errore all'avvio, non
un refuso silenzioso. I default sono **punti di partenza dichiarati o misure
scritte**: dove c'e' una tabella nel commento, quel numero e' stato misurato e la
tabella dice come. ROI, soglie di colore e coefficienti di durata si ricavano con
`tools/calibrate.py` e si scrivono in `profiles/<gioco>.json` — e sono **del
setup di cattura, non del gioco**.

## Convenzioni

- **Codice in italiano**: commenti, docstring, messaggi di log, help della CLI,
  stringhe dell'interfaccia. **Identificatori in inglese.**
- Windows + PowerShell.
- I messaggi git multi-riga da PowerShell si rompono (le here-string vengono
  ri-analizzate e si mangiano le virgolette): scrivere il messaggio su file e
  usare `git commit -F file`.
- Commit solo dopo una suite verde. Commit piccoli e logici. Solo in locale.
- **Le prove d'ascolto si consegnano in MP4** (`tools/dub.py --mp4`): gioco,
  traccia doppiata e in alto su fondo nero il testo **letto dall'OCR** con la
  voce assegnata. Senza, non si distingue "ha sbagliato a leggere" da "ha
  sbagliato a dire" — e difetti che sembravano del sintetizzatore si sono
  rivelati frasi spezzate fra due sottotitoli.

## Le regole di metodo, che valgono piu' del codice

**Verificare una trasformata contro la propria inversa** prima di accusare un
modello: una trasformata sbagliata produce spazzatura plausibile, non un errore.

**Guardare l'ingresso del modello prima di accusare il modello.** L'OCR leggeva
`Oaai recuperiamo veicoli acauistati` e sembrava scadente sull'italiano: il
ritaglio che riceveva aveva le code di `g` e `q` tagliate, e una `g` senza coda
**e'** una `a`.

**Il caso nullo migliore condivide tutto tranne la risposta.** Le impronte
permutate fra le battute lasciano identiche scena, tempi e alternanza e tolgono
solo *chi e' chi*: sono loro ad aver fissato la soglia della fusione, dove il
conteggio delle identita' da solo ne avrebbe scelta una che fondeva a caso.

**Controllare che la misura possa esprimere la risposta.** Un caso: selezionare i
pixel di testo con una maschera che pretende uno stacco maggiore di 60 e poi
misurare lo stacco — risposta 60,15, cioe' la soglia che si guarda allo specchio.
Un altro, di oggi: `ritardo_anello` era la differenza fra l'orologio e una
quantita' **definita come l'orologio**, quindi valeva zero anche dove un terzo
dei frame veniva saltato.

**Un'unita' di misura e' un operatore come un altro.** `chars_per_second` valeva
17,4, misurato contando *tutti* i caratteri, ed era diviso per `spoken_length()`,
che conta **solo lettere e cifre**: un quarto di errore su ogni durata prevista,
per anni, senza che nessun numero fosse sbagliato — sbagliato era che i due si
incontrassero.

**Due errori che si compensano sono piu' pericolosi di un errore solo.** La stima
delle durate era corta di un quarto e l'anello di correzione la compensava
alzando il guadagno: il risultato finale era ragionevole. Correggendo *solo* la
stima tutto e' peggiorato di colpo. Quando una correzione giusta peggiora le
cose, il difetto non era uno.

**Un rimedio che funziona non conferma la diagnosi.** Il percentile basso sulla
f0 curava il difetto, quindi la spiegazione che lo accompagnava — "c'e' del fondo
tonale che contamina" — e' rimasta in piedi senza essere verificata. Era
sbagliata: quelle frequenze erano un uomo che urla, e si vede perche' salgono con
l'energia della finestra invece di stare nelle pause.

**Verificare che il trattamento sia stato applicato prima di leggere il
risultato.** La prova del separatore vocale dava un risultato pulito e falso: il
raggruppamento non migliorava perche' l'audio non era cambiato (correlazione
0,983 con l'originale). Bastavano una correlazione e un istogramma.

**Isolare una taratura con un motore deterministico.** SuperTonic e' a diffusione:
cambiando la voce cambia la sintesi, cambiano i tempi, cambiano le decisioni. Due
misure di seguito hanno detto il contrario del vero. Le tarature si isolano con
Piper e si verificano dopo con SuperTonic.

**E la piu' importante: l'orecchio dell'utente trova cio' che la suite non puo'.**
E' successo a ogni difetto serio di questo progetto, con la suite verde. Quando
l'utente dice "non funziona" e i numeri dicono di si', **sono i numeri a essere
sotto esame** — e la risposta giusta e' chiedergli *il secondo* in cui l'ha
sentito, non un'altra impressione.

## Dove sta il lavoro

`PROSSIMA_SESSIONE.md` e' il passaggio di consegne: stato, cosa e' aperto e con
quale misura si scioglie. Va aggiornato a fine sessione, e vale piu' di questo
file per sapere *cosa* fare adesso.
