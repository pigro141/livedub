"""Banco di chi parla: stesse impronte, raggruppamento diverso.

    python -m tools.dub video.mp4 --profile gtav --start 1240 --end 1340 \\
        --set vision.ocr_backend=oneocr --dump-speaker runs\\banco\\speaker.jsonl
    python -m tools.recluster runs\\banco\\speaker.jsonl --sweep speaker.merge_similarity 0.55:0.95:0.05

La prima riga costa una passata di OCR, la seconda cinquanta millisecondi per
soglia. E' lo stesso rapporto — e la stessa ragione — di `replay --dump-reads`
seguito da `tools/retrack.py`: due tarature confrontate su due esecuzioni diverse
del video sarebbero confrontate anche su tutto il rumore che le separa, e qui il
rumore e' proprio cio' che si sta cercando di togliere.

Il registro contiene **tutto** l'ingresso del tracker: l'impronta breve con cui
si e' scelta la voce (`scegli`) e quella intera da cui si e' imparato (`impara`).
Rigiocarle nell'ordine riproduce la sessione battuta per battuta.

## Perche' i numeri sono due e non uno

Contare le identita' e basta premia il rimedio peggiore del male. Una soglia di
fusione abbastanza bassa unisce tutti in un personaggio solo: una identita', zero
frammenti, e all'ascolto tre persone con la stessa voce — cioe' il punto di
partenza da cui si e' venuti via. Quindi, ogni volta che ci sono le etichette:

- **frammentazione**: quante identita' per personaggio reale. Deve scendere a 1;
- **purezza**: quanti personaggi reali dentro un'identita'. Deve restare 1.

Nessuna delle due, da sola, puo' dire di no. Insieme si'.

E la guardia che vale anche senza etichette: **le battute gia' dette non devono
cambiare voce**. Una fusione sposta il perdente sulla voce del vincitore, e quel
costo si paga e si conta (`assorbite`); ma il vincitore — chi ha parlato di piu'
— non deve cambiare voce mai, e quel numero deve essere zero. Un personaggio con
la voce sbagliata e' una scelta discutibile, uno che cambia voce a meta' scena e'
un errore evidente.

## Le etichette

Si costruiscono a orecchio, una volta per registrazione:

    python -m tools.recluster runs\\banco\\speaker.jsonl --wav 2026-07-25.mp4 --offset 1240

scrive un WAV per identita' del raggruppamento **base** (fusione spenta) — le sue
battute in fila, mezzo secondo di silenzio in mezzo — e un modello di file da
riempire. Si ascolta, si scrive un nome accanto a ogni identita', e da li' in poi
ogni taratura ha una risposta contro cui misurarsi. E' lo stesso protocollo che
aveva gia' dato i tre gruppi puliti su questa scena, solo scritto su file.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, load_profile  # noqa: E402
from listen.speaker import SpeakerTracker  # noqa: E402
from speak.pool import VoicePool, build_pool, voce_neutra, voce_per  # noqa: E402


def load(path: str | Path) -> list[dict]:
    """Le righe del registro che parlano di una battuta.

    Il registro contiene anche note di servizio — quale impronta sta girando, per
    esempio — che non hanno un istante e non vanno rigiocate. Filtrarle qui e non
    a valle evita che ogni lettore debba ricordarsene.
    """
    righe = Path(path).read_text(encoding="utf-8").splitlines()
    tutti = [json.loads(r) for r in righe if r.strip()]
    return [r for r in tutti if r.get("kind") in ("scegli", "impara")]


def note(path: str | Path) -> list[dict]:
    """Le note di servizio del registro: cio' che `load` lascia fuori."""
    righe = Path(path).read_text(encoding="utf-8").splitlines()
    tutti = [json.loads(r) for r in righe if r.strip()]
    return [r for r in tutti if r.get("kind") not in ("scegli", "impara")]


@dataclass
class Detta:
    """Una battuta pronunciata durante la rigiocata: chi, con che voce."""

    t_on: float
    text: str
    sid: str
    voice_id: str


@dataclass
class Esito:
    """Cio' che resta di una rigiocata: i numeri, e chi ha detto cosa."""

    tracker: SpeakerTracker
    pool: VoicePool
    dette: list[Detta]
    imparate: list[tuple[dict, str]]  # (record, identita' che ha imparato)

    @property
    def identita(self) -> int:
        return len(self.tracker)

    @property
    def solitarie(self) -> int:
        """Identita' con una battuta sola: il sintomo diretto della frammentazione."""
        return sum(1 for p in self.tracker.attivi if p.battute <= 1)

    @property
    def fusioni(self) -> int:
        return len(self.tracker.fusioni)

    def cambi_voce(self) -> tuple[int, int, int]:
        """(assorbite, in_attesa, tradite): due prezzi dichiarati, e il difetto.

        *assorbite* sono le battute di un'identita' poi confluita in un'altra;
        *in attesa* quelle dette con la voce neutra prima di sapere il sesso.
        Tutte e due sono prezzi scelti, e si contano per sapere quanto costano.

        *tradite* e' un'altra cosa: un'identita' **sopravvissuta**, che non stava
        aspettando niente, e che parla con una voce diversa da quella che ha
        adesso. Quello non e' un prezzo, e' il difetto peggiore della lista, e
        deve restare zero.
        """
        assorbite = attesa = tradite = 0
        for b in self.dette:
            finale = self.pool.assegnata(b.sid)
            if finale is None or finale.voice_id == b.voice_id:
                continue
            if b.voice_id == "neutra":
                attesa += 1
            elif self.tracker.risolvi(b.sid) != b.sid:
                assorbite += 1
            else:
                tradite += 1
        return assorbite, attesa, tradite


def rigioca(records: list[dict], cfg: Config, *, mescola: int | None = None) -> Esito:
    """Rifa' girare tracker e pool sulle impronte registrate.

    `mescola` e' il caso nullo: permuta le impronte fra le battute lasciando i
    tempi dove sono. La scena, la durata, l'alternanza restano identiche; l'unica
    cosa che cambia e' **chi** e' chi. Se le fusioni non crollano, non e'
    l'identita' a produrle.
    """
    imparare = [r for r in records if r["kind"] == "impara" and r.get("emb")]
    scambio: dict[int, list] = {}
    if mescola is not None:
        rng = np.random.default_rng(mescola)
        impronte = [r["emb"] for r in imparare]
        rng.shuffle(impronte)
        scambio = {id(r): e for r, e in zip(imparare, impronte)}

    tracker = SpeakerTracker(cfg.speaker)
    pool = VoicePool(build_pool(cfg.tts.voices, cfg.tts.pool_size, backend=cfg.tts.backend))
    neutra = voce_neutra(pool.voices, backend=cfg.tts.backend)
    dette: list[Detta] = []
    imparate: list[tuple[dict, str]] = []

    for r in records:
        grezza = scambio.get(id(r), r.get("emb"))
        emb = np.asarray(grezza, dtype=np.float32) if grezza else None
        t = float(r["t_on"])
        if r["kind"] == "scegli":
            d = tracker.scegli(emb, t=t)
            sid = d.speaker_id
            p = tracker.get(sid)
            voce = voce_per(
                pool, sid, p, t, neutra=neutra,
                defer_max=cfg.speaker.gender_defer_max_lines,
                ripiego=cfg.speaker.gender_fallback,
                anonima=d.anonima,
            )
            dette.append(Detta(t_on=t, text=r.get("text", ""), sid=sid, voice_id=voce.voice_id))
        else:
            d = tracker.impara(emb, t=t, f0=float(r.get("f0", 0.0)))
            if d.merged is not None:
                pool.merge(*d.merged)
            imparate.append((r, d.speaker_id))
    return Esito(tracker=tracker, pool=pool, dette=dette, imparate=imparate)


# -- le etichette, e i due numeri che servono insieme ------------------------


def base(records: list[dict], cfg: Config) -> Esito:
    """Il raggruppamento **senza fusione**: la chiave su cui poggiano le etichette.

    Le identita' cambiano nome a ogni taratura; quelle di base no, perche' non
    dipendono da nessun parametro in discussione. Etichettare quelle una volta
    sola rende confrontabili tutte le rigiocate che verranno.
    """
    fermo = copy.deepcopy(cfg)
    fermo.speaker.merge = False
    return rigioca(records, fermo)


def verita(records: list[dict], cfg: Config, etichette: dict[str, str]) -> dict[float, str]:
    """Da «S3 e' Simeon» a «la battuta al secondo 1247,3 e' di Simeon»."""
    return {
        float(r["t_on"]): etichette[sid]
        for r, sid in base(records, cfg).imparate
        if sid in etichette
    }


def confronta(esito: Esito, per_battuta: dict[float, str]) -> tuple[float, float, str]:
    """(frammentazione, purezza, dettaglio). Uno solo dei due non dice niente."""
    per_identita: dict[str, list[str]] = {}
    per_persona: dict[str, set[str]] = {}
    for r, sid in esito.imparate:
        nome = per_battuta.get(float(r["t_on"]))
        if nome is None:
            continue
        vivo = esito.tracker.risolvi(sid)
        per_identita.setdefault(vivo, []).append(nome)
        per_persona.setdefault(nome, set()).add(vivo)

    if not per_identita:
        return 0.0, 0.0, "(nessuna battuta etichettata)"
    frammentazione = sum(len(v) for v in per_persona.values()) / len(per_persona)
    purezza = sum(len(set(v)) for v in per_identita.values()) / len(per_identita)
    righe = [f"  {nome:<12} {len(ids)} identita': {', '.join(sorted(ids))}" for nome, ids in sorted(per_persona.items())]
    sporche = [
        f"  {sid} contiene {len(set(nomi))} persone: {', '.join(sorted(set(nomi)))}"
        for sid, nomi in sorted(per_identita.items())
        if len(set(nomi)) > 1
    ]
    return frammentazione, purezza, "\n".join(righe + sporche)


# -- l'ascolto: un WAV per identita' ----------------------------------------


def scrivi_wav(
    records: list[dict],
    cfg: Config,
    video: str,
    offset: float,
    cartella: Path,
    samplerate: int = 48000,
) -> None:
    """Un file per identita' di base, le sue battute in fila. Poi si ascolta.

    Il **centro** del segnale, non il mixdown: e' li' che sta il dialogo ed e' lo
    stesso estratto su cui lavora il tracker. Giudicare a orecchio un audio
    diverso da quello che la catena tratta risponderebbe a un'altra domanda.
    """
    import wave

    from mix.center import split
    from tools.sources import AudioPipe

    esito = base(records, cfg)
    durata = max(float(r.get("t_off") or r["t_on"]) for r, _ in esito.imparate) + 2.0
    pipe = AudioPipe(video, samplerate=samplerate, channels=2, start=offset, end=offset + durata)
    stereo = pipe.read(int(durata * samplerate))
    pipe.close()
    centro, _ = split(stereo)

    cartella.mkdir(parents=True, exist_ok=True)
    silenzio = np.zeros(int(0.5 * samplerate), np.float32)
    per_identita: dict[str, list[np.ndarray]] = {}
    for r, sid in esito.imparate:
        t0 = max(0.0, float(r["t_on"]) - 0.2)
        t1 = min(float(r.get("t_off") or (t0 + 2.5)), t0 + 4.0)
        a, b = int(t0 * samplerate), int(t1 * samplerate)
        if b <= a or a >= len(centro):
            continue
        per_identita.setdefault(sid, []).append(centro[a : min(b, len(centro))])
        per_identita[sid].append(silenzio)

    modello = {}
    for sid, pezzi in sorted(per_identita.items()):
        audio = np.concatenate(pezzi)
        path = cartella / f"{sid}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(samplerate)
            w.writeframes((np.clip(audio, -1.0, 1.0) * 32000).astype("<i2").tobytes())
        battute = sum(1 for _, s in esito.imparate if s == sid)
        print(f"  {sid:>4}  {battute:>3} battute  {len(audio)/samplerate:5.1f}s  -> {path}")
        modello[sid] = "?"
    modello_path = cartella / "etichette.json"
    if not modello_path.exists():
        modello_path.write_text(json.dumps(modello, indent=2), encoding="utf-8")
        print(f"\nscritto il modello da riempire: {modello_path}")
        print("si ascolta, si mette un nome al posto di ogni '?', e poi --etichette")
    else:
        print(f"\n{modello_path} esiste gia': non lo sovrascrivo")


# -- stampa -----------------------------------------------------------------


def riga(esito: Esito) -> str:
    assorbite, attesa, tradite = esito.cambi_voce()
    return (
        f"identita' {esito.identita:>3}   con una battuta sola {esito.solitarie:>3}   "
        f"fusioni {esito.fusioni:>3}   voci {len(esito.pool):>2}   "
        f"assorbite {assorbite:>3}   in attesa {attesa:>3}   tradite {tradite:>3}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.recluster",
        description="Rifa' il raggruppamento di chi parla su impronte gia' registrate.",
    )
    ap.add_argument("registro", help="JSONL prodotto da tools.dub --dump-speaker")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    ap.add_argument(
        "--sweep",
        nargs=2,
        metavar=("CHIAVE", "DA:A:PASSO"),
        help="una riga per valore, es. speaker.merge_similarity 0.55:0.95:0.05",
    )
    ap.add_argument("--shuffle", action="store_true", help="il caso nullo: impronte permutate")
    ap.add_argument("--etichette", default=None, help="JSON identita' di base -> nome, dall'ascolto")
    ap.add_argument("--wav", default=None, metavar="VIDEO", help="scrivi un WAV per identita' di base")
    ap.add_argument("--offset", type=float, default=0.0, help="il --start con cui e' stato registrato")
    ap.add_argument("--out", default=None, help="cartella dei WAV (di suo, accanto al registro)")
    ap.add_argument("--show", type=int, default=0, help="elenca le prime N battute dette")
    args = ap.parse_args(argv)

    cfg = (
        load_profile(args.profile, args.overrides)
        if args.profile
        else Config().apply(args.overrides)
    )
    records = load(args.registro)
    if not records:
        print(f"nessuna impronta in {args.registro}", file=sys.stderr)
        return 2
    for nota in note(args.registro):
        print(f"  nota: {nota}")
    n_scelte = sum(1 for r in records if r["kind"] == "scegli")
    n_imparate = sum(1 for r in records if r["kind"] == "impara")
    span = max(float(r["t_on"]) for r in records) - min(float(r["t_on"]) for r in records)
    print(f"{n_scelte} battute dette, {n_imparate} imparate, su {span:.0f}s\n")

    if args.wav:
        cartella = Path(args.out) if args.out else Path(args.registro).parent / "voci"
        scrivi_wav(records, cfg, args.wav, args.offset, cartella)
        return 0

    per_battuta: dict[float, str] = {}
    if args.etichette:
        etichette = json.loads(Path(args.etichette).read_text(encoding="utf-8"))
        etichette = {k: v for k, v in etichette.items() if v and v != "?"}
        per_battuta = verita(records, cfg, etichette)
        print(f"{len(per_battuta)} battute etichettate su {n_imparate}, "
              f"{len(set(per_battuta.values()))} personaggi reali\n")

    if args.sweep:
        chiave, intervallo = args.sweep
        da, a, passo = (float(x) for x in intervallo.split(":"))
        valori = [round(da + i * passo, 6) for i in range(int(round((a - da) / passo)) + 1)]
        for v in valori:
            prova = copy.deepcopy(cfg).apply([f"{chiave}={v}"])
            esito = rigioca(records, prova)
            testo = f"{v:>6.3f}   {riga(esito)}"
            if per_battuta:
                fr, pu, _ = confronta(esito, per_battuta)
                testo += f"   frammentazione {fr:4.2f}   purezza {pu:4.2f}"
            print(testo)
        return 0

    esito = rigioca(records, cfg, mescola=0 if args.shuffle else None)
    print(("caso nullo (impronte permutate): " if args.shuffle else "") + riga(esito))
    print()
    print(esito.tracker.report())
    print()
    print(esito.pool.report())
    if per_battuta:
        fr, pu, dettaglio = confronta(esito, per_battuta)
        print(f"\nframmentazione {fr:.2f} identita' per personaggio "
              f"(1 = perfetta)   purezza {pu:.2f} personaggi per identita' (1 = pulita)")
        print(dettaglio)
    if args.show:
        print()
        for b in esito.dette[: args.show]:
            print(f"  t={b.t_on:8.2f}s  {b.sid:>4} -> {b.voice_id:<14} {b.text[:52]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
