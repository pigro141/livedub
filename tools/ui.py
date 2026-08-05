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
from ui.overlay import inchiostro  # noqa: E402


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


class App:
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
        if getattr(args, "recording", False):
            self.cfg.record.enabled = True
        self.coda: queue.Queue = queue.Queue()
        self.stop = threading.Event()
        self.threads: list[threading.Thread] = []
        self.pipeline: DubPipeline | None = None
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
            )
            self.overlay.vision = self.cfg.vision

        barra = tk.Frame(self.root)
        barra.pack(fill="x", padx=8, pady=6)
        self.b_area = tk.Button(barra, text="Seleziona area", command=self.scegli_area)
        self.b_area.pack(side="left")
        self.b_start = tk.Button(barra, text="Avvia", command=self.avvia, width=10)
        self.b_start.pack(side="left", padx=6)
        self.b_stop = tk.Button(barra, text="Ferma", command=self.ferma, width=10, state="disabled")
        self.b_stop.pack(side="left")
        self.l_roi = tk.Label(barra, text=self._testo_roi(), anchor="w")
        self.l_roi.pack(side="left", padx=12)

        self.l_stato = tk.Label(self.root, text="fermo", anchor="w", fg="#666")
        self.l_stato.pack(fill="x", padx=10)

        self.log = scrolledtext.ScrolledText(
            self.root, font=("Consolas", 10), bg="#12131a", fg="#d8d8e0", insertbackground="#fff"
        )
        self.log.pack(fill="both", expand=True, padx=8, pady=8)
        # Un colore per personaggio: la domanda che si fa guardando questo log
        # non e' "cosa ha detto" ma "e' sempre lo stesso a parlare?", e a quella
        # l'occhio risponde da un colore molto prima che da una sigla.
        self.colori = ["#7ee787", "#79c0ff", "#ffa657", "#d2a8ff", "#ff7b72", "#f2cc60"]
        for i, c in enumerate(self.colori):
            self.log.tag_config(f"s{i}", foreground=c)
        self.log.tag_config("nota", foreground="#8b949e")
        self.noti: dict[str, int] = {}

        self.root.protocol("WM_DELETE_WINDOW", self.chiudi)
        self.root.after(100, self._svuota_coda)

    # -- ROI ---------------------------------------------------------------

    def _testo_roi(self) -> str:
        x, y, w, h = self.cfg.vision.roi
        return f"ROI  x{x:.3f}  y{y:.3f}  w{w:.3f}  h{h:.3f}"

    def scegli_area(self) -> None:
        SelettoreArea(self.root, self._applica_roi)

    def _applica_roi(self, roi) -> None:
        self.cfg.vision.roi = roi
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
        try:
            while True:
                tipo, dato = self.coda.get_nowait()
                if tipo == "riga":
                    sid, voce, testo, lat, t = dato
                    if sid not in self.noti:
                        self.noti[sid] = len(self.noti) % len(self.colori)
                    self.scrivi(
                        f"{t:7.1f}s  {sid:>4}  {voce:<14} {lat:4.0f} ms  {testo}",
                        tag=f"s{self.noti[sid]}",
                    )
                elif tipo == "overlay":
                    testo, originale, fine, pezzo, bande, rett, tinta = dato
                    if self.overlay is not None:
                        self.overlay.mostra(testo, pezzo, bande, rett, tinta, originale)
                        self._overlay_fino_a = fine
                elif tipo == "aggiorna":
                    if self.overlay is not None:
                        self.overlay.aggiorna(dato)
                elif tipo == "stato":
                    self.l_stato.config(text=dato)
                elif tipo == "nota":
                    self.scrivi(dato, tag="nota")
        except queue.Empty:
            pass
        # **Il sottotitolo tradotto sparisce da solo.** Una banda perenne in
        # mezzo allo schermo e' peggio dell'originale che copriva.
        if self.overlay is not None and time.perf_counter() >= self._overlay_fino_a:
            self.overlay.nascondi()
        self.root.after(100, self._svuota_coda)

    # -- avvio e arresto ---------------------------------------------------

    def avvia(self) -> None:
        if self.threads:
            return
        self.stop.clear()
        self.b_start.config(state="disabled")
        self.b_stop.config(state="normal")
        self.b_area.config(state="disabled")
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
            self.sessione = None if self.args.no_save else Session(samplerate=sr)
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

            def ciclo_video() -> None:
                # La sorgente si apre **nel thread che la usa**: dxcam sta su COM,
                # e creata altrove non solleva — restituisce `None` a ogni grab.
                schermo = make_screen(self.args.backend, monitor=self.args.monitor)
                self.coda.put(("nota", f"cattura schermo: {schermo.name}"))
                # **La telecamera virtuale sta qui e non altrove**: il fotogramma
                # da mandare a OBS e' quello appena catturato, e portarlo su un
                # altro thread vorrebbe dire copiarlo trenta volte al secondo per
                # niente.
                camera = None
                if self.cfg.record.enabled:
                    from ui.record import apri_o_spiega

                    camera = apri_o_spiega(self.cfg.record, self.coda)
                    if camera is not None:
                        self.coda.put((
                            "nota",
                            f"telecamera virtuale accesa ({self.cfg.record.width} px "
                            f"di larghezza): in OBS aggiungi la sorgente «Dispositivo "
                            f"di acquisizione video» -> «OBS Virtual Camera»",
                        ))
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
                        if n == 0 and vuoti > 2 * self.cfg.capture.fps and schermo.name != "mss":
                            schermo.close()
                            schermo = make_screen("mss", monitor=self.args.monitor)
                            self.coda.put((
                                "nota",
                                "! la cattura veloce non restituisce fotogrammi: passo a mss",
                            ))
                            vuoti = 0
                        continue
                    n += 1
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
                            self.coda.put(
                                ("overlay",
                                 (riga.text, riga.text_original, fine,
                                  *inchiostro(g.frame, self.cfg)))
                            )
                    # **La cancellatura segue la scena, la geometria no.** Il
                    # riquadro resta dove e' comparso; sotto, i pixel si
                    # rinfrescano — se no, mentre la telecamera si muove, resta
                    # una toppa di immagine vecchia in mezzo allo schermo. A
                    # 10 Hz invece che a 30 perche' ogni giro rifa' la bitmap di
                    # Tk, e su una macchia sfocata l'occhio non distingue le due.
                    if (self.overlay is not None and n % 3 == 0
                            and time.perf_counter() < self._overlay_fino_a):
                        self.coda.put(("aggiorna", g.frame.copy()))
                        # Il tetto resta, ma non e' piu' lui a decidere: e' una
                        # previsione, e una previsione sbagliata in difetto fa
                        # sparire il tradotto con l'originale ancora a schermo.
                        # Chi decide e' l'inchiostro, dentro `Overlay.aggiorna`.
                        self._overlay_fino_a = max(
                            self._overlay_fino_a, time.perf_counter() + 0.5
                        ) if self.overlay._visibile else self._overlay_fino_a
                    # **Si manda la tela che c'e' gia'**, non una seconda
                    # composizione: cosi' quello che si vede sul monitor e quello
                    # che finisce in OBS sono gli stessi pixel, e non c'e' modo
                    # che divergano.
                    if camera is not None:
                        ult = self.overlay.ultima if self.overlay is not None else None
                        if ult is None:
                            camera.manda(g.frame)
                        else:
                            camera.manda(g.frame, ult[0], ult[1], ult[2])
                    if n % 30 == 0:
                        p = len(self.pipeline.tracker) if self.pipeline.tracker else 0
                        self.coda.put(("stato",
                                       f"in corso  |  {n} frame  |  {len(self.pipeline.spoken)} battute"
                                       f"  |  {p} personaggi  |  {len(self.pipeline.pool)} voci"))
                if camera is not None:
                    camera.chiudi()

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
                rapporto = self.pipeline.report() if self.pipeline is not None else ""
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
        "--recording",
        action="store_true",
        help="espone una telecamera virtuale con il gioco e il sottotitolo tradotto (per OBS)",
    )
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
