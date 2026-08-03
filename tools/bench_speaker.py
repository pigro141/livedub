"""Quanta voce serve per riconoscere chi parla? E il grigio dice davvero
che e' cambiato qualcuno?

    python -m tools.bench_speaker --clean
    python -m tools.bench_speaker gameplay.mp4 --profile gtav --start 1400 --end 1700

E' la misura che viene **prima** del tracker, e il piano lo dice esplicitamente.
La pipeline ha bisogno dell'identita' entro ~300 ms dalla comparsa del
sottotitolo; un embedding di speaker ne vuole di norma 1–1,5 s. O quella curva
dice che a 300 ms si decide, o il tracker va progettato intorno a una rete di
sicurezza — e progettarlo prima di sapere quale dei due casi vale significa
scrivere codice che forse non serve, o peggio, che serve e non c'e'.

## Il problema: qui non c'e' una risposta giusta scritta da qualche parte

Sulla registrazione non c'e' nessuna etichetta di speaker. "Accuratezza" quindi
non si legge, si **costruisce**, e il modo di costruirla e' tutta la misura:

- **positivi**: due ritagli **non contigui** della stessa presa di parola. Non
  contigui perche' due meta' attaccate condividono anche le code dei fonemi;
- **negativi**: ritagli di prese di parola diverse.

I negativi sono sporchi per costruzione — due battute lontane possono essere lo
stesso personaggio — ma sporcano nel verso giusto: fanno sembrare il
riconoscimento **peggiore** di com'e'. Un risultato buono nonostante loro e'
vero; un risultato cattivo va guardato due volte.

## Cio' che rende la misura capace di dire di no

C'e' un modo perfetto di prendere 100% su questo protocollo senza riconoscere
nessuna voce: descrivere la **scena**. Due ritagli della stessa presa di parola
hanno la stessa musica di fondo, lo stesso motore, la stessa stanza; due prese
di parola lontane no. Un'impronta che codificasse solo il canale separerebbe
benissimo, e la curva sarebbe indistinguibile da quella di un riconoscitore che
funziona.

Per questo qui si stampano sempre, accanto alla curva, tre cose che possono
smentirla:

1. **lo stesso protocollo sul non-parlato.** Ritagli presi dove il VAD dice
   silenzio, positivi e negativi costruiti allo stesso modo. Li' dentro non c'e'
   nessuna voce da riconoscere: tutto cio' che separa e' scena. Se separa quanto
   il parlato, la curva sopra non parlava di voci;
2. **negativi vicini contro negativi lontani.** Due prese di parola a pochi
   secondi di distanza stanno quasi sempre nella stessa scena; a un minuto no.
   Se il riconoscimento regge solo sui lontani, sta datando l'audio, non
   identificandolo;
3. **il backend `mfcc` sugli stessi identici ritagli.** Media e deviazione dei
   cepstri descrivono soprattutto il canale. Se pareggia ECAPA, la conclusione e'
   la stessa dei punti sopra.

## E il controllo a risposta nota, che sta prima di tutti

Con `--clean` la stessa curva si calcola su voci sintetiche di **identita'
nota**. Serve a separare i due modi di fallire che dal gioco si vedono uguali:
*codice rotto* e *segnale inutilizzabile*. Se le voci note non si separano, il
colpevole e' qui dentro — la trasformata mel, il ricampionamento, il modello — e
non ha senso guardare l'audio del gioco. Il controllo pulito e' un **pavimento**,
non un tetto: due voci Piper sono un uomo e una donna, e passarlo non dimostra
che il modello regga su due uomini nella stessa stanza.

## La seconda domanda, che puo' chiudere una strada

Il piano assume che una riga **grigia** sia un secondo personaggio. Se e' vero,
fra due battute consecutive di colore diverso l'impronta deve cambiare piu' che
fra due battute dello stesso colore. Se non e' vero — se il grigio e' solo una
battuta in dissolvenza — l'ipotesi cade, e vale la pena saperlo prima di
costruirci sopra il vincolo del tracker. Anche qui la differenza fra i due gruppi
si stampa accanto al suo caso nullo, che si ottiene rimescolando le etichette di
colore: senza, "il grigio separa un po' di piu'" e' una frase che si puo' dire
di qualunque partizione casuale.
"""

from __future__ import annotations

import argparse
import difflib
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, load_profile  # noqa: E402
from core.types import LineClass, SubtitleEvent, VoiceSpec  # noqa: E402
from listen.embed import MODEL_RATE, MfccEmbedder, make_embedder, similarity, to_model_rate  # noqa: E402
from listen.vad import Speech, make_vad  # noqa: E402
from mix.center import split  # noqa: E402

# Le durate della curva. Il primo valore e' sotto il budget della pipeline, gli
# ultimi sono quello che un embedding di norma pretende: la domanda e' dove, fra
# i due, la curva smette di salire.
DURATE = (0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)

# Distanza minima fra due ritagli della stessa presa di parola. Due meta'
# attaccate condividono la coda di un fonema e l'inizio del successivo: sarebbe
# un positivo piu' facile del dovuto, cioe' un'altra misura che si guarda allo
# specchio.
STACCO = 0.25

FRASI = [
    "Dove diavolo credi di andare a quest'ora della notte?",
    "Non ho tempo per queste stronzate, sali in macchina e muoviti.",
    "Te lo dico una volta sola, poi non rispondo piu' di niente.",
    "La banca chiude fra venti minuti, dobbiamo essere fuori prima.",
    "Ho fatto tutto quello che mi avevi chiesto, adesso tocca a te.",
    "Guarda che se ci prendono non ci sono avvocati che tengano.",
    "Quel tizio non mi piace per niente, ha la faccia sbagliata.",
    "Aspetta qui, torno fra cinque minuti e poi ce ne andiamo.",
]


# -- il materiale ----------------------------------------------------------


@dataclass
class Track:
    """L'audio del centro, gia' a 16 kHz, con il tempo del primo campione.

    Si ricampiona **una volta sola** sull'intero tratto e non ritaglio per
    ritaglio: il filtro anti-alias ha una memoria di duecento campioni, e
    applicarlo a spezzoni da mezzo secondo ne sporcherebbe i bordi in modo
    diverso a ogni durata — cioe' proprio lungo l'asse della curva.
    """

    mono: np.ndarray
    t0: float
    rate: int = MODEL_RATE

    @property
    def t1(self) -> float:
        return self.t0 + len(self.mono) / self.rate

    def cut(self, t: float, dur: float) -> np.ndarray | None:
        i = int(round((t - self.t0) * self.rate))
        n = int(round(dur * self.rate))
        if i < 0 or n <= 0 or i + n > len(self.mono):
            return None
        return self.mono[i : i + n]


@dataclass
class Material:
    """Cio' che una passata sulla registrazione lascia in mano."""

    events: list[SubtitleEvent] = field(default_factory=list)
    speech: list[Speech] = field(default_factory=list)
    track: Track | None = None
    # Il canale dei lati: musica, motori, ambiente. Per costruzione **non**
    # contiene il dialogo, che sta al centro. E' il caso nullo piu' severo che
    # questa registrazione possa offrire, perche' a differenza del silenzio e'
    # simultaneo al parlato: stessa scena, stesso istante, stessa energia che
    # entra ed esce, e nessuna voce da riconoscere. Se separa quanto il centro,
    # non resta nessuna lettura in cui l'impronta stia identificando qualcuno.
    track_side: Track | None = None
    media_seconds: float = 0.0


def collect_audio(path: str, cfg: Config, start: float, end: float | None) -> Material:
    """Solo l'audio, senza far girare l'OCR.

    Esiste per una ragione pratica che ha effetti sulla qualita' della misura:
    la passata completa costa piu' del tempo reale (l'OCR e' il grosso), e su
    dieci minuti di registrazione sono quaranta minuti di attesa. La curva
    accuratezza-vs-durata non ha bisogno dei sottotitoli, quindi puo' girare su
    tratti dieci volte piu' lunghi — e con questi numeri di segmenti la lunghezza
    del tratto e' la differenza fra una curva e un'impressione.

    Cio' che si perde: il legame con le battute. Quindi niente analisi del
    grigio e niente selezione dei segmenti che stanno sotto un sottotitolo.
    """
    from tools.sources import AudioPipe, has_audio_track, probe

    if not has_audio_track(path):
        raise RuntimeError(f"{path} non ha traccia audio leggibile")
    info = probe(path)
    sr = cfg.audio.samplerate
    pipe = AudioPipe(path, samplerate=sr, channels=2, start=start, end=end)
    vad = make_vad(cfg.vad, sr)
    blocchi: list[np.ndarray] = []
    lati: list[np.ndarray] = []
    segments: list[Speech] = []
    passo = int(round(sr / cfg.capture.fps))
    durata = (end if end is not None else info.duration) - start
    t = start
    try:
        while t - start < durata:
            block = pipe.read(passo)
            if block.size == 0:
                break
            mono, side = split(block)
            blocchi.append(mono.astype(np.float32))
            lati.append(side.astype(np.float32))
            segments.extend(vad.push(mono, t=t))
            t += passo / sr
    finally:
        pipe.close()
    segments.extend(vad.flush())
    intero = np.concatenate(blocchi) if blocchi else np.zeros(0, np.float32)
    lato = np.concatenate(lati) if lati else np.zeros(0, np.float32)
    return Material(
        events=[],
        speech=segments,
        track=Track(to_model_rate(intero, sr), t0=start),
        track_side=Track(to_model_rate(lato, sr), t0=start),
        media_seconds=t - start,
    )


def collect(path: str, cfg: Config, start: float, end: float | None) -> Material:
    """Una sola passata: battute dal video, prese di parola e audio dal centro.

    Insieme e non in due corse, per la stessa ragione di `bench_onset`: la
    domanda riguarda l'allineamento fra i due, e due esecuzioni separate
    darebbero due elenchi che si somigliano invece di una prova.
    """
    from tools.replay import Replay
    from tools.sources import VideoSource

    source = VideoSource(path, fps=cfg.capture.fps, start=start, end=end)
    if not source.has_audio:
        raise RuntimeError(
            f"{path} non ha traccia audio leggibile: la misura non puo' esprimere la risposta"
        )
    vad = make_vad(cfg.vad, source.samplerate)
    segments: list[Speech] = []
    blocchi: list[np.ndarray] = []
    lati: list[np.ndarray] = []
    t_primo: list[float] = []

    def on_audio(t: float, block: np.ndarray) -> None:
        # Stessa estrazione del duck: misurare un segnale diverso da quello che
        # la pipeline vedra' darebbe una curva che non vale per la pipeline.
        if block.ndim == 2 and block.shape[1] == 2:
            mono, side = split(block)
        else:
            mono, side = block.reshape(-1), np.zeros(block.shape[0], np.float32)
        if not t_primo:
            t_primo.append(t)
        blocchi.append(mono.astype(np.float32))
        lati.append(side.astype(np.float32))
        segments.extend(vad.push(mono, t=t))

    replay = Replay(source, cfg, real=True)
    stats = replay.run(quiet=True, on_audio=on_audio)
    segments.extend(vad.flush())

    track = track_side = None
    if blocchi:
        track = Track(to_model_rate(np.concatenate(blocchi), source.samplerate), t0=t_primo[0])
        track_side = Track(to_model_rate(np.concatenate(lati), source.samplerate), t0=t_primo[0])
    return Material(
        events=sorted(stats.closed, key=lambda e: e.t_on),
        speech=segments,
        track=track,
        track_side=track_side,
        media_seconds=stats.media_seconds,
    )


# -- il punteggio ----------------------------------------------------------


def eer(pos: np.ndarray, neg: np.ndarray) -> tuple[float, float]:
    """Equal error rate e soglia a cui si ottiene.

    Si sceglie l'EER e non l'accuratezza al meglio possibile perche' e' l'unico
    numero che non dipende da quanti positivi e negativi si sono costruiti: il
    protocollo qui sopra ne fabbrica in proporzioni arbitrarie, e un'accuratezza
    grezza racconterebbe soprattutto quelle.
    """
    if pos.size == 0 or neg.size == 0:
        return float("nan"), float("nan")
    soglie = np.unique(np.concatenate([pos, neg]))
    frr = np.array([np.mean(pos < s) for s in soglie])  # positivi respinti
    far = np.array([np.mean(neg >= s) for s in soglie])  # negativi accettati
    i = int(np.argmin(np.abs(frr - far)))
    return float((frr[i] + far[i]) / 2.0), float(soglie[i])


def accuratezza(pos: np.ndarray, neg: np.ndarray, soglia: float) -> float:
    """Accuratezza bilanciata a una soglia fissata: quella che usa il tracker."""
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    return 0.5 * (float(np.mean(pos >= soglia)) + float(np.mean(neg < soglia)))


# -- le coppie -------------------------------------------------------------


@dataclass
class Coppie:
    """Punteggi dei positivi e dei negativi, piu' il conto di cosa c'era."""

    pos: np.ndarray
    neg: np.ndarray
    neg_vicini: np.ndarray
    neg_lontani: np.ndarray
    n_spans: int


def spans_di_parlato(speech: list[Speech]) -> list[tuple[float, float]]:
    return [(s.t0, s.t1) for s in speech if s.t1 is not None and s.t1 > s.t0]


def spans_di_silenzio(
    speech: list[Speech], track: Track, minimo: float
) -> list[tuple[float, float]]:
    """I buchi fra una presa di parola e la successiva.

    E' il caso nullo del protocollo: qui dentro, per costruzione, non c'e'
    nessuna voce da riconoscere.
    """
    parlato = sorted(spans_di_parlato(speech))
    out: list[tuple[float, float]] = []
    cursore = track.t0
    for a, b in parlato:
        if a - cursore >= minimo:
            out.append((cursore, a))
        cursore = max(cursore, b)
    if track.t1 - cursore >= minimo:
        out.append((cursore, track.t1))
    return out


def peek(
    spans: list[tuple[float, float]],
    track: Track,
    dur: float,
    quanti: int,
    cartella: Path,
    etichetta: str,
) -> None:
    """Salva su disco i ritagli che il modello riceve davvero.

    E' `--peek` di `replay`, trasportato dall'immagine al suono, e per la stessa
    ragione: prima di concludere che un modello non regge, si guarda — qui si
    ascolta — cio' che gli si sta dando. La ROI di default inquadrava il tappeto
    e l'OCR sembrava incapace; il ritaglio con le code delle lettere tagliate
    faceva sembrare scadente il riconoscitore. Un embedding che non separa
    nessuno e un embedding a cui si danno sparanti e motori si vedono uguali
    dall'uscita, e si distinguono in dieci secondi di ascolto.
    """
    import wave

    cartella.mkdir(parents=True, exist_ok=True)
    scritti = 0
    for a, b in spans:
        if scritti >= quanti or b - a < 2 * dur + STACCO:
            continue
        for dove, t in (("testa", a), ("coda", b - dur)):
            c = track.cut(t, dur)
            if c is None:
                continue
            p = cartella / f"{etichetta}_{t:08.2f}s_{dove}.wav"
            with wave.open(str(p), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(track.rate)
                w.writeframes((np.clip(c, -1, 1) * 32767).astype(np.int16).tobytes())
        scritti += 1
    print(f"   {scritti} ritagli '{etichetta}' salvati in {cartella}")


def spans_sotto_sottotitolo(
    speech: list[Speech], events: list[SubtitleEvent], pre: float, post: float
) -> list[tuple[float, float]]:
    """Le prese di parola che cadono mentre un sottotitolo e' a schermo.

    Serve a separare due fallimenti che dall'uscita si vedono uguali. Il VAD
    apre un segmento su qualunque cosa stacchi dal fondo — un motore, uno sparo,
    una porta — e su quei segmenti non c'e' nessuna identita' da riconoscere: una
    curva piatta direbbe "l'impronta non funziona" quando la verita' e' "non le
    e' stata data una voce". Il sottotitolo e' l'unica prova indipendente che in
    quell'istante qualcuno stava parlando, e usarla come filtro e' il modo di
    chiedere all'impronta la domanda giusta.
    """
    finestre = [
        (e.t_on - pre, (e.t_off if e.t_off is not None else e.t_on + 4.0) + post) for e in events
    ]
    out: list[tuple[float, float]] = []
    for s in speech:
        if s.t1 is None:
            continue
        if any(a <= s.t0 <= b for a, b in finestre):
            out.append((s.t0, s.t1))
    return out


def coppie(
    spans: list[tuple[float, float]],
    track: Track,
    embedder,
    dur: float,
    rng: np.random.Generator,
    *,
    max_neg: int = 4000,
    vicino: float = 10.0,
    lontano: float = 60.0,
    cache: dict | None = None,
) -> Coppie:
    """Positivi dalla stessa presa di parola, negativi da prese diverse.

    La `cache` non e' un'ottimizzazione qualunque: le righe "parlato" e
    "parlato, segm. fissi" della stessa durata devono confrontare **gli stessi
    identici vettori**, altrimenti la differenza fra le due conterrebbe anche il
    rumore di due calcoli distinti invece del solo effetto della selezione.
    """
    memo = cache if cache is not None else {}

    def impronta(t: float) -> np.ndarray | None:
        chiave = (round(t, 6), dur)
        if chiave not in memo:
            c = track.cut(t, dur)
            memo[chiave] = None if c is None else embedder.embed(c, track.rate)
        return memo[chiave]

    teste: list[np.ndarray] = []
    code: list[np.ndarray] = []
    centri: list[float] = []
    for a, b in spans:
        if b - a < 2 * dur + STACCO:
            continue
        prima = impronta(a)
        dopo = impronta(b - dur)
        if prima is None or dopo is None:
            continue
        teste.append(prima)
        code.append(dopo)
        centri.append((a + b) / 2.0)

    n = len(teste)
    if n < 2:
        vuoto = np.zeros(0)
        return Coppie(vuoto, vuoto, vuoto, vuoto, n)

    pos = np.array([similarity(teste[i], code[i]) for i in range(n)])
    tutte = [(i, j) for i in range(n) for j in range(i + 1, n)]
    if len(tutte) > max_neg:
        scelte = rng.choice(len(tutte), size=max_neg, replace=False)
        tutte = [tutte[k] for k in scelte]
    neg = np.array([similarity(teste[i], teste[j]) for i, j in tutte])
    dist = np.array([abs(centri[i] - centri[j]) for i, j in tutte])
    return Coppie(
        pos=pos,
        neg=neg,
        neg_vicini=neg[dist <= vicino],
        neg_lontani=neg[dist >= lontano],
        n_spans=n,
    )


# -- il controllo a risposta nota ------------------------------------------


def voci_note(backend: str, variants: bool) -> list[VoiceSpec]:
    """Le identita' su cui la risposta e' scritta in anticipo."""
    from speak.pool import FAMIGLIE, NATIVE

    basi = FAMIGLIE.get(backend, FAMIGLIE["piper"])
    voci = [
        VoiceSpec(voice_id=b.split("-")[1] if "-" in b else b, backend=backend, base_voice=b,
                  gender=NATIVE[b][0])
        for b in basi
    ]
    if variants:
        # Varianti di intonazione della stessa voce: identita' *diverse* agli
        # effetti del pool, ma non persone diverse. Sono un caso piu' duro e
        # vanno lette come tale, non come "il modello sbaglia".
        voci += [
            VoiceSpec(f"{v.voice_id}{s:+g}", backend, v.base_voice, semitones=s, gender=v.gender)
            for v in list(voci)
            for s in (-3.0, +3.0)
        ]
    return voci


def controllo_pulito(
    embedder, backend: str, durate: tuple[float, ...], variants: bool, rng
) -> None:
    """La stessa curva su voci di identita' nota."""
    from dataclasses import replace

    from core.config import Config as _C
    from speak.base import make_tts

    voci = voci_note(backend, variants)
    tts = make_tts(replace(_C().tts, backend=backend, samplerate=22050))
    print(f"\n== controllo a risposta nota: {len(voci)} voci {backend}, {len(FRASI)} frasi ==")
    if len(voci) <= 2:
        print("   ATTENZIONE: due voci sole, un uomo e una donna. E' un pavimento:")
        print("   passarlo esclude che il codice sia rotto, non dimostra che regga")
        print("   su due personaggi maschili nella stessa scena.")

    clip: dict[str, list[np.ndarray]] = {}
    for v in voci:
        audio = []
        for frase in FRASI:
            s = tts.synthesize(frase, v)
            audio.append(to_model_rate(s.audio, s.samplerate))
        clip[v.voice_id] = audio

    print("   durata   EER    acc@0,62   coppie")
    for dur in durate:
        n = int(dur * MODEL_RATE)
        emb: dict[str, list[np.ndarray]] = {}
        for vid, audio in clip.items():
            fette = []
            for a in audio:
                if len(a) < n:
                    continue
                # Dal centro della frase: l'attacco e la coda di una sintesi
                # contengono silenzio, e misurare il silenzio a 0,2 s vorrebbe
                # dire misurare quanto silenzio c'e'.
                i = (len(a) - n) // 2
                fette.append(embedder.embed(a[i : i + n], MODEL_RATE))
            emb[vid] = fette
        # Lo stesso calcolo del controllo sul fondo, per costruzione e non per
        # somiglianza: due statistiche scritte due volte divergono, e le due
        # tabelle vanno confrontate riga per riga.
        e, acc, n_pos, n_neg = curva_note(emb)
        print(f"   {dur:5.2f}s  {e:6.1%}  {acc:7.1%}   {n_pos}+/{n_neg}-")


def curva_note(
    emb_per_voce: dict[str, list[np.ndarray]]
) -> tuple[float, float, int, int]:
    """EER e accuratezza a 0,62 su impronte di identita' nota."""
    pos = np.array(
        [
            similarity(f[i], f[j])
            for f in emb_per_voce.values()
            for i in range(len(f))
            for j in range(i + 1, len(f))
        ]
    )
    ids = list(emb_per_voce)
    neg = np.array(
        [
            similarity(x, y)
            for a in range(len(ids))
            for b in range(a + 1, len(ids))
            for x in emb_per_voce[ids[a]]
            for y in emb_per_voce[ids[b]]
        ]
    )
    return eer(pos, neg)[0], accuratezza(pos, neg, 0.62), pos.size, neg.size


def controllo_sul_fondo(
    embedder,
    mat: Material,
    silenzio: list[tuple[float, float]],
    backend: str,
    durate: tuple[float, ...],
    snr_db: tuple[float, ...],
    rng: np.random.Generator,
) -> None:
    """Voci di identita' nota, ma sul fondo vero della registrazione.

    Il controllo pulito e la curva dal gioco sono i due estremi, e fra loro c'e'
    un salto che non si sa come attribuire: se le voci note si separano
    perfettamente e quelle del gioco no, la differenza sta nel fondo, nella
    compressione del gioco, nella lunghezza dei ritagli o nel fatto che sotto il
    VAD non ci fosse nessuna voce — quattro cause, un solo numero.

    Qui la variabile e' **una sola**: le stesse frasi, le stesse voci, gli
    stessi ritagli, sommati al rumore vero preso dai buchi di silenzio della
    registrazione. Se la curva crolla verso un certo rapporto segnale/rumore,
    il fondo e' la causa e la cura e' a monte dell'impronta — un'estrazione del
    parlato migliore, non un modello migliore. Se invece regge fino a rapporti
    peggiori di quelli veri, il fondo e' scagionato e il colpevole va cercato
    altrove.
    """
    from dataclasses import replace

    from core.config import Config as _C
    from speak.base import make_tts

    if mat.track is None or not silenzio:
        return
    voci = voci_note(backend, variants=False)
    tts = make_tts(replace(_C().tts, backend=backend, samplerate=22050))

    pulite: dict[str, list[np.ndarray]] = {}
    for v in voci:
        pulite[v.voice_id] = [
            to_model_rate(s.audio, s.samplerate)
            for s in (tts.synthesize(f, v) for f in FRASI)
        ]

    # Il fondo vero, in un pezzo unico da cui ritagliare a caso.
    fondo = np.concatenate(
        [c for a, b in silenzio for c in [mat.track.cut(a, min(b - a, 6.0))] if c is not None]
    )
    if fondo.size < MODEL_RATE:
        print("\n   (fondo di gioco insufficiente per il controllo sul rumore)")
        return

    print(f"\n== controllo a risposta nota, ma sul fondo vero del gioco ==")
    print(f"   {len(voci)} voci, {len(FRASI)} frasi, fondo da {fondo.size / MODEL_RATE:.0f}s di silenzio del video")
    print("   SNR     " + "".join(f"{d:>9.2f}s" for d in durate))
    for snr in snr_db:
        celle = []
        for dur in durate:
            n = int(dur * MODEL_RATE)
            emb: dict[str, list[np.ndarray]] = {}
            for vid, clip in pulite.items():
                fette = []
                for k, a in enumerate(clip):
                    if len(a) < n:
                        continue
                    i = (len(a) - n) // 2
                    voce = a[i : i + n]
                    j = int(rng.integers(0, max(1, fondo.size - n)))
                    rumore = fondo[j : j + n]
                    # I livelli si misurano sul ritaglio, non sull'intera frase:
                    # un SNR calcolato su tutta la frase includerebbe le pause,
                    # e il rapporto vero sul ritaglio sarebbe un altro.
                    rms_v = float(np.sqrt(np.mean(voce**2))) + 1e-9
                    rms_r = float(np.sqrt(np.mean(rumore**2))) + 1e-9
                    k_r = rms_v / (rms_r * (10.0 ** (snr / 20.0)))
                    fette.append(embedder.embed(voce + k_r * rumore, MODEL_RATE))
                emb[vid] = fette
            e, acc, _, _ = curva_note(emb)
            celle.append(f"{e:8.1%} ")
        print(f"   {snr:+4.0f} dB " + "".join(celle))
    print(
        "   (EER; confronta con la riga del controllo pulito, che e' lo stesso\n"
        "   materiale a SNR infinito)"
    )


def snr_stimato(mat: Material, parlato: list[tuple[float, float]], silenzio: list[tuple[float, float]]) -> float | None:
    """Quanto stacca il parlato dal fondo, in dB, su questa registrazione.

    E' grezzo — il "segnale" contiene anche il fondo — quindi sovrastima il
    rapporto vero. Serve solo a dire quale riga della tabella qui sopra sia
    quella che riguarda questo video.
    """
    if mat.track is None or not parlato or not silenzio:
        return None

    def livello(spans):
        v = []
        for a, b in spans:
            c = mat.track.cut(a, min(b - a, 2.0))
            if c is not None and c.size:
                v.append(float(np.sqrt(np.mean(c**2))))
        return float(np.median(v)) if v else None

    s, r = livello(parlato), livello(silenzio)
    if not s or not r:
        return None
    return 20.0 * float(np.log10(s / r))


# -- il grigio -------------------------------------------------------------


def ancora(e: SubtitleEvent, speech: list[Speech], pre: float, post: float) -> Speech | None:
    """La presa di parola piu' vicina alla comparsa del sottotitolo."""
    migliore, distanza = None, 1e9
    for s in speech:
        if s.t1 is None:
            continue
        d = s.t0 - e.t_on
        if -pre <= d <= post and abs(d) < distanza:
            migliore, distanza = s, abs(d)
    return migliore


def analisi_grigio(
    mat: Material, embedder, dur: float, rng: np.random.Generator, pre: float, post: float
) -> None:
    """Il grigio concorda con un cambio di voce?"""
    eventi = mat.events
    bianchi = [e for e in eventi if e.cls is LineClass.WHITE]
    grigi = [e for e in eventi if e.cls is LineClass.GREY]
    print(f"\n== il grigio e' un secondo speaker? ==")
    print(f"   battute: {len(bianchi)} bianche, {len(grigi)} grigie")
    if not grigi:
        print("   Nessuna riga grigia in questo tratto: la domanda non e' posta qui,")
        print("   e nessun risultato su questo video puo' confermare o smentire l'ipotesi.")
        return

    # Prima ancora dell'audio, due conti che possono chiudere la questione da soli.
    simultanee = sum(
        1 for g in grigi if any(abs(b.t_on - g.t_on) < 0.05 for b in bianchi)
    )
    eco = 0
    for g in grigi:
        recenti = [b for b in bianchi if 0 <= g.t_on - b.t_on <= 4.0]
        if any(
            difflib.SequenceMatcher(None, g.text.lower(), b.text.lower()).ratio() > 0.8
            for b in recenti
        ):
            eco += 1
    print(
        f"   grigie che compaiono insieme a una bianca (entro 50 ms): {simultanee}/{len(grigi)}"
        f"  ({simultanee/len(grigi):.0%})"
    )
    print(
        f"   grigie che ripetono una bianca recente (testo simile >80%): {eco}/{len(grigi)}"
        f"  ({eco/len(grigi):.0%})"
    )
    if eco > 0.5 * len(grigi):
        print("   Piu' di meta' delle grigie sono l'eco di una bianca: il grigio qui e' una")
        print("   battuta in dissolvenza, non un secondo personaggio. Il vincolo di colore")
        print("   sul tracker non va scritto, va sostituito da un dedupe testuale.")

    if mat.track is None:
        return

    # Ora l'audio. La condizione dura: due battute consecutive devono agganciarsi
    # a prese di parola **diverse**. Se si agganciassero alla stessa, i due
    # ritagli sarebbero lo stesso audio e la somiglianza varrebbe 1 per
    # costruzione — la misura risponderebbe "nessun cambio" sempre.
    ancore: dict[int, Speech] = {}
    for i, e in enumerate(eventi):
        a = ancora(e, mat.speech, pre, post)
        if a is not None:
            ancore[i] = a
    print(f"   battute agganciate a una presa di parola: {len(ancore)}/{len(eventi)}")

    emb: dict[int, np.ndarray] = {}
    for i, a in ancore.items():
        c = mat.track.cut(a.t0, dur)
        if c is not None:
            emb[i] = embedder.embed(c, mat.track.rate)

    uguali: list[float] = []
    diversi: list[float] = []
    scartate_stessa_ancora = 0
    for i in range(len(eventi) - 1):
        j = i + 1
        if i not in emb or j not in emb:
            continue
        if ancore[i].t0 == ancore[j].t0:
            scartate_stessa_ancora += 1
            continue
        s = similarity(emb[i], emb[j])
        (uguali if eventi[i].cls is eventi[j].cls else diversi).append(s)

    print(
        f"   coppie consecutive utilizzabili: {len(uguali)} stesso colore, "
        f"{len(diversi)} colore diverso  ({scartate_stessa_ancora} scartate: stessa presa di parola)"
    )
    if len(diversi) < 5 or len(uguali) < 5:
        print("   Troppo poche per dire qualcosa. Serve un tratto piu' lungo o piu' dialogo:")
        print("   con questi numeri qualunque differenza fra i due gruppi e' rumore.")
        return

    u, d = np.array(uguali), np.array(diversi)
    osservata = float(np.median(u) - np.median(d))
    print(f"   somiglianza p50: stesso colore {np.median(u):+.3f}, colore diverso {np.median(d):+.3f}")
    print(f"   differenza osservata: {osservata:+.3f}  (positiva = il grigio segnala un cambio)")

    # Il caso nullo: le stesse somiglianze con le etichette di colore
    # rimescolate. Senza, "un po' piu' basso" e' una frase vera di qualunque
    # partizione casuale.
    tutte = np.concatenate([u, d])
    n_u = len(u)
    finte = np.empty(2000)
    for k in range(2000):
        p = rng.permutation(tutte)
        finte[k] = float(np.median(p[:n_u]) - np.median(p[n_u:]))
    p_value = float(np.mean(finte >= osservata))
    print(
        f"   con le etichette rimescolate: p50 {np.median(finte):+.3f}, "
        f"p95 {np.percentile(finte, 95):+.3f}   ->  p = {p_value:.3f}"
    )
    if p_value > 0.05:
        print("   L'ipotesi NON regge su questi dati: il colore della riga non predice un")
        print("   cambio di voce meglio di un'etichetta tirata a caso. Il vincolo di colore")
        print("   sul tracker andrebbe scritto sapendo che qui non ha trovato conferma.")
    else:
        print("   L'ipotesi regge: il cambio di colore accompagna un cambio di impronta")
        print("   piu' spesso di quanto farebbe un'etichetta casuale.")


# -- il programma ----------------------------------------------------------


def riga_curva(nome: str, c: Coppie, soglia: float) -> None:
    if c.pos.size == 0 or c.neg.size == 0:
        print(f"   {nome:22} (nessuna coppia: segmenti troppo corti per questa durata)")
        return
    e, s_eer = eer(c.pos, c.neg)
    print(
        f"   {nome:22} {e:6.1%}  {accuratezza(c.pos, c.neg, soglia):7.1%}  "
        f"{np.median(c.pos):+.3f} {np.median(c.neg):+.3f}   {c.n_spans:4d} segm  "
        f"{c.pos.size}+/{c.neg.size}-"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.bench_speaker",
        description="Quanta voce serve per riconoscere chi parla, e il grigio dice il vero?",
    )
    ap.add_argument("video", nargs="?", default=None, help="registrazione con traccia audio")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--clean", action="store_true", help="solo il controllo a risposta nota")
    ap.add_argument(
        "--audio-only",
        action="store_true",
        help="salta l'OCR: solo la curva, ma su tratti molto piu' lunghi",
    )
    ap.add_argument("--no-clean", action="store_true", help="salta il controllo a risposta nota")
    ap.add_argument("--tts", default="piper", choices=("piper", "supertonic", "kokoro"))
    ap.add_argument("--variants", action="store_true", help="aggiungi le varianti di intonazione")
    ap.add_argument("--durations", default=None, help="es. 0.3,1.0,3.0")
    ap.add_argument("--anchor", type=float, default=1.0, help="durata del ritaglio per il grigio")
    ap.add_argument("--pre", type=float, default=0.5)
    ap.add_argument("--post", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--peek",
        type=int,
        default=0,
        metavar="N",
        help="salva N ritagli per gruppo in runs/speaker_peek e ascoltali",
    )
    args = ap.parse_args(argv)

    cfg = (
        load_profile(args.profile, args.overrides)
        if args.profile
        else Config().apply(args.overrides)
    )
    durate = (
        tuple(float(x) for x in args.durations.split(","))
        if args.durations
        else DURATE
    )
    rng = np.random.default_rng(args.seed)

    embedder = make_embedder(cfg.speaker)
    print(f"impronta: backend '{embedder.name}', {embedder.dim} dimensioni")
    if embedder.name != "ecapa-onnx":
        print("ATTENZIONE: non e' il modello. Ogni numero qui sotto misura il canale")
        print("piu' della voce, e va letto come caso nullo, non come risultato.")

    if not args.no_clean:
        t0 = time.perf_counter()
        controllo_pulito(embedder, args.tts, durate, args.variants, rng)
        print(f"   ({time.perf_counter() - t0:.0f} s)")
    if args.clean:
        return 0
    if not args.video:
        print("\nNessun video: solo il controllo a risposta nota.", file=sys.stderr)
        return 0

    t0 = time.perf_counter()
    mat = (
        collect_audio(args.video, cfg, args.start, args.end)
        if args.audio_only
        else collect(args.video, cfg, args.start, args.end)
    )
    if mat.track is None:
        print("nessun audio raccolto", file=sys.stderr)
        return 2
    parlato = spans_di_parlato(mat.speech)
    silenzio = spans_di_silenzio(mat.speech, mat.track, minimo=2 * max(durate) + STACCO)
    print(
        f"\n{mat.media_seconds:.0f}s di media, {len(mat.events)} battute chiuse, "
        f"{len(parlato)} prese di parola (durata p50 "
        f"{np.median([b - a for a, b in parlato]) if parlato else 0:.2f}s), "
        f"{len(silenzio)} buchi di silenzio  ({time.perf_counter() - t0:.0f} s)"
    )

    # Lo stesso insieme di segmenti a tutte le durate. Senza, la curva confronta
    # anche insiemi diversi: le durate lunghe pescano solo nei segmenti lunghi,
    # che sono i monologhi, che sono il caso facile. Una curva che sale
    # potrebbe essere solo questo.
    lunghi = [s for s in parlato if s[1] - s[0] >= 2 * max(durate) + STACCO]
    print(f"   segmenti abbastanza lunghi per tutte le durate: {len(lunghi)}")
    dialogo = (
        spans_sotto_sottotitolo(mat.speech, mat.events, args.pre, args.post)
        if mat.events
        else []
    )
    if mat.events:
        print(
            f"   segmenti che cadono sotto un sottotitolo (cioe' probabile dialogo): "
            f"{len(dialogo)}/{len(parlato)}"
        )

    if args.peek:
        cartella = Path("runs") / "speaker_peek"
        print(f"\n== ritagli su disco, da ascoltare ==")
        peek(parlato, mat.track, args.anchor, args.peek, cartella, "parlato")
        if dialogo:
            peek(dialogo, mat.track, args.anchor, args.peek, cartella, "sottotitolo")
        if silenzio:
            peek(silenzio, mat.track, args.anchor, args.peek, cartella, "silenzio")

    soglia = cfg.speaker.similarity
    print(f"\n== accuratezza in funzione della durata di clip (soglia in config: {soglia:.2f}) ==")
    print("   caso                    EER   acc@sgl   p50+   p50-    segmenti  coppie")
    leggero = MfccEmbedder()
    memo: dict = {}
    memo_lati: dict = {}
    memo_leggero: dict = {}
    for dur in durate:
        print(f"   -- clip da {dur:.2f}s --")
        c = coppie(parlato, mat.track, embedder, dur, rng, cache=memo)
        riga_curva("parlato", c, soglia)
        if dialogo:
            riga_curva(
                "sotto sottotitolo",
                coppie(dialogo, mat.track, embedder, dur, rng, cache=memo),
                soglia,
            )
        if lunghi:
            riga_curva(
                "parlato, segm. fissi",
                coppie(lunghi, mat.track, embedder, dur, rng, cache=memo),
                soglia,
            )
        if c.neg_vicini.size and c.neg_lontani.size:
            riga_curva("  neg. vicini (<10s)", Coppie(c.pos, c.neg_vicini, c.neg_vicini, c.neg_vicini, c.n_spans), soglia)
            riga_curva("  neg. lontani (>60s)", Coppie(c.pos, c.neg_lontani, c.neg_lontani, c.neg_lontani, c.n_spans), soglia)
        if mat.track_side is not None:
            riga_curva(
                "LATI (caso nullo)",
                coppie(parlato, mat.track_side, embedder, dur, rng, cache=memo_lati),
                soglia,
            )
        if silenzio:
            riga_curva(
                "SILENZIO (caso nullo)",
                coppie(silenzio, mat.track, embedder, dur, rng, cache=memo),
                soglia,
            )
        if embedder.name != "mfcc":
            riga_curva(
                "mfcc (caso nullo)",
                coppie(parlato, mat.track, leggero, dur, rng, cache=memo_leggero),
                soglia,
            )

    print(
        "\n   Come si legge: la riga 'parlato' vale qualcosa solo se sta molto sopra le\n"
        "   righe di caso nullo. LATI e' la piu' severa: sono gli stessi istanti, la\n"
        "   stessa scena, la stessa energia, ma il dialogo li' non c'e'. Se separa quanto\n"
        "   il centro, non resta nessuna lettura in cui l'impronta stia identificando\n"
        "   qualcuno. Stessa conclusione se il SILENZIO separa quanto il parlato, o se\n"
        "   'mfcc' pareggia ECAPA. E se i negativi vicini vanno molto peggio dei lontani,\n"
        "   il riconoscimento sta datando l'audio invece di identificarlo."
    )

    stacco = snr_stimato(mat, parlato, silenzio)
    if stacco is not None:
        print(f"\n   Su questo video il parlato stacca dal fondo di circa {stacco:+.0f} dB")
        print("   (stima per eccesso: dentro il 'parlato' c'e' anche il fondo).")
    if not args.no_clean:
        controllo_sul_fondo(
            embedder, mat, silenzio, args.tts, durate[:5], (24.0, 12.0, 6.0, 0.0, -6.0), rng
        )

    analisi_grigio(mat, embedder, args.anchor, rng, args.pre, args.post)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
