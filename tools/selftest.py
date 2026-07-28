"""Suite di autoverifica di livedub.

Non c'e' pytest: la suite e' un modulo eseguibile e ogni gruppo e' una funzione
che si puo' chiamare da sola.

    .\.venv\Scripts\python.exe -m tools.selftest
    .\.venv\Scripts\python.exe -m tools.selftest ring config

    from tools.selftest import test_ring, Check
    c = Check(); test_ring(c); c.report()

Vincoli che la suite si impone:
- **niente hardware**: nessuna scheda audio, nessuna cattura schermo;
- **nessun modello**: i gruppi che toccheranno VAD/embedding/OCR dovranno
  forzare i backend leggeri, altrimenti al primo avvio scaricherebbero file;
- **tempo virtuale**: dove si misura, si misura con `VirtualClock`, cosi' il
  risultato non dipende dal carico della macchina.
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np

# Permette sia `python -m tools.selftest` sia `python tools/selftest.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import RealClock, VirtualClock, get_clock, set_clock  # noqa: E402
from core.config import Config  # noqa: E402
from core.metrics import Counter, MetricsRegistry, Timer  # noqa: E402
from core.ring import Overrun, RingBuffer  # noqa: E402
from core.stage import Chain, FnStage, Stage  # noqa: E402
from core.types import (  # noqa: E402
    AudioChunk,
    Emotion,
    LineClass,
    OcrLine,
    SubtitleEvent,
    merge_lines,
)


class Check:
    """Accumulatore di verifiche. Non si ferma al primo errore: un solo giro
    deve dire *tutto* quello che e' rotto, non la prima cosa."""

    def __init__(self, verbose: bool = False) -> None:
        self.passed = 0
        self.failures: list[str] = []
        self.group_name = "-"
        self.verbose = verbose

    def group(self, name: str) -> None:
        self.group_name = name

    def ok(self, cond: bool, desc: str) -> bool:
        if cond:
            self.passed += 1
            if self.verbose:
                print(f"  ok   {self.group_name}: {desc}")
        else:
            self.failures.append(f"{self.group_name}: {desc}")
            print(f"  FAIL {self.group_name}: {desc}")
        return bool(cond)

    def eq(self, got, want, desc: str) -> bool:
        return self.ok(got == want, f"{desc} (atteso {want!r}, ottenuto {got!r})")

    def close(self, got: float, want: float, desc: str, tol: float = 1e-6) -> bool:
        return self.ok(
            abs(got - want) <= tol, f"{desc} (atteso {want} +/-{tol}, ottenuto {got})"
        )

    def raises(self, exc, fn, desc: str) -> bool:
        try:
            fn()
        except exc:
            return self.ok(True, desc)
        except Exception as e:  # eccezione sbagliata: e' comunque un fallimento
            return self.ok(False, f"{desc} (atteso {exc.__name__}, ottenuto {type(e).__name__})")
        return self.ok(False, f"{desc} (nessuna eccezione sollevata)")

    def report(self) -> int:
        total = self.passed + len(self.failures)
        print()
        if self.failures:
            print(f"{len(self.failures)} FALLITE su {total} verifiche:")
            for f in self.failures:
                print(f"  - {f}")
            return 1
        print(f"{self.passed}/{total} verifiche verdi.")
        return 0


# ---------------------------------------------------------------- clock ----


def test_clock(c: Check) -> None:
    c.group("clock")

    real = RealClock()
    t0 = real.now()
    t1 = real.now()
    c.ok(t1 >= t0, "RealClock e' monotono")
    c.ok(t0 >= 0.0, "RealClock parte da zero")

    v = VirtualClock()
    c.close(v.now(), 0.0, "VirtualClock parte a 0")
    v.advance(1.5)
    c.close(v.now(), 1.5, "advance somma")
    v.advance(0.5)
    c.close(v.now(), 2.0, "advance e' cumulativo")
    c.close(v.now(), 2.0, "now() da solo non fa scorrere il tempo")
    v.set(10.0)
    c.close(v.now(), 10.0, "set porta al tempo indicato")
    c.raises(ValueError, lambda: v.set(9.0), "set indietro e' un errore")
    c.raises(ValueError, lambda: v.advance(-1.0), "advance negativo e' un errore")

    previous = set_clock(v)
    c.ok(get_clock() is v, "set_clock sostituisce l'orologio globale")
    restored = set_clock(previous)
    c.ok(restored is v, "set_clock restituisce quello che ha sostituito")
    c.ok(get_clock() is previous, "l'orologio globale e' stato ripristinato")


# -------------------------------------------------------------- metrics ----


def test_metrics(c: Check) -> None:
    c.group("metrics")

    t = Timer("x")
    c.eq(t.count, 0, "timer nuovo e' vuoto")
    c.close(t.p50, 0.0, "percentile di un timer vuoto e' 0")
    for ms in range(1, 101):  # 1..100
        t.add(float(ms))
    c.eq(t.count, 100, "conta tutti i campioni")
    c.close(t.mean, 50.5, "media di 1..100", tol=1e-9)
    c.close(t.max, 100.0, "massimo")
    c.close(t.p50, 50.5, "p50 interpola fra i due centrali", tol=1e-9)
    c.close(t.percentile(0.0), 1.0, "p0 e' il minimo")
    c.close(t.percentile(1.0), 100.0, "p100 e' il massimo")
    c.ok(t.p95 > t.p50, "p95 sta sopra la mediana")
    c.ok(t.p99 >= t.p95, "p99 non sta sotto p95")
    c.raises(ValueError, lambda: t.percentile(1.5), "percentile fuori range e' un errore")

    # La finestra scorre, ma count e max restano sulla storia intera.
    w = Timer("w", window=4)
    for ms in (10.0, 20.0, 30.0, 40.0, 50.0):
        w.add(ms)
    c.eq(w.count, 5, "count e' sulla storia intera")
    c.close(w.max, 50.0, "max e' sulla storia intera")
    c.close(w.percentile(0.0), 20.0, "il percentile usa solo la finestra")

    n = Counter("n")
    c.eq(n.value, 0, "contatore parte da 0")
    n.inc()
    n.inc(4)
    c.eq(n.value, 5, "inc somma")
    n.reset()
    c.eq(n.value, 0, "reset azzera")

    reg = MetricsRegistry()
    c.ok(reg.timer("a") is reg.timer("a"), "il registro non duplica i timer")
    c.ok(reg.counter("b") is reg.counter("b"), "il registro non duplica i contatori")
    reg.timer("a").add(5.0)
    reg.counter("b").inc(3)
    snap = reg.snapshot()
    c.eq(snap["timers"]["a"]["count"], 1, "lo snapshot riporta i timer")
    c.eq(snap["counters"]["b"], 3, "lo snapshot riporta i contatori")
    c.ok("a" in reg.report(), "il report nomina i timer")
    c.ok("(nessuna misura" in MetricsRegistry().report(), "report di un registro vuoto")
    reg.reset()
    c.eq(reg.timer("a").count, 0, "reset del registro azzera i timer")


# ---------------------------------------------------------------- stage ----


class _Double(Stage):
    def process(self, x):
        return x * 2


class _Boom(Stage):
    def process(self, x):
        raise RuntimeError("scoppio previsto")

    def bypass(self, x):
        return "fallback"


class _Slow(Stage):
    """Stadio che consuma tempo *del media* senza costare nulla a muro."""

    def __init__(self, name, cost, **kw):
        super().__init__(name, **kw)
        self.cost = cost

    def process(self, x):
        self.clock.advance(self.cost)
        return x


class _FakeCost:
    """Cronometro finto: restituisce i valori indicati, uno per chiamata."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.i = 0

    def __call__(self) -> float:
        v = self.steps[min(self.i, len(self.steps) - 1)]
        self.i += 1
        return v


def test_stage(c: Check) -> None:
    c.group("stage")

    d = _Double("double")
    c.eq(d.run(21), 42, "process viene chiamato")
    c.eq(d(21), 42, "lo stadio e' chiamabile")
    c.eq(d.elapsed.count, 2, "ogni run e' cronometrato")

    d.enabled = False
    c.eq(d.run(21), 21, "spento, lascia passare l'ingresso")
    c.eq(d.elapsed.count, 2, "spento, non si cronometra")
    c.eq(d.metrics.counter("double.skipped").value, 1, "spento, conta lo skip")

    boom = _Boom("boom")
    c.raises(RuntimeError, lambda: boom.run(1), "on_error=raise propaga")
    c.eq(boom.errors, 1, "l'errore viene contato anche quando propaga")

    soft = _Boom("soft", on_error="bypass")
    c.eq(soft.run(1), "fallback", "on_error=bypass degrada invece di cadere")
    c.eq(soft.errors, 1, "l'errore viene contato")
    c.eq(soft.elapsed.count, 1, "anche il tentativo fallito e' cronometrato")

    c.raises(
        ValueError, lambda: Stage("x", on_error="esplodi"), "on_error sconosciuto e' un errore"
    )
    c.raises(NotImplementedError, lambda: Stage("nudo").run(1), "Stage base non ha process")

    # I due tempi non vanno confusi: il costo si misura a muro, il tempo del
    # media e' un'altra cosa. Questa coppia di verifiche esiste perche' il primo
    # tentativo li aveva fusi e in replay ogni stadio risultava gratis.
    vc = VirtualClock()
    reg = MetricsRegistry()
    slow = _Slow("slow", cost=0.030, metrics=reg, clock=vc, cost_now=_FakeCost([0.0, 0.002]))
    slow.run(None)
    c.close(vc.now(), 0.030, "lo stadio ha fatto avanzare il tempo del media")
    c.close(reg.timer("slow").p50, 2.0, "il costo e' quello a muro, non quello del media", tol=1e-9)

    free = _Slow("free", cost=5.0, metrics=reg, clock=VirtualClock(), cost_now=_FakeCost([1.0]))
    free.run(None)
    c.close(
        reg.timer("free").p50, 0.0, "5s di media a costo zero restano costo zero", tol=1e-9
    )

    timed = FnStage("timed", lambda x: x, metrics=reg, cost_now=_FakeCost([0.0, 0.0125]))
    timed.run(1)
    c.close(reg.timer("timed").p50, 12.5, "il cronometro converte in millisecondi", tol=1e-9)

    err = _Boom("errcost", metrics=reg, on_error="bypass", cost_now=_FakeCost([0.0, 0.004]))
    err.run(1)
    c.close(reg.timer("errcost").p50, 4.0, "anche il fallimento riporta il suo costo", tol=1e-9)

    # Catena.
    chain = Chain(
        "cat",
        [FnStage("inc", lambda x: x + 1), FnStage("dbl", lambda x: x * 2)],
        metrics=reg,
        clock=vc,
    )
    c.eq(chain.run(3), 8, "la catena rispetta l'ordine: (3+1)*2")
    c.eq(len(chain), 2, "len della catena")
    c.ok(chain.find("dbl") is not None, "find trova per nome")
    c.ok(chain.find("assente") is None, "find restituisce None se non c'e'")
    c.ok(chain.set_enabled("dbl", False), "set_enabled trova lo stadio")
    c.eq(chain.run(3), 4, "con dbl spento la catena lascia passare")
    c.ok(not chain.set_enabled("assente", False), "set_enabled su nome ignoto e' False")

    nested = Chain("fuori", [Chain("dentro", [FnStage("foglia", lambda x: x)])])
    c.ok(nested.find("foglia") is not None, "find scende nelle catene annidate")


# ----------------------------------------------------------------- ring ----


def test_ring(c: Check) -> None:
    c.group("ring")

    r = RingBuffer(capacity=8, channels=1, samplerate=1000)
    c.eq(r.written, 0, "buffer nuovo non ha scritture")
    c.eq(r.available, 0, "buffer nuovo non ha dati")

    start = r.write(np.arange(4, dtype=np.float32))
    c.eq(start, 0, "write restituisce l'indice assoluto del blocco")
    c.eq(r.written, 4, "written conta i frame")
    c.eq(r.available, 4, "available prima del giro")
    c.ok(np.array_equal(r.read_last(4), np.arange(4)), "rilegge quello che ha scritto")

    # Padding a sinistra quando i dati non bastano.
    padded = r.read_last(6)
    c.eq(len(padded), 6, "read_last rispetta la lunghezza richiesta")
    c.ok(np.array_equal(padded[:2], np.zeros(2)), "il padding sta a sinistra")
    c.ok(np.array_equal(padded[2:], np.arange(4)), "i dati restano allineati a destra")
    c.eq(len(r.read_last(6, pad=False)), 4, "senza pad restituisce quel che c'e'")

    # Giro del buffer: la scrittura scavalca la fine dell'array.
    c.eq(r.write(np.arange(4, 10, dtype=np.float32)), 4, "seconda scrittura parte da 4")
    c.eq(r.written, 10, "written e' assoluto, non modulo capacita'")
    c.eq(r.available, 8, "available si ferma alla capacita'")
    c.ok(np.array_equal(r.read_last(8), np.arange(2, 10)), "dopo il giro rilegge la coda giusta")

    # Lettura per indice assoluto e sorpasso.
    c.ok(np.array_equal(r.read_from(4, 3), np.arange(4, 7)), "read_from legge dall'indice dato")
    c.eq(len(r.read_from(8, 10)), 2, "read_from non inventa dati non ancora scritti")
    c.raises(Overrun, lambda: r.read_from(0, 2), "leggere dati sovrascritti e' un Overrun")
    c.raises(ValueError, lambda: r.read_from(99, 1), "leggere nel futuro e' un errore")
    c.ok(r.overruns >= 1, "l'overrun viene contato")

    # Multicanale.
    st = RingBuffer(capacity=4, channels=2, samplerate=48000)
    block = np.array([[1.0, -1.0], [2.0, -2.0]], dtype=np.float32)
    st.write(block)
    got = st.read_last(2)
    c.eq(got.shape, (2, 2), "il multicanale conserva la forma")
    c.ok(np.array_equal(got, block), "il multicanale conserva i valori")
    c.raises(
        ValueError, lambda: st.write(np.zeros((2, 3), np.float32)), "numero di canali sbagliato"
    )
    c.raises(ValueError, lambda: RingBuffer(0), "capacita' nulla e' un errore")

    # Un blocco piu' grande del buffer tiene la coda e si segnala.
    big = RingBuffer(capacity=4, samplerate=1000)
    big.write(np.arange(10, dtype=np.float32))
    c.ok(np.array_equal(big.read_last(4), np.arange(6, 10)), "blocco sovradimensionato: tiene la coda")
    c.eq(big.overruns, 1, "blocco sovradimensionato: lo segnala")

    # Conversione tempo/frame.
    tr = RingBuffer(capacity=16, samplerate=48000)
    c.close(tr.frame_to_time(48000), 1.0, "48000 frame a 48 kHz sono un secondo")
    c.eq(tr.time_to_frame(0.5), 24000, "mezzo secondo sono 24000 frame")
    c.close(tr.frame_to_time(tr.time_to_frame(2.5)), 2.5, "il giro tempo->frame->tempo torna")


# --------------------------------------------------------------- config ----


def test_config(c: Check) -> None:
    c.group("config")

    cfg = Config()
    c.eq(cfg.profile, "gtav", "profilo di default")
    c.eq(cfg.get("vision.sat_max"), 60, "get legge un campo annidato")

    c.eq(cfg.set("vision.sat_max", "70"), 70, "int convertito da stringa")
    c.ok(isinstance(cfg.get("vision.sat_max"), int), "il tipo resta int")
    c.close(cfg.set("timing.rate_max", "1.5"), 1.5, "float convertito da stringa")
    c.eq(cfg.set("mix.passthrough", "false"), False, "booleano da 'false'")
    c.eq(cfg.set("mix.passthrough", "1"), True, "booleano da '1'")
    c.eq(cfg.set("ui.enabled", "si"), True, "booleano da 'si'")
    c.eq(cfg.set("tts.backend", "tone"), "tone", "stringa passa invariata")
    c.eq(
        cfg.set("vision.roi", "0.1,0.5,0.8,0.3"),
        (0.1, 0.5, 0.8, 0.3),
        "tupla di float da stringa separata da virgole",
    )

    c.raises(ValueError, lambda: cfg.set("mix.passthrough", "forse"), "booleano non valido")
    c.raises(ValueError, lambda: cfg.set("vision.sat_max", "molto"), "int non valido")
    c.raises(KeyError, lambda: cfg.set("vision.inesistente", "1"), "campo sconosciuto")
    c.raises(KeyError, lambda: cfg.set("sezione.assente", "1"), "sezione sconosciuta")
    c.raises(KeyError, lambda: cfg.get("niente"), "get su percorso ignoto")

    c.raises(ValueError, lambda: Config().apply(["senza_uguale"]), "override senza '=' e' un errore")
    applied = Config().apply(["vad.threshold=0.8", "tts.backend=tone"])
    c.close(applied.get("vad.threshold"), 0.8, "apply imposta il primo override")
    c.eq(applied.get("tts.backend"), "tone", "apply imposta il secondo override")
    c.eq(Config().apply(None).profile, "gtav", "apply(None) non fa danni")

    dumped = Config().dump()
    c.ok("vision.sat_max" in dumped, "il dump nomina i campi annidati")
    c.ok("audio.device" in dumped and "(vuoto)" in dumped, "il dump mostra le stringhe vuote")
    c.eq(len(dumped.splitlines()), len(_leaf_paths(Config())), "il dump elenca ogni foglia")

    # Giro completo su disco: salvare e ricaricare non deve cambiare nulla.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "profilo.json"
        original = Config().apply(["vision.sat_max=42", "vision.roi=0.2,0.6,0.5,0.2"])
        original.save(path)
        reloaded = Config.load(path)
        c.eq(reloaded.get("vision.sat_max"), 42, "il salvataggio conserva gli interi")
        c.eq(reloaded.get("vision.roi"), (0.2, 0.6, 0.5, 0.2), "il salvataggio conserva le tuple")
        c.eq(reloaded.dump(), original.dump(), "salva/ricarica e' un giro identita'")
        c.ok(
            isinstance(reloaded.get("tts.voices"), tuple),
            "le tuple restano tuple dopo il giro su JSON",
        )


def _leaf_paths(obj, prefix: str = "") -> list[str]:
    from dataclasses import fields, is_dataclass

    out: list[str] = []
    for f in fields(obj):
        value = getattr(obj, f.name)
        if is_dataclass(value):
            out.extend(_leaf_paths(value, f"{prefix}{f.name}."))
        else:
            out.append(f"{prefix}{f.name}")
    return out


# ---------------------------------------------------------------- types ----


def _line(text: str, cls: LineClass, top: int) -> OcrLine:
    return OcrLine(text=text, cls=cls, bbox=(0, top, 100, 20))


def test_types(c: Check) -> None:
    c.group("types")

    c.ok(LineClass.WHITE.is_dialogue, "il bianco e' dialogo")
    c.ok(LineClass.GREY.is_dialogue, "il grigio e' dialogo")
    c.ok(not LineClass.COLORED.is_dialogue, "il colorato non e' dialogo")

    sub = SubtitleEvent(text="ciao mondo", cls=LineClass.WHITE, t_on=1.0)
    c.eq(sub.n_chars, 10, "n_chars conta i caratteri")
    c.ok(sub.duration is None, "senza t_off la durata non e' nota")
    c.close(sub.closed(3.5).duration, 2.5, "closed calcola la durata")
    c.close(sub.t_on, 1.0, "closed non tocca l'originale (evento immutabile)")

    e = Emotion.neutral()
    c.eq(e.label, "neutral", "l'emozione neutra ha etichetta neutral")
    c.close(e.arousal, 0.0, "l'emozione neutra ha arousal 0")

    chunk = AudioChunk(samples=np.zeros(480, np.float32), t0=2.0, samplerate=48000)
    c.eq(chunk.n_frames, 480, "n_frames")
    c.eq(chunk.channels, 1, "un array 1-D e' mono")
    c.close(chunk.duration, 0.01, "480 frame a 48 kHz sono 10 ms")
    c.close(chunk.t1, 2.01, "t1 e' t0 piu' la durata")
    c.eq(AudioChunk(np.zeros((10, 2), np.float32), 0.0, 48000).channels, 2, "array 2-D e' stereo")


def test_grammar(c: Check) -> None:
    """La grammatica dei sottotitoli: e' la fondamenta di tutto il resto, quindi
    ha un gruppo suo."""
    c.group("grammar")

    # Una riga bianca sola: una battuta.
    ev = merge_lines([_line("ciao", LineClass.WHITE, 0)], t_on=1.0)
    c.eq(len(ev), 1, "una riga bianca produce una battuta")
    c.eq(ev[0].text, "ciao", "il testo passa")
    c.eq(ev[0].cls, LineClass.WHITE, "la classe passa")
    c.close(ev[0].t_on, 1.0, "il t_on passa")

    # Due righe bianche: una frase andata a capo, non due battute.
    ev = merge_lines(
        [_line("non e' il momento", LineClass.WHITE, 0), _line("di scherzare", LineClass.WHITE, 20)],
        t_on=0.0,
    )
    c.eq(len(ev), 1, "due righe bianche sono UNA battuta andata a capo")
    c.eq(ev[0].text, "non e' il momento di scherzare", "le righe si uniscono con uno spazio")
    c.eq(len(ev[0].lines), 2, "la battuta ricorda da quante righe viene")

    # Bianco sopra, grigio sotto: due speaker, due battute distinte.
    ev = merge_lines(
        [_line("dove vai?", LineClass.WHITE, 0), _line("lasciami stare", LineClass.GREY, 20)],
        t_on=0.0,
    )
    c.eq(len(ev), 2, "bianco + grigio sono DUE battute")
    c.eq(ev[0].cls, LineClass.WHITE, "la prima battuta e' quella bianca")
    c.eq(ev[1].cls, LineClass.GREY, "la seconda battuta e' quella grigia")
    c.eq(ev[0].text, "dove vai?", "il testo non si mescola fra le due")
    c.eq(ev[1].text, "lasciami stare", "il testo della grigia resta suo")

    # Una riga colorata butta se' stessa, non le vicine.
    ev = merge_lines(
        [
            _line("premi E per entrare", LineClass.COLORED, 0),
            _line("sali in macchina", LineClass.WHITE, 20),
        ],
        t_on=0.0,
    )
    c.eq(len(ev), 1, "la riga colorata sparisce")
    c.eq(ev[0].text, "sali in macchina", "la riga bianca sopravvive alla vicina colorata")

    # Solo colorato: niente da dire.
    c.eq(merge_lines([_line("obiettivo", LineClass.COLORED, 0)], 0.0), [], "solo colorato: nessuna battuta")
    c.eq(merge_lines([], 0.0), [], "nessuna riga: nessuna battuta")

    # L'ordine verticale comanda, non l'ordine della lista.
    ev = merge_lines(
        [_line("seconda", LineClass.WHITE, 40), _line("prima", LineClass.WHITE, 0)], t_on=0.0
    )
    c.eq(ev[0].text, "prima seconda", "le righe si ordinano per posizione verticale")

    # Grigio sopra e bianco sotto: due battute, nell'ordine in cui stanno.
    ev = merge_lines(
        [_line("aspetta", LineClass.GREY, 0), _line("no", LineClass.WHITE, 20)], t_on=0.0
    )
    c.eq([e.cls for e in ev], [LineClass.GREY, LineClass.WHITE], "l'ordine segue lo schermo")

    # Tre righe W/G/W: tre battute, il grigio non fonde le due bianche.
    ev = merge_lines(
        [
            _line("a", LineClass.WHITE, 0),
            _line("b", LineClass.GREY, 20),
            _line("c", LineClass.WHITE, 40),
        ],
        t_on=0.0,
    )
    c.eq(len(ev), 3, "W/G/W sono tre battute distinte")
    c.eq([e.text for e in ev], ["a", "b", "c"], "nessun testo si mescola fra le tre")

    # Righe vuote non generano battute fantasma.
    ev = merge_lines([_line("   ", LineClass.WHITE, 0), _line("vero", LineClass.WHITE, 20)], 0.0)
    c.eq(len(ev), 1, "una riga vuota non crea una battuta in piu'")
    c.eq(ev[0].text, "vero", "la riga vuota non lascia spazi nel testo")
    c.eq(merge_lines([_line("  ", LineClass.WHITE, 0)], 0.0), [], "solo spazi: nessuna battuta")


def test_timing(c: Check) -> None:
    """La misura su cui poggia F2: durata prevista dal numero di caratteri."""
    c.group("timing")

    from tools.bench_timing import fit, letters

    c.eq(letters("Ciao, Lamar!"), 9, "letters conta le sole lettere")
    c.eq(letters("!!!"), 0, "una lettura di sola punteggiatura non ha lunghezza")
    c.ok(
        letters("Che succede, Simeon?") == letters("Che succede Simeon"),
        "la punteggiatura che l'OCR inventa non cambia la lunghezza",
    )
    c.ok(
        letters("Ma domani...") == letters("Madomani."),
        "e nemmeno lo spazio che l'OCR si mangia",
    )

    # La retta contro la propria inversa: da coefficienti noti si generano le
    # durate, e l'adattamento deve restituire quei coefficienti. Senza questa
    # verifica un errore di segno o di ordine (b, a invece di a, b) darebbe
    # numeri plausibili e sbagliati, che e' il modo in cui questi errori
    # sopravvivono.
    n = np.arange(10, 60, dtype=float)
    a, b = fit(n, 1.25 + 0.037 * n)
    c.close(a, 1.25, "fit ritrova l'intercetta", tol=1e-6)
    c.close(b, 0.037, "fit ritrova la pendenza", tol=1e-9)

    # Rumore simmetrico: i coefficienti reggono, ed e' cio' che distingue
    # "misura rumorosa" da "misura sbagliata".
    rumore = np.array([+0.2, -0.2] * (len(n) // 2), dtype=float)
    a2, b2 = fit(n, 1.25 + 0.037 * n + rumore)
    c.ok(abs(a2 - 1.25) < 0.1, "con rumore simmetrico l'intercetta regge")
    c.ok(abs(b2 - 0.037) < 0.005, "con rumore simmetrico la pendenza regge")

    c.eq(fit(np.array([1.0]), np.array([1.0])), (0.0, 0.0), "un punto solo non definisce una retta")


def test_replay_stats(c: Check) -> None:
    """Il banco misura anche se stesso, e va verificato come il resto."""
    c.group("replay")

    from tools.replay import ReplayStats

    s = ReplayStats()
    c.close(s.media_seconds, 0.0, "una corsa vuota non ha media")
    c.close(s.speedup, 0.0, "ne' velocita', invece di dividere per zero")

    # Una fetta che NON parte da zero: e' il caso in cui la versione precedente
    # dichiarava 1290s di media per 50s di fetta, cioe' 24x invece di 0,9x.
    s.media_first, s.media_last, s.wall_seconds = 1240.0, 1290.0, 55.0
    c.close(s.media_seconds, 50.0, "il media e' la lunghezza della fetta, non l'istante finale")
    c.ok(0.8 < s.speedup < 1.0, "e la velocita' e' quella vera")

    z = ReplayStats()
    z.media_first, z.media_last, z.wall_seconds = 0.0, 10.0, 1.0
    c.close(z.speedup, 10.0, "su una fetta che parte da zero il conto non cambia")


def test_duration_model(c: Check) -> None:
    """Il predittore di durata e le sue guardie."""
    c.group("duration")

    from core.config import TimingConfig
    from fuse.timing import DurationModel, spoken_length

    c.eq(spoken_length("Ciao, Lamar!"), 9, "spoken_length ignora la punteggiatura")
    c.eq(spoken_length("Ma domani..."), spoken_length("Madomani."), "e lo spazio mangiato dall'OCR")

    cfg = TimingConfig()
    cfg.predict_a, cfg.predict_b = 1.0, 0.02
    m = DurationModel(cfg)
    c.close(m.predict("a" * 50), 2.0, "predict applica la retta")
    c.close(m.predict("a" * 5000), cfg.max_duration, "non sale sopra il massimo")
    corto = TimingConfig()
    corto.predict_a, corto.predict_b = 0.1, 0.001
    c.close(
        DurationModel(corto).predict("ab"),
        corto.min_duration,
        "e non scende sotto il minimo",
    )

    # Il piano: quanto tempo c'e' e a che velocita' starci dentro.
    p = m.plan("a" * 50, spoken=2.0)          # previsione 2.0s, sintesi 2.0s
    c.close(p.rate, 1.0, "se ci sta gia', la velocita' resta nominale")
    c.ok(p.fits, "e non c'e' sforamento")
    p = m.plan("a" * 50, spoken=2.4)          # serve andare piu' svelti
    c.close(p.rate, 1.2, "per starci dentro accelera")
    c.ok(p.fits, "e ci sta")
    p = m.plan("a" * 50, spoken=4.0)          # oltre cio' che WSOLA sa fare
    c.close(p.rate, cfg.rate_max, "la velocita' e' limitata")
    c.ok(not p.fits, "oltre il limite si dichiara lo sforamento")
    c.close(p.overflow, 4.0 / cfg.rate_max - 2.0, "e lo si quantifica")

    # never_drop: la battuta si dice comunque. E' la promessa del prodotto, non
    # un dettaglio, quindi ha una verifica sua.
    c.ok(p.overflow > 0 and p.rate > 0, "sforando, la battuta resta dicibile")

    # Il tempo gia' consumato riduce il budget, non la durata prevista.
    p = m.plan("a" * 50, spoken=1.0, elapsed=0.5)
    c.close(p.budget, 1.5, "il budget e' quello che resta")
    c.close(p.predicted, 2.0, "la durata prevista non cambia")

    # Apprendimento: la verita' e' un'altra retta, e il modello ci si avvicina.
    learner = DurationModel(TimingConfig())
    prima = learner.predict("a" * 40)
    for _ in range(60):
        for n in (10, 20, 30, 40, 50):
            learner.observe("a" * n, 0.5 + 0.05 * n)
    c.ok(learner.samples == 300, "ha visto tutti i campioni")
    c.ok(abs(learner.predict("a" * 40) - 2.5) < abs(prima - 2.5), "impara nella direzione giusta")

    # Le guardie. Senza queste l'aggiornamento in linea e' il posto ideale per
    # rovinare tutto in silenzio.
    guard = DurationModel(TimingConfig())
    c.ok(not guard.observe("una battuta vera", 0.2), "un frammento non e' una durata")
    c.ok(not guard.observe("una battuta vera", 30.0), "un sottotitolo in pausa nemmeno")
    c.ok(not guard.observe("", 1.5), "una battuta senza lettere nemmeno")
    c.eq(guard.samples, 0, "nessuno dei tre e' stato imparato")
    c.eq(guard.ignored, 3, "e tutti e tre sono stati contati")

    fermo = DurationModel(TimingConfig())
    a0, b0 = fermo.a, fermo.b
    for _ in range(fermo.cfg.learn_min_samples - 1):
        fermo.observe("a" * 30, 2.0)
    c.ok(fermo.a == a0 and fermo.b == b0, "sotto la soglia di campioni non si muove niente")

    # E la guardia che conta di piu': dati coerenti ma assurdi non devono poter
    # spostare la retta oltre la fascia dichiarata.
    matto = DurationModel(TimingConfig())
    for _ in range(300):
        matto.observe("a" * 40, 7.9)
    drift = matto.cfg.learn_max_drift
    c.ok(matto.a <= matto.cfg.predict_a + drift + 1e-9, "l'intercetta resta nella fascia")
    c.ok(matto.b <= matto.cfg.predict_b * (1 + drift) + 1e-9, "la pendenza resta nella fascia")


from tools.selftest_audio import (  # noqa: E402
    test_center,
    test_mixer,
    test_pool,
    test_stretch,
    test_tts_fake,
)
from tools.selftest_vision import (  # noqa: E402
    test_diff,
    test_lines,
    test_ocr_prep,
    test_reader,
    test_roi,
    test_tracker,
)

GROUPS = {
    "clock": test_clock,
    "metrics": test_metrics,
    "stage": test_stage,
    "ring": test_ring,
    "config": test_config,
    "types": test_types,
    "grammar": test_grammar,
    "timing": test_timing,
    "duration": test_duration_model,
    "replay": test_replay_stats,
    "roi": test_roi,
    "lines": test_lines,
    "diff": test_diff,
    "ocr": test_ocr_prep,
    "tracker": test_tracker,
    "reader": test_reader,
    "stretch": test_stretch,
    "center": test_center,
    "pool": test_pool,
    "tts": test_tts_fake,
    "mixer": test_mixer,
}


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    verbose = "-v" in args
    if verbose:
        args.remove("-v")
    wanted = args or list(GROUPS)

    unknown = [name for name in wanted if name not in GROUPS]
    if unknown:
        print(f"gruppi sconosciuti: {', '.join(unknown)}")
        print(f"disponibili: {', '.join(GROUPS)}")
        return 2

    c = Check(verbose=verbose)
    for name in wanted:
        try:
            GROUPS[name](c)
        except Exception:
            c.failures.append(f"{name}: il gruppo e' esploso")
            print(f"  FAIL {name}: il gruppo e' esploso")
            traceback.print_exc()
    return c.report()


if __name__ == "__main__":
    raise SystemExit(main())
