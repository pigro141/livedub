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
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.audio import Loopback, Player, find_loopback, list_devices  # noqa: E402
from capture.screen import make_screen  # noqa: E402
from core.clock import RealClock, set_clock  # noqa: E402
from core.config import Config, load_profile  # noqa: E402
from core.pipeline import DubPipeline  # noqa: E402
from tools.live import costruisci_tts  # noqa: E402
from tools.session import Session  # noqa: E402
from ui.overlay import inchiostro, inchiostro_da_box, ritaglia  # noqa: E402


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
        self.stop = threading.Event()
        self.threads: list[threading.Thread] = []
        self.pipeline: DubPipeline | None = None
        # La finestra scelta. `None` = tutto lo schermo, che e' il vecchio modo
        # e resta possibile: su un gioco in fullscreen esclusivo e' l'unico.
        self.finestra = None
        self.sessione: Session | None = None

        self.root = tk.Tk()
        self.root.title("livedub")
        self.root.geometry("880x560")

        # La sostituzione grafica dal vivo: una finestra sopra il gioco, sulla
        # ROI. Solo se si traduce **e** l'overlay e' acceso — coprire il
        # sottotitolo originale con la sua stessa traduzione mancante non
        # servirebbe a niente.
        self.overlay = None
        self._overlay_fino_a = 0.0
        if self.cfg.translate.enabled and self.cfg.translate.overlay:
            from ui.overlay import Overlay

            self.overlay = Overlay(
                self.root, self.cfg.vision.roi,
                colore=self.cfg.translate.color,
                fondo=self.cfg.translate.background,
                font=self.cfg.translate.font,
                font_frac=self.cfg.translate.font_frac,
                opacita=self.cfg.translate.background_opacity,
                contorno=self.cfg.translate.outline,
                # **Due campi che nessuno leggeva.** `background_mode` e
                # `blur_strength` valevano solo per l'MP4: dal vivo l'overlay
                # sfocava sempre, qualunque cosa dicesse la config. E' lo stesso
                # difetto di `max_ocr_hz` e di `tts.device`, un campo dichiarato
                # e mai letto — che qui vuol dire una prova fatta con una
                # configurazione diversa da quella che si crede.
                modo=self.cfg.translate.background_mode,
                blur=self.cfg.translate.blur_strength,
                trasparente=self.cfg.translate.transparent,
                escludi_cattura=not getattr(args, "overlay_catturabile", False),
            )

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
        # Quanto vecchio e' il ritaglio quando finisce a schermo. Senza questo
        # numero il ritardo del blur si poteva solo guardare, e guardandolo si
        # discute; misurandolo si corregge.
        from core.metrics import MetricsRegistry

        self._metriche = MetricsRegistry()
        self._t_ritardo = self._metriche.timer("overlay.ritardo")

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
            sessione_accesa=lambda: self.pipeline is not None,
            solo=self.TECNOLOGIE, cerca=False,
        )
        self.p_tecnologie.pack(fill="both", expand=True)

        self._scheda_aree()

        avanzate = ttk.Frame(self.schede)
        self.schede.add(avanzate, text="Impostazioni avanzate")
        self.p_avanzate = Pannello(
            avanzate, self.cfg, al_cambio=self._campo_cambiato,
            sessione_accesa=lambda: self.pipeline is not None,
        )
        self.p_avanzate.pack(fill="both", expand=True)

    def stato(self, testo: str, colore: str | None = None) -> None:
        """Lo stato in testata: una parola e un pallino.

        Il colore lo si vede senza leggere, ed e' cio' che serve quando la
        finestra si guarda di sfuggita con il gioco davanti.
        """
        t = self.tema
        if colore is None:
            basso = testo.lower()
            if "!" in testo or "error" in basso or "guast" in basso:
                colore = t.ROSSO
            elif "ferm" in basso or "pront" in basso:
                colore = t.TESTO_FIOCO
            else:
                colore = t.VERDE
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
        if not self._in_attesa or self.pipeline is None:
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
        if self.pipeline is None:
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

    def _scheda_aree(self) -> None:
        """Piu' aree di lettura, con il loro modo.

        **Il modo non e' un dettaglio**: `testo+audio` legge e fa parlare,
        `solo testo` legge, traduce e disegna ma non pronuncia. Pronunciare un
        cartello di missione e' esattamente il difetto che l'11% delle battute
        di GTA V aveva.
        """
        import tkinter as tk
        from tkinter import ttk

        pagina = ttk.Frame(self.schede)
        self.schede.add(pagina, text="Aree")
        ttk.Label(
            pagina,
            text="Piu' zone da leggere sullo stesso schermo. Se due si accavallano, la parte "
                 "in comune viene letta una volta sola e resta a quella piu' in alto "
                 "nell'elenco: leggerla due volte vorrebbe dire due voci sovrapposte. "
                 "Le aree si applicano al prossimo Avvia.",
            style="Tenue.TLabel", wraplength=980, justify="left",
        ).pack(fill="x", padx=12, pady=12)

        corpo = ttk.Frame(pagina)
        corpo.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.elenco_aree = tk.Listbox(
            corpo, font=self.tema.MONO, height=12, bg=self.tema.PANNELLO,
            fg=self.tema.TESTO, selectbackground=self.tema.ACCENTO,
            selectforeground="#0d1117", relief="flat", borderwidth=0,
            highlightthickness=0, activestyle="none",
        )
        self.elenco_aree.pack(side="left", fill="both", expand=True)
        bottoni = ttk.Frame(corpo)
        bottoni.pack(side="left", fill="y", padx=8)
        ttk.Button(bottoni, text="Aggiungi (testo + audio)", width=24,
                   command=lambda: self._aggiungi_area("testo_audio")).pack(pady=2)
        ttk.Button(bottoni, text="Aggiungi (solo testo)", width=24,
                   command=lambda: self._aggiungi_area("testo")).pack(pady=2)
        ttk.Button(bottoni, text="Togli la selezionata", width=24,
                   command=self._togli_area).pack(pady=2)
        ttk.Button(bottoni, text="Svuota (torna alla ROI)", width=24,
                   command=lambda: self._scrivi_aree([])).pack(pady=(12, 2))
        self._mostra_aree()

    def _mostra_aree(self) -> None:
        from vision.aree import dividi, leggi

        self.elenco_aree.delete(0, "end")
        aree = leggi(self.cfg.vision.aree)
        if not aree:
            self.elenco_aree.insert(
                "end", "(nessuna: si legge la ROI qui sopra, com'e' sempre stato)"
            )
            return
        pezzi = dividi(aree)
        for i, a in enumerate(aree):
            suoi = [p for p in pezzi if p.area == i]
            intera = len(suoi) == 1 and suoi[0].roi == a.roi
            nota = "" if intera else f"   -> {len(suoi)} pezzi, tolte le sovrapposizioni"
            x, y, w, h = a.roi
            modo = "testo + audio" if a.parla else "solo testo"
            self.elenco_aree.insert(
                "end", f"{i + 1}.  x{x:.3f} y{y:.3f} w{w:.3f} h{h:.3f}   {modo}{nota}"
            )

    def _aggiungi_area(self, modo: str) -> None:
        self._modo_nuova_area = modo
        SelettoreArea(self.root, self._area_tirata)

    def _area_tirata(self, roi) -> None:
        from vision.aree import Area, leggi, scrivi

        aree = leggi(self.cfg.vision.aree)
        aree.append(Area(roi=tuple(roi), modo=getattr(self, "_modo_nuova_area", "testo_audio")))
        self._scrivi_aree(aree)

    def _togli_area(self) -> None:
        from vision.aree import leggi

        scelte = self.elenco_aree.curselection()
        aree = leggi(self.cfg.vision.aree)
        if not scelte or not aree:
            return
        del aree[scelte[0]]
        self._scrivi_aree(aree)

    def _scrivi_aree(self, aree) -> None:
        from vision.aree import scrivi

        self.cfg.vision.aree = scrivi(aree)
        self._mostra_aree()
        self._riallinea_pannelli()
        quante = len(aree)
        self.scrivi(
            f"aree: {quante} dichiarate — si applicano al prossimo Avvia"
            if quante else "aree: nessuna, si torna a leggere la ROI"
        )

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
        elif campo.percorso == "vision.aree":
            self._mostra_aree()
        if campo.caldo:
            self.scrivi(f"{campo.percorso} = {valore}")
        else:
            self.scrivi(f"{campo.percorso} = {valore}   (si legge solo all'avvio)")
            if self.pipeline is not None:
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

        self.finestra = finestra
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
        if self.pipeline is not None:
            self.scrivi("(vale dalla prossima partenza)", tag="nota")

    def _segui_finestra(self) -> None:
        """Il gioco si sposta, e il sottotitolo deve seguirlo.

        Una finestra spostata senza che l'overlay la segua e' un sottotitolo
        tradotto in mezzo al desktop. Costa una chiamata a Windows, e si fa
        insieme allo svuotamento della coda invece che a ogni fotogramma.
        """
        if self.finestra is None or self.overlay is None:
            return
        from capture.finestre import rettangolo_client, viva

        if not viva(self.finestra.hwnd):
            return
        r = rettangolo_client(self.finestra.hwnd)
        if r and r != self.overlay.ancora:
            self.overlay.aggancia(r)

    def scegli_area(self) -> None:
        SelettoreArea(self.root, self._applica_roi)

    def _applica_roi(self, roi) -> None:
        # **Il rettangolo si tira sullo schermo, ma la ROI e' della finestra.**
        # Il selettore normalizza su quello che vede — lo schermo — mentre il
        # fotogramma che arriva all'OCR e' la finestra del gioco. Senza questa
        # conversione l'area finirebbe sulla stessa frazione di *schermo* invece
        # che sulla stessa frazione di *finestra*: cioe' quasi sempre altrove, e
        # sarebbe la prima cosa che si rompe usando il programma come si deve.
        if self.finestra is not None:
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
        if self.pipeline is not None:
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
                            if not (self.pipeline is None
                                    or self.pipeline.a_schermo(t_on)):
                                fine = max(fine, time.perf_counter()
                                           + self.cfg.translate.overlay_min_s)
                            self._overlay_fino_a = fine
                        # **La riga che divide in due il problema.** Se qui c'e'
                        # scritto un riquadro e a schermo non si vede niente, il
                        # difetto e' di Windows (finestra) e non nostro
                        # (traduzione, OCR, geometria). Senza, le due ipotesi si
                        # confondono e si cerca per ore dalla parte sbagliata.
                        self.scrivi(
                            f"overlay  {self.overlay.top.geometry()}  "
                            f"{'visibile' if self.overlay._visibile else 'NASCOSTO'}",
                            tag="nota",
                        )
                elif tipo == "spegni":
                    if self.overlay is not None:
                        self.overlay.nascondi()

                elif tipo == "stato":
                    self.stato(dato)
                elif tipo == "nota":
                    self.scrivi(dato, tag="nota")
        except queue.Empty:
            pass
        if ultimo_ritaglio is not None and self.overlay is not None:
            pezzo, quando = ultimo_ritaglio
            self.overlay.aggiorna(pezzo)
            self._t_ritardo.add((time.perf_counter() - quando) * 1000.0)
        # **Il sottotitolo tradotto sparisce da solo.** Una banda perenne in
        # mezzo allo schermo e' peggio dell'originale che copriva.
        self._segui_finestra()
        # **Anche qui si aspetta il conto dei giri vuoti.** Questa riga spegneva
        # sul solo orologio, quindi scavalcava l'isteresi del ciclo video e la
        # rendeva inutile: il tradotto spariva lo stesso al primo buco di
        # letture. Il ritardo di due secondi e' la rete per il caso in cui il
        # ciclo video si sia fermato — li' i giri vuoti non arrivano piu', e una
        # finestra che non si spegne resta in mezzo allo schermo.
        if self.overlay is not None and self.overlay._visibile:
            scaduto = time.perf_counter() >= self._overlay_fino_a
            fermo = time.perf_counter() >= self._overlay_fino_a + 2.0
            if fermo or (scaduto and self.overlay._vuoti
                         >= self.cfg.translate.overlay_hold_frames):
                self.overlay.nascondi()
        self.root.after(self.PASSO_UI, self._svuota_coda)

    # -- avvio e arresto ---------------------------------------------------

    def avvia(self) -> None:
        if self.threads:
            return
        self.stop.clear()
        self.b_start.config(state="disabled")
        self.b_stop.config(state="normal")
        self.b_area.config(state="disabled")
        self.b_finestra.config(state="disabled")
        threading.Thread(target=self._prepara, daemon=True).start()

    def _prepara(self) -> None:
        try:
            set_clock(RealClock())
            loops, default = list_devices()
            entrata = find_loopback(self.args.loopback)
            uscita = default
            if self.args.output:
                trovati = [d for d in loops if self.args.output.lower() in d.name.lower()]
                uscita = trovati[0] if trovati else default
            if entrata.index == uscita.index:
                self.coda.put(("nota", "! cattura e uscita sono lo stesso device: rientrerebbe"))
                self._fine_thread()
                return
            sr = 48000
            self.coda.put(("nota", f"carico {self.cfg.tts.backend}..."))
            tts = costruisci_tts(self.cfg.tts.backend, self.cfg)
            self.pipeline = DubPipeline(self.cfg, tts, samplerate=sr)
            # **Dal vivo si tengono le ultime, non tutte.** Una sessione di tre
            # ore lascia vive 3600 battute per +10,4 MB (misurato con
            # `tools/bench_memoria.py`), e cresce senza limite. Chi le rilegge e'
            # il cancello anti-doppioni, che guarda indietro di secondi: 400 sono
            # venti minuti di conversazione, cioe' cento volte quello che serve.
            self.pipeline.max_spoken = 400
            # **`ui.save_mix` era dichiarato e non lo leggeva nessuno**: il
            # quinto campo di questa forma, dopo `max_ocr_hz`, `tts.device`,
            # `background_mode` e `overlay.ritardo`. Chi lo metteva a `false` si
            # ritrovava lo stesso 660 MB di RAM e 340 MB di WAV per mezz'ora.
            self.sessione = None if self.args.no_save else Session(
                samplerate=sr, salva_mix=bool(self.cfg.ui.save_mix)
            )
            if self.sessione is not None and self.cfg.ui.save_mix:
                self.coda.put(("nota", "registro l'audio: ~11 MB al minuto su disco, "
                                       "fino a 660 MB di RAM (ui.save_mix=false lo spegne)"))
            # **Il registro delle impronte anche dal vivo.** Senza, di una
            # sessione dal vivo si sa cosa e' stato detto ma non cosa il
            # riconoscitore ha visto — e quando dal vivo va peggio che sul banco
            # non c'e' modo di sapere se cambia il segnale, il ritaglio o il
            # modello. Costa due decimi di megabyte e si rigioca con
            # `tools.recluster`.
            if self.sessione is not None:
                self._registro = (self.sessione.dir / "speaker.jsonl").open(
                    "w", encoding="utf-8"
                )
                self.pipeline.speaker_log = self._registro
            self.coda.put(("nota", f"catturo: {entrata}"))
            self.coda.put(("nota", f"suono su: {uscita}"))
            self.coda.put(("nota", f"{self._testo_roi()}   attesa voce "
                                   f"{self.cfg.speaker.decide_after_ms} ms"))
            pronto = threading.Event()
            t_avvio = time.perf_counter()

            def ciclo_audio() -> None:
                # **Il guasto piu' probabile di tutti: le cuffie staccate a meta'
                # partita.** WASAPI non aspetta: il device sparisce e la lettura
                # solleva. Senza questo, il thread moriva **in silenzio** — il
                # doppiaggio ammutoliva, la finestra continuava a dire «in
                # corso», e non c'era niente da leggere. E' esattamente la forma
                # dei difetti che questo progetto ha imparato a temere: non un
                # errore, un silenzio.
                #
                # Non si prova a riaprire il device da soli: il flusso audio ha
                # una linea temporale (`_marche`) che riparte da zero, e riprendere
                # a meta' vorrebbe dire programmare battute su un orologio che non
                # esiste piu'. Si ferma tutto e **si dice cosa e' successo**, che
                # per l'utente vuol dire «rimetti le cuffie e ripremi Avvia».
                try:
                    with Loopback(entrata, block=self.args.block, samplerate=sr) as ing, Player(
                        uscita, block=self.args.block, samplerate=sr
                    ) as alt:
                        self.pipeline.start_live()
                        pronto.set()
                        while not self.stop.is_set():
                            gioco = ing.read()
                            quando = self.pipeline.mixer.now
                            fuori = self.pipeline.on_audio(gioco, n=len(gioco))
                            alt.write(fuori)
                            if self.sessione is not None:
                                self.sessione.audio(fuori, quando)
                except Exception as guasto:
                    pronto.set()  # se no il ciclo video aspetta dieci secondi per niente
                    self.coda.put(("nota", f"! l'audio si e' fermato: {type(guasto).__name__}: "
                                           f"{guasto}"))
                    self.coda.put(("nota", "! probabile: cuffie o altoparlanti staccati, "
                                           "oppure il device e' cambiato. Ricollega e premi Avvia."))
                    self.coda.put(("stato", "audio interrotto"))
                    self.stop.set()  # il video senza audio non serve a niente

            def ciclo_video() -> None:
                # La sorgente si apre **nel thread che la usa**: dxcam sta su COM,
                # e creata altrove non solleva — restituisce `None` a ogni grab.
                hwnd = self.finestra.hwnd if self.finestra is not None else None
                schermo = make_screen(
                    self.args.backend, monitor=self.args.monitor, hwnd=hwnd
                )
                self.coda.put(("nota", f"cattura: {schermo.name}"))
                pronto.wait(timeout=10.0)
                periodo = 1.0 / max(1e-6, self.cfg.capture.fps)
                prossimo = time.perf_counter()
                n = vuoti = 0
                while not self.stop.is_set():
                    ora = time.perf_counter()
                    if ora < prossimo:
                        time.sleep(min(0.002, prossimo - ora))
                        continue
                    prossimo += periodo
                    # **Se si e' rimasti indietro, si riparte da adesso.**
                    # Sommando il periodo e basta, un giro lento lascia
                    # `prossimo` nel passato: il ciclo smette di dormire e gira a
                    # tutta velocita' per rimettersi in pari, prendendosi la CPU
                    # che serve al thread audio. Misurato nella sessione
                    # dell'utente: `speaker.ring_lag` a 4674 ms, cioe' quasi
                    # cinque secondi di campioni mai arrivati, e il riconoscimento
                    # di chi parla che lavorava su audio vecchio di secondi.
                    # Saltare i giri arretrati costa qualche fotogramma; non
                    # saltarli costa l'audio.
                    if prossimo < ora:
                        prossimo = ora + periodo
                    g = schermo.grab()
                    if not g.ok:
                        # **`None` vuol dire due cose diverse, e si distinguono
                        # solo dal tempo.** Desktop Duplication risponde `None`
                        # quando lo schermo non e' cambiato — normale — e
                        # risponde `None` anche quando non funziona affatto, che
                        # su questa macchina e' il caso: 1071 grab, zero
                        # fotogrammi, con un video a tutto schermo. La seconda
                        # non finisce mai, e senza questo ripiego la finestra
                        # resta li' a non fare niente **senza dire perche'**.
                        vuoti += 1
                        if (n == 0 and vuoti > 2 * self.cfg.capture.fps
                                and schermo.name == "dxcam"):
                            schermo.close()
                            schermo = make_screen("mss", monitor=self.args.monitor)
                            self.coda.put((
                                "nota",
                                "! la cattura veloce non restituisce fotogrammi: passo a mss",
                            ))
                            vuoti = 0
                        continue
                    n += 1
                    # **Il ritaglio per la sfocatura parte subito, prima
                    # dell'OCR.** Stava in fondo al giro, dopo `on_frame`, e
                    # quindi pagava tutto il costo del riconoscimento prima di
                    # essere spedito: misurato nella sessione dell'utente,
                    # `vision.ocr` sta a **84 ms al p50 e 137 al massimo** — cioe'
                    # la macchia arrivava a schermo con quattro fotogrammi di
                    # ritardo sulla scena, e in panoramica si vede eccome.
                    #
                    # Quei millisecondi non sono suoi: per sfocare non serve
                    # sapere cosa c'e' scritto. I pixel sono gia' in mano appena
                    # il fotogramma e' stato preso, e da li' devono partire.
                    # Ridisegnare costa 10 ms, quindi il costo non e' mai stato
                    # nel disegno: era nell'attesa.
                    if self.overlay is not None and self.overlay._visibile:
                        pezzo = ritaglia(g.frame, self.overlay.rett)
                        if pezzo is not None:
                            self.coda.put(("aggiorna", (pezzo, time.perf_counter())))
                    for riga in self.pipeline.on_frame(g.frame):
                        if self.sessione is not None:
                            self.sessione.line(riga)
                        self.coda.put((
                            "riga",
                            (riga.speaker_id, riga.voice_id, riga.text,
                             riga.live_latency_ms, time.perf_counter() - t_avvio),
                        ))
                        # **La sostituzione grafica dal vivo.** Si passa dalla
                        # coda come tutto il resto: disegnare da qui vorrebbe
                        # dire toccare Tkinter dal thread video, che e' il modo
                        # piu' rapido di far cadere l'interfaccia. Si manda solo
                        # se c'e' stata una traduzione — se no si coprirebbe il
                        # sottotitolo originale con sé stesso.
                        if self.overlay is not None and riga.text_original:
                            # **Quanto resta a schermo il tradotto: quanto il
                            # sottotitolo del gioco, non quanto la nostra voce.**
                            # La durata dell'audio doppiato e' quasi sempre piu'
                            # corta della permanenza del sottotitolo: usando
                            # quella, la finestra spariva mentre l'originale era
                            # ancora li', e per l'ultimo pezzo di battuta si
                            # tornava a vedere l'italiano. La permanenza prevista
                            # e' `D = a + b*n`, che la catena stima gia' e corregge
                            # mentre gira.
                            resta = self.pipeline.timing.predict(riga.text)
                            fine = time.perf_counter() + max(riga.duration, resta)
                            # **Il fotogramma ce l'abbiamo gia' in mano.** Serviva
                            # all'OCR; per sfocare il sottotitolo vecchio basta
                            # ritagliarlo, e non c'e' nessuna seconda cattura da
                            # pagare — cosa che avevo scritto e che era falsa.
                            # **La geometria viene dal fotogramma in cui il
                            # sottotitolo c'era, non da questo.** Fra la lettura
                            # e adesso sono passati piu' di due secondi: qui
                            # `inchiostro()` cercava l'inchiostro su una scena
                            # gia' cambiata, e cio' che trovava era scenario.
                            # `riga.boxes` sono le bande che il riconoscitore ha
                            # accettato allora. `inchiostro()` resta come
                            # ripiego, per i profili senza box.
                            trovato = inchiostro_da_box(
                                g.frame, self.cfg, riga.boxes, riga.ink
                            )
                            if trovato[0] is None:
                                trovato = inchiostro(g.frame, self.cfg)
                            self.coda.put(
                                ("overlay",
                                 (riga.text, riga.text_original, fine,
                                  riga.t_subtitle, *trovato))
                            )
                    # **Il blur e' un filtro dal vivo, a ogni fotogramma.**
                    # A 10 Hz si vedeva: la scena scorre e la macchia sfocata
                    # resta indietro di un decimo, che su una panoramica sono
                    # decine di pixel. Costa poco perche' non si manda tutto lo
                    # schermo — 11 MB a giro — ma **solo il ritaglio** attorno al
                    # sottotitolo, che e' mezzo megabyte.
                    #
                    # E chi decide se il tradotto resta a schermo e' il lettore,
                    # non un orologio e nemmeno i pixel: prima si prolungava il
                    # timer finche' la finestra era visibile — un anello chiuso
                    # su se' stesso — e la finestra non spariva piu'.
                    if self.overlay is not None and self.overlay._visibile:
                        # I pixel li ha gia' spediti il ritaglio di sopra, che
                        # gira **prima** dell'OCR: qui resta solo decidere se la
                        # finestra deve restare accesa. Il rinfresco non sta piu'
                        # dentro il ramo `a_schermo` perche' durante un buco di
                        # letture la toppa si congelava — un rettangolo di
                        # immagine vecchia proprio nei fotogrammi in cui si stava
                        # decidendo se spegnerla.
                        #
                        # **Si contano i giri vuoti, non si guarda l'orologio.**
                        # L'OCR perde una riga per qualche fotogramma e la
                        # ritrova subito: spegnere al primo giro vuoto fa
                        # lampeggiare il tradotto. Si spegne quando il buco e'
                        # abbastanza lungo da essere una sparizione vera.
                        if self.pipeline.a_schermo(self.overlay.t_on):
                            self.overlay._vuoti = 0
                            self._overlay_fino_a = time.perf_counter() + 0.4
                        else:
                            self.overlay._vuoti += 1
                            if (self.overlay._vuoti
                                    >= self.cfg.translate.overlay_hold_frames
                                    and time.perf_counter() >= self._overlay_fino_a):
                                self.coda.put(("spegni", None))
                    if n % 30 == 0:
                        p = len(self.pipeline.tracker) if self.pipeline.tracker else 0
                        self.coda.put(("stato",
                                       f"in corso  |  {n} frame  |  {self.pipeline.dette} battute"
                                       f"  |  {p} personaggi  |  {len(self.pipeline.pool)} voci"))

            for f in (ciclo_audio, ciclo_video):
                t = threading.Thread(target=f, daemon=True)
                t.start()
                self.threads.append(t)
            self.coda.put(("stato", "in corso"))
        except Exception as exc:  # un errore di device non deve chiudere la finestra
            self.coda.put(("nota", f"! avvio fallito: {type(exc).__name__}: {exc}"))
            self._fine_thread()

    def _fine_thread(self) -> None:
        self.b_start.config(state="normal")
        self.b_stop.config(state="disabled")
        self.b_area.config(state="normal")
        self.b_finestra.config(state="normal")
        self.threads.clear()

    def ferma(self) -> None:
        self.stop.set()
        for t in self.threads:
            t.join(timeout=2.0)
        self.threads.clear()
        if self.pipeline is not None:
            self.pipeline.finish()
            self.coda.put(("nota", "--- personaggi ---"))
            if self.pipeline.tracker is not None:
                for r in self.pipeline.tracker.report().splitlines():
                    self.coda.put(("nota", r))
            self.coda.put(("nota", self.pipeline.pool.report()))
        if self.sessione is not None:
            try:
                if getattr(self, "_registro", None) is not None:
                    self._registro.close()
                    self._registro = None
                # **Il riepilogo va nella cartella, non solo sul terminale.**
                # Senza, `mix.underrun` e `speak.first_sample` restano nella
                # finestra e muoiono con lei — e sono esattamente i due numeri che
                # dicono se lo streaming ha retto. Dopo la prima prova dal vivo di
                # Qwen la diagnosi si e' dovuta **dedurre**, perche' i contatori
                # non erano stati scritti da nessuna parte.
                # **Le metriche della finestra vanno nel report, e non ci
                # andavano.** `overlay.ritardo` — quanto vecchio e' il ritaglio
                # quando arriva a schermo — veniva misurato a ogni giro e poi
                # buttato, perche' qui si scriveva solo il rapporto della
                # catena. E' esattamente la domanda «il blur va in differita?»,
                # con la risposta gia' raccolta e mai letta da nessuno.
                rapporto = self.pipeline.report() if self.pipeline is not None else ""
                rapporto = f"{rapporto}\n\n-- finestra --\n{self._metriche.report()}"
                self.coda.put(
                    ("nota", f"sessione salvata in {self.sessione.close(self.cfg, rapporto)}")
                )
            except Exception as exc:
                self.coda.put(("nota", f"! salvataggio fallito: {exc}"))
        self.pipeline = None
        self.sessione = None
        self._registro = None
        self.coda.put(("stato", "fermo"))
        self._fine_thread()

    def chiudi(self) -> None:
        if self.threads:
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
