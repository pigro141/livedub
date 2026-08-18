"""Il doppiaggio dal vivo, con una finestra invece di un terminale.

    python -m tools.ui --profile live --loopback voicemeeter

Tre cose sole, che sono quelle che servono per provare:

- **il selettore d'area.** Si trascina un rettangolo sullo schermo e quella
  diventa la ROI. Era la cosa piu' scomoda del progetto: la ROI si ricavava con
  `tools/calibrate.py` su una registrazione, e non e' del gioco ma **del setup di
  cattura** — stesso gioco e stessa risoluzione, i sottotitoli stanno a 0,965
  dell'altezza in una registrazione e a 0,914 in un'altra. Cambiare il modo di
  catturare voleva dire rifare la calibrazione; adesso vuol dire tirare un
  rettangolo col mouse;
- **avvia e ferma**, perche' una prova d'ascolto si interrompe quando si e'
  sentito abbastanza, non dopo `--seconds`;
- **il log di chi parla**, che e' la ragione vera di questa finestra. Il
  riconoscimento del personaggio si giudica solo vedendo *insieme* la battuta e
  la voce che le e' toccata: da un terminale che scorre dietro il gioco a schermo
  intero non si vede niente, e senza questa finestra l'unico modo di giudicare
  era riascoltare la registrazione dopo.

**La finestra non fa niente di lento.** I due cicli — audio ogni 10 ms, video a
30 Hz — restano nei loro thread, come in `tools/live.py`; qui arriva solo il
testo gia' pronto, attraverso una coda, e Tkinter lo pesca con `after`. Mettere
l'interfaccia dentro il ciclo video sarebbe il modo piu' rapido di far perdere
battute a una catena che finora non ne perde.
"""

from __future__ import annotations

import argparse
import queue
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, load_profile  # noqa: E402
from core.motore import (  # noqa: E402  (`colore_stato` si rilegge da qui: la regola sta col motore)
    STATO_GUASTO,
    Motore,
    Opzioni,
    colore_stato,
    in_coda,
    righe_guasto_audio,
)


class SelettoreArea:
    """Una finestra semitrasparente a tutto schermo su cui si tira il rettangolo.

    Semitrasparente e non opaca perche' l'area va scelta **guardando i
    sottotitoli**: su un pannello nero si tirerebbe un rettangolo a memoria, che
    e' esattamente il modo in cui la ROI di default ha finito per inquadrare il
    tappeto.
    """

    def __init__(self, root, al_termine) -> None:
        import tkinter as tk

        self.al_termine = al_termine
        self.top = tk.Toplevel(root)
        self.top.attributes("-fullscreen", True)
        self.top.attributes("-alpha", 0.28)
        self.top.configure(bg="black")
        self.top.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.top, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.x0 = self.y0 = 0
        self.rect = None
        self.canvas.bind("<ButtonPress-1>", self._giu)
        self.canvas.bind("<B1-Motion>", self._muovi)
        self.canvas.bind("<ButtonRelease-1>", self._su)
        self.top.bind("<Escape>", lambda e: self.top.destroy())
        self.w = self.top.winfo_screenwidth()
        self.h = self.top.winfo_screenheight()

    def _giu(self, e) -> None:
        self.x0, self.y0 = e.x, e.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#39d353", width=2)

    def _muovi(self, e) -> None:
        if self.rect:
            self.canvas.coords(self.rect, self.x0, self.y0, e.x, e.y)

    def _su(self, e) -> None:
        x0, x1 = sorted((self.x0, e.x))
        y0, y1 = sorted((self.y0, e.y))
        self.top.destroy()
        if x1 - x0 < 20 or y1 - y0 < 8:
            return  # un clic per sbaglio non deve azzerare la ROI
        # Normalizzata sullo schermo: cosi' non dipende dalla risoluzione, ed e'
        # la stessa forma che il profilo salva su disco.
        self.al_termine((x0 / self.w, y0 / self.h, (x1 - x0) / self.w, (y1 - y0) / self.h))


class SelettoreFinestra:
    """L'elenco delle finestre aperte, per scegliere **cosa** catturare.

    E' la scelta che viene prima di tutte le altre. Catturando lo schermo
    intero, nel fotogramma che va all'OCR finisce anche cio' che sta davanti al
    gioco — comprese le nostre finestre — e il programma finisce per leggere se
    stesso. Scegliendo la finestra, la cattura contiene quella e basta:
    verificato mettendo sopra alla finestra catturata una finestra rossa che la
    copriva a meta', nel fotogramma ne e' arrivato lo **0,000**.

    L'elenco e' ordinato per area perche' il gioco e' quasi sempre la finestra
    piu' grande: la risposta giusta e' in cima nove volte su dieci.
    """

    def __init__(self, root, al_termine) -> None:
        import tkinter as tk

        from capture.finestre import elenco

        self.al_termine = al_termine
        self.top = tk.Toplevel(root)
        self.top.title("Scegli la finestra da tradurre")
        self.top.geometry("760x380")
        self.top.attributes("-topmost", True)
        self.finestre = elenco()

        tk.Label(
            self.top, anchor="w", fg="#666",
            text="Il gioco e' quasi sempre il primo della lista. "
                 "Deve stare in finestra o senza bordi, non a schermo intero esclusivo.",
        ).pack(fill="x", padx=10, pady=(8, 4))
        cornice = tk.Frame(self.top)
        cornice.pack(fill="both", expand=True, padx=10)
        barra = tk.Scrollbar(cornice)
        barra.pack(side="right", fill="y")
        self.lista = tk.Listbox(
            cornice, font=("Consolas", 10), yscrollcommand=barra.set, activestyle="none"
        )
        self.lista.pack(fill="both", expand=True)
        barra.config(command=self.lista.yview)
        for f in self.finestre:
            self.lista.insert("end", f"  {f.larghezza:>5}x{f.altezza:<5} {f.processo:<22} {f.titolo}")
        if self.finestre:
            self.lista.selection_set(0)
        self.lista.bind("<Double-Button-1>", lambda e: self.scegli())

        piede = tk.Frame(self.top)
        piede.pack(fill="x", padx=10, pady=8)
        tk.Button(piede, text="Aggiorna", command=self.aggiorna).pack(side="left")
        tk.Button(piede, text="Usa questa", command=self.scegli, width=14).pack(side="right")
        tk.Button(piede, text="Tutto lo schermo", command=self.schermo).pack(side="right", padx=6)

    def aggiorna(self) -> None:
        from capture.finestre import elenco

        self.finestre = elenco()
        self.lista.delete(0, "end")
        for f in self.finestre:
            self.lista.insert("end", f"  {f.larghezza:>5}x{f.altezza:<5} {f.processo:<22} {f.titolo}")

    def schermo(self) -> None:
        self.top.destroy()
        self.al_termine(None)

    def scegli(self) -> None:
        sel = self.lista.curselection()
        if not sel:
            return
        f = self.finestre[sel[0]]
        self.top.destroy()
        self.al_termine(f)


class App:
    # **Ogni quanto la finestra guarda la coda, in millisecondi.** Erano 100, poi
    # 33 per allinearsi alla cattura. Ma questo passo e' un **ritardo aggiunto**:
    # un ritaglio che arriva subito dopo il giro aspetta un giro intero prima di
    # essere disegnato.
    #
    # Misurato il costo del ridisegno sul percorso vero (disegna + colore-chiave
    # + PhotoImage, sulla fascia della sessione dell'utente): **10,5 ms** nel
    # caso peggiore. A 16 ms ci sta con un terzo di margine, e il ritardo che
    # questo passo aggiunge si dimezza.
    PASSO_UI = 16

    def __init__(self, args) -> None:
        import tkinter as tk
        from tkinter import scrolledtext

        self.args = args
        self.cfg = (
            load_profile(args.profile, args.overrides)
            if args.profile
            else Config().apply(args.overrides)
        )
        if args.tts:
            self.cfg.tts.backend = args.tts
        self.coda: queue.Queue = queue.Queue()
        # **I due cicli non stanno piu' qui.** Vivono in `core/motore.py`, che
        # non sa cosa sia una finestra: da quando i front-end sono due, tenerli
        # dentro Tkinter voleva dire copiarli — e una strada parallela che non
        # eredita le cure dell'altra e' un difetto gia' pagato due volte in
        # questo progetto.
        self.motore = Motore(self.cfg, Opzioni.da_args(args), in_coda(self.coda))

        self.root = tk.Tk()
        self.root.title("livedub")
        self.root.geometry("880x560")

        # La sostituzione grafica dal vivo: una finestra sopra il gioco, sulla
        # ROI. Solo se si traduce **e** l'overlay e' acceso — coprire il
        # sottotitolo originale con la sua stessa traduzione mancante non
        # servirebbe a niente.
        # **Non si costruisce qui.** Si costruisce quando parte la catena, con
        # la configurazione di allora: accendendo la traduzione dalle
        # impostazioni — cioe' il modo dichiarato di accenderla — questo blocco
        # aveva gia' deciso di no, e la catena traduceva senza che nessuno
        # disegnasse. Si veda `Motore.prepara_overlay`.

        # **La testata.** Nome, stato e cosa si sta guardando, sempre visibili.
        # Il pallino colorato dice se sta girando prima di qualunque parola: la
        # finestra si guarda di sfuggita mentre si gioca, ed e' esattamente la
        # condizione in cui una parola non si legge.
        from tkinter import ttk

        from ui import tema

        self.tema = tema
        tema.applica(self.root)

        testata = ttk.Frame(self.root, style="Testata.TFrame")
        testata.pack(fill="x")
        dentro = ttk.Frame(testata, style="Testata.TFrame")
        dentro.pack(fill="x", padx=14, pady=10)
        ttk.Label(dentro, text="livedub", style="Testata.TLabel").pack(side="left")
        self.spia = tk.Canvas(dentro, width=16, height=16, bg=tema.PANNELLO,
                              highlightthickness=0)
        self.spia.pack(side="left", padx=(14, 5))
        tema.pallino(self.spia, tema.TESTO_FIOCO)
        self.l_stato = ttk.Label(dentro, text="fermo", style="TenueP.TLabel")
        self.l_stato.pack(side="left")
        self.l_bersaglio = ttk.Label(dentro, text="nessuna finestra scelta",
                                     style="TenueP.TLabel")
        self.l_bersaglio.pack(side="right")

        barra = ttk.Frame(self.root)
        barra.pack(fill="x", padx=12, pady=(10, 6))
        self.b_finestra = ttk.Button(barra, text="Scegli finestra", command=self.scegli_finestra)
        self.b_finestra.pack(side="left")
        self.b_area = ttk.Button(barra, text="Seleziona area", command=self.scegli_area)
        self.b_area.pack(side="left", padx=6)
        # Un solo bottone e' quello che si preme, e si vede: se sono tutti uguali
        # l'occhio deve leggerli tutti per trovarlo.
        self.b_start = ttk.Button(barra, text="Avvia", command=self.avvia, style="Primario.TButton")
        self.b_start.pack(side="left", padx=(14, 6))
        self.b_stop = ttk.Button(barra, text="Ferma", command=self.ferma, state="disabled")
        self.b_stop.pack(side="left")

        # **L'unico parametro che due giochi vogliono al contrario.** Il colore
        # e' l'HUD in GTA V (obiettivi di missione, nomi di app) e il nome di
        # chi parla in Mafia: The Old Country (`ENZO:`, `ALFIO:` in giallo).
        # Nessuna soglia li concilia, quindi la sceglie chi il gioco lo sta
        # guardando. Si veda `VisionConfig.exclude_colored`.
        #
        # Si cambia **a caldo**: la casella scrive nello stesso oggetto config
        # che il lettore rilegge a ogni fotogramma, quindi non c'e' niente da
        # ricostruire e non c'e' da riavviare.
        self.v_colorati = tk.BooleanVar(value=bool(self.cfg.vision.exclude_colored))
        self.c_colorati = ttk.Checkbutton(
            barra, text="Ignora i sottotitoli colorati",
            variable=self.v_colorati, command=self._cambia_colorati,
        )
        self.c_colorati.pack(side="left", padx=(18, 0))

        # **Quanto acceso dev'essere un colore per contare come colore.**
        # Il criterio non guarda *quale* tinta sia — giallo, rosso, ciano si
        # comportano identici, misurato — ma quanto stacca dal bianco. Sotto
        # questa soglia una riga non e' colorata affatto: misurato su sette
        # colori, un azzurro pallido a saturazione 50 viene letto anche a difesa
        # accesa. Si spegne con la casella: a difesa spenta il numero non lo
        # guarda nessuno, e un comando attivo che non fa niente e' peggio di uno
        # assente.
        self.v_sat = tk.IntVar(value=int(self.cfg.vision.sat_max))
        ttk.Label(barra, text="soglia", style="Tenue.TLabel").pack(side="left", padx=(10, 4))
        self.s_sat = ttk.Spinbox(
            barra, from_=0, to=255, width=4, textvariable=self.v_sat,
            command=self._cambia_sat, justify="right",
        )
        self.s_sat.pack(side="left")
        self.s_sat.bind("<KeyRelease>", lambda _e: self._cambia_sat())
        # Uscendo dal campo, quel che si vede torna a essere quel che si usa.
        self.s_sat.bind("<FocusOut>", lambda _e: self.v_sat.set(int(self.cfg.vision.sat_max)))
        self._aggiorna_sat()

        self.l_roi = ttk.Label(barra, text=self._testo_roi(), style="Mono.TLabel")
        self.l_roi.pack(side="right")

        # **La striscia delle modifiche in attesa.** Alcuni parametri si leggono
        # una volta sola alla costruzione: cambiati a sessione accesa non fanno
        # niente. Prima lo dicevo e basta, ed e' meta' del lavoro — «lo sapevi»
        # non e' «si applica». Qui compare una striscia che li conta e un bottone
        # che li applica davvero, rifacendo la catena.
        self._in_attesa: list[str] = []
        self.striscia = ttk.Frame(self.root, style="Pannello.TFrame")
        self.l_attesa = ttk.Label(self.striscia, text="", style="TenueP.TLabel")
        self.l_attesa.pack(side="left", padx=12, pady=7)
        ttk.Button(self.striscia, text="Applica ora", style="Accento.TButton",
                   command=self.applica_in_attesa).pack(side="right", padx=10, pady=5)
        ttk.Button(self.striscia, text="Lascia stare",
                   command=self.scarta_in_attesa).pack(side="right", pady=5)

        # **Le schede.** La barra sopra resta sempre visibile perche' e' quello
        # che si tocca durante una prova; sotto ci sono le cose che si guardano
        # una volta e poi si lasciano stare.
        from tkinter import ttk

        self.schede = ttk.Notebook(self.root)
        self.schede.pack(fill="both", expand=True, padx=8, pady=8)

        sessione = ttk.Frame(self.schede)
        self.schede.add(sessione, text="Sessione")
        self.log = scrolledtext.ScrolledText(
            sessione, font=tema.MONO, bg=tema.PANNELLO, fg=tema.TESTO,
            insertbackground=tema.TESTO, relief="flat", borderwidth=0,
            padx=12, pady=10, spacing1=1, spacing3=2, wrap="word",
        )
        self.log.pack(fill="both", expand=True)
        # `ScrolledText` si porta dietro una `Scrollbar` classica di Tk, che non
        # passa da ttk e quindi resterebbe chiara in mezzo a una finestra scura.
        self.log.vbar.configure(
            bg=tema.CAMPO, troughcolor=tema.PANNELLO, activebackground=tema.BORDO,
            borderwidth=0, highlightthickness=0, width=12, relief="flat",
            elementborderwidth=0,
        )

        self._schede_config()
        # Un colore per personaggio: la domanda che si fa guardando questo log
        # non e' "cosa ha detto" ma "e' sempre lo stesso a parlare?", e a quella
        # l'occhio risponde da un colore molto prima che da una sigla.
        self.colori = list(tema.VOCI)
        for i, c in enumerate(self.colori):
            self.log.tag_config(f"s{i}", foreground=c)
        self.log.tag_config("nota", foreground=tema.TESTO_TENUE)
        self.noti: dict[str, int] = {}

        self.root.protocol("WM_DELETE_WINDOW", self.chiudi)
        self.root.after(self.PASSO_UI, self._svuota_coda)

    # -- schede ------------------------------------------------------------

    # **I quattro motori che si scelgono, piu' cio' che ognuno si porta
    # dietro.** L'elenco e' di percorsi e non di valori: le *scelte* vengono
    # dallo schema, cioe' dai commenti di `core/config.py`, quindi aggiungere un
    # backend non richiede di toccare questo file.
    TECNOLOGIE: tuple[str, ...] = (
        "vision.ocr_backend", "vision.ocr_device",
        "tts.backend", "tts.device", "tts.kokoro_weights", "tts.pool_size",
        "speaker.backend", "vad.backend", "emotion.backend",
        "translate.enabled", "translate.backend", "translate.source", "translate.target",
        "correct.backend",
    )

    def _schede_config(self) -> None:
        """Tecnologie e impostazioni, **disegnate dallo stesso pannello**.

        Sono due viste dello stesso elenco e non due griglie diverse: la scheda
        delle tecnologie e' il pannello filtrato ai quattordici percorsi che
        scelgono un motore. Un secondo disegnatore mostrerebbe una cosa mentre
        l'altro ne fa un'altra, che e' come sono nati i difetti dell'overlay.
        """
        from tkinter import ttk

        from ui.pannello import Pannello

        tecnologie = ttk.Frame(self.schede)
        self.schede.add(tecnologie, text="Tecnologie")
        ttk.Label(
            tecnologie,
            text="Quale motore usare per ogni stadio. Quasi tutti si leggono una volta "
                 "sola: dopo averli cambiati serve ripremere Avvia.",
            style="Tenue.TLabel", wraplength=900, justify="left",
        ).pack(fill="x", padx=12, pady=(12, 0))
        self.p_tecnologie = Pannello(
            tecnologie, self.cfg, al_cambio=self._campo_cambiato,
            sessione_accesa=lambda: self.motore.pipeline is not None,
            solo=self.TECNOLOGIE, cerca=False,
        )
        self.p_tecnologie.pack(fill="both", expand=True)


        avanzate = ttk.Frame(self.schede)
        self.schede.add(avanzate, text="Impostazioni avanzate")
        self.p_avanzate = Pannello(
            avanzate, self.cfg, al_cambio=self._campo_cambiato,
            sessione_accesa=lambda: self.motore.pipeline is not None,
        )
        self.p_avanzate.pack(fill="both", expand=True)

    def stato(self, testo: str, colore: str | None = None) -> None:
        """Lo stato in testata: una parola e un pallino.

        Il colore lo si vede senza leggere, ed e' cio' che serve quando la
        finestra si guarda di sfuggita con il gioco davanti.
        """
        t = self.tema
        if colore is None:
            colore = colore_stato(testo, t)
        self.l_stato.config(text=testo)
        t.pallino(self.spia, colore)

    # -- le modifiche che aspettano un riavvio ------------------------------

    def _segna_in_attesa(self, percorso: str) -> None:
        """Un parametro freddo cambiato a sessione accesa: si accoda e si mostra.

        **«Lo sapevi» non e' «si applica».** Dire che serve un riavvio e poi
        lasciare all'utente il compito di ricordarselo, fermare e riavviare a
        mano e' meta' del lavoro: in pratica quella modifica resta non applicata
        per tutta la sessione, ed e' esattamente la situazione che questa UI deve
        impedire — una sessione che gira con una configurazione diversa da quella
        che la finestra mostra.
        """
        if percorso not in self._in_attesa:
            self._in_attesa.append(percorso)
        self._mostra_attesa()

    def _mostra_attesa(self) -> None:
        if not self._in_attesa or self.motore.pipeline is None:
            self.striscia.pack_forget()
            return
        quante = len(self._in_attesa)
        cosa = ", ".join(self._in_attesa[:3]) + ("..." if quante > 3 else "")
        self.l_attesa.config(
            text=f"{quante} modific{'a' if quante == 1 else 'he'} in attesa ({cosa}): "
                 f"si applic{'a' if quante == 1 else 'ano'} rifacendo la catena, un paio di secondi"
        )
        self.striscia.pack(fill="x", before=self.schede, padx=12, pady=(0, 6))

    def scarta_in_attesa(self) -> None:
        """Le modifiche restano scritte in config, ma non si riavvia adesso."""
        self._in_attesa.clear()
        self._mostra_attesa()
        self.scrivi("le modifiche restano scritte: avranno effetto al prossimo Avvia")

    def applica_in_attesa(self) -> None:
        """Ferma e riavvia la catena perche' i parametri freddi facciano effetto.

        **Il prezzo e' dichiarato e non nascosto**: la sessione si chiude e se ne
        apre un'altra, quindi il rapporto viene scritto e i personaggi imparati
        fin qui ripartono da quello che il file `cast.json` ha salvato. Non e' un
        cambio a caldo travestito: e' un riavvio, fatto per te, in un clic.
        """
        if self.motore.pipeline is None:
            self._in_attesa.clear()
            self._mostra_attesa()
            return
        cosa = ", ".join(self._in_attesa)
        self._in_attesa.clear()
        self._mostra_attesa()
        self.scrivi(f"--- rifaccio la catena per applicare: {cosa}")
        self.stato("riavvio in corso", self.tema.AMBRA)
        self.ferma()
        # Si riparte al giro dopo di Tk, cosi' `ferma()` ha finito di svuotare la
        # coda e il log dice le cose nell'ordine in cui sono successe.
        self.root.after(400, self.avvia)

    def _riallinea_pannelli(self) -> None:
        """La barra e i pannelli mostrano la stessa config: vanno tenuti insieme.

        La barra in alto e le schede sono **tre griglie di caselle sopra un solo
        oggetto**. Toccando la barra, i pannelli devono rileggere; se no la
        scheda avanzata continuerebbe a mostrare il valore di prima, cioe' una
        configurazione che non e' in uso.
        """
        for nome in ("p_tecnologie", "p_avanzate"):
            pannello = getattr(self, nome, None)
            if pannello is not None:
                pannello.aggiorna()

    def _campo_cambiato(self, campo, valore) -> None:
        """Un parametro toccato dal pannello: si scrive a log e si riallinea.

        **Le due viste sono lo stesso oggetto config ma due griglie di caselle**:
        cambiando `tts.backend` dalla scheda delle tecnologie, la stessa riga
        nelle avanzate deve aggiornarsi da sola. Se no una delle due mostrerebbe
        un valore che non e' piu' quello in uso — lo stesso difetto della soglia
        del colore digitata `9999`, spostato di una finestra.
        """
        for pannello in (getattr(self, "p_tecnologie", None), getattr(self, "p_avanzate", None)):
            if pannello is not None:
                pannello.aggiorna()
        if campo.percorso == "vision.exclude_colored":
            self.v_colorati.set(bool(valore))
            self._aggiorna_sat()
        elif campo.percorso == "vision.sat_max":
            self.v_sat.set(int(valore))
        elif campo.percorso == "vision.roi":
            self.l_roi.configure(text=self._testo_roi())
        if campo.caldo:
            self.scrivi(f"{campo.percorso} = {valore}")
        else:
            self.scrivi(f"{campo.percorso} = {valore}   (si legge solo all'avvio)")
            if self.motore.pipeline is not None:
                self._segna_in_attesa(campo.percorso)

    # -- ROI ---------------------------------------------------------------

    def _cambia_colorati(self) -> None:
        """La casella dei sottotitoli colorati, applicata subito.

        Si scrive nella config **viva**, quella che il lettore rilegge a ogni
        fotogramma, e si dichiara a log: un interruttore che cambia cosa si
        legge senza dirlo darebbe una sessione diversa da quella che si crede di
        stare guardando.
        """
        acceso = bool(self.v_colorati.get())
        self.cfg.vision.exclude_colored = acceso
        self._aggiorna_sat()
        self._riallinea_pannelli()
        self.scrivi(
            "sottotitoli colorati: " + ("ignorati (difesa dall'HUD accesa)" if acceso
                                        else "letti (per i giochi che colorano il nome di chi parla)")
        )

    def _aggiorna_sat(self) -> None:
        """La soglia si tocca solo quando serve, cioe' a difesa accesa."""
        self.s_sat.configure(state="normal" if self.v_colorati.get() else "disabled")

    def _cambia_sat(self) -> None:
        """La soglia del colore, applicata subito.

        **Il campo si puo' anche digitare, quindi puo' contenere qualunque
        cosa.** Una casella vuota o `'12a'` non deve spegnere la catena a meta'
        sessione: un valore che non e' un numero si ignora e basta, e quello
        buono resta quello di prima. Fuori da 0-255 non ha senso — la
        saturazione e' `max - min` su tre canali a 8 bit — quindi si taglia
        invece di accettare un numero che non puo' succedere.
        """
        try:
            scritto = int(self.s_sat.get())
        except (ValueError, TypeError):
            return  # sta ancora scrivendo: si aspetta
        valore = max(0, min(255, scritto))
        # **Se il numero e' stato tagliato, la casella deve dirlo.** Digitando
        # 9999 la catena usava 255 mentre a schermo restava 9999: e' il difetto
        # peggiore possibile qui — una sessione che gira con una configurazione
        # diversa da quella che la UI mostra. Trovato guidando la finestra vera,
        # non leggendo il codice.
        if valore != scritto:
            self.v_sat.set(valore)
        if valore == int(self.cfg.vision.sat_max):
            return
        self.cfg.vision.sat_max = valore
        self._riallinea_pannelli()
        self.scrivi(f"soglia del colore: {valore} (sotto, una riga non e' colorata)")

    def _testo_roi(self) -> str:
        x, y, w, h = self.cfg.vision.roi
        return f"ROI  x{x:.3f}  y{y:.3f}  w{w:.3f}  h{h:.3f}"

    def scegli_finestra(self) -> None:
        SelettoreFinestra(self.root, self._applica_finestra)

    def _applica_finestra(self, finestra) -> None:
        from capture.finestre import rettangolo_client

        self.motore.finestra = finestra
        if finestra is None:
            self.scrivi("cattura: tutto lo schermo", tag="nota")
            if self.overlay is not None:
                self.overlay.aggancia(None)
                # Catturando lo schermo l'overlay ci rientra: va nascosto alla
                # cattura, e il prezzo e' che non lo vede nemmeno chi registra.
                self.overlay.esclusione(True)
                self.scrivi("  (l'overlay resta fuori dagli screenshot e da OBS)", tag="nota")
        else:
            self.scrivi(f"cattura: {finestra}", tag="nota")
            if self.overlay is not None:
                self.overlay.aggancia(rettangolo_client(finestra.hwnd))
                # Catturando la sola finestra del gioco l'overlay **non** ci
                # rientra: misurato, zero righe lette che fossero nostre. Quindi
                # torna una finestra normale, e chi registra lo vede.
                self.overlay.esclusione(False)
        self.l_roi.config(text=self._testo_roi())
        self._riallinea_pannelli()
        if self.motore.pipeline is not None:
            self.scrivi("(vale dalla prossima partenza)", tag="nota")

    def scegli_area(self) -> None:
        SelettoreArea(self.root, self._applica_roi)

    def _applica_roi(self, roi) -> None:
        # **Il rettangolo si tira sullo schermo, ma la ROI e' della finestra.**
        # Il selettore normalizza su quello che vede — lo schermo — mentre il
        # fotogramma che arriva all'OCR e' la finestra del gioco. Senza questa
        # conversione l'area finirebbe sulla stessa frazione di *schermo* invece
        # che sulla stessa frazione di *finestra*: cioe' quasi sempre altrove, e
        # sarebbe la prima cosa che si rompe usando il programma come si deve.
        if self.motore.finestra is not None:
            from capture.finestre import rettangolo_client

            r = rettangolo_client(self.finestra.hwnd)
            if r:
                ax, ay, aw, ah = r
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                x = (roi[0] * sw - ax) / max(1, aw)
                y = (roi[1] * sh - ay) / max(1, ah)
                w = roi[2] * sw / max(1, aw)
                h = roi[3] * sh / max(1, ah)
                fuori = x < -0.02 or y < -0.02 or x + w > 1.02 or y + h > 1.02
                roi = (min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0),
                       min(w, 1.0), min(h, 1.0))
                if fuori:
                    self.scrivi("! l'area che hai tirato esce dalla finestra scelta: "
                                "l'ho tagliata al suo bordo", tag="nota")
        self.cfg.vision.roi = roi
        # **Un'area alta e' il difetto che si vede di piu', e non sembra suo.**
        # La fascia d'analisi e' l'area piu' un respiro proporzionale a lei:
        # tirandola alta un sesto dello schermo diventa 391 px per una riga da
        # 45, e in quello spazio ci finisce la scena. Su un fondo chiaro la riga
        # di testo si **salda** a cio' che ha attorno — misurato, una banda alta
        # 186 px che conteneva un sottotitolo da 45 — e il riquadro sfocato
        # cresce con lei. Nessun filtro puo' disfare una saldatura; stringere
        # l'area si'.
        if roi[3] > 0.12:
            self.scrivi(
                f"! l'area e' alta {roi[3]:.3f} dello schermo: tirala stretta "
                f"attorno alla riga dei sottotitoli (0,06-0,10), se no il blur "
                f"si allarga su quello che le sta intorno", tag="nota")
        self.l_roi.config(text=self._testo_roi())
        # **L'overlay deve seguire l'area, e non la seguiva.** Il selettore e' il
        # modo dichiarato di usare questo programma; senza questa riga la
        # finestra del tradotto restava dove stava la ROI di partenza, cioe' il
        # difetto che si sarebbe attribuito al calcolo del riquadro.
        if self.overlay is not None:
            self.overlay.riposiziona(roi)
        self.scrivi(f"area impostata: {self._testo_roi()}", tag="nota")
        if self.motore.pipeline is not None:
            self.scrivi("(vale dalla prossima partenza)", tag="nota")

    # -- log ---------------------------------------------------------------

    def scrivi(self, testo: str, tag: str = "nota") -> None:
        self.log.insert("end", testo + "\n", tag)
        self.log.see("end")

    def _svuota_coda(self) -> None:
        # **Dei ritagli si disegna solo l'ultimo.** Ne arrivano trenta al
        # secondo e questo giro ne fa dieci: disegnarli tutti vorrebbe dire fare
        # tre volte il lavoro per mostrare solo l'ultimo, e — peggio — se
        # disegnare costa piu' di quanto arriva la coda si allunga e la macchia
        # sfocata resta indietro **sempre di piu'**. E' il ritardo che si vede a
        # schermo quando la telecamera si muove.
        ultimo_ritaglio = None
        try:
            while True:
                tipo, dato = self.coda.get_nowait()
                if tipo == "aggiorna":
                    ultimo_ritaglio = dato
                    continue
                if tipo == "riga":
                    sid, voce, testo, lat, t = dato
                    if sid not in self.noti:
                        self.noti[sid] = len(self.noti) % len(self.colori)
                    self.scrivi(
                        f"{t:7.1f}s  {sid:>4}  {voce:<14} {lat:4.0f} ms  {testo}",
                        tag=f"s{self.noti[sid]}",
                    )
                elif tipo == "overlay":
                    testo, originale, fine, t_on, pezzo, bande, rett, tinta = dato
                    if self.overlay is not None:
                        # **Una battuta arrivata tardi si mostra lo stesso, per
                        # un minimo.** Prima si mostrava solo se il sottotitolo
                        # originale era ancora a schermo, e se no la traduzione
                        # veniva buttata senza dirlo: nel log dell'utente sta
                        # scritto `NASCOSTO` accanto a una battuta tradotta mai
                        # comparsa. Il giocatore quella riga l'ha letta un
                        # secondo fa e sta ascoltando la voce che la dice: un
                        # buco e' peggio di un ritardo.
                        #
                        # L'unica cosa che non si fa mai e' **tornare
                        # indietro**: una battuta piu' vecchia di quella gia' a
                        # schermo si accavallerebbe alla nuova, che e' il
                        # difetto peggiore — due sottotitoli insieme.
                        if t_on >= self.overlay.t_on:
                            self.overlay.mostra(testo, pezzo, bande, rett, tinta,
                                                originale)
                            self.overlay.t_on = t_on
                            if not (self.motore.pipeline is None
                                    or self.motore.pipeline.a_schermo(t_on)):
                                fine = max(fine, time.perf_counter()
                                           + self.cfg.translate.overlay_min_s)
                            self.motore.overlay_fino_a = fine
                        # **La riga che divide in due il problema.** Se qui c'e'
                        # scritto un riquadro e a schermo non si vede niente, il
                        # difetto e' di Windows (finestra) e non nostro
                        # (traduzione, OCR, geometria). Senza, le due ipotesi si
                        # confondono e si cerca per ore dalla parte sbagliata.
                        self.scrivi(
                            f"overlay  {self.overlay.geometria()}  "
                            f"{'visibile' if self.overlay._visibile else 'NASCOSTO'}",
                            tag="nota",
                        )
                elif tipo == "spegni":
                    if self.overlay is not None:
                        self.overlay.nascondi()

                elif tipo == "stato":
                    self.stato(dato)
                elif tipo == "guasto":
                    self._audio_guasto(dato)
                elif tipo == "finito":
                    # I bottoni li rimette a posto **il thread della finestra**:
                    # il motore si spegne anche da solo (avvio fallito, device
                    # sparito) e da li' non si tocca Tk.
                    self._fine_thread()
                elif tipo == "nota":
                    self.scrivi(dato, tag="nota")
        except queue.Empty:
            pass
        if ultimo_ritaglio is not None and self.overlay is not None:
            pezzo, quando = ultimo_ritaglio
            self.overlay.aggiorna(pezzo)
            self.motore.ritardo((time.perf_counter() - quando) * 1000.0)
        # **Il sottotitolo tradotto sparisce da solo.** Una banda perenne in
        # mezzo allo schermo e' peggio dell'originale che copriva.
        self.motore.segui_finestra()
        # **Anche qui si aspetta il conto dei giri vuoti.** Questa riga spegneva
        # sul solo orologio, quindi scavalcava l'isteresi del ciclo video e la
        # rendeva inutile: il tradotto spariva lo stesso al primo buco di
        # letture. Il ritardo di due secondi e' la rete per il caso in cui il
        # ciclo video si sia fermato — li' i giri vuoti non arrivano piu', e una
        # finestra che non si spegne resta in mezzo allo schermo.
        if self.overlay is not None and self.overlay._visibile:
            scaduto = time.perf_counter() >= self.motore.overlay_fino_a
            fermo = time.perf_counter() >= self.motore.overlay_fino_a + 2.0
            if fermo or (scaduto and self.overlay._vuoti
                         >= self.cfg.translate.overlay_hold_frames):
                self.overlay.nascondi()
        self.root.after(self.PASSO_UI, self._svuota_coda)

    # -- avvio e arresto ---------------------------------------------------

    @property
    def overlay(self):
        """**Uno solo, e ce l'ha il motore.** Tenerne una copia qui vorrebbe dire
        che a un certo punto le due divergono, ed e' gia' successo.
        """
        return self.motore.overlay

    def _nuovo_overlay(self):
        """Una finestra senza bordi sopra il gioco, con la config di **adesso**.

        `background_mode` e `blur_strength` si leggono qui e non altrove: erano
        due campi che valevano solo per l'MP4 — dal vivo l'overlay sfocava
        sempre, qualunque cosa dicesse la config.
        """
        from ui.overlay import Overlay

        return Overlay(
            self.root, self.cfg.vision.roi,
            colore=self.cfg.translate.color,
            fondo=self.cfg.translate.background,
            font=self.cfg.translate.font,
            font_frac=self.cfg.translate.font_frac,
            opacita=self.cfg.translate.background_opacity,
            contorno=self.cfg.translate.outline,
            modo=self.cfg.translate.background_mode,
            blur=self.cfg.translate.blur_strength,
            trasparente=self.cfg.translate.transparent,
            escludi_cattura=not getattr(self.args, "overlay_catturabile", False),
        )

    def avvia(self) -> None:
        if self.motore.acceso:
            return
        # **L'overlay si costruisce adesso, con la configurazione di adesso**, e
        # si dice a chiare lettere se c'e' o no: una traduzione che esce e non si
        # vede e' un difetto che non lascia tracce da nessuna parte.
        self.motore.prepara_overlay(self._nuovo_overlay)
        if self.cfg.translate.enabled:
            self.scrivi(
                f"traduzione {self.cfg.translate.source}→{self.cfg.translate.target} "
                f"con {self.cfg.translate.backend}: "
                + ("il tradotto si disegna sopra il gioco" if self.overlay is not None
                   else "! solo voce, niente a schermo (translate.overlay e' spento)"),
                tag="nota",
            )
        self.b_start.config(state="disabled")
        self.b_stop.config(state="normal")
        self.b_area.config(state="disabled")
        self.b_finestra.config(state="disabled")
        self.motore.avvia()

    def _audio_guasto(self, dettaglio: str) -> None:
        """Il ciclo audio e' morto: si chiude la sessione come se fosse un Ferma.

        **Il guasto piu' probabile e' anche quello da cui si deve poter
        tornare**: cuffie staccate, il device cambiato sotto i piedi. Dirlo e
        basta lasciava la finestra in uno stato che non esiste — nessun thread
        vivo, Avvia spento, la sessione aperta e il WAV mai scritto — e l'unica
        via d'uscita era premere Ferma, che nessuno pensa di premere quando ha
        appena letto «premi Avvia».
        """
        for riga in righe_guasto_audio(dettaglio):
            self.scrivi(riga, tag="nota")
        if self.motore.acceso or self.motore.pipeline is not None:
            self.ferma()  # chiude la sessione, salva il WAV, riaccende Avvia
        else:
            # **E se la catena era gia' morta, i bottoni li rimette comunque
            # qualcuno.** Senza questo ramo il messaggio dice «premi Avvia»
            # indicando un bottone spento: e' lo stesso difetto di prima, che
            # sopravvive dentro la sua stessa cura.
            self._fine_thread()
        # Dopo `ferma`, se no lo stato «fermo» che manda lei arriverebbe dopo
        # questo e cancellerebbe il rosso. Il colore e' dichiarato: «audio
        # interrotto» senza il punto esclamativo verrebbe **verde**, cioe' il
        # colore di «va tutto bene» sopra una catena morta.
        self.coda.put(("stato", STATO_GUASTO))

    def _fine_thread(self) -> None:
        self.b_start.config(state="normal")
        self.b_stop.config(state="disabled")
        self.b_area.config(state="normal")
        self.b_finestra.config(state="normal")

    def ferma(self) -> None:
        self.motore.ferma()

    def chiudi(self) -> None:
        if self.motore.acceso:
            self.ferma()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.ui", description="Doppiaggio dal vivo, con finestra.")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--loopback", default="voicemeeter")
    ap.add_argument("--output", default=None)
    ap.add_argument("--block", type=int, default=480)
    ap.add_argument("--backend", default="auto")
    ap.add_argument("--monitor", type=int, default=1)
    ap.add_argument("--tts", default=None)
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument(
        "--avvia",
        action="store_true",
        help="parte subito, senza aspettare il tasto (l'area e' quella del profilo)",
    )
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    args = ap.parse_args(argv)
    app = App(args)
    if args.avvia:
        # Comodo per riprovare la stessa cosa dieci volte di fila: l'area e'
        # quella del profilo, che se non e' quella giusta si ridisegna dopo.
        app.root.after(300, app.avvia)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
