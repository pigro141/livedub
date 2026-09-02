<!--
  Le note che accompagnano ogni release, **fuori dal workflow**.

  Stanno in un file loro e non dentro `eseguibile.yml` per due ragioni. La prima
  e' meccanica: una here-string di PowerShell vuole il suo `"@` alla colonna
  zero, e dentro un blocco `run: |` di YAML la colonna zero non esiste — il file
  non si analizzava nemmeno. La seconda conta di piu': queste sono **parole per
  chi scarica**, e le parole non si scrivono dentro un file di configurazione,
  dove nessuno le rilegge e dove correggerle vuol dire toccare la costruzione.

  I quattro segnaposto li riempie il workflow. Sono numerati come quelli di
  `ui/lingua.py`? No: qui sono a nome, perche' questo file non passa da nessun
  traduttore automatico — e' il posto in cui un nome si puo' ancora permettere.
-->
Windows 10/11, 64 bit. Si scompatta e si apre `livedub.exe`: non c'e' niente da installare.

| | |
|---|---|
| pacchetto | **{{MB}} MB** |
| SHA256 | `{{SHA}}` |
| provato | {{PROVE}} prove dentro l'eseguibile, tutte fatte e tutte passate ([l'esecuzione]({{RUN}})) |

**I modelli non sono qui dentro, ed e' voluto.** I pesi delle voci, del
riconoscimento di chi parla e del lettore di testo hanno ognuno la propria
licenza, e quello di Windows **non e' ridistribuibile**: il programma se li
prende al primo avvio, con la barra, dichiarando **prima** quanti megabyte sono.
Si veda `LICENZE.md`.

**Cosa e' stato provato, e cosa no — che e' la meta' che conta.** Il pacchetto
non e' solo costruito: e' **aperto**, su un runner `windows-latest`, e da dentro
se stesso legge una riga disegnata, sintetizza una battuta, costruisce la
finestra e ritrova i propri modelli anche lanciato da un'altra cartella.

Un runner pero' non ha scheda audio, non ha scheda video e non ha un gioco
aperto: la cattura, il loopback, il mixaggio e la voce su GPU restano **senza
prova automatica**. E su quei runner **Smart App Control e' spento** — quindi
«parte qui» non vuol dire «parte su una Windows 11 appena installata». Se la tua
lo ha acceso, puo' rifiutarsi di aprire un eseguibile che non ha ancora
reputazione: in quel caso la strada che funziona e' `installa.ps1` dal sorgente,
ed e' spiegata nel README.
