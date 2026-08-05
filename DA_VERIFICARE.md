# Cosa verificare a mano

Lavoro fatto in autonomia. Qui sotto **solo le cose che io non ho potuto
verificare**, in ordine di quanto costa sbagliarsi. La suite è verde (1098
verifiche) ma la suite non sente niente: ogni difetto serio di questo progetto è
stato trovato dall'orecchio, con la suite verde.

---

## 0. LA COSA PIU' IMPORTANTE: la grafica nuova non l'ha vista nessuno

Ultimo lavoro della sessione, **scritto e mai eseguito a schermo**. La suite e'
verde e gli import passano, ma un overlay si giudica solo col gioco acceso.

Cosa dovrebbe fare adesso (`ui/overlay.py`):

- **stringersi sull'inchiostro vero** invece di coprire tutta la ROI. Il riquadro
  si ricava dalla stessa maschera che usa l'OCR (`vision.lines.text_mask`): non
  una stima di dove sia il testo, letteralmente i pixel che l'OCR ha letto;
- **sfocare** il sottotitolo vecchio invece di coprirlo di nero, prendendo la ROI
  dal fotogramma corrente.

**Se il riquadro cade nel posto sbagliato**, il sospetto numero uno e' la
conversione fra pixel del fotogramma e pixel dello schermo in
`Overlay._prepara_sfondo` (`sx`, `sy`): li' si assume che la ROI del fotogramma e
la ROI dello schermo abbiano le stesse proporzioni, e con una cattura che scala
non e' detto.

**Se non si vede nessuna sfocatura**, `_inchiostro()` in `tools/ui.py` sta
tornando `(None, None)` — cattura l'eccezione apposta, per non perdere una battuta
per colpa di un effetto grafico. Togliere il `try` li' dentro e guardare l'errore
e' il primo passo.

Il comando per provarla e' quello della sezione 1 qui sotto.

## 1. La compressione resta al tetto, e adesso so perche' — non e' piu' il passo

Due sessioni dal vivo con traduzione, 18 e 24 battute. Entrambe:
`dub.rate_x1000` a **1250 su tutti i percentili**, con il parlato che riempie
**41-49% della scena**. Tutto il tempo del mondo, e la voce corre lo stesso.

La prima volta era il passo dell'italiano applicato all'inglese: corretto
(`PASSO_LINGUA`), e non e' bastato. Il passo vero misurato dal vivo e' **16,74
car/s** contro i 14,37 dichiarati, quindi resta un po' di sottostima — ma il
grosso viene da un'altra parte.

**E' la latenza che mangia il budget.** `DurationModel.plan` calcola
`budget = durata prevista - (tempo gia' passato - accepted_delay)`. Con la
traduzione sulla strada critica il tempo gia' passato e' ~1,7 s (500 ms di
`decide_after_ms` + ~600 ms di traduzione la prima volta + 217 ms di sintesi +
coda), e `accepted_delay_ms` vale **250**. Quindi al budget vengono tolti ~1,4 s
di una finestra che ne dura due, e WSOLA schiaccia per rientrare in quel poco che
resta.

**La cura giusta e' quella che `fuse/timing.py` descrive gia' nel suo docstring**:
`accepted_delay_ms` esiste per «la parte che torna identica a ogni battuta», e
la traduzione e' esattamente quella. Va alzato — indicativamente a **800-900 ms**
quando `translate.enabled` — e poi **rimisurato**, perche' il docstring avverte
anche che scusare troppo fa crescere la coda: la tabella li' dentro dice che a
250 ms c'era il ginocchio *senza* traduzione.

**Non l'ho cambiato**, perche' cambiare una soglia senza rimisurarla e' il modo
in cui in questo progetto sono nate meta' delle sessioni sprecate. E' la prima
cosa da fare, con la tabella di `fuse/timing.py` rifatta a traduzione accesa.

## Qwen: chiuso## Qwen: chiuso, e non c'e' piu' niente da verificare
## Il nome del parlante — **controllato**, come chiesto

Le sette forme provate su testo di gioco realistico, con l'elenco dei personaggi
dichiarato: prendono tutte il nome giusto e lo tolgono dal testo da pronunciare.

    nome:        'MICHAEL: Ti avevo detto di non tornare.'  -> Michael
    nome:        'Franklin : Come va, bello?'               -> Franklin
    -nome:       '- Lamar: Toc toc!'                        -> Lamar
    [nome]       '[Trevor] Sono un uomo cambiato.'          -> Trevor
    nome-        'Simeon - Il dipendente del mese.'         -> Simeon
    nome>>       'Lamar >> Andiamo, negro.'                 -> Lamar
    nome(nota):  'Michael (urlando): Vattene!'              -> Michael

Piu' le 42 verifiche del gruppo `etichetta`, che coprono i falsi positivi e la
voce stabile fra sessioni. **Resta vero che non esiste materiale di un gioco che
scriva i nomi**: quando ce l'avrai, il contatore `vision.label.hit` dice subito se
il formato dichiarato e' quello giusto.

### Come si configura, in concreto

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

## 7. La traduzione — **adesso provata sul materiale vero**

Tradotti i sottotitoli **italiani** di GTA V in **inglese** con TranslateGemma via
Ollama: **28 battute su 28**, con la sostituzione grafica (blur sull'originale,
testo nuovo sopra). L'MP4 e' quello che ti ho mandato.

Esempi: `'Ma domani'` -> `'But tomorrow'`, `'Saremo insieme!'` ->
`"We'll stick together!"`, `'ma se ne avessi uno vorrei che fosse come te.'` ->
`"But if I had one, I'd want it to be like you."`

**Cosa guardare nell'MP4**: che il blur cada **sul** sottotitolo del gioco e che
il testo inglese lo copra bene; e che la voce dica l'inglese. Se il riquadro cade
altrove, la ROI del profilo non e' tarata per quel setup.

**Quello che resta non provato**: Argos (`translate.backend=locale`), che vuole
`pip install argostranslate` e il pacchetto della coppia di lingue. Google invece
e' misurato (64 ms, 6/6 sul registro volgare).

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
