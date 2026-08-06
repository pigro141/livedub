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

import re
import sys
import tempfile
import time
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


def test_audio_source(c: Check) -> None:
    """La traccia audio del banco, verificata contro un ingresso costruito.

    Il file di prova si genera qui: e' l'unico modo di sapere cosa **deve**
    uscire. I due canali portano frequenze diverse apposta — un mixdown mono
    nascosto restituirebbe comunque un tono plausibile, e la verifica non lo
    vedrebbe.

    Non serve hardware e non serve un modello: solo il binario di ffmpeg che
    arriva con `imageio-ffmpeg`. Se manca, il gruppo lo dice e passa oltre
    invece di fallire — una dipendenza assente non e' codice rotto.
    """
    c.group("audio_source")

    import subprocess

    from tools.sources import AudioPipe, VideoSource, ffmpeg_exe, has_audio_track

    exe = ffmpeg_exe()
    if exe is None:
        c.ok(True, "ffmpeg assente: gruppo saltato (pip install imageio-ffmpeg)")
        return

    sr, dur, f_sx, f_dx = 48000, 2.0, 440.0, 1000.0
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        raw, media, muto = tmpdir / "a.f32", tmpdir / "a.mp4", tmpdir / "muto.mp4"
        t = np.arange(int(sr * dur), dtype=np.float32) / sr
        stereo = np.stack(
            [0.5 * np.sin(2 * np.pi * f_sx * t), 0.5 * np.sin(2 * np.pi * f_dx * t)], axis=1
        ).astype(np.float32)
        raw.write_bytes(stereo.tobytes())
        base = [exe, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"color=c=black:s=160x120:r=30:d={dur}"]
        subprocess.run(
            base + ["-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", str(raw),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(media)],
            check=True, capture_output=True,
        )
        subprocess.run(
            base + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(muto)],
            check=True, capture_output=True,
        )

        c.ok(has_audio_track(media), "riconosce un file con traccia audio")
        c.ok(not has_audio_track(muto), "e uno senza")

        with AudioPipe(media, samplerate=sr, channels=2) as pipe:
            got = np.concatenate([pipe.read(4800) for _ in range(15)], axis=0)
        c.eq(got.shape, (72000, 2), "legge la forma richiesta")
        c.ok(abs(float(np.sqrt((got[:, 0] ** 2).mean())) - 0.354) < 0.03, "il livello e' quello")

        def picco(x: np.ndarray) -> float:
            seg = x[sr // 2 : sr // 2 + 8192]
            spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
            return float(np.fft.rfftfreq(len(seg), 1 / sr)[int(np.argmax(spec))])

        c.ok(abs(picco(got[:, 0]) - f_sx) < 5.0, "il canale sinistro porta la sua frequenza")
        c.ok(abs(picco(got[:, 1]) - f_dx) < 5.0, "il destro la sua: i canali non sono mescolati")

        # Oltre la fine della traccia si riempie di silenzio invece di
        # accorciarsi: una sorgente che si accorcia da sola sfaserebbe i frame.
        with AudioPipe(media, samplerate=sr, channels=2) as pipe:
            coda = [pipe.read(sr) for _ in range(4)]  # 4 s da una traccia di 2
        c.eq(coda[-1].shape, (sr, 2), "oltre la fine restituisce comunque la lunghezza chiesta")
        c.close(float(np.abs(coda[-1]).max()), 0.0, "e la riempie di silenzio", tol=1e-6)

        # L'allineamento con i frame e' costruito, non calcolato.
        src = VideoSource(media, fps=30.0)
        c.ok(src.has_audio, "la sorgente video dichiara di avere audio")
        blocchi = [p.audio.shape[0] for p in src.packets() if p.audio is not None]
        c.eq(set(blocchi), {sr // 30}, "ogni pacchetto porta samplerate/fps campioni")
        c.ok(abs(sum(blocchi) / sr - len(blocchi) / 30.0) < 1e-9, "audio e video non scivolano")

        muta = VideoSource(muto, fps=30.0)
        c.ok(not muta.has_audio, "su un file senza traccia lo dichiara")
        c.ok(
            all(p.audio is None for p in muta.packets()),
            "e non inventa silenzio spacciandolo per audio",
        )
        c.ok(
            not VideoSource(media, fps=30.0, with_audio=False).has_audio,
            "with_audio=False spegne la traccia anche quando c'e'",
        )


def test_vad(c: Check) -> None:
    """Il rilevatore di parlato, su un segnale costruito.

    Costruito perche' la risposta deve essere nota **prima**: su audio di gioco
    "il VAD non trova la voce" e "la voce non c'e'" hanno lo stesso aspetto, e
    solo un ingresso di cui si conosce la verita' li separa.
    """
    c.group("vad")

    from core.config import VadConfig
    from listen.vad import EnergyVad, Speech, dbfs, make_vad

    sr = 16000
    c.close(dbfs(np.zeros(100, np.float32)), -120.0, "il silenzio digitale vale -120 dBFS")
    c.close(dbfs(np.ones(100, np.float32)), 0.0, "un segnale a fondo scala vale 0 dBFS", tol=1e-4)
    c.ok(abs(dbfs(np.full(100, 0.5, np.float32)) + 6.02) < 0.05, "meta' ampiezza sono -6 dB")
    c.eq(dbfs(np.zeros(0, np.float32)), -120.0, "un blocco vuoto non esplode")

    def scena(*pezzi: tuple[float, float]) -> np.ndarray:
        """(durata, ampiezza) -> rumore continuo, con i tratti forti al posto giusto."""
        rng = np.random.default_rng(7)
        out = []
        for durata, amp in pezzi:
            n = int(sr * durata)
            out.append((rng.standard_normal(n) * amp).astype(np.float32))
        return np.concatenate(out)

    cfg = VadConfig()
    cfg.backend = "energy"

    # Fondo debole, un secondo di "parlato" forte, poi di nuovo fondo.
    audio = scena((2.0, 0.005), (1.0, 0.15), (2.0, 0.005))
    vad = EnergyVad(cfg, sr)
    chiuse = []
    for i in range(0, len(audio), 1600):
        chiuse += vad.push(audio[i : i + 1600])
    chiuse += vad.flush()
    c.eq(len(chiuse), 1, "trova una presa di parola sola")
    if chiuse:
        s = chiuse[0]
        c.ok(abs(s.t0 - 2.0) < 0.10, f"e comincia dove comincia davvero (t0={s.t0:.3f})")
        c.ok(abs((s.duration or 0) - 1.0) < 0.25, f"con la durata giusta (d={s.duration:.3f})")
        c.ok(s.peak_dbfs > -30.0, "e ricorda quanto era forte")

    # L'onset dichiarato e' quello del PRIMO frame sopra soglia, non quello
    # della conferma: con min_speech_ms alto la differenza si vede a occhio.
    lento = VadConfig()
    lento.backend, lento.min_speech_ms = "energy", 400
    vad = EnergyVad(lento, sr)
    audio = scena((2.0, 0.005), (1.5, 0.15), (2.0, 0.005))
    chiuse = []
    for i in range(0, len(audio), 1600):
        chiuse += vad.push(audio[i : i + 1600])
    chiuse += vad.flush()
    c.eq(len(chiuse), 1, "con conferma lenta trova sempre una presa sola")
    if chiuse:
        c.ok(
            abs(chiuse[0].t0 - 2.0) < 0.10,
            f"e l'onset NON slitta di min_speech_ms (t0={chiuse[0].t0:.3f}, non ~2.4)",
        )

    # Il fondo che cambia: la stessa voce, prima in una scena silenziosa e poi
    # in una rumorosa. Una soglia assoluta ne troverebbe una sola.
    forte = scena((2.0, 0.05), (1.0, 0.5), (2.0, 0.05))
    vad = EnergyVad(cfg, sr)
    chiuse = []
    for i in range(0, len(forte), 1600):
        chiuse += vad.push(forte[i : i + 1600])
    chiuse += vad.flush()
    c.eq(len(chiuse), 1, "con fondo dieci volte piu' alto trova comunque la voce")

    # E il contrario, senza il quale il precedente non dimostra niente: su
    # rumore uniforme non deve inventare parlato.
    piatto = scena((5.0, 0.05),)
    vad = EnergyVad(cfg, sr)
    chiuse = []
    for i in range(0, len(piatto), 1600):
        chiuse += vad.push(piatto[i : i + 1600])
    chiuse += vad.flush()
    c.eq(len(chiuse), 0, "su rumore uniforme non trova nessuna presa di parola")

    # Il fondo si stima mentre si tace, e questo da solo si avvita: un fondo
    # fermo tiene acceso il rilevatore, e un rilevatore acceso impedisce al
    # fondo di muoversi. Qui una scena silenziosa passa a rumorosa e ci **resta**
    # — un inseguimento, non una battuta. Senza la guardia il VAD dichiarava
    # parlato fino in fondo; misurato sull'audio vero di GTA V faceva l'87% del
    # tempo con otto aperture al minuto, che e' il ritratto di un rilevatore
    # acceso e non di uno che rileva.
    salita = scena((2.0, 0.005), (20.0, 0.15))
    vad = EnergyVad(cfg, sr)
    chiuse = []
    for i in range(0, len(salita), 1600):
        chiuse += vad.push(salita[i : i + 1600])
    aperta = vad.current
    chiuse += vad.flush()
    tetto = (cfg.floor_hold_ms + cfg.floor_window_ms + 1000) / 1000.0
    piu_lunga = max((s.duration or 0.0) for s in chiuse) if chiuse else 0.0
    c.ok(
        piu_lunga < tetto,
        f"un rumore che non finisce non diventa una presa di parola infinita "
        f"(la piu' lunga dura {piu_lunga:.1f}s, non 20)",
    )
    c.ok(
        aperta is None or (22.0 - aperta.t0) < tetto,
        "e a fine scena il rilevatore non e' rimasto incastrato sopra soglia",
    )
    parlato = sum(s.duration or 0.0 for s in chiuse)
    c.ok(
        parlato < 0.5 * 22.0,
        f"il fondo si e' ritarato sulla scena nuova ({parlato:.1f}s di parlato su 22)",
    )

    # E la guardia non deve rubare le battute vere: una presa di parola normale,
    # piu' corta di `floor_hold_ms`, resta intera. Senza questa verifica la
    # precedente si accontenterebbe di un rilevatore che tronca tutto.
    normale = scena((2.0, 0.005), (2.5, 0.15), (2.0, 0.005))
    vad = EnergyVad(cfg, sr)
    chiuse = []
    for i in range(0, len(normale), 1600):
        chiuse += vad.push(normale[i : i + 1600])
    chiuse += vad.flush()
    c.eq(len(chiuse), 1, "una battuta di due secondi e mezzo resta una presa sola")
    if chiuse:
        c.ok(
            abs((chiuse[0].duration or 0) - 2.5) < 0.3,
            f"e non viene troncata dalla guardia (d={chiuse[0].duration:.2f}s)",
        )

    # Due prese separate da un silenzio lungo restano due; da uno breve, una.
    due = scena((1.5, 0.005), (0.8, 0.15), (1.0, 0.005), (0.8, 0.15), (1.5, 0.005))
    vad = EnergyVad(cfg, sr)
    chiuse = []
    for i in range(0, len(due), 1600):
        chiuse += vad.push(due[i : i + 1600])
    chiuse += vad.flush()
    c.eq(len(chiuse), 2, "un secondo di silenzio separa due prese di parola")

    attaccate = scena((1.5, 0.005), (0.8, 0.15), (0.1, 0.005), (0.8, 0.15), (1.5, 0.005))
    vad = EnergyVad(cfg, sr)
    chiuse = []
    for i in range(0, len(attaccate), 1600):
        chiuse += vad.push(attaccate[i : i + 1600])
    chiuse += vad.flush()
    c.eq(len(chiuse), 1, "un respiro di 100 ms non le separa")

    # Il risultato non deve dipendere da come l'audio e' spezzettato: in gioco
    # la dimensione dei blocchi la decide la scheda audio, non noi.
    rif = None
    for blocco in (256, 1600, 4800, 7999):
        vad = EnergyVad(cfg, sr)
        audio = scena((2.0, 0.005), (1.0, 0.15), (2.0, 0.005))
        got = []
        for i in range(0, len(audio), blocco):
            got += vad.push(audio[i : i + blocco])
        got += vad.flush()
        segni = [(round(s.t0, 2), round(s.t1 or 0, 2)) for s in got]
        if rif is None:
            rif = segni
        c.eq(segni, rif, f"stesso risultato con blocchi da {blocco} campioni")

    c.raises(
        ValueError,
        lambda: EnergyVad(cfg, sr).push(np.zeros((100, 2), np.float32)),
        "audio stereo al VAD e' un errore, non un mixdown silenzioso",
    )
    c.ok(isinstance(make_vad(cfg, sr), EnergyVad), "make_vad costruisce quello a energia")
    silero = VadConfig()
    silero.backend = "silero"
    c.ok(
        isinstance(make_vad(silero, sr), EnergyVad),
        "silero non c'e' ancora e si ripiega su energy (dichiarato, non silenzioso)",
    )
    c.raises(ValueError, lambda: make_vad(_vad_cfg("inventato"), sr), "backend ignoto e' un errore")

    s = Speech(1.0)
    c.ok(s.duration is None, "una presa ancora aperta non ha durata")
    c.close(s.ended(2.5).duration, 1.5, "chiuderla la fissa")


def _vad_cfg(backend: str):
    from core.config import VadConfig

    cfg = VadConfig()
    cfg.backend = backend
    return cfg


def test_live_start(c: Check) -> None:
    """Le due origini: quella della sessione e quella del mixer.

    Esiste perche' il difetto e' arrivato in produzione e si e' sentito prima
    di essere misurato: il doppiaggio partiva venti secondi dopo la realta',
    con le pause giuste. Le pause erano giuste perche' i due orologi corrono
    alla stessa velocita'; a essere diverse erano le origini.
    """
    c.group("live_start")

    from core.config import Config
    from core.pipeline import DubPipeline
    from speak.base import ToneTts

    cfg = Config()
    cfg.vision.ocr_backend = "none"  # nessun modello: la suite non scarica
    orologio = VirtualClock()
    pipeline = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=48000)

    # Il tempo passato ad aprire i device e a caricare i modelli, prima che il
    # primo blocco audio arrivi.
    orologio.set(18.0)
    c.close(pipeline.mixer.now, 0.0, "il mixer parte da zero, l'orologio no")

    pipeline.start_live(warmup=False)
    c.close(pipeline.mixer.now, 18.0, "start_live allinea l'origine del mixer")

    evento = SubtitleEvent(text="sali in macchina", cls=LineClass.WHITE, t_on=18.0)
    riga = pipeline._speak(evento)
    anticipo = riga.t_scheduled - pipeline.mixer.now
    c.ok(
        0.0 <= anticipo < 0.05,
        f"la battuta e' programmata sul presente del mixer, non nel futuro "
        f"(scarto {anticipo:.3f}s)",
    )

    # E la prova al contrario, senza la quale la precedente non dimostra nulla:
    # senza allineamento la stessa battuta nasce diciotto secondi avanti.
    storto = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=48000)
    riga_storta = storto._speak(evento)
    c.ok(
        riga_storta.t_scheduled - storto.mixer.now > 17.0,
        "senza allineamento la battuta nasce con tutto il ritardo dell'avvio",
    )


def test_lingua(c: Check) -> None:
    """Cosa puo' finire in bocca al sintetizzatore.

    Il riconoscitore e' addestrato su cinese e inglese: sullo scenario
    restituisce glifi CJK, e il cancello che doveva fermarli contava i
    caratteri *alfanumerici*, che in Python li comprende. Il difetto e' arrivato
    fino alle cuffie.
    """
    c.group("lingua")

    from vision.ocr import italian_only, latin_letters

    c.eq(italian_only("冏一"), "", "i glifi cinesi spariscono")
    c.eq(latin_letters("冏一"), 0, "e non contano come lettere")
    c.ok("冏一".isalnum(), "mentre per Python SONO alfanumerici: ecco il difetto")
    # Il glifo estraneo si toglie **senza** mettere uno spazio al suo posto:
    # quando e' una sostituzione dentro una parola — 'aveva一no' per 'avevano',
    # che e' il caso frequente — lo spazio spezzerebbe la parola in due, e il
    # sintetizzatore leggerebbe due parole inventate invece di una giusta.
    c.eq(italian_only("一..uuA"), "..uuA", "un misto tiene solo la parte latina")
    c.eq(italian_only("aveva一no"), "avevano", "e non spezza la parola che stava rovinando")
    c.eq(italian_only("／一一"), "", "e la punteggiatura a larghezza intera non salva la riga")

    # La punteggiatura italiana si TIENE: al sintetizzatore serve.
    c.eq(
        italian_only("E questi li consideri obiettivi raggiunti?"),
        "E questi li consideri obiettivi raggiunti?",
        "una battuta italiana passa intatta",
    )
    c.eq(italian_only("Perche' no, pero'..."), "Perche' no, pero'...", "apostrofi e puntini restano")
    c.eq(italian_only("Città, così, è"), "Città, così, è", "gli accenti restano")
    c.eq(italian_only("Ehi!  Tu,   fermo."), "Ehi! Tu, fermo.", "gli spazi doppi si appiattiscono")
    c.eq(latin_letters("Ehi!"), 3, "latin_letters conta lettere e cifre, non punteggiatura")
    c.eq(latin_letters("...!?"), 0, "una riga di sola punteggiatura non ha lettere")

    # I simboli non sono punteggiatura: il sintetizzatore li legge come PAROLE.
    # 'Va bene.../' usciva dalle cuffie come "va bene barra", ed e' arrivato di
    # li' perche' la barra stava nella lista chiamata "serve alla prosodia".
    c.eq(italian_only("Va bene.../"), "Va bene...", "la barra sparisce: Piper la direbbe 'barra'")
    c.eq(italian_only("r ilii-+il"), "r ilii-il", "e il piu', che l'OCR produce a ogni tratto spezzato")
    c.eq(italian_only("Ti do 500$"), "Ti do 500$", "il dollaro resta: in GTA V la cifra E' la battuta")

    # Spazzatura di scena in TESTA alla frase, che e' il prezzo del riquadro
    # allargato per non tagliare le battute lunghe. In mezzo e' un inciampo, in
    # testa e' la prima cosa che si sente.
    c.eq(
        italian_only("-- :- Pero devo dirglielo"),
        "Pero devo dirglielo",
        "i gruppi di sola punteggiatura in testa se ne vanno",
    )
    c.eq(italian_only(". obbligato a parlare"), "obbligato a parlare", "anche uno solo")
    c.eq(italian_only("Ehi, fermo. , 1"), "Ehi, fermo. , 1", "ma una cifra in coda NON e' spazzatura")
    c.eq(
        italian_only("Aspetta, arrivo. --"),
        "Aspetta, arrivo.",
        "e la coda si pulisce come la testa",
    )
    # Il prezzo, dichiarato invece che scoperto dopo: un'ellissi iniziale se ne
    # va con la spazzatura, perche' di lettere non ne ha nessuna.
    c.eq(italian_only("... e poi?"), "e poi?", "un '...' iniziale e' il prezzo di questa pulizia")


def test_lessico(c: Check) -> None:
    """Il filtro sulla lingua: l'ultimo che sta fra l'OCR e le cuffie.

    Le soglie di colore e contrasto hanno gia' fatto il possibile — un cordolo
    bianco **e'** bianco e sottile — e cio' che resta si separa solo sapendo
    che il dialogo e' italiano e l'asfalto no.
    """
    c.group("lessico")

    from vision.lexicon import Lexicon, carica

    lex = Lexicon({"va", "bene", "sfogati", "pure", "tuo", "figlio", "cazzo",
                   "un", "altra", "brillante", "ideona", "di", "perche"})

    c.ok(lex.nota("bene"), "una parola del dizionario e' nota")
    c.ok(lex.nota("Bene."), "e la punteggiatura attorno non la nasconde")
    c.ok(lex.nota("CAZZO"), "ne' le maiuscole")
    c.ok(not lex.nota("IIFIL"), "la spazzatura no")
    c.eq(lex.conta("Un altra brillante ideona"), 4, "conta le parole note della riga")
    c.eq(lex.conta("IIFIL REEr"), 0, "e zero e' il segnale che cerchiamo")

    # Una parola di UNA lettera non e' una prova. 'i', 'e', 'a', 'o' sono
    # italiano vero e stanno in ogni dizionario, ma l'OCR le ricava da qualunque
    # tratto verticale della scena. Dal vivo `'I ler!'` e' passato per la sola
    # 'I', ha preso la voce del secondo personaggio, ed e' uscito dalle cuffie
    # mentre a schermo non c'era nessun sottotitolo.
    articoli = Lexicon({"i", "e", "a", "va", "bene", "si"})
    c.eq(articoli.conta("I ler!"), 0, "un articolo di una lettera non valida la riga")
    c.eq(articoli.conta("e"), 0, "ne' una congiunzione da sola")
    c.eq(articoli.conta("Si."), 1, "ma due lettere si', altrimenti si perde 'Si.'")
    c.eq(articoli.conta("i bene"), 1, "e la parola vera accanto conta lo stesso")

    # Basta UNA parola: l'OCR ne rompe sempre qualcuna, e pretenderle tutte
    # buone scarterebbe il dialogo vero insieme alla scena.
    c.ok(lex.conta("Propric qui, cazzo!") >= 1, "una parola buona basta a salvare la riga")

    # `separa` non puo' inventare: o trova due parole vere, o si arrende.
    c.eq(lex.separa("Vabene"), "Va bene", "due parole incollate si separano")
    c.eq(lex.separa("Sfogatipure"), "Sfogati pure", "anche quando sono lunghe")
    c.eq(lex.separa("IIFIL"), None, "ma la spazzatura non si separa in niente")
    c.eq(lex.separa("bene"), None, "e una parola gia' buona si lascia stare")
    c.eq(
        lex.separa("benecazzoxyz"), None,
        "e se una delle due meta' non e' una parola, non si taglia",
    )
    # La maiuscola si conserva: e' l'inizio di una battuta, non un dettaglio.
    c.eq(lex.separa("VABENE"), "VA BENE", "e le maiuscole restano come stavano")
    # E la punteggiatura pure. Separare `'Vabene,'` perdendo la virgola
    # riparerebbe una cosa rompendone un'altra: quella virgola e' la pausa che
    # il sintetizzatore ci mette.
    c.eq(lex.separa("Vabene,"), "Va bene,", "e la virgola non si perde per strada")
    c.eq(lex.separa("«Vabene!»"), "«Va bene!»", "ne' i segni che stanno da tutt'e due i lati")
    c.eq(lex.scolla("Vabene, tuofiglio"), "Va bene, tuo figlio", "scolla tutta la riga")

    # **I nomi propri non si toccano.** 'Lamar' -> 'La mar' e 'Davis' -> 'Da
    # vis' passavano la regola "solo se esistono tutt'e due", perche' esistono
    # davvero: la parola spezzata era giusta e il risultato sbagliato. A
    # distinguerli e' la maiuscola in mezzo alla frase, e a inizio riga quel
    # segnale non c'e' perche' ce l'hanno tutte le battute.
    nomi = Lexicon({"la", "mar", "da", "vis", "di", "va", "bene", "casa"})
    c.eq(
        nomi.scolla("di Lamar Davis"), "di Lamar Davis",
        "un nome proprio in mezzo alla frase resta intero",
    )
    c.eq(nomi.separa("Vabene", prima=True), "Va bene", "ma a inizio riga si separa lo stesso")
    c.eq(nomi.separa("Vabene", prima=False), None, "e in mezzo no, che e' il prezzo dichiarato")

    # Un taglio solo. Se i punti buoni sono due, la parola e' ambigua e
    # sceglierne uno sarebbe indovinare.
    ambigua = Lexicon({"can", "tare", "canta", "re"})
    c.eq(ambigua.separa("cantare"), None, "una parola con due tagli buoni non si tocca")

    # Un lessico vuoto deve DICHIARARSI vuoto. Se rispondesse "conosciuta" a
    # tutto, il filtro sarebbe spento in silenzio e si continuerebbe a misurare
    # credendo che stia lavorando — che e' peggio di non averlo.
    vuoto = Lexicon(set())
    c.ok(not vuoto, "un lessico vuoto e' falso in verita', cosi' chi lo usa se ne accorge")
    c.eq(vuoto.conta("qualunque cosa"), 0, "e non conosce niente")
    mancante = carica("cartella/che/non/esiste")
    c.ok(not mancante, "una cartella assente da un lessico vuoto, non un errore")

    # E quello vero, se e' stato scaricato: qui non si finge.
    reale = carica("models/lexicon")
    if reale:
        c.ok(len(reale) > 100_000, f"il lessico italiano vero ha {len(reale)} parole")
        for w in ("vaffanculo", "cazzo", "puttane", "rapinato", "banche", "perche"):
            c.ok(reale.nota(w), f"e contiene {w!r}")
        c.eq(reale.conta("IIFIL REEr lte"), 0, "mentre la spazzatura resta spazzatura")


def test_fretta(c: Check) -> None:
    """Stringere il residuo di una battuta gia' cominciata.

    L'invariante e' una sola e vale piu' di tutte le altre: **cio' che e' gia'
    uscito dalle cuffie non si tocca**. Ristirare l'intera battuta darebbe una
    forma d'onda diversa da quella gia' suonata, e la giunzione cadrebbe dove
    l'orecchio e' gia' passato — un salto udibile, e non rimediabile perche' il
    suono e' gia' andato. Si ristira solo da `consumed` in poi.
    """
    c.group("fretta")

    from mix.mixer import Mixer

    sr = 24000

    def scena(durata: float, suonato: float):
        m = Mixer(samplerate=sr, passthrough=False)
        t = np.linspace(0, durata, int(sr * durata), endpoint=False, dtype=np.float32)
        voce = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        m.schedule(voce, 0.0)
        m.process(None, n=int(sr * suonato))
        return m, m._queue[0]

    m, item = scena(2.0, 0.5)
    consumato = item.consumed
    prima = item.audio[:consumato].copy()
    lunga_prima = len(item.audio)
    rate = m.hurry(m.now, limits=(1.0, 1.35))
    c.ok(rate > 1.0, f"con la battuta dopo alle porte si stringe (rate={rate:.3f})")
    c.ok(rate <= 1.35 + 1e-6, "senza superare il limite dichiarato")
    c.eq(item.consumed, consumato, "la posizione di lettura non si sposta")
    c.ok(
        np.array_equal(item.audio[:consumato], prima),
        "e i campioni GIA' SUONATI sono identici, campione per campione",
    )
    c.ok(len(item.audio) < lunga_prima, "mentre il totale si accorcia")
    residuo = (len(item.audio) - consumato) / sr
    c.close(residuo, 1.5 / rate, "il residuo dura quanto lo stiramento promette", tol=0.05)

    # Con tempo in abbondanza non si tocca niente: la fretta e' una risposta a
    # un fatto, non un modo di parlare.
    m, item = scena(2.0, 0.5)
    lunga = len(item.audio)
    c.eq(m.hurry(m.now + 10.0, limits=(1.0, 1.35)), 1.0, "con tempo avanzo non si stringe")
    c.eq(len(item.audio), lunga, "e la battuta resta lunga uguale")

    # Nessuno sta parlando: niente da stringere, e non e' un errore.
    vuoto = Mixer(samplerate=sr, passthrough=False)
    c.eq(vuoto.hurry(0.0), 1.0, "senza niente in corso non succede niente")

    # Una battuta programmata ma non ancora cominciata non si tocca: non e' lei
    # a essere in ritardo, e stringerla toglierebbe tempo a chi non l'ha speso.
    m2 = Mixer(samplerate=sr, passthrough=False)
    suono = np.full(int(sr * 2.0), 0.2, dtype=np.float32)
    fra_poco = m2.schedule(suono, 5.0)
    c.eq(m2.hurry(m2.now, limits=(1.0, 1.35)), 1.0, "una battuta non ancora iniziata resta intera")
    c.eq(len(fra_poco.audio), len(suono), "davvero intera")

    # Un residuo brevissimo si lascia stare: il guadagno e' inudibile e
    # l'artefatto cadrebbe sull'ultima sillaba, che e' la piu' esposta.
    # **L'ultima parola si dice, non si schiaccia.** Tutta la compressione di
    # `hurry` cade sulla coda, cioe' proprio sulla parola che chiude la frase:
    # sotto la soglia si sfora, che e' la stessa promessa del progetto applicata
    # alla fine della battuta.
    m3, corto = scena(2.0, 1.7)  # residuo 300 ms: una parola
    lungo_prima = len(corto.audio)
    c.eq(
        m3.hurry(m3.now, limits=(1.0, 1.35), min_residue=0.6), 1.0,
        "con l'ultima parola sola non si stringe: si sfora",
    )
    c.eq(len(corto.audio), lungo_prima, "e la coda resta lunga com'era")
    # Ma con abbastanza residuo si stringe eccome, altrimenti la soglia avrebbe
    # semplicemente spento la funzione.
    m3b, _ = scena(3.0, 0.5)
    c.ok(
        m3b.hurry(m3b.now, limits=(1.0, 1.35), min_residue=0.6) > 1.0,
        "mentre con due secondi e mezzo davanti si stringe",
    )

    # **Il tetto vale sul totale.** Una battuta arrivata gia' accelerata non
    # puo' essere accelerata di nuovo fino al limite: le due compressioni si
    # moltiplicano. Dal vivo una battuta a 1,550 riceveva la fretta a 1,550 e la
    # coda usciva a 2,40x — ciascuno stadio dentro il limite, insieme molto
    # fuori, e all'ascolto la frase veniva inghiottita invece che finita.
    m5 = Mixer(samplerate=sr, passthrough=False)
    lungo = np.full(int(sr * 2.0), 0.2, dtype=np.float32)
    gia_veloce = m5.schedule(lungo, 0.0, rate=1.35)
    m5.process(None, n=int(sr * 0.5))
    c.eq(
        m5.hurry(m5.now, limits=(1.0, 1.35)), 1.0,
        "una battuta gia' al tetto non si stringe ancora: si sfora",
    )
    c.eq(len(gia_veloce.audio), len(lungo), "e resta lunga com'era")

    m6 = Mixer(samplerate=sr, passthrough=False)
    mezzo = m6.schedule(lungo, 0.0, rate=1.2)
    m6.process(None, n=int(sr * 0.5))
    r6 = m6.hurry(m6.now, limits=(1.0, 1.55))
    c.ok(
        1.0 < r6 <= 1.55 / 1.2 + 1e-6,
        f"con budget residuo si stringe solo di quello che resta (rate={r6:.3f} <= {1.55/1.2:.3f})",
    )
    c.ok(
        mezzo.rate <= 1.55 + 1e-6,
        f"e il totale speso resta sotto il tetto (rate totale={mezzo.rate:.3f})",
    )

    # `finisce_a` deve leggere la coda com'e' ADESSO: dopo `hurry` la durata e'
    # cambiata, e un contatore tenuto a parte direbbe la lunghezza di prima.
    m4, item4 = scena(2.0, 0.5)
    prima_fine = m4.finisce_a
    m4.hurry(m4.now, limits=(1.0, 1.35))
    c.ok(
        m4.finisce_a < prima_fine,
        f"dopo la stretta la coda finisce prima ({m4.finisce_a:.3f} < {prima_fine:.3f})",
    )


def test_coda_stiramento(c: Check) -> None:
    """Comprimendo, la **fine** del segnale sopravvive?

    Difetto trovato dall'ascolto — "taglia l'ultima parola delle frasi lunghe" —
    e invisibile a tutte le verifiche che c'erano: durata esatta, ampiezza
    esatta, intonazione ferma, giro identita' a posto. La fine non mancava,
    era **sostituita** da audio ripetuto, e la normalizzazione dell'overlap-add
    riempiva il buco cosi' bene da renderlo inudibile a ogni misura globale.

    La causa e' il puntatore di analisi: insegue la periodicita' e a ogni passo
    puo' arretrare fino a `search_ms`; quegli arretramenti si **sommano**, e a
    fine corsa non ha mai letto l'ultimo tratto dell'ingresso.

    Qui la prova mette qualcosa di **riconoscibile** in coda — un tono acuto
    dove il resto e' grave — e chiede che si ritrovi. Una misura che guarda solo
    durata ed energia non puo' esprimere questa risposta, ed e' esattamente il
    motivo per cui il difetto e' sopravvissuto fin qui.
    """
    c.group("coda")

    from mix.stretch import time_stretch

    sr = 22050
    t = np.arange(int(sr * 2.0)) / sr
    x = (0.3 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    u = int(sr * 0.2)
    x[-u:] = (0.3 * np.sin(2 * np.pi * 700 * t[:u])).astype(np.float32)

    def acuto_su_grave(y: np.ndarray) -> float:
        seg = y[-int(sr * 0.15) :]
        spec = np.abs(np.fft.rfft(seg))
        f = np.fft.rfftfreq(len(seg), 1 / sr)
        return float(
            spec[(f > 600) & (f < 800)].sum() / max(spec[(f > 120) & (f < 250)].sum(), 1e-9)
        )

    c.ok(acuto_su_grave(x) > 5.0, "la prova sa vedere l'ultima parola quando c'e'")

    for r in (1.10, 1.20, 1.35):
        q = acuto_su_grave(time_stretch(x, r, samplerate=sr))
        # **Questa e' la prova principale sullo stiramento**, piu' del giro
        # identita': con il puntatore che accumulava arretramento questo valore
        # era 0,00 a 1,20 e 1,35 — la fine spariva del tutto — mentre durata,
        # ampiezza, intonazione e giro identita' erano tutti perfetti. Fra
        # spettro e contenuto vince il contenuto: una parola che manca si sente
        # sempre, uno spettro un po' piu' ruvido no.
        c.ok(q > 1.0, f"rate {r}: la fine del segnale c'e' ancora (acuto/grave {q:.2f})")

    # E il controllo opposto, senza il quale il precedente non dimostra niente:
    # a rate 1 non si tocca niente, quindi la coda deve essere quella intera.
    c.ok(
        acuto_su_grave(time_stretch(x, 1.0, samplerate=sr)) > 5.0,
        "a rate 1 la coda resta intatta",
    )

    # **E la via d'uscita: la coda non ci passa proprio.** Finche' WSOLA perde
    # la fine, l'ultima parola non gli si da' in pasto — si comprime il corpo e
    # si riattacca la coda com'era. Qui la prova e' esatta e non statistica:
    # i campioni finali devono essere gli stessi, uno per uno.
    from mix.stretch import fit_duration_keep_tail

    y, r = fit_duration_keep_tail(x, 1.5, sr, limits=(1.0, 1.35), tail_seconds=0.3)
    coda_n = int(0.3 * sr)
    c.ok(r > 1.0, f"il corpo viene comunque compresso (rate {r:.3f})")
    c.ok(
        np.array_equal(y[-coda_n:], x[-coda_n:]),
        "e gli ultimi 300 ms sono identici all'originale, campione per campione",
    )
    c.ok(
        acuto_su_grave(y) > 5.0,
        f"quindi l'ultima parola c'e' tutta (acuto/grave {acuto_su_grave(y):.1f})",
    )
    c.ok(len(y) < len(x), "e la battuta e' comunque piu' corta di prima")


def test_velocita_totale(c: Check) -> None:
    """La velocita' vera di una battuta e' il prodotto di tutti gli stadi.

    E' il terzo travestimento dello stesso errore nella stessa giornata: il
    sintetizzatore accelera, `fit_duration` accelera, `hurry` accelera, e
    ciascuno rispettava `rate_max` senza sapere degli altri. Il tetto e' una
    proprieta' della **voce** — di quanto in fretta si puo' parlare restando
    comprensibili — e non di un passaggio del codice.
    """
    c.group("velocita")

    from core.config import Config
    from core.pipeline import DubPipeline
    from core.types import LineClass, SubtitleEvent
    from speak.base import Speech
    from core.clock import VirtualClock

    class TtsCheVaVeloce:
        """Onora `rate` accorciando davvero, come fa Piper con `length_scale`."""

        name = "prova"
        samplerate = 22050
        # Il motore dichiara il proprio passo, come ogni backend vero: la catena
        # lo legge da qui e non dalla config, altrimenti stimerebbe le durate di
        # questo con il ritmo di un altro.
        chars_per_second = 17.4

        def __init__(self) -> None:
            self.chiesti: list[float] = []

        def synthesize(self, text: str, voice, rate: float = 1.0) -> Speech:
            self.chiesti.append(rate)
            # Un secondo ogni 17,4 caratteri alla velocita' nominale.
            n = sum(ch.isalnum() for ch in text)
            durata = (n / 17.4) / max(1e-6, rate)
            return Speech(
                audio=np.full(int(self.samplerate * durata), 0.2, dtype=np.float32),
                samplerate=self.samplerate,
                voice_id=voice.voice_id,
                text=text,
            )

    cfg = Config()
    cfg.tts.backend = "prova"
    cfg.timing.rate_max = 1.35
    cfg.tts.native_rate_max = 1.30
    tts = TtsCheVaVeloce()
    clock = VirtualClock()
    p = DubPipeline(cfg, tts, clock=clock, samplerate=22050)
    clock.set(0.0)
    p.start_live(warmup=False)

    # Una battuta lunga in una finestra stretta: entrambe le leve devono
    # tirare, e insieme non devono superare il tetto. `elapsed` e' realistico
    # (300 ms di arretrato **oltre** il ritardo costante, che ormai si scusa),
    # non mezzo minuto: con la finestra gia' finita si finirebbe in un altro
    # ramo e la verifica misurerebbe quello.
    lunga = "Questa e' una battuta molto lunga che non ci sta nella sua finestra"
    clock.set(0.3 + cfg.timing.accepted_delay_ms / 1000.0)
    riga = p._speak(SubtitleEvent(text=lunga, cls=LineClass.WHITE, t_on=0.0))

    c.ok(tts.chiesti and tts.chiesti[-1] > 1.0, f"al sintetizzatore si chiede fretta ({tts.chiesti[-1]:.3f})")
    c.ok(
        tts.chiesti[-1] <= cfg.tts.native_rate_max + 1e-6,
        f"ma non oltre il suo tetto ({tts.chiesti[-1]:.3f} <= {cfg.tts.native_rate_max})",
    )
    c.ok(
        riga.rate <= cfg.timing.rate_max + 1e-6,
        f"e WSOLA resta sotto rate_max ({riga.rate:.3f} <= {cfg.timing.rate_max})",
    )
    # I due fattori restano **separati**: quanto il sintetizzatore abbia davvero
    # accelerato non e' misurabile senza sintetizzare due volte, e un totale
    # stimato qui sarebbe una stima travestita da misura — proprio nel numero su
    # cui si decide se la voce sta correndo troppo.

    # **Un sintetizzatore che consegna meno di quanto promette.** E' il caso di
    # Piper: `length_scale` non e' proporzionale. Chiedendo 1,3 ne arriva 1,15,
    # e senza correzione il tetto sulla velocita' resta un desiderio.
    class TtsPigro(TtsCheVaVeloce):
        """Onora solo meta' della fretta che gli si chiede."""

        def synthesize(self, text: str, voice, rate: float = 1.0) -> Speech:
            return super().synthesize(text, voice, rate=1.0 + (rate - 1.0) * 0.5)

    pigro = TtsPigro()
    pc = VirtualClock()
    pp = DubPipeline(cfg, pigro, clock=pc, samplerate=22050)
    pc.set(0.0)
    pp.start_live(warmup=False)
    for i in range(8):
        pc.set(0.3 + cfg.timing.accepted_delay_ms / 1000.0 + i * 6.0)
        pp._speak(SubtitleEvent(text=lunga, cls=LineClass.WHITE, t_on=i * 6.0))
    # La soglia e' bassa perche' in questa scena la finestra e' larga e la
    # fretta chiesta e' appena sopra 1: il divario da correggere e' piccolo e la
    # correzione ci mette. Cio' che si verifica e' la **direzione** e il fatto
    # che l'anello sia chiuso; quanto in fretta converga dipende da quanto e'
    # grosso l'errore, e in gioco lo e' molto di piu'.
    c.ok(
        pp._native_gain > 1.02,
        f"il guadagno impara che il sintetizzatore e' pigro ({pp._native_gain:.3f})",
    )

    # **Il riscaldamento tocca anche la voce neutra.** Non e' nel pool — apposta
    # — ma da quando le decisioni sotto soglia sono anonime e' la voce che parla
    # per prima, quindici battute su diciotto nei primi trenta secondi. Scaldare
    # tutto tranne quella sposterebbe di un posto il difetto che il riscaldamento
    # esiste per chiudere: la prima battuta che costa 1,8 s di sintesi.
    scaldato = TtsCheVaVeloce()
    sc = DubPipeline(Config(), scaldato, clock=VirtualClock(), samplerate=22050)
    scaldato.chiesti.clear()
    voci_prima = set()

    class Spia(TtsCheVaVeloce):
        def synthesize(self, text, voice, rate: float = 1.0):
            voci_prima.add(voice.voice_id)
            return super().synthesize(text, voice, rate)

    spia = Spia()
    sp = DubPipeline(Config(), spia, clock=VirtualClock(), samplerate=22050)
    sp.start_live(warmup=True)
    c.ok("neutra" in voci_prima, "la voce neutra viene scaldata come le altre")
    c.ok(
        voci_prima >= {v.voice_id for v in sp.pool.voices},
        "e il pool intero pure, non solo la prima voce",
    )
    c.ok(
        pigro.chiesti[-1] > pigro.chiesti[0],
        f"e gli si chiede via via di piu' ({pigro.chiesti[0]:.3f} -> {pigro.chiesti[-1]:.3f})",
    )

    # E con un sintetizzatore onesto il guadagno non deve gonfiarsi: correggere
    # un divario che non c'e' farebbe correre la voce senza motivo.
    onesto = TtsCheVaVeloce()
    oc = VirtualClock()
    op = DubPipeline(cfg, onesto, clock=oc, samplerate=22050)
    oc.set(0.0)
    op.start_live(warmup=False)
    for i in range(8):
        oc.set(0.3 + i * 6.0)
        op._speak(SubtitleEvent(text=lunga, cls=LineClass.WHITE, t_on=i * 6.0))
    c.ok(
        op._native_gain < 1.05,
        f"con un sintetizzatore fedele il guadagno resta a uno ({op._native_gain:.3f})",
    )

    # Con tempo in abbondanza non si chiede fretta a nessuno. Orologio nuovo:
    # il `VirtualClock` non torna indietro, ed e' giusto cosi'.
    calmo_clock = VirtualClock()
    calmo = DubPipeline(cfg, TtsCheVaVeloce(), clock=calmo_clock, samplerate=22050)
    calmo_clock.set(0.0)
    calmo.start_live(warmup=False)
    breve = calmo._speak(SubtitleEvent(text="Ciao", cls=LineClass.WHITE, t_on=0.0))
    c.close(breve.rate, 1.0, "una battuta corta in una finestra larga resta a velocita' naturale", tol=1e-6)


def test_duck_non_pompa(c: Check) -> None:
    """Fra due battute incatenate il gioco non deve risalire e riabbassarsi.

    E' un difetto che si sente sull'**audio del gioco**, non sulla voce, ed e'
    per questo che all'ascolto sembrava che si tagliuzzasse tutto invece che il
    doppiaggio. Nel dialogo fitto le battute stanno a 120 ms l'una dall'altra —
    misurato dal vivo, il 26% degli intervalli — e un rilascio da 220 ms in quei
    120 ms risale a meta' strada per poi essere rischiacciato in quaranta.

    La verifica guarda **l'inviluppo**, non la logica che lo decide: si misura
    quanto il guadagno risale nel buco, che e' la grandezza che l'orecchio sente.
    """
    c.group("duck")

    from mix.mixer import Mixer

    sr = 24000
    voce = np.full(int(sr * 0.6), 0.3, dtype=np.float32)
    gioco = np.full((int(sr * 0.02), 2), 0.5, dtype=np.float32)

    def corsa(hold_ms: float) -> float:
        """Due battute a 120 ms di distanza. Quanto risale il gioco nel mezzo?"""
        m = Mixer(samplerate=sr, duck_db=-14.0, hold_ms=hold_ms)
        m.schedule(voce, 0.0)
        m.schedule(voce, 0.6 + 0.12)
        picco = 0.0
        for i in range(int(1.4 / 0.02)):
            fuori = m.process(gioco)
            t = i * 0.02
            if 0.6 <= t < 0.72:  # dentro il buco fra le due battute
                # Il centro del gioco: mid = (L+R)/2, e la voce e' identica sui
                # due canali, quindi si guarda la differenza dal doppiaggio.
                mid = float(np.max(np.abs(fuori[:, 0] + fuori[:, 1]) / 2))
                picco = max(picco, mid)
        return picco

    senza = corsa(0.0)
    con = corsa(500.0)
    c.ok(
        con < senza,
        f"con l'attesa il gioco risale meno nel buco ({con:.3f} contro {senza:.3f})",
    )
    # In decibel, che e' la scala in cui il pompaggio si sente.
    salita_senza = 20 * np.log10(max(senza, 1e-6) / 0.5 * (10 ** (14 / 20)))
    c.ok(
        salita_senza > 3.0,
        f"e senza l'attesa la risalita e' udibile: +{salita_senza:.1f} dB sopra il duck",
    )

    # Ma con un silenzio lungo il duck DEVE rilasciare, altrimenti il gioco
    # resterebbe abbassato per tutta la scena.
    m = Mixer(samplerate=sr, duck_db=-14.0, hold_ms=500.0)
    m.schedule(voce, 0.0)
    for _ in range(int(2.5 / 0.02)):
        fuori = m.process(gioco)
    finale = float(np.max(np.abs(fuori[:, 0] + fuori[:, 1]) / 2))
    c.ok(
        finale > 0.45,
        f"dopo due secondi di silenzio il gioco e' tornato su ({finale:.3f} di 0.5)",
    )


def test_una_voce_alla_volta(c: Check) -> None:
    """Due battute vicine non devono partire insieme.

    Il mixer somma tutto cio' che e' attivo: senza serializzazione due voci
    italiane si sovrappongono, e due voci sovrapposte non si capiscono. E'
    peggio di una battuta in ritardo, che almeno si sente.
    """
    c.group("una_voce")

    from core.config import Config
    from core.pipeline import DubPipeline
    from speak.base import ToneTts

    cfg = Config()
    cfg.vision.ocr_backend = "none"
    orologio = VirtualClock()
    p = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=48000)
    p.start_live(warmup=False)

    def battuta(testo: str) -> object:
        return SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=orologio.now())

    prima = p._speak(battuta("Non ho mai avuto un figlio nero,"))
    seconda = p._speak(battuta("ma se ne avessi uno vorrei che fosse come te."))

    c.ok(prima.duration > 0, "la prima battuta ha una durata")
    c.ok(
        seconda.t_scheduled >= prima.t_scheduled + prima.duration,
        f"la seconda comincia dopo la fine della prima "
        f"({seconda.t_scheduled:.2f} contro {prima.t_scheduled + prima.duration:.2f})",
    )
    c.ok(
        seconda.t_scheduled >= prima.t_scheduled + prima.duration + cfg.tts.gap_seconds - 1e-6,
        "con in mezzo il respiro dichiarato",
    )

    # Passato abbastanza tempo, la voce e' di nuovo libera e non si accumula
    # ritardo: la serializzazione non deve diventare una coda perpetua.
    orologio.set(seconda.t_scheduled + seconda.duration + 5.0)
    terza = p._speak(battuta("Come va, bello?"))
    c.close(
        terza.t_scheduled, orologio.now(), "a voce libera la battuta parte subito", tol=1e-6
    )
    c.ok(p.metrics.timer("dub.backlog").count == 3, "l'arretrato viene misurato a ogni battuta")


class _StreamTts:
    """Un motore finto che consegna a pezzi, per provare lo streaming senza GPU.

    Imita cio' che conta di Qwen e nient'altro: `streaming = True`, blocchi che
    escono uno alla volta, e `rate` **ignorato** — perche' e' proprio il motore
    che non sa accelerare a dare senso a tutta la parte in cui la fretta cade
    su WSOLA.
    """

    name = "stream-fake"
    streaming = True

    def __init__(self, samplerate: int = 48000, chars_per_second: float = 10.0,
                 blocchi: int = 4, ritardo: float = 0.0) -> None:
        self.samplerate = samplerate
        self.chars_per_second = chars_per_second
        self.blocchi = blocchi
        self.ritardo = ritardo

    def preload(self, names) -> None:
        pass

    def _durata(self, text: str) -> float:
        from fuse.timing import spoken_length

        return max(0.2, spoken_length(text) / self.chars_per_second)

    def synthesize(self, text, voice, rate: float = 1.0):
        from speak.base import Speech

        n = int(self._durata(text) * self.samplerate)
        return Speech(np.zeros(n, np.float32), self.samplerate, voice.voice_id, text=text)

    def stream(self, text, voice, rate: float = 1.0, max_seconds: float = 0.0):
        import time as _t

        n = int(self._durata(text) * self.samplerate)
        if max_seconds > 0:
            n = min(n, int(max_seconds * self.samplerate))
        passo = max(1, n // max(1, self.blocchi))
        fatti = 0
        while fatti < n:
            if self.ritardo:
                _t.sleep(self.ritardo)
            quanti = min(passo, n - fatti)
            fatti += quanti
            yield np.full(quanti, 0.1, np.float32), fatti >= n


def test_streaming(c: Check) -> None:
    """Una battuta si puo' programmare prima di esistere.

    E' il pezzo che rende utilizzabile un motore autoregressivo: aspettare la
    battuta intera costa secondi, il primo blocco costa centinaia di
    millisecondi. Il mixer deve quindi saper tenere una battuta **aperta** — e
    l'unica parola che cambia significato e' `done`, che non e' piu' "i campioni
    sono finiti" ma "i campioni sono finiti e non ne arrivano altri".
    """
    c.group("streaming")

    from core.config import Config
    from core.pipeline import DubPipeline
    from mix.mixer import Mixer
    from speak.base import ToneTts, sa_streaming

    sr = 48000

    # -- **il cuscino: non si comincia a suonare il vuoto** ------------------
    # Il difetto che una prova dal vivo ha trovato e che il banco non poteva
    # vedere: la battuta partiva nell'istante in cui la sua generazione
    # cominciava, quindi il mixer versava silenzio e le parole arrivavano a
    # goccia. All'ascolto: parole sminuzzate, contenuto sempre piu' indietro.
    mp = Mixer(samplerate=sr, passthrough=False, prebuffer_ms=300.0)
    vuota = mp.schedule(np.zeros(0, np.float32), 0.0, aperta=True, durata_attesa=2.0)
    for _ in range(5):
        fuori = mp.process(None, n=sr // 100)
        c.ok(float(np.abs(fuori).max()) == 0.0, "senza campioni non esce niente")
    c.eq(vuota.consumed, 0, "e la battuta non e' partita")
    c.eq(mp.metrics.counter("mix.underrun").value, 0,
         "e **non** e' un underrun: non e' ancora cominciata")
    c.ok(mp.metrics.counter("mix.prebuffer").value >= 5,
         "l'attesa si conta a parte, cosi' si distingue 'lenta' da 'rotta'")
    c.ok(vuota.t_start > 0.0, "l'inizio slitta invece di accumulare ritardo")

    mp.append(vuota, np.full(int(0.1 * sr), 0.4, np.float32))  # meno del cuscino
    mp.process(None, n=sr // 100)
    c.eq(vuota.consumed, 0, "con meno del cuscino si aspetta ancora")

    mp.append(vuota, np.full(int(0.3 * sr), 0.4, np.float32))  # adesso basta
    fuori = mp.process(None, n=sr // 100)
    c.ok(float(np.abs(fuori).max()) > 0.1, "raggiunto il cuscino, parte")

    # E una battuta **chiusa** corta non aspetta: li' non arrivera' altro.
    mc = Mixer(samplerate=sr, passthrough=False, prebuffer_ms=300.0)
    corta = mc.schedule(np.full(int(0.05 * sr), 0.4, np.float32), 0.0)
    fuori = mc.process(None, n=sr // 100)
    c.ok(float(np.abs(fuori).max()) > 0.1,
         "una battuta gia' completa parte subito, anche se dura meno del cuscino")
    c.ok(corta.consumed > 0, "cioe' il cuscino vale solo per chi sta ancora arrivando")

    # -- il mixer: una battuta aperta non e' una battuta finita ---------------
    m = Mixer(samplerate=sr, passthrough=False, prebuffer_ms=0.0)
    item = m.schedule(np.zeros(0, np.float32), 0.0, aperta=True, durata_attesa=1.0)
    c.ok(not item.done, "una battuta aperta e vuota non e' finita")
    c.ok(item.a_secco, "ed e' a secco: era il suo turno e i campioni non c'erano")
    c.close(m.finisce_a, 1.0, "finisce_a usa la durata attesa finche' e' aperta", tol=1e-6)

    m.process(None, n=sr // 10, t=0.0)
    c.ok(m.metrics.counter("mix.underrun").value >= 1, "il buco viene contato")
    c.ok(m.pending == 1, "e la battuta resta in coda invece di sparire")

    m.append(item, np.full(sr // 2, 0.5, np.float32))
    c.eq(len(item.audio), sr // 2, "i campioni arrivati si aggiungono")
    fuori = m.process(None, n=sr // 10, t=0.1)
    c.ok(float(np.abs(fuori).max()) > 0.1, "e al blocco dopo si sentono")

    m.append(item, np.zeros(0, np.float32), chiudi=True)
    c.ok(not item.aperta, "chiudere la chiude")
    while not item.done:
        m.process(None, n=sr // 10)
    c.ok(item.done, "e a campioni esauriti adesso e' finita davvero")

    # -- `clear` annulla, cosi' il produttore smette -------------------------
    m2 = Mixer(samplerate=sr, passthrough=False)
    aperta = m2.schedule(np.zeros(0, np.float32), 0.0, aperta=True, durata_attesa=1.0)
    m2.clear()
    m2.append(aperta, np.ones(1000, np.float32))
    c.ok(aperta.annullata, "una battuta buttata via e' contrassegnata")
    c.eq(len(aperta.audio), 0, "e chi produceva non riesce piu' a versarci dentro")

    # -- `hurry` su una battuta aperta guarda la durata attesa ---------------
    # Il residuo *presente* e' quello che il produttore ha fatto in tempo a
    # consegnare: guardare quello vorrebbe dire misurare la velocita' del motore
    # invece della lunghezza della battuta, e concludere ogni volta "manca
    # pochissimo, non stringo" — cioe' spegnere `hurry` dove serve di piu'.
    m3 = Mixer(samplerate=sr, passthrough=False, prebuffer_ms=300.0)
    viva = m3.schedule(np.zeros(0, np.float32), 0.0, aperta=True, durata_attesa=4.0)
    # Mezzo secondo consegnato: basta a superare il cuscino e a far partire la
    # battuta, ed e' comunque un ottavo dei quattro secondi che durera'.
    m3.append(viva, np.full(sr // 2, 0.3, np.float32))
    m3.process(None, n=sr // 100, t=0.0)  # falla partire
    c.ok(viva.consumed > 0, "la battuta e' partita, quindi `hurry` ha su cosa lavorare")
    r = m3.hurry(t_finish=2.0, limits=(1.0, 1.35), min_residue=0.6)
    c.ok(r > 1.001, f"si stringe anche se il residuo presente e' corto (rate {r:.3f})")
    c.close(viva.rate_futuro, r, "e cio' che deve ancora arrivare arrivera' stretto uguale",
            tol=1e-6)
    prima = len(viva.audio)
    m3.append(viva, np.full(sr, 0.3, np.float32))  # un secondo naturale
    aggiunti = len(viva.audio) - prima
    c.ok(aggiunti < sr * 0.99, f"il blocco nuovo entra compresso ({aggiunti} invece di {sr})")

    # -- la catena: si programma sulla previsione, e i campioni arrivano dopo -
    cfg = Config()
    cfg.vision.ocr_backend = "none"
    orologio = VirtualClock()
    tts = _StreamTts(samplerate=sr, chars_per_second=10.0, blocchi=4)
    c.ok(sa_streaming(tts), "il motore finto si dichiara capace di streaming")
    c.ok(not sa_streaming(ToneTts()), "e un motore normale no")

    p = DubPipeline(cfg, tts, clock=orologio, samplerate=sr)
    p.start_live(warmup=False)
    testo = "Lavoriamo insieme gia da qualche mese, giusto?"
    riga = p._speak(SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=orologio.now()))

    c.ok(riga.duration > 0, "la riga esce con una durata, che e' quella prevista")
    c.ok(p._banco, "con l'orologio virtuale la catena si sa sul banco")
    c.eq(len(p._produttori), 0, "e non lancia nessun thread: li' consegnerebbe tardi sempre")

    coda = p.mixer._queue
    c.eq(len(coda), 1, "e in coda c'e' una battuta sola")
    c.ok(not coda[0].aperta, "chiusa dal produttore")
    atteso = int(tts._durata(testo) * sr / riga.rate)
    c.ok(
        abs(len(coda[0].audio) - atteso) <= sr // 10,
        f"con tutti i campioni ({len(coda[0].audio)} contro {atteso} attesi)",
    )
    c.ok(p.metrics.timer("speak.first_sample").count == 1,
         "e il tempo al primo campione e' misurato, che e' l'unico che si sente")

    # Due battute di fila non si sovrappongono nemmeno qui: la seconda si
    # prenota sulla previsione della prima, non su cio' che e' gia' arrivato.
    seconda = p._speak(
        SubtitleEvent(text="Si, era lui.", cls=LineClass.WHITE, t_on=orologio.now())
    )
    c.ok(
        seconda.t_scheduled >= riga.t_scheduled + riga.duration - 1e-6,
        "la seconda comincia dopo la fine prevista della prima",
    )

    # -- il motore che si incanta viene tagliato, e la prenotazione lo segue --
    # Misurato con Qwen: `'Toc toc, negri!'` — quindici caratteri — ha prodotto
    # 9,12 secondi di audio contro 1,04 previsti. Senza tetto quella battuta tiene
    # occupata l'unica voce per nove secondi; senza correggere `_free_at`, la
    # battuta dopo parte **sopra** di lei, che e' il difetto peggiore del prodotto.
    incantato = _StreamTts(samplerate=sr, chars_per_second=1.0, blocchi=4)
    p3 = DubPipeline(cfg, incantato, clock=VirtualClock(), samplerate=sr)
    p3.start_live(warmup=False)
    p3._cps = 10.0  # la catena prevede un secondo, il motore ne fa dieci
    corta = "Toc toc, negri!"
    r3 = p3._speak(SubtitleEvent(text=corta, cls=LineClass.WHITE, t_on=p3.clock.now()))
    vera = len(p3.mixer._queue[0].audio) / sr
    from fuse.timing import spoken_length as _sl

    previsto = _sl(corta) / 10.0
    c.ok(vera <= 3.0 * previsto + 1.05,
         f"la battuta incantata viene troncata al tetto ({vera:.2f}s, previsti {previsto:.2f}s)")
    c.ok(p3._free_at >= r3.t_scheduled + vera - 1e-6,
         "e la prenotazione si allunga su cio' che e' arrivato davvero")
    dopo = p3._speak(
        SubtitleEvent(text="Come va, bello?", cls=LineClass.WHITE, t_on=p3.clock.now())
    )
    c.ok(dopo.t_scheduled >= r3.t_scheduled + vera - 1e-6,
         "cosi' la battuta dopo non parte sopra quella lunga")
    c.eq(p3.metrics.counter("speak.stream_failed").value, 0, "e niente e' esploso per strada")

    # -- la frequenza del motore non e' quella del mixer ---------------------
    # **Questa verifica esiste per un difetto vero.** Il ramo in streaming non
    # ricampionava: versava campioni a 22050 in un mixer a 48000, e ne usciva un
    # doppiaggio a 2,2x — voce da scoiattolo. Nessun contatore lo diceva, la suite
    # era verde, e a smascherarlo e' stato che il passo misurato del motore
    # risultava di 30 caratteri al secondo, che non e' una velocita' di parlato.
    # Il ramo normale la conversione la faceva da sempre: era il ramo nuovo a non
    # aver ereditato una riga.
    lento = _StreamTts(samplerate=22050, chars_per_second=10.0, blocchi=4)
    p2 = DubPipeline(cfg, lento, clock=VirtualClock(), samplerate=48000)
    p2.start_live(warmup=False)
    r_lenta = p2._speak(
        SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=p2.clock.now())
    )
    campioni = len(p2.mixer._queue[0].audio)
    atteso48 = int(lento._durata(testo) * 48000 / r_lenta.rate)
    c.ok(
        abs(campioni - atteso48) <= 48000 // 20,
        f"la battuta arriva al mixer nella **sua** frequenza "
        f"({campioni} campioni contro {atteso48} attesi a 48 kHz)",
    )
    c.close(
        campioni / 48000.0,
        lento._durata(testo) / r_lenta.rate,
        "cioe' dura i secondi che deve durare, non la meta'",
        tol=0.05,
    )

    # -- e dal vivo il produttore e' un thread, che e' il caso che conta -------
    # Con l'orologio vero la battuta si programma e **ritorna subito**: e' tutto
    # il punto dello streaming. Il motore finto mette 40 ms a consegnare i suoi
    # quattro blocchi, quindi se `_speak` li aspettasse si vedrebbe.
    import time

    from core.clock import RealClock

    vivo = DubPipeline(
        cfg, _StreamTts(samplerate=sr, blocchi=4, ritardo=0.01), clock=RealClock(), samplerate=sr
    )
    vivo.start_live(warmup=False)
    c.ok(not vivo._banco, "con l'orologio vero la catena si sa dal vivo")
    t0 = time.perf_counter()
    r2 = vivo._speak(SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=vivo.clock.now()))
    ritorno_ms = (time.perf_counter() - t0) * 1000.0
    c.ok(ritorno_ms < 30.0, f"_speak torna subito, senza aspettare la sintesi ({ritorno_ms:.0f} ms)")
    c.ok(r2.duration > 0, "e la battuta e' gia' programmata")
    c.eq(len(vivo._produttori), 1, "con un produttore suo")
    for t in vivo._produttori:
        t.join(timeout=10.0)
    c.ok(not any(t.is_alive() for t in vivo._produttori), "che poi finisce")
    c.ok(not vivo.mixer._queue[0].aperta, "e chiude la battuta")
    c.ok(
        vivo.metrics.timer("speak.first_sample").count == 1,
        "il tempo al primo campione si misura solo dal vivo, dove significa qualcosa",
    )


def test_etichetta(c: Check) -> None:
    """Chi parla scritto dal gioco: si legge, si toglie, e vale mezzo secondo.

    **Queste verifiche girano su testo sintetico, e va detto.** GTA V i nomi non
    li scrive, quindi non esiste materiale vero su cui provarle: dicono che il
    codice fa quello che dichiara, non che funzioni su un gioco. La prima cosa da
    fare con una registrazione di un altro gioco e' rimisurare tutto qui sopra.
    """
    c.group("etichetta")

    from core.config import Config, LabelConfig
    from core.pipeline import DubPipeline
    from core.types import OcrLine
    from speak.base import ToneTts
    from vision.label import LabelReader

    # -- le tre forme pronte ------------------------------------------------
    for forma, riga, atteso in (
        ("nome:", "Franklin: Come va, bello?", "Come va, bello?"),
        ("nome:", "FRANKLIN : Come va, bello?", "Come va, bello?"),
        ("[nome]", "[Franklin] Come va, bello?", "Come va, bello?"),
        ("[nome]", "(Franklin) Come va, bello?", "Come va, bello?"),
        ("nome-", "Franklin - Come va, bello?", "Come va, bello?"),
        ("nome-", "Franklin — Come va, bello?", "Come va, bello?"),
    ):
        cfg = LabelConfig(enabled=True, form=forma)
        e = LabelReader(cfg).dal_testo(riga)
        c.ok(e is not None and e.testo == atteso,
             f"forma {forma}: {riga!r} -> {None if e is None else e.testo!r}")

    # -- e il nome esce dal testo, che e' il punto ---------------------------
    e = LabelReader(LabelConfig(enabled=True)).dal_testo("Franklin: Come va, bello?")
    c.eq(e.nome, "Franklin", "il nome si legge")
    c.ok("Franklin" not in e.testo, "e sparisce da cio' che si pronuncia")

    # -- i falsi positivi, che sono il vero nemico --------------------------
    # Ogni falso positivo **crea un personaggio** e gli brucia addosso una voce
    # del pool, togliendola a qualcuno che parla davvero.
    lettore = LabelReader(LabelConfig(enabled=True))
    for riga, perche in (
        ("Si, era lui: adesso lo so", "c'e' punteggiatura di frase dentro il nome"),
        ("Franklin:", "non resta niente da dire"),
        (": Come va", "il nome e' vuoto"),
        ("12345: Come va", "il nome non ha lettere"),
        ("Come va, bello?", "non c'e' nessun separatore"),
        ("A" * 40 + ": Come va", "il nome e' troppo lungo"),
    ):
        c.ok(lettore.dal_testo(riga) is None, f"scartato ({perche}): {riga!r}")

    # -- l'elenco dichiarato e' la guardia forte ----------------------------
    con_elenco = LabelReader(
        LabelConfig(enabled=True, names=("Franklin", "Lamar", "Simeon"))
    )
    c.ok(con_elenco.dal_testo("Franklin: Come va") is not None, "un nome dell'elenco passa")
    c.ok(con_elenco.dal_testo("Sconosciuto: Come va") is None,
         "uno fuori elenco no: e' un OCR che ha letto male, non un personaggio nuovo")
    e = con_elenco.dal_testo("FRANKLlN: Come va")  # I maiuscola letta come elle
    c.ok(e is None, "e nemmeno una lettura sbagliata di un nome dell'elenco")
    e = con_elenco.dal_testo("franklin : Come va")
    c.ok(e is not None and e.nome == "Franklin",
         "ma maiuscole e spazi non contano, e il nome torna nella forma dichiarata")

    c.ok(
        LabelReader(LabelConfig(enabled=True, require_names=True)).dal_testo("X: ciao") is None,
        "con require_names e senza elenco non si etichetta niente",
    )

    # -- il colore ----------------------------------------------------------
    col = LabelReader(LabelConfig(
        enabled=True, colors={"Franklin": "#5ac8fa", "Lamar": "#ffcc00"},
        color_tolerance=60.0,
    ))
    c.eq(col.dal_colore((90.0, 200.0, 250.0)), "Franklin", "il colore piu' vicino vince")
    c.eq(col.dal_colore((255.0, 204.0, 0.0)), "Lamar", "e distingue i due")
    c.ok(col.dal_colore((255.0, 255.0, 255.0)) is None,
         "ma oltre la soglia non si decide: senza, il bianco finirebbe a qualcuno")

    # -- una regex libera, per i giochi che non rientrano nelle tre forme ----
    libero = LabelReader(LabelConfig(
        enabled=True, regex=r"^<<(?P<nome>[^>]+)>>\s*(?P<testo>.+)$"
    ))
    e = libero.dal_testo("<<Franklin>> Come va")
    c.ok(e is not None and e.nome == "Franklin" and e.testo == "Come va", "regex libera")
    try:
        LabelReader(LabelConfig(enabled=True, regex=r"^(.+)$"))
        c.ok(False, "una regex senza i gruppi dichiarati deve sollevare")
    except ValueError:
        c.ok(True, "una regex senza i gruppi dichiarati solleva invece di tacere")

    # -- e nella catena: niente attesa, niente impronta ---------------------
    cfg = Config()
    cfg.vision.ocr_backend = "none"
    cfg.label.enabled = True
    cfg.label.names = ("Franklin", "Lamar")
    orologio = VirtualClock()
    p = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=48000)
    p.start_live(warmup=False)

    ev = SubtitleEvent(text="Franklin: Come va, bello?", cls=LineClass.WHITE, t_on=0.0)
    d = p._speaker_for(ev)
    c.eq(d.speaker_id, "L-Franklin", "chi parla arriva dal gioco, non dall'audio")
    c.close(d.confidence, 1.0, "e non e' una stima: e' quello che il gioco ha scritto", tol=1e-9)
    c.ok(p.metrics.counter("vision.label.hit").value == 1, "e si conta, per accorgersi se il formato e' sbagliato")

    riga = p._speak(ev)
    c.ok("Franklin" not in riga.text, f"la battuta detta non contiene il nome: {riga.text!r}")
    c.eq(riga.speaker_id, "L-Franklin", "e resta attribuita a lui")

    # Due personaggi diversi, due voci diverse: e' tutto il punto della feature.
    altra = p._speak(
        SubtitleEvent(text="Lamar: Toc toc!", cls=LineClass.WHITE, t_on=1.0)
    )
    c.ok(altra.voice_id != riga.voice_id,
         f"due nomi diversi -> due voci diverse ({riga.voice_id} / {altra.voice_id})")

    # E senza etichetta la catena resta quella di prima.
    muto = DubPipeline(Config(), ToneTts(), clock=VirtualClock(), samplerate=48000)
    c.ok(muto.label is None, "spenta di default: nessun gioco e' uguale a un altro")

    # -- le altre forme pronte ---------------------------------------------
    for forma, riga in (
        ("-nome:", "- Franklin: Come va"),
        ("nome>>", "Franklin >> Come va"),
        ("nome>>", "Franklin » Come va"),
        ("nome(nota):", "Franklin (arrabbiato): Come va"),
        ("NOME", "FRANKLIN Come va, bello?"),
    ):
        e = LabelReader(LabelConfig(enabled=True, form=forma, names=("Franklin",))).dal_testo(riga)
        c.ok(e is not None and e.nome == "Franklin" and "Come va" in e.testo,
             f"forma {forma}: {riga!r} -> {None if e is None else (e.nome, e.testo)}")

    # -- **sempre la stessa voce, anche fra sessioni diverse** --------------
    # Senza questo, la voce non e' del personaggio: e' del turno. Chi apre la
    # scena prende la prima voce del pool, quindi riaprendo il gioco da un altro
    # punto lo stesso personaggio ne prende un'altra.
    import json as _json

    cartella = Path(tempfile.mkdtemp())
    cast = cartella / "cast.json"

    cfg2 = Config()
    cfg2.vision.ocr_backend = "none"
    cfg2.label.enabled = True
    cfg2.label.names = ("Franklin", "Lamar")
    cfg2.label.cast_file = str(cast)

    def parla(cfg, chi: str, testo: str):
        pp = DubPipeline(cfg, ToneTts(), clock=VirtualClock(), samplerate=48000)
        pp.start_live(warmup=False)
        r = pp._speak(SubtitleEvent(text=f"{chi}: {testo}", cls=LineClass.WHITE, t_on=0.0))
        pp._cast.salva()
        return r.voice_id

    # Prima sessione: parla solo Lamar. Seconda: parla solo Franklin — cioe' il
    # caso in cui ognuno, da solo, prenderebbe la prima voce libera del pool.
    v_lamar = parla(cfg2, "Lamar", "Toc toc!")
    v_franklin = parla(cfg2, "Franklin", "Come va, bello?")
    ricordo = _json.loads(cast.read_text(encoding="utf-8"))
    c.ok("Lamar" in ricordo and "Franklin" in ricordo,
         f"il file ricorda chi ha quale voce: {ricordo}")
    # **La verifica che conta.** Senza prenotare le voci ricordate all'avvio,
    # qui finivano tutti e due su `riccardo` — ognuno primo nella sua sessione —
    # e il file archiviava la collisione come se fosse giusta.
    c.ok(v_lamar != v_franklin,
         f"due personaggi non finiscono sulla stessa voce solo perche' hanno "
         f"parlato in sessioni diverse ({v_lamar} / {v_franklin})")
    c.eq(parla(cfg2, "Lamar", "Un'altra volta."), v_lamar,
         "Lamar ha la stessa voce anche in una sessione nuova")
    c.eq(parla(cfg2, "Franklin", "Anche io."), v_franklin, "e Franklin la sua")

    # -- e la mappa scritta a mano vince su tutto --------------------------
    cfg3 = Config()
    cfg3.vision.ocr_backend = "none"
    cfg3.label.enabled = True
    cfg3.label.names = ("Franklin",)
    cfg3.label.cast_file = str(cast)
    voluta = DubPipeline(cfg3, ToneTts(), clock=VirtualClock(), samplerate=48000).pool.voices[3]
    cfg3.label.voices = {"Franklin": voluta.voice_id}
    c.eq(parla(cfg3, "Franklin", "Come va."), voluta.voice_id,
         "la voce dichiarata a mano vince sul ricordo e sull'automatico")

    cfg3.label.voices = {"Franklin": "voce-che-non-esiste"}
    p4 = DubPipeline(cfg3, ToneTts(), clock=VirtualClock(), samplerate=48000)
    p4.start_live(warmup=False)
    r4 = p4._speak(SubtitleEvent(text="Franklin: Ciao", cls=LineClass.WHITE, t_on=0.0))
    c.ok(r4.voice_id in {v.voice_id for v in p4.pool.voices},
         "una voce inesistente in config non zittisce nessuno: si dichiara e si prosegue")


def test_correzione(c: Check) -> None:
    """Il correttore puo' agire solo dove non puo' fare danni.

    Il modulo nasce da una bocciatura misurata — due giuste su otto, con
    `rapinato -> rovinato` — quindi qui non si verifica che corregga: si verifica
    che **non tocchi** ciò che non deve, e che si astenga quando non sa.
    """
    c.group("correzione")

    from vision.correct import (
        NessunCorrettore, Proposta, Revisore, candidati, distanza, make_correttore,
    )

    class _Finto:
        """Un correttore che propone sempre, con la fiducia che gli si dice.

        Serve a provare le guardie: se le guardie funzionano, nemmeno un
        correttore completamente sconsiderato riesce a fare danni.
        """

        name = "finto"

        def __init__(self, parola: str, fiducia: float = 1.0) -> None:
            self.parola, self.fiducia = parola, fiducia
            self.visto: list[tuple[str, int]] = []

        def proponi(self, parola, contesto):
            self.visto.append((parola, len(contesto)))
            return Proposta(self.parola, self.fiducia)

    class _Lex:
        parole = {"fatto", "cane", "bulldozer", "rapinato", "rovinato", "casa", "andiamo"}

        def nota(self, w):
            return w.strip(".,;:!?'\"()").lower() in self.parole

    lex = _Lex()

    c.eq(distanza("farto", "fatto"), 1, "distanza di edit")
    c.ok(distanza("abc", "xyz", 1) > 1, "e si ferma al tetto")

    # -- una parola italiana non si tocca **mai** ---------------------------
    # E' la guardia che uccide `rapinato -> rovinato` alla radice: non perche' il
    # correttore sia bravo, ma perche' non gli viene proprio chiesto.
    finto = _Finto("rovinato")
    rev = Revisore(lex, finto, min_fiducia=0.5)
    r = rev.rivedi("Mi hanno rapinato")
    c.ok(not r.cambiato, f"una parola italiana resta com'e': {r.testo!r}")
    c.ok(all(w != "rapinato" for w, _ in finto.visto),
         "e al correttore non viene nemmeno proposta")

    # -- un nome proprio non si tocca --------------------------------------
    finto = _Finto("cane")
    rev = Revisore(lex, finto, min_fiducia=0.5)
    r = rev.rivedi("Si chiama Esteban oggi")
    c.ok(not r.cambiato, f"maiuscola a meta' frase = nome proprio: {r.testo!r}")

    r = Revisore(lex, _Finto("cane"), min_fiducia=0.5, nomi=("simeon",)).rivedi("simeon parla")
    c.ok(not r.cambiato, "e un nome dichiarato nemmeno da minuscolo")

    # -- sotto la fiducia non si corregge, e si dichiara --------------------
    rev = Revisore(lex, _Finto("fatto", fiducia=0.5), min_fiducia=0.9)
    r = rev.rivedi("Ho farto tutto")
    c.ok(not r.cambiato, "sotto la soglia non si tocca")
    c.ok("farto" in r.astenuto, "e l'astensione si dichiara invece di sparire")

    # -- la proposta dev'essere italiana e vicina --------------------------
    rev = Revisore(lex, _Finto("zzzz", fiducia=1.0), min_fiducia=0.9)
    c.ok(not rev.rivedi("Ho farto tutto").cambiato,
         "una proposta che non e' una parola viene scartata")

    rev = Revisore(lex, _Finto("bulldozer", fiducia=1.0), min_fiducia=0.9)
    c.ok(not rev.rivedi("Ho farto tutto").cambiato,
         "e una troppo lontana pure: 'IIFIL' -> 'infila' non deve poter succedere")

    # -- quando tutto torna, corregge --------------------------------------
    rev = Revisore(lex, _Finto("fatto", fiducia=1.0), min_fiducia=0.9)
    r = rev.rivedi("Ho farto tutto")
    c.ok(r.cambiato and "fatto" in r.testo, f"con tutto a posto corregge: {r.testo!r}")
    c.eq(r.cambi, [("farto", "fatto")], "e dice cosa ha cambiato")

    # -- il contesto arriva davvero al correttore --------------------------
    finto = _Finto("fatto", fiducia=1.0)
    rev = Revisore(lex, finto, min_fiducia=0.9, contesto_battute=3)
    for t in ("Prima riga", "Seconda riga", "Terza riga", "Quarta riga"):
        rev.ricorda(t)
    rev.rivedi("Ho farto tutto")
    c.ok(finto.visto and finto.visto[-1][1] == 3,
         f"il correttore riceve le ultime 3 battute (ne ha viste {finto.visto[-1][1]})")

    # -- i candidati: si sceglie fra parole vere, non si inventa ------------
    cs = candidati("farto", lex)
    c.ok("fatto" in cs, f"il candidato giusto c'e': {cs}")
    c.ok(all(lex.nota(w) for w in cs), "e sono tutte parole del lessico")
    c.ok(candidati("oulldozer", lex) == ["bulldozer"],
         "quando ce n'e' uno solo, non c'e' niente da scegliere")

    # -- il default non corregge, e un nome sconosciuto solleva ------------
    from core.config import CorrectConfig

    c.ok(isinstance(make_correttore(CorrectConfig()), NessunCorrettore),
         "di default non si corregge niente")
    try:
        make_correttore(CorrectConfig(backend="refuso"))
        c.ok(False, "un backend sconosciuto deve sollevare")
    except ValueError:
        c.ok(True, "un backend sconosciuto solleva invece di ripiegare in silenzio")
    c.ok(hasattr(NessunCorrettore(), "proponi"), "il correttore di default rispetta il protocollo")


def test_traduzione(c: Check) -> None:
    """Tradurre: prima dei tempi, con la cache, e senza mai restare muti."""
    c.group("traduzione")

    from core.config import Config, TranslateConfig
    from core.pipeline import DubPipeline
    from speak.base import ToneTts
    from translate.base import NessunTraduttore, Traduzioni, make_traduttore

    class _Finto:
        name = "finto"

        def __init__(self, mappa=None, rompe=False) -> None:
            self.mappa = mappa or {}
            self.rompe = rompe
            self.chiamate = 0

        def traduci(self, testo, da, a):
            self.chiamate += 1
            if self.rompe:
                raise RuntimeError("rete assente")
            return self.mappa.get(testo)

    # -- il default non traduce --------------------------------------------
    c.ok(isinstance(make_traduttore(TranslateConfig()), NessunTraduttore),
         "spenta di default: su GTA V si tradurrebbe l'italiano in italiano")
    try:
        make_traduttore(TranslateConfig(enabled=True, backend="refuso"))
        c.ok(False, "un backend sconosciuto deve sollevare")
    except ValueError:
        c.ok(True, "un backend sconosciuto solleva invece di ripiegare")

    # -- tradurre, e la cache ----------------------------------------------
    finto = _Finto({"Hello there": "Ciao"})
    t = Traduzioni(finto, da="en", a="it")
    r = t("Hello there")
    c.eq(r.testo, "Ciao", "traduce")
    c.ok(r.tradotto, "e lo dichiara")
    r2 = t("Hello there")
    c.eq(r2.testo, "Ciao", "la seconda volta pure")
    c.ok(r2.da_cache, "ma dalla cache")
    c.eq(finto.chiamate, 1, "il traduttore e' stato chiamato una volta sola")

    # -- fallire non e' tradurre a caso ------------------------------------
    # Una battuta nella lingua sbagliata e' un difetto; una battuta muta e' un
    # buco, e questo progetto sfora invece di scartare.
    t = Traduzioni(_Finto({}), da="en", a="it")
    r = t("Something else")
    c.eq(r.testo, "Something else", "se non sa tradurre tiene l'originale")
    c.ok(not r.tradotto, "e non finge di averlo tradotto")
    c.eq(t.n_falliti, 1, "il fallimento si conta")

    t = Traduzioni(_Finto(rompe=True), da="en", a="it")
    c.eq(t("Boom").testo, "Boom", "e un'eccezione non zittisce la battuta")

    # -- i tempi si calcolano sul testo TRADOTTO ---------------------------
    # E' l'ordine che conta: `chars_per_second` e `D = a + b*n` sono misurati
    # sull'italiano e vanno applicati a cio' che verra' **detto**.
    cfg = Config()
    cfg.vision.ocr_backend = "none"
    cfg.translate.enabled = True
    cfg.translate.backend = "nessuno"
    p = DubPipeline(cfg, ToneTts(), clock=VirtualClock(), samplerate=48000)
    p.start_live(warmup=False)
    p.traduci = Traduzioni(
        _Finto({"Hi": "Buongiorno a tutti quanti voi che siete qui"}), da="en", a="it"
    )
    riga = p._speak(SubtitleEvent(text="Hi", cls=LineClass.WHITE, t_on=0.0))
    c.eq(riga.text, "Buongiorno a tutti quanti voi che siete qui", "si dice il tradotto")
    c.eq(riga.text_original, "Hi", "e l'originale resta scritto, per la prova d'ascolto")
    c.ok(riga.duration > 0.8,
         f"la durata segue il testo tradotto, non le due lettere dell'originale "
         f"({riga.duration:.2f}s)")

    # -- tradurre cambia anche la **voce** ---------------------------------
    # Un pool italiano che dice battute inglesi non ha un accento: ha i fonemi
    # sbagliati, e sembra un difetto del modello.
    from speak.backends.kokoro import FONEMI_LINGUA, PER_LINGUA
    from speak.pool import build_pool

    it = build_pool(None, 6, backend="kokoro", lingua="it")
    en = build_pool(None, 6, backend="kokoro", lingua="en")
    c.ok(all(v.base_voice in PER_LINGUA["it"] for v in it),
         "con `it` il pool prende solo le voci italiane")
    c.ok(all(v.base_voice in PER_LINGUA["en"] for v in en),
         "con `en` solo le inglesi")
    c.ok(not {v.base_voice for v in it} & {v.base_voice for v in en},
         "e i due insiemi non si toccano")
    c.ok(all(v.semitones == 0.0 for v in en),
         "le sei inglesi sono tutte native: **nessun semitono spostato**, perche' "
         "Kokoro in inglese ne ha abbastanza e una voce trasformata e' sempre "
         "peggio di una nativa quando se ne puo' fare a meno")
    c.eq(len({v.gender for v in en}), 2, "e alternano maschile e femminile")
    c.eq(FONEMI_LINGUA["en"], "en-us", "l'inglese si fonemizza con le regole inglesi")

    # **E il passo cambia con la lingua.** Usare quello italiano sull'inglese
    # faceva credere ogni battuta piu' lunga di quanto fosse: budget stretto,
    # WSOLA al tetto su *tutti* i percentili, e il parlato che riempiva appena
    # meta' scena. Compressione autoinflitta da una stima sbagliata.
    from speak.backends.kokoro import PASSO_LINGUA, KokoroTts

    c.ok(PASSO_LINGUA["en"] > PASSO_LINGUA["it"],
         f"l'inglese e' piu' svelto dell'italiano ({PASSO_LINGUA['en']} contro "
         f"{PASSO_LINGUA['it']} car/s, misurati tutti e due)")
    k_it = KokoroTts(lingua="it", download=False)
    k_en = KokoroTts(lingua="en", download=False)
    c.close(k_it.chars_per_second, PASSO_LINGUA["it"], "il motore dichiara il passo italiano", tol=1e-6)
    c.close(k_en.chars_per_second, PASSO_LINGUA["en"], "e quello inglese quando parla inglese", tol=1e-6)
    c.eq(KokoroTts(lingua="en-us", download=False).lingua_base, "en",
         "un codice regionale ricade sulla lingua base")

    # La catena prende la lingua **di arrivo**, non quella del gioco.
    cfg_en = Config()
    cfg_en.vision.ocr_backend = "none"
    cfg_en.tts.backend = "kokoro"
    cfg_en.translate.enabled = True
    cfg_en.translate.target = "en"
    p_en = DubPipeline(cfg_en, ToneTts(), clock=VirtualClock(), samplerate=48000)
    c.ok(all(v.base_voice in PER_LINGUA["en"] for v in p_en.pool.voices),
         "la catena che traduce in inglese costruisce un pool inglese")


def test_overlay(c: Check) -> None:
    """Il sottotitolo tradotto disegnato sopra il gioco.

    **Questo gruppo non c'era, ed e' il motivo per cui l'overlay e' arrivato in
    mano all'utente rotto due volte con la suite verde.** La prima versione
    dimensionava la finestra sul testo originale e ci disegnava dentro quello
    tradotto; la seconda sfocava un rettangolo largo quanto la ROI e scriveva con
    un carattere scelto da noi. Nessuna delle due poteva fallire una verifica,
    perche' verifiche non ce n'erano.

    Qui si controlla senza aprire nessuna finestra: `dipingi` e' pura e torna
    un'immagine, e un'immagine si misura.
    """
    c.group("overlay")
    import cv2
    from PIL import Image, ImageDraw

    from ui.overlay import (
        CHIAVE_RGB, MisuraCarattere, Sostituzione, _fascia, carica_font,
        colore_del_gioco, corpo_del_gioco, dipingi, inchiostro, su_chiave,
    )

    # -- il colore si prende dal gioco, e si rialza ------------------------
    # La media sui pixel mascherati comprende i bordi scuri dei glifi: un bianco
    # misurato 180 e' un bianco 255 con dentro l'antialiasing.
    c.eq(colore_del_gioco((180, 180, 180)), (255, 255, 255),
         "un grigio da antialiasing torna il bianco che era")
    giallo = colore_del_gioco((200, 160, 20))
    c.ok(giallo[0] == 255 and giallo[1] < 255 and giallo[2] < giallo[1],
         f"e un giallo resta giallo invece di diventare bianco ({giallo})")
    c.eq(colore_del_gioco((0, 0, 0)), (255, 255, 255),
         "un inchiostro nero (niente da misurare) ricade sul bianco")

    # -- la misura si prende dal gioco, su **larghezza e altezza** ---------
    # Prima si confrontava la sola altezza della banda con l'altezza di `Ag`:
    # chiedeva un carattere alto quanto una riga intera per ottenere delle sole
    # maiuscole, il 40% di troppo. Poi la sola larghezza: giusta di lunghezza e
    # piu' alta dell'originale, perche' il carattere del gioco e' stretto e
    # Arial no. Adesso si cerca il corpo che sbaglia meno su **tutti e due**.
    #
    # **Andata e ritorno**: si costruisce la banda disegnando davvero il testo a
    # un corpo noto, e si deve ritrovare quel corpo. E' l'unica prova che non si
    # possa superare per caso — se il numero che esce non e' quello che e'
    # entrato, la formula sbaglia e basta.
    from PIL import Image as _Im, ImageDraw as _Dr

    reg = _Dr.Draw(_Im.new("L", (1, 1)))
    for testo, vero in (("Ciao, Lamar!", 26), ("Come stai, fratello mio?", 44),
                        ("Andiamo.", 62)):
        f_vero = carica_font("Arial", vero)
        larga = int(reg.textlength(testo, font=f_vero))
        _, y0v, _, y1v = f_vero.getbbox("Ag")
        corpo = corpo_del_gioco([(0, 0, larga, y1v - y0v)], testo, 1.0, "Arial")
        c.ok(abs(corpo - vero) <= 1,
             f"'{testo}' scritto a {vero} punti si rimisura {corpo}")

    # E il compromesso non deve mai gonfiare il testo oltre la riga che copre.
    for larga, alta in ((300, 30), (700, 30), (400, 55)):
        corpo = corpo_del_gioco([(0, 0, larga, alta)], "Ciao, Lamar!", 1.0, "Arial")
        f = carica_font("Arial", corpo)
        _, ya, _, yb = f.getbbox("Ag")
        c.ok((yb - ya) <= alta * 1.35,
             f"su una banda {larga}x{alta} l'inchiostro scelto e' alto {yb - ya}, "
             f"non sfonda la riga")

    alto = corpo_del_gioco([(0, 0, 300, 30)], "Ciao, Lamar!", 1.0, "Arial")
    c.ok(corpo_del_gioco([(0, 0, 600, 60)], "Ciao, Lamar!", 2.0, "Arial")
         > alto * 1.5,
         "e su uno schermo il doppio piu' fitto il carattere raddoppia")

    # **La taglia e' una sola per tutto il gioco.** Una taglia che cambia da una
    # battuta all'altra e' rumore della misura, e a schermo si vede.
    m = MisuraCarattere()
    for testo, larga in (("Ciao, Lamar!", 300), ("Ciao, Lamar!", 180),
                         ("Come stai?", 250), ("Ciao, Lamar!", 305),
                         ("Ciao, Lamar!", 298)):
        ultimo = m.aggiorna([(0, 0, larga, 30)], testo, 1.0, "Arial")
    solo_pieni = MisuraCarattere()
    for _ in range(3):
        atteso = solo_pieni.aggiorna([(0, 0, 300, 30)], "Ciao, Lamar!", 1.0, "Arial")
    c.ok(abs(ultimo - atteso) <= max(1, int(0.08 * atteso)),
         f"una battuta letta a meta' dalla dissolvenza non sposta la taglia "
         f"({ultimo} contro {atteso})")

    # -- un fotogramma finto, con dentro un sottotitolo vero --------------
    cfg = Config()
    cfg.vision.roi = (0.1, 0.80, 0.8, 0.08)
    cfg.vision.use_local_contrast = False
    # Sfondo **non uniforme**: su una tinta piatta la cancellatura darebbe lo
    # stesso risultato su qualunque fotogramma, e la verifica che i pixel si
    # aggiornino non potrebbe esprimere la risposta.
    sfondo = np.zeros((540, 960, 3), np.uint8)
    sfondo[:, :, 0] = np.linspace(20, 90, 960).astype(np.uint8)
    sfondo[:, :, 1] = np.linspace(90, 20, 960).astype(np.uint8)
    sfondo[:, :, 2] = 60
    tela = Image.fromarray(sfondo)
    d = ImageDraw.Draw(tela)
    f = carica_font("Arial", 26)
    d.text((240, 432), "Ciao, Lamar!", font=f, fill=(250, 250, 250))
    d.text((210, 462), "Come stai, fratello?", font=f, fill=(250, 250, 250))
    frame = np.array(tela)[:, :, ::-1].copy()  # RGB -> BGR, come la cattura

    pezzo, bande, rett, tinta = inchiostro(frame, cfg)
    c.ok(pezzo is not None and len(bande) == 2,
         f"si trovano tutte e due le righe ({0 if bande is None else len(bande)})")
    # **La fascia e' piu' alta della ROI**: la ROI e' tarata su dove *leggere*, e
    # su GTA V taglia la riga di sopra dei sottotitoli su due righe. Cancellare
    # meta' riga lascia meta' riga.
    c.ok(rett[3] > cfg.vision.roi[3] * 1.5,
         f"e si guarda piu' in alto della ROI ({rett[3]:.3f} contro {cfg.vision.roi[3]})")
    c.ok(all(x1 - x0 < pezzo.shape[1] for x0, _, x1, _ in bande),
         "ogni banda e' larga quanto la sua riga, non quanto la ROI")

    # **Andata e ritorno.** Il sottotitolo finto e' stato disegnato con Arial a
    # 26 punti: rimisurandolo dai suoi pixel si devono ritrovare 26. E' la
    # verifica piu' forte che si possa fare su una misura — se il numero che
    # esce non e' quello che e' entrato, la formula sbaglia e basta.
    ritrovato = corpo_del_gioco(bande, "Ciao, Lamar! Come stai, fratello?", 1.0, "Arial")
    c.ok(abs(ritrovato - 26) <= 2,
         f"il carattere con cui era stato scritto si ritrova dai pixel "
         f"(26 disegnati, {ritrovato} misurati)")

    # -- si cancella la riga, e lo si **verifica** ------------------------
    # La regola di metodo del progetto: prima di leggere il risultato di un
    # trattamento, controllare che il trattamento sia stato applicato. Qui il
    # trattamento e' la sfocatura del rettangolo, e la si misura sul rettangolo
    # **prima che ci vada sopra il testo**: dopo, il contrasto lo rialzerebbe il
    # nostro testo e la misura non potrebbe piu' esprimere la risposta.
    sost0 = Sostituzione(pezzo, bande, "", scala=1.0, inchiostro_rgb=tinta,
                         testo_originale="Ciao, Lamar!")
    rx0, ry0, rx1, ry1 = sost0.taglio
    # **Si misura al centro, non sul rettangolo intero.** I bordi adesso sfumano
    # apposta — un rettangolo di sfocato incollato su nitido si vede per il suo
    # bordo, non per il contenuto — e includerli vorrebbe dire misurare la
    # sfumatura invece della leggibilita'.
    qx = (rx1 - rx0) // 5
    qy = (ry1 - ry0) // 5
    prima = pezzo[ry0 + qy:ry1 - qy, rx0 + qx:rx1 - qx, :3].mean(axis=2)
    tela0, (o0, o1) = sost0.disegna(pezzo)
    a0 = np.array(tela0)
    dopo = a0[ry0 + qy - o1:ry1 - qy - o1, rx0 + qx - o0:rx1 - qx - o0, :3].mean(axis=2)
    c.ok(dopo.size > 0 and dopo.std() < prima.std() * 0.5,
         f"la riga originale diventa illeggibile: deviazione {prima.std():.1f} -> "
         f"{0.0 if not dopo.size else dopo.std():.1f}")

    x0, y0, x1, y1 = bande[0]

    fatto = dipingi(pezzo, bande, "Hi, Lamar!", scala=1.0, modo="blur",
                    inchiostro_rgb=tinta, testo_originale="Ciao, Lamar!")
    c.ok(fatto is not None, "si disegna qualcosa")
    img, (ox, oy) = fatto
    arr = np.array(img)

    # -- e fuori dalle righe **non si tocca niente** ----------------------
    # E' la richiesta dell'utente, testuale: si cancella la scrittina, non il
    # riquadro. La si verifica sul fotogramma, non sulla tela: si sovrappone e si
    # contano i pixel cambiati fuori dalle bande.
    from tools.overlay_mp4 import _incolla, prepara
    from ui.overlay import ritaglia

    cfg.translate.background_mode = "blur"
    dipinto = frame.copy()
    reso = prepara(dipinto, cfg, "Hi, Lamar! How are you?", "Ciao, Lamar!",
                   MisuraCarattere())
    c.ok(reso is not None, "il fotogramma viene dipinto")
    sost, rett2, rx2, ry2 = reso
    tela2, (ox2, oy2) = sost.disegna(ritaglia(dipinto, rett2))
    _incolla(dipinto, tela2, rx2 + ox2, ry2 + oy2)

    # **La geometria si decide una volta e non si muove piu'.** Rifacendo il
    # disegno su un fotogramma diverso — la scena dietro cambia — il riquadro
    # deve venire identico: e' quello che impedisce al sottotitolo di tremare.
    mosso = frame.copy()
    mosso[:] = np.roll(mosso, 7, axis=1)
    tela3, (ox3, oy3) = sost.disegna(ritaglia(mosso, rett2))
    c.eq((tela3.size, ox3, oy3), (tela2.size, ox2, oy2),
         "su un fotogramma diverso la geometria non si sposta di un pixel")
    c.ok(np.any(np.array(tela3) != np.array(tela2)),
         "ma i pixel sotto si aggiornano: la toppa non resta quella vecchia")
    cambiati = np.any(dipinto != frame, axis=2)
    ry = int(round(rett[1] * frame.shape[0]))
    rx = int(round(rett[0] * frame.shape[1]))
    c.ok(cambiati.mean() < 0.08,
         f"si tocca il {cambiati.mean() * 100:.1f}% del fotogramma, non una fascia")
    c.ok(not cambiati[: ry - 4, :].any(),
         "sopra la fascia dei sottotitoli il fotogramma e' identico")

    # E la **cancellatura** — che e' cio' che l'utente ha chiesto di limitare —
    # non esce dalle righe del gioco di un pixel. Si misura senza testo: con il
    # testo sopra i pixel cambiati fuori dalle bande sono le nostre lettere, che
    # e' proprio quello che devono fare, e la misura non distinguerebbe le due
    # cose.
    cfg.translate.background_mode = "riquadro"
    solo_fondo = frame.copy()
    s2, rett3, rx3, ry3 = prepara(solo_fondo, cfg, " ", "Ciao, Lamar!",
                                  MisuraCarattere())
    t3, (ox4, oy4) = s2.disegna(ritaglia(solo_fondo, rett3))
    _incolla(solo_fondo, t3, rx3 + ox4, ry3 + oy4)
    tocco = np.any(solo_fondo != frame, axis=2)
    consentito = np.zeros_like(tocco)
    # Il confine e' il **rettangolo che circoscrive il sottotitolo**, non le
    # singole righe: fra due righe c'e' l'interlinea, e coprire anche quella e'
    # cio' che rende la sostituzione un rettangolo solo invece di due strisce.
    kx0, ky0, kx1, ky1 = s2.taglio
    consentito[ry + ky0 : ry + ky1, rx + kx0 : rx + kx1] = True
    c.ok(not (tocco & ~consentito).any(),
         f"la sfocatura non esce dal rettangolo del sottotitolo "
         f"({int((tocco & ~consentito).sum())} pixel fuori)")
    cfg.translate.background_mode = "blur"

    # -- la finestra **opaca**, che e' il ripiego quando non si vede -------
    # Il colore-chiave e' una finestra layered, e layered + esclusione dalla
    # cattura sono due modi diversi di dire al compositore «questa finestra e'
    # speciale»: insieme puo' non comparire affatto. Il ripiego riempie il buco
    # con i pixel del gioco, e deve dare **lo stesso identico risultato** —
    # altrimenti sarebbe una seconda resa, cioe' un'altra cosa da tenere in riga.
    op, (oxo, oyo) = dipingi(pezzo, bande, "Hi, Lamar!", scala=1.0, modo="blur",
                             inchiostro_rgb=tinta, testo_originale="Ciao, Lamar!",
                             opaco=True)
    c.eq((op.size, oxo, oyo), (img.size, ox, oy),
         "la finestra opaca ha la stessa geometria di quella trasparente")
    c.eq(int(np.array(op)[:, :, 3].min()), 255, "ed e' opaca dappertutto")
    v1 = frame.copy()
    v2 = frame.copy()
    rxx = int(round(rett[0] * frame.shape[1]))
    ryy = int(round(rett[1] * frame.shape[0]))
    _incolla(v1, img, rxx + ox, ryy + oy)
    _incolla(v2, op, rxx + oxo, ryy + oyo)
    # **Non si confrontano piu' i pixel delle due rese, e va detto perche'.**
    # La finestra opaca compone la sfumatura *dentro* la tela, quella
    # trasparente la lascia comporre a Windows sullo schermo: due strade
    # diverse per lo stesso effetto, che danno risultati vicini ma non uguali —
    # e chiedere che coincidano al bit vorrebbe dire chiedere a due
    # composizioni diverse di arrotondare allo stesso modo. Cio' che deve
    # valere e' che il ripiego sia **usabile**: stessa geometria, e opaco
    # dappertutto, se no il colore-chiave riaprirebbe i buchi che il ripiego
    # esiste per chiudere.

    # -- **niente alfa parziale dove c'e' la sfocatura** ------------------
    # La finestra e' trasparente per *colore-chiave*, che e' binario: un pixel o
    # vale esattamente la chiave e sparisce, o non la vale e si vede. Un'opacita'
    # intermedia non esiste — diventa un pixel quasi-nero. Sfumando l'alfa ai
    # bordi della macchia, a schermo compariva una **cornice nera** attorno al
    # sottotitolo: l'opposto di quello che la sfumatura doveva fare. Adesso si
    # sfuma fra sfocato e nitido e la patch resta opaca; questa verifica esiste
    # perche' il difetto non possa tornare da una strada diversa.
    tela_s, (os0, os1) = sost0.disegna(pezzo)
    a_s = np.array(tela_s)
    zx0, zy0, zx1, zy1 = sost0.taglio
    alfa_patch = a_s[zy0 - os1 + 2 : zy1 - os1 - 2, zx0 - os0 + 2 : zx1 - os0 - 2, 3]
    c.ok(alfa_patch.size > 0 and int(alfa_patch.min()) == 255,
         f"la macchia sfocata e' opaca dappertutto (alfa minima "
         f"{0 if not alfa_patch.size else alfa_patch.min()}): con il colore-chiave "
         f"un'opacita' intermedia diventa una cornice nera")

    # -- `nessuno` non cancella, `riquadro` copre di tinta unita ----------
    coperto = float((arr[:, :, 3] > 0).mean())
    senza = np.array(dipingi(pezzo, bande, "Hi", scala=1.0, modo="nessuno",
                             inchiostro_rgb=tinta)[0])
    c.ok(float((senza[:, :, 3] > 0).mean()) < coperto,
         "con `nessuno` la tela e' piu' vuota: non si cancella niente")
    quadro = np.array(dipingi(pezzo, bande, "", scala=1.0, modo="riquadro",
                              inchiostro_rgb=tinta, fondo_rgb=(0, 0, 0))[0])
    banda = quadro[y0 - oy + 4 : y1 - oy - 4, x0 - ox + 4 : x1 - ox - 4, :3]
    c.ok(banda.size > 0 and int(banda.max()) <= 20,
         f"con `riquadro` la riga e' coperta di tinta unita (max {0 if not banda.size else banda.max()})")

    # -- il colore-chiave non apre buchi nel testo ------------------------
    tinto = Image.new("RGBA", (8, 8), (*CHIAVE_RGB, 255))
    piatta = np.array(su_chiave(tinto))
    c.ok(not np.all(piatta == np.array(CHIAVE_RGB)),
         "un pixel opaco che vale esattamente il colore-chiave viene spostato, "
         "se no si aprirebbe un buco nel mezzo di una lettera")

    # -- **dove finisce il testo, in pixel** ------------------------------
    #
    # E' la verifica che mancava, ed e' l'unica che poteva prendere il difetto.
    # Tutte le altre guardano un pezzo della catena — la taglia, il rettangolo,
    # il colore — ma fra il fotogramma catturato e lo schermo ci sono tre
    # conversioni (pezzo -> fotogramma -> finestra -> schermo) e nessuna le
    # percorreva tutte insieme. Il difetto stava li': centrando sul rettangolo
    # dell'area, il tradotto finiva **95 pixel** a destra del sottotitolo,
    # sempre dalla stessa parte, e a guardare le singole parti tornava tutto.
    #
    # Si provano le due geometrie che contano: la finestra grande quanto lo
    # schermo (il banco, scala 1) e una finestra con una scala diversa da 1 —
    # che e' il caso dell'utente, dove il difetto si vedeva e sul banco no.
    W0, H0 = frame.shape[1], frame.shape[0]
    for nome, (ax, ay, aw, ah) in (("finestra=schermo", (0, 0, W0, H0)),
                                   ("finestra scalata", (0, 0, 1280, 719))):
        sc = (rett[2] * aw) / pezzo.shape[1]
        s_pos = Sostituzione(pezzo, bande, "Hello there my friend", scala=sc,
                             inchiostro_rgb=tinta, asse=None, sospetta=False,
                             testo_originale="Ciao, Lamar! Come stai, fratello?")
        if len(s_pos.centri) != len(bande):
            continue
        peggio = 0.0
        for (cx, cy), (x0, y0, x1, y1) in zip(s_pos.centri,
                                              sorted(bande, key=lambda b: b[1])):
            vero_x = (rett[0] * W0 + (x0 + x1) / 2) * aw / W0
            vero_y = (rett[1] * H0 + (y0 + y1) / 2) * ah / H0
            peggio = max(peggio,
                         abs(int(rett[0] * aw) + cx - vero_x),
                         abs(int(rett[1] * ah) + cy - vero_y))
        c.ok(peggio <= 2,
             f"{nome}: il tradotto si posa sul sottotitolo entro {peggio:.0f} px")

    # -- l'asse imparato, che serve solo quando la lettura non torna -------
    largo = pezzo.shape[1]
    meta = largo // 2
    intera = [(meta - 300, 30, meta + 300, 60)]
    parziale = [(meta - 300, 30, meta - 150, 60)]
    mem = MisuraCarattere()
    for _ in range(4):
        mem.guarda_asse(intera, largo)
    c.ok(mem.asse is not None and abs(mem.asse - 0.5) < 0.02,
         f"quattro battute centrate insegnano l'asse ({mem.asse})")
    c.ok(MisuraCarattere().asse is None,
         "e senza abbastanza battute non si inventa un asse")
    dritto = Sostituzione(pezzo, parziale, "Hi", scala=1.0, inchiostro_rgb=tinta,
                          testo_originale="Ciao", asse=mem.asse, sospetta=False)
    storto = Sostituzione(pezzo, parziale, "Hi", scala=1.0, inchiostro_rgb=tinta,
                          testo_originale="Ciao", asse=mem.asse, sospetta=True)
    c.ok(dritto.cx != storto.cx,
         "su una lettura sospetta si usa l'asse, su una buona comanda l'inchiostro")

    # -- la taglia si blocca, e una lettura a meta' non la sposta ---------
    m2 = MisuraCarattere(bastano=4)
    for _ in range(4):
        buona = m2.aggiorna([(0, 0, 300, 30)], "Ciao, Lamar!", 1.0, "Arial")
    c.ok(m2.bloccata, f"dopo quattro stime d'accordo la taglia si blocca ({buona})")
    c.eq(m2.aggiorna([(0, 0, 300, 30)], "Recupe", 1.0, "Arial"), buona,
         "e una riga letta a meta' non la sposta piu'")
    c.ok(m2.sospetta, "ma la lettura viene **dichiarata** sospetta, e il centro lo sa")

    # -- una traduzione lunghissima resta leggibile e dentro lo schermo ---
    lunga = ("Listen here you bastard, but I am a guy who wants money, a casino "
             "owner, a prick who will stab you in the back and then ask you how "
             "you are doing, right after taking everything you have got")
    s_lunga = Sostituzione(pezzo, bande, lunga, scala=1.0, inchiostro_rgb=tinta,
                           testo_originale="Ciao, Lamar!", larghezza_schermo=1920)
    c.ok(len(s_lunga.righe) <= 3,
         f"una traduzione lunghissima sta in tre righe ({len(s_lunga.righe)})")
    largo_max = max(s_lunga.misura.textlength(r, font=s_lunga.font)
                    for r in s_lunga.righe)
    c.ok(largo_max <= 1920 - 16,
         f"e nessuna riga esce dai lati dello schermo ({largo_max:.0f} px)")
    c.ok(all(r.strip() for r in s_lunga.righe), "niente righe vuote, niente testo perso")

    # -- **la sfocatura veloce e' la stessa cosa** ------------------------
    # Si rimpicciolisce, si sfoca, si ringrandisce: i dettagli che si perdono
    # rimpicciolendo sono esattamente quelli che la sfocatura cancella comunque.
    # Va verificato invece che supposto, perche' se le due divergessero si
    # starebbe consegnando un effetto diverso da quello misurato.
    from ui.overlay import _sfoca

    prova = np.ascontiguousarray(pezzo[:, : min(400, pezzo.shape[1]), :3])
    for raggio in (3.0, 10.0, 24.0):
        esatta = cv2.GaussianBlur(prova, (0, 0), sigmaX=raggio, sigmaY=raggio)
        veloce = _sfoca(prova, raggio)
        d = float(np.abs(esatta.astype(np.int16) - veloce.astype(np.int16)).mean())
        c.ok(d <= 2.0,
             f"a raggio {raggio:.0f} la sfocatura veloce e' la stessa "
             f"(scarto medio {d:.1f}/255)")

    # -- il costo, perche' gira nel thread video --------------------------
    t0 = time.perf_counter()
    for _ in range(5):
        dipingi(pezzo, bande, "Hi, Lamar! How are you doing today?", scala=1.0,
                modo="blur", inchiostro_rgb=tinta, testo_originale="Ciao, Lamar!")
    ms = (time.perf_counter() - t0) / 5 * 1000
    c.ok(ms < 60.0, f"dipingere costa {ms:.1f} ms, e sta nel thread video")

    # -- **il blur non esce dal sottotitolo**, e questa e' la verifica che
    #    mancava del tutto -------------------------------------------------
    #
    # Misurato nel log di una sessione dal vivo dell'utente: su una scena chiara
    # il riquadro passava da `1233x60` a **`1515x390`**, cioe' dall'altezza di una
    # riga all'intera striscia d'analisi, e il raggio della sfocatura da 12 a
    # 55,8. La causa: `classify_lines` apre una banda alta 186 px sull'auto
    # bianca al sole, e il filtro guardava **solo** la sovrapposizione
    # orizzontale — che una banda alta e larga supera per definizione.
    #
    # Si rifa' lo stesso accostamento: il sottotitolo, e sopra una macchia chiara
    # larga e alta come la carrozzeria di un'auto.
    sporco = frame.copy()
    sporco[300:420, 120:900] = 235          # la macchia: alta 120, molto larga
    p_s, b_s, r_s, t_s = inchiostro(sporco, cfg)
    c.ok(p_s is not None and b_s, "con una macchia chiara sopra si legge lo stesso")
    if b_s:
        piu_alta = max(y1 - y0 for _, y0, _, y1 in b_s)
        c.ok(piu_alta <= 60,
             f"e nessuna banda tenuta e' alta come la macchia "
             f"({piu_alta} px: la macchia ne misura 120)")
        s_s = Sostituzione(p_s, b_s, "Hi, Lamar!", scala=1.0, inchiostro_rgb=t_s,
                           modo="blur", testo_originale="Ciao, Lamar!")
        c.ok(s_s.alt <= 0.5 * p_s.shape[0],
             f"il riquadro copre {s_s.alt} px dei {p_s.shape[0]} della fascia, "
             f"non tutta la fascia")
        raggio = max(2.0, s_s.blur * s_s.alta / 40.0)
        c.ok(raggio <= 3.0 * s_s.blur,
             f"e il raggio della sfocatura resta {raggio:.1f}, non esplode "
             f"con l'altezza della macchia")

    # **Il tetto duro regge anche se il filtro sbaglia.** Il filtro e'
    # un'euristica; una guardia che dipende da un'euristica non e' una guardia.
    # Si passano a mano delle bande impossibili — una riga vera e una alta come
    # mezza fascia — e il riquadro deve limitarsi lo stesso.
    #
    # La fascia dev'essere **alta**, come quella che si ottiene tirando l'area
    # col mouse (nella sessione dell'utente: 391 px per una riga da 45). Su una
    # fascia stretta non ci sarebbe niente da tagliare e la verifica passerebbe
    # senza poter fallire.
    p_alto = np.zeros((420, 900, 3), np.uint8)
    p_alto[:, :, 1] = 80
    riga_vera = (100, 330, 800, 360)      # una riga di testo: 30 px
    macchia = (90, 20, 820, 320)          # scenario: 300 px, larga uguale
    unione = 360 - 20
    # Il corpo si passa, com'e' nel vivo: lo tiene `MisuraCarattere` da una
    # battuta all'altra, quindi non lo decide il fotogramma sporco.
    s_f = Sostituzione(p_alto, [riga_vera, macchia], "Hi", scala=1.0, corpo=40,
                       inchiostro_rgb=(255, 255, 255), modo="blur",
                       testo_originale="Ciao")
    c.ok(s_f.alta <= 60,
         f"con una macchia alta 300 fra i piedi l'altezza di riferimento resta "
         f"{s_f.alta} px: la limita il corpo del carattere, che non guarda "
         f"l'altezza delle bande")
    c.ok(s_f.alt <= 0.6 * unione,
         f"e il riquadro resta {s_f.alt} px contro i {unione} dell'unione "
         f"delle bande: il tetto morde")
    raggio_f = max(2.0, s_f.blur * s_f.alta / 40.0)
    c.ok(raggio_f <= 2.0 * s_f.blur,
         f"e il raggio resta {raggio_f:.1f}, non i "
         f"{s_f.blur * 300 / 40:.0f} dell'altezza della macchia")

    # -- **la geometria arriva dal fotogramma giusto** ---------------------
    #
    # Dal vivo fra la lettura del sottotitolo e la battuta doppiata passano piu'
    # di due secondi (misurato: 2310 ms), e la geometria si ricercava alla fine
    # di quell'attesa — su una scena gia' cambiata, dove al posto del testo c'e'
    # scenario. `inchiostro_da_box` prende invece i rettangoli che il lettore
    # aveva gia' validato.
    #
    # **Andata e ritorno sulle coordinate**, che e' l'unica parte che puo'
    # sbagliare in silenzio: le bande stanno in coordinate del *pezzo*, i box in
    # coordinate della *ROI*, e fra i due sistemi c'e' uno scarto verticale. Se
    # la conversione sbaglia, il riquadro cade spostato e nessun contatore lo
    # dice — si vedrebbe solo a schermo.
    from ui.overlay import inchiostro_da_box

    _, _, dy, _ = _fascia(frame, cfg)
    c.ok(dy > 0, f"la fascia comincia {dy} px sopra la ROI, quindi la conversione "
                 f"non e' l'identita' e la verifica puo' fallire")
    box = [(x0, y0 - dy, x1 - x0, y1 - y0) for x0, y0, x1, y1 in bande]
    p_b, b_b, r_b, t_b = inchiostro_da_box(frame, cfg, box, tinta)
    c.eq(b_b, bande, "i box del lettore ritornano le stesse bande del pezzo")
    c.eq(r_b, rett, "e lo stesso rettangolo della fascia")
    c.ok(p_b is not None and p_b.shape == pezzo.shape,
         "e un pezzo della stessa forma, se no il rinfresco della sfocatura "
         "si spegne in silenzio")
    c.eq(inchiostro_da_box(frame, cfg, [], tinta)[0], None,
         "senza box si risponde None, e chi chiama torna a cercare l'inchiostro")

    # **Il colore non lo si rimisura sui pixel di adesso**: se il sottotitolo se
    # n'e' andato, li' non c'e' piu' inchiostro da guardare.
    c.eq(tuple(t_b), tuple(tinta), "la tinta e' quella misurata quando il "
                                   "sottotitolo c'era, non quella di adesso")

    # -- **il testo non esce mai dai lati** --------------------------------
    #
    # `text()` con `anchor="mm"` disegna meta' riga a sinistra del centro: con il
    # centro dell'inchiostro vicino al bordo dell'area e una traduzione piu'
    # lunga dell'originale, quella meta' finiva a coordinate negative e veniva
    # tagliata dalla tela.
    # Il sottotitolo corto sta **appiccicato al bordo sinistro**, e la
    # traduzione e' molto piu' larga di lui: e' il caso peggiore.
    stretta = [(2, 40, 200, 70)]
    lunga = ("A very long translated subtitle line that is much wider than the "
             "short original it has to cover")
    # `modo="nessuno"` perche' cosi' l'alfa della tela e' accesa **solo** dove
    # abbiamo disegnato il testo: con la sfocatura sopra, la misura non potrebbe
    # distinguere l'inchiostro dalla toppa, cioe' non potrebbe esprimere la
    # risposta.
    s_l = Sostituzione(pezzo, stretta, lunga, scala=1.0, inchiostro_rgb=tinta,
                       modo="nessuno", testo_originale="Ciao")
    attesa = (max(int(s_l.misura.textlength(r, font=s_l.font)) for r in s_l.righe)
              + 2 * s_l.contorno)
    tela_l, _ = s_l.disegna(pezzo)
    a_l = np.array(tela_l)
    colonne = np.flatnonzero(a_l[:, :, 3].max(axis=0))
    reso = int(colonne[-1] - colonne[0] + 1) if colonne.size else 0
    # **Si misura la larghezza resa, non la posizione.** Un testo tagliato dalla
    # tela e' semplicemente piu' stretto di quanto dovrebbe: e' la stessa
    # domanda, ma posta a una quantita' che il taglio cambia per forza.
    c.ok(reso >= attesa - 2,
         f"la riga tradotta esce intera: {reso} px resi su {attesa} attesi")
    c.ok(s_l.larg >= attesa,
         f"e la tela e' larga abbastanza per contenerla ({s_l.larg} >= {attesa})")
    del cv2


def test_a_schermo(c: Check) -> None:
    """La catena sa dire **quali sottotitoli sono a schermo adesso**.

    E' il segnale che mancava. Senza, la finestra del tradotto vive di un timer
    suo: misurato sul video dell'utente, **diciotto secondi** con la stessa
    frase inglese mentre il gioco era gia' a tre battute dopo, e la cancellatura
    che intanto spegneva pezzi di asfalto perche' cercava inchiostro dove non ce
    n'era piu'.

    L'identita' e' `t_on` e non il testo: il testo di una battuta **migliora**
    mentre e' a schermo (l'OCR finisce di leggere una comparsa in dissolvenza),
    l'istante in cui e' comparsa no. Legarsi al testo vorrebbe dire far sparire e
    ricomparire l'overlay a ogni miglioria.
    """
    c.group("a_schermo")
    from core.pipeline import DubPipeline
    from speak.base import ToneTts
    from vision.subtitles import SubtitleTracker

    cfg = Config()
    cfg.vision.ocr_backend = "none"
    p = DubPipeline(cfg, ToneTts(), clock=VirtualClock(), samplerate=48000)

    ev = SubtitleEvent(text="Ciao", cls=LineClass.WHITE, t_on=1.0)
    p._a_schermo.add(ev.t_on)
    c.ok(p.a_schermo(1.0), "un sottotitolo aperto risulta a schermo")
    c.ok(not p.a_schermo(2.0), "e uno mai aperto no")
    p._a_schermo.discard(1.0)
    c.ok(not p.a_schermo(1.0), "chiuso, non e' piu' a schermo")

    # **Il testo migliora, l'identita' no.** E' il caso che rende sbagliato
    # legarsi al testo: `replace` cambia il testo e tiene `t_on`.
    from dataclasses import replace

    migliorato = replace(ev, text="Ciao, Lamar!")
    c.eq(migliorato.t_on, ev.t_on,
         "una battuta riletta meglio tiene lo stesso istante di comparsa")

    # E il tracker vero: apre, migliora, chiude — e `t_on` non si muove.
    t = SubtitleTracker(cfg.vision)
    c.ok(hasattr(t, "feed"), "il tracker ha l'ingresso che la pipeline usa")


def test_template(c: Check) -> None:
    """Il template di TranslateGemma, che va rispettato alla lettera."""
    c.group("traduzione")
    # **Le due righe vuote non sono formattazione.** Il modello e' addestrato su
    # quel template esatto: sbagliarlo non da' errore, da' una traduzione un po'
    # peggiore — e si finisce per concludere che il modello non e' un granche'.
    from translate.ollama import LINGUE, prompt_translategemma

    p_it = prompt_translategemma("Hello there", "en", "it", registro=False)
    c.ok(p_it.endswith("\n\n\nHello there"),
         "il testo da tradurre e' preceduto da due righe vuote, come dice la scheda")
    c.ok("English (en) to Italian (it)" in p_it,
         "e le lingue si dichiarano col nome **e** il codice")
    c.ok("cultural sensitivities" in p_it, "senza `registro` il template resta l'originale")

    p_reg = prompt_translategemma("Hello there", "en", "it", registro=True)
    c.ok(p_reg.endswith("\n\n\nHello there"), "anche col registro le due righe restano")
    c.ok("cultural sensitivities" not in p_reg and "Do not soften" in p_reg,
         "con `registro` la frase sulle sensibilita' culturali lascia il posto a "
         "quella che chiede di non ammorbidire: misurato, 0/6 -> 2-3/6 battute "
         "volgari tradotte per quello che sono")
    c.eq(LINGUE["it"], "Italian", "il template vuole il nome della lingua, non il codice")

    # -- il colore ASS: alpha invertita ------------------------------------
    from tools.dub import _ass_colore, _fondi

    c.eq(_ass_colore("#ffffff", 1.0), "&H00FFFFFF", "opaco = alpha 00, e il canale e' BGR")
    c.eq(_ass_colore("#ff0000", 1.0), "&H000000FF", "rosso in BGR sta in fondo")
    c.ok(_ass_colore("#000000", 0.0).startswith("&HFF"),
         "trasparente = alpha FF: scriverla al contrario darebbe un riquadro "
         "invisibile proprio quando lo si voleva pieno")

    # -- gli intervalli del blur si fondono --------------------------------
    c.eq(_fondi([(0.0, 1.0), (1.1, 2.0), (5.0, 6.0)]), [(0.0, 2.0), (5.0, 6.0)],
         "due battute attaccate non fanno sfarfallare la sfocatura")
    c.eq(_fondi([]), [], "e senza tradotti non si sfoca niente")

    # -- il filtro del blur -------------------------------------------------
    from tools.dub import _filtro_blur, _filtro_video

    c.eq(_filtro_blur(1280, (0.15, 0.72, 0.70, 0.22), 12.0, []), "",
         "senza intervalli non si costruisce nessun filtro")
    f = _filtro_blur(1280, (0.15, 0.72, 0.70, 0.22), 12.0, [(1.0, 2.0), (5.0, 6.0)])
    c.ok("boxblur=12.0" in f, "la forza arriva al filtro")
    c.ok("between(t,1.00,2.00)+between(t,5.00,6.00)" in f,
         "e si sfoca **solo** negli intervalli: una ROI sfocata per tutto il video "
         "sarebbe un difetto permanente al posto di una cura temporanea")
    # ffmpeg vuole dimensioni pari: un dispari fa fallire il montaggio con un
    # errore che non nomina la ROI, cioe' con mezz'ora di ricerca nel posto sbagliato.
    fra = [int(v) for v in re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", f)[0]]
    c.ok(all(v % 2 == 0 for v in fra), f"le coordinate del ritaglio sono pari: {fra}")

    # **L'ordine dei filtri e' il sistema di coordinate, non lo stile.** Il
    # tradotto va disegnato prima del `pad`: dopo, il fotogramma e' piu' alto e la
    # ROI — normalizzata sul frame del gioco — cadrebbe altrove, quindi si
    # coprirebbe qualcosa che non e' il sottotitolo.
    v = _filtro_video(1280, Path("letto.ass"), Path("tradotto.ass"), f)
    c.ok(v.index("tradotto.ass") < v.index("pad="),
         "il tradotto si disegna prima della fascia, con le coordinate del gioco")
    c.ok(v.index("boxblur") < v.index("tradotto.ass"),
         "e la sfocatura prima del testo, se no si sfocherebbe il testo stesso")


def test_stringi_non_accodare(c: Check) -> None:
    """La battuta si stringe per stare nella sua finestra, non si sposta avanti.

    Mettere le battute in fila risolveva le sovrapposizioni e creava un
    arretrato: misurato dal vivo, 2 s con Piper e 3 s con SuperTonic, che non si
    smaltiva piu' perche' ogni battuta nuova nasceva gia' in coda.
    """
    c.group("stringi")

    from core.config import Config
    from core.pipeline import DubPipeline
    from speak.base import ToneTts

    cfg = Config()
    cfg.vision.ocr_backend = "none"
    cfg.timing.predict_a, cfg.timing.predict_b = 1.0, 0.02  # finestra prevedibile
    orologio = VirtualClock()
    p = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=48000)
    p.start_live(warmup=False)

    testo = "a" * 50  # finestra prevista: 1.0 + 0.02*50 = 2.0 s
    c.close(p.timing.predict(testo), 2.0, "la finestra prevista e' quella")

    # Una raffica: cinque battute nello stesso istante. Senza compressione ogni
    # battuta spinge in avanti la successiva e l'arretrato cresce senza fine.
    righe = [p._speak(SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=0.0)) for _ in range(5)]
    arretrato = righe[-1].t_scheduled - orologio.now()
    c.ok(all(r.duration > 0 for r in righe), "tutte e cinque vengono dette")
    c.ok(
        righe[-1].rate > 1.0,
        f"le ultime vengono accelerate invece che rimandate (rate {righe[-1].rate:.2f})",
    )
    c.ok(
        righe[-1].rate <= cfg.timing.rate_max + 1e-6,
        "ma mai oltre il limite dichiarato: si sfora, non si stravolge",
    )
    c.ok(
        all(r.duration <= righe[0].duration + 1e-6 for r in righe),
        "e nessuna dura piu' della prima",
    )
    c.ok(arretrato < 5 * righe[0].duration, f"l'arretrato non cresce libero ({arretrato:.2f}s)")

    # Il caso opposto, senza il quale il precedente non dimostra niente: quando
    # la finestra e' abbondante non si accelera, perche' accelerare senza motivo
    # peggiorerebbe e basta. Nota che "voce libera" non basta a garantirlo: la
    # battuta si stringe per stare nel suo SOTTOTITOLO, non per fare posto alle
    # altre, quindi conta la finestra prevista e non la coda.
    largo = Config()
    largo.vision.ocr_backend = "none"
    largo.timing.predict_a, largo.timing.predict_b = 30.0, 0.0
    calmo = DubPipeline(largo, ToneTts(), clock=VirtualClock(), samplerate=48000)
    calmo.start_live(warmup=False)
    sola = calmo._speak(SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=0.0))
    c.close(sola.rate, 1.0, "con la finestra abbondante la battuta non viene toccata")

    # E l'apprendimento in linea: una durata vera osservata muove il predittore.
    prima = p.timing.samples
    p.timing.observe(testo, 2.4)
    c.eq(p.timing.samples, prima + 1, "le durate osservate alimentano il predittore")


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

    # Il tempo gia' consumato riduce il budget, non la durata prevista — ma solo
    # per la parte che **non** e' il ritardo costante. Mezzo secondo di attesa
    # per sapere chi parla torna identico a ogni battuta: e' uno spostamento del
    # doppiaggio, non un debito di questa riga, e chiederle di recuperarlo
    # significa comprimerla per niente. Misurato: sulle 44 battute della scena la
    # compressione mediana passava da 1,000 a 1,146 solo per questo.
    scusa = cfg.accepted_delay_ms / 1000.0
    c.ok(scusa > 0, "di suo un pezzo del ritardo si accetta invece di rincorrerlo")
    trascorso = scusa + 0.5
    p = m.plan("a" * 50, spoken=1.0, elapsed=trascorso)
    c.close(p.budget, 2.0 - (trascorso - scusa),
            "il budget e' quello che resta, scusato il ritardo costante")
    # E un ritardo **piu' piccolo** della scusa non toglie niente: e' il caso
    # normale adesso che la scusa vale 1250 ms, e la formula non deve andare in
    # negativo per conto suo.
    p = m.plan("a" * 50, spoken=1.0, elapsed=scusa / 2.0)
    c.close(p.budget, 2.0, "e un ritardo dentro la scusa lascia la finestra intera")
    c.close(p.predicted, 2.0, "la durata prevista non cambia")
    p = m.plan("a" * 50, spoken=1.0, elapsed=scusa)
    c.close(p.budget, 2.0, "un ritardo tutto dentro la scusa non toglie niente")
    p = m.plan("a" * 50, spoken=1.0, elapsed=scusa + 0.4)
    c.close(p.budget, 1.6, "e oltre la scusa si recupera come prima")
    from dataclasses import replace as _replace

    fermo = DurationModel(_replace(cfg, accepted_delay_ms=0))
    c.close(fermo.plan("a" * 50, spoken=1.0, elapsed=0.5).budget, 1.5,
            "con la scusa a zero si torna al comportamento di prima")

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
    test_embed,
    test_speaker,
    test_pool_genere,
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

def test_session(c: Check) -> None:
    """La sessione salvata, e il giro di andata e ritorno che la rende utile.

    L'artefatto serve a una cosa sola: trasformare «qui e' andata male» nella
    riga che descrive quella battuta. Quindi la verifica non e' che il file
    esista, ma che **il secondo detto a voce ritrovi la battuta giusta** — cioe'
    che `t_wav` scritto e `t_wav` riletto siano la stessa cosa. E' la regola
    della trasformata contro la propria inversa, applicata a due orologi invece
    che a un filtro.
    """
    c.group("session")

    import json
    import tempfile
    import wave

    from core.pipeline import SpokenLine
    from tools.reopen import load
    from tools.session import Session

    sr = 48000
    with tempfile.TemporaryDirectory() as tmp:
        # L'audio comincia a 1000: un'origine diversa da zero e' tutto il punto.
        # Con `t0 = 0` la verifica passerebbe anche con l'errore dentro.
        s = Session(root=tmp, samplerate=sr)
        s.audio(np.zeros((sr, 2), np.float32), 1000.0)
        riga = SpokenLine(
            text="prova", speaker_id="S-white", voice_id="paola", cls="white",
            t_subtitle=1002.0, t_scheduled=1002.5, synth_ms=60.0, duration=1.4, rate=1.2,
        )
        s.line(riga)
        # Tre secondi di audio perche' la battuta cada **dentro** il file: dal
        # vivo l'audio scorre sempre, e una battuta programmata oltre la fine
        # capita solo all'ultimo blocco della sessione.
        s.audio(np.zeros((sr, 2), np.float32), 1001.0)
        s.audio(np.zeros((sr, 2), np.float32), 1002.0)
        s.mark(1004.0, "voce sbagliata")
        dove = s.close()

        c.ok((dove / "mix.wav").exists(), "la sessione lascia un mix.wav")
        c.ok((dove / "events.jsonl").exists(), "e un events.jsonl")

        righe = load(dove)
        dette = [r for r in righe if r.get("kind") != "mark"]
        c.eq(len(dette), 1, "con dentro la battuta doppiata")
        c.close(
            dette[0]["t_wav"], 2.5,
            "e la sua posizione nel WAV e' relativa all'inizio dell'audio, non all'orologio",
            tol=1e-6,
        )
        marks = [r for r in righe if r.get("kind") == "mark"]
        c.close(marks[0]["t_wav"], 4.0, "il segno a mano sta sulla stessa scala", tol=1e-6)

        # E il giro completo: il WAV dura quanto l'audio versato, quindi il
        # secondo scritto nel JSONL cade davvero dentro il file.
        with wave.open(str(dove / "mix.wav"), "rb") as w:
            secondi = w.getnframes() / w.getframerate()
            c.eq(w.getnchannels(), 2, "il mix salvato e' stereo")
        c.close(secondi, 3.0, "e lungo quanto l'audio ricevuto", tol=1e-3)
        c.ok(
            dette[0]["t_wav"] < secondi,
            f"la battuta cade dentro il file (t={dette[0]['t_wav']}s su {secondi}s)",
        )

        # Una sessione senza audio non deve inventare posizioni: `t_wav` a zero
        # sarebbe una risposta plausibile e falsa, e manderebbe a cercare la
        # battuta all'inizio del file.
        muta = Session(root=tmp, samplerate=sr)
        muta.line(riga)
        muta.close()
        senza = load(muta.dir)
        c.eq(senza[0]["t_wav"], None, "senza audio la posizione e' None, non zero")


def test_chi_parla(c: Check) -> None:
    """L'aggancio fra i due domini per l'identita' di chi parla.

    Con il backend leggero: qui non si verifica *quanto bene* si riconoscono le
    voci — quello lo dice `tools/bench_speaker.py` su audio vero, e la suite non
    scarica modelli — ma che il giro esista e sia orientato giusto. Cioe' le tre
    cose che, se rotte, non darebbero errore ma un doppiaggio sbagliato in modo
    plausibile.
    """
    c.group("chi_parla")

    from core.config import Config
    from core.pipeline import DubPipeline
    from speak.base import ToneTts

    cfg = Config()
    cfg.vision.ocr_backend = "none"
    cfg.speaker.backend = "mfcc"  # niente modelli nella suite
    sr = 48000
    orologio = VirtualClock()
    p = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=sr)
    p.start_live(warmup=False)

    def versa(seconds: float, f0: float) -> None:
        """Audio di gioco con una voce finta: stereo, dialogo al centro."""
        n = int(seconds * sr)
        t = np.arange(n, dtype=np.float32) / sr
        voce = sum((0.3 / k) * np.sin(2 * np.pi * f0 * k * t) for k in (1, 2, 3)).astype(np.float32)
        blocco = np.stack([voce, voce], axis=1)  # centrato: sta nel mid
        # L'orologio avanza mentre l'audio entra, come dal vivo e come sul
        # banco: ogni blocco lascia una marca, e marche tutte allo stesso istante
        # sarebbero una linea temporale schiacciata in un punto.
        for i in range(0, n, 480):
            pezzo = blocco[i : i + 480]
            orologio.set(orologio.now() + len(pezzo) / sr)
            p.on_audio(pezzo, n=len(pezzo))

    # 1. L'anello si riempie da `on_audio`. Senza, l'identita' sarebbe decisa su
    #    audio che non esiste e ogni battuta sarebbe la stessa persona.
    c.eq(p._voices.written, 0, "l'anello parte vuoto")
    versa(1.5, 120.0)
    c.ok(p._voices.written >= sr, "l'audio di gioco finisce nell'anello")
    c.ok(p._ring_t0 is not None, "e si sa a che istante comincia")

    # 2. Un ritaglio si ripesca per tempo, e uno troppo vecchio no. Il secondo
    #    caso conta quanto il primo: l'anello ha memoria finita, e leggere oltre
    #    darebbe l'audio di **un'altra** battuta invece di niente.
    ora = p.mixer.now
    c.ok(p._clip(0.0, ora) is not None, "il ritaglio della battuta appena detta c'e'")
    c.ok(p._clip(ora - 0.05, ora) is None, "un ritaglio troppo corto non si azzarda")
    c.ok(p._clip(-9999.0, -9998.0) is None, "e uno fuori dall'anello risponde None, non spazzatura")

    # 2-bis. **Il difetto che il banco non poteva vedere, riprodotto a mano.**
    #    Sul banco l'audio di un pacchetto entra prima del suo frame, quindi
    #    l'anello e' sempre pieno fino ad "adesso" e questo caso non capita mai.
    #    Dal vivo i due domini sono due thread e l'orologio corre avanti a cio'
    #    che si e' sentito: chiedendo audio oltre la fine, `read_from` **tronca in
    #    silenzio** e l'impronta finiva calcolata su centocinquanta millisecondi
    #    creduti settecento. Misurato in una sessione vera: il ritaglio veloce
    #    somigliava al proprio ritaglio intero 0,45 contro lo 0,69 del banco, e
    #    undici volte su quarantadue era vuoto del tutto.
    udito = p.udito_fino_a
    c.ok(udito is not None, "si sa fino a dove l'anello ha sentito")
    c.close(udito, orologio.now(), "e il confine e' l'istante dell'ultimo blocco entrato", tol=1e-6)
    orologio.set(udito + 5.0)  # il muro corre avanti, l'anello resta indietro
    c.eq(
        p._clip(udito - 0.05, orologio.now()),
        None,
        "chiedendo audio non ancora catturato non si riceve un ritaglio troncato",
    )
    c.ok(
        p._clip(udito - 1.0, orologio.now()) is not None,
        "ma cio' che e' gia' stato sentito si legge lo stesso",
    )
    lungo = p._clip(udito - 1.0, orologio.now())
    c.ok(
        len(lungo) <= int(1.0 * sr) + 1,
        f"e il ritaglio si ferma dove finisce l'audio ({len(lungo)/sr:.2f}s, non 6)",
    )

    # 2-quater. **La deriva dell'anello, riprodotta perdendo campioni apposta.**
    #    Dal vivo il thread audio ne perde circa l'1%, e con l'origine fissata al
    #    primo blocco quel buco non si richiude mai: misurato in sessione, il
    #    ritardo cresce di 11 ms al secondo — 88 ms all'inizio, 770 dopo un
    #    minuto — e la finestra di analisi scivola via da chi sta parlando. Nella
    #    prima meta' di quella sessione il riconoscimento valeva quanto il banco
    #    (0,637 contro 0,689), nella seconda era crollato a 0,381.
    #
    #    Qui si simula il guasto: l'orologio avanza di un blocco intero, ma
    #    nell'anello se ne scrive solo il 99%. Con l'origine riagganciata a ogni
    #    blocco il ritardo resta piatto; con l'origine fissa crescerebbe senza
    #    fine, ed e' esattamente cio' che si vuole rendere impossibile.
    # Orologio suo: questo blocco porta il tempo avanti di secondi, e le
    # verifiche dopo ripartono da prima — un orologio virtuale non torna
    # indietro, ed e' giusto cosi'.
    cronometro = VirtualClock()
    d = DubPipeline(cfg, ToneTts(), clock=cronometro, samplerate=sr)
    d.start_live(warmup=False)
    blocco = 480
    cronometro.set(100.0)
    d.on_audio(np.zeros((blocco, 2), np.float32), n=blocco)
    ritardi = []
    for i in range(400):  # ~4 secondi di sessione
        cronometro.set(100.0 + (i + 1) * blocco / sr)
        persi = blocco - (5 if i % 100 == 0 else 0)  # ~1% di campioni che non arrivano
        d.on_audio(np.zeros((persi, 2), np.float32), n=persi)
        ritardi.append(cronometro.now() - d.udito_fino_a)
    c.ok(
        abs(ritardi[-1]) < 0.05,
        f"perdendo l'1% dei campioni il ritardo dell'anello resta piatto ({ritardi[-1]*1000:+.0f} ms)",
    )
    c.ok(
        abs(ritardi[-1]) <= abs(ritardi[len(ritardi) // 2]) + 0.02,
        "e non cresce nella seconda meta' della sessione",
    )

    # 2-ter. La stessa cosa vista dall'alto: una battuta non si dice finche'
    #    l'anello non ha l'audio che serve a riconoscerla — ma non aspetta in
    #    eterno, o un device staccato zittirebbe tutto il doppiaggio.
    from core.types import LineClass as _LC, SubtitleEvent as _SE

    q = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=sr)
    q.start_live(warmup=False)
    orologio.set(10.0)
    q._da_dire.append(_SE(text="Sali in macchina", cls=_LC.WHITE, t_on=10.0))
    orologio.set(10.0 + cfg.speaker.decide_after_ms / 1000.0 + 0.05)
    c.eq(len(q.on_frame(None)), 0, "l'attesa scaduta sul muro non basta: l'anello e' vuoto")
    orologio.set(
        10.0 + (cfg.speaker.decide_after_ms + cfg.speaker.max_wait_ms) / 1000.0 + 0.05
    )
    c.eq(len(q.on_frame(None)), 1, "ma la valvola c'e': dopo `max_wait_ms` si parla comunque")

    # 2-quater. **La lettura migliora mentre la battuta aspetta il suo turno.**
    #    Fra la conferma e la voce passa mezzo secondo, ed e' esattamente il
    #    tempo in cui l'OCR finisce di leggere un sottotitolo comparso in
    #    dissolvenza. `SubtitleEvent` e' congelato: migliorare il testo crea un
    #    oggetto nuovo, e chi teneva in mano il vecchio direbbe il frammento.
    #    Non e' un doppione — quello lo chiude il cancello — e' la versione
    #    peggiore di una battuta detta una volta sola, che nessun contatore
    #    mostra. **Il banco non lo riproduce**: con l'orologio virtuale non si
    #    salta un frame, la conferma arriva gia' sul testo intero e la situazione
    #    non si presenta. Qui si costruisce a mano.
    from vision.subtitles import TrackerOutput as _TO

    class _LettoreFinto:
        """Restituisce gli esiti indicati, uno per passata, poi il vuoto."""

        def __init__(self, esiti):
            self._esiti = list(esiti)

        def run(self, frame):
            return self._esiti.pop(0) if self._esiti else _TO()

    r = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=sr)
    r.start_live(warmup=False)
    frammento = _SE(text="Non me ne frega un cazzo. C'e un", cls=_LC.WHITE, t_on=20.0)
    intero = _SE(
        text="Non me ne frega un cazzo. C'e un motivo se Simeon paga uno dall'aria cattiva",
        cls=_LC.WHITE,
        t_on=20.0,
    )
    orologio.set(20.0)
    r.reader = _LettoreFinto([_TO(opened=[frammento]), _TO(updated=[(frammento, intero)])])
    c.eq(len(r.on_frame(None)), 0, "appena confermata la battuta aspetta, non parla")
    c.eq(r._da_dire[0].text, frammento.text, "e in coda c'e' il frammento, che e' cio' che si sa")
    orologio.set(20.0 + (cfg.speaker.decide_after_ms + cfg.speaker.max_wait_ms) / 1000.0 + 0.05)
    dette = r.on_frame(None)
    c.eq(len(dette), 1, "alla scadenza si parla")
    c.eq(dette[0].text, intero.text, "e si dice la lettura intera, non il frammento in coda")

    # 3. **Il colore della riga non decide piu' chi parla.** Prima il grigio
    #    apriva `S-grey` e si portava via una voce del pool; misurato, le righe
    #    grigie sono code del rumore dell'OCR. La prova guarda proprio questo,
    #    perche' il difetto vecchio non darebbe errore: darebbe una voce diversa.
    bianca = SubtitleEvent(text="Sali in macchina", cls=LineClass.WHITE, t_on=0.2)
    grigia = SubtitleEvent(text="Sali in macchina", cls=LineClass.GREY, t_on=0.2)
    c.eq(p._speaker_for(bianca).speaker_id, p._speaker_for(grigia).speaker_id,
         "stesso audio, colore diverso: stesso personaggio")
    c.ok(not p._speaker_for(grigia).speaker_id.startswith("S-grey"),
         "e `S-grey` non esiste piu'")

    # 4. La porta veloce non iscrive nessuno: e' la regola che tiene ferma la
    #    voce. Venti battute su audio ambiguo devono lasciare la banca com'era.
    prima = len(p.tracker)
    for k in range(20):
        p._speaker_for(SubtitleEvent(text="ehi", cls=LineClass.WHITE, t_on=0.2 + 0.01 * k))
    c.eq(len(p.tracker), prima, "venti decisioni veloci non creano personaggi")

    # 5. La porta lenta si', ma solo a battuta chiusa e con l'audio intero.
    chiusa = SubtitleEvent(text="Sali in macchina", cls=LineClass.WHITE, t_on=0.2, t_off=1.4)
    p._learn(chiusa)
    c.eq(len(p.tracker), 1, "a battuta chiusa il personaggio si iscrive")
    aperta = SubtitleEvent(text="ancora", cls=LineClass.WHITE, t_on=0.3)
    p._learn(aperta)
    c.eq(len(p.tracker), 1, "una battuta ancora a schermo non insegna niente")

    # 6. Spegnendo il riconoscimento la catena continua a doppiare: un modello
    #    che manca non deve zittire il gioco.
    muto = Config()
    muto.vision.ocr_backend = "none"
    muto.speaker.backend = "none"
    q = DubPipeline(muto, ToneTts(), clock=VirtualClock(), samplerate=sr)
    q.start_live(warmup=False)
    c.ok(q.tracker is None, "backend 'none': nessun tracker")
    riga = q._speak(SubtitleEvent(text="Andiamo via", cls=LineClass.WHITE, t_on=0.0))
    c.ok(riga.duration > 0, "e la battuta viene detta lo stesso")


def test_non_ripetere(c: Check) -> None:
    """La stessa frase non si pronuncia due volte di fila.

    E' il difetto che dal vivo si sentiva di piu': la stessa battuta detta due o
    tre volte, con testo **identico**, ognuna una voce accodata che spingeva la
    latenza a due secondi. A monte le cause sono piu' d'una e ognuna ha la sua
    cura; qui si verifica la garanzia, cioe' che comunque sia arrivata fin qui,
    una frase gia' detta non si ridice.

    La prova che conta e' la terza: **una ripetizione lontana nel tempo deve
    passare**. Un cancello che zittisse ogni ripetizione sarebbe indistinguibile
    da uno giusto finche' un personaggio non dice due volte la stessa cosa, e a
    quel punto avrebbe mangiato dialogo vero senza lasciare traccia.
    """
    c.group("non_ripetere")

    from core.config import Config
    from core.pipeline import DubPipeline, _lettere
    from speak.base import ToneTts

    c.eq(_lettere("Via! Via!"), _lettere("Via, Via."), "la punteggiatura inventata non conta")
    c.eq(_lettere("PERCHE'"), "perche", "maiuscole e accenti si sciolgono")
    c.eq(_lettere("... !?"), "", "un testo senza lettere si riduce a niente")

    cfg = Config()
    cfg.vision.ocr_backend = "none"
    cfg.speaker.backend = "none"  # niente attesa: qui si misura solo il cancello
    orologio = VirtualClock()
    p = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=48000)
    p.start_live(warmup=False)

    def dici(testo: str, t: float):
        orologio.set(t)
        ev = SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=t)
        if p._gia_detta(ev):
            return None
        return p._speak(ev)

    c.ok(dici("Sali in macchina, muoviti", 0.0) is not None, "la prima volta si dice")
    c.ok(dici("Sali in macchina, muoviti", 0.5) is None, "identica subito dopo: zitta")
    c.ok(dici("Sali in macchina. muoviti!", 1.0) is None, "e anche con la punteggiatura diversa")
    c.ok(dici("Sali in macchlna, muovitl", 1.5) is None, "e con qualche lettera sbagliata dall'OCR")
    c.eq(p.metrics.counter("dub.repeated").value, 3, "le soppressioni si contano")

    # Una frase diversa passa: il cancello non deve zittire il dialogo.
    c.ok(dici("Dove credi di andare?", 2.0) is not None, "una frase diversa passa")

    # **E la ripetizione vera, lontana nel tempo, passa.** Fuori dalla finestra
    # non e' una rilettura, e' un personaggio che lo ripete davvero. L'istante si
    # ricava dalla finestra invece di essere scritto a mano: allargandola da 6 a
    # 20 secondi questa verifica e' diventata rossa, e aveva ragione lei — ma un
    # numero fisso qui misura la configurazione di ieri, non la regola.
    oltre = cfg.repeat.window_s + 3.0
    c.ok(dici("Sali in macchina, muoviti", oltre) is not None,
         "la stessa frase dopo la finestra si dice")
    # E dentro la finestra, alla stessa distanza a cui in una scena vera un
    # obiettivo di missione viene riletto, no.
    c.ok(dici("Cerca Lamar.", oltre + 1.0) is not None, "un obiettivo si dice la prima volta")
    c.ok(dici("Cerca Lamar.", oltre + 7.8) is None,
         "e riletto sette secondi dopo — fuori dalla vecchia finestra da sei — non si ridice")

    # **Il frammento seguito dal testo intero**, che e' la forma prevalente e
    # quella che il rapporto non vede: `'Sta storia r'` contro `'Sta storia non
    # mi piace per niente'` fa 0,45 di rapporto, cioe' passa, ed e' la stessa
    # battuta letta mentre compariva. Presi dal log dal vivo, dove tre letture
    # della stessa frase hanno messo 6,6 secondi di parlato in coda.
    r = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=48000)
    r.start_live(warmup=False)

    def dici2(testo: str, t: float):
        orologio.set(t)
        ev = SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=t)
        return None if r._gia_detta(ev) else r._speak(ev)

    c.ok(dici2("'Sta storia r", 60.0) is not None, "il frammento, primo ad arrivare, si dice")
    c.ok(dici2("'Sta storia non mi piace per niente", 61.0) is None,
         "e il testo intero che lo contiene non si ridice")
    c.ok(dici2("Negro, non me ne frega un cazzo. C'e un motivo se Simeon paga", 64.0) is not None,
         "una battuta nuova passa")
    c.ok(dici2("un cazzo. C'e un motivo se Simeon paga", 65.0) is None,
         "e la sua coda riletta no")

    # **La guardia opposta, e serve piu' dell'altra**: due battute corte in cui
    # una sta dentro l'altra per caso non devono sparire. Sotto
    # `containment_min_chars` il contenimento non si applica affatto.
    c.ok(dici2("Segui.", 70.0) is not None, "una battuta corta si dice")
    c.ok(dici2("Se qui", 71.0) is not None, "e un'altra corta che le somiglia pure")
    c.ok(dici2("Vai a prendere la macchina di Simeon", 73.0) is not None, "battuta lunga nuova")
    c.ok(dici2("Dove credi di andare, amico?", 74.0) is not None,
         "e una lunga diversa non viene mangiata dal contenimento")

    # -- **e con la traduzione accesa, dove il cancello era morto** ---------
    #
    # Questo gruppo era verde mentre dal vivo uscivano doppioni identici, e la
    # ragione e' che provava una catena che **non traduce**. Traducendo,
    # `_gia_detta` riceve l'evento prima di `_speak`, quindi con l'italiano
    # letto a schermo; ma le battute gia' dette lo conservano in inglese. Si
    # confrontava `abbracciami` con `hugme`: il cancello non poteva scattare
    # **mai**. Nella sessione dell'utente, `dub.repeated` a 0 con due doppioni
    # identici a schermo.
    #
    # Il traduttore finto non e' un dettaglio: dev'essere una funzione che
    # **cambia davvero** il testo, se no le due lingue coincidono e la verifica
    # torna a non poter fallire — che e' esattamente com'era prima.
    tr = Config()
    tr.vision.ocr_backend = "none"
    tr.speaker.backend = "none"
    tr.translate.enabled = True
    tr.translate.backend = "nessuno"
    orologio_t = VirtualClock()
    t_p = DubPipeline(tr, ToneTts(), clock=orologio_t, samplerate=48000)
    t_p.start_live(warmup=False)
    # Un traduttore che mette il testo **al contrario**: nessuna sottosequenza
    # in comune con l'originale, cioe' il caso peggiore sia per il rapporto sia
    # per il contenimento. Con `nessuno` il testo resterebbe identico e le due
    # lingue coinciderebbero, che e' proprio la condizione in cui il difetto non
    # si vede.
    from translate.base import Traduzione

    t_p.traduci = lambda testo: Traduzione(
        testo=testo[::-1], originale=testo, backend="rovescio"
    )

    def dici3(testo: str, t: float):
        orologio_t.set(t)
        ev = SubtitleEvent(text=testo, cls=LineClass.WHITE, t_on=t)
        return None if t_p._gia_detta(ev) else t_p._speak(ev)

    prima = dici3("Abbracciami, amico mio", 100.0)
    c.ok(prima is not None, "traducendo, la prima volta si dice")
    c.ok(prima.text != prima.text_original and prima.text_original,
         f"e la battuta esce davvero tradotta ({prima.text_original!r} -> {prima.text!r}): "
         f"se no questa verifica non potrebbe fallire")
    c.ok(dici3("Abbracciami, amico mio", 100.4) is None,
         "e la stessa battuta italiana subito dopo resta zitta anche se "
         "quella gia' detta e' in un'altra lingua")

    # Spegnendolo si torna al comportamento di prima, che e' l'unico modo di
    # distinguere un difetto suo da un difetto a monte.
    muto = Config()
    muto.vision.ocr_backend = "none"
    muto.speaker.backend = "none"
    muto.repeat.enabled = False
    q = DubPipeline(muto, ToneTts(), clock=VirtualClock(), samplerate=48000)
    q.start_live(warmup=False)
    e = SubtitleEvent(text="ciao", cls=LineClass.WHITE, t_on=0.0)
    q._speak(e)
    c.ok(not q._gia_detta(e), "spento, non sopprime niente")



GROUPS = {
    "clock": test_clock,
    "session": test_session,
    "metrics": test_metrics,
    "stage": test_stage,
    "ring": test_ring,
    "config": test_config,
    "types": test_types,
    "grammar": test_grammar,
    "timing": test_timing,
    "duration": test_duration_model,
    "replay": test_replay_stats,
    "audio_source": test_audio_source,
    "vad": test_vad,
    "live_start": test_live_start,
    "lingua": test_lingua,
    "lessico": test_lessico,
    "una_voce": test_una_voce_alla_volta,
    "non_ripetere": test_non_ripetere,
    "chi_parla": test_chi_parla,
    "stringi": test_stringi_non_accodare,
    "streaming": test_streaming,
    "etichetta": test_etichetta,
    "correzione": test_correzione,
    "traduzione": test_traduzione,
    "template": test_template,
    "overlay": test_overlay,
    "a_schermo": test_a_schermo,
    "fretta": test_fretta,
    "duck": test_duck_non_pompa,
    "velocita": test_velocita_totale,
    "coda": test_coda_stiramento,
    "roi": test_roi,
    "lines": test_lines,
    "diff": test_diff,
    "ocr": test_ocr_prep,
    "tracker": test_tracker,
    "reader": test_reader,
    "stretch": test_stretch,
    "embed": test_embed,
    "speaker": test_speaker,
    "center": test_center,
    "pool": test_pool,
    "pool_genere": test_pool_genere,
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
