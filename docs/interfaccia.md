# Menta — il disegno di livedub

> **Stato: costruito.** Questo documento e' stato scritto prima della finestra e
> poi realizzato in `ui/qt_tema.py` (i numeri) e `tools/ui_qt.py` (la finestra).
> Dove i due non vanno d'accordo **vince il codice**, perche' e' stato guardato a
> schermo e questo no. Le prescrizioni cadute alla prima occhiata sono elencate
> in `CLAUDE.md`, sezione «Quello che il documento diceva e che a schermo era
> sbagliato»; le principali, per non riscriverle:
>
> - **i tre punti di rottura sono uno**. Ridurre la barra della misura sotto i
>   720 px faceva sparire i numeri uno per uno, e i primi ad andarsene erano
>   quelli che si guardano quando qualcosa non va (§6, §11.5);
> - **la pillola di stato non c'e'**. Lo stato era detto in tre posti — testata,
>   barra in fondo, faccia del logo — per una parola sola (§11.1, §12);
> - **il monospazio e' rimasto solo nel log**, e li' e' il carattere
>   dell'interfaccia con le *cifre tabulari*: le colonne servivano ai numeri, e i
>   campi ora si separano con dei punti (§7);
> - **la tessera del logo non c'e'**: il logo ha gia' la sua sagoma (§11.1);
> - **le schede sono sei** (§11.4): Preparazione, Sessione, Voce, Volumi,
>   Traduzione, Tutte le impostazioni. «Aree» c'e' stata e non c'e' piu' — le
>   zone multiple sono state tolte il 18 agosto 2026, e i suoi tre parametri
>   sono passati alla Preparazione. «Volumi» e' nata il 19: i sei campi di
>   `mix.` erano tre dentro «Voce» e tre in nessun posto.
>
> Quello che regge intero: la tavolozza, `R(h)`, la scala delle distanze, i
> corpi, il materiale, la regola dei canali, gli stati, gli errori e
> l'accessibilita'. Le schermate si rifanno in trenta secondi con
> `python -m tools.scatta runs\menta`.

Guida per costruire l'interfaccia. Non descrive quella di oggi: **la sostituisce**.
Tutto quello che c'e' qui dentro deriva da una cosa sola — i colori e la geometria
del logo — e il resto e' conseguenza.

Si chiama **Menta** dal verde dell'onda che esce dalla bocca del logo, `#43f1c1`,
che in questo disegno e' il colore di tutto cio' che si puo' toccare.

**`assets/logo/menta-anteprima.png` e' come viene.** Testata, barra dei comandi,
striscia, linguette, log e barra della misura disegnati con i valori esatti di
questo file, nei due temi piu' lo stato di guasto. Non e' una finestra vera — e'
un disegno — ma usa le stesse costanti, quindi cambiando un numero qui e
rigenerandola si vede cosa succede senza compilare niente.

## Come si usa questo file

Chi scrive un pezzo di finestra cerca qui il numero e non lo inventa. Se il
numero non c'e', **si ricava con una regola scritta qui** (il raggio, le
distanze, i corpi) e la si aggiunge alla tabella. Un numero deciso guardando quel
pezzo e non la finestra e' il modo in cui erano nati i 3, 6, 8, 9, 10, 12, 14, 16,
18, 22, 24 sparsi che questo disegno sostituisce: nessuno sbagliato da solo,
insieme un'interfaccia senza scala.

Ogni valore di colore qui dentro e' **misurato**, non scelto a occhio: i rapporti
di contrasto sono WCAG 2.1 calcolati sui valori che vedi, e le distanze fra colori
sono ΔE in CIELAB. Dove un numero non passa, c'e' scritto che non passa e cosa si
fa invece.

> **Le regole marcate ⚠ sono quelle che, rotte, non danno errore.** Sono le piu'
> importanti: producono un'interfaccia plausibile e sbagliata, con la suite verde.

---

## 1. Da dove viene tutto

Il logo e' un **riquadro di sottotitolo vivo**: la cosa che questo programma
legge a schermo, con due occhi, due barre grigie al posto del testo, una bocca, e
dalla bocca un'onda verde acido — la voce che ci mettiamo sopra. La catena intera
in una forma sola.

Da quella forma escono, letteralmente campionati dal file, **sei dei dodici
colori** dell'interfaccia e **la regola del raggio**. Non e' un ossequio al
marchio: e' il modo piu' economico di avere un'interfaccia coerente, perche' il
riferimento non e' un documento che qualcuno deve ricordarsi, e' un PNG che sta
nel repo.

| campionato dal logo | valore | diventa |
|---|---|---|
| il corpo del riquadro | `#212836` | `superficie_alta` — campi, tessere |
| il contorno chiaro | `#808ba5` | `testo_tenue` |
| le barre del sottotitolo | `#545e71` | `testo_fioco` |
| l'onda | `#43f1c1` | **`accento`** |
| il punto piu' chiaro dell'onda | `#95ffdf` | `accento_chiaro` — passaggio del mouse |
| il raggio degli angoli, 19,8% dell'altezza | | la regola `R(h)` |

---

## 2. I due loghi

Sono due **stati** dello stesso personaggio, non due disegni.

| file | stato | come e' fatto |
|---|---|---|
| `assets/logo/livedub.png` | sereno | occhi tondi e aperti, bocca aperta, onda regolare |
| `assets/logo/livedub-guasto.png` | guasto | sopracciglia abbassate, occhi socchiusi, bocca serrata e storta, onda che esce lo stesso |

### ⚠ L'onda e' l'unica cosa che sfonda la sagoma

A 64 px il riquadro con dentro gli occhi e' un rettangolo qualunque; il rettangolo
**con l'onda che esce a destra** e' livedub. Qualunque ritocco futuro che riporti
l'onda dentro il riquadro perde il logo, e lo perde **solo alle taglie piccole** —
cioe' non si vede guardando il file grande, che e' l'unico modo in cui si guarda
un logo mentre lo si disegna. Si controlla aprendo `livedub-64.png` al 100%.

### Cosa vuol dire il secondo, e cosa non vuol dire

Quello arrabbiato **sta ancora parlando**: l'onda esce, storta e a fatica. Copre
gli stati in cui la catena e' in avaria *ma il programma e' vivo* — audio
interrotto, avvio fallito, traduzione caduta, eccezione raccolta.

**Non e' il logo dello stato spento.** A programma fermo il personaggio e' quello
sereno: fermo non e' rotto, e un logo incazzato su una finestra appena aperta dice
una cosa falsa alla prima occhiata che l'utente le da'. Se un giorno servira'
«spento», sara' un terzo disegno — occhi chiusi, niente onda — non questo.

### Le misure del disegno

Prese sul file, non a occhio (tela 1015x1015):

| cosa | valore |
|---|---|
| riquadro del corpo | 957 x 801 px, rapporto **1,195** (circa 6:5) |
| raggio degli angoli | **158 px** = **19,8%** dell'altezza |
| corpo | `#212836`, sfumatura verticale appena percettibile |
| contorno chiaro | `#808ba5`, spesso 3-4 px |
| barre del sottotitolo | `#545e71` |
| onda, mediana | `#43f1c1` |
| onda, punto piu' chiaro | `#95ffdf` |

### Il fondo tolto

Gli originali erano PNG opachi su nero. Toglierlo con una soglia sulla luminosita'
**buca il personaggio** — il corpo e' `#212836` e il fondo era `#0b0b0d`, venti
livelli, con una vignettatura che li avvicina ancora — e un ritaglio netto lascia
intorno all'onda un **anello nero**, perche' il suo alone e' additivo e sfuma
dentro il nero su cui e' nato: invisibile su fondo scuro, evidente su fondo chiaro.

Come e' stato fatto, e perche' le due meta' combaciano:

- `soggetto` = i pixel che staccano dal fondo piu' di **T = 20**, chiusi con un
  kernel 7x7 e con i buchi riempiti **allagando dal bordo**, cosi' le pupille e
  l'interno della bocca — neri quanto il fondo — restano opachi perche' l'acqua
  non li raggiunge;
- fuori dal soggetto l'alfa sale linearmente da 0 (stacco 4) a **1 esattamente a
  T**. I due pezzi si incontrano senza scalino **per costruzione**, perche'
  condividono la soglia: non e' una sfumatura azzeccata, e' la stessa soglia
  scritta una volta sola.

Poi i pixel si **smoltiplicano** (`C = fondo + (px − fondo) / alfa`): l'alone
lasciato com'era si porterebbe dietro il nero su cui e' nato, e su fondo chiaro
diventerebbe una macchia grigia invece di un bagliore.

Verificato **guardando l'immagine** — che e' come si verifica una correzione
geometrica in questo progetto — su bianco, sul chiaro dell'interfaccia, sullo
scuro e su un verde saturo. Il contatore dice il resto: 666.198 pixel opachi e
13.385 in sfumatura, cioe' il **2,0%** di alone, che e' la quantita' giusta per un
bagliore e sarebbe zero per un ritaglio netto.

### ⚠ I due file sono registrati sullo stesso rettangolo

Sono ritagliati sull'**unione** dei due riquadri, non ciascuno sul proprio.
Scambiando il sereno con l'arrabbiato — che e' precisamente quello che la finestra
fa quando la catena cade — il riquadro non si sposta e non cambia taglia. Chi li
rigenera non deve perdere questa proprieta': due loghi ritagliati stretti ciascuno
sul suo contenuto **saltano** al cambio, e un logo che saltella chiede attenzione
mentre l'utente sta giocando.

### Le taglie

```
livedub.png            1015x1015  RGBA   sorgente
livedub-256.png         256x256          finestra, icona, informazioni
livedub-64.png           64x64           testata, barra delle applicazioni
livedub-guasto.png     1015x1015
livedub-guasto-256.png  256x256
livedub-guasto-64.png    64x64
```

Serve anche un `livedub.ico` multi-risoluzione (16/32/48/256) per l'eseguibile:
Windows non ridimensiona bene un PNG grande nella barra delle applicazioni, e a
16 px l'onda va ridisegnata a mano — a quella taglia la sfumatura diventa
poltiglia.

---

## 3. La tavolozza

Dodici ruoli, due temi. **Li sceglie Windows** (`QStyleHints.colorScheme`), che
avvisa quando cambiano: non si legge il registro e non si riavvia, si riapplica il
foglio di stile a sessione accesa.

### Tema scuro (quello principale)

| ruolo | valore | contrasto sul fondo | dove |
|---|---|---|---|
| `fondo` | `#0f131b` | — | la finestra |
| `superficie` | `#181e29` | — | testata, pannelli, log, liste |
| `superficie_alta` | `#212836` | — | campi, tessere, bottoni normali |
| `bordo` | `#2c3444` | 1,3:1 | fili di separazione |
| `bordo_forte` | `#3b4557` | 1,9:1 | contorno dei campi, mouse sopra |
| `testo_fioco` | `#545e71` | 2,9:1 ✗ | solo disabilitato e decorazioni |
| `testo_tenue` | `#808ba5` | **5,5:1** AA | note, etichette, valori |
| `testo` | `#e4e9f2` | **15,3:1** AAA | il testo |
| `accento` | `#43f1c1` | **12,9:1** AAA | tutto cio' che si tocca |
| `accento_chiaro` | `#95ffdf` | 15,6:1 AAA | mouse sopra un elemento accentato |
| `accento_scuro` | `#1fb894` | — | premuto |
| `su_accento` | `#06231c` | **11,5:1** sull'accento | testo sopra un riempimento menta |
| `ambra` | `#f5b544` | 10,3:1 AAA | avvisi, cose in attesa |
| `rosso` | `#ff6b5e` | 6,7:1 AA | guasti |

### Tema chiaro

| ruolo | valore | contrasto su `superficie` | note |
|---|---|---|---|
| `fondo` | `#f2f4f8` | — | |
| `superficie` | `#ffffff` | — | |
| `superficie_alta` | `#e9edf4` | — | |
| `bordo` | `#d3dae6` | 1,4:1 | |
| `bordo_forte` | `#b9c3d4` | 1,8:1 | |
| `testo_fioco` | `#7e8aa2` | 3,5:1 | solo disabilitato |
| `testo_tenue` | `#5a6579` | **5,9:1** AA | |
| `testo` | `#141922` | **17,6:1** AAA | |
| `accento` | `#07785d` | **5,5:1** AA | menta scurita, per testo e contorni |
| `accento_chiaro` | `#43f1c1` | 1,4:1 ✗ | **solo come riempimento** |
| `accento_scuro` | `#05614c` | 7,4:1 | premuto |
| `su_accento` | `#06231c` | 11,5:1 sulla menta | |
| `ambra` | `#a16207` | 4,9:1 AA | |
| `rosso` | `#cc372c` | 5,1:1 AA | |

### ⚠ La menta e' un riempimento, non un testo

`#43f1c1` su bianco fa **1,44:1**. E' il numero che avrebbe fatto sbagliare tutto:
sul tema scuro la menta e' magnifica (12,9:1) e chi la prova li' conclude che
funziona. Quindi:

- **su fondo scuro** la menta e' testo, contorno, riempimento — tutto;
- **su fondo chiaro** la menta e' **solo riempimento**, con sopra `su_accento`
  (`#06231c`, 11,5:1). Per il testo e i contorni si usa `accento` = `#07785d`.

Il guadagno e' che il bottone **Avvia** e' letteralmente il colore dell'onda del
logo **in tutti e due i temi**, ed e' l'unico elemento della finestra che non
cambia colore col tema. Chi lo cerca lo trova sempre nello stesso modo.

### Il blu se ne va

L'interfaccia di oggi ha tre colori accesi con tre significati che si accavallano:
un verde «sta funzionando», un blu «questo si preme», e un quarto verde `#39d353`
scritto a mano nel selettore d'area, fuori da qualunque tavolozza e mai guardato
nel tema chiaro.

In Menta ce n'e' **uno**. La menta vuol dire *interazione e vita*: il bottone che
si preme, il campo che ha il fuoco, la linguetta scelta, la spia quando la catena
gira, il rettangolo che si tira sullo schermo. Ambra e rosso restano, ma non sono
colori d'interfaccia: sono **stati**, e compaiono solo dove c'e' uno stato.

---

## 4. Il colore come informazione

Nel log il colore **e' il dato**: la domanda che ci si fa guardandolo non e' «cosa
ha detto» ma «e' sempre lo stesso a parlare?», e a quella l'occhio risponde da un
colore molto prima che da una sigla. Sei colori, uno per personaggio, a rotazione.

| | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| scuro | `#ffb86b` | `#79c0ff` | `#ff8fb1` | `#c9a0ff` | `#f2d65c` | `#9ee85f` |
| chiaro | `#b45309` | `#1e5fbf` | `#b8286a` | `#6d3ad6` | `#8a6a00` | `#3f7d1e` |

Tutti sopra 4,5:1 sul proprio fondo (il piu' basso e' 5,0:1). La distanza minima
fra due voci e' **ΔE 26,3** sullo scuro e **31,7** sul chiaro: sopra 25 due colori
si distinguono anche di sfuggita, che e' l'unico modo in cui si guarda un log
mentre si gioca.

### ⚠ Le due file non sono l'una l'inverso dell'altra

I sei che si distinguono sul nero, messi sul bianco, diventano pastelli che si
confondono a coppie. I sei del tema chiaro sono **piu' scuri e piu' saturi**:
stessi ruoli, colori diversi. Chi tocca una fila deve rimisurare l'altra.

### ⚠ La regola dei canali, che e' quella che tiene in piedi il sistema

Sei voci piu' tre stati (menta, ambra, rosso) fanno **nove tinte**, e nove tinte
non stanno sul cerchio dei colori con margini comodi. Misurato: la voce 1
(`#ffb86b`) e l'ambra (`#f5b544`) distano **ΔE 16,0**, cioe' si confondono.

La soluzione non e' cercare nove tinte perfette — non ci sono. E' che **le due
famiglie non usano mai lo stesso canale**:

| famiglia | come si manifesta | dove |
|---|---|---|
| le sei voci | **colore del testo** | solo nel log, sul nome e sulla battuta |
| menta / ambra / rosso | **riempimenti, marche, contorni, la spia** | ovunque tranne il testo del log |

Quindi una riga di errore nel log **non e' rossa**: ha una marca rossa da 3 px nel
margine sinistro. E la voce arancione resta arancione senza che nessuno la scambi
per un avviso, perche' un avviso non e' mai una parola colorata.

Rotta questa regola, il log smette di rispondere alla sua unica domanda — e non
smette di colpo, smette per gradi, mentre tutto continua a funzionare.

---

## 5. Geometria

### Il raggio si ricava, non si sceglie

Il logo stonda al **19,8% dell'altezza**. La regola e' quella, con un tetto perche'
un pannello alto 600 px non e' una pillola:

```
R(h) = clamp(round(0.20 * h), 4, 18)
```

Quelli che escono, e che si scrivono come costanti:

| elemento | altezza | raggio |
|---|---|---|
| marca nel margine, spunta | 16-18 | **4** |
| riga di elenco, campo, contatore, tendina, riga di parametro | 28-32 | **6** |
| bottone | 34 | **7** |
| linguetta, tessera del logo | 40 | **8** |
| striscia, tessera d'errore, scheda | 56-90 | **11-18** |
| pannello, dialogo, pannello a tutto schermo | grande | **18** |

E tre cerchi, che sono la stessa regola portata al limite — **raggio = meta' del
lato**:

| elemento | lato | raggio |
|---|---|---|
| la spia | 10 | 5 |
| la maniglia dello slider | 14 | 7 |
| il bottone ⓘ | 28 | 14 |
| la pillola di stato | h 28 | 14 |

Chi aggiunge un elemento applica `R(h)` e mette il risultato in tabella. **Non
copia un raggio da un elemento di altezza diversa**: 8 px su un bottone alto 34 e
8 px su un pannello alto 400 non sono lo stesso angolo, sono due decisioni diverse
travestite da una.

### Le distanze

Passo di quattro. Otto valori, e non se ne aggiungono.

```
S0  2    marche, fili, correzioni ottiche
S1  4    dentro un controllo
S2  8    fra controlli che stanno insieme
S3  12   fra un'etichetta e la sua cosa
S4  16   fra gruppi dentro una sezione
S5  24   margine di una sezione
S6  32   fra sezioni
S7  48   respiro grande, stato vuoto
```

Con passi regolari le distanze si **confrontano**: due cose alla stessa distanza
sono allo stesso livello, e l'occhio lo legge senza saperlo.

**Il margine standard di un contenitore e' `S5` in orizzontale e `S3` in
verticale.** Non e' simmetrico apposta: una finestra e' larga e bassa, e lo stesso
margine sopra e ai lati fa sembrare tutto schiacciato in alto.

### La griglia

Colonna unica. Il contenuto delle schede si allinea a sinistra e **non supera 880
px di larghezza utile**, centrato se la finestra e' piu' larga. Un elenco di
parametri lungo 2400 px su un monitor grande e' illeggibile: l'occhio perde la
riga fra l'etichetta e il controllo. Il log fa eccezione — quello usa tutta la
larghezza, perche' e' fatto di colonne allineate in monospazio.

---

## 6. La finestra

| | valore | perche' |
|---|---|---|
| minimo | **960 x 640** | sotto, la barra dei comandi non ci sta in una riga |
| predefinita | **1280 x 860** | ci stanno il log e dodici righe di parametri |
| tetto all'apertura | `schermo.larghezza − 48`, `schermo.altezza − 72` | su un 1366x768 la finestra nasceva piu' alta dello spazio disponibile |
| posizione | l'ultima usata, **se e' ancora dentro uno schermo che esiste** | lo schermo di ieri puo' non esserci piu' |

**Si ricorda taglia, posizione e scheda aperta.** Ripartire sempre al centro a una
misura fissa e' un fastidio su un monitor grande e un guasto su uno piccolo.

### Le altezze fisse

```
testata            56
barra dei comandi  52
striscia           40   (compare e sparisce)
linguette          40
barra della misura 28   (in fondo, sempre)
```

Il resto e' il contenuto, che si allunga.

### I tre punti di rottura

Non e' una pagina web, ma una finestra si trascina.

| larghezza | cosa cambia |
|---|---|
| **< 1120** | le impostazioni di sessione (casella + soglia) vanno a capo sotto le azioni |
| **< 1000** | la ROI sparisce dalla barra e resta solo nella barra della misura |
| **altezza < 720** | la barra della misura si riduce a tre valori: stato, battute, latenza |

⚠ Sotto il minimo **non si comprime niente**: si mette una barra di scorrimento.
Un controllo che si stringe fino a diventare illeggibile e' peggio di un controllo
che esce dalla finestra, perche' il secondo si vede e il primo si usa per sbaglio.

---

## 7. Tipografia

| | carattere | ripiego |
|---|---|---|
| interfaccia | **Segoe UI Variable**, poi Segoe UI | il carattere di sistema |
| valori e log | **Cascadia Mono**, poi Consolas | c'e' su ogni Windows 11 |

Cinque corpi, **due pesi**, e basta.

| nome | pt | peso | uso |
|---|---|---|---|
| `C_NOME` | 16 | 600 | «livedub» in testata |
| `C_STATO` | 13 | 600 | il testo dentro la pillola di stato, i numeri della barra della misura |
| `C_TITOLO` | 11 | 600 | titoli di sezione, +0,6 px di spaziatura fra le lettere |
| `C_TESTO` | 10 | 400 | tutto il resto |
| `C_NOTA` | 9 | 400 | note, nomi dei campi, unita' di misura |

**Il monospazio e' un'informazione, non un vezzo**: vuol dire «questo e' un valore,
e le colonne sono allineate apposta». Lo portano il log, gli elenchi di finestre,
i valori numerici e i nomi dei campi di config. Nel log l'allineamento e' meta' di
cio' che lo rende leggibile — ed e' il motivo per cui gli spazi vanno protetti a
mano quando si scrive in HTML, dove altrimenti si mangiano.

**Interlinea 1,45** nel testo scorrevole, **1,25** nel log. Il log e' fatto di
righe indipendenti che si scorrono con l'occhio: piu' aria lo allunga e basta.

---

## 8. Materiale

Il logo non e' piatto: ha un contorno chiaro, una luce sul bordo alto e un
lucido in alto a sinistra. L'interfaccia prende la stessa idea in dose minima —
**una sola luce, sempre dall'alto**.

| superficie | come |
|---|---|
| pannello, tessera | fondo `superficie`, e **1 px di `rgba(255,255,255,0.05)`** sul bordo alto |
| campo, bottone | fondo `superficie_alta`, contorno `bordo_forte` da 1 px |
| dialogo, pannello a tutto schermo | fondo `superficie`, ombra `0 12px 32px rgba(0,0,0,0.45)` |

Nel tema chiaro la luce diventa **ombra**: `1 px di rgba(0,0,0,0.04)` sul bordo
basso. Copiare la luce dall'alto sul tema chiaro non da' errore e da' pannelli che
sembrano ritagliati male.

### ⚠ Il bagliore ha un significato, e uno solo

L'alone menta (`0 0 12px rgba(67,241,193,0.35)`) si usa **solo** sulla spia quando
sta uscendo audio. Non sui bottoni, non sui campi col fuoco, non sui bordi.

E' l'elemento piu' facile da abusare di tutto questo documento: fa sembrare tutto
piu' bello, e un bagliore su ogni cosa non vuol dire piu' niente. Uno solo, e vuol
dire «sta parlando adesso».

### I bordi non sono contorni

Misurato: `bordo` sta a 1,3:1 e `bordo_forte` a 1,8:1 sulla superficie che
separano. Sono **fili**, e vanno bene per dividere due zone. Ma qualunque cosa
debba essere *percepita come un contorno* — il fuoco, un campo in errore, la riga
scelta in un elenco — usa `accento` o `rosso`, che stanno sopra 5:1. Un contorno
che porta un significato e non si vede e' peggio di nessun contorno.

---

## 9. Il movimento

| cosa | durata | curva |
|---|---|---|
| colore, opacita', stato di un controllo | **120 ms** | `cubic-bezier(0.2, 0, 0, 1)` |
| comparsa e scomparsa di un pannello, striscia | **200 ms** | la stessa |
| cambio del logo sereno ↔ guasto | **0 ms** | — |

### ⚠ Niente si muove in un angolo mentre il gioco gira

Questa finestra sta accanto a una partita. Qualunque cosa pulsi, rimbalzi o
scorra in periferia si prende un'attenzione che appartiene al gioco, e la si
prende **proprio quando l'utente e' meno in grado di ignorarla**. Il logo non si
anima, la spia non lampeggia, i numeri della barra della misura si aggiornano al
massimo **due volte al secondo** — non trenta, che e' la frequenza a cui arrivano.

Se il sistema chiede meno movimento (`prefers-reduced-motion`), tutte le durate
vanno a 0. Non e' una rifinitura: l'utente tipo di questo programma sta guardando
uno schermo che si muove gia' molto.

---

## 10. L'avvio, fotogramma per fotogramma

**1. Prima che si veda qualcosa.** Si legge la configurazione — profilo scelto,
override della riga di comando, e l'ultima usata. Si crea l'applicazione con lo
stile **Fusion**: una base neutra e uguale su ogni macchina, perche' lo stile
nativo di Windows non si lascia vestire del tutto da un foglio di stile.

**2. Si sceglie il tema** chiedendolo a Windows. Se non risponde si resta sullo
**scuro e non si indovina**: un default dichiarato vale piu' di una lettura che
puo' sbagliare.

**3. La finestra prende taglia e posto** da dove li aveva, tagliati sullo schermo
vero (§6).

**4. Si monta la colonna**: testata, barra dei comandi, striscia (nascosta),
linguette, contenuto, barra della misura.

**5. La prima cosa che si vede e' cosa fare.** Non il log: al centro della scheda
**Sessione**, finche' non e' stata detta la prima battuta, sta il pannello dei tre
passi.

```
        ┌──────────────────────────────────────────────┐
        │              [ logo 96 px ]                  │
        │                                              │
        │   ①  Scegli la finestra del gioco            │  ← menta, attivo
        │   ②  Tira l'area sui sottotitoli             │  ← tenue
        │   ③  Avvia                                   │  ← tenue
        │                                              │
        │   Il gioco deve stare in finestra o senza     │
        │   bordi, non a schermo intero esclusivo.      │
        └──────────────────────────────────────────────┘
```

Ogni passo fatto diventa una spunta menta e il successivo si accende. Fatti tutti
e tre, il pannello si dissolve in 200 ms e sotto c'e' il log.

Oggi quella riga esiste gia' — e' scritta nel log come testo, terza riga dopo la
scheda tecnica, e scompare sotto la prima decina di messaggi. **E' l'interfaccia
vera della prima volta e sta in mezzo a un registro diagnostico.** Tutto il resto,
166 parametri nelle altre schede, sta li' per dopo.

**6. Parte il timer a 16 ms** che svuota la coda del motore. Non e' un numero
tondo: e' un ritardo aggiunto, e il ridisegno costa 10,5 ms nel caso peggiore
misurato, quindi a 16 ci sta con un terzo di margine.

**Lo stato d'apertura e' `fermo`, con la spia `testo_fioco`** — grigia, non verde.
Grigio vuol dire «non sta girando niente», ed e' vero.

### Niente schermata di benvenuto

Non c'e' e non ci va. La prima cosa che deve arrivare all'occhio sono i tre passi;
una schermata di benvenuto li rimanda indietro di qualche secondo per mostrare un
logo che l'utente vedra' comunque in testata per tutta la sessione.

---

## 11. Le sezioni

### 11.1 Testata — h 56, fondo `superficie`

Margini `S5` ai lati, contenuto centrato in verticale, spaziatura `S3`.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [logo]  livedub   ( ● in corso )              gta5.exe · GTA V          ⓘ   │
│  40px    16/600     pillola h28              tenue, a destra          28px  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**La tessera del logo** e' 40x40, raggio 8, e contiene `livedub-64.png` a 32 px
con `S1` di margine. E' l'unica immagine dell'interfaccia. **Scambia con
`livedub-guasto-64.png` sul guasto** (§12).

**La pillola di stato** sostituisce il pallino piu' l'etichetta di oggi. Altezza
28, raggio 14, imbottitura `S1 S3`, dentro: la spia da 10 px e il testo a
`C_STATO`. Il fondo e' il colore dello stato **al 12%**, il testo e la spia sono
il colore pieno. Un pallino da 12 px isolato in una testata larga 1280 e' un
dettaglio che nessuno guarda; una pillola colorata la si vede con la coda
dell'occhio, che e' l'unico modo in cui la si guardera'.

**Il nome del bersaglio** a destra, in `testo_tenue`: e' la risposta a «ma sta
guardando la finestra giusta?», che ci si fa una volta all'inizio e mai piu'. A
riposo dice `nessuna finestra scelta`.

**ⓘ** e' l'unico bottone senza fondo: testo `accento`, sotto il mouse prende
`superficie_alta`. Apre la stessa cosa di **F1** — versione, sistema, provider,
percorso del registro, licenza.

### 11.2 Barra dei comandi — h 52

Margini `S5` ai lati, spaziatura `S2`. Due zone divise da un filo di 1 px
(`bordo`) con `S4` di respiro per parte.

```
  Scegli finestra   Seleziona area   [ AVVIA ]   Ferma   │  ☐ Ignora i sottotitoli colorati   soglia [ 60 ]
  ─────────────────── azioni ───────────────────────────    ────────── impostazioni della sessione ──────────
```

A sinistra le **azioni** (si premono e succede qualcosa adesso); a destra le
**impostazioni della sessione** (valgono finche' non le si cambia). Senza il filo
si leggono come un'unica barra di comandi, e la casella sembra un bottone.

**Un solo bottone e' quello che si preme, e si vede.** `Avvia` e' l'unico
riempito di menta, con testo `su_accento`, peso 600, e piu' imbottitura degli
altri (`S2 S5` contro `S2 S4`). Se fossero tutti uguali l'occhio dovrebbe leggerli
tutti per trovarlo.

A sessione accesa si spengono **tre** bottoni insieme — `Avvia`, `Seleziona area`,
`Scegli finestra` — e `Ferma` si accende. Un bottone spento e' `superficie` con
testo `testo_fioco`: scompare senza sparire.

Il contatore della **soglia** e' spento quando la casella accanto e' spenta. E'
l'unica dipendenza fra due controlli in questa barra, ed e' esplicita.

### 11.3 Striscia delle modifiche in attesa — h 40

Nascosta quasi sempre. Fondo `superficie_alta`, raggio 11, e **una marca ambra da
3 px sul bordo sinistro** — l'unico bordo colorato asimmetrico della finestra, e
il segno che l'occhio legge come «questo blocco e' una cosa a parte» senza doverlo
riquadrare.

```
▌ 3 modifiche in attesa (vision.ocr_backend, tts.backend, …): si applicano
▌ rifacendo la catena, un paio di secondi        [ Lascia stare ]  [ Applica ora ]
```

`Applica ora` e' un bottone **contornato di menta** e non riempito: il riempimento
menta e' di `Avvia`, e due riempimenti menta che fanno cose diverse sono un
riempimento di troppo. **Ambra e non rosso**, perche' non e' rotto niente: e' una
cosa che aspetta.

### 11.4 Le sei schede — linguette h 40

Angoli alti a 8, imbottitura `S2 S5`, distacco `S1`. Quella scelta prende il fondo
`superficie` — si salda al corpo — e **2 px di menta sotto**. Le altre stanno sul
`fondo` in `testo_tenue`.

| # | scheda | cosa c'e' |
|---|---|---|
| 0 | **Preparazione** | i tre passi da fare prima di premere Avvia, piu' i parametri della lettura e dell'area |
| 1 | **Sessione** | la battuta di adesso, chi ha parlato, e sotto il log |
| 2 | **Voce** | il motore, le voci, la fretta |
| 3 | **Volumi** | quanto forte la nostra voce, quanto si abbassa quella del gioco, e i tre tempi del duck |
| 4 | **Traduzione** | i due selettori di lingua, come si copre l'originale, e la prova dei traduttori |
| 5 | **Tutte le impostazioni** | tutti e 166, con ricerca, tre livelli, «solo a caldo» |

**«Volumi» e' nata perche' «Voce» rispondeva a due domande.** «Con che voce
parla» e «quanto forte si sente» si fanno in momenti diversi: la prima prima di
avviare, la seconda **mentre si ascolta**. E li' dentro ce n'erano tre su sei —
gli altri tre (attacco, rilascio, passthrough) si raggiungevano solo dall'albero
intero. Fuori restano `mix.prebuffer_ms`, che coi tre motori di oggi non muove
niente, e `mix.output_device`, che non lo legge nessuno.

**«Aree» non c'e' piu'.** Il documento ne prescriveva una — elenco a sinistra e
quattro bottoni a destra — ed e' stata costruita. Le zone multiple sono state
tolte il 18 agosto 2026 perche' la promessa che le reggeva (piu' scritte tradotte
insieme sopra il gioco) dal vivo non era mantenibile: l'overlay disegna **una**
scritta per volta. I tre parametri che quella scheda ospitava — `capture.solo_roi`,
`capture.roi_margin`, `vision.line_pad` — sono passati alla Preparazione, dove
stanno con l'area che si legge.

**Il log** — Cascadia Mono `C_TESTO`, interlinea 1,25, tetto a **5000 righe**
(senza, una sessione di tre ore se lo mangia tutto). Ogni riga ha **16 px di
margine sinistro riservati alla marca di gravita'** (§13): il testo resta allineato
che ci sia o no.

**Impostazioni avanzate** ha in cima ricerca, una tendina larga 140 (`l'essenziale`
/ `le principali` / `tutto`), la casella `solo a caldo` e `Riporta ai default`. I
tre livelli sono la cosa piu' importante di quel pannello: 166 manopole sono la
risposta giusta a una domanda che quasi nessuno fa, e mostrarle tutte allo stesso
modo non e' neutrale — e' scegliere l'ultimo dei tre utenti e far pagare agli
altri due.

Ogni riga di parametro (h 40, raggio 6) ha un **bordo sinistro da 2 px trasparente
che diventa menta sotto il mouse**: si accende senza spostare niente, ed e' per
questo che e' trasparente invece di assente.

### 11.5 La barra della misura — h 28, in fondo

**Nuova.** Fondo `superficie`, un filo `bordo` sopra, testo in monospazio
`C_NOTA`, valori in `C_STATO`. Sempre presente.

```
 OCR 19.9 Hz  ·  battute 34  ·  latenza p50 1150 ms  ·  compress. 1.23  ·  underrun 0  ·  ROI x0.204 y0.884 w0.592 h0.070
```

Un valore fuori norma passa in **ambra**; `underrun > 0` passa in **rosso**. Sono
gli unici numeri della finestra che cambiano da soli, e per questo si aggiornano a
**2 Hz** e non a trenta.

Esiste perche' questo progetto misura tutto e poi **non lo guarda finche' non
finisce la sessione**. Le stesse quantita' sono gia' nel rapporto finale: metterle
sotto gli occhi durante la partita e' la differenza fra accorgersi che l'OCR e'
sceso a 12 Hz e scoprirlo mezz'ora dopo leggendo un file.

### 11.6 I due pannelli a tutto schermo

**Il selettore d'area** — velo `rgba(0,0,0,0.55)` su tutto lo schermo, cursore a
croce, rettangolo con tratto **menta** da 2 px e i quattro angoli marcati da
squadrette da 12 px. Dentro il rettangolo il velo si toglie del tutto.

⚠ **Semitrasparente e non opaco**, perche' l'area va scelta *guardando i
sottotitoli*: su un pannello nero si tira un rettangolo a memoria, che e'
esattamente il modo in cui la ROI di serie ha finito per inquadrare il tappeto.
Esc chiude senza toccare niente, e un clic per sbaglio (meno di 20x8 px) non
azzera la ROI.

Sotto il cursore, mentre si tira, un'etichetta in monospazio con le quattro
frazioni. **Se l'altezza supera 0,12 l'etichetta diventa ambra** e dice
`troppo alta`: la fascia d'analisi e' l'area piu' un respiro proporzionale a lei,
e un rettangolo alto un sesto dello schermo diventa 391 px per una riga da 45. Oggi
questo avviso arriva **dopo**, come riga di log, quando il rettangolo e' gia'
stato lasciato.

**Il selettore di finestra** — dialogo 820x460, raggio 18, elenco in monospazio,
**ordinato per area** perche' il gioco e' quasi sempre la finestra piu' grande: la
risposta giusta e' in cima nove volte su dieci. In fondo `Aggiorna` a sinistra,
`Tutto lo schermo` e `Usa questa` (riempito di menta) a destra. Doppio clic su una
riga vale come `Usa questa`.

---

## 12. Gli stati

**Il colore lo decide una regola, non chi chiama.** Sta in `core/motore.py`,
`colore_stato(testo, tema)`, e sta fuori dalle finestre perche' e' una regola e non
un disegno — cosi' si verifica senza aprire niente.

```
c'e' un "!", o "error", o "guast", o "interrott"   →  rosso
c'e' "ferm" o "pront"                              →  testo_fioco
altrimenti                                         →  menta
```

E' servita: «audio interrotto» veniva **verde** — il colore del «va tutto bene»
sopra una catena morta — perche' non contiene ne' `!` ne' «guasto», e nessuno
poteva accorgersene senza staccare le cuffie a meta' sessione.

| stato | pillola | spia | logo |
|---|---|---|---|
| `fermo` | `testo_fioco` | ferma | sereno |
| `in corso` | **menta** | **con alone** | sereno |
| `riavvio in corso` | ambra | ferma | sereno |
| `! audio interrotto` | rosso | ferma | **guasto** |
| `guasto` | rosso | ferma | **guasto** |

### ⚠ Il logo cambia sulla stessa regola, non su una seconda

```python
rotto = self._colore_stato == self.tavolozza.rosso
```

Non un elenco di stati brutti scritto in testata. Questo progetto ha gia' pagato
per due strade parallele che non ereditavano le cure l'una dell'altra: un elenco
scritto qui si separerebbe da `colore_stato` al primo stato nuovo, e si
separerebbe **in silenzio**, con la suite verde.

E al cambio di tema il confronto va rifatto contro la tavolozza **nuova**, perche'
`rosso` e' `#ff6b5e` sullo scuro e `#cc372c` sul chiaro. E' esattamente il punto
in cui una condizione scritta su una stringa di colore congelata smette di
funzionare senza dare errore.

---

## 13. Gli errori

Quattro livelli, e la differenza fra loro e' **quanto e' morto il programma**, non
quanto e' brutta la notizia.

| livello | cosa e' successo | dove | segno |
|---|---|---|---|
| **nota** | qualcosa e' cambiato | una riga di log | nessuna marca |
| **avviso** | va avanti, ma qualcosa e' storto | una riga di log | marca **ambra** 3x16 nel margine |
| **guasto** | la sessione e' chiusa | tessera nel log + pillola + logo | marca **rossa**, tessera |
| **crash** | eccezione non prevista | tutto il precedente + un dialogo | dialogo modale |

### ⚠ Avviso e guasto non possono vedersi uguali

Oggi si vedono uguali: ogni riga va nel log dello stesso colore, `!` compresi.
Quindi `! l'area e' alta 0,180 dello schermo` (un consiglio) e
`! l'audio si e' fermato` (la fine della sessione) escono identici, in mezzo a
righe che scorrono.

E la cura ovvia — colorarli di rosso — e' sbagliata due volte: brucia il canale
del colore del testo, che appartiene alle voci (§4), e addestra l'occhio a
ignorare il rosso, perche' gli `!` di questo programma sono quasi tutti avvisi che
non fermano niente.

Quindi: **una marca da 3 px nel margine sinistro**, ambra o rossa, raggio 4. Il
testo resta del colore del testo. Il rosso pieno resta alla pillola e al logo, che
sono l'unico posto in cui vuol dire «la catena non sta girando».

### La tessera del guasto

Un guasto non e' una riga: e' una tessera, larga quanto il log, fondo
`superficie_alta`, raggio 11, marca rossa a sinistra, e **dentro ci sta il
bottone**.

```
▌ L'audio si e' fermato                                    12:04:31
▌ OSError: [Errno -9988] Stream closed
▌
▌ Probabile: cuffie o altoparlanti staccati, oppure il device
▌ e' cambiato sotto i piedi.
▌
▌                              [ Apri il registro ]  [ RIPROVA ]
```

**Un errore deve dire cosa fare, e il comando che nomina deve essere premibile.**
E' una regola che viene da un difetto vero: la prima versione del guasto audio
scriveva «Ricollega e premi Avvia» e lasciava `Avvia` **spento**, la sessione
aperta, il WAV mai scritto e lo stato verde. Il messaggio indicava un bottone che
non si poteva premere.

Metterci dentro il bottone e' la conclusione naturale: se il testo sa cosa fare,
lo puo' fare. E ha un effetto secondario che vale da solo — **non si puo' scrivere
la tessera senza decidere quale sia l'azione di ricupero**, quindi il caso in cui
non c'e' azione salta fuori mentre si scrive l'errore invece che davanti
all'utente.

Da qui la regola generale: *fermare i thread non e' fermare la sessione*. Ogni
cura di un guasto risponde alla domanda **«cosa fa la strada normale che questa
non fa?»** — chiudere la sessione, scrivere il WAV, rimettere i bottoni, scrivere
lo stato.

### Il dialogo del crash

L'unica finestra modale del programma, e resta l'unica. Un'eccezione dentro un
callback di Qt stampa su una console che nell'eseguibile non esiste, e la finestra
resta li' come se niente fosse — **peggio di un crash, perche' si continua a
usarla credendo che funzioni**. Dice il tipo, il messaggio, il percorso del
registro, e ha un bottone che copia tutto negli appunti.

---

## 14. Accessibilita'

- **Il fuoco si vede sempre**: contorno menta da 2 px, staccato di 2 px
  dall'elemento, raggio `R(h) + 2`. Non si toglie mai. Chi naviga col Tab senza
  contorno di fuoco non naviga.
- **Il colore non e' mai l'unico segnale.** La pillola ha il testo dello stato,
  non solo la tinta; la marca d'errore ha una tessera con delle parole; le voci
  del log hanno la sigla del personaggio accanto al colore. Un utente daltonico
  perde le sei voci come *identita' a colpo d'occhio* e le ritrova nella sigla —
  ed e' la ragione per cui la sigla non si toglie mai «perche' tanto c'e' il
  colore».
- **Contrasto**: testo normale sopra 4,5:1, testo grande e contorni significativi
  sopra 3:1. Le due eccezioni dichiarate sono `testo_fioco` (2,9:1 sullo scuro) e
  `accento_chiaro` sul tema chiaro (1,4:1): il primo si usa **solo** per il
  disabilitato, il secondo **solo** come riempimento.
- **Ogni controllo ha un nome accessibile.** Un bottone chiamato «Avvia» va bene;
  la spia e il logo no, e vanno descritti («la catena sta girando»).
- **Il movimento si spegne** se il sistema lo chiede.
- **Tutto si raggiunge da tastiera**, e le cinque scorciatoie sono: `Ctrl+S` salva
  la configurazione, `Ctrl+O` la apre, `Ctrl+F` va alla ricerca, `Ctrl+L` copia la
  diagnostica, `F1` chi siamo.

---

## 15. Cosa non si fa mai

**Non entra niente nel fotogramma catturato.** Catturando lo schermo invece della
sola finestra del gioco, tutto quello che si disegna sopra finisce nell'immagine
che va all'OCR: misurato, il **100%** dei pixel dell'overlay. Il logo, i dialoghi
e il selettore d'area non fanno eccezione — ed e' la ragione per cui il selettore
d'area e' un pannello che si chiude e non un riquadro che resta.

**Nell'overlay sopra il gioco non ci va niente di questo documento.** Quella
finestra ha regole opposte — niente bordi, i clic la attraversano, non ruba il
fuoco — e un compito solo: far sembrare che il sottotitolo originale non ci sia mai
stato e metterci sopra il nostro. Nessun logo, nessuna filigrana, nessun angolo
stondato.

**I sei colori delle voci sono dei personaggi e di nessun altro.**

**Un colore nuovo entra in `Tavolozza` o non entra.** Il `#39d353` scritto a mano
nel selettore d'area e' l'esempio di come si comincia: funziona, si vede, e nel
tema chiaro non l'ha mai guardato nessuno.

**Nessun numero si copia da un elemento di altezza diversa.**

---

## 16. In che ordine si fa

Non e' un elenco di desideri: e' un ordine, e le prime due righe vanno prima delle
altre perche' tutto il resto le usa.

| # | cosa | perche' prima |
|---|---|---|
| 1 | `Tavolozza` con i dodici ruoli nuovi, due temi | tutto il foglio di stile ne dipende |
| 2 | le costanti `S0..S7`, `R(h)`, i cinque corpi | idem |
| 3 | il foglio di stile riscritto sui ruoli nuovi | qui la finestra cambia faccia |
| 4 | il logo in testata + `setWindowIcon` + `.ico` | non c'e' **nessun** `QIcon` nel progetto |
| 5 | lo scambio sereno ↔ guasto legato a `colore_stato` | una riga, e chiude il cerchio dei due loghi |
| 6 | la pillola di stato al posto di pallino + etichetta | |
| 7 | le marche di gravita' nel log | qui l'avviso smette di sembrare un guasto |
| 8 | la tessera del guasto col bottone dentro | |
| 9 | il pannello dei tre passi | |
| 10 | la barra della misura | l'unica che tocca il motore: gli serve una lettura a 2 Hz |
| 11 | il `#39d353` dentro la tavolozza (diventa menta) | |
| 12 | i punti di rottura della larghezza | ultimo: e' rifinitura |

### ⚠ E il modo di verificare tutto questo e' guardarlo

Il pezzo peggiore mai consegnato in questo progetto e' arrivato **verde, con gli
import a posto**, e il difetto era il primo che si vedeva mettendolo a schermo: la
finestra dimensionata sul testo originale con dentro quello tradotto. Nessuna
verifica lo prendeva perche' non esisteva nessuna verifica su quel pezzo, e la
suite verde e' stata scambiata per una conferma.

Quindi: dopo ogni riga della tabella qui sopra, **uno screenshot**. Nei due temi.
E il logo a 64 px guardato al 100%, che e' l'unica taglia a cui si vede se e'
ancora riconoscibile.

Quello che si puo' provare senza aprire una finestra **deve stare fuori dalla
finestra**: `colore_stato` e' gia' li', e ci vanno anche `R(h)`, la scelta della
tavolozza e la regola che decide la marca di gravita' di una riga. Sono regole,
non disegno, e si verificano in una suite che gira senza hardware.

---

## 17. Appendice — i valori, pronti da incollare

```python
SCURA = Tavolozza(
    nome="scuro",
    fondo="#0f131b", superficie="#181e29", superficie_alta="#212836",
    bordo="#2c3444", bordo_forte="#3b4557",
    testo="#e4e9f2", testo_tenue="#808ba5", testo_fioco="#545e71",
    accento="#43f1c1", accento_chiaro="#95ffdf", accento_scuro="#1fb894",
    su_accento="#06231c",
    ambra="#f5b544", rosso="#ff6b5e",
    voci=("#ffb86b", "#79c0ff", "#ff8fb1", "#c9a0ff", "#f2d65c", "#9ee85f"),
)

CHIARA = Tavolozza(
    nome="chiaro",
    fondo="#f2f4f8", superficie="#ffffff", superficie_alta="#e9edf4",
    bordo="#d3dae6", bordo_forte="#b9c3d4",
    testo="#141922", testo_tenue="#5a6579", testo_fioco="#7e8aa2",
    accento="#07785d", accento_chiaro="#43f1c1", accento_scuro="#05614c",
    su_accento="#06231c",
    ambra="#a16207", rosso="#cc372c",
    voci=("#b45309", "#1e5fbf", "#b8286a", "#6d3ad6", "#8a6a00", "#3f7d1e"),
)

S0, S1, S2, S3, S4, S5, S6, S7 = 2, 4, 8, 12, 16, 24, 32, 48
C_NOME, C_STATO, C_TITOLO, C_TESTO, C_NOTA = 16, 13, 11, 10, 9
UI, MONO = "Segoe UI Variable", "Cascadia Mono"

H_TESTATA, H_BARRA, H_STRISCIA, H_LINGUETTE, H_MISURA = 56, 52, 40, 40, 28
MIN_LARGO, MIN_ALTO = 960, 640
LARGO, ALTO = 1280, 860
MAX_CONTENUTO = 880

def R(h: int) -> int:
    """Il raggio di un elemento alto `h`. Dal logo: 19,8% dell'altezza."""
    return max(4, min(18, round(0.20 * h)))
```

⚠ Due cose che Qt **non sa disegnare** da un foglio di stile e vanno generate
come PNG, un giro per tavolozza perche' dipendono dal colore: il segno di **spunta**
della casella e i **triangolini** delle tendine e dei contatori. Il trucco dei tre
bordi CSS qui non funziona — Qt accetta quelle proprieta' senza lamentarsi e
disegna un quadratino, che e' precisamente il tipo di difetto che non da' errore.
Si disegnano a 4x e si rimpiccioliscono con LANCZOS, perche' PIL non fa
antialiasing sulle linee.
