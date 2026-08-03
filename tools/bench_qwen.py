"""Il banco di Qwen3-TTS: e' fedele? e si puo' spezzare?

Due domande, e la seconda decide se lo streaming di questo motore esiste.

## 1. Il ciclo srotolato e' fedele all'originale? (`--riferimento`)

`speak/backends/qwen.py` non chiama piu' `generate_onnx()`: ne ha trascritto il
ciclo autoregressivo in tre pezzi, perche' lo streaming ha bisogno dei frame
**mentre** escono. Una trascrizione che *quasi* coincide produce parlato
plausibile e sbagliato — e' la stessa forma della trasformata verificata contro
la propria inversa, e in questo progetto ha gia' pagato due volte.

Stesso seme, stesso testo, stessa voce, e si confrontano i campioni.
**Cosa smentisce**: campioni diversi. Il modello campiona da un RNG globale, ma i
due percorsi partono dallo stesso stato e fanno le stesse estrazioni nello stesso
ordine: se il risultato differisce, la trascrizione ha cambiato qualcosa.

## 2. Il vocoder si puo' chiamare su un pezzo? (`--vocoder`)

E' **la** domanda dello streaming. Il modello genera 12 frame al secondo e sta
avanti da solo (0,66x tempo reale), ma per far uscire audio prima della fine
bisogna vocodare i primi frame **senza avere i successivi**. Se il vocoder e' una
rete convoluzionale non causale, il pezzo vocodato da solo non e' il pezzo giusto:
ai bordi ci mette quello che sa, cioe' silenzio, e all'ascolto sono click.

Si generano i codici una volta sola, poi si vocoda tutto, poi si vocodano prefissi
e blocchi e si confrontano con la porzione corrispondente dell'intero.

**Cosa smentisce lo streaming a blocchi**: se anche togliendo una guardia di
qualche frame ai bordi la correlazione con l'intero resta sotto 0,99 (o l'errore
RMS relativo sopra il 5%), il vocoder non e' troncabile e lo streaming di questo
motore non e' il lavoro che si credeva: servirebbe un vocoder causale, che non
c'e'. Scritto **prima** della prova, come si deve: una previsione dichiarata dopo
non puo' perdere.

## Uso

    .\\.venv\\Scripts\\python.exe -m tools.bench_qwen --riferimento
    .\\.venv\\Scripts\\python.exe -m tools.bench_qwen --vocoder
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from core.types import VoiceSpec
from fuse.timing import spoken_length
from speak.backends.qwen import NATIVE_RATE

TESTO ="Lavoriamo insieme gia' da qualche mese, giusto? Devo dare una svolta alla mia vita."
VOCE = "qwen-uomo1"


def _voce(base: str = VOCE) -> VoiceSpec:
    return VoiceSpec(
        voice_id="banco", backend="qwen", base_voice=base,
        semitones=0.0, rate=1.0, gender="m",
    )


def _confronta(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Correlazione ed errore RMS relativo fra due tratti della stessa lunghezza."""
    n = min(len(a), len(b))
    a, b = a[:n].astype(np.float64), b[:n].astype(np.float64)
    if n == 0:
        return float("nan"), float("nan")
    rms = float(np.sqrt(np.mean(b * b)))
    err = float(np.sqrt(np.mean((a - b) ** 2)))
    da, db = a - a.mean(), b - b.mean()
    den = float(np.sqrt((da * da).sum() * (db * db).sum()))
    corr = float((da * db).sum() / den) if den > 0 else float("nan")
    return corr, (err / rms if rms > 0 else float("nan"))


def prova_riferimento(tts) -> bool:
    """Il ciclo srotolato contro `generate_onnx()`, stesso seme.

    **L'unita' del confronto e' il passo di quantizzazione, e trovarla ha corretto
    due volte il criterio.** La funzione originale non restituisce campioni: scrive
    un WAV, e `soundfile` lo scrive in PCM a 16 bit.

    Il primo criterio chiedeva uno scarto sotto 1e-5 e ha risposto «diversi» con
    3,052e-05, che e' **esattamente** 2^-15. Il secondo riquantizzava anche il
    nostro a 16 bit e contava i campioni diversi: 71916 su 143653, cioe' meta' —
    ma quella meta' e' solo il verso dell'arrotondamento, perche' `np.round` e la
    conversione di `soundfile` non arrotondano allo stesso modo.

    Il criterio giusto e' il terzo: **lo scarto massimo non supera un passo**. Una
    trascrizione infedele non sbaglia di un LSB, sbaglia un'estrazione — e da li'
    in poi il testo detto e' un altro, cioe' scarti dell'ordine di 0,1. Fra 3e-05
    e 1e-01 non c'e' nulla da interpretare.
    """
    voce = _voce()
    print("== fedelta' del ciclo srotolato ==")
    mio = tts.synthesize(TESTO, voce)
    rif = tts.synthesize_riferimento(TESTO, voce)
    print(f"  srotolato : {len(mio.audio):7d} campioni, {mio.total_ms:7.0f} ms")
    print(f"  originale : {len(rif.audio):7d} campioni, {rif.total_ms:7.0f} ms")
    if len(mio.audio) != len(rif.audio):
        print("  DIVERSI: lunghezze differenti -> la trascrizione non e' fedele.")
        return False

    lsb = 2.0 ** -15
    d = np.abs(mio.audio - rif.audio) if mio.audio.size else np.zeros(1)
    print(f"  scarto massimo: {d.max():.3e} = {d.max() / lsb:.2f} passi a 16 bit")
    print(f"  scarto medio  : {d.mean():.3e} = {d.mean() / lsb:.2f} passi")
    ok = bool(d.max() <= 1.01 * lsb)
    print("  " + (
        "FEDELE: differiscono solo per la scrittura del WAV a 16 bit."
        if ok else "DIVERSI: la trascrizione ha cambiato qualcosa."
    ))
    return ok


def prova_vocoder(tts) -> bool:
    """Il vocoder si puo' chiamare su un prefisso, o mente ai bordi?"""
    voce = _voce()
    print("== il vocoder e' troncabile? ==")

    np.random.seed(1234)
    t0 = time.perf_counter()
    st = tts._stato(TESTO, tts._descrizione(voce))
    ms_prefill = (time.perf_counter() - t0) * 1000.0
    t0 = time.perf_counter()
    frames = list(tts._codici(st))
    ms_passi = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    intero = tts._onda(frames)
    ms_voc = (time.perf_counter() - t0) * 1000.0

    T = len(frames)
    if T == 0:
        print("  nessun frame generato.")
        return False
    hop = len(intero) / T
    print(f"  frame: {T}   campioni: {len(intero)}   passo: {hop:.1f} campioni/frame"
          f"  ({hop / 24000 * 1000:.1f} ms)")
    print(f"  prefill {ms_prefill:.0f} ms | {ms_passi / T:.1f} ms/frame | vocoder {ms_voc:.0f} ms")
    print(f"  il modello gira a {ms_passi / (T * hop / 24000 * 1000):.2f}x tempo reale")

    hop_i = int(round(hop))
    print("\n  -- prefisso: vocoder(codici[:k]) contro l'intero --")
    print(f"  {'k':>4} {'guardia':>8} {'corr':>9} {'err rms':>9}")
    ok = False
    for k in (2, 4, 8, 16, 32):
        if k >= T:
            break
        pezzo = tts._onda(frames[:k])
        for guardia in (0, 1, 2, 4):
            n = (k - guardia) * hop_i
            if n <= 0:
                continue
            corr, err = _confronta(pezzo[:n], intero[:n])
            print(f"  {k:>4} {guardia:>8} {corr:>9.4f} {err:>9.4f}")
            if k >= 4 and corr >= 0.99 and err <= 0.05:
                ok = True
        print()

    print("  -- blocco interno: vocoder(codici[a:b]) contro l'intero --")
    print(f"  {'a':>4} {'b':>4} {'guardia':>8} {'corr':>9} {'err rms':>9}")
    for a, b in ((8, 16), (16, 32)):
        if b >= T:
            break
        pezzo = tts._onda(frames[a:b])
        for guardia in (0, 1, 2):
            i0 = guardia * hop_i
            i1 = (b - a - guardia) * hop_i
            if i1 <= i0:
                continue
            corr, err = _confronta(pezzo[i0:i1], intero[a * hop_i + i0 : a * hop_i + i1])
            print(f"  {a:>4} {b:>4} {guardia:>8} {corr:>9.4f} {err:>9.4f}")
        print()

    print("  verdetto: " + (
        "il vocoder e' troncabile, lo streaming a blocchi si puo' fare."
        if ok else
        "il pezzo vocodato da solo NON e' il pezzo giusto: streaming a blocchi non"
        " trasparente."
    ))
    return ok


def prova_streaming(tts) -> None:
    """Quanto costa davvero un frame, e quanto costa rivocodare il prefisso.

    Due numeri che decidono tutto, e nessuno dei due si legge da una passata sola.

    **Il passo.** La misura archiviata diceva 55,3 ms per frame, cioe' 0,66x tempo
    reale: il modello sta avanti da solo e lo streaming e' possibile. Ma la prima
    passata di `--vocoder` ha dato 85,8 ms, cioe' **1,07x** — piu' lento del tempo
    reale, che vorrebbe dire uno streaming che balbetta. La differenza e' il
    riscaldamento: i primi passi su CUDA compilano i kernel. Qui si scalda prima, e
    si guarda la mediana invece della media, perche' e' la media che il primo passo
    trascina.

    **La rivocodifica.** Il blocco interno non e' utilizzabile (corr 0,95): si
    vocoda ogni volta il **prefisso intero** e si tiene solo la coda nuova. E'
    trasparente, ma costa O(k) a ogni blocco, cioe' O(T^2/blocco) in tutto. Se quel
    costo supera il tempo che il blocco dura, lo streaming non recupera piu'.
    """
    voce = _voce()
    print("== il passo, a modello caldo ==")
    tts.synthesize("Prova di riscaldamento, una frase qualunque.", voce)

    np.random.seed(1234)
    t0 = time.perf_counter()
    st = tts._stato(TESTO, tts._descrizione(voce))
    ms_prefill = (time.perf_counter() - t0) * 1000.0

    passi, frames = [], []
    t = time.perf_counter()
    for f in tts._codici(st):
        ora = time.perf_counter()
        passi.append((ora - t) * 1000.0)
        t = ora
        frames.append(f)
    p = np.array(passi)
    T = len(frames)
    intero = tts._onda(frames)
    hop = len(intero) / T
    durata_frame = hop / NATIVE_RATE * 1000.0

    print(f"  prefill      : {ms_prefill:.0f} ms")
    print(f"  passo p50    : {np.median(p):.1f} ms   (primo {p[0]:.0f}, media {p.mean():.1f})")
    print(f"  frame        : {durata_frame:.1f} ms di audio")
    print(f"  tempo reale  : {np.median(p) / durata_frame:.2f}x  "
          f"({'sta avanti' if np.median(p) < durata_frame else 'NON sta avanti'})")

    print("\n== rivocodare il prefisso: quanto costa ==")
    print(f"  {'k frame':>8} {'ms':>7} {'ms/frame':>9}")
    costi = {}
    for k in (2, 4, 8, 16, 32, 64, T):
        if k > T:
            break
        t0 = time.perf_counter()
        tts._onda(frames[:k])
        ms = (time.perf_counter() - t0) * 1000.0
        costi[k] = ms
        print(f"  {k:>8} {ms:>7.1f} {ms / k:>9.2f}")

    print("\n== la latenza al primo campione, per dimensione del blocco ==")
    print(f"  {'blocco':>7} {'audio':>8} {'prefill+passi':>14} {'vocoder':>8} {'totale':>8}")
    for blocco in (1, 2, 3, 4, 6, 8):
        passi_ms = float(np.median(p)) * blocco
        voc = costi.get(blocco) or float(np.interp(blocco, list(costi), list(costi.values())))
        tot = ms_prefill + passi_ms + voc
        print(f"  {blocco:>7} {blocco * durata_frame:>7.0f}ms {passi_ms:>13.0f}ms"
              f" {voc:>7.0f}ms {tot:>7.0f}ms")


def prova_pezzi(tts) -> bool:
    """I pezzi rimessi insieme fanno la battuta intera?

    **E' la trasformata contro la propria inversa, applicata allo streaming.**
    `stream()` vocoda prefissi, affetta, ricampiona e consegna; se una sola di
    quelle operazioni sbaglia di qualche campione a ogni giuntura, quello che esce
    e' parlato *plausibile* — leggermente impastato alle giunture, e nessun
    contatore lo dice. Concatenando i blocchi si deve riottenere esattamente cio'
    che `synthesize()` produce sulla stessa battuta con lo stesso seme.

    L'unica differenza ammessa e' in **coda**: `synthesize` toglie il silenzio
    finale, `stream` no (non puo': la coda di un prefisso e' il centro della
    battuta). Si confronta quindi sulla parte comune.

    ## L'identita' bit a bit non e' disponibile, e chiederla e' l'errore

    Il primo criterio scritto qui chiedeva uno scarto sotto 1e-6 e ha risposto
    «diversi» con 8,8e-04. Ma quel numero era gia' noto **prima** di questa prova:
    `--vocoder` aveva misurato che `vocoder(codici[:k])` differisce dall'intero per
    un errore RMS di 3-5e-04. Lo streaming eredita quell'errore per costruzione —
    i blocchi gia' consegnati vengono da prefissi piu' corti — e non c'e' modo di
    toglierlo senza rinunciare allo streaming.

    Quindi la domanda giusta non e' «sono identici» ma **«le giunture aggiungono
    qualcosa?»**. Se affettare, ricampionare e concatenare fossero sbagliati,
    l'errore sarebbe concentrato ai bordi dei blocchi e molto piu' grande di
    quello di fondo. Si misurano tutti e due e si confrontano: e' il controllo che
    distingue "il vocoder e' impreciso" da "il mio codice e' rotto", due cose che
    da un numero solo si somigliano.

    **Cosa smentisce**: errore alle giunture molto sopra quello di fondo, o un
    numero di blocchi pari a uno — che vorrebbe dire che lo streaming non ha
    streamato.
    """
    voce = _voce()
    print("== i pezzi rimessi insieme ==")
    tts.synthesize("Riscaldamento.", voce)

    t0 = time.perf_counter()
    pezzi, tempi = [], []
    for blocco, finita in tts.stream(TESTO, voce):
        tempi.append((time.perf_counter() - t0) * 1000.0)
        pezzi.append(blocco)
        if finita:
            break
    a_pezzi = np.concatenate(pezzi) if pezzi else np.zeros(0, np.float32)
    ms_stream = (time.perf_counter() - t0) * 1000.0

    intero = tts.synthesize(TESTO, voce)
    print(f"  blocchi        : {len(pezzi)}  "
          f"({', '.join(f'{len(p) / tts.samplerate * 1000:.0f}ms' for p in pezzi[:8])}...)")
    print(f"  primo campione : {tempi[0]:.0f} ms   (intero: {intero.total_ms:.0f} ms)")
    print(f"  totale stream  : {ms_stream:.0f} ms")
    print(f"  campioni       : a pezzi {len(a_pezzi)}, intero {len(intero.audio)}")

    n = min(len(a_pezzi), len(intero.audio))
    if n == 0:
        print("  VUOTO.")
        return False
    d = np.abs(a_pezzi[:n] - intero.audio[:n])
    corr, err = _confronta(a_pezzi[:n], intero.audio[:n])
    print(f"  sulla parte comune ({n} campioni): scarto max {d.max():.3e}, "
          f"corr {corr:.6f}, err rms {err:.2e}")

    # L'errore **alle giunture** contro quello di fondo. Se affettare e concatenare
    # fossero sbagliati, il primo sarebbe molto piu' grande del secondo.
    bordi = np.cumsum([len(p) for p in pezzi])[:-1]
    intorno = np.zeros(n, dtype=bool)
    for b in bordi:
        intorno[max(0, b - 64) : min(n, b + 64)] = True
    if intorno.any() and (~intorno).any():
        e_giunture = float(np.sqrt(np.mean(d[intorno] ** 2)))
        e_fondo = float(np.sqrt(np.mean(d[~intorno] ** 2)))
        print(f"  errore alle giunture {e_giunture:.2e} contro fondo {e_fondo:.2e}"
              f"  (rapporto {e_giunture / max(e_fondo, 1e-12):.2f})")
        giunture_ok = e_giunture <= 3.0 * e_fondo
    else:
        giunture_ok = True

    ok = bool(len(pezzi) > 1 and err < 1e-3 and corr > 0.9999 and giunture_ok)
    print("  " + (
        "FEDELE: lo streaming consegna la stessa battuta, e le giunture non"
        " aggiungono niente all'errore del vocoder."
        if ok else "DIVERSI: le giunture non tornano."
    ))
    return ok


def prova_fretta(tts, ripetizioni: int = 3) -> None:
    """Si può chiedere a parole di parlare più in fretta?

    **È l'unica leva che questo motore potrebbe avere.** Qwen non ha un parametro
    di velocità: `rate` gli arriva e lo ignora. Ma la voce non si sceglie da un
    elenco, si **descrive** — e una descrizione è testo libero, quindi «parla
    svelto» ci sta dentro come ci sta «voce roca». Se funziona, il motore torna in
    gioco; se non funziona, è chiuso, perché a valle resta solo WSOLA che è già al
    tetto.

    ## Come si misura una quantità che è una variabile casuale

    Il passo di questo modello varia da 7 a 15 car/s **fra battute diverse**, che
    è più del guadagno che si sta cercando. Confrontare due condizioni su frasi
    diverse non direbbe niente: si misurerebbe quale frase è capitata dove.

    Quindi **le stesse frasi in tutte le condizioni**, e il confronto si fa per
    frase — è la stessa forma del caso nullo che condivide tutto tranne la
    risposta. Le ripetizioni servono all'altra metà della varianza, quella della
    stessa frase con sé stessa (il modello campiona), e si guarda la mediana.

    **Cosa smentisce**: se il passo delle condizioni «svelte» resta dentro la
    banda delle ripetizioni della condizione base, l'istruzione non è una leva —
    il modello la legge come stile e non come tempo, esattamente come i tag
    `<laugh>` che arrivavano al modello e non facevano niente. Scritto prima
    della prova.
    """
    print("== si può chiedere a parole di andare più svelti? ==")
    # **Il seme va tolto, o le ripetizioni non ripetono niente.** Il banco lo fissa
    # (serve alle prove di fedeltà, dove due percorsi devono fare le stesse
    # estrazioni), ma qui la varianza del campionamento **è** la quantità da
    # misurare: con il seme fisso le tre passate darebbero tre volte lo stesso
    # numero e la banda risulterebbe larga zero, cioè qualunque differenza
    # sembrerebbe significativa.
    seme = tts.seed
    tts.seed = None
    tts.synthesize("Riscaldamento.", _voce())

    frasi = [
        "Oggi recuperiamo veicoli acquistati da idioti a tassi d'interesse alti.",
        "Non ho mai avuto un figlio nero, ma se ne avessi uno vorrei che fosse come te.",
        "Quando c'è una cosa da vincere, cazzo, io la voglio vincere.",
    ]
    condizioni = {
        "base": "Un uomo adulto, voce calda e sicura, tono colloquiale.",
        "svelto": "Un uomo adulto, voce calda e sicura, parla svelto.",
        "molto svelto": (
            "Un uomo adulto, voce calda e sicura, parla molto in fretta, "
            "ritmo incalzante, senza pause."
        ),
        "concitato": (
            "Un uomo adulto che parla rapidissimo e con urgenza, come se avesse "
            "poco tempo, sillabe fitte e nessuna pausa."
        ),
    }

    from speak.backends.qwen import VOICES

    originale = dict(VOICES)
    risultati: dict[str, list[float]] = {k: [] for k in condizioni}
    try:
        for nome, descrizione in condizioni.items():
            VOICES["qwen-uomo1"] = (descrizione, "m")
            for frase in frasi:
                n = spoken_length(frase)
                passi = []
                for _ in range(ripetizioni):
                    d = tts.synthesize(frase, _voce()).duration
                    if d > 0.2:
                        passi.append(n / d)
                if passi:
                    risultati[nome].append(float(np.median(passi)))
                    print(f"  {nome:>13}  {np.median(passi):5.2f} car/s"
                          f"   (ripetizioni: {', '.join(f'{p:.1f}' for p in passi)})"
                          f"   {frase[:34]!r}")
            print()
    finally:
        VOICES.clear()
        VOICES.update(originale)
        tts.seed = seme

    base = risultati["base"]
    print(f"  {'condizione':>13} {'passo p50':>10} {'contro base':>12}")
    for nome, v in risultati.items():
        if not v:
            continue
        p50 = float(np.median(v))
        # Il guadagno si calcola **per frase** e poi si mediana, non fra le
        # mediane: le frasi non hanno lo stesso passo e mescolarle rimette dentro
        # proprio la varianza che l'appaiamento serviva a togliere.
        guad = float(np.median([a / b for a, b in zip(v, base)])) if len(v) == len(base) else 1.0
        print(f"  {nome:>13} {p50:>10.2f} {guad:>11.2f}x")
    print("\n  per riferimento: piper fa 18,3 car/s sulla stessa scena;"
          " sotto ~13 il motore non ci sta.")


def main() -> None:
    p = argparse.ArgumentParser(description="Banco di Qwen3-TTS: fedelta' e troncabilita'.")
    p.add_argument("--riferimento", action="store_true",
                   help="confronta il ciclo srotolato con `generate_onnx()`")
    p.add_argument("--vocoder", action="store_true",
                   help="il vocoder si puo' chiamare su un pezzo?")
    p.add_argument("--streaming", action="store_true",
                   help="passo a modello caldo, costo della rivocodifica, latenza prevista")
    p.add_argument("--pezzi", action="store_true",
                   help="i blocchi di stream() concatenati fanno la battuta intera?")
    p.add_argument("--fretta", action="store_true",
                   help="si puo' chiedere a parole di parlare piu' svelto?")
    p.add_argument("--ripetizioni", type=int, default=3,
                   help="quante volte ogni frase per condizione (il modello campiona)")
    p.add_argument("--variante", default="int4")
    p.add_argument("--device", default="auto")
    p.add_argument("--seed", type=int, default=1234)
    args = p.parse_args()

    from speak.backends.qwen import QwenTts

    tts = QwenTts(
        samplerate=24000, variante=args.variante, device=args.device, seed=args.seed
    )
    if not (args.riferimento or args.vocoder or args.streaming or args.pezzi or args.fretta):
        p.error("scegliere almeno una prova fra --riferimento --vocoder --streaming"
                " --pezzi --fretta")
    if args.riferimento:
        prova_riferimento(tts)
    if args.vocoder:
        prova_vocoder(tts)
    if args.streaming:
        prova_streaming(tts)
    if args.pezzi:
        prova_pezzi(tts)
    if args.fretta:
        prova_fretta(tts, ripetizioni=args.ripetizioni)


if __name__ == "__main__":
    main()
