# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`),
doppiaggio italiano dal vivo dei sottotitoli dei videogiochi.

## La prima cosa: il grafo è la memoria

In `graphify-out/graph.json` c'è la mappa della codebase. Per **qualunque**
domanda architetturale — dove sta X, cosa rompo se tocco Y, chi chiama cosa — si
interroga quello **prima** di partire a grep:

```
graphify query "<domanda>"
```

Costruirlo è caro, interrogarlo no. **È stato ricostruito da zero il 18 agosto**,
dopo la rimozione delle aree: un `--update` si sarebbe rifiutato di rimpicciolire
il grafo, ed è il caso in cui il rebuild è la strada giusta. Conosce quindi la
finestra a cinque schede, `ui/tutorial.py`, `ui/lingua.py`, `translate/lingue.py`
e i 41 cataloghi.

Si riaggiorna con `/graphify . --update` **dopo** modifiche grosse, non prima di
ogni task.

## Dove siamo

Suite verde a **1764 verifiche**. `SviluppoProgetto.md`: **18 step su 19**.

Restano **due voci, e sono decisioni tue, non lavoro**: il repo GitHub e il sito.
Il link donazioni è chiuso (Ko-fi, «Buy me a token!», nel README).

## Cosa è successo il 18 agosto

**La finestra parla quarantuno lingue.** `ui.lingua` (default `auto`, segue
Windows), 41 cataloghi da 214 chiavi in `ui/lingue/*.json`, generati con
`tools/traduci_ui.py` e scritti nel repo. Cambia a caldo come il tema; arabo,
ebraico, persiano e urdu ribaltano il verso della finestra. Nessuna lingua fa
sforare le schede: la più larga è il tamil a 872 px sul minimo di 960.

**Una guida iniziale in sei passi** (`ui/tutorial.py`), il primo è la lingua.
Dove può controlla invece di chiedere fiducia.

**La scheda Sessione non è più un log**: in cima la battuta di adesso con la sua
voce e la sua fretta, poi chi ha parlato con una tessera per personaggio, il
registro sotto. E il selettore di finestra non è più illeggibile sotto il mouse
(1,12:1 → 13,95:1 sul tema scuro).

**Le aree multiple sono state tolte**, su decisione dell'utente: *infattibile*.
Girava, con le sue verifiche verdi, ma la promessa che la reggeva — più scritte
tradotte insieme sopra il gioco — dal vivo non è mantenibile, perché **l'overlay
disegna una scritta per volta**. Ne restano due pezzi: `vision.roi.troppo_grande`
e `translate.misura_originale` (il tradotto che tiene la misura dell'originale
stringendo il carattere, **spento di serie**).

**Il tetto del parlato arriva a 3×**, coi default fermi sulle misure.

## Quindi il lavoro di adesso, in ordine

1. **Provare dal vivo col gioco acceso**, che è la cosa che manca a tutto il
   resto. Gli screenshot dicono che la finestra è quella del documento, non come
   sta **accanto a una partita**. Da guardare in particolare: la scheda Sessione
   rifatta (serve davvero mentre giochi, o distrae?), il velo al cambio di
   lingua, e la guida iniziale su una macchina che non è questa.

   ```powershell
   .\.venv\Scripts\python.exe -m tools.ui_qt --profile live
   ```

   ⚠ **senza `--no-save`**, se no la sessione non finisce in `runs/` e non si può
   rileggere con `tools/reopen`. È già successo.

2. **`translate.misura_originale`, la scelta d'occhio.** È spento e va giudicato
   acceso, su una frase molto più lunga dell'originale: il tradotto sta nel
   riquadro ma diventa piccolo, e a un certo punto si legge peggio dell'originale
   che copre. Nessuna misura può decidere dove sta quel punto.

3. **L'HUD pronunciata**, l'unico difetto vero rimasto aperto dalla prova dal
   vivo dell'11 agosto, e aspetta una decisione fra due strade perché una tocca
   una soglia che vale per tutti i sottotitoli. La misura è già fatta: le letture
   consecutive di `Sali sul <spazzatura>` si somigliano fra **0,58 e 0,77** e
   `vision.continue_similarity` vale 0,75, quindi dieci su dodici aprono una
   battuta nuova invece di continuare quella di prima. L'altra strada è una
   regola sul **prefisso comune**, che non tocca il caso generale.

4. **`! l'audio si e' fermato: OSError [Errno -9988]`**, visto otto volte nel
   registro del 17 agosto e mai più dopo. Va capito se è il guasto vero che
   quella guardia esiste per prendere, o il normale **Ferma** raccontato come
   guasto: si scioglie guardando se quelle righe cadono sempre subito dopo uno
   stop.

5. **`menta-anteprima.png` si è scollata dal prodotto**: mostra quattro schede,
   oggi sono cinque. È l'immagine che finirebbe nel README o nel sito. Si
   rigenera con `tools/scatta.py`, che fotografa la finestra vera.

6. **Cancellare la finestra Tk**, quando la Qt avrà fatto una sessione vera senza
   sorprese. Oggi resta solo per il confronto (`prova.ps1 -Tk`), non è vestita
   Menta e non è più l'entry point di niente.

## Le due decisioni ferme, che aspettano te

1. **Creare il repo GitHub.** È tutto pronto: README col diagramma, `LICENZE.md`,
   `installa.ps1`, `livedub.spec`, `livedub.bat`, il link donazioni.
   **Da decidere prima di pubblicare**: i commit fino al 17 agosto portano il
   trailer `Co-Authored-By: Claude`. Dal 18 in poi non ce ne sono più. Toglierli
   dai vecchi significa **riscrivere la storia**, e dopo la pubblicazione si
   riscriverebbe una storia già clonata: la finestra per decidere è adesso.
2. **Il sito.**

E una decisione d'orecchio che resta da mesi: **promuovere `line_pad` a 0,2 come
default**. Misurato meglio su tutti e due i giochi, ma cambia il gioco principale
(130 → 123 battute aperte) e quello lo giudica l'ascolto.

## Come si prova quello che scrivi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                    # 1764 verifiche
.\.venv\Scripts\python.exe -m tools.selftest lingue ui_lingua tutorial
.\.venv\Scripts\python.exe -m tools.selftest menta menta_regole menta_finestra
.\.venv\Scripts\python.exe -m tools.ui_qt --profile live        # la finestra, dal vivo
.\.venv\Scripts\python.exe -m tools.scatta runs\menta          # 14 schermate, due temi
.\.venv\Scripts\python.exe -m tools.scatta runs\g --lingua de  # e in un'altra lingua
.\.venv\Scripts\python.exe -m tools.scatta runs\g --tutorial   # la guida, passo per passo
.\.venv\Scripts\python.exe -m tools.traduci_ui --controlla     # quanto manca a ogni catalogo
.\.venv\Scripts\python.exe -m tools.traduci_ui --misura        # e se qualche lingua sfora

# la catena su una registrazione, senza gioco
.\.venv\Scripts\python.exe -m tools.dub yt_scena.mp4 --profile gtav `
    --start 29 --end 315 --set vision.ocr_backend=oneocr
```

`mafia_scena.mp4` è il secondo gioco (Atto 3 «Pizzu», 150 s, gitignorato);
`assets/gioco2/` ha le due schermate che il gruppo `gioco2` usa — una su scena
chiara e una su quasi nero, cioè il caso difficile e la linea di base.

## Come voglio che tu lavori

- **Scrivi solo quando hai finito.** Non commentare ogni passo.
- **Descrivi in modo semplicissimo ma dettagliato** cosa hai fatto.
- **Non sprecare token.**
- **Prima di azzardare, chiedi.**
- **Interroga il grafo prima di grep**, e aggiornalo a fine sessione.
- **Nei commit non compare mai Claude**, in nessuna forma: niente trailer, niente
  co-autori. L'autore è sempre e solo l'utente.

## Le regole di metodo

`CLAUDE.md` le ha per esteso, e valgono più del codice. Le tre che hanno morso di
più nelle ultime sessioni:

**Controllare che la misura possa esprimere la risposta**, prima di leggere il
risultato. Un numero impossibile è più utile di uno sbagliato: quello sbagliato
si archivia.

**Un pezzo che nessuno ha guardato non è «scritto», è «supposto».** Ogni difetto
grafico è uscito da uno screenshot, non da una rilettura del codice.

**Una cura è quasi sempre più stretta del difetto.** La guardia che impediva alla
guida di aprirsi durante le verifiche copriva «costruita e dichiarata fuori
schermo» e non «costruita e mai mostrata»: la suite è rimasta appesa dieci minuti
senza stampare una riga. Non rossa — appesa. La domanda che la prende è sempre
*«cosa fa la strada vecchia che questa non fa?»*.

Fine del prompt.
