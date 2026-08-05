# Cosa verificare a mano

Lavoro fatto in autonomia. Qui sotto **solo le cose che io non ho potuto
verificare**, in ordine di quanto costa sbagliarsi. La suite è verde (1087
verifiche) ma la suite non sente niente: ogni difetto serio di questo progetto è
stato trovato dall'orecchio, con la suite verde.

---

## Qwen: chiuso, e non c'e' piu' niente da verificare

La prova dal vivo l'abbiamo fatta due volte. La prima aveva dentro un difetto mio
(la battuta partiva prima di essere generata) e non valeva; sistemato quello, la
seconda ha sfondato tutte e tre le soglie dichiarate prima:

| criterio | soglia | misurato |
|---|---|---|
| `mix.underrun` | 0 | **5415** |
| latenza p50 | < 2,5 s | **26,7 s** al primo campione |
| compressione | < 1450 | **1450 a ogni percentile** |

Su 65 battute lette, 25 hanno prodotto audio. **Il backend e' stato tolto.**

Quello che resta e che non va buttato: il mixer sa tenere una battuta aperta col
suo cuscino, la catena sa programmare prima di avere l'audio, e la verifica
`streaming` gira su un motore finto. Il prossimo motore autoregressivo eredita
tutto.

E la lezione da portarsi dietro quando si valuta il prossimo: **la domanda
decisiva non e' la latenza, e' quanto parlato produce per secondo di scena.** Qwen
ne produceva il 157%: nessuno scheduler e nessuna scheda video lo salvano.

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

- il cuscino non tocca i motori normali: aggregati identici con cuscino a 350 ms
  e a 0, e il contatore `mix.prebuffer` resta a zero perché quel ramo non parte;
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
