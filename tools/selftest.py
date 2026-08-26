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

    # -- l'ambiente della traduzione offline --------------------------------
    # **Il guardiano della GPU.** `pip install argostranslate` tira `minisbd`,
    # che dipende da `onnxruntime` (CPU): quel pacchetto scrive nella stessa
    # cartella di `onnxruntime-gpu` e la sintesi Kokoro torna su CPU — 725 ms a
    # battuta invece di 207, **senza un errore**. E' il ripiego silenzioso gia'
    # pagato con `preload_dlls()`, e qui e' a un `pip install` di distanza da
    # chiunque. Questa riga e' l'unica cosa che se ne accorgerebbe.
    from tools.controlla_traduzione import controlla

    bene, righe = controlla(vuole_cuda=False)
    c.ok(bene, "l'ambiente della traduzione e' a posto: " + " | ".join(righe))

    # E la coppia di lingue si risolve **una volta sola**: `auto` diventa `en`
    # sia quando si sceglie cosa scaricare sia quando si traduce. Risolverlo in
    # un posto e non nell'altro vuol dire scaricare un modello e usarne un altro.
    from translate.locale import TraduttoreLocale, coppia

    c.eq(coppia("auto", "it"), ("en", "it"), "`auto` non esiste offline: e' l'inglese")
    c.eq(coppia("", ""), ("en", "it"), "e senza niente, la coppia di serie")
    c.eq(TraduttoreLocale(da="auto", a="fr").coppia(), ("en", "fr"),
         "la stessa regola per il modello da scaricare e per la battuta")

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

    # -- e **fino al bordo**, che e' il difetto visto dall'utente ---------
    # La sfumatura verso i pixel del gioco rimetteva l'originale proprio sul
    # bordo: 8-14 px nitidi tutt'intorno a un riquadro che sta stretto al testo,
    # cioe' le cime e le code dei glifi italiani ancora leggibili. Le misure che
    # c'erano non potevano dirlo — sono tutte di *quanto e' grande* la macchia o
    # *quanto e' opaca*, e lo sbaglio era **cosa resta leggibile dentro di lei**.
    #
    # La quantita' giusta e' il contrasto fra i pixel che **erano** inchiostro e
    # quelli che non lo erano: se la riga e' stata cancellata i due si
    # confondono. Misurato su questo stesso fotogramma, che parte da 183,9 senza
    # toppa: con la sfumatura a 0,18 la cornice sta a 68,3 contro 34,2 del resto
    # — il bordo si legge il **doppio** del centro — e a sfumatura spenta 24,3
    # contro 29,2. Il rapporto separa i due casi di un fattore due e mezzo, che
    # non e' una soglia vinta sull'orlo di un precipizio.
    def _contrasto(luma, ink):
        return (float(luma[ink].mean() - luma[~ink].mean())
                if ink.sum() >= 5 and (~ink).sum() >= 5 else float("nan"))

    p_full = pezzo[ry0:ry1, rx0:rx1, :3].mean(axis=2)
    d_full = a0[ry0 - o1:ry1 - o1, rx0 - o0:rx1 - o0, :3].mean(axis=2)
    hh = min(p_full.shape[0], d_full.shape[0])
    ww = min(p_full.shape[1], d_full.shape[1])
    p_full, d_full = p_full[:hh, :ww], d_full[:hh, :ww]
    era_ink = p_full > 200
    sp = max(2, min(hh, ww) // 6)
    orlo = np.zeros(p_full.shape, bool)
    orlo[:sp, :] = orlo[-sp:, :] = orlo[:, :sp] = orlo[:, -sp:] = True
    c_tutto = _contrasto(d_full, era_ink)
    c_orlo = _contrasto(d_full[orlo], era_ink[orlo])
    c.ok(int(era_ink[orlo].sum()) >= 20,
         f"la cornice della toppa contiene inchiostro da cancellare "
         f"({int(era_ink[orlo].sum())} px): se no la verifica non potrebbe fallire")
    c.ok(c_orlo == c_orlo and c_orlo <= c_tutto * 1.2,
         f"sul bordo la riga originale non si legge piu' che al centro "
         f"(contrasto cornice {c_orlo:.1f} contro {c_tutto:.1f}): sfumare verso "
         f"i pixel del gioco rimetteva li' il sottotitolo da nascondere")

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


def test_anticipo(c: Check) -> None:
    """Tradurre **durante** l'attesa di sapere chi parla, non dopo.

    Erano due attese in fila che non hanno niente da dirsi: mezzo secondo per
    avere abbastanza parlato da calcolare l'impronta (una domanda sull'**audio**)
    e la traduzione (una domanda sul **testo**, che c'e' gia' da quando il
    sottotitolo e' stato confermato). In fila costavano `500 + 657`; sovrapposte
    costano `max(500, 657)`.

    **La verifica che conta e' la seconda, e deve poter fallire.** Non basta
    dire a parole «si traduce prima»: si guarda l'**ordine vero** in cui i due
    stadi vengono chiamati, con un traduttore che registra quando tocca a lui e
    una spia su `_speaker_for`. Rimettendo la traduzione dentro `_speak` questa
    riga diventa rossa — che e' l'unica cosa che rende utile scriverla. E' la
    lezione della guardia del tutorial, che descriveva a parole il caso giusto e
    lo provava col meccanismo sbagliato, quindi non poteva fallire proprio nel
    caso per cui esisteva.

    E la terza: **quando non c'e' nessuna attesa non c'e' nessun guadagno**, e
    si vede dal contatore. E' il caso dell'etichetta (`vision/label.py`), dove
    `pronta()` torna vero subito: va saputo leggendo i numeri invece di
    scoprirlo credendo che il pezzo non funzioni.
    """
    c.group("anticipo")

    import threading as _th
    import time as _time

    from core.anticipa import Anticipo, Preparato
    from core.config import Config
    from core.pipeline import DubPipeline
    from core.types import LineClass as _LC, SubtitleEvent as _SE
    from speak.base import ToneTts
    from translate.base import Traduzione
    from vision.subtitles import TrackerOutput as _TO

    def aspetta(cond, limite: float = 3.0) -> bool:
        """Aspetta che una condizione diventi vera. Torna `False` se scade."""
        fine = _time.perf_counter() + limite
        while _time.perf_counter() < fine:
            if cond():
                return True
            _time.sleep(0.005)
        return cond()

    # -- 1. l'anticipo da solo, fuori dalla pipeline ------------------------
    #
    # Sta in un modulo suo apposta: e' una regola, non del disegno, e si prova
    # senza aprire niente — nessun modello, nessuna rete, nessun Qt.
    fatti: list[str] = []

    def prepara(testo: str) -> Preparato:
        fatti.append(testo)
        return Preparato(testo, testo, testo.upper())

    a = Anticipo(prepara, memoria=4)
    c.ok(a.chiedi("ciao"), "un testo mai visto si mette in coda")
    c.ok(not a.chiedi("ciao"), "e chiederlo di nuovo non lo rifa'")
    c.ok(aspetta(lambda: a.pronti == 1), "il lavoratore lo prepara da solo")
    c.eq(a.prendi("ciao").finale, "CIAO", "e chi lo prende trova il lavoro gia' fatto")
    c.eq(a._n_anticipate.value, 1, "che e' un colpo anticipato, e si conta")

    # Mai chiesto: si fa sul posto. E' il comportamento di sempre, ed e' il
    # ripiego che rende impossibile stare peggio di prima.
    c.eq(a.prendi("mai visto").finale, "MAI VISTO", "quello mai chiesto si fa sul posto")
    c.eq(a._n_inline.value, 1, "e si conta come fatto sul posto, non come anticipato")

    # **Il ricordo ha un tetto.** Tre cose in questo progetto sono gia' cresciute
    # senza fermarsi; questa non deve essere la quarta.
    for i in range(10):
        a.chiedi(f"riga {i}")
    c.ok(aspetta(lambda: len(fatti) >= 12), "dieci testi in coda vengono preparati")
    c.ok(a.pronti <= 4, f"e il ricordo resta al suo tetto ({a.pronti} <= 4)")
    a.ferma()

    # Un preparatore che solleva non spegne il doppiaggio: si tiene l'originale,
    # che e' la politica gia' scritta per la traduzione fallita.
    def rompe(testo: str) -> Preparato:
        raise RuntimeError("rete assente")

    b = Anticipo(rompe, memoria=4)
    c.eq(b.prendi("resta cosi'").finale, "resta cosi'",
         "se preparare fallisce si tiene l'originale invece di sollevare")
    b.ferma()

    # **Fermarsi non lascia nessuno appeso**, e si prova con un thread davvero
    # fermo — non modellando l'attributo che *dovrebbe* dirlo. Una suite appesa
    # non e' rossa: e' muta, ed e' gia' costata dieci minuti in questo progetto.
    d = Anticipo(prepara, memoria=4)
    d._in_volo["appesa"] = _th.Event()  # in volo per qualcuno che non tornera' mai
    uscito = _th.Event()

    def chi_aspetta():
        d.prendi("appesa")
        uscito.set()

    _th.Thread(target=chi_aspetta, daemon=True).start()
    c.ok(not uscito.wait(0.15), "chi aspetta un testo in volo resta fermo")
    d.ferma()
    c.ok(uscito.wait(1.0), "e `ferma()` lo sveglia invece di lasciarlo li'")

    # -- 2. nella catena: si traduce PRIMA di decidere chi parla ------------
    #
    # Il traduttore dorme apposta: senza un costo misurabile, «prima» e «dopo»
    # darebbero gli stessi numeri e questa verifica non potrebbe distinguerli.
    COSTO = 0.15

    cfg = Config()
    cfg.vision.ocr_backend = "none"
    cfg.vad.backend = "energy"  # se no il gruppo scaricherebbe un modello
    cfg.translate.enabled = True
    cfg.translate.backend = "nessuno"
    orologio = VirtualClock()
    p = DubPipeline(cfg, ToneTts(), clock=orologio, samplerate=48000)
    p.start_live(warmup=False)
    c.ok(p._anticipo is not None, "con la traduzione accesa l'anticipo c'e'")

    ordine: list[str] = []

    def traduttore_lento(testo: str) -> Traduzione:
        ordine.append("traduci")
        _time.sleep(COSTO)
        return Traduzione(testo=testo[::-1], originale=testo, backend="rovescio")

    p.traduci = traduttore_lento
    vero_speaker_for = p._speaker_for

    def spia(event):
        ordine.append("chi_parla")
        return vero_speaker_for(event)

    p._speaker_for = spia

    class _LettoreFinto:
        def __init__(self, esiti):
            self._esiti = list(esiti)

        def run(self, frame):
            return self._esiti.pop(0) if self._esiti else _TO()

        def close(self):
            return _TO()

    battuta = _SE(text="Sali in macchina, muoviti", cls=_LC.WHITE, t_on=10.0)
    p.reader = _LettoreFinto([_TO(opened=[battuta])])
    orologio.set(10.0)
    c.eq(len(p.on_frame(None)), 0, "appena confermata la battuta aspetta, non parla")
    c.eq(len(p._da_dire), 1, "ed e' in coda in attesa di sapere chi parla")

    # **Qui sta tutto.** Mentre la battuta aspetta, la traduzione e' gia' partita
    # e ha finito. Con la traduzione dentro `_speak` — cioe' com'era — a questo
    # punto `ordine` sarebbe vuoto e le due righe qui sotto sarebbero rosse.
    c.ok(aspetta(lambda: "traduci" in ordine),
         "mentre la battuta aspetta l'audio, la traduzione e' gia' partita")
    c.ok("chi_parla" not in ordine,
         "e si e' tradotto PRIMA di decidere chi parla: sono due domande "
         "indipendenti, e in fila costavano la somma")
    # **Si aspetta che abbia finito, non che sia partita.** Il traduttore finto
    # segna il suo turno e *poi* dorme: guardando solo `ordine` si ripartirebbe
    # a meta' del suo lavoro, e il thread video ne pagherebbe la seconda meta' —
    # cioe' la verifica misurerebbe la propria fretta invece dell'anticipo.
    c.ok(aspetta(lambda: p._anticipo.pronti >= 1),
         "e finisce mentre la battuta e' ancora in coda")

    orologio.set(10.0 + (cfg.speaker.decide_after_ms + cfg.speaker.max_wait_ms) / 1000.0 + 0.05)
    dette = p.on_frame(None)
    c.eq(len(dette), 1, "alla scadenza dell'attesa si parla")
    c.eq(ordine, ["traduci", "chi_parla"], "e l'ordine e' quello, una volta sola per parte")
    c.eq(dette[0].text, battuta.text[::-1], "la battuta esce tradotta")
    c.eq(dette[0].text_original, battuta.text,
         "e porta con se' cosa c'era scritto, se no la prova d'ascolto non "
         "distingue «ha letto male» da «ha tradotto male»")

    # **I due cronometri dicono cose diverse, ed e' per questo che sono due.**
    # Il costo della traduzione c'e' tutto; addosso al thread video non c'e'
    # piu'. Se tornassero a coincidere, l'anticipo non starebbe funzionando.
    riga = p.metrics.timer("translate.riga")
    attesa = p.metrics.timer("translate.attesa")
    c.ok(riga.count == 1 and riga.max >= COSTO * 1000 * 0.8,
         f"la traduzione ha un cronometro suo e ha misurato il suo costo "
         f"({riga.max:.0f} ms su {COSTO*1000:.0f} attesi)")
    c.ok(attesa.max < COSTO * 1000 * 0.5,
         f"e il thread video non l'ha pagato ({attesa.max:.1f} ms, "
         f"contro i {riga.max:.0f} che costava)")
    c.eq(p.metrics.counter("translate.anticipate").value, 1,
         "la battuta ha trovato il lavoro gia' fatto")
    c.eq(p.metrics.counter("translate.inline").value, 0,
         "e non ne ha fatto nessuno sul posto")

    # -- 3. senza attesa non c'e' guadagno, e si vede ----------------------
    #
    # Con il nome scritto dal gioco `pronta()` torna vero subito: non c'e'
    # nessuna attesa in cui nascondere la traduzione, e il lavoro si fa sul
    # posto come prima. Non e' un difetto, e' una cosa da sapere leggendo i
    # numeri. Qui si riproduce togliendo il tracker, che e' l'altro modo in cui
    # `pronta()` non aspetta niente.
    senza = Config()
    senza.vision.ocr_backend = "none"
    senza.speaker.backend = "none"
    senza.translate.enabled = True
    senza.translate.backend = "nessuno"
    s = DubPipeline(senza, ToneTts(), clock=VirtualClock(), samplerate=48000)
    s.start_live(warmup=False)
    s.traduci = lambda testo: Traduzione(testo=testo[::-1], originale=testo, backend="r")
    s.reader = _LettoreFinto([_TO(opened=[_SE(text="Dove vai?", cls=_LC.WHITE, t_on=1.0)])])
    c.eq(len(s.on_frame(None)), 1, "senza attesa la battuta esce nello stesso fotogramma")
    c.eq(s.metrics.counter("translate.inline").value, 1,
         "e la traduzione si fa sul posto: non c'era nessuna attesa in cui infilarla")
    c.eq(s.metrics.counter("translate.anticipate").value, 0,
         "quindi zero anticipate, ed e' giusto cosi'")

    # -- 4. il cancello anti-doppioni regge lo spostamento ------------------
    #
    # E' il confine che questo lavoro tocca: `_gia_detta` riceve l'italiano
    # letto a schermo e le battute gia' dette conservano cio' che si e' **detto**
    # — che traducendo e' un'altra lingua. Era gia' andato storto una volta
    # (`abbracciami` contro `hugme`, `dub.repeated` a zero con due doppioni a
    # schermo). Qui si ripassa dalla porta nuova, cioe' da `on_frame`.
    doppia = _SE(text="Abbracciami, amico mio", cls=_LC.WHITE, t_on=30.0)
    ancora = _SE(text="Abbracciami, amico mio", cls=_LC.WHITE, t_on=30.6)
    orologio2 = VirtualClock()
    g = DubPipeline(cfg, ToneTts(), clock=orologio2, samplerate=48000)
    g.start_live(warmup=False)
    g.traduci = lambda testo: Traduzione(testo=testo[::-1], originale=testo, backend="r")
    passo = (cfg.speaker.decide_after_ms + cfg.speaker.max_wait_ms) / 1000.0 + 0.05
    g.reader = _LettoreFinto([_TO(opened=[doppia]), _TO(), _TO(opened=[ancora])])
    orologio2.set(30.0)
    g.on_frame(None)
    orologio2.set(30.0 + passo)
    c.eq(len(g.on_frame(None)), 1, "la prima si dice")
    orologio2.set(30.6 + passo)
    c.eq(len(g.on_frame(None)), 0, "e la stessa riletta subito dopo no, anche traducendo")
    c.eq(g.metrics.counter("dub.repeated").value, 1, "e la soppressione si conta")

    # -- 5. con la traduzione spenta non cambia niente ---------------------
    #
    # E' il caso principale del prodotto — GTA V, gia' in italiano — e non deve
    # pagare nemmeno un thread per una cosa che non gli serve.
    muto = Config()
    muto.vision.ocr_backend = "none"
    muto.vad.backend = "energy"
    lavoratori = lambda: sum(1 for t in _th.enumerate() if t.name == "anticipo")
    prima_thread = lavoratori()
    m = DubPipeline(muto, ToneTts(), clock=VirtualClock(), samplerate=48000)
    m.start_live(warmup=False)
    m.reader = _LettoreFinto([_TO(opened=[_SE(text="Ciao", cls=_LC.WHITE, t_on=1.0)])])
    m.on_frame(None)
    c.ok(m._anticipo is None,
         "senza traduzione e senza correttore non si costruisce nessun anticipo")
    c.eq(lavoratori(), prima_thread,
         "e una sessione che non traduce non accende nessun lavoratore in piu'")
    c.eq(m.metrics.timer("translate.riga").count, 0,
         "ne' scrive una riga nei cronometri della traduzione")

    p.finish()
    g.finish()
    m.finish()


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
    test_cancello_area,
    test_diff,
    test_lines,
    test_ocr_prep,
    test_reader,
    test_roi,
    test_tracker,
)
from tools.selftest_gioco2 import test_gioco2  # noqa: E402
from tools.selftest_menta import (  # noqa: E402
    test_finestra_menta,
    test_menta,
    test_regole_finestra,
)
from tools.selftest_schema import test_limiti, test_livelli, test_schema  # noqa: E402
from tools.selftest_aree import (  # noqa: E402
    test_memoria,
    test_sessione,
    test_due_sessioni,
    test_ripresa,
    test_guasto_audio,
    test_uscita_audio,
    test_solo_roi,
    test_catture,
    test_motore,
    test_stato_sessione,
    test_overlay_base,
    test_overlay_quando,
    test_manopole,
    test_coerenza,
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

    # **E i volumi arrivano al mixer a sessione accesa.** La riga che li rilegge
    # sta in `on_audio`, cioe' nel dominio che li usa; senza, girare la manopola
    # scriveva in config e basta — e il pannello dichiarava il contrario. Si
    # prova dal *fuori*: si cambia `cfg`, si versa un blocco, si guarda il
    # mixer. Chiedere a `Mixer.ritara` proverebbe la funzione e non il filo.
    prima = p.mixer.envelope.duck_gain
    cfg.mix.duck_db = -30.0
    cfg.mix.dub_gain_db = 3.0
    versa(0.05, 120.0)
    c.ok(p.mixer.envelope.duck_gain < prima,
         "cambiando `mix.duck_db` a sessione accesa, il mixer lo prende")
    c.close(p.mixer.dub_gain, 1.413, "e cosi' il volume della voce", tol=1e-3)

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



def test_lingue(c: Check) -> None:
    """Le lingue: la tabella, chi dichiara di saperle fare, e chi ha una voce.

    Sono tre regole che vivono **fuori dalla finestra**, ed e' apposta: la parte
    che si puo' provare senza aprire Qt deve stare fuori da Qt, che e' la
    lezione gia' pagata quattro volte su cinque difetti.
    """
    c.group("lingue")

    from speak.pool import ha_voce, lingue_con_voce
    from translate.lingue import (
        AUTO,
        LINGUE,
        PER_CODICE,
        TUTTE,
        copertura,
        etichetta,
        lingua,
        nome_en,
        nome_it,
        normalizza,
    )

    # -- la tabella ---------------------------------------------------------
    c.eq(len(LINGUE), 133, "le lingue di Google Translate sono centotrentatre")
    c.eq(len(PER_CODICE), len(LINGUE), "e nessun codice e' ripetuto")
    nomi = [x.italiano.lower() for x in LINGUE]
    c.eq(nomi, sorted(nomi),
         "in ordine alfabetico italiano, che e' l'ordine in cui si cerca "
         "con l'occhio — e ordinato dal codice, non a mano")
    c.ok(all(x.italiano and x.inglese and x.codice for x in LINGUE),
         "ogni voce ha codice, nome italiano e nome inglese")
    # Il nome inglese non e' decorazione: e' quello che entra nel prompt.
    c.eq(nome_en("ja"), "Japanese", "il nome inglese serve al template del modello")
    c.eq(nome_it("ht"), "Creolo haitiano", "e quello italiano al menu")
    c.eq(etichetta("ja"), "Giapponese (ja)",
         "nel menu si legge il nome e si cerca il codice")

    # -- i codici scritti in un altro modo ----------------------------------
    # `zh-Hans` sta nei vecchi profili, `he` e' l'ISO moderno, `it_IT` e' come
    # lo scrive Piper. Senza gli alias diventerebbero lingue sconosciute, cioe'
    # un avviso su una scelta che funziona.
    c.eq(normalizza("zh-Hans"), "zh-CN", "il vecchio codice cinese torna in tabella")
    c.eq(normalizza("he"), "iw", "e l'ebraico moderno diventa quello di Google")
    c.eq(normalizza("it_IT"), "it", "e la forma di Piper pure")
    c.eq(normalizza("IT"), "it", "maiuscolo compreso")
    # **Ma un codice che non si conosce torna com'e'.** Mapparlo su un ripiego
    # ragionevole sarebbe l'ennesima correzione silenziosa: la sessione
    # girerebbe con una lingua diversa da quella scritta.
    c.eq(normalizza("xx"), "xx", "un codice sconosciuto non si sostituisce")
    c.ok(lingua("xx") is None, "e si sa che non e' in tabella")

    # -- chi dichiara di saper fare cosa ------------------------------------
    g = copertura("google")
    c.eq(g.codici, TUTTE, "google e' l'unico elenco chiuso: tutte quelle in tabella")
    c.ok(g.auto, "e l'unico che riconosce la lingua da solo")
    c.ok(g.sa_fare("ja") and not g.sa_fare("xx"),
         "quindi un codice inventato viene marcato anche con google")

    for nome in ("locale", "llm", "ollama"):
        cop = copertura(nome)
        c.ok(cop.codici is None,
             f"«{nome}» non ha un elenco chiuso, e `None` non vuol dire «tutte»")
        c.ok(not cop.auto and not cop.sa_fare(AUTO),
             f"«{nome}» non capisce `auto`: la coppia gli arriva gia' risolta")
        c.ok("en" in cop.nota,
             f"e la nota di «{nome}» dice **quale** lingua verrebbe usata al suo posto")
        c.ok(cop.sa_fare("ja"),
             f"ma col dubbio si risponde di si': marcare cio' che potrebbe "
             f"funzionare fa smettere di leggere gli avvisi veri ({nome})")

    # **Il caso nullo della copertura**: se `sa_fare` dicesse sempre di si', la
    # riga di sopra passerebbe lo stesso. Serve un `no` da qualche parte.
    c.ok(not copertura("locale").sa_fare("auto") and copertura("google").sa_fare("auto"),
         "e i due backend rispondono diverso sulla stessa domanda")

    # -- e la voce, che e' l'altra meta' -------------------------------------
    # Tradurre verso una lingua per cui il motore montato non ha voci non da'
    # errore: esce una voce che ne pronuncia un'altra.
    #
    # **Queste tre righe dicevano il falso, e non era un limite dei motori.**
    # «piper non ha voci giapponesi» e «le dieci di supertonic sono tutte
    # italiane» erano scritte in `pool.LINGUE_VOCE` e basta: Piper ha 175 voci in
    # 51 lingue e SuperTonic-3 e' multilingue in 31. La verifica confermava il
    # difetto invece di prenderlo, che e' la forma peggiore di verde.
    c.ok(ha_voce("piper", "it"), "piper ha voci italiane")
    c.ok(ha_voce("piper", "de"), "e anche tedesche: l'indice ne dichiara 51 lingue")
    c.ok(not ha_voce("piper", "am"), "ma non amariche, e quello va detto")
    c.ok(not ha_voce("piper", "ja"),
         "e nemmeno giapponesi: la voce c'e', ma piper-tts non sa fonemizzarla")
    c.ok(ha_voce("supertonic", "en"),
         "le dieci voci di supertonic parlano tutte e trentuno le sue lingue")
    c.ok(not ha_voce("supertonic", "sw"),
         "e lo swahili non e' fra quelle")
    c.ok(ha_voce("kokoro", "en") and ha_voce("kokoro", "it"),
         "kokoro ha italiano e inglese")
    c.ok(ha_voce("kokoro", "zh") and not ha_voce("kokoro", "de"),
         "e altre sei, ma non il tedesco")
    c.ok(ha_voce("kokoro", "en-GB"),
         "e una variante e' la sua lingua: `en-GB` e' inglese")
    # Un bip non ha lingua: avvisare che «non c'e' una voce giapponese» per un
    # bip e' rumore, e il rumore fa smettere di leggere gli avvisi veri.
    c.ok(ha_voce("tone", "ja") and ha_voce("silent", "ja"),
         "i motori che non pronunciano parole non hanno una lingua da avvisare")
    c.ok(ha_voce("motore-mai-visto", "ja"),
         "e di un motore sconosciuto non si inventa un avviso")

    # **Le lingue di Kokoro non sono scritte due volte.** Copiarle in `pool.py`
    # sarebbe il secondo posto che dice la stessa cosa, e il secondo posto non
    # lo aggiorna nessuno.
    from speak.backends.kokoro import PER_LINGUA

    c.eq(set(lingue_con_voce("kokoro")), set(PER_LINGUA),
         "e le lingue di kokoro le dichiara kokoro, non il pool")

    # -- il nome per esteso arriva **dentro il prompt** ----------------------
    # Era il difetto muto: `LINGUE.get(a, a)` ripiegava sul codice, quindi con
    # `target=ja` il modello leggeva «into ja» invece di «into Japanese».
    # Risponde lo stesso, e risponde peggio, senza che niente lo dichiari.
    from translate.ollama import LINGUE as NOMI_OLLAMA
    from translate.ollama import prompt_translategemma

    c.eq(NOMI_OLLAMA["it"], "Italian", "il template vuole il nome, non il codice")
    c.eq(len(NOMI_OLLAMA), len(LINGUE),
         "e adesso ce l'hanno tutte e centotrentatre, non tredici")
    p = prompt_translategemma("Ciao", "it", "ja")
    c.ok("Japanese" in p and "into ja\n" not in p,
         "una lingua fuori dalle tredici scritte a mano non finisce piu' "
         "nel prompt come codice nudo")
    c.ok("Chinese (Simplified)" in prompt_translategemma("Ciao", "it", "zh-Hans"),
         "e un codice scritto in un altro modo si risolve lo stesso")

    # -- la scelta arriva davvero al traduttore ------------------------------
    # **Una manopola che scrive in config un valore che nessuno rilegge e' il
    # difetto tipico di questa codebase** (`max_ocr_hz`, `tts.device`,
    # `background_mode`, `overlay.ritardo`). Qui si prova la catena intera: si
    # scrive la lingua come la scriverebbe il pannello e si guarda cosa riceve
    # il traduttore.
    from core.config import Config
    from core.pipeline import DubPipeline
    from core.types import LineClass, SubtitleEvent
    from speak.base import ToneTts

    visto: list[tuple[str, str]] = []

    class _Spia:
        name = "spia"

        def traduci(self, testo, da, a):
            visto.append((da, a))
            return f"[{a}] {testo}"

    cfg = Config()
    cfg.vision.ocr_backend = "none"
    cfg.speaker.backend = "none"
    cfg.translate.enabled = True
    cfg.translate.backend = "prova"
    cfg.set("translate.source", "en")     # la stessa porta del pannello
    cfg.set("translate.target", "ja")
    p = DubPipeline(cfg, ToneTts(), clock=VirtualClock(), samplerate=48000)
    p.start_live(warmup=False)
    p.traduci.traduttore = _Spia()
    p._speak(SubtitleEvent(text="Hello there", cls=LineClass.WHITE, t_on=0.0))
    c.eq(visto, [("en", "ja")],
         "la coppia scritta in config e' quella che riceve il traduttore: "
         "una lingua scelta nel menu e mai riletta sarebbe il difetto di sempre")


def test_ui_lingua(c: Check) -> None:
    """La lingua della **finestra**: i cataloghi, e cosa resta in italiano.

    Non apre Qt per la parte che non ne ha bisogno — i cataloghi, il conteggio
    delle chiavi mancanti, la regola su cosa non si traduce — e ne apre il meno
    possibile per l'unica cosa che lo richiede: che rimettere l'italiano
    **rimetta l'italiano** invece di tradurre una traduzione.
    """
    c.group("lingue")

    from ui import lingua as L

    # -- i cataloghi ci sono e sono pieni ------------------------------------
    chiavi = L.chiavi()
    c.ok(len(chiavi) > 100,
         f"l'elenco delle chiavi e' estratto e non vuoto ({len(chiavi)})")
    c.ok(all(isinstance(k, str) and k.strip() for k in chiavi),
         "e non contiene stringhe vuote")
    lingue = L.disponibili()
    c.eq(lingue[0], "it", "l'italiano viene per primo: e' la lingua del sorgente")
    c.ok(len(lingue) > 20, f"e ci sono {len(lingue)} lingue fra cui scegliere")
    c.eq(L.carica("it"), {},
         "l'italiano non ha catalogo: e' quello che c'e' scritto nel sorgente")

    # **Quante chiavi mancano, per ogni lingua.** Una finestra mezza tradotta
    # senza che niente lo dica e' peggio di una finestra in italiano: si crede
    # che quella parola non esista invece che non sia stata tradotta. Il tetto
    # e' zero perche' i cataloghi sono generati tutti insieme; una stringa nuova
    # nel codice lo alza, e la suite lo dice invece di lasciarlo scivolare.
    buchi = {x: len(L.mancanti(x)) for x in lingue if x != "it"}
    peggio = max(buchi.values(), default=0)
    c.eq(peggio, 0,
         f"nessun catalogo ha buchi (il peggiore ne ha {peggio}): "
         f"rilancia `tools/traduci_ui.py` se questa diventa rossa")

    # -- quanto cresce il testo, che e' la meta' esplicita della richiesta ---
    # «Il testo non deve sforare nessun riquadro». Il pixel lo misura
    # `tools/traduci_ui.py --misura`, con la finestra vera e il **carattere
    # vero**: misurato su tutti i cataloghi, la piu' larga e' il tamil a 934 px
    # sul minimo di 960, e nessuna sfora. Qui non si puo' rifare quella misura —
    # la suite gira offscreen, dove non c'e' nessun carattere installato e il
    # ripiego e' molto piu' largo: provato, dava per rotte trentuno lingue su
    # quarantadue. Una misura che non puo' esprimere la risposta va cambiata,
    # non interpretata.
    #
    # Quello che si puo' misurare qui e' la **crescita in caratteri**, che non
    # dipende da nessun carattere tipografico. Non e' il pixel, ed e' scritto:
    # e' il cricchetto che si accorge di una traduzione lunga il triplo — quelle
    # che fanno sforare — il giorno in cui si rigenera un catalogo.
    lunghe: list[str] = []
    for codice in lingue:
        if codice == "it":
            continue
        catalogo = L.carica(codice)
        for chiave, valore in catalogo.items():
            # Sotto i dieci caratteri il rapporto non vuol dire niente: «Voce»
            # in ungherese e' «Hang», ma «Avvia» -> «Uruchomienie» e' il doppio
            # senza che nessuna riga si allarghi.
            if len(chiave) >= 10 and len(valore) > 2.2 * len(chiave):
                lunghe.append(f"{codice}: {chiave[:28]!r} -> {valore[:28]!r}")
    c.ok(not lunghe,
         "nessuna traduzione e' piu' del doppio abbondante dell'italiano"
         + (f" — {len(lunghe)}: {lunghe[:3]}" if lunghe else ""))

    # -- i pezzi composti a runtime, e il modo di non perderli ---------------
    # La riga «da fare nella preparazione: …» nasce unendo dei pezzi, quindi
    # nessuna passeggiata sui widget puo' vederli separati: nel catalogo era
    # finita **una combinazione sola**, quella dell'istante dell'estrazione, e
    # nelle schermate si vedeva — finestra in tedesco, quella riga in italiano.
    # I pezzi ora stanno in `COMPOSTE`, e il rischio ovvio di un elenco a mano e'
    # che diverga da quello che il codice chiede davvero. Quindi non lo si
    # rilegge a occhio: si legge il **sorgente** di `tools/ui_qt.py` e si
    # pretende che i due coincidano, che e' la stessa strada di `core/schema.py`
    # con i commenti di config.
    import ast
    from pathlib import Path

    sorgente = Path(__file__).resolve().parent / "ui_qt.py"
    albero = ast.parse(sorgente.read_text(encoding="utf-8"))
    chieste = {
        n.args[0].value
        for n in ast.walk(albero)
        if isinstance(n, ast.Call) and n.args
        and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
        and (
            (isinstance(n.func, ast.Name) and n.func.id == "dillo")
            or (isinstance(n.func, ast.Attribute) and n.func.attr == "traduci")
        )
    }
    c.ok(chieste, f"il sorgente compone davvero delle frasi ({len(chieste)} pezzi)")
    c.eq(sorted(chieste - set(L.COMPOSTE)), [],
         "ogni pezzo composto nella finestra sta in `COMPOSTE`, se no uscirebbe "
         "in italiano in mezzo a una finestra tradotta")
    c.eq(sorted(set(L.COMPOSTE) - chieste), [],
         "e non ce ne sono di avanzati, che sarebbero chiavi tradotte per niente")
    c.eq(sorted(set(L.COMPOSTE) - set(chiavi)), [],
         "e stanno tutti nell'elenco delle chiavi: `--estrai` li aggiunge")

    # -- cosa **non** si traduce, e sono regole ------------------------------
    c.ok(not L._traducibile("vision.sat_max"),
         "un percorso di config non e' una frase: tradotto, non si cerca piu'")
    c.ok(not L._traducibile("roi_margin"), "e nemmeno il nome nudo di un campo")
    c.ok(not L._traducibile("—") and not L._traducibile("12"),
         "un glifo e un numero non sono testo")
    c.ok(not L._traducibile("<b>ciao</b>"), "e l'HTML del log si lascia stare")
    c.ok(L._traducibile("Seleziona area"), "una frase invece si'")

    # -- da destra a sinistra ------------------------------------------------
    c.ok(L.da_destra("ar") and L.da_destra("iw") and L.da_destra("fa"),
         "arabo, ebraico e persiano si scrivono da destra")
    c.ok(L.da_destra("he"), "anche scritto con l'ISO moderno")
    c.ok(not L.da_destra("it") and not L.da_destra("ja"),
         "e l'italiano e il giapponese no")

    # -- `auto` e il ripiego dichiarato --------------------------------------
    c.ok(L.risolvi("auto") in lingue,
         "`auto` finisce sempre su una lingua che ha un catalogo")
    c.eq(L.risolvi("codice-che-non-esiste"), "it",
         "e una lingua senza catalogo torna all'italiano invece di lasciare "
         "la finestra a meta'")
    c.eq(L.risolvi(""), "it", "come il vuoto")

    # **E perche' e' rimasta in italiano non e' una domanda sola.** La finestra
    # scriveva «! nessun catalogo per "auto"» su un Windows italiano, cioe'
    # marcava come guasto il caso in cui `auto` aveva funzionato: visto nel
    # registro di una prova vera, due volte. Un `!` dove non e' successo niente
    # e' il ripiego silenzioso girato dall'altra parte.
    c.eq(L.perche_italiano("de"), "", "in tedesco non e' rimasta in italiano")
    c.eq(L.perche_italiano("it"), "scelto", "l'italiano si puo' volere")
    c.eq(L.perche_italiano(""), "scelto", "e il vuoto e' l'italiano")
    c.eq(L.perche_italiano("codice-che-non-esiste"), "senza catalogo",
         "un codice senza catalogo e' un ripiego, e si dichiara")
    c.ok(L.perche_italiano("auto") in ("", "sistema"),
         "`auto` o trova la lingua di Windows o resta in italiano — "
         "e in nessuno dei due casi e' un guasto")

    # -- e adesso il pezzo che ha bisogno di Qt ------------------------------
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

    QApplication.instance() or QApplication([])

    # Una finestrella con dentro una chiave vera del catalogo, una marcata
    # `nontradurre` e un percorso di config.
    chiave = next(k for k in chiavi if k == "Avvia")
    radice = QWidget()
    layout = QVBoxLayout(radice)
    bottone = QPushButton(chiave)
    layout.addWidget(bottone)
    spiega = QLabel("Quanto acceso e' «colorato»")
    spiega.setProperty(L.MARCHIO, True)
    layout.addWidget(spiega)
    percorso = QLabel("vision.sat_max")
    layout.addWidget(percorso)

    raccolte = L.raccogli(radice)
    c.ok(chiave in raccolte, "l'estrazione vede il testo del bottone")
    c.ok("Quanto acceso e' «colorato»" not in raccolte,
         "e non vede quello marcato `nontradurre` — le spiegazioni dei campi "
         "vengono dai commenti di config, misure comprese, e non si traducono")
    c.ok("vision.sat_max" not in raccolte, "ne' il percorso del campo")

    tradotte, italiane = L.applica(radice, "en")
    c.ok(tradotte >= 1, f"applicando l'inglese qualcosa cambia ({tradotte})")
    c.eq(bottone.text(), L.carica("en")[chiave], "e il bottone dice quello del catalogo")
    c.eq(spiega.text(), "Quanto acceso e' «colorato»", "il marcato resta com'era")
    c.eq(percorso.text(), "vision.sat_max", "e il percorso pure")

    # **Il giro di ritorno, che e' la meta' che si dimentica.** Senza la memoria
    # dell'originale su ogni widget, il secondo cambio di lingua tradurrebbe una
    # traduzione: `Start` non e' una chiave del catalogo tedesco, quindi
    # resterebbe `Start` per sempre e l'italiano non tornerebbe piu'.
    L.applica(radice, "de")
    c.eq(bottone.text(), L.carica("de")[chiave],
         "cambiando lingua si riparte dall'italiano, non dall'inglese")
    L.applica(radice, "it")
    c.eq(bottone.text(), chiave, "e tornando all'italiano si ritrova il sorgente")
    c.eq(italiane + tradotte, len(raccolte),
         "il conto torna: ogni stringa e' o tradotta o lasciata in italiano")
    radice.deleteLater()


def test_percorsi(c: Check) -> None:
    """Dove il programma tiene i modelli, e la prova che il pacchetto porta.

    Due regole che si possono verificare **senza costruire un eseguibile**, che
    e' il punto: costruirlo costa dieci minuti e si fa altrove, ma la regola che
    decide dove finisce mezzo giga di modelli e' aritmetica e sta qui.
    """
    import ast

    from core import percorsi
    from tools import autoprova

    c.group("percorsi")

    radice = percorsi.radice()
    c.ok((radice / "core" / "percorsi.py").exists(),
         f"da sorgente la radice e' il repo ({radice})")
    c.eq(percorsi.modelli("piper"), radice / "models" / "piper",
         "`models/<cosa>` sta sotto la radice")
    c.ok("_internal" not in percorsi.modelli().parts,
         "e non dentro `_internal`, dove nel pacchetto stanno i .py")

    # Un percorso assoluto lo ha scritto qualcuno apposta: non si sposta.
    fuori = Path(tempfile.gettempdir()).resolve() / "lessico-mio"
    c.eq(percorsi.dato(fuori), fuori, "un percorso assoluto resta dov'e'")
    c.eq(percorsi.dato("models/lexicon"), radice / "models" / "lexicon",
         "uno relativo si risolve contro la radice, non contro la cartella di lancio")

    # **I quattro posti che cercavano `models/` per conto loro.** Erano quattro
    # formule uguali scritte in quattro file, e nel pacchetto ne bastava una
    # rimasta indietro per far riscaricare mezzo giga a ogni avvio.
    from listen.embed import ECAPA_DIR
    from speak.backends.kokoro import MODELS_DIR as KOKORO
    from speak.backends.piper import MODELS_DIR as PIPER
    from ui.qt_tema import _DISEGNI
    from vision.oneocr_worker import RUNTIME_DIR

    for nome, p in (("piper", PIPER), ("kokoro", KOKORO), ("ecapa", ECAPA_DIR),
                    ("oneocr", RUNTIME_DIR), ("ui", _DISEGNI)):
        c.ok(percorsi.modelli() in p.parents, f"{nome} cerca sotto models/ ({p.name})")

    # **L'elenco dei moduli nascosti si confronta col sorgente dello spec**, non
    # con la memoria di chi lo ha scritto: e' la stessa forma gia' usata per
    # `registro.banco()` e per le stringhe composte della finestra. Un
    # `hiddenimports` potato per sbaglio non da' errore alla costruzione — da' un
    # eseguibile che muore all'Avvia.
    sorgente = (Path(__file__).resolve().parent.parent / "livedub.spec").read_text(
        encoding="utf-8")
    dichiarati: set[str] = set()
    for nodo in ast.walk(ast.parse(sorgente)):
        if isinstance(nodo, ast.keyword) and nodo.arg == "hiddenimports":
            dichiarati = {v.value for v in nodo.value.elts if isinstance(v, ast.Constant)}
    c.ok(len(dichiarati) > 5, f"lo spec dichiara {len(dichiarati)} moduli nascosti")
    mancanti = [n for n in autoprova.NASCOSTI if n not in dichiarati]
    c.ok(not mancanti, f"e l'autoprova non ne cerca nessuno che lo spec non porti ({mancanti})")
    c.ok("tools.autoprova" in dichiarati,
         "l'autoprova stessa e' fra i nascosti, se no non c'e' niente da lanciare")

    # Ogni prova ha un nome solo, e ognuna dichiara cosa le serve: una prova che
    # chiedesse una cosa che il runner non ha e non lo dicesse verrebbe contata
    # come rotta invece che come saltata.
    nomi = [n for n, _, _ in autoprova.PROVE]
    c.eq(len(set(nomi)), len(nomi), "i nomi delle prove non si ripetono")
    c.ok(all(r in ("sempre", "rete", "qt") for _, _, r in autoprova.PROVE),
         "e ognuna dichiara se le serve la rete o Qt")


def test_tutorial(c: Check) -> None:
    """La guida iniziale: quando si apre, cosa scrive, e cosa dichiara di dire.

    Tre domande, e nessuna delle tre ha bisogno di guardare il dialogo:

    - **va mostrato?** e' una regola su un numero letto da un file, e sta in
      `core/preferenze.py` apposta — fuori da Qt, che e' l'unica parte del
      programma dove i difetti a freddo si erano nascosti tutti;
    - **saltarlo lo segna?** se no si riaprirebbe a ogni avvio, cioe' l'unica via
      d'uscita che gli si e' data lascerebbe il programma peggio di prima;
    - **quello che dice sta nei cataloghi?** un dialogo che non esiste finche'
      non lo si apre non lo trova nessuna passeggiata, e le sue parole
      uscirebbero in italiano in mezzo a una finestra tradotta.

    L'ultima e' l'unica che apre Qt, e lo apre per il motivo giusto: l'elenco
    dichiarato (`testi()`) si confronta con il dialogo **costruito davvero**,
    passo per passo. Un elenco a mano che nessuno confronta e' il modo in cui
    `COMPOSTE` sarebbe divergiuto al primo paragrafo aggiunto.
    """
    c.group("tutorial")

    import os
    import tempfile

    from core import preferenze as P

    # **Le preferenze vere non si toccano.** `tutorial_visto()` scrive in
    # `%LOCALAPPDATA%`: una suite che lo chiamasse per davvero segnerebbe la
    # guida come vista sulla macchina di chi la lancia, cioe' spegnerebbe la
    # cosa che sta verificando.
    vecchio = os.environ.get("LOCALAPPDATA")
    tana = tempfile.mkdtemp(prefix="livedub-pref-")
    os.environ["LOCALAPPDATA"] = tana
    try:
        c.ok(P.tutorial_da_mostrare({}),
             "senza preferenze la guida si apre: e' la prima volta")
        c.ok(not P.tutorial_da_mostrare({"tutorial_visto": P.TUTORIAL}),
             "vista una volta, non si riapre piu'")
        c.ok(P.tutorial_da_mostrare({"tutorial_visto": P.TUTORIAL - 1}),
             "ma una guida piu' nuova di quella vista si riapre: e' il motivo "
             "per cui e' un numero e non un «l'ho vista»")
        c.ok(P.tutorial_da_mostrare({"tutorial_visto": "boh"}),
             "e un valore che non si capisce vale «mai vista»: mostrarla una "
             "volta di troppo e' un fastidio, nasconderla e' il difetto")

        c.ok(P.tutorial_da_mostrare(), "sul disco pulito, quindi, va mostrata")
        P.tutorial_visto()
        c.ok(not P.tutorial_da_mostrare(),
             "e dopo averla segnata non va piu' mostrata — su disco, non solo "
             "in memoria")

        from ui import lingua as L
        from ui import tutorial as T

        # -- quello che dichiara di dire -------------------------------------
        voci = T.testi()
        c.ok(len(voci) > 30, f"la guida dichiara {len(voci)} stringhe")
        c.eq(len(set(voci)), len(voci), "senza doppioni")
        c.ok(all(v and v.strip() for v in voci), "e senza stringhe vuote")
        c.ok(all(L._traducibile(v) for v in voci),
             "e sono tutte traducibili: niente percorsi, glifi o HTML")

        # **I modelli dichiarati sono quelli usati davvero.** Stessa strada di
        # `COMPOSTE`: si legge il sorgente invece di rileggere l'elenco a occhio,
        # perche' un elenco a mano diverge e diverge in silenzio.
        import ast
        from pathlib import Path

        sorgente = Path(T.__file__)
        albero = ast.parse(sorgente.read_text(encoding="utf-8"))
        usati = {
            n.args[0].value
            for n in ast.walk(albero)
            if isinstance(n, ast.Call) and n.args
            and isinstance(n.func, ast.Name) and n.func.id == "_T"
            and isinstance(n.args[0], ast.Constant)
            and isinstance(n.args[0].value, str)
        }
        c.ok(usati, f"il sorgente compone davvero delle frasi ({len(usati)})")
        # **I perche' del banco sono modelli anche loro**, e non arrivano a `_T`
        # come letterali: `core/banco.py` parla per codici e la frase la sceglie
        # `MOTIVI`. Contarli qui e' l'unico modo di tenere vera la doppia
        # inclusione qui sotto — se no la seconda riga li dichiarerebbe
        # «avanzati» e li farebbe togliere dal catalogo.
        usati |= set(T.MOTIVI.values())
        c.eq(sorted(usati - set(T.MODELLI)), [],
             "ogni modello composto sta in `MODELLI`, se no uscirebbe in "
             "italiano in mezzo a una finestra tradotta")
        c.eq(sorted(set(T.MODELLI) - usati), [],
             "e non ce ne sono di avanzati, che sarebbero chiavi tradotte per niente")

        # I segnaposto reggono il giro: e se una traduzione li rompe si ricade
        # sull'italiano invece di far esplodere il dialogo.
        c.eq(T._T("passo {0} di {1}", "it", 2, 6), "passo 2 di 6",
             "un modello si riempie")

        # **E i segnaposto sopravvivono alla traduzione, in tutte le lingue.**
        # Questa e' la verifica che mancava, e la sua assenza aveva lasciato
        # passare un difetto muto: con i segnaposto scritti a nome — `{nome}`,
        # `{ocr}` — Google traduce anche cio' che sta **dentro** le graffe
        # (`{Name}`, `{имя}`, `{ن}`), `format` solleva, e il ripiego rimette
        # l'italiano. Tutte e quarantuno le lingue erano rotte cosi', e non lo
        # diceva niente: nessun errore, la suite verde, e ogni riga di verifica
        # del tutorial in italiano dentro una finestra tradotta.
        import string

        def _segnaposto(testo: str):
            try:
                return {f for _, f, _, _ in string.Formatter().parse(testo) if f is not None}
            except ValueError:
                return None

        rotti: list[str] = []
        for codice in L.disponibili():
            if codice == "it":
                continue
            catalogo = L.carica(codice)
            for modello in T.MODELLI:
                tradotto = catalogo.get(modello)
                if tradotto is None:
                    continue
                if _segnaposto(tradotto) != _segnaposto(modello):
                    rotti.append(f"{codice}: {modello!r} -> {tradotto!r}")
        c.eq(rotti, [],
             f"i segnaposto sopravvivono alla traduzione in tutte le lingue"
             + (f" — {len(rotti)} rotti, il primo: {rotti[0]}" if rotti else ""))

        # -- e finiscono nei cataloghi ---------------------------------------
        fuori = set(L.fuori_dalla_passeggiata())
        c.eq(sorted(set(voci) - fuori), [],
             "tutto quello che la guida dice passa da `fuori_dalla_passeggiata`")
        c.eq(sorted(set(L.COMPOSTE) - fuori), [],
             "e i pezzi composti della finestra ci sono ancora")
        chiavi = set(L.chiavi())
        c.eq(sorted(set(voci) - chiavi), [],
             "e sta nell'elenco delle chiavi: rilancia `tools/traduci_ui.py "
             "--estrai` se questa diventa rossa")

        # -- adesso il dialogo, costruito davvero ----------------------------
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from core.config import Config

        QApplication.instance() or QApplication([])
        cfg = Config()
        d = T.Tutorial(None, cfg=cfg)
        try:
            visto: set[str] = set()
            for i in range(len(T.PASSI)):
                visto |= set(L.raccogli(d))
                if i == 0:
                    # **La lingua scelta finisce in configurazione**, ed e' il
                    # primo passo della guida: senza, la scelta sarebbe una
                    # tendina che non fa niente.
                    codici = d._codici
                    c.ok("en" in codici, "l'inglese e' fra le lingue offerte")
                    d._lingua_scelta(codici.index("en"))
                    c.eq(cfg.ui.lingua, "en",
                         "scegliendo l'inglese, `ui.lingua` diventa `en`")
                    d._lingua_scelta(codici.index("it"))
                if i < len(T.PASSI) - 1:
                    d._avanti()
            c.eq(sorted(visto - set(voci)), [],
                 "il dialogo non dice niente che non abbia dichiarato")
            # Fuori dal conto ci sono i **modelli** (che a schermo arrivano gia'
            # riempiti, dentro widget `nontradurre`) e le stringhe che vivono
            # solo mentre il banco lavora, dichiarate in `SOLO_DURANTE`: la
            # passeggiata non attraversa quello stato, e pretenderlo qui
            # vorrebbe dire far girare un banco vero dentro la suite.
            non_composte = set(voci) - set(T.MODELLI) - set(T.SOLO_DURANTE)
            c.eq(sorted(non_composte - visto), [],
                 "e non dichiara niente che non dica: una riga elencata e mai "
                 "mostrata e' una chiave tradotta per niente")

            # **Il bottone dell'ultimo passo cambia davvero.** La passeggiata dei
            # cataloghi ricorda l'italiano di ogni widget, quindi un `setText`
            # normale li' non tiene: visto a schermo, «Ho capito» tornava
            # «Avanti» un istante dopo, senza nessun errore.
            cfg.ui.lingua = "en"
            d._mostra()
            c.eq(d.b_avanti.text(), L.carica("en")[T.FINE],
                 "all'ultimo passo il bottone chiude la guida, anche tradotto")
            d._indietro()
            c.eq(d.b_avanti.text(), L.carica("en")[T.AVANTI],
                 "e tornando indietro torna il passo successivo")
            cfg.ui.lingua = "it"
        finally:
            d.reject()

        # -- saltarlo e' finirlo, e non lascia niente a meta' ----------------
        P.scrivi({})
        c.ok(P.tutorial_da_mostrare(), "preferenze pulite: si riaprirebbe")
        prima = Config().ui.lingua
        d = T.Tutorial(None, cfg=Config())
        d._chiudi()
        c.ok(not P.tutorial_da_mostrare(),
             "saltarlo lo segna come visto: se no si riaprirebbe a ogni avvio, "
             "e saltarlo sarebbe peggio di non averlo mai aperto")
        c.eq(Config().ui.lingua, prima,
             "e chi lo salta senza toccare niente resta con la configurazione "
             "di prima")

        # -- e non si apre da solo su una finestra che non e' a schermo ------
        # `tools/scatta.py` e `tools/traduci_ui.py` costruiscono la finestra
        # senza mostrarla: un dialogo modale li' dentro li bloccherebbe per
        # sempre, e nessuno dei due sta nella suite.
        from tools.ui_qt import Finestra

        class _Finta:
            """La finestra ridotta alle **due** domande che la regola le pone.

            Erano una sola, e la suite si e' appesa per questo. Il doppio
            modellava soltanto `WA_DontShowOnScreen` e chiamava quel caso
            «costruita e non mostrata» — che e' un'altra cosa. Il gruppo
            `coerenza` costruisce la finestra e **non la mostra affatto**, senza
            dichiarare nessun attributo: il timer parte, `exec()` non torna piu',
            e la suite intera resta ferma oltre dieci minuti senza stampare una
            riga. Non rossa: appesa.

            La verifica diceva a parole la cosa giusta e la provava con il
            meccanismo sbagliato, cioe' non poteva fallire proprio nel caso per
            cui esisteva.
            """

            def __init__(self, *, visibile: bool, nascosta: bool = False) -> None:
                self._visibile = visibile
                self._nascosta = nascosta
                self.aperto = False

            def isVisible(self) -> bool:
                return self._visibile

            def testAttribute(self, _a) -> bool:
                return self._nascosta

            def apri_tutorial(self, prima_volta: bool = False) -> None:
                self.aperto = True

        P.scrivi({})
        mai_mostrata = _Finta(visibile=False)
        Finestra._forse_tutorial(mai_mostrata)
        c.ok(not mai_mostrata.aperto,
             "su una finestra costruita e mai mostrata la guida non si apre — "
             "e' il caso che ha appeso la suite")
        fuori_schermo = _Finta(visibile=True, nascosta=True)
        Finestra._forse_tutorial(fuori_schermo)
        c.ok(not fuori_schermo.aperto,
             "ne' su una dichiarata fuori schermo, come la costruiscono "
             "`tools/scatta.py` e `tools/traduci_ui.py`")
        vera = _Finta(visibile=True)
        Finestra._forse_tutorial(vera)
        c.ok(vera.aperto, "su una finestra vera, la prima volta, si'")
    finally:
        if vecchio is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = vecchio


def test_bloccati(c: Check) -> None:
    """Le rinunce dichiarate: **cosa non carica qui, e come lo si dice**.

    Gira senza Qt, senza rete e senza toccare i pacchetti veri: quello che si
    verifica e' la **regola**, cioe' la parte che decide come si racconta un
    blocco. La parte che misura sta sotto la riga di mezzo di `core/bloccati.py`
    e dipende da questa macchina, quindi qui non si guarda.

    I casi che contano sono tre, e sono tre modi di sbagliare gia' pagati:

    - **riconoscere il blocco in una lingua sola.** La frase con cui Windows
      dice «criterio di controllo» e' tradotta: cercarne una scritta a mano
      funzionerebbe qui e non altrove, e altrove il blocco tornerebbe a essere
      l'`ImportError` incomprensibile da cui si e' partiti;
    - **confondere «non installato» con «bloccato».** Sono due frasi diverse
      perche' chiedono all'utente due cose diverse: la prima si cura con un
      `pip install`, la seconda no;
    - **dichiarare a torto.** `ok` deve restare `ok`, se no il pannello marca
      con un `⚠` una scelta che funziona — e un avviso che nessuno puo'
      soddisfare si spegne da solo nella testa di chi lo legge.
    """
    c.group("bloccati")

    from core import bloccati as B

    # -- la frase la dice Windows, non noi -----------------------------------
    frase = B.frase_di_sistema()
    c.ok(bool(frase), "Windows sa dire con che frase blocca un file: la si "
                      "chiede a lui perche' e' tradotta, e una scritta a mano "
                      "riconoscerebbe il blocco solo sulle macchine italiane")

    class _Finta(OSError):
        pass

    con_numero = _Finta("qualcosa")
    con_numero.winerror = B.CODICE_CRITERIO
    c.ok(B.e_criterio(con_numero),
         "un `ctypes.CDLL` fallito porta il numero 4551 e si legge quello")
    c.ok(B.e_criterio(ImportError(
        f"DLL load failed while importing _x: {frase}")),
        "un `import` fallito non porta nessun numero — Python lascia solo il "
        "testo — e li' si confronta con la frase che il sistema stesso da'")
    c.ok(not B.e_criterio(ImportError("DLL load failed: modulo non trovato")),
         "e un errore qualunque non diventa un blocco: dichiarare a torto e' il "
         "ripiego silenzioso girato dall'altra parte")

    # -- importare non e' usare ----------------------------------------------
    B.dimentica()
    c.eq(B.prova("modulo_che_non_esiste_mai").stato, B.ASSENTE,
         "un modulo che non c'e' e' «assente», e si cura con un pip install")
    B.dimentica()

    def _muore(_m):
        raise ImportError(f"DLL load failed while importing _y: {frase}")

    e = B.prova("json", usa=_muore, nome="finto_bloccato")
    c.eq(e.stato, B.CRITERIO,
         "**importare non e' usare**: `piper` importa e muore alla prima "
         "sintesi, `llama_cpp` apre la sua DLL con ctypes. Per questo `prova` "
         "accetta un `usa`, e quello che solleva li' conta come il resto")
    c.ok(B.prova("json", usa=None, nome="finto_bloccato") is e,
         "e la risposta resta in cache: un `usa` puo' costare una sintesi vera")
    B.dimentica("finto_bloccato")
    c.ok(B.prova("json", nome="finto_bloccato").ok,
         "`dimentica` la butta via, se no chi installa dovrebbe riavviare")

    # -- le tre frasi dicono tre cose diverse --------------------------------
    riga = B.perche(B.Esito("x", B.CRITERIO), "la traduzione locale", "usa google")
    c.ok("Smart App Control" in riga and "cade la traduzione locale" in riga
         and "usa google" in riga,
         "la riga dice **cosa cade**, perche' e cosa fare: senza la prima e' "
         "una curiosita' tecnica, senza l'ultima e' una porta chiusa")
    c.ok("Smart App Control" not in B.perche(B.Esito("x", B.ASSENTE)),
         "«non installato» non si racconta come un blocco di Windows: manderebbe "
         "a cercare la cura sbagliata")
    c.ok(not B.Esito("x", B.OK).rinuncia and B.Esito("x", B.ASSENTE).rinuncia,
         "e le rinunce sono dichiarate come in `core.banco.AVVISI`: dare lo "
         "stesso segno di spunta a «funziona» e a «non c'e'» e' il ripiego "
         "silenzioso messo in figura")

    # -- la mappa fra pannello e pezzi ---------------------------------------
    from core.config import Config

    cfg = Config()
    for percorso, quali in B.SCELTE.items():
        c.ok(cfg.get(percorso) is not None,
             f"«{percorso}» e' un campo vero della configurazione")
        for valore, chiave in quali.items():
            c.ok(chiave in B.PEZZI,
                 f"«{percorso}={valore}» rimanda a un pezzo dichiarato")
    c.eq(B.scelte_indisponibili("campo.che.non.esiste"), {},
         "un campo che non dipende da niente non produce nessun avviso")

    # -- e la prova per il menu ha un tetto ----------------------------------
    # **Una prova che riesce puo' costare piu' di una che fallisce**: qui un
    # pacchetto bloccato risponde in 49-157 ms, ma `argostranslate` che
    # *funziona* tira dentro stanza e torch. Pagarli mentre si disegna una scheda
    # vorrebbe dire una finestra lenta per scrivere un avviso che quasi sempre
    # non serve. Sforato il tetto **non si marca**, che non promette niente —
    # marcare a torto sarebbe un avviso che nessuno puo' soddisfare.
    B.dimentica()
    lento = {"modulo": "time", "serve_a": "niente"}
    vecchio = B.PEZZI.get("finto_lento")
    vecchie_scelte = B.SCELTE.get("finto.campo")
    B.PEZZI["finto_lento"] = lento
    B.SCELTE["finto.campo"] = {"x": "finto_lento"}
    try:
        def _lentissimo(_m):
            import time as _t
            _t.sleep(0.4)
            raise ImportError(f"DLL load failed: {frase}")

        lento["usa"] = _lentissimo
        c.eq(B.scelte_indisponibili("finto.campo", entro_ms=20), {},
             "una prova che non risponde in tempo non marca niente: «non lo so "
             "ancora» non e' «non funziona»")
        # E intanto la prova e' andata avanti per conto suo: si aspetta il suo
        # comodo e la risposta c'e'.
        import time as _t

        for _ in range(60):
            if B._fatte.get("finto_lento") is not None:
                break
            _t.sleep(0.05)
        c.ok("x" in B.scelte_indisponibili("finto.campo"),
             "ma finisce in cache, quindi la scheda disegnata dopo l'avviso ce "
             "l'ha")
    finally:
        B.PEZZI.pop("finto_lento", None)
        if vecchio is not None:
            B.PEZZI["finto_lento"] = vecchio
        B.SCELTE.pop("finto.campo", None)
        if vecchie_scelte is not None:
            B.SCELTE["finto.campo"] = vecchie_scelte
        B.dimentica()

    # -- la rinuncia e' un'eccezione che si sa leggere ------------------------
    r = B.Rinuncia(B.Esito("llm", B.CRITERIO), "la traduzione llm")
    c.ok(isinstance(r, RuntimeError) and r.esito.stato == B.CRITERIO,
         "chi la prende decide cosa fare, ma la prende sapendo **cosa** e' "
         "successo: e' l'unica cosa che l'ImportError grezzo non diceva")


def test_finestra_gdi(c: Check) -> None:
    """La cattura di una finestra sola **senza nessuna libreria da installare**.

    `PrintWindow` sta in `user32.dll`, cioe' in Windows: fuori dal criterio per
    costruzione, dove `windows_capture` e `winrt-Windows.Graphics.Capture` sono
    bloccati in tutte le versioni pubblicate.

    Quello che si verifica qui e' la **geometria** e la **rinuncia**, non la
    qualita' dell'immagine: quella la si e' guardata, ed e' l'unico modo (una
    correzione geometrica si verifica sull'immagine).
    """
    c.group("finestra-gdi")

    from capture.printwindow import PrintWindowSource
    from capture.screen import fascia_da_roi

    # -- la fascia, in frazioni e non in pixel -------------------------------
    f = fascia_da_roi([(0.1, 0.80, 0.8, 0.10)], 0.08)
    c.ok(f is not None and abs(f[0] - 0.72) < 1e-6 and abs(f[1] - 0.98) < 1e-6,
         "la fascia prende la riga piu' il margine, che non e' prudenza: "
         "l'overlay sfoca i pixel attorno e **cresce verso l'alto**")
    c.eq(fascia_da_roi([]), None, "senza aree non c'e' niente da stringere")
    c.eq(fascia_da_roi([(0, 0.02, 1, 0.95)]), None,
         "e una fascia che copre quasi tutto non si ritaglia: non farebbe "
         "risparmiare niente e aggiungerebbe un modo di sbagliare")
    su, giu = fascia_da_roi([(0, 0.9, 1, 0.08)], 0.5)
    c.ok(su >= 0.0 and giu <= 1.0,
         "un margine grande non porta la fascia fuori dalla finestra")

    # -- la striscia si ricalcola sull'altezza di adesso ---------------------
    s = PrintWindowSource(0, fascia=(0.75, 0.95))
    c.eq(s._striscia(1000), (750, 200),
         "la striscia e' in **frazioni**: un gioco che passa a schermo intero "
         "cambia l'altezza, e una striscia in pixel finirebbe a leggere un altro "
         "punto **senza errore**")
    c.eq(s._striscia(400), (300, 80), "e a un'altra misura segue da sola")
    c.eq(PrintWindowSource(0)._striscia(720), (0, 720),
         "senza fascia si prende tutto")

    # -- il nero si dichiara, ma non troppo presto ---------------------------
    c.ok(not s.nero and not s.deciso,
         "appena aperta non dice niente: una finestra puo' dare un fotogramma "
         "vuoto prima di aver disegnato, e chiamarlo subito nero sarebbe una "
         "rinuncia dichiarata a torto")
    s._viste, s._con_pixel = 8, 0
    c.ok(s.nero and s.deciso,
         "guardati abbastanza fotogrammi e tutti neri, si dice: un fotogramma "
         "nero non e' un errore — la sessione resta accesa, i contatori restano "
         "verdi e sembra rotto l'OCR")
    s._con_pixel = 1
    c.ok(not s.nero,
         "**uno** che porta pixel basta: la domanda e' «si legge?», non «si "
         "legge sempre»")

    # -- una finestra che non esiste si dichiara chiusa ----------------------
    morta = PrintWindowSource(0)
    c.ok(morta.chiusa, "un hwnd che non e' una finestra e' «chiusa», non un giro "
                       "di grab a vuoto")
    c.ok(not morta.grab().ok, "e il suo fotogramma non c'e'")

    # -- su una finestra vera: geometria e costo -----------------------------
    from capture.finestre import elenco

    vere = elenco()
    if not vere:
        c.ok(True, "(nessuna finestra da catturare: la parte dal vivo si salta)")
        return
    v = vere[0]
    intera = PrintWindowSource(v.hwnd)
    g = intera.grab()
    c.ok(g.ok, "su una finestra vera il fotogramma arriva")
    if g.ok:
        alta, larga = g.frame.shape[:2]
        c.ok(larga == v.larghezza or abs(larga - v.larghezza) < 40,
             "ed e' largo quanto la finestra")
        con_fascia = PrintWindowSource(v.hwnd, fascia=(0.8, 0.95))
        g2 = con_fascia.grab()
        c.ok(g2.ok and g2.frame.shape == g.frame.shape,
             "**con la fascia il fotogramma resta grande uguale**: si reincolla "
             "in una tela della misura della finestra, perche' ROI e ritaglio "
             "dell'overlay sono in coordinate del fotogramma intero e "
             "consegnarne uno piu' piccolo vorrebbe dire cambiare quel sistema "
             "in cinque posti")
        if g2.ok:
            su, quanto = con_fascia._striscia(alta)
            fuori = g2.frame[:su]
            c.ok(fuori.size == 0 or int(fuori.max()) == 0,
                 "e fuori dalla fascia c'e' nero, non immagine vecchia")


def test_cuda(c: Check) -> None:
    """La CUDA: **dichiarare quella che si e' ottenuta**, e la strada per averla.

    Due meta' dello stesso difetto, visto nel pacchetto costruito in CI: il
    registro diceva `Failed to load cublasLt64_13.dll` e, tre righe piu' su,
    `onnxruntime.get_available_providers()` rispondeva `Tensorrt, CUDA, CPU`.
    Quel secondo elenco sono i provider **compilati dentro** onnxruntime, che e'
    un'altra domanda — e la guida al passo 6 la usava per scrivere «scheda video:
    CUDA» all'utente, due righe sopra il banco che scriveva «chiesto CUDA,
    ottenuto CPUExecutionProvider». Due righe dello stesso pannello che si
    contraddicono, e a mentire era quella che si legge **prima** di decidere.

    Gira senza rete e senza scheda video: le funzioni di `core/cuda.py` che
    decidono sono pure — prendono cio' che PyPI *avrebbe* risposto — e sono
    proprio i casi che su questa macchina non capitano mai (una ruota che manca
    per Windows, una versione di prova, una dipendenza di secondo livello).
    """
    c.group("cuda")

    import ast

    from core import cuda as CU
    from core import onnx as O

    # -- il modello da settanta byte deve **aprirsi** ------------------------
    # E' il perno di tutto: `cuda_ottenuta` risponde aprendo una sessione con
    # questi byte. Se non fossero un ONNX valido la funzione cadrebbe nel suo
    # `except` e direbbe «CPU» su **qualunque** macchina, GPU comprese — cioe' il
    # ripiego silenzioso rimesso al posto di quello che si era appena tolto, e
    # senza un errore da nessuna parte.
    try:
        import onnxruntime as rt

        sess = rt.InferenceSession(O._MODELLO_MINIMO,
                                   providers=["CPUExecutionProvider"])
        c.eq([e.name for e in sess.get_inputs()], ["x"],
             "il modello minimo e' un ONNX vero e si apre: se non lo fosse, "
             "`cuda_ottenuta` direbbe «CPU» su ogni macchina senza dare errore")
    except ImportError:
        c.ok(False, "onnxruntime non si importa: la CUDA non e' misurabile qui")

    # -- i tre esiti sono tre, e il terzo e' quello che serve ----------------
    ottenuta, com_e = O.cuda_ottenuta("la verifica")
    c.ok(isinstance(ottenuta, bool) and isinstance(com_e, str) and com_e,
         f"`cuda_ottenuta` risponde con un fatto e una frase: {com_e!r}")
    c.eq("CUDA" == com_e, ottenuta,
         "e la frase e il fatto dicono la stessa cosa: «CPU (CUDA non "
         "caricata)» contiene la parola CUDA e vuol dire il contrario")
    c.ok(O.cuda_ottenuta("la verifica") is O.cuda_ottenuta("la verifica"),
         "la risposta si tiene da parte: costa una sessione la prima volta e "
         "zero le successive")

    # **`dimentica()` puo' far cambiare idea da «no» a «si'», mai il contrario.**
    # Esiste per un istante solo — quello in cui 1,6 GB di DLL sono appena
    # arrivati sul disco — e senza di lei il programma continuerebbe a dire «CPU»
    # con le librerie li' accanto.
    O.dimentica()
    c.eq(O._cuda, None, "`dimentica()` butta via la risposta tenuta da parte")
    c.eq(O._precaricato, False, "e anche il precaricamento, che va rifatto "
                                "guardando la cartella nuova")
    c.eq(O.cuda_ottenuta("la verifica")[0], ottenuta,
         "e rifacendo la domanda si ottiene la stessa risposta di prima")

    # -- nessuno dichiara la CUDA leggendo l'elenco compilato ----------------
    # **L'elenco si ricava dal sorgente**, come per `registro.banco()`: una riga
    # nuova che chieda `get_available_providers()` per dire all'utente «c'e' la
    # scheda video» tornerebbe a mentire in silenzio, e nessuno andrebbe a
    # cercarla. I due posti che possono usarlo sono dichiarati qui, col perche'.
    radice = Path(__file__).resolve().parent.parent
    ammessi = {
        # e' lui che apre la sessione: prima di provare, guarda se c'e' qualcosa
        # da provare
        "core\\onnx.py",
        # la sua domanda **e'** l'elenco compilato: la ruota CPU installata
        # accanto a quella GPU lo cambia, ed e' esattamente cio' che va preso
        "tools\\controlla_traduzione.py",
        # il rapporto d'errore scrive **tutti e due** i numeri, `compilato:` e
        # `ottenuto:`, ed e' l'unico posto in cui il primo serve: chi legge una
        # segnalazione deve poter distinguere «senza scheda video» da «le DLL
        # non si caricano», che e' proprio la differenza che era sparita
        "core\\versione.py",
    }
    # **Si guarda il codice, non il testo.** Un `grep` conterebbe i commenti che
    # spiegano il difetto — cioe' dichiarerebbe colpevoli proprio i file che sono
    # stati curati, ed e' un modo perfetto di far spegnere una verifica.
    fuori_posto: list[str] = []
    for sorgente in sorted(radice.rglob("*.py")) + sorted(radice.glob("*.ps1")):
        parti = sorgente.relative_to(radice).parts
        if parti[0] in (".venv", "dist", "build", "runs", "models", ".git"):
            continue
        testo = sorgente.read_text(encoding="utf-8", errors="replace")
        if "get_available_providers" not in testo:
            continue
        if sorgente.suffix == ".py":
            chiamato = any(
                isinstance(n, ast.Attribute) and n.attr == "get_available_providers"
                for n in ast.walk(ast.parse(testo)))
        else:
            # PowerShell: via i commenti, e resta cio' che esegue davvero.
            chiamato = any("get_available_providers" in r.split("#")[0]
                           for r in testo.splitlines())
        nome = str(sorgente.relative_to(radice))
        if chiamato and nome not in ammessi:
            fuori_posto.append(nome)
    c.eq(fuori_posto, [],
         "solo `core/onnx.py` e `tools/controlla_traduzione.py` guardano "
         "l'elenco dei provider **compilati**: chiunque altro sta rispondendo "
         "«c'e' la CUDA» a chi ha chiesto «la sto usando»")

    # -- da dove viene l'elenco delle librerie -------------------------------
    # **Non e' scritto qui.** Le distribuzioni vengono dagli extra di
    # `onnxruntime-gpu`, i nomi dei file da `onnxruntime._get_nvidia_dll_paths`,
    # cioe' dalla funzione che ORT usa per caricarli: una seconda tabella
    # divergerebbe verso il verde — un nome vecchio darebbe «scaricato» su una
    # cartella incompleta.
    finti = [
        "numpy >=1.21.6",
        'nvidia-cudnn-cu13 ~=9.0; extra == "cudnn"',
        'nvidia-cufft ~=12.0; extra == "cuda"',
        'onnx ; extra == "training"',
    ]
    c.eq(sorted(n for n, _ in CU.distribuzioni(finti)),
         ["nvidia-cudnn-cu13", "nvidia-cufft"],
         "degli extra si tengono le sole distribuzioni NVIDIA che li attivano")
    c.eq(CU.distribuzioni(finti, extra=("cudnn",)),
         (("nvidia-cudnn-cu13", "~=9.0"),),
         "e ogni extra porta le sue, col vincolo attaccato")
    c.eq(CU.dipendenze(["nvidia-cublas ~=13.0", "setuptools",
                        'nvidia-x ; extra == "y"']),
         (("nvidia-cublas", "~=13.0"),),
         "e si sale sulle dipendenze **senza marcatore**: `nvidia-cudnn` chiede "
         "`nvidia-cublas`, che chiede `nvidia-nvjitlink`, e nessuno dei due "
         "compare nei requisiti di ORT")

    # -- quale versione, e la ruota giusta -----------------------------------
    # Misurato il 24 agosto: `nvidia-cudnn-cu13` aveva pubblicato la 9.25.0.15
    # **senza la ruota Windows**, con cinque `.devN` ancora piu' recenti sopra.
    # Chi si fermasse alla piu' alta direbbe «per questa macchina non c'e' CUDA»
    # con la 9.24 li' accanto che va benissimo.
    c.eq(CU.versioni_buone(["9.24.0.1", "9.25.0.15", "9.26.0.dev1", "8.9.0"],
                           "~=9.0"),
         ("9.25.0.15", "9.24.0.1"),
         "le versioni buone tornano **tutte**, dalla piu' recente in giu', e "
         "senza le build di prova: la ruota giusta fa parte della scelta")
    c.eq(CU.versioni_buone(["9.1.0"], "~=13.0"), (),
         "e un vincolo che nessuna soddisfa non ripiega su niente")
    rilascio = [
        {"filename": "nvidia_x-1.0-py3-none-manylinux_2_28_x86_64.whl", "url": "l"},
        {"filename": "nvidia_x-1.0-py3-none-win_amd64.whl", "url": "w", "size": 7},
    ]
    c.eq(CU.ruota(rilascio).get("url"), "w",
         "si prende la ruota Windows a 64 bit e non la prima che capita: una "
         "manylinux si scarica benissimo e dentro non ha nessuna DLL")
    c.eq(CU.ruota([{"filename": "nvidia_x-1.0-py3-none-win_amd64.whl",
                    "url": "w", "yanked": True}]), {},
         "e una ruota ritirata non e' una ruota")
    c.eq(CU.ruota(rilascio[:1]), {},
         "senza ruota per questa macchina si dice «non c'e'», non si ripiega")

    # -- dentro la ruota, e dentro la cartella -------------------------------
    c.eq(CU.dll_dentro(["nvidia/cu13/bin/x86_64/cublas64_13.dll",
                        "nvidia/cublas/bin/altro.dll",
                        "nvidia_x-1.0.dist-info/RECORD"]),
         ("nvidia/cu13/bin/x86_64/cublas64_13.dll", "nvidia/cublas/bin/altro.dll"),
         "le DLL si riconoscono dal **nome del file** e non dalla cartella: "
         "NVIDIA l'ha gia' cambiata una volta passando da CUDA 12 a 13")
    c.eq(CU.manca(["cuBLAS64_13.dll", "cudnn64_9.dll"], ["cublas64_13.DLL"]),
         ("cudnn64_9.dll",),
         "e il confronto e' senza maiuscole, perche' Windows non le distingue e "
         "le ruote non sono coerenti fra loro (`nvJitLink_130_0.dll`)")
    c.eq(CU.manca(["a.dll"], ["a.dll", "b.dll"]), (),
         "una DLL in piu' non fa mancare niente")

    # -- dove finiscono, e quanto pesano -------------------------------------
    from core.percorsi import radice as radice_programma

    c.eq(CU.cartella(), radice_programma() / "models" / "cuda",
         "le DLL stanno sotto `models/`, che e' materiale della macchina, e "
         "ancorate alla radice del programma: chi apre l'exe da un'altra "
         "cartella non deve ritrovarsi due copie da 1,6 GB")
    from core.banco import PEZZI

    c.eq(PEZZI["cuda"].mb, CU.MB_RETE,
         "il peso che il banco dichiara **prima** e' quello che si scarica "
         "davvero, non quello che occupa poi sul disco")
    c.ok(CU.MB_DISCO > CU.MB_RETE,
         f"e sul disco pesa di piu' ({CU.MB_DISCO} contro {CU.MB_RETE} MB): le "
         "ruote sono compresse")
    c.ok(PEZZI["cuda"].mb > max(p.mb for k, p in PEZZI.items() if k != "cuda"),
         "ed e' il pezzo piu' pesante di tutti, piu' del modello piu' grande: "
         "e' l'unico che si scarica per una **scelta** e non perche' la catena "
         "ne abbia bisogno per partire")

    # -- «c'e'» vuol dire «c'e' tutto» ---------------------------------------
    # Un archivio a meta' e' precisamente il difetto costato un `KeyError` dentro
    # `kokoro_onnx`, lontanissimo da dove stava: chi mette qualcosa in cache
    # controlli **cosa** c'e' dentro, non che ci sia.
    chiesti = CU.nomi_dll()
    if chiesti:
        c.ok(all(n.lower().endswith(".dll") for n in chiesti),
             f"i nomi da trovare li elenca chi li carica ({len(chiesti)} DLL), "
             "non una tabella scritta qui")
        c.eq(CU.manca(chiesti, chiesti[:-1]), (chiesti[-1],),
             "e a una cartella a cui ne manca uno **manca**: con una cartella a "
             "meta' `preload_dlls` carica cio' che trova e tace su cio' che non "
             "trova, e il provider poi non si apre")
    else:
        c.ok(True, "questo onnxruntime non sa elencare le DLL di NVIDIA: la "
                   "cartella si dichiara incompleta, che e' il ripiego prudente")


def test_banco(c: Check) -> None:
    """Il mini banco della guida: **quali motori, dati questi numeri**.

    Gira **senza toccare niente**: nessuna GPU, nessuna rete, nessun modello sul
    disco, nessun Qt. E' il punto di tutto `core/banco.py` — la parte che misura
    e la parte che decide stanno separate proprio perche' la seconda si possa
    provare con numeri finti, compresi i casi che su questa macchina non
    capitano mai.

    I casi che contano sono quattro, e tre sono il **ripiego silenzioso** visto
    da tre lati diversi:

    - niente CUDA -> Piper, perche' Kokoro su CPU costa 725 ms contro 207;
    - CUDA **dichiarata** e non **ottenuta**: chiedere un acceleratore non e'
      ottenerlo, ed e' il difetto che `core/onnx.py` esiste per chiudere;
    - CUDA ottenuta ma millisecondi da CPU: una sessione puo' dire «CUDA» e
      andare lo stesso piano;
    - il modello scaricato a meta': senza `dopo_lo_scarico` resterebbe scritto
      `tts.backend = kokoro` con i pesi non sul disco.
    """
    c.group("banco")

    from dataclasses import replace

    from core import banco as B

    # -- la scelta, con numeri finti -----------------------------------------
    senza = B.scegli(B.Sonda(cuda=False, argos=True))
    c.eq(senza.tts, "piper",
         "senza CUDA la voce e' Piper: Kokoro sulla CPU costa 725 ms a battuta "
         "contro 207, cioe' non e' vivibile")
    c.eq(senza.traduzione, "locale",
         "e la traduzione e' quella locale, che vince di un fattore sette e non "
         "manda niente fuori dal PC")

    con = B.scegli(B.Sonda(cuda=True, argos=True))
    c.eq(con.tts, "kokoro", "con CUDA si prova Kokoro")

    # **Dichiarata non e' ottenuta.** E' la riga per cui `Sonda.provider` esiste
    # separato da `Sonda.cuda`.
    bugia = B.scegli(B.Sonda(cuda=True, provider="CPUExecutionProvider"))
    c.eq(bugia.tts, "piper",
         "CUDA dichiarata ma sessione aperta sulla CPU: si torna a Piper — "
         "chiedere un acceleratore non e' ottenerlo")
    c.ok(any(m.codice == "cuda_persa" for m in bugia.motivi),
         "e lo dice, perche' un ripiego che non si dichiara e' peggio di un errore")

    lenta = B.scegli(B.Sonda(cuda=True, provider="CUDAExecutionProvider",
                             sintesi_ms=B.SINTESI_MAX_MS + 1))
    c.eq(lenta.tts, "piper",
         "e una GPU che consegna i tempi di una CPU non basta averla: contano i "
         "millisecondi, non il nome del provider")
    veloce = B.scegli(B.Sonda(cuda=True, provider="CUDAExecutionProvider",
                              sintesi_ms=B.SINTESI_MAX_MS - 1))
    c.eq(veloce.tts, "kokoro", "sotto la soglia invece resta Kokoro")

    # **Una misura puo' solo retrocedere.** Promuovere Piper a Kokoro perche' un
    # numero e' venuto bello vorrebbe dire scegliere il motore che compete con il
    # gioco per la GPU sulla base di una prova fatta a gioco spento.
    c.eq(B.scegli(B.Sonda(cuda=False, sintesi_ms=10.0, passo=20.0)).tts, "piper",
         "e nessuna misura promuove: da Piper non si sale")

    corto = B.scegli(B.Sonda(cuda=True, provider="CUDAExecutionProvider",
                             sintesi_ms=100.0, passo=B.PASSO_MINIMO - 1))
    c.eq(corto.tts, "piper",
         "un motore che produce meno parlato di quanto la scena ne contenga "
         "esce comunque: e' la domanda che ha tolto il quarto motore, e la "
         "latenza non c'entrava")

    # -- la traduzione --------------------------------------------------------
    c.eq(B.scegli(B.Sonda(argos=False, llm=True)).traduzione, "llm",
         "senza Argos si ripiega sul modello in memoria, che resta in locale")
    nessuna = B.scegli(B.Sonda(argos=False, llm=False, traduzione_accesa=True))
    c.eq(nessuna.traduzione, "",
         "e senza nessuno dei due **non si sceglie**: l'unica alternativa che "
         "funzionerebbe sempre e' google, che manda i sottotitoli fuori dal PC")
    c.ok(any(m.codice == "traduzione_manca" and B.RIGA_PIP in m.valori
             for m in nessuna.motivi),
         "si consegna la riga di pip invece di eseguirla: `onnxruntime` e "
         "`onnxruntime-gpu` non convivono, e un'installazione da dentro "
         "spegnerebbe la CUDA in silenzio")
    # **E la riga consegnata deve installare la traduzione.** Era
    # `pip install -r requirements.txt`, che dal 25 agosto argostranslate non lo
    # porta piu': una riga da incollare che non fa la cosa per cui la si incolla
    # e' peggio di nessuna riga.
    c.ok("installa_traduzione" in B.RIGA_PIP,
         "la riga consegnata e' lo script che mette Argos con `--no-deps`, non "
         "un `pip install -r requirements.txt` che non lo installa affatto")
    # **Il peso si dice prima, perche' e' il numero su cui uno decide.**
    c.ok(any(m.codice == "traduzione_manca" and B.TRADUZIONE_MB in m.valori
             for m in nessuna.motivi),
         f"e con quanto pesa ({B.TRADUZIONE_MB} MB): un'attesa dichiarata e' "
         "un'attesa, un'attesa muta e' una finestra bloccata")
    # **Con la traduzione spenta non e' una notizia, e' rumore.** Su GTA V in
    # italiano non c'e' niente da tradurre: senza questa riga l'avviso ambra
    # ce l'avrebbero tutti, e gli avvisi che nessuno deve soddisfare si spengono
    # da soli nella testa di chi li legge.
    zitta = B.scegli(B.Sonda(argos=False, llm=False, traduzione_accesa=False))
    c.ok(not any(m.codice == "traduzione_manca" for m in zitta.motivi),
         "e non lo si dice a chi la traduzione non l'ha accesa")
    piano = B.scegli(B.Sonda(argos=True, traduzione_ms=B.TRADUZIONE_MAX_MS + 1))
    c.ok(any(m.codice == "traduzione_lenta" for m in piano.motivi),
         "una traduzione che sfora l'attesa di `decide_after_ms` si dichiara: "
         "sotto quella soglia e' gratis, sopra si paga intera")

    # -- cosa serve, e cosa manca --------------------------------------------
    su_gpu = B.Scelta(tts="kokoro", traduzione="locale")
    serve_gpu = B.serve(su_gpu, traduzione=False)
    c.ok("kokoro" in serve_gpu and "piper" not in serve_gpu,
         "si scarica il motore scelto e non gli altri: 326 MB per un motore che "
         "non verra' acceso sono 326 MB")
    c.ok("traduzione" not in serve_gpu,
         "e con la traduzione spenta la coppia di lingue non si prende: la "
         "scarica `make_traduttore` quando la si accende, dichiarandolo")
    c.ok("traduzione" in B.serve(su_gpu, traduzione=True),
         "accesa si'")
    c.ok("ecapa" in B.serve(B.Scelta(tts="piper"), traduzione=False),
         "l'impronta della voce serve a tutti i motori")

    # -- le librerie della scheda video ---------------------------------------
    # **1,1 GB non li decide una misura.** Senza CUDA `scegli()` sceglie Piper, e
    # Piper non chiedera' mai le DLL che gliela farebbero avere: il giro si
    # chiuderebbe su se stesso. Quindi la domanda «le vuoi?» arriva da fuori — e
    # fuori vuol dire la configurazione, cioe' chi ha **scelto** il motore che
    # gira su GPU.
    c.ok("cuda" not in B.serve(su_gpu, traduzione=False),
         "le librerie CUDA non entrano da sole: sono il pezzo piu' pesante di "
         "tutti e nessuna misura puo' dire se convengano")
    c.ok("cuda" in B.serve(B.Scelta(tts="piper"), cuda=True),
         "entrano quando le si e' chieste, **anche col motore leggero**: nel "
         "pacchetto la CUDA non viaggia, quindi il primo giro sceglie Piper e "
         "solo dopo le DLL la macchina cambia")

    from core.config import Config as _Cfg

    _c = _Cfg()
    _c.tts.backend, _c.tts.device = "piper", "auto"
    c.eq(B.vuole_cuda(_c), False,
         "`auto` non chiede la scheda video: vuol dire «vedi tu», e vedere tu "
         "non puo' voler dire scaricare un gigabyte")
    _c.tts.device = "cuda"
    c.eq(B.vuole_cuda(_c), True, "scritto `cuda` a mano si', ed e' una scelta")
    _c.tts.backend, _c.tts.device = "kokoro", "auto"
    c.eq(B.vuole_cuda(_c), True,
         "e chi sceglie Kokoro ha gia' chiesto la GPU: e' l'unico motore che ci "
         "gira, e su CPU costa 725 ms a battuta contro 207")

    # **«Le DLL ci sono, questo avvio no.»** Un terzo stato, e non un dettaglio:
    # ORT carica le sue librerie una volta per processo, quindi appena scaricate
    # la sessione di adesso e' gia' partita sulla CPU. Dire «niente scheda video»
    # sarebbe falso, dire «CUDA» sarebbe peggio.
    riavvia = B.scegli(B.Sonda(cuda=False, cuda_da_riavviare=True))
    c.eq(riavvia.tts, "piper",
         "con le DLL appena arrivate **non** si promette Kokoro: scriverlo in "
         "configurazione vorrebbe dire aprirlo sulla CPU alla prima battuta, "
         "con l'aria di aver funzionato")
    c.ok(any(m.codice == "cuda_riavvia" for m in riavvia.motivi),
         "e si dice l'unica cosa vera: riaprendo il programma cambia")
    c.ok("cuda_riavvia" in B.AVVISI,
         "ed e' un avviso e non una spunta verde, perche' c'e' ancora qualcosa "
         "da fare")
    c.ok(not any(m.codice == "cuda_riavvia"
                 for m in B.scegli(B.Sonda(cuda=True, cuda_da_riavviare=True)).motivi),
         "con la CUDA gia' ottenuta invece non c'e' niente da riavviare")

    c.eq(B.da_scaricare(("ecapa", "piper"), {"piper"}), ("ecapa",),
         "quello che c'e' gia' non si riscarica")
    c.eq(B.da_scaricare(("ecapa", "piper"), {"ecapa", "piper"}), (),
         "e con tutto sul disco non si scarica niente")
    c.ok(B.peso_mb(("kokoro", "voci_kokoro")) > B.peso_mb(("piper",)),
         "i megabyte si dicono prima: un'attesa dichiarata e' un'attesa, "
         "un'attesa muta e' una finestra bloccata")

    # -- e se il modello non arriva -------------------------------------------
    meta = B.dopo_lo_scarico(B.Scelta(tts="kokoro"), {"ecapa", "kokoro"})
    c.eq(meta.tts, "piper",
         "pesi arrivati e stili no: non e' «quasi», e' un motore che alla prima "
         "battuta non parte")
    c.ok(any(m.codice == "motore_mancante" for m in meta.motivi), "e si dice")
    intero = B.dopo_lo_scarico(B.Scelta(tts="kokoro"),
                               {"ecapa", "kokoro", "voci_kokoro"})
    c.eq(intero.tts, "kokoro", "con tutti e due i pezzi resta Kokoro")
    c.eq(B.dopo_lo_scarico(B.Scelta(tts="piper"), set()).tts, "piper",
         "e su Piper non c'e' niente da retrocedere")

    # -- i perche' hanno tutti una frase, in ogni lingua ----------------------
    # E' la stessa forma di `COMPOSTE` e dei modelli del tutorial: due elenchi
    # che devono coincidere e che nessuno confronterebbe a occhio. Un codice
    # senza frase esce come una **riga vuota** — nessun errore, e la
    # spiegazione sparita.
    from ui import tutorial as T

    c.eq(sorted(set(B.MOTIVI) - set(T.MOTIVI)), [],
         "ogni motivo che `scegli()` puo' produrre ha la sua frase")
    c.eq(sorted(set(T.MOTIVI) - set(B.MOTIVI)), [],
         "e non ce ne sono di avanzati")
    c.eq(sorted(set(B.PEZZI) - set(T.PEZZI_NOMI)), [],
         "e ogni pezzo scaricabile ha un nome da mostrare mentre si scarica")
    c.eq(sorted(B.AVVISI - set(B.MOTIVI)), [],
         "gli avvisi sono motivi veri, non nomi rimasti indietro")
    c.ok("cuda_no" not in B.AVVISI,
         "«nessuna scheda video» non e' un avviso: e' un fatto, e Piper e' la "
         "risposta giusta")
    c.ok("cuda_persa" in B.AVVISI,
         "«chiesta la GPU e ottenuta la CPU» si', perche' li' qualcosa e' "
         "andato storto — e una schermata tutta verde sopra un ripiego e' il "
         "ripiego silenzioso messo in figura")

    # Tutti i motivi si riempiono davvero: un segnaposto di troppo qui
    # sarebbe una riga che ricade sull'italiano in tutte e quarantuno le lingue.
    for codice in B.MOTIVI:
        riga = T.motivo_in_riga(B.Motivo(codice, ("x", "y")), "it")
        c.ok(riga and "{" not in riga, f"il motivo `{codice}` diventa una frase")

    # -- quello che si scrive in configurazione -------------------------------
    from core.config import Config

    cfg = Config()
    cfg.tts.backend = "supertonic"
    esito = B.Referto(B.Scelta(tts="piper", traduzione="locale"),
                      B.Sonda(presenti=frozenset()))
    toccati = B.applica(cfg, esito)
    c.eq(cfg.tts.backend, "piper", "la scelta finisce in configurazione")
    c.ok("vision.ocr_backend" not in toccati,
         "ma OneOCR non si accende se i suoi file non sono arrivati: sarebbe "
         "una catena che non parte, con la scusa che il banco aveva promesso")
    c.ok("tts.device" not in toccati,
         "e `tts.device` lo legge solo Kokoro: scriverlo su Piper sarebbe il "
         "settimo campo dichiarato e mai letto di questo progetto")

    cfg2 = Config()
    B.applica(cfg2, B.Referto(B.Scelta(tts="kokoro"),
                              B.Sonda(presenti=frozenset({"oneocr"}))))
    c.eq(cfg2.tts.device, "cuda",
         "con Kokoro si scrive `cuda` e non `auto`: la GPU e' stata ottenuta su "
         "una sessione vera, quindi da qui in poi un ripiego deve sollevare")
    c.eq(cfg2.vision.ocr_backend, "oneocr",
         "e OneOCR si accende quando i suoi file ci sono davvero")

    # -- la guida e' cresciuta, quindi si rivede ------------------------------
    from core import preferenze as P

    c.ok(P.TUTORIAL >= 2,
         "la guida ha un passo in piu' che installa roba: il numero di versione "
         "e' salito, quindi la rivede anche chi l'aveva gia' vista — e' "
         "esattamente il caso per cui e' un numero e non un «l'ho vista»")


def test_registro(c: Check) -> None:
    """Il registro dice cosa e' successo — e chi simula scrive in un altro file.

    **Il difetto che questo gruppo chiude era gia' costato una sessione.** Nel
    registro dell'utente c'erano 122 righe «l'audio si e' fermato» e **zero**
    vere: 56 dalle schermate (`tools/scatta.py`) e 64 dalla suite, scritte per
    avere qualcosa da fotografare o da controllare e finite nello stesso file
    dove finiscono i guasti veri. Il 17 agosto le venti righe `-9988` cadono
    tutte fra le 18:23 e le 18:55, e le uniche quattro sessioni dal vivo di quel
    giorno partono alle 19:06: il ciclo audio, quando quel messaggio e' stato
    scritto, non era ancora mai partito.

    Tre domande, e nessuna ha bisogno di aprire una finestra:

    - **come si chiama il file?** e' una regola pura (`nome`), e sta in
      `core/registro.py` per lo stesso motivo per cui `colore_stato` sta in
      `core/motore.py`;
    - **la riga finta arriva altrove davvero?** si scrive e si guarda il disco,
      con la commutazione fatta a registro **gia' aperto**, che e' il caso
      difficile;
    - **chi costruisce la finestra fuori dal vivo lo dichiara?** l'elenco non si
      scrive, si **ricava** dal sorgente: il canale e' `Finestra.__init__`, e
      qualunque strumento nuovo che costruisca una finestra tornerebbe a
      sporcare senza che niente lo dica.
    """
    c.group("registro")

    import ast
    import datetime as dt
    import fnmatch
    import os
    import tempfile
    from pathlib import Path

    from core import registro as R

    # -- la regola, senza toccare il disco ---------------------------------
    giorno = dt.date(2026, 8, 17)
    vero_nome = R.nome(giorno, False)
    banco_nome = R.nome(giorno, True)
    c.eq(vero_nome, "livedub-2026-08-17.log", "il registro dell'utente porta la data")
    c.eq(banco_nome, "livedub-banco-2026-08-17.log",
         "e quello di banco si distingue **dal nome**: chi apre la cartella deve "
         "poterli separare senza aprirli")
    # La pulizia dei sette giorni conta una famiglia per volta, e il glob deve
    # tenerle separate: con un `livedub-*.log` solo, un pomeriggio di schermate
    # avrebbe fatto scadere il registro vero.
    forma = f"{R.PREFISSO}-????-??-??.log"
    c.ok(fnmatch.fnmatch(vero_nome, forma), "il glob della pulizia prende il registro vero")
    c.ok(not fnmatch.fnmatch(banco_nome, forma),
         "e non prende quello di banco: sette giorni di schermate non fanno "
         "scadere il registro di ieri")

    # -- e sul disco, con la commutazione a registro gia' aperto ------------
    # In una tana di passaggio: una suite che scrivesse davvero nel registro
    # dell'utente per provare che non ci scrive sarebbe la verifica che si
    # guarda allo specchio.
    vecchio = os.environ.get("LOCALAPPDATA")
    era_di_banco = R.di_banco()
    tana = tempfile.mkdtemp(prefix="livedub-log-")
    os.environ["LOCALAPPDATA"] = tana
    try:
        R.banco(False)
        R.chiudi()
        R.apri()
        vero_file = R.file_oggi()
        c.ok(vero_file.name.startswith(f"{R.PREFISSO}-2"),
             "dal vivo si scrive nel registro dell'utente")
        R.scrivi("! l'audio si e' fermato: un guasto vero")
        quanto_era = vero_file.stat().st_size
        c.ok(quanto_era > 0, "e quello che si scrive ci arriva davvero")

        R.banco()
        banco_file = R.file_oggi()
        c.ok(banco_file != vero_file, "chi simula scrive in un altro file")
        R.scrivi("! l'audio si e' fermato: OSError: [Errno -9985] Device unavailable")
        c.eq(vero_file.stat().st_size, quanto_era,
             "e il registro dell'utente non cresce di un byte")
        # **La riga non sparisce**: sparire in silenzio sarebbe lo stesso difetto
        # girato dall'altra parte, cioe' quello che questa cura sta chiudendo.
        c.ok(banco_file.exists() and "Device unavailable" in
             banco_file.read_text(encoding="utf-8"),
             "ma la riga non sparisce: sta nel registro di banco, leggibile")

        R.banco(False)
        c.eq(R.file_oggi(), vero_file,
             "e si torna indietro: la scelta e' del processo, non del file")
    finally:
        R.chiudi()
        # **Si rimette lo stato di prima, e non si lascia acceso il banco.**
        # Lasciandolo acceso, i gruppi che aprono una finestra troverebbero il
        # lavoro gia' fatto da qui, e la verifica che sta in `menta_finestra` —
        # «il registro dell'utente non cresce» — non potrebbe piu' fallire nel
        # caso per cui esiste, cioe' quel gruppo che smette di dichiararlo.
        R.banco(era_di_banco)
        if vecchio is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = vecchio

    # -- chi costruisce la finestra fuori dal vivo lo dichiara --------------
    def _chiamato(n) -> str:
        if isinstance(n.func, ast.Name):
            return n.func.id
        if isinstance(n.func, ast.Attribute):
            return n.func.attr
        return ""

    strumenti = Path(__file__).resolve().parent
    costruttori: list[str] = []
    zitti: list[str] = []
    for sorgente in sorted(strumenti.glob("*.py")):
        # `ui_qt.py` e' il vivo: il registro dell'utente e' proprio il suo.
        if sorgente.name == "ui_qt.py":
            continue
        albero = ast.parse(sorgente.read_text(encoding="utf-8"))
        nomi = {_chiamato(n) for n in ast.walk(albero) if isinstance(n, ast.Call)}
        if "Finestra" not in nomi:
            continue
        costruttori.append(sorgente.name)
        if "banco" not in nomi:
            zitti.append(sorgente.name)
    c.ok(len(costruttori) >= 4,
         f"gli strumenti che costruiscono la finestra fuori dal vivo sono "
         f"{len(costruttori)}: {', '.join(costruttori)}")
    c.eq(zitti, [],
         "e ognuno dichiara `registro.banco()`: l'elenco si ricava dal sorgente, "
         "cosi' uno strumento nuovo non puo' tornare a sporcare in silenzio")



def test_lingue_voci(c: Check) -> None:
    """I cataloghi delle voci, e la regola che sposta il motore sulla lingua.

    Gira **senza rete, senza modelli e senza Qt**: i cataloghi sono tabelle nel
    repo e `motore_per_lingua` e' aritmetica su di esse. E' il punto — la regola
    sta in `core/motore.py` proprio per poterla provare qui invece che dentro la
    finestra, che e' l'unica parte del programma dove i difetti si trovano solo
    rileggendola a freddo.
    """
    from core.banco import Sonda
    from core.motore import (
        CAMBIATO, INVARIATO, MUTA, ORDINE_MOTORI, motore_per_lingua,
        motori_possibili,
    )
    from speak.backends import kokoro as K
    from speak.backends import piper_voci as PV
    from speak.backends import supertonic as ST
    from speak.pool import basi_per, build_pool, lingue_con_voce, voce_neutra

    # -- i cataloghi ---------------------------------------------------------
    c.eq(len(PV.VOCI), 51, "l'indice ufficiale di piper ha 51 lingue")
    c.eq(sum(len(v) for v in PV.VOCI.values()), 175, "e 175 voci")
    # **Cinquanta e non cinquantuno, e la differenza e' il punto.** La voce
    # giapponese usa `phoneme_type: japanese`, che `piper-tts` non conosce: il
    # modello si scarica e la prima sintesi solleva. Dichiarare 51 sarebbe vero
    # sull'indice e falso in questo programma.
    c.eq(len(PV.LINGUE), 50, "ma quelle che questo programma sa dire sono 50")
    c.ok("ja" in PV.VOCI and "ja" not in PV.LINGUE,
         "il giapponese c'e' nell'indice e non fra le nostre: e' dichiarato")
    c.eq(PV.voci_per("ja", 4), (),
         "e non se ne offre nessuna, invece di offrirne una che muore alla sintesi")
    c.eq(len(ST.LINGUE), 31, "supertonic-3 ne parla 31 con le stesse dieci voci")
    c.eq(len(K.PER_LINGUA), 8, "kokoro ne ha 8, scritte nel nome delle voci")
    c.eq(len(K.VOICES), 54, "e 54 voci in tutto")

    # **Il percorso si ricava dalla chiave, e su tutte e 175.** E' l'unica cosa
    # che tiene questo catalogo senza una seconda tabella da aggiornare: se la
    # regola valesse su 174 su 175, l'unica che sfugge darebbe un 404 al primo
    # download di quella lingua e nient'altro.
    male = [k for lista in PV.VOCI.values() for k in lista
            if len(k.split("-")) != 3
            or not PV.sottopercorso(k).endswith(k.split("-")[2])]
    c.eq(male, [], "il percorso HF si ricava dalla chiave per tutte le voci")

    # **La tabella scritta due volte, presa mentre si scrive.** L'elenco delle
    # lingue di SuperTonic sta nel repo perche' un elenco che dipende da un
    # import si svuota quando quell'import non c'e'; che le due copie non
    # divergano lo dice questa riga, e solo qui, dove il pacchetto c'e' davvero.
    try:
        import supertonic as _st

        c.eq(sorted(ST.LINGUE), sorted(_st.SUPPORTED_LANGUAGES),
             "e l'elenco scritto nel repo e' quello del pacchetto")
    except ImportError:  # pragma: no cover - dipende dall'ambiente
        c.ok(True, "(supertonic non installato: elenco non confrontabile)")

    # **Ogni lingua di Kokoro ha le sue regole di fonemizzazione.** Il difetto da
    # cui viene questa riga: `FONEMI_LINGUA` elencava gia' es/fr/de/pt e le voci
    # no — la fonemizzazione era pronta per lingue che il pool non sapeva
    # parlare, e le voci di sette lingue restavano invisibili.
    c.eq(sorted(K.FONEMI_LINGUA), sorted(K.PER_LINGUA),
         "le lingue di kokoro e le loro regole di fonemizzazione coincidono")

    # -- il pool, lingua per lingua ------------------------------------------
    # **Nessun `voice_id` doppio, in nessuna lingua di nessun motore.** Due voci
    # con lo stesso nome vorrebbero dire due personaggi che il pool crede uno:
    # `assegnata()` risponderebbe di un altro, e nessun contatore lo direbbe. Il
    # caso che l'ha fatto capitare: `de_DE-thorsten-medium` e
    # `de_DE-thorsten-high` sono **la stessa persona** a due qualita'.
    doppi, vuoti = [], []
    for backend in ("piper", "supertonic", "kokoro"):
        for lingua in lingue_con_voce(backend):
            if not basi_per(backend, lingua):
                vuoti.append((backend, lingua))
                continue
            ids = [v.voice_id
                   for v in build_pool(None, 6, backend=backend, lingua=lingua)]
            if len(set(ids)) != len(ids):
                doppi.append((backend, lingua, ids))
    c.eq(doppi, [], "nessuna lingua costruisce due voci con lo stesso nome")
    c.eq(vuoti, [], "e ogni lingua dichiarata ha almeno una voce da cui partire")

    # L'italiano e l'inglese non si muovono: sono le combinazioni su cui e' stata
    # fatta ogni misura scritta in CLAUDE.md, e un pool diverso renderebbe quei
    # numeri riferiti a un'altra cosa.
    c.eq([v.voice_id for v in build_pool(None, 6, backend="piper", lingua="it")],
         ["riccardo", "paola", "riccardo-2_5", "paola+2", "riccardo+2_5",
          "paola-2_5"],
         "il pool italiano di piper e' quello di sempre")
    c.eq([v.voice_id for v in build_pool(None, 6, backend="kokoro", lingua="en")],
         ["michael", "heart", "fenrir", "bella", "george", "emma"],
         "e le sei inglesi di kokoro restano le sei scelte")
    c.eq([v.voice_id for v in build_pool(None, 2, backend="kokoro", lingua="it")],
         ["nicola", "sara"],
         "l'italiano di kokoro non prende le inglesi della sua famiglia")

    # La voce d'attesa segue la lingua: presa dalla famiglia italiana mentre la
    # scena e' in spagnolo sarebbe **la prima battuta di ogni personaggio nuovo**
    # detta con i fonemi sbagliati.
    es = build_pool(None, 6, backend="kokoro", lingua="es")
    c.ok(voce_neutra(es, "kokoro", "es").base_voice in K.PER_LINGUA["es"],
         "la voce neutra e' della lingua che si parla, non dell'italiano")

    # Una voce che nessun catalogo conosce resta un errore all'avvio: un pool
    # costruito su un refuso e' una sessione che muore alla prima battuta con la
    # configurazione stampata verde.
    c.raises(ValueError, lambda: build_pool(("inesistente",)),
             "una voce fuori da tutti i cataloghi e' un errore, non un ripiego")
    c.raises(ValueError, lambda: PV.parlante("en_US-libritts-high#5000"),
             "e un parlante fuori scala pure: piper non lo rifiuta, cambia voce")

    # -- la regola che sceglie il motore -------------------------------------
    gpu = Sonda(cuda=True, provider="CUDAExecutionProvider", sintesi_ms=210.0)
    cpu = Sonda(cuda=False)

    c.eq(motore_per_lingua("it", "piper", gpu).codice, INVARIATO,
         "se il motore che c'e' parla la lingua non succede niente")
    c.eq(motore_per_lingua("it", "piper", gpu).avviso, "",
         "e non si scrive niente: un avviso a ogni cambio e' rumore")
    c.eq(motore_per_lingua("de", "piper", gpu).codice, INVARIATO,
         "piper parla tedesco, quindi non si cambia motore per il tedesco")
    # Il giapponese e' il caso che fa vedere tutto il meccanismo: Piper ha la
    # voce e non la sa dire, Kokoro ne ha cinque ma vuole la CUDA, SuperTonic la
    # parla su CPU. La risposta cambia con la macchina, ed e' giusto cosi'.
    c.eq(motore_per_lingua("ja", "piper", gpu).motore, "kokoro",
         "il giapponese con la CUDA va a kokoro")
    c.eq(motore_per_lingua("ja", "piper", cpu).motore, "supertonic",
         "e senza, a supertonic: non si passa a kokoro su una macchina senza GPU")

    croato = motore_per_lingua("hr", "piper", gpu)
    c.eq((croato.motore, croato.codice), ("supertonic", CAMBIATO),
         "il croato lo parla solo supertonic, e il motore ci si sposta da solo")
    c.ok(croato.avviso,
         "e questa volta lo si dice, perche' e' stata scavalcata una scelta")

    muta = motore_per_lingua("am", "piper", gpu)
    c.eq((muta.motore, muta.codice), ("piper", MUTA),
         "l'amarico non lo parla nessuno: si tiene quello che c'e' e si dichiara")

    c.eq(motore_per_lingua("ja", "tone", gpu).codice, INVARIATO,
         "un bip non ha lingua: non gli si cambia motore sotto i piedi")

    # **La clausola sulla macchina, che e' meta' della decisione.** Kokoro su CPU
    # costa 725 ms a battuta contro i 207 su CUDA: passarci sopra
    # automaticamente vorrebbe dire consegnare una latenza doppia per aver
    # seguito una lingua. Il giudizio e' quello di `core.banco.scegli`, non un
    # secondo giudizio scritto qui.
    c.ok("kokoro" in motori_possibili(gpu), "con la CUDA kokoro e' fra i candidati")
    c.ok("kokoro" not in motori_possibili(cpu),
         "senza, no — e lo dice il banco, non questa regola")
    c.eq(motori_possibili(None), ORDINE_MOTORI,
         "e senza sonda non si toglie niente: «non lo so» non e' «no»")

    lenta = Sonda(cuda=True, provider="CUDAExecutionProvider", sintesi_ms=900.0)
    c.ok("kokoro" not in motori_possibili(lenta),
         "una CUDA che va come una CPU retrocede, ed e' la stessa riga del banco")

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
    "anticipo": test_anticipo,
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
    # **L'area la disegna l'utente**: stretta o larga, la battuta si legge lo
    # stesso. Il cancello del diff normalizzava sull'area, quindi la stessa
    # battuta valeva meno in un'area piu' grande — fino a non passare piu'.
    "cancello": test_cancello_area,
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
    # L'unico gruppo che apre l'OCR **vero**, e l'unico che guarda un gioco che
    # non e' GTA V. Sta in fondo perche' costa qualche secondo (il worker
    # OneOCR va acceso) e perche' e' il solo che possa dire «questa suite gira
    # su una macchina senza il modello».
    "gioco2": test_gioco2,
    "schema": test_schema,
    "livelli": test_livelli,
    "limiti": test_limiti,
    "memoria": test_memoria,
    "sessione_mix": test_sessione,
    "due_sessioni": test_due_sessioni,
    "ripresa": test_ripresa,
    "guasto_audio": test_guasto_audio,
    "uscita_audio": test_uscita_audio,
    # **Quali motori su questa macchina**, con numeri finti: niente GPU, niente
    # rete, niente modelli, niente Qt. La regola sta in `core/banco.py` proprio
    # per poter provare qui i casi che su questo PC non capitano mai.
    # Le rinunce dichiarate stanno **prima** del banco: e' il banco a dipendere
    # da loro, perche' «questo pacchetto c'e'?» adesso vuol dire «si carica?».
    "bloccati": test_bloccati,
    "finestra-gdi": test_finestra_gdi,
    # **La CUDA dichiarata contro la CUDA ottenuta**, e la strada per prendersi
    # le librerie che nel pacchetto non viaggiano. Sta prima del banco perche' e'
    # il banco a dipenderne: `Sonda.cuda` adesso vuol dire «una sessione l'ha
    # presa», non «ORT e' stato compilato con quel provider».
    "cuda": test_cuda,
    "banco": test_banco,
    # Il registro su file, e la regola che tiene fuori chi simula. Sta prima dei
    # gruppi che aprono una finestra, perche' sono loro a doverla rispettare.
    "registro": test_registro,
    "solo_roi": test_solo_roi,
    # **Cosa resta acceso dopo Ferma.** Cinque cicli e si confronta con prima:
    # una cattura di finestra lasciata indietro non da' errore, copia il gioco a
    # ogni fotogramma e fa invecchiare tutto il resto.
    "catture": test_catture,
    # I due cicli fuori dalle finestre, e le due finestre che li chiamano.
    "motore": test_motore,
    # **In che stato e' la sessione, e quali bottoni ne conseguono.** La regola
    # sta in `core/motore.py` e non nella finestra, come `colore_stato`: e' cosi'
    # che si prova senza aprire Qt lo stato in cui il programma si e' piantato —
    # «avviato» scritto sopra un Avvia premibile che non faceva niente.
    "stato": test_stato_sessione,
    "overlay_base": test_overlay_base,
    "overlay_quando": test_overlay_quando,
    # I controlli della finestra: quale manopola per quale campo, e la
    # rotellina che non deve toccare niente attraversando la pagina.
    "manopole": test_manopole,
    # Una configurazione, sei schede: le viste non possono divergere.
    "coerenza": test_coerenza,
    # **Menta**: la tavolozza, la geometria e le due regole del documento che,
    # rotte, non danno errore — la marca di gravita' e le soglie della barra
    # della misura. Gira senza aprire una finestra, che e' il punto: quello che
    # si puo' provare senza Qt deve stare fuori da Qt.
    "menta": test_menta,
    "menta_regole": test_regole_finestra,
    "menta_finestra": test_finestra_menta,
    # Le lingue: quelle del doppiaggio (la tabella, chi le sa fare, chi ha una
    # voce) e quella della finestra (i cataloghi, e cosa resta in italiano).
    "lingue": test_lingue,
    "lingue_voci": test_lingue_voci,
    "ui_lingua": test_ui_lingua,
    # La guida iniziale: quando si apre, che saltarla la chiude per sempre, e
    # che quello che dice sta nei cataloghi — un dialogo che non esiste finche'
    # non lo si apre nessuna passeggiata lo trova.
    # **Dove finisce mezzo giga di modelli**, che e' una regola e non un
    # dettaglio dell'eseguibile: da sorgente le due formule sbagliate coincidono,
    # nel pacchetto no. Qui c'e' anche il confronto fra cio' che l'autoprova
    # cerca e cio' che `livedub.spec` dichiara.
    "percorsi": test_percorsi,
    "tutorial": test_tutorial,
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
