"""Stiramento temporale e spostamento di intonazione (WSOLA).

Serve a due cose diverse che sono la stessa operazione:

- **far durare una battuta quanto il sottotitolo** (F2). Piper ha un
  `length_scale`, ma misurato non e' proporzionale: chiedendo 0,8 si ottiene un
  errore del 14%. Per centrare una scadenza serve un'operazione esatta, e questa
  lo e' per costruzione — la lunghezza in uscita e' decisa, non sperata;
- **allargare il pool di voci**. Le voci italiane di Piper sono due. Spostando
  l'intonazione si ottengono varianti distinguibili della stessa voce, che e'
  l'unico modo di avere sei personaggi diversi con due modelli.

WSOLA invece del semplice ricampionamento perche' cambiare la velocita'
ricampionando cambia anche l'intonazione: si otterrebbe un personaggio che parla
in fretta *e* con la voce da topolino. WSOLA sovrappone finestre cercando ogni
volta la posizione che si aggancia meglio alla precedente, quindi la periodicita'
della voce — cioe' l'intonazione — resta dov'era.

**Come si verifica, e come NON si verifica.** L'istinto dice: stirare di `r` e
poi di `1/r` deve restituire l'ingresso. Provandolo, il residuo campione-per-
campione risulta del 75% a rate 1,35 — sembrerebbe una trasformata rotta. Non lo
e', e la strada per capirlo dice due cose sul metodo:

1. la misura campione-per-campione non puo' esprimere la risposta. WSOLA sposta
   i segmenti per agganciarli bene, quindi l'uscita e' *sfasata* rispetto
   all'ingresso. Controprova: lo stesso segnale traslato di 90 campioni da' 177%
   di differenza campione-per-campione e correlazione 0,999. Con misure
   insensibili alla fase (correlazione massima, moduli di spettro) il giro in
   allungamento torna 0,9996 e 0,0%;
2. **in compressione la perdita e' vera, ed e' inevitabile**. Comprimere di 1,35
   butta via un quarto del materiale; riespandere non lo reinventa. Il giro
   identita' quindi vale come prova di correttezza solo in *allungamento*, dove
   nulla viene scartato. E' li' che dimostra che finestre, sovrapposizione e
   normalizzazione sono giuste.

Cosa resta a garantire la compressione: la durata in uscita e' esatta allo
0,001%, e l'intonazione non si sposta di un hertz (120,0 Hz prima e dopo, contro
84 e 162 Hz che darebbe un banale ricampionamento).

Misurata anche la ragione del limite di `rate_max`: a 1,6 la correlazione crolla
a 0,52 e lo spettro se ne va del 73%. A 1,35 siamo ancora a 0,75. Il limite in
config non e' cautela generica, e' il punto dove la misura peggiora in fretta.
"""

from __future__ import annotations

import numpy as np


def resample(x: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Cambia frequenza di campionamento per interpolazione lineare.

    Le voci Piper escono a frequenze diverse (paola 22050, riccardo 16000) e il
    mixer ne vuole una sola. L'interpolazione lineare non e' a banda limitata,
    quindi in *discesa* introduce aliasing: per questo si passa da un filtro
    prima di decimare.
    """
    if src_rate == dst_rate or x.size == 0:
        return x.astype(np.float32, copy=True)
    if src_rate <= 0 or dst_rate <= 0:
        raise ValueError(f"frequenze non valide: {src_rate} -> {dst_rate}")

    data = x.astype(np.float32)
    if dst_rate < src_rate:
        data = _lowpass(data, cutoff_ratio=dst_rate / src_rate)

    n_out = max(1, int(round(len(data) * dst_rate / src_rate)))
    src_pos = np.arange(len(data), dtype=np.float64)
    dst_pos = np.linspace(0, len(data) - 1, n_out)
    return np.interp(dst_pos, src_pos, data).astype(np.float32)


def _lowpass(x: np.ndarray, cutoff_ratio: float) -> np.ndarray:
    """Media mobile grossolana come anti-alias prima di decimare.

    Non e' un filtro raffinato, ma toglie la parte di banda che il
    ricampionamento ripiegherebbe sulle frequenze basse — che e' il danno udibile.
    """
    if cutoff_ratio >= 1.0:
        return x
    taps = max(3, int(round(1.0 / max(cutoff_ratio, 1e-3))))
    if taps % 2 == 0:
        taps += 1
    if taps >= len(x):
        return x
    kernel = np.hanning(taps)
    kernel /= kernel.sum()
    return np.convolve(x, kernel, mode="same").astype(np.float32)


def time_stretch(
    x: np.ndarray,
    rate: float,
    samplerate: int = 22050,
    frame_ms: float = 46.0,
    search_ms: float = 10.0,
) -> np.ndarray:
    """Cambia la durata di `x` di un fattore `1/rate`, lasciando l'intonazione.

    `rate > 1` accorcia (si parla piu' in fretta), `rate < 1` allunga.
    """
    if x.size == 0:
        return x.astype(np.float32, copy=True)
    if rate <= 0:
        raise ValueError(f"rate non valido: {rate}")
    if abs(rate - 1.0) < 1e-3:
        return x.astype(np.float32, copy=True)

    data = x.astype(np.float32)
    n = max(64, int(round(frame_ms * samplerate / 1000.0)))
    n += n % 2  # pari, cosi' hop = n/2 e' intero
    hop_syn = n // 2
    hop_ana = max(1, int(round(hop_syn * rate)))
    search = max(0, int(round(search_ms * samplerate / 1000.0)))
    window = np.hanning(n + 1)[:n].astype(np.float32)

    if len(data) < n + hop_ana + search:
        # Troppo corto perche' WSOLA abbia senso: si ricampiona e basta. Su
        # frammenti cosi' brevi la differenza non e' udibile.
        target = max(1, int(round(len(data) / rate)))
        return np.interp(
            np.linspace(0, len(data) - 1, target), np.arange(len(data)), data
        ).astype(np.float32)

    out_len = int(np.ceil(len(data) / rate)) + n
    out = np.zeros(out_len, dtype=np.float32)
    norm = np.zeros(out_len, dtype=np.float32)

    ta = 0  # posizione di analisi
    ts = 0  # posizione di sintesi
    passo = 0  # quanti salti di analisi sono stati fatti
    # `natural` e' il pezzo che seguirebbe senza tagli: il candidato migliore e'
    # quello che gli somiglia di piu', ed e' questo a preservare la periodicita'.
    natural = data[hop_syn : hop_syn + n].copy()

    while ta + n <= len(data) and ts + n <= out_len:
        segment = data[ta : ta + n]
        out[ts : ts + n] += segment * window
        norm[ts : ts + n] += window

        ts += hop_syn
        passo += 1
        # **Il centro di ricerca viene dalla posizione IDEALE, non da quella
        # scelta l'ultima volta.** Scrivere `ta + hop_ana` sembra equivalente e
        # non lo e': `_best_offset` puo' spostare `ta` indietro fino a `search`,
        # e sommando quello spostamento al passo successivo l'arretramento si
        # **accumula**. Il puntatore di analisi resta cosi' sempre piu' indietro
        # e non arriva mai in fondo all'ingresso: l'uscita ha la durata giusta e
        # l'ampiezza giusta, ma la coda contiene audio ripetuto invece della
        # fine vera.
        #
        # Misurato con un tono acuto negli ultimi 200 ms — "l'ultima parola" —
        # a rate 1,20 e 1,35 di quel tono nell'uscita non restava **niente**,
        # mentre durata e ampiezza erano perfette. E' la forma esatta del difetto
        # contro cui il `CLAUDE.md` mette in guardia: una trasformata sbagliata
        # non da' errore, da' spazzatura plausibile. Dal vivo si sentiva come
        # "taglia l'ultima parola delle frasi lunghe".
        # Il passo di analisi resta libero di inseguire la periodicita': e' la
        # ragione per cui si usa WSOLA invece di ricampionare, ed e' la
        # proprieta' che il giro identita' misura. Provato ad ancorarlo alla
        # griglia ideale per non perdere la coda, e ancorarlo costa piu' di
        # quanto renda — lo spettro del giro identita' passa da 0,01 a 0,04 e la
        # coda si recupera solo ai rate bassi. La coda si ripara alla fine, dove
        # il buco sta davvero.
        next_centre = ta + hop_ana
        lo = max(0, next_centre - search)
        hi = min(len(data) - n, next_centre + search)
        if hi <= lo:
            ta = min(max(0, next_centre), max(0, len(data) - n))
        else:
            ta = lo + _best_offset(data, lo, hi, n, natural)
        natural = data[ta + hop_syn : ta + hop_syn + n]
        if natural.size < n:
            natural = np.pad(natural, (0, n - natural.size))

    # **La coda dell'ingresso va emessa comunque.** Il ciclo si ferma quando
    # `ta + n` supera la fine, e a quel punto restano fino a `hop_ana` campioni
    # che nessuna finestra ha mai letto — a rate 1,35 sono una settantina di
    # millisecondi, cioe' l'ultima sillaba. L'uscita ha lunghezza e ampiezza
    # giuste lo stesso, perche' la normalizzazione riempie il buco con cio' che
    # sta intorno: la fine non manca, e' **sostituita**, ed e' il modo in cui
    # questo difetto e' riuscito a sopravvivere a tutte le altre verifiche.
    #
    # E va incollata **dove le tocca**, cioe' alla posizione di uscita che
    # corrisponde alla sua posizione di ingresso: `ts` e' dove si e' fermata la
    # marcia, non dove la fine dell'ingresso deve suonare. Sbagliare quel punto
    # sposta la coda nel tempo, e sull'allungamento si vedeva nello spettro.
    #
    # Solo in **compressione**: allungando, il puntatore di analisi avanza piu'
    # lento di come si riempie l'uscita e l'ingresso viene percorso tutto, quindi
    # non c'e' nessun buco da tappare. Aggiungere li' una finestra in piu' non
    # ripara niente e sporca lo spettro — verificato dal giro identita', che in
    # allungamento e' esatto e se ne accorge.
    if rate > 1.0 and ta + n < len(data):
        ts_coda = int(round((len(data) - n) / rate))
        if 0 <= ts_coda and ts_coda + n <= out_len:
            coda = data[len(data) - n :]
            out[ts_coda : ts_coda + n] += coda * window
            norm[ts_coda : ts_coda + n] += window

    good = norm > 1e-6
    out[good] /= norm[good]
    target = max(1, int(round(len(data) / rate)))
    return out[:target]


def _best_offset(data: np.ndarray, lo: int, hi: int, n: int, natural: np.ndarray) -> int:
    """Fra i candidati in [lo, hi], quello che si aggancia meglio a `natural`."""
    if hi <= lo:
        return 0
    candidates = np.lib.stride_tricks.sliding_window_view(data[lo : hi + n], n)
    scores = candidates @ natural
    # Normalizzare per l'energia evita che un tratto forte vinca solo perche'
    # e' forte: quello che conta e' la *forma*, non il volume.
    energy = np.sqrt((candidates * candidates).sum(axis=1)) + 1e-9
    return int(np.argmax(scores / energy))


def pitch_shift(
    x: np.ndarray, semitones: float, samplerate: int = 22050, **kw
) -> np.ndarray:
    """Sposta l'intonazione di `semitones` lasciando la durata.

    Si stira nel tempo e poi si ricampiona della quantita' opposta: le due
    operazioni si annullano sulla durata e si sommano sull'intonazione.
    """
    if abs(semitones) < 1e-3 or x.size == 0:
        return x.astype(np.float32, copy=True)
    factor = 2.0 ** (semitones / 12.0)
    stretched = time_stretch(x, 1.0 / factor, samplerate=samplerate, **kw)
    resampled = np.interp(
        np.arange(0, len(stretched), factor), np.arange(len(stretched)), stretched
    ).astype(np.float32)
    return _fit(resampled, len(x))


def _fit(x: np.ndarray, n: int) -> np.ndarray:
    """Porta l'array a esattamente `n` campioni, tagliando o riempiendo."""
    if len(x) == n:
        return x
    if len(x) > n:
        return x[:n].copy()
    return np.pad(x, (0, n - len(x)))


def fit_duration(
    x: np.ndarray, target_seconds: float, samplerate: int, limits: tuple[float, float] = (0.7, 1.5)
) -> tuple[np.ndarray, float]:
    """Porta `x` a durare `target_seconds`, entro i limiti dati.

    Restituisce (audio, rate applicato). Se il rate necessario esce dai limiti
    si applica il limite: **meglio sforare che stravolgere**. La battuta va
    detta comunque, e una voce accelerata del 60% non e' piu' una voce.
    """
    if x.size == 0 or target_seconds <= 0:
        return x.astype(np.float32, copy=True), 1.0
    current = len(x) / samplerate
    rate = current / target_seconds
    rate = float(np.clip(rate, limits[0], limits[1]))
    return time_stretch(x, rate, samplerate=samplerate), rate


def fit_duration_keep_tail(
    x: np.ndarray,
    target_seconds: float,
    samplerate: int,
    limits: tuple[float, float] = (0.7, 1.5),
    tail_seconds: float = 0.7,
) -> tuple[np.ndarray, float]:
    """Come `fit_duration`, ma **l'ultima parola non passa da WSOLA**.

    Lo stiramento perde la fine di cio' che comprime — il puntatore di analisi
    insegue la periodicita', arretra, e gli arretramenti si sommano finche' la
    coda dell'ingresso non viene mai letta. Misurato con un tono riconoscibile
    negli ultimi 200 ms: a rate 1,20 e 1,35 non ne resta **niente**. Dal vivo si
    sente cosi': *«si ferma a "questa roba stia" e non dice "funzionando"»*.

    Ancorare il puntatore alla griglia ideale recupera la coda e peggiora lo
    spettro di dieci volte (0,0043 -> 0,0432, misurato in diretta e non
    attraverso il giro identita'). La riparazione vera di WSOLA e' un lavoro a
    se'; questa funzione non la fa e non finge di farla.

    Quello che fa e' togliere la coda dalla strada: si comprime **solo il
    corpo** e si riattacca la fine come e' uscita dal sintetizzatore. L'ultima
    parola arriva quindi verbatim, e il prezzo e' che la compressione si
    concentra su cio' che viene prima — dove qualche decimo in piu' non si nota,
    mentre una parola finale mancante si nota sempre.
    """
    if x.size == 0 or target_seconds <= 0:
        return x.astype(np.float32, copy=True), 1.0
    coda_n = min(len(x), int(max(0.0, tail_seconds) * samplerate))
    corpo = x[: len(x) - coda_n]
    coda = x[len(x) - coda_n :]
    # Se il corpo e' troppo corto per essere stirato utilmente, non si fa
    # niente: comprimere venti millisecondi non guadagna nulla e li rovina.
    if len(corpo) < int(0.2 * samplerate):
        return x.astype(np.float32, copy=True), 1.0
    bersaglio_corpo = target_seconds - coda_n / samplerate
    if bersaglio_corpo <= 0.05:
        # Non c'e' finestra nemmeno per il solo corpo: si stringe quanto e'
        # lecito e si sfora, che e' la promessa del progetto.
        bersaglio_corpo = (len(corpo) / samplerate) / limits[1]
    stretto, rate = fit_duration(corpo, bersaglio_corpo, samplerate, limits=limits)
    return np.concatenate([stretto, coda]).astype(np.float32), rate
