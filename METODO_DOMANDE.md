# Il metodo per risolvere le domande di produzione

Come si lavora `DOMANDE_PRODUZIONE.md`. Non è una procedura burocratica: ognuno
dei sei passi esiste perché **saltandolo si è già sbagliato**, in questa sessione
o in una archiviata.

---

## I sei passi, per **una** domanda alla volta

### 1. Una sola domanda, e per intero

Si prende una domanda e si finisce. Farne cinque a metà produce cinque ❓ che
sembrano ✅, ed è precisamente lo stato da cui questo documento cerca di uscire.

### 2. Cinque sotto-domande, scritte prima di guardare il codice

Sempre le stesse cinque, che sono le facce di ogni difetto di produzione:

1. **Cosa dovrebbe succedere, se il difetto c'è?** — l'elenco dei candidati.
2. **Si può misurare senza la condizione vera?** — cioè senza tre ore, senza il
   gioco acceso, senza staccare le cuffie. È la domanda che decide se la
   risposta arriva stasera o mai.
3. **Qual è la soglia?** — dichiarata **adesso**, prima di vedere il numero.
4. **Chi, nel codice, potrebbe causarlo?** — un nome di file, non un'intuizione.
5. **Come se ne accorgerebbe l'utente?** — se la risposta è «in nessun modo», è
   già un secondo difetto da segnare.

> **La 2 è quella che sblocca quasi tutto.** La memoria su tre ore sembrava
> impossibile da provare: la catena non sa che ora è, quindi tre ore sono 3600
> battute e si fanno in cinque minuti. Prima di dire «serve una sessione vera»,
> chiedersi cosa dipenda davvero dal tempo.

### 3. Misurare, non dedurre

Un banco nuovo se serve (`tools/bench_memoria.py` è nato così). Costa mezz'ora e
resta per sempre.

### 4. Controllare che la misura possa esprimere la risposta

**Prima di leggere il risultato.** Il banco della memoria ha stampato `0.0 MB`
per un processo Python — che ne usa 28 prima di importare qualcosa. Un numero
impossibile è più utile di uno sbagliato: quello sbagliato si archivia.

E guardare anche i numeri di contorno: mentre la memoria diceva zero, il
conteggio degli oggetti aveva **già** dato la risposta vera.

### 5. Decidere, e scrivere il perché

Tre esiti leciti, e il terzo è un esito:

- **si corregge** — e si aggiunge la verifica che quel difetto non superi;
- **si dichiara** — è un limite, va nel README, non è un bug;
- **si lascia aperto** — ma con scritto *con quale misura* si chiude.

### 6. Verificare le due metà, non una

La regola che ha salvato il tetto sulle battute: la cura accorcia la lista
**e** il conteggio deve restare vero **e** il cancello anti-doppioni deve ancora
scattare. Un tetto che zittisse il cancello avrebbe curato dieci megabyte creando
il difetto peggiore del prodotto.

---

## Le tre trappole viste in questa sessione

**Un ❓ non è un ✅ in attesa.** Sembra «probabilmente va bene»; è «nessuno lo
sa». Sono la stessa cosa dei campi dichiarati e mai letti, visti dall'altra
parte.

**Il difetto vero spesso sta *fra* due domande.** La 50 (quanto pesa il WAV) e la
91 (quanta RAM) da sole erano innocue; incrociate hanno dato i **660 MB tenuti in
RAM** da `Session`, che è la voce di memoria più grossa del programma.

**Il banco può spegnere qualcosa che non si spegne.** `bench_memoria` metteva
`cfg.ui.save_mix = False` e misurava senza registrazione — ma quel campo **non lo
leggeva nessuno**. La prova stava misurando una configurazione che non esiste.
Prima di fidarsi di un `= False` in un banco, verificare che qualcuno lo legga.

---

## Da dove riprendere

`DOMANDE_PRODUZIONE.md` ha lo stato aggiornato di tutte e cento. Le rimanenti si
dividono in tre gruppi:

| gruppo | quante | cosa serve |
|---|---|---|
| **si chiudono da soli** | ~20 | intervalli dei valori (27, 28), ricerca nel log (25), annulla (31), `runs/` che cresce (85), indicatore di latenza (44, 70, 86), avviso su Google nella finestra (74) |
| **servono l'utente e il gioco** | ~8 | cuffie staccate (39), fps rubati (93), schermo a 150% (12), due monitor (55), VRAM con GTA V acceso (94) |
| **sono lavoro vero** | ~6 | scrivere il WAV a blocchi invece che in RAM (84, 91), selettore d'area nella Qt (37), portare Avvia nella Qt |

**L'ordine consigliato**: prima il primo gruppo (ognuna mezz'ora, e la finestra
migliora a vista), poi il terzo, e il secondo si accorpa alla prossima prova
d'ascolto dell'utente — che è l'unico momento in cui il gioco è acceso comunque.
