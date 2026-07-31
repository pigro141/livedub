"""Verifiche del dominio audio: stretch, pool di voci, sintesi, mixer.

Nessun modello viene scaricato: la sintesi si prova con `ToneTts`, che e' finto
apposta. Le verifiche su Piper stanno altrove perche' richiedono la rete.
"""

from __future__ import annotations

import numpy as np

from core.types import VoiceSpec
from mix.center import (
    DuckEnvelope,
    center_energy,
    db_to_gain,
    duck_center,
    gain_to_db,
    join,
    split,
)
from mix.mixer import Mixer
from mix.stretch import fit_duration, pitch_shift, resample, time_stretch
from speak.base import SilentTts, ToneTts
from speak.pool import VoicePool, build_pool

SR = 22050


def _voce(dur: float = 1.5, f0: float = 120.0, sr: int = SR) -> np.ndarray:
    """Segnale periodico con inviluppo a sillabe: mette alla prova l'aggancio
    di WSOLA come non farebbe una sinusoide pura."""
    t = np.arange(int(dur * sr), dtype=np.float32) / sr
    sig = sum((1.0 / k) * np.sin(2 * np.pi * f0 * k * t) for k in (1, 2, 3, 4))
    return (sig * (0.5 + 0.5 * np.sin(2 * np.pi * 3.0 * t)) / 3.0).astype(np.float32)


def _f0(x: np.ndarray, sr: int = SR) -> float:
    n = min(len(x), int(0.5 * sr))
    if n < 256:
        return 0.0
    seg = x[:n] * np.hanning(n)
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(n, 1 / sr)
    band = (freqs > 60) & (freqs < 400)
    return float(freqs[band][np.argmax(spec[band])])


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    c = np.correlate(a, b, mode="full")
    return float(c.max() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def _spec_diff(a: np.ndarray, b: np.ndarray) -> float:
    n = min(len(a), len(b))
    w = np.hanning(n)
    A = np.abs(np.fft.rfft(a[:n] * w))
    B = np.abs(np.fft.rfft(b[:n] * w))
    return float(np.linalg.norm(A - B) / (np.linalg.norm(A) + 1e-12))


def test_stretch(c) -> None:
    c.group("stretch")
    x = _voce()

    # 1. La durata in uscita e' decisa, non sperata: e' la proprieta' per cui
    #    esiste questo modulo invece di usare il length_scale di Piper.
    for r in (0.7, 0.85, 1.15, 1.35, 1.6):
        y = time_stretch(x, r, SR)
        atteso = len(x) / r
        c.ok(
            abs(len(y) - atteso) / atteso < 0.001,
            f"rate {r}: la lunghezza in uscita e' esatta (attesi {atteso:.0f}, {len(y)})",
        )

    c.ok(np.array_equal(time_stretch(x, 1.0, SR), x), "rate 1 e' l'identita'")
    c.eq(time_stretch(np.zeros(0, np.float32), 1.2, SR).size, 0, "un ingresso vuoto resta vuoto")
    c.raises(ValueError, lambda: time_stretch(x, 0.0, SR), "rate nullo e' un errore")
    c.raises(ValueError, lambda: time_stretch(x, -1.0, SR), "rate negativo e' un errore")
    c.eq(len(time_stretch(x[:100], 1.3, SR)), 77, "un frammento cortissimo non esplode")

    # 2. L'intonazione non si sposta. E' l'intera ragione di usare WSOLA invece
    #    di ricampionare: il controllo di sotto mostra cosa si eviterebbe.
    c.close(_f0(x), 120.0, "il segnale di prova ha f0 nota", tol=3.0)
    for r in (0.7, 1.35):
        c.close(_f0(time_stretch(x, r, SR)), 120.0, f"rate {r}: l'intonazione resta ferma", tol=4.0)
    ricampionato = np.interp(np.arange(0, len(x), 1.35), np.arange(len(x)), x).astype(np.float32)
    c.ok(
        abs(_f0(ricampionato) - 120.0) > 30.0,
        "il semplice ricampionamento invece sposta l'intonazione (la prova sa distinguere)",
    )

    # 3. Giro identita' — valido solo in ALLUNGAMENTO. In compressione si butta
    #    via materiale e riespandere non lo reinventa: non e' un difetto della
    #    trasformata, e pretenderlo sarebbe una prova mal posta.
    #
    #    **Le soglie sono state allargate, e il motivo va letto prima di
    #    stringerle di nuovo.** Una versione precedente le superava con
    #    larghissimo margine — corr 0,9999 e spettro 0,0001 — e lo faceva
    #    **grazie a un difetto**: il puntatore di analisi arretrava
    #    cumulativamente, e la deriva della compressione veniva annullata da
    #    quella dell'allungamento. Un'inversa quasi esatta ottenuta da due
    #    errori che si compensano. Nel frattempo, in una direzione sola, quella
    #    versione perdeva l'ultima parola di ogni battuta compressa: misurato in
    #    diretta, spettro 0,0043 contro 0,0432 ma **contenuto della coda 0,00
    #    contro 28,2**.
    #
    #    Questa prova, da sola, sceglieva quindi l'algoritmo che cancella le
    #    parole. Resta perche' serve — un giro identita' che si rompe davvero
    #    direbbe qualcosa — ma non e' piu' la prova principale: quella e' il
    #    gruppo `coda` in `tools/selftest.py`, che chiede che la fine del
    #    segnale ci sia ancora. Fra spettro e contenuto vince il contenuto.
    for r in (0.7, 0.85):
        z = time_stretch(time_stretch(x, r, SR), 1.0 / r, SR)
        c.ok(_corr(x, z) > 0.98, f"allungamento r={r}: il giro identita' torna (corr {_corr(x,z):.4f})")
        c.ok(
            _spec_diff(x, z) < 0.06,
            f"allungamento r={r}: lo spettro regge ({_spec_diff(x,z):.4f})",
        )

    # ...e la misura campione-per-campione non saprebbe dirlo, perche' WSOLA
    # sfasa. Verificarlo impedisce di rifare l'errore.
    z = time_stretch(time_stretch(x, 0.7, SR), 1.0 / 0.7, SR)
    n = min(len(x), len(z))
    rms_diff = float(np.sqrt(np.mean((x[:n] - z[:n]) ** 2)))
    c.ok(rms_diff > 0.0, "il residuo campione-per-campione non e' nullo (c'e' sfasamento)")
    c.ok(_corr(x, z) > 0.98, "ma la correlazione dice che il segnale e' lo stesso")

    # 4. pitch_shift: cambia l'intonazione, NON la durata.
    for s in (-4.0, -2.0, 2.0, 4.0):
        y = pitch_shift(x, s, SR)
        c.eq(len(y), len(x), f"{s:+g} semitoni: la durata non cambia")
        atteso = 120.0 * 2 ** (s / 12.0)
        c.close(_f0(y), atteso, f"{s:+g} semitoni: l'intonazione va dove deve", tol=6.0)
    c.ok(np.array_equal(pitch_shift(x, 0.0, SR), x), "zero semitoni e' l'identita'")

    # 5. resample.
    for sr2 in (16000, 48000):
        y = resample(x, SR, sr2)
        c.eq(len(y), int(round(len(x) * sr2 / SR)), f"{SR}->{sr2}: lunghezza proporzionale")
        z = resample(y, sr2, SR)
        c.ok(_corr(x, z) > 0.99, f"{SR}->{sr2}->{SR}: il giro torna")
        c.close(_f0(y, sr2), 120.0, f"{SR}->{sr2}: l'intonazione non si sposta", tol=4.0)
    c.ok(np.array_equal(resample(x, SR, SR), x), "stessa frequenza e' l'identita'")

    # **L'anti-alias, con una prova che puo' dire di no.** Le verifiche qui
    # sopra girano su un segnale a 120 Hz e passavano identiche quando il filtro
    # anti-alias era, per tutti i rapporti usati dal progetto, `[0, 1, 0]` —
    # cioe' l'identita'. Un giro identita' su una fondamentale bassa non puo'
    # esprimere il ripiegamento, perche' il ripiegamento vive sopra il Nyquist
    # di destinazione e li' quel segnale non ha niente. L'unica prova che lo
    # vede e' un tono messo apposta dove il danno si produce.
    for src, dst in ((48000, 16000), (44100, 22050)):
        t = np.arange(src, dtype=np.float32) / src
        sotto = np.sin(2 * np.pi * (0.3 * dst / 2) * t).astype(np.float32)
        sopra = np.sin(2 * np.pi * (1.3 * dst / 2) * t).astype(np.float32)
        rms_sotto = float(np.sqrt(np.mean(resample(sotto, src, dst) ** 2)))
        rms_sopra = float(np.sqrt(np.mean(resample(sopra, src, dst) ** 2)))
        c.ok(rms_sotto > 0.6, f"{src}->{dst}: la banda utile passa ({rms_sotto:.3f} su 0,707)")
        c.ok(
            rms_sopra < 0.02,
            f"{src}->{dst}: sopra il Nyquist non si ripiega ({rms_sopra:.4f}, "
            f"{20*np.log10(rms_sopra/0.7071 + 1e-12):+.0f} dB)",
        )
    c.raises(ValueError, lambda: resample(x, 0, SR), "frequenza nulla e' un errore")

    # 6. fit_duration: centra la scadenza, e quando non puo' si ferma al limite
    #    invece di stravolgere la voce.
    for target in (1.2, 1.5, 1.8):
        y, r = fit_duration(x, target, SR)
        c.close(len(y) / SR, target, f"target {target}s centrato", tol=0.02)
        c.ok(0.7 <= r <= 1.5, f"target {target}s: rate dentro i limiti")
    y, r = fit_duration(x, 5.0, SR, limits=(0.7, 1.5))
    c.close(r, 0.7, "target irraggiungibile: si applica il limite")
    c.ok(len(y) / SR < 5.0, "si sfora piuttosto che stravolgere la voce")
    y, r = fit_duration(np.zeros(0, np.float32), 1.0, SR)
    c.close(r, 1.0, "ingresso vuoto: rate neutro")


def test_center(c) -> None:
    c.group("center")

    rng = np.random.default_rng(0)
    n = 2048
    voce = rng.standard_normal(n).astype(np.float32) * 0.3  # centrata
    musica = rng.standard_normal(n).astype(np.float32) * 0.3  # larga
    stereo = np.stack([voce + musica, voce - musica], axis=1)

    mid, side = split(stereo)
    c.ok(np.allclose(mid, voce, atol=1e-5), "il mid isola quello che sta al centro")
    c.ok(np.allclose(side, musica, atol=1e-5), "il side isola quello che sta ai lati")

    # La verifica che conta: a guadagno 1 non deve succedere niente.
    c.ok(np.allclose(join(mid, side), stereo, atol=1e-6), "split e join sono inversi")
    c.ok(
        np.allclose(duck_center(stereo, 1.0), stereo, atol=1e-6),
        "guadagno 1: l'audio del gioco passa immutato",
    )

    ducked = duck_center(stereo, 0.2)
    m2, s2 = split(ducked)
    c.ok(np.allclose(m2, voce * 0.2, atol=1e-5), "il duck abbassa il centro")
    c.ok(np.allclose(s2, musica, atol=1e-5), "il duck NON tocca i lati")

    c.raises(ValueError, lambda: split(np.zeros(10, np.float32)), "il mono non e' stereo")
    c.raises(ValueError, lambda: split(np.zeros((10, 3), np.float32)), "tre canali non vanno bene")

    solo_centro = np.stack([voce, voce], axis=1)
    solo_lati = np.stack([musica, -musica], axis=1)
    c.ok(center_energy(solo_centro) > 0.99, "segnale tutto centrato")
    c.ok(center_energy(solo_lati) < 0.01, "segnale tutto laterale")
    c.close(center_energy(np.zeros((10, 2), np.float32)), 0.0, "silenzio: nessuna energia")

    c.close(db_to_gain(0.0), 1.0, "0 dB e' guadagno unitario")
    c.close(db_to_gain(-6.0), 0.5012, "-6 dB dimezza circa", tol=1e-3)
    c.close(gain_to_db(db_to_gain(-14.0)), -14.0, "dB e guadagno sono inversi", tol=1e-6)

    # Inviluppo.
    env = DuckEnvelope(48000, duck_db=-12.0, attack_ms=40, release_ms=200)
    c.close(env.gain, 1.0, "l'inviluppo parte a riposo")
    primo = env.block(64, active=True)
    c.ok(primo[0] < 1.0, "appena acceso comincia a scendere")
    c.ok(primo[-1] < primo[0], "e continua a scendere")
    for _ in range(200):
        env.block(64, active=True)
    c.close(env.gain, db_to_gain(-12.0), "a regime raggiunge il livello richiesto", tol=1e-3)
    salita = env.block(64, active=False)
    c.ok(salita[-1] > db_to_gain(-12.0), "spento, risale")
    c.ok(
        env.attack < env.release,
        "l'attacco e' piu' rapido del rilascio (fare spazio in fretta, tornare piano)",
    )
    env.reset()
    c.close(env.gain, 1.0, "reset riporta a riposo")
    c.eq(len(env.block(0, True)), 0, "un blocco vuoto non esplode")


def test_pool(c) -> None:
    c.group("pool")

    pool = build_pool()
    c.eq(len(pool), 6, "il pool di default ha sei voci")
    c.eq(len({v.voice_id for v in pool}), 6, "gli identificativi sono tutti diversi")
    c.eq(pool[0].semitones, 0.0, "la prima voce e' nativa, non trasformata")
    c.eq(pool[1].semitones, 0.0, "anche la seconda e' nativa")
    c.ok(
        pool[0].base_voice != pool[1].base_voice,
        "le prime due voci vengono da modelli diversi: e' il contrasto piu' forte disponibile",
    )
    c.eq({v.gender for v in pool}, {"m", "f"}, "il pool copre entrambi i generi")
    c.ok(
        max(abs(v.semitones) for v in pool[:4]) <= max(abs(v.semitones) for v in pool),
        "le varianti piu' spinte arrivano dopo",
    )

    c.eq(len(build_pool(size=2)), 2, "la dimensione richiesta viene rispettata")
    c.eq(len(build_pool(size=99)), 8, "non si inventano varianti oltre quelle definite")
    solo_paola = build_pool(("it_IT-paola-medium",), size=6)
    c.ok(all(v.base_voice == "it_IT-paola-medium" for v in solo_paola), "una base sola")
    c.ok(len(solo_paola) >= 3, "anche con una base sola il pool ha piu' voci")
    c.raises(ValueError, lambda: build_pool(("inesistente",)), "nessuna base valida e' un errore")

    # Assegnazione: stabile, e stabile e basta.
    vp = VoicePool(build_pool(size=3))
    a1 = vp.voice_for("S0", 1.0)
    b1 = vp.voice_for("S1", 2.0)
    c.ok(a1.voice_id != b1.voice_id, "personaggi diversi ricevono voci diverse")
    c.eq(vp.voice_for("S0", 3.0).voice_id, a1.voice_id, "un personaggio non cambia mai voce")
    c.eq(len(vp), 2, "conta i personaggi sentiti")
    c.ok(vp.known("S0") and not vp.known("S9"), "sa chi ha gia' sentito")
    c.eq(vp.assignments[0].lines, 2, "conta le battute per personaggio")
    c.eq(vp.assignments[0].speaker_id, "S0", "le assegnazioni sono in ordine di apparizione")
    c.eq(vp.collisions, 0, "finche' ci sono voci libere non ci sono collisioni")

    vp.voice_for("S2", 4.0)
    quarto = vp.voice_for("S3", 5.0)
    c.eq(vp.collisions, 1, "esaurite le voci, la collisione viene contata")
    c.eq(quarto.voice_id, a1.voice_id, "si ricomincia dal principio invece di lasciare muti")
    c.eq(vp.voice_for("S0").voice_id, a1.voice_id, "e chi aveva gia' una voce la conserva")

    c.ok("S0" in vp.report(), "il report nomina i personaggi")

    # **La fusione vista dal pool.** Il tracker decide chi vince, qui si esegue —
    # e l'esecuzione ha due obblighi: il vincitore non cambia voce (e' il punto
    # dell'operazione), e la voce del perdente torna in circolo, perche' in una
    # scena con sedici identita' e sei voci quella e' l'unica ragione per cui ne
    # resta ancora una da dare.
    f = VoicePool(build_pool(size=3))
    v0 = f.voice_for("S0", 1.0)
    v1 = f.voice_for("S1", 2.0)
    f.merge("S1", "S0")
    c.eq(f.voice_for("S0", 3.0).voice_id, v0.voice_id, "il vincitore non cambia voce")
    c.eq(f.voice_for("S1", 3.0).voice_id, v0.voice_id, "il vecchio id parla con la voce del vincitore")
    c.eq(len(f), 1, "e i due contano come un personaggio solo")
    c.eq(f.voice_for("S2", 4.0).voice_id, v1.voice_id, "la voce liberata torna al prossimo personaggio")
    c.eq(f.assegnata("S1").voice_id, v0.voice_id, "`assegnata` segue la fusione")
    c.eq(f.assegnata("S9"), None, "e non assegna niente a chi non ha ancora parlato")

    # Il vincitore che non ha ancora parlato eredita la voce gia' sentita invece
    # di prenderne una nuova: quella voce e' gia' nell'orecchio di chi ascolta.
    g = VoicePool(build_pool(size=3))
    vecchia = g.voice_for("S1", 1.0)
    g.merge("S1", "S0")
    c.eq(g.voice_for("S0", 2.0).voice_id, vecchia.voice_id, "la voce si trasferisce, non si rifa'")
    c.eq(len(g), 1, "e resta una assegnazione sola")

    vp.reset()
    c.eq(len(vp), 0, "reset dimentica tutto")
    c.ok("nessun personaggio" in VoicePool().report(), "report di un pool vuoto")


def test_pool_genere(c) -> None:
    """Il pool rispetta il sesso della voce quando lo si sa.

    Questa prova nasce da un ascolto, non da un ragionamento: in una scena con
    tre uomini uno parlava con la voce di `paola`, e quando il tracker lo
    spezzava in due identita' alternava femminile e maschile a seconda di come
    parlava. La causa non era un difetto: era l'alternanza voluta del pool, che
    e' giusta finche' non si sa niente su chi parla e diventa il peggiore dei
    difetti appena si sa.
    """
    c.group("pool_genere")

    voci = build_pool(("it_IT-paola-medium", "it_IT-riccardo-x_low"), size=6)
    maschili = [v.voice_id for v in voci if v.gender == "m"]
    femminili = [v.voice_id for v in voci if v.gender == "f"]
    c.ok(len(maschili) >= 3 and len(femminili) >= 3, "il pool ha voci di entrambi i sessi")

    # Tre uomini di fila: tre voci maschili **diverse**. Senza il vincolo il
    # secondo prenderebbe una voce femminile, ed e' esattamente cio' che si e'
    # sentito.
    p = VoicePool(voci)
    dati = [p.voice_for(f"S{k}", gender="m") for k in range(3)]
    c.ok(all(v.gender == "m" for v in dati), "tre uomini ricevono tre voci maschili")
    c.eq(len({v.voice_id for v in dati}), 3, "e sono tre voci distinte, non la stessa")

    # La voce, una volta data, non si tocca piu': e' la promessa del pool, e un
    # personaggio che cambia voce a meta' scena e' peggio di uno con la voce
    # sbagliata.
    c.eq(p.voice_for("S0", gender="f").voice_id, dati[0].voice_id,
         "chiedere l'altro sesso non riassegna una voce gia' data")

    # Una donna dopo tre uomini prende una voce femminile, non l'avanzo.
    donna = p.voice_for("S3", gender="f")
    c.eq(donna.gender, "f", "una donna riceve una voce femminile")

    # Senza informazione si torna all'ordine del pool, che alterna: quando non si
    # sa, alternare e' la scelta giusta perche' massimizza il contrasto.
    q = VoicePool(voci)
    ignoti = [q.voice_for(f"X{k}").gender for k in range(2)]
    c.ok(ignoti[0] != ignoti[1], "senza sapere il sesso, il pool alterna")

    # **La voce di attesa non e' del pool.** Se lo fosse, prima o poi diventerebbe
    # la voce definitiva di qualcuno e chi ascolta sentirebbe la voce «non so chi
    # sia» trasformarsi in un personaggio.
    from speak.pool import voce_neutra

    piccolo = build_pool(size=3)
    n = voce_neutra(piccolo)
    c.ok(n.voice_id not in {v.voice_id for v in piccolo}, "la neutra non e' una voce del pool")
    c.ok(
        n.base_voice != piccolo[0].base_voice or n.semitones != piccolo[0].semitones,
        "e non e' nemmeno la stessa voce con un altro nome",
    )
    pieno = build_pool(size=99)
    esaurito = voce_neutra(pieno)
    c.ok(
        esaurito.voice_id not in {v.voice_id for v in pieno},
        "anche a famiglia esaurita resta distinta da tutte",
    )

    # **L'assegnazione rinviata, tutta insieme.** E' la politica che gira in
    # pipeline e sul banco: la stessa funzione, altrimenti una taratura provata
    # sul banco misurerebbe un doppiaggio che non esiste.
    from speak.pool import voce_per

    class FintoPersonaggio:
        def __init__(self, gender, battute):
            self.gender, self.battute = gender, battute

    d = VoicePool(build_pool(size=6))
    neutra = voce_neutra(d.voices)
    incerto = FintoPersonaggio("?", 1)
    c.eq(voce_per(d, "S0", incerto, neutra=neutra).voice_id, "neutra",
         "chi non si sa ancora chi sia parla con la neutra")
    c.eq(len(d), 0, "e non consuma nessuna voce del pool")
    incerto.battute = 3
    dato = voce_per(d, "S0", incerto, neutra=neutra)
    c.eq(dato.gender, "m", "scaduto il rinvio si assegna col ripiego, che e' maschile")
    c.eq(voce_per(d, "S0", incerto, neutra=neutra).voice_id, dato.voice_id,
         "e da li' in poi la voce non cambia piu'")
    donna = FintoPersonaggio("f", 1)
    c.eq(voce_per(d, "S1", donna, neutra=neutra).gender, "f",
         "un sesso dichiarato non aspetta: si assegna subito")
    c.eq(voce_per(d, "S2", FintoPersonaggio("?", 3), neutra=neutra, ripiego="f").gender, "f",
         "il ripiego si puo' cambiare per una scena con voci femminili")

    # Esaurite le voci di un sesso si ripiega sull'altro invece di lasciare muto
    # un personaggio.
    r = VoicePool(voci)
    tutte = [r.voice_for(f"M{k}", gender="m") for k in range(len(voci) + 2)]
    c.eq(len(tutte), len(voci) + 2, "nessun personaggio resta senza voce")
    c.ok(r.collisions > 0, "e il riciclo si segnala invece di passare inosservato")


def test_tts_fake(c) -> None:
    c.group("tts")

    tts = ToneTts()
    voce = VoiceSpec("prova", "tone", "base", semitones=0.0, gender="m")
    s = tts.synthesize("Sali in macchina, muoviti!", voce)
    c.ok(s.duration > 0.5, "produce audio di durata plausibile")
    c.eq(s.samplerate, 22050, "riporta la propria frequenza")
    c.eq(s.voice_id, "prova", "riporta la voce usata")
    c.ok(float(np.abs(s.audio).max()) <= 1.0, "l'audio sta dentro il fondo scala")
    c.ok(s.rtf < 1.0, "sintetizza piu' in fretta di quanto duri")

    # **La velocita' chiesta a SuperTonic sta dentro cio' che accetta.** Fuori
    # dai suoi limiti il modello non rallenta: solleva `ValueError` e la sessione
    # finisce li'. Ed e' facile uscirne senza volerlo, perche' quel numero e' il
    # prodotto di tre decisioni prese in tre posti — ritmo di base 1,50, fretta
    # della catena fino a 1,45, carattere della voce. Col difetto, la scena del
    # concessionario si interrompeva alla battuta 10 di 44. Non serve il modello
    # per verificarlo, solo il conto.
    from speak.backends.supertonic import (
        DEFAULT_SPEED,
        VELOCITA_MAX,
        VELOCITA_MIN,
        velocita_effettiva,
    )

    # **Ogni motore dichiara il proprio passo, e nell'unita' giusta.** Il valore
    # di config era 17,4 misurato contando tutti i caratteri, ma viene diviso per
    # `spoken_length()`, che conta solo lettere e cifre: un quarto di errore su
    # ogni durata prevista, per tutti e due i backend. La verifica che lo
    # impedisce e' che il numero dichiarato stia dove sta la misura.
    from speak.base import ToneTts as _Tone
    from speak.backends.piper import PiperTts as _Piper
    from speak.backends.supertonic import SupertonicTts as _Super

    for motore, atteso in ((_Piper, 13.7), (_Tone, 14.0)):
        c.ok(
            10.0 <= motore.chars_per_second <= 20.0,
            f"{motore.name if hasattr(motore,'name') else motore.__name__}: "
            f"passo dichiarato plausibile ({motore.chars_per_second})",
        )
        c.close(motore.chars_per_second, atteso, f"e vale la misura ({atteso})", tol=0.1)
    # SuperTonic lo dichiara **in funzione della velocita'**, perche' misurato e'
    # lineare: chi cambia `tts.speed` non deve anche ricordarsi di aggiornare la
    # stima delle durate.
    c.close(_Super(speed=1.50).chars_per_second, 12.9, "supertonic a 1,50 fa 12,9 car/s", tol=0.1)
    c.close(_Super(speed=2.00).chars_per_second, 17.2, "e a 2,00 ne fa 17,2", tol=0.2)
    c.ok(
        _Super(speed=1.75).chars_per_second > _Super(speed=1.05).chars_per_second,
        "piu' velocita' vuol dire piu' caratteri al secondo",
    )

    c.close(velocita_effettiva(DEFAULT_SPEED, 1.0, 1.0), 1.50, "senza fretta si chiede il ritmo di base")
    c.eq(velocita_effettiva(DEFAULT_SPEED, 1.45, 1.0), VELOCITA_MAX,
         "con la fretta massima si chiede il massimo accettato, non 2,08")
    c.eq(velocita_effettiva(DEFAULT_SPEED, 0.1, 0.5), VELOCITA_MIN, "e sotto non si scende")
    for r in (0.5, 0.8, 1.0, 1.2, 1.45):
        for car in (0.96, 1.0, 1.05):
            v = velocita_effettiva(DEFAULT_SPEED, r, car)
            c.ok(VELOCITA_MIN <= v <= VELOCITA_MAX, f"rate {r} carattere {car}: {v:.2f} e' accettabile")

    lungo = tts.synthesize("a" * 100, voce)
    corto = tts.synthesize("a" * 20, voce)
    c.ok(lungo.duration > corto.duration, "un testo piu' lungo dura di piu'")

    veloce = tts.synthesize("a" * 60, voce, rate=1.5)
    normale = tts.synthesize("a" * 60, voce, rate=1.0)
    c.ok(veloce.duration < normale.duration, "rate maggiore accorcia")

    grave = VoiceSpec("g", "tone", "base", semitones=-5.0, gender="m")
    acuta = VoiceSpec("a", "tone", "base", semitones=+5.0, gender="m")
    c.ok(
        _f0(tts.synthesize("aaaa", grave).audio) < _f0(tts.synthesize("aaaa", acuta).audio),
        "i semitoni cambiano davvero l'intonazione",
    )
    femmina = VoiceSpec("f", "tone", "base", gender="f")
    c.ok(
        _f0(tts.synthesize("aaaa", femmina).audio) > _f0(tts.synthesize("aaaa", voce).audio),
        "la voce femminile e' piu' acuta di quella maschile",
    )

    c.eq(tts.synthesize("", voce).duration > 0, True, "anche un testo vuoto produce qualcosa")
    c.eq(SilentTts().synthesize("qualcosa", voce).audio.size, 0, "SilentTts non produce audio")


def test_mixer(c) -> None:
    c.group("mixer")

    sr = 48000
    mx = Mixer(samplerate=sr, duck_db=-12.0, attack_ms=20, release_ms=100)
    blocco = np.full((480, 2), 0.2, dtype=np.float32)  # 10 ms, tutto al centro

    out = mx.process(blocco)
    c.eq(out.shape, (480, 2), "la forma in uscita e' quella in ingresso")
    c.close(mx.now, 0.01, "il tempo avanza della durata del blocco")
    c.ok(np.allclose(out, blocco, atol=1e-4), "senza battute l'audio del gioco passa immutato")

    # Una battuta programmata deve comparire in uscita e abbassare il centro.
    voce = np.full(int(0.05 * sr), 0.3, dtype=np.float32)
    mx.schedule(voce, t_start=mx.now, speaker_id="S0", text="prova")
    c.eq(mx.pending, 1, "la battuta e' in coda")
    out = mx.process(blocco)
    c.ok(float(np.abs(out).max()) > 0.2, "la voce italiana si sente in uscita")
    mid = (out[:, 0] + out[:, 1]) * 0.5
    c.ok(float(mid[-1]) != 0.2, "il centro del gioco e' stato toccato")

    for _ in range(20):
        mx.process(blocco)
    c.eq(mx.pending, 0, "a battuta finita la coda si svuota")

    # Il duck agisce sul centro e non sui lati.
    mx2 = Mixer(samplerate=sr, duck_db=-20.0, attack_ms=1, release_ms=1000)
    largo = np.stack(
        [np.full(480, 0.3, np.float32), np.full(480, -0.3, np.float32)], axis=1
    )  # tutto laterale
    mx2.schedule(np.zeros(int(0.5 * sr), np.float32), t_start=0.0)
    for _ in range(10):
        fuori = mx2.process(largo)
    c.ok(
        np.allclose(fuori, largo, atol=1e-3),
        "mentre si parla, il contenuto laterale del gioco resta intatto",
    )

    mx3 = Mixer(samplerate=sr, duck_db=-20.0, attack_ms=1, release_ms=1000)
    centrato = np.full((480, 2), 0.3, np.float32)
    mx3.schedule(np.zeros(int(0.5 * sr), np.float32), t_start=0.0)
    for _ in range(10):
        fuori = mx3.process(centrato)
    c.ok(float(np.abs(fuori).max()) < 0.1, "mentre si parla, il centro del gioco e' abbassato")

    # Senza passthrough esce la sola voce.
    solo = Mixer(samplerate=sr, passthrough=False)
    solo.schedule(np.full(480, 0.5, np.float32), t_start=0.0)
    out = solo.process(blocco)
    c.ok(float(np.abs(out - 0.5).max()) < 1e-5, "senza passthrough resta solo la voce")

    # Senza audio di gioco serve la lunghezza.
    vuoto = Mixer(samplerate=sr)
    c.eq(vuoto.process(None, n=256).shape, (256, 2), "si puo' lavorare senza audio di gioco")
    c.raises(ValueError, lambda: Mixer(sr).process(None), "senza audio e senza n e' un errore")
    c.raises(
        ValueError, lambda: Mixer(sr).process(np.zeros((10, 5), np.float32)), "cinque canali no"
    )
    c.eq(Mixer(sr).process(np.zeros(480, np.float32)).shape, (480, 2), "un mono viene raddoppiato")

    # Una battuta in ritardo non si perde: si sposta e si conta.
    tardi = Mixer(samplerate=sr)
    tardi.process(blocco)
    tardi.schedule(np.full(240, 0.4, np.float32), t_start=0.0)
    c.eq(tardi.metrics.counter("mix.late").value, 1, "il ritardo viene contato")
    out = tardi.process(blocco)
    c.ok(float(np.abs(out).max()) > 0.2, "ma la battuta viene detta lo stesso")

    # Il limitatore interviene invece di tagliare.
    forte = Mixer(samplerate=sr, passthrough=False)
    forte.schedule(np.full(480, 3.0, np.float32), t_start=0.0)
    out = forte.process(None, n=480)
    c.ok(float(np.abs(out).max()) <= 1.0, "l'uscita non supera il fondo scala")
    c.eq(forte.metrics.counter("mix.limited").value, 1, "il limitatore si segnala")

    # clear e reset.
    pulizia = Mixer(samplerate=sr)
    pulizia.schedule(np.zeros(100, np.float32), 0.0)
    pulizia.schedule(np.zeros(100, np.float32), 0.0)
    c.eq(pulizia.clear(), 2, "clear svuota la coda")
    c.eq(pulizia.metrics.counter("mix.dropped").value, 2, "e conta cosa ha buttato")
    pulizia.process(blocco)
    pulizia.reset()
    c.close(pulizia.now, 0.0, "reset riporta il tempo a zero")


def test_embed(c) -> None:
    """L'impronta di chi parla, e soprattutto la trasformata che la precede.

    Nessun modello viene caricato: qui si prova cio' che sta *intorno* al
    modello, che e' esattamente dove si sbaglia in silenzio. Un banco mel
    spostato di un bin, una preenfasi applicata dopo la finestra o un'ampiezza
    nella scala sbagliata non danno errore: danno un embedding che separa
    qualcosa, ma non le voci. Il modello vero si verifica altrove, con una
    risposta nota — `tools.bench_speaker --clean` — perche' quella prova ha
    bisogno di sintetizzare, e la suite non sintetizza.
    """
    c.group("embed")

    from core.config import SpeakerConfig
    from listen.embed import (
        MODEL_RATE,
        MfccEmbedder,
        cmn,
        dct2,
        fbank,
        make_embedder,
        mel_bank,
        similarity,
        to_model_rate,
    )

    # 1. Il banco mel. Le colonne sono `n_fft // 2` e non una di piu': Kaldi
    #    scarta la banda di Nyquist, e un banco largo un bin di troppo non da'
    #    errore, da' tutte le bande spostate.
    bank = mel_bank(80, 512, MODEL_RATE)
    c.eq(bank.shape, (80, 256), "il banco ha 80 bande su 256 bin")
    c.ok(float(bank.min()) >= 0.0, "nessun peso negativo")
    c.ok(bool(np.all(bank.sum(axis=1) > 0)), "nessuna banda vuota")
    # I picchi salgono, ma non a ogni banda: sotto i 200 Hz le bande mel sono
    # piu' strette dei 31,25 Hz che separano due bin di FFT, quindi alcune
    # cadono sullo stesso bin. Pretendere una crescita stretta sarebbe chiedere
    # al banco una risoluzione che la finestra non ha.
    picchi = np.argmax(bank, axis=1)
    c.ok(bool(np.all(np.diff(picchi) >= 0)), "le bande salgono in frequenza, in ordine")
    c.ok(int(picchi[-1]) > int(picchi[0]) + 200, "e coprono lo spettro da un capo all'altro")
    c.raises(ValueError, lambda: mel_bank(80, 512, MODEL_RATE, 8000.0, 20.0), "banda assurda e' un errore")

    # 2. La trasformata contro una risposta nota: un tono puro deve accendere
    #    la banda che lo contiene. E' la forma che qui sostituisce l'inversa —
    #    una fbank non e' invertibile, ma sa dire dove ha messo l'energia.
    def banda_di(hz: float) -> int:
        m = 1127.0 * np.log(1.0 + hz / 700.0)
        m_low = 1127.0 * np.log(1.0 + 20.0 / 700.0)
        m_high = 1127.0 * np.log(1.0 + (MODEL_RATE / 2) / 700.0)
        return int(round((m - m_low) / ((m_high - m_low) / 81.0) - 1.0))

    t = np.arange(MODEL_RATE, dtype=np.float32) / MODEL_RATE
    for hz in (300.0, 1000.0, 4000.0):
        fb = fbank((0.3 * np.sin(2 * np.pi * hz * t)).astype(np.float32), MODEL_RATE)
        atteso = banda_di(hz)
        trovata = int(np.argmax(fb.mean(axis=0)))
        c.ok(abs(trovata - atteso) <= 1, f"un tono a {hz:.0f} Hz accende la banda {atteso} (trovata {trovata})")

    # 3. Il conto dei frame. Kaldi non riempie i bordi: da un secondo escono
    #    98 frame, non 100. Sbagliarlo di due non si vede a occhio e sposta
    #    ogni statistica temporale.
    fb = fbank(np.zeros(MODEL_RATE, np.float32) + 0.01, MODEL_RATE)
    c.eq(fb.shape, (98, 80), "un secondo a 16 kHz sono 98 frame da 80 bande")
    c.eq(fbank(np.zeros(100, np.float32), MODEL_RATE).shape, (0, 80), "meno di un frame non esplode")

    # 4. La media sottratta toglie cio' che e' costante, e il guadagno globale
    #    lo e': in scala logaritmica un fattore due e' un'offset uguale su tutte
    #    le bande. Due registrazioni della stessa voce a volume diverso devono
    #    dare la stessa cosa, altrimenti l'impronta misura la manopola.
    rng = np.random.default_rng(3)
    voce = (0.2 * rng.standard_normal(MODEL_RATE)).astype(np.float32)
    piano, forte = cmn(fbank(voce, MODEL_RATE)), cmn(fbank(voce * 4.0, MODEL_RATE))
    c.ok(float(np.abs(piano - forte).max()) < 1e-3, "la media sottratta annulla il guadagno")
    c.ok(float(np.abs(cmn(fbank(voce, MODEL_RATE)).mean(axis=0)).max()) < 1e-4, "e lascia media nulla")

    # 5. La DCT: ortonormale, quindi conserva la norma quando si tengono tutti
    #    i coefficienti.
    x = rng.standard_normal((7, 40))
    c.close(
        float(np.linalg.norm(dct2(x, 40))), float(np.linalg.norm(x)), "la DCT conserva la norma", tol=1e-3
    )

    # 6. Il backend leggero. Non deve riconoscere nessuno — non ne e' capace —
    #    ma deve essere deterministico, normalizzato e non esplodere sul vuoto.
    e = MfccEmbedder()
    a = e.embed(voce, MODEL_RATE)
    c.eq(a.shape, (e.dim,), f"l'impronta mfcc ha {e.dim} dimensioni")
    c.close(float(np.linalg.norm(a)), 1.0, "ed e' normalizzata", tol=1e-5)
    c.ok(np.array_equal(a, e.embed(voce, MODEL_RATE)), "due calcoli danno lo stesso vettore")
    c.close(similarity(a, a), 1.0, "il coseno con se stessi vale 1", tol=1e-5)
    c.ok(float(np.linalg.norm(e.embed(np.zeros(200, np.float32), MODEL_RATE))) == 0.0,
         "un ritaglio troppo corto da' il vettore nullo, non rumore")
    a48 = e.embed(to_model_rate(np.repeat(voce, 3), 48000), MODEL_RATE)
    c.ok(a48.shape == a.shape, "l'audio a 48 kHz arriva al modello nella forma giusta")

    # 7. `make_embedder`: il ripiego esiste ma si dichiara. Un ripiego
    #    silenzioso farebbe misurare il backend stupido credendo di misurare il
    #    modello, e la curva sbagliata sarebbe indistinguibile da quella giusta.
    cfg = SpeakerConfig()
    cfg.backend = "mfcc"
    c.eq(make_embedder(cfg).name, "mfcc", "il backend chiesto e' quello che si ottiene")
    cfg.backend = "sconosciuto"
    c.raises(ValueError, lambda: make_embedder(cfg), "un backend inventato e' un errore")
    cfg.backend = "none"
    c.raises(ValueError, lambda: make_embedder(cfg), "'none' non e' un'impronta")

    import listen.embed as _embed
    from pathlib import Path
    import tempfile

    cfg.backend = "ecapa-onnx"
    originale = _embed.ECAPA_DIR
    try:
        _embed.ECAPA_DIR = Path(tempfile.mkdtemp()) / "assente"
        ripiego = make_embedder(cfg, download=False, quiet=True)
        c.eq(ripiego.name, "mfcc", "modello assente: si ripiega")
        c.ok(ripiego.name != "ecapa-onnx", "e `.name` lo dice, cosi' il banco lo puo' stampare")
    finally:
        _embed.ECAPA_DIR = originale


def test_speaker(c) -> None:
    """Il tracker dei personaggi, su impronte costruite.

    Costruite perche' la risposta deve essere nota prima: su impronte vere "il
    tracker sbaglia" e "le voci non si distinguono" hanno lo stesso aspetto. Qui
    i vettori sono fabbricati in modo che la verita' sia scritta, e cio' che si
    verifica e' la *logica* — quale porta crea personaggi, quale no, e cosa
    succede quando l'impronta non c'e'.
    """
    c.group("speaker")

    from core.config import SpeakerConfig
    from listen.speaker import PLAUSIBILE_SOPRA, SpeakerTracker, stima_f0

    def voce(seed: int, rumore: float = 0.0) -> np.ndarray:
        """Un'impronta normalizzata: stessa `seed` = stessa persona."""
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(192).astype(np.float32)
        if rumore:
            v = v + rumore * np.random.default_rng(seed + 1000).standard_normal(192).astype(np.float32)
        return (v / np.linalg.norm(v)).astype(np.float32)

    cfg = SpeakerConfig()
    cfg.similarity = 0.55

    # 1. Due persone distinte, imparate dalle battute intere.
    t = SpeakerTracker(cfg)
    a1 = t.impara(voce(1), t=1.0)
    b1 = t.impara(voce(2), t=2.0)
    c.eq(len(t), 2, "due impronte lontane sono due personaggi")
    c.ok(a1.speaker_id != b1.speaker_id, "e prendono due identita' diverse")
    c.ok(b1.is_new, "il secondo si dichiara nuovo")
    a2 = t.impara(voce(1), t=3.0)
    c.eq(a2.speaker_id, a1.speaker_id, "la stessa impronta ritrova il suo personaggio")
    c.eq(len(t), 2, "e non ne apre un terzo")
    c.eq(t.get(a1.speaker_id).battute, 2, "il centroide ha imparato due battute")

    # 2. **Il difetto peggiore possibile, e la prova che lo vede.** La porta
    #    veloce riceve ritagli corti, che somigliano poco al proprio centroide:
    #    misurato, sotto 0,40 tre volte su quattro a 0,30 s. Se creasse
    #    personaggi, ne inventerebbe uno a ogni battuta — all'ascolto "la voce
    #    cambia in continuazione", che e' il guasto peggiore di tutti.
    prima = len(t)
    for k in range(20):
        d = t.scegli(voce(1, rumore=3.0), t=10.0 + k)
        c.ok(d.provisional, f"scelta {k}: si dichiara provvisoria") if k == 0 else None
    c.eq(len(t), prima, "venti scelte veloci non creano nemmeno un personaggio")

    # 3. Senza impronta non si inventa nessuno **e non si fa un nome**: la
    #    risposta e' anonima, cioe' la voce neutra. Prima si rispondeva l'ultimo
    #    che aveva parlato, che in un dialogo e' sbagliato una volta su due;
    #    misurato sulla scena vera, in quella fascia la porta veloce prendeva 2
    #    battute su 13.
    prima = len(t)
    d = t.scegli(None, t=30.0)
    c.eq(len(t), prima, "impronta assente: nessun personaggio nuovo")
    c.ok(d.anonima, "e non si fa un nome: la battuta e' anonima")
    d = t.scegli(np.zeros(192, np.float32), t=31.0)
    c.eq(len(t), prima, "impronta nulla: idem")
    c.ok(d.anonima, "e anche questa e' anonima")

    # 4. Un ritaglio senza voce da' somiglianze intorno a zero con tutti: la
    #    scelta veloce non deve prenderlo per un personaggio a caso.
    quasi = voce(99)
    d = t.scegli(quasi * 0.0 + 1e-6, t=32.0)
    c.ok(d.confidence < PLAUSIBILE_SOPRA + 1e-6, "impronta senza voce: fiducia bassa")
    c.ok(d.anonima, "e sotto la soglia del nome non si nomina nessuno")

    # **La soglia del nome, con la risposta nota.** Sopra si nomina, sotto no, e
    # il valore viene dalla tabella in `SpeakerConfig.name_min_score`.
    banca = SpeakerTracker(cfg)
    for _ in range(2):
        banca.impara(voce(41), t=0.0)
    forte = banca.scegli(voce(41), t=1.0)
    c.ok(not forte.anonima, "un'impronta che somiglia molto riceve un nome")
    c.ok(forte.confidence >= cfg.name_min_score, "e il punteggio sta sopra la soglia")
    debole = banca.scegli(voce(41, rumore=6.0), t=2.0)
    if debole.confidence < cfg.name_min_score:
        c.ok(debole.anonima, "una che somiglia poco resta anonima")

    # 5. Il tetto: oltre `max_speakers` ci si attacca al migliore invece di
    #    lasciare un personaggio senza voce.
    stretto = SpeakerTracker(SpeakerConfig())
    stretto.cfg.similarity = 0.9
    stretto.cfg.max_speakers = 3
    for s in range(10):
        stretto.impara(voce(100 + s), t=float(s))
    c.eq(len(stretto), 3, "non si superano i max_speakers")

    # 6. Un tracker vuoto non esplode, e il primo che parla apre il primo posto.
    vuoto = SpeakerTracker(cfg)
    d = vuoto.scegli(voce(7), t=0.0)
    c.eq(len(vuoto), 0, "a banca vuota la porta veloce non iscrive nessuno")
    c.ok(d.anonima, "e a banca vuota non fa nemmeno un nome")
    c.ok(d.provisional, "dichiarando la scelta provvisoria")
    c.eq(vuoto.impara(voce(7), t=0.1).speaker_id, "S0", "e la porta lenta la conferma")
    c.eq(len(vuoto), 1, "iscrivendola davvero")
    vuoto.reset()
    c.eq(len(vuoto), 0, "reset svuota la banca")
    c.ok("nessun personaggio" in vuoto.report(), "e il report lo dice")

    # 7. L'intonazione, con risposta nota: una sinusoide a 120 Hz vale 120 Hz.
    for hz in (110.0, 200.0):
        sr = 16000
        tt = np.arange(int(0.8 * sr), dtype=np.float32) / sr
        onda = sum((0.5 / k) * np.sin(2 * np.pi * hz * k * tt) for k in (1, 2, 3)).astype(np.float32)
        c.close(stima_f0(onda, sr), hz, f"l'intonazione a {hz:.0f} Hz si ritrova", tol=6.0)
    c.eq(stima_f0(np.zeros(16000, np.float32), 16000), 0.0, "sul silenzio non si inventa")
    c.eq(stima_f0(np.zeros(10, np.float32), 16000), 0.0, "e su un frammento nemmeno")

    # 8. Il genere segue l'intonazione, con una fascia morta in mezzo: li' un
    #    uomo chiaro e una donna scura non si distinguono, e "non so" fa
    #    scegliere al pool la prossima voce libera invece di quella sbagliata.
    t2 = SpeakerTracker(cfg)
    for k, hz in enumerate((120.0, 124.0, 118.0)):
        t2.impara(voce(11), t=0.1 * k, f0=hz)
    c.eq(t2.people[0].gender, "?", "tre misure non bastano ancora a dichiarare un sesso")
    t2.impara(voce(11), t=0.5, f0=122.0)
    c.eq(t2.people[0].gender, "m", "120 Hz confermati quattro volte sono maschile")
    for k, hz in enumerate((220.0, 214.0, 231.0, 226.0)):
        t2.impara(voce(12), t=1.0 + 0.1 * k, f0=hz)
    c.eq(t2.people[1].gender, "f", "220 Hz sono femminile")
    for k, hz in enumerate((190.0, 188.0, 186.0, 191.0)):
        t2.impara(voce(13), t=2.0 + 0.1 * k, f0=hz)
    c.eq(t2.people[2].gender, "?", "fra le due soglie non si sa, e lo dice")
    t2.impara(voce(14), t=3.0)
    c.eq(t2.people[3].gender, "?", "senza intonazione non si sa")

    # **La prova che ha cambiato `MISURE_MINIME`.** I primi due ritagli di Lamar
    # misurano 242 e 193 Hz: con due misure il tracker lo dichiarava femmina, la
    # voce partiva femminile e non si toccava piu'. Le misure vere di quel
    # personaggio, in ordine, non devono mai produrre una "f".
    lamar = SpeakerTracker(cfg)
    generi = []
    for k, hz in enumerate((242.8, 193.1, 194.0, 145.8, 201.3, 165.8, 184.0, 205.8, 176.8)):
        lamar.impara(voce(31), t=float(k), f0=hz)
        generi.append(lamar.people[0].gender)
    c.ok("f" not in generi, "le misure vere di un uomo non danno mai 'femminile'")
    c.eq(generi[-1], "?", "restano un onesto 'non si sa'")

    # **La mediana invece della media mobile**, con la prova che le distingue:
    # un solo ritaglio in cui l'intonazione e' quella della musica. La media
    # mobile ci si sposta e non torna piu'; la mediana lo ignora.
    t3 = SpeakerTracker(cfg)
    for hz in (118.0, 260.0, 122.0, 126.0):
        t3.impara(voce(21), t=0.0, f0=hz)
    c.close(t3.people[0].f0, 124.0, "un valore fuori posto non sposta la mediana", tol=3.0)
    c.eq(t3.people[0].gender, "m", "e il sesso resta quello giusto")
    c.ok(t3.people[0].f0_dispersione < 10.0, "misure d'accordo: dispersione bassa")
    t4 = SpeakerTracker(cfg)
    for hz in (98.0, 268.0, 171.0, 248.0):  # i valori veri di Lamar, in miniatura
        t4.impara(voce(22), t=0.0, f0=hz)
    c.ok(t4.people[0].f0_dispersione > 40.0, "misure sparse: la dispersione lo dice")

    # 9. **La fusione**, su vettori costruiti perche' la risposta sia scritta.
    #    Il difetto vero: dal vivo, sedici identita' per tre personaggi reali.
    #    Qui si riproduce in piccolo — una persona spezzata in due — e si verifica
    #    che il secondo pezzo venga riassorbito quando, e non prima che, i due
    #    centroidi si somiglino abbastanza.
    def asse(*coefficienti: float) -> np.ndarray:
        v = np.zeros(192, np.float32)
        for i, x in enumerate(coefficienti):
            v[i] = x
        return (v / np.linalg.norm(v)).astype(np.float32)

    def scena(soglia_fusione: float) -> SpeakerTracker:
        """S0, un frammento S1 che gli somiglia poco, e una battuta che li avvicina."""
        cfg2 = SpeakerConfig()
        cfg2.similarity = 0.55
        cfg2.merge_similarity = soglia_fusione
        s = SpeakerTracker(cfg2)
        s.impara(asse(1.0, 0.0), t=0.0)  # S0
        s.impara(asse(0.5, 0.866), t=1.0)  # 0,50 con S0: sotto soglia, si apre S1
        # 0,90 con S0 contro 0,83 con S1: va a S0, e ne sposta il centroide fino
        # a 0,681 da S1. E' il meccanismo vero — il centroide si arricchisce e i
        # due frammenti si somigliano sempre di piu' — in tre battute.
        s.impara(asse(0.9, 0.436), t=2.0)
        return s

    unita = scena(0.65)  # i due centroidi finiscono a 0,681 l'uno dall'altro
    c.eq(len(unita), 1, "due frammenti della stessa persona tornano un personaggio solo")
    c.eq(len(unita.people), 2, "il frammento resta in banca, non si cancella")
    c.eq(unita.fusioni[0][:2], ("S1", "S0"), "vince chi ha piu' battute, non chi e' comparso prima")
    c.eq(unita.risolvi("S1"), "S0", "e il vecchio id continua a portare al personaggio vivo")
    c.eq(unita.get("S1").speaker_id, "S0", "anche chiedendo il personaggio per il vecchio id")
    c.eq(unita.get("S0").battute, 3, "le battute del frammento si sommano a quelle del vincitore")
    c.ok("fuso in S0" in unita.report(), "il report dice dove e' finito, invece di farlo sparire")

    separate = scena(0.75)  # sopra la somiglianza raggiunta: non si deve fondere
    c.eq(len(separate), 2, "sopra la soglia i due restano due")
    c.eq(len(separate.fusioni), 0, "e non risulta nessuna fusione")

    spenta = SpeakerTracker(SpeakerConfig())
    spenta.cfg.merge = False
    spenta.cfg.merge_similarity = 0.10  # fonderebbe qualunque cosa, se fosse accesa
    spenta.impara(asse(1.0, 0.0), t=0.0)
    spenta.impara(asse(0.5, 0.866), t=1.0)
    spenta.impara(asse(0.8, 0.6), t=2.0)
    c.eq(len(spenta), 2, "con `merge` spento non si fonde niente, qualunque sia la soglia")

    # Gli id non si riusano dopo una fusione: due battute lontane non devono
    # potersi ritrovare con lo stesso nome.
    dopo = scena(0.65)
    dopo.impara(asse(0.0, 0.0, 1.0), t=3.0)
    c.eq(sorted(p.speaker_id for p in dopo.people), ["S0", "S1", "S2"], "il nuovo id e' S2, non S1")

    # La porta veloce non propone piu' un'identita' assorbita: sarebbe una voce
    # che il pool ha gia' spostato altrove.
    veloce = scena(0.65)
    veloce.impara(asse(0.5, 0.866), t=4.0)  # il vincitore diventa confermato di sicuro
    d = veloce.scegli(asse(0.9, 0.4), t=5.0)
    c.ok(veloce.get(d.speaker_id).merged_into is None, "la scelta veloce nomina solo identita' vive")
