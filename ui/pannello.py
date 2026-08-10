"""Il pannello delle impostazioni, disegnato percorrendo l'albero di config.

**Non c'e' un elenco di campi qui dentro.** Le manopole nascono da
`core.schema.campi()`, quindi aggiungere un parametro in `core/config.py` lo fa
comparire nel pannello senza toccare questo file — ed e' il punto: un elenco
scritto a mano diverge al primo campo aggiunto.

Tre cose che il pannello deve fare bene, e che sono la ragione per cui non e'
solo una griglia di caselle:

**1. Dire cosa fa ogni manopola, con la misura.** Accanto a ogni campo c'e' una
`?` che apre il commento di `core/config.py` cosi' com'e' scritto — comprese le
tabelle delle misure. Non e' un testo riscritto per l'occasione: riscriverlo
vorrebbe dire perdere le misure e inventare rischi.

**2. Distinguere cio' che si applica subito da cio' che vuole un riavvio.**
I campi freddi (il motore della voce, quello dell'OCR, l'anello audio) sono
marcati e, se cambiati a sessione accesa, lo dicono. Fingere che si applichino
darebbe una sessione che gira con una configurazione diversa da quella che il
pannello mostra, che e' il difetto peggiore per uno strumento di misura.

**3. Non far mai divergere quel che si vede da quel che si usa.** Ogni manopola
riscrive il valore **rileggendolo da config** dopo averlo applicato: se `set()`
lo ha convertito o rifiutato, a schermo si vede il risultato vero. E' lo stesso
difetto trovato sulla soglia del colore digitando `9999`, generalizzato.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from core.schema import TITOLI, Campo, campi

# Larghezza del testo dell'aiuto, in caratteri. I commenti di `config.py` sono
# scritti a 88 colonne: piu' stretto di cosi' le tabelle delle misure si
# spezzano, e una tabella spezzata non si legge.
LARGHEZZA_AIUTO = 92


class Pannello(ttk.Frame):
    """Tutte le impostazioni, raggruppate per sezione, con la loro spiegazione.

    `al_cambio(campo, valore)` viene chiamato a ogni modifica applicata: chi
    ospita il pannello decide cosa farne (scriverlo a log, segnare che serve un
    riavvio, salvare il profilo).
    """

    def __init__(
        self,
        padre,
        cfg,
        *,
        al_cambio: Callable[[Campo, Any], None] | None = None,
        sessione_accesa: Callable[[], bool] = lambda: False,
        solo: tuple[str, ...] = (),
        cerca: bool = True,
    ) -> None:
        super().__init__(padre)
        self.cfg = cfg
        self.al_cambio = al_cambio
        self.sessione_accesa = sessione_accesa
        self._var: dict[str, tk.Variable] = {}
        self._widget: dict[str, tk.Widget] = {}
        self._righe: list[tuple[Campo, tk.Widget]] = []
        # **Lo stesso pannello serve anche la scheda delle tecnologie.** Un
        # secondo disegnatore mostrerebbe una cosa mentre questo ne fa un'altra,
        # ed e' esattamente cosi' che sono nati i difetti dell'overlay: si filtra
        # l'elenco, non si riscrive la griglia.
        self.solo = tuple(solo)

        # Il filtro: con 165 campi, trovarne uno scorrendo e' il modo peggiore.
        barra = ttk.Frame(self)
        if cerca:
            barra.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Label(barra, text="Cerca").pack(side="left")
        self.v_cerca = tk.StringVar()
        casella = ttk.Entry(barra, textvariable=self.v_cerca, width=28)
        casella.pack(side="left", padx=6)
        self.v_cerca.trace_add("write", lambda *_: self._filtra())
        self.v_solo_caldi = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            barra, text="solo quelli applicabili a caldo",
            variable=self.v_solo_caldi, command=self._filtra,
        ).pack(side="left", padx=10)
        ttk.Button(barra, text="Riporta ai default", command=self.ripristina).pack(side="right")

        self.stato = ttk.Label(self, text="", foreground="#8b949e", anchor="w")
        self.stato.pack(fill="x", padx=8, pady=(4, 0))

        self._scorrevole(cfg)
        self._filtra()
        # Se le spiegazioni non ci sono (pacchetto senza `core/config.py` fra i
        # dati), lo si dice a chiare lettere invece di mostrare un pannello che
        # sembra completo e ha perso tutte le misure.
        if not any(c.aiuto for c, _ in self._righe if c is not None):
            self._dillo(
                "le spiegazioni dei parametri non sono disponibili in questa copia "
                "(manca core/config.py): le manopole funzionano, i testi no",
                errore=True,
            )

    # -- costruzione -------------------------------------------------------

    def _scorrevole(self, cfg) -> None:
        """Una tela che scorre: 165 campi non stanno in una finestra."""
        contenitore = ttk.Frame(self)
        contenitore.pack(fill="both", expand=True, padx=6, pady=6)
        tela = tk.Canvas(contenitore, highlightthickness=0)
        barra = ttk.Scrollbar(contenitore, orient="vertical", command=tela.yview)
        self.dentro = ttk.Frame(tela)
        self.dentro.bind(
            "<Configure>", lambda _e: tela.configure(scrollregion=tela.bbox("all"))
        )
        finestra = tela.create_window((0, 0), window=self.dentro, anchor="nw")
        tela.bind("<Configure>", lambda e: tela.itemconfigure(finestra, width=e.width))
        tela.configure(yscrollcommand=barra.set)
        tela.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        # La rotellina, che senza questo non muove niente dentro un Canvas.
        tela.bind_all("<MouseWheel>", lambda e: tela.yview_scroll(-e.delta // 120, "units"))

        sezione_corrente = None
        for campo in campi(cfg):
            if self.solo and campo.percorso not in self.solo:
                continue
            if campo.sezione != sezione_corrente:
                sezione_corrente = campo.sezione
                titolo = ttk.Label(
                    self.dentro,
                    text=TITOLI.get(campo.sezione, campo.sezione),
                    font=("Segoe UI", 10, "bold"),
                )
                titolo.pack(fill="x", pady=(14, 4))
                self._righe.append((None, titolo))  # type: ignore[arg-type]
            self._riga(campo)

    def _riga(self, campo: Campo) -> None:
        riga = ttk.Frame(self.dentro)
        riga.pack(fill="x", pady=1)

        etichetta = ttk.Label(riga, text=campo.nome, width=26, anchor="w")
        etichetta.pack(side="left")

        widget = self._manopola(riga, campo)
        widget.pack(side="left")
        self._widget[campo.percorso] = widget

        # **Il marchio del riavvio sta sulla riga, non in una nota a fondo
        # pagina.** Chi cambia il motore della voce deve vederlo li'.
        if not campo.caldo:
            ttk.Label(riga, text="riavvio", foreground="#c9772a").pack(side="left", padx=6)
        if not campo.modificabile:
            ttk.Label(riga, text="non modificabile", foreground="#8b949e").pack(side="left", padx=6)

        ttk.Button(riga, text="?", width=2, command=lambda c=campo: self.spiega(c)).pack(
            side="left", padx=4
        )
        sommario = campo.sommario
        if sommario:
            ttk.Label(
                riga, text=_una_riga(sommario), foreground="#8b949e", anchor="w"
            ).pack(side="left", fill="x", expand=True, padx=6)
        self._righe.append((campo, riga))

    def _manopola(self, padre, campo: Campo) -> tk.Widget:
        """La manopola giusta per il tipo. Il tipo del valore e' il contratto."""
        if not campo.modificabile:
            var = tk.StringVar(value=_testo(campo.valore))
            self._var[campo.percorso] = var
            return ttk.Entry(padre, textvariable=var, width=22, state="disabled")

        if campo.tipo == "bool":
            var = tk.BooleanVar(value=bool(campo.valore))
            self._var[campo.percorso] = var
            return ttk.Checkbutton(padre, variable=var, command=lambda c=campo: self.applica(c))

        if campo.scelte:
            var = tk.StringVar(value=str(campo.valore))
            self._var[campo.percorso] = var
            menu = ttk.Combobox(
                padre, textvariable=var, values=list(campo.scelte), width=20, state="readonly"
            )
            menu.bind("<<ComboboxSelected>>", lambda _e, c=campo: self.applica(c))
            return menu

        var = tk.StringVar(value=_testo(campo.valore))
        self._var[campo.percorso] = var
        casella = ttk.Entry(padre, textvariable=var, width=22)
        # Si applica quando si e' finito di scrivere — a ogni tasto vorrebbe dire
        # applicare `1` mentre si sta digitando `12`.
        casella.bind("<Return>", lambda _e, c=campo: self.applica(c))
        casella.bind("<FocusOut>", lambda _e, c=campo: self.applica(c))
        return casella

    # -- applicare ---------------------------------------------------------

    def applica(self, campo: Campo) -> None:
        """Scrive il valore in config e **rilegge quello che c'e' davvero**.

        La rilettura non e' un lusso: `Config.set` converte al tipo del campo e
        puo' rifiutare. Senza, il pannello mostrerebbe cio' che e' stato
        digitato mentre la catena usa un'altra cosa — che e' esattamente il
        difetto trovato sulla soglia del colore digitando `9999`.
        """
        var = self._var[campo.percorso]
        try:
            self.cfg.set(campo.percorso, var.get())
        except (ValueError, TypeError, KeyError):
            # **Il messaggio e' per l'utente, non per chi ha scritto il codice.**
            # `invalid literal for int() with base 10` dice cosa e' successo a
            # Python; qui serve dire cosa fare, e soprattutto che il valore di
            # prima e' ancora quello in uso — se no si resta col dubbio di aver
            # rotto qualcosa a meta' sessione.
            atteso = {
                "int": "un numero intero", "float": "un numero",
                "bool": "vero o falso", "tuple": "dei numeri separati da virgola",
            }.get(campo.tipo, "un testo")
            self._dillo(
                f"{campo.nome}: qui ci va {atteso}. Resta "
                f"{_testo(self.cfg.get(campo.percorso))}, che e' quello in uso.",
                errore=True,
            )
            self._rileggi(campo)
            return
        self._rileggi(campo)
        vero = self.cfg.get(campo.percorso)
        if campo.caldo:
            self._dillo(f"{campo.percorso} = {_testo(vero)}")
        elif self.sessione_accesa():
            self._dillo(
                f"{campo.percorso} = {_testo(vero)} — si applica al prossimo Avvia, "
                "non a questa sessione",
                errore=True,
            )
        else:
            self._dillo(f"{campo.percorso} = {_testo(vero)}")
        if self.al_cambio is not None:
            self.al_cambio(campo, vero)

    def _rileggi(self, campo: Campo) -> None:
        vero = self.cfg.get(campo.percorso)
        var = self._var[campo.percorso]
        if isinstance(var, tk.BooleanVar):
            var.set(bool(vero))
        else:
            var.set(_testo(vero))

    def aggiorna(self) -> None:
        """Rilegge **tutti** i campi da config.

        Serve quando qualcosa fuori dal pannello tocca la configurazione — il
        selettore d'area che scrive la ROI, un profilo caricato. Senza, due
        finestre della stessa cosa direbbero due cose diverse.
        """
        for campo, _ in self._righe:
            if campo is not None and campo.percorso in self._var:
                self._rileggi(campo)

    def ripristina(self) -> None:
        """Riporta tutto ai default dichiarati in `core/config.py`."""
        n = 0
        for campo, _ in self._righe:
            if campo is None or not campo.modificabile:
                continue
            if self.cfg.get(campo.percorso) != campo.default:
                self.cfg.set(campo.percorso, campo.default)
                n += 1
        self.aggiorna()
        self._dillo(f"riportati ai default {n} campi")

    # -- aiuto e filtro ----------------------------------------------------

    def spiega(self, campo: Campo) -> None:
        """La spiegazione del campo, cosi' com'e' scritta in `core/config.py`."""
        top = tk.Toplevel(self)
        top.title(campo.percorso)
        top.geometry("760x520")
        intestazione = ttk.Frame(top)
        intestazione.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(
            intestazione, text=campo.percorso, font=("Segoe UI", 11, "bold")
        ).pack(side="left")
        ttk.Label(
            intestazione,
            text=("si applica subito" if campo.caldo else "serve un riavvio per applicarlo"),
            foreground=("#2f7d32" if campo.caldo else "#c9772a"),
        ).pack(side="right")
        ttk.Label(
            top,
            text=f"adesso: {_testo(self.cfg.get(campo.percorso))}     "
                 f"default: {_testo(campo.default)}     tipo: {campo.tipo}",
            foreground="#8b949e",
        ).pack(fill="x", padx=10, pady=(2, 6))

        testo = tk.Text(top, wrap="word", width=LARGHEZZA_AIUTO, font=("Consolas", 9))
        testo.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        testo.insert(
            "1.0",
            campo.aiuto
            or "Questo campo non ha ancora una spiegazione scritta in core/config.py.\n\n"
               "Non e' un dettaglio: significa che nessuno ha ancora messo per iscritto "
               "cosa misura e cosa si rischia a cambiarlo. Cambialo con prudenza.",
        )
        testo.configure(state="disabled")
        ttk.Button(top, text="Chiudi", command=top.destroy).pack(pady=(0, 10))

    def _filtra(self) -> None:
        """Mostra solo le righe che contano, e nasconde i titoli rimasti vuoti."""
        cerca = self.v_cerca.get().strip().lower()
        solo_caldi = self.v_solo_caldi.get()
        visti = 0
        da_mostrare: list[tuple[Campo, tk.Widget]] = []
        for campo, widget in self._righe:
            if campo is None:
                da_mostrare.append((campo, widget))
                continue
            ok = True
            if solo_caldi and not campo.caldo:
                ok = False
            if cerca and cerca not in campo.percorso.lower() and cerca not in campo.aiuto.lower():
                ok = False
            if ok:
                da_mostrare.append((campo, widget))
                visti += 1

        # Un titolo di sezione senza campi sotto e' rumore: si toglie.
        tenuti = set()
        for i, (campo, widget) in enumerate(da_mostrare):
            if campo is not None:
                tenuti.add(id(widget))
                continue
            seguono = any(c is not None for c, _ in da_mostrare[i + 1 : i + 400])
            prossimo_titolo = next(
                (j for j in range(i + 1, len(da_mostrare)) if da_mostrare[j][0] is None),
                len(da_mostrare),
            )
            if seguono and prossimo_titolo > i + 1:
                tenuti.add(id(widget))

        for campo, widget in self._righe:
            if id(widget) in tenuti:
                widget.pack(fill="x", pady=(14, 4) if campo is None else 1)
            else:
                widget.pack_forget()
        self.stato.configure(text=f"{visti} parametri mostrati")

    def _dillo(self, testo: str, errore: bool = False) -> None:
        self.stato.configure(text=testo, foreground="#c0392b" if errore else "#8b949e")


def _testo(valore: Any) -> str:
    if isinstance(valore, tuple):
        return ", ".join(_testo(v) for v in valore)
    if isinstance(valore, float):
        return f"{valore:g}"
    if isinstance(valore, dict):
        return f"({len(valore)} voci)"
    return str(valore)


def _una_riga(testo: str, massimo: int = 110) -> str:
    pulito = " ".join(testo.replace("**", "").replace("`", "").split())
    return pulito if len(pulito) <= massimo else pulito[: massimo - 1] + "…"
