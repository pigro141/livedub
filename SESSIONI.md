# Le sessioni che restano, una per volta

Questo file esiste per un motivo solo: **una sessione di Claude Code = un
compito**. Aprire una sessione e chiederle tre cose costa il triplo e consegna un
terzo, perché il contesto si riempie di roba che non serve al compito vero.

Si apre una sessione nuova, si incolla **soltanto** il blocco `PROMPT` della
sessione di turno, si finisce, si chiude. Poi la prossima.

**L'ordine non è un suggerimento.** Le sessioni dalla F in poi producono
*artefatti* — immagini, pacchetti, pagine — e un artefatto generato prima che il
programma sia fermo è un artefatto già scaduto. È già successo: `livedub.exe` è
del 10 agosto (prima della finestra Menta, delle quarantuno lingue, della guida e
della rimozione delle aree) e `menta-anteprima.png` mostra quattro schede quando
oggi sono cinque. **Non anticiparle.**

Stato al 18 agosto: suite verde a 1813 verifiche.

---

## A — `translate.misura_originale` diventa un'opzione della finestra

Piccola, chiusa, nessuna decisione d'occhio richiesta: si mette l'interruttore,
si giudica dopo.

```
PROMPT
------
Lavori su livedub. Leggi CLAUDE.md prima di toccare qualcosa.

`translate.misura_originale` esiste in config, è spento di serie e non è
raggiungibile dalla finestra. Fa questo: il sottotitolo tradotto mantiene la
misura di quello che copre, stringendo il corpo del carattere invece di
allargare il riquadro. È l'unica metà utile della modalità `schermo`
sopravvissuta alla rimozione delle aree.

Compito: renderlo **un'opzione della finestra Qt** (`tools/ui_qt.py`), nella
scheda Traduzione, accanto agli altri campi di `translate`. Resta **spento di
serie**: si accende per giudicarlo, non si promuove.

Prima di scrivere, interroga il grafo (`graphify query "..."`) per sapere dove
i campi di `translate` diventano widget: in questo progetto il pannello si
**ricava** dallo schema (`core/schema.py`) invece di essere scritto a mano, e la
spiegazione del campo viene dal commento in `core/config.py`. Quindi molto
probabilmente non c'è nessun widget da scrivere — c'è da capire perché quel
campo non compare già, e la risposta giusta potrebbe essere una riga sola. Se
invece scopri che va scritto a mano, fermati e dimmi perché prima di farlo.

Due cose da non sbagliare:
- la spiegazione del campo **non si riscrive**: viene dal commento di
  `core/config.py`, che contiene le misure. Se il commento è povero, arricchisci
  quello.
- l'etichetta va nei cataloghi della finestra: `tools/traduci_ui.py --estrai`
  la fa comparire fra le mancanti. Rigenera i cataloghi solo se serve davvero, e
  con `--controlla` dimmi quanto manca dopo.

Prova: `.\.venv\Scripts\python.exe -m tools.selftest` (1813 verifiche, deve
restare verde) e `.\.venv\Scripts\python.exe -m tools.scatta runs\opz
--profile gtav`, poi **guarda l'immagine** della scheda Traduzione: in questo
progetto ogni difetto grafico è uscito da uno screenshot, mai da una rilettura
del codice.

Non committare senza suite verde. Nei commit non compare mai Claude, in nessuna
forma.
```

---

## B — `OSError [Errno -9988]`: guasto vero o **Ferma** raccontato male?

L'ipotesi dell'utente è che sia il normale **Ferma** che passa dalla guardia
sbagliata e viene stampato come guasto. Va **dimostrata**, non creduta.

```
PROMPT
------
Lavori su livedub. Leggi CLAUDE.md prima di toccare qualcosa.

Nel registro del 17 agosto compare otto volte
`! l'audio si e' fermato: OSError [Errno -9988]`, e mai più dopo.

Domanda, una sola: è il guasto vero che quella guardia esiste per prendere,
oppure è il normale **Ferma** dell'utente raccontato come guasto?

Si scioglie con un dato che è già scritto: guarda se quelle otto righe cadono
**sempre subito dopo uno stop** — cioè se nel registro (o negli eventi della
sessione, in `runs/`) c'è ogni volta una fermata volontaria nei millisecondi
precedenti. Se sì, è il secondo caso; se anche una sola cade a sessione viva, è
il primo, e allora la domanda cambia.

Poi **riproducilo tu**: apri la finestra, avvia, premi Ferma, guarda il
registro. -9988 è `paInputOverflowed` di PortAudio, quindi la spiegazione
«chiudo il flusso mentre sta leggendo» è plausibile — ma plausibile non è
misurato, e questo repo ha già archiviato tre conclusioni false partendo da una
spiegazione che funzionava.

Se è **Ferma raccontato come guasto**, correggilo: una fermata volontaria non
deve stampare un `!`. Ma la cura va scritta guardando cosa fa la strada vecchia
che la nuova non fa — qui, la guardia deve continuare a prendere il guasto vero
quando c'è. Un `!` speso dove non è successo niente svaluta tutti gli altri, ed è
lo stesso difetto già corretto per «nessun catalogo per auto».

Prova: `.\.venv\Scripts\python.exe -m tools.selftest`. Se aggiungi una regola,
mettila **fuori da Qt** (in `core/`), perché è lì che si può verificare senza
aprire una finestra.

Non committare senza suite verde. Nei commit non compare mai Claude.
```

---

## C — Guardare la guida della prima volta

Non è lavoro: è una cosa da **vedere**. Costa trenta secondi e non richiede il
gioco acceso.

```
PROMPT
------
Lavori su livedub. Fammi vedere la guida iniziale (`ui/tutorial.py`, sei passi,
si apre da sola la prima volta) senza aprire il gioco:

.\.venv\Scripts\python.exe -m tools.scatta runs\guida --profile gtav --tutorial

Poi dimmi **soltanto dove sono i PNG** e quanti sono. Non descrivermeli a
parole e non aprirli tutti: li guardo io. Se qualcuno esce vuoto o con i
quadratini al posto delle lettere, quello sì, dimmelo — vuol dire che è stato
fotografato con la piattaforma sbagliata (`QT_QPA_PLATFORM=offscreen` non ha
nessun carattere installato; `tools/scatta.py` usa `WA_DontShowOnScreen`
apposta).
```

---

## D — La prova dal vivo, col gioco acceso

**È la cosa che manca a tutto il resto.** Gli screenshot dicono che la finestra è
quella del documento; non dicono come sta accanto a una partita. La fa l'utente,
la sessione serve solo a preparare il campo e a rileggere dopo.

```
PROMPT
------
Lavori su livedub. Leggi CLAUDE.md e PROSSIMA_SESSIONE.md.

Oggi si fa **la prova dal vivo col gioco acceso**. Io gioco, tu prepari e poi
rileggi. Non scrivere codice se non te lo chiedo.

Prima: controlla che il campo sia pronto (venv, cattura, `ollama serve` se serve
la traduzione, il modello) e **stampami la configurazione** con cui parte, per
esteso. Una riga di comando lunga otto opzioni copiata male non dà errore: dà
una prova fatta con un'altra configurazione. `tools/prova.ps1` fa già questi
controlli.

.\.venv\Scripts\python.exe -m tools.ui_qt --profile live

ATTENZIONE: **senza `--no-save`**, se no la sessione non finisce in `runs/` e non
si può rileggere. È già successo.

Le tre cose da guardare, che sono d'occhio e non di numero:
- la **scheda Sessione** rifatta (battuta di adesso in cima, tessere dei
  personaggi, registro sotto): serve davvero mentre gioco, o distrae?
- il **velo al cambio di lingua**;
- la **guida iniziale**.

Quando ti dico che ho finito, rileggi la sessione con
`.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella>` e dimmi i numeri
veri: battute, latenza p50/p95, `dub.rate_x1000` ai percentili, `mix.underrun`,
Hz dell'OCR, `overlay.ritardo`.

Se ti dico «non funziona» e i numeri dicono di sì, **sono i numeri a essere sotto
esame**: chiedimi *il secondo* in cui l'ho sentito, non un'altra impressione.
```

---

## E — Cancellare la finestra Tk

**Solo dopo che la D è andata bene.** Finché la Qt non ha fatto una sessione vera
senza sorprese, la Tk è la rete.

```
PROMPT
------
Lavori su livedub. Leggi CLAUDE.md prima di toccare qualcosa.

La finestra Tk (`tools/ui.py`, `ui/tema.py`) non è più l'entry point di niente:
il prodotto è la Qt (`tools/ui_qt.py`), che è quella che impacchetta
`livedub.spec`, quella che apre `livedub.bat`, quella che lancia
`tools/prova.ps1`. La Tk resta solo per il confronto, raggiungibile con
`prova.ps1 -Tk`, non è vestita Menta e non lo sarà.

Compito: toglierla. Ma **prima di cancellare, guarda cosa ci si appoggia**:
interroga il grafo (`graphify query "chi usa ui/tema.py"`, `"chi importa
tools/ui.py"`) e portami l'elenco. Cerca in particolare pezzi che sembrano della
Tk e invece li usa anche la Qt, e il flag `-Tk` in `tools/prova.ps1`, la suite
(`tools/selftest.py`: qualche gruppo potrebbe provare `ui/tema.py`), lo spec e la
documentazione.

La domanda giusta non è «il difetto è sparito» ma **«cosa faceva prima che
adesso non fa più?»**. Quindi dimmi, prima di togliere, cosa smette di essere
possibile.

Prova: `.\.venv\Scripts\python.exe -m tools.selftest` deve restare verde, e il
conto delle verifiche scenderà — dimmi di quanto e quali gruppi sono spariti,
perché un gruppo che sparisce senza che nessuno se ne accorga è esattamente come
un ripiego silenzioso.

Aggiorna `CLAUDE.md` e `docs/interfaccia.md` dove nominano la Tk.
Non committare senza suite verde. Nei commit non compare mai Claude.
```

---

## F — Rifare gli artefatti scaduti

**Da qui in poi solo quando il programma è fermo**, cioè dopo A, B, D ed E.

Sono cose generate quando il programma non era finito, e che oggi mostrano un
prodotto che non esiste più: `menta-anteprima.png` con quattro schede, il README
scritto prima delle quarantuno lingue e della guida, `livedub.spec` e
`installa.ps1` mai riprovati dopo.

```
PROMPT
------
Lavori su livedub. Leggi CLAUDE.md e PROSSIMA_SESSIONE.md.

Il programma adesso è fermo. Tutto il materiale che lo *racconta* è stato
generato quando non lo era, quindi racconta un prodotto che non esiste più. Va
rifatto, non ritoccato.

Fai il **censimento prima di scrivere**: portami l'elenco di ogni file che
descrive il prodotto (immagini, README, LICENZE.md, `installa.ps1`,
`livedub.spec`, `livedub.bat`, docs) con **la data e cosa dice di sbagliato**.
Poi aspetta il mio ok.

Quello che già so essere scaduto:
- `menta-anteprima.png` mostra **quattro schede**, oggi sono cinque. Si rigenera
  con `.\.venv\Scripts\python.exe -m tools.scatta runs\menta --profile gtav`,
  che fotografa la finestra vera — non si disegna a mano e non si ritocca.
- il README non nomina le **quarantuno lingue** della finestra né la **guida
  iniziale**, che sono le due cose più visibili aggiunte dopo che è stato
  scritto. E l'ordine giusto è quello che l'utente incontra: si apre, sceglie la
  lingua, la guida lo porta per mano.
- le **aree multiple** sono state tolte: qualunque documento che le prometta va
  corretto, perché promette una cosa che non c'è.

Regola sulle immagini: si fotografa la finestra vera con `tools/scatta.py`,
**mai** `QT_QPA_PLATFORM=offscreen` (zero caratteri installati: restituisce una
finestra di quadratini, cioè una fotografia che non può mostrare il difetto che
si sta cercando).

Non committare senza suite verde. Nei commit non compare mai Claude.
```

---

## G — L'eseguibile

**Ultima cosa prima di pubblicare**, perché un pacchetto costruito mentre il
programma cambia si verifica una volta e domani non è più quello.

```
PROMPT
------
Lavori su livedub. Leggi CLAUDE.md e PROSSIMA_SESSIONE.md.

Va costruito l'eseguibile. `livedub.spec` c'è ed è aggiornato, ma l'unico exe mai
costruito è del **10 agosto** — prima della finestra Menta, delle quarantuno
lingue, della guida iniziale e della rimozione delle aree. Quindi non è «già
fatto»: è **supposto**.

Il posto in cui guardare per primo sono i **dati**, non il codice:
- `core/config.py` deve viaggiare fra i dati, se no il pannello resta **senza
  spiegazioni** (166 campi muti);
- `ui/lingue/*.json` (41 cataloghi) devono viaggiare, se no l'exe è **solo
  italiano, e senza dirlo** — che è la forma peggiore di difetto in questo
  progetto: il ripiego silenzioso;
- controlla che non ce ne siano altri della stessa specie: qualunque file che il
  programma **legge dal disco** e che non è codice. Interroga il grafo, non
  fidarti dello spec.

Poi **provalo davvero**: apri l'exe su questa macchina, guarda che il pannello
abbia le spiegazioni, cambia la lingua della finestra in tedesco e in arabo, apri
la guida. Un exe che parte non è un exe che funziona. Se puoi, provalo in una
cartella dove il repo non c'è: è l'unico modo per accorgersi di un file che
l'exe sta leggendo dal sorgente invece che da dentro di sé.

Dimmi quanto pesa e quanto ci mette ad aprirsi.

Non committare senza suite verde. Nei commit non compare mai Claude.
```

---

## H — GitHub e il sito

**Ultima in assoluto**, e comincia con una decisione che dopo non si può più
prendere.

```
PROMPT
------
Lavori su livedub. Leggi CLAUDE.md e PROSSIMA_SESSIONE.md.

Si pubblica. Ma **prima di qualunque comando git**, una decisione che dopo la
pubblicazione non si può più prendere in modo pulito:

I commit **fino al 17 agosto 2026** portano il trailer `Co-Authored-By: Claude`.
Dal 18 in poi non ce n'è più nessuno. La regola del progetto è che **l'autore è
sempre e solo l'utente** e che Claude non compare in nessuna forma. Toglierli dai
vecchi significa **riscrivere la storia** — cosa che si può fare adesso senza
conseguenze, e che dopo la pubblicazione riscriverebbe una storia **già clonata**
da altri.

Portami: quanti commit hanno quel trailer, il comando esatto che li ripulirebbe,
e cosa cambia per me se lo faccio (le date, gli hash, il fatto che il repo locale
va riallineato). **Poi aspetta il mio ok.** Non riscrivere niente di tua
iniziativa.

Fatta quella, il resto: creare il repo, spingere, e il **sito ospitato su
GitHub** (Pages). Il sito usa le immagini rigenerate nella sessione F, non quelle
vecchie.

Controlla prima di spingere che non finisca nel repo materiale della macchina:
`models/`, `runs/`, le registrazioni. Sono gitignorati, ma «gitignorato» va
verificato, non creduto — `git status --ignored` e un'occhiata a cosa entrerebbe.
```

---

## Cosa **non** è in questa lista, e perché

- **L'HUD pronunciata** (`Sali sul <spazzatura>` letto come battute nuove) è
  stata **chiusa senza intervento** il 18 agosto, per decisione dell'utente:
  abbassare `vision.continue_similarity` toccava una soglia che vale per tutti i
  sottotitoli, e la regola sul prefisso comune costava più del difetto.
- **`line_pad` a 0,2 come default** resta una decisione d'orecchio, non una
  sessione: è misurato meglio su tutti e due i giochi ma cambia il gioco
  principale (130 → 123 battute aperte), e quello lo giudica l'ascolto.
