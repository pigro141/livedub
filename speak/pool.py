"""Il pool di voci e la loro assegnazione ai personaggi.

Il problema che risolve: i sottotitoli non dicono chi parla, quindi i
personaggi si scoprono uno alla volta, in ordine di apparizione, e ognuno deve
ricevere una voce **subito** e **tenerla** per tutta la sessione. Un personaggio
che cambia voce a meta' scena e' peggio di un personaggio con la voce sbagliata:
il secondo e' una scelta discutibile, il primo e' un errore evidente.

Il vincolo duro di Piper e' che le voci italiane sono **due**: `paola` e
`riccardo` — verificato sull'indice ufficiale, non e' una svista di
configurazione. Con due voci non si doppia una banda di rapinatori. Il pool si
allarga quindi per trasformazione: spostando l'intonazione di qualche semitono e
cambiando un po' la velocita' si ottengono varianti che l'orecchio separa senza
fatica, perche' in una conversazione conta il *contrasto* fra le voci piu' della
loro identita' assoluta.

Con SuperTonic il vincolo cade: **dieci voci native**, cinque maschili e cinque
femminili, quindi nessuna variante finche' i personaggi non superano la decina.
Una voce nativa e' sempre meglio di una trasformata, e le trasformazioni restano
disponibili solo come riserva.

Con Kokoro il vincolo **torna**, identico a quello di Piper: le voci italiane
sono due, `if_sara` e `im_nicola` — il modello ne ha cinquantaquattro, ma le
altre parlano altre lingue. Quindi anche qui il pool si riallarga per
trasformazione, con la stessa tabella di scostamenti di Piper. E' il motivo per
cui un motore con voci migliori non da' automaticamente una scena migliore:
oltre il secondo personaggio si torna comunque a spostare i semitoni.

L'ordine di assegnazione non e' casuale: prima le native, poi gli scostamenti
piccoli, poi quelli grandi. Cosi' una scena con due soli personaggi usa le voci
migliori, e le varianti entrano solo quando servono davvero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.types import VoiceSpec

# Le voci native, con la loro frequenza di uscita e il genere.
NATIVE = {
    "it_IT-paola-medium": ("f", 22050),
    "it_IT-riccardo-x_low": ("m", 16000),
    "supertonic-M1": ("m", 44100),
    "supertonic-M2": ("m", 44100),
    "supertonic-M3": ("m", 44100),
    "supertonic-M4": ("m", 44100),
    "supertonic-M5": ("m", 44100),
    "supertonic-F1": ("f", 44100),
    "supertonic-F2": ("f", 44100),
    "supertonic-F3": ("f", 44100),
    "supertonic-F4": ("f", 44100),
    "supertonic-F5": ("f", 44100),
    "kokoro-nicola": ("m", 24000),
    "kokoro-sara": ("f", 24000),
    # Le inglesi di Kokoro, che servono quando si traduce verso l'inglese. Sei
    # native invece di due: **e' l'unico caso in cui il pool non ha bisogno di
    # spostare i semitoni** per distinguere sei personaggi.
    "kokoro-heart": ("f", 24000),
    "kokoro-bella": ("f", 24000),
    "kokoro-michael": ("m", 24000),
    "kokoro-fenrir": ("m", 24000),
    "kokoro-emma": ("f", 24000),
    "kokoro-george": ("m", 24000),
}

# Varianti, in ordine di assegnazione: prima le native, poi gli scostamenti
# piccoli, poi quelli grandi. (voce_base, semitoni, velocita')
#
# Le due famiglie stanno nella stessa tabella e non si mescolano mai, perche'
# `build_pool` filtra per `voices` e in una sessione il backend e' uno solo.
# L'alternanza maschile/femminile e' voluta: due personaggi consecutivi si
# distinguono molto di piu' se cambia il genere che se cambia il timbro.
VARIANTS: tuple[tuple[str, float, float], ...] = (
    ("it_IT-riccardo-x_low", 0.0, 1.00),  # maschile nativa
    ("it_IT-paola-medium", 0.0, 1.00),  # femminile nativa
    ("it_IT-riccardo-x_low", -2.5, 0.96),  # maschile piu' grave e lenta
    ("it_IT-paola-medium", +2.0, 1.05),  # femminile piu' acuta e svelta
    ("it_IT-riccardo-x_low", +2.5, 1.03),  # maschile piu' chiara
    ("it_IT-paola-medium", -2.5, 0.97),  # femminile piu' scura
    ("it_IT-riccardo-x_low", -4.0, 1.00),  # maschile molto grave
    ("it_IT-paola-medium", +4.0, 1.00),  # femminile molto acuta
    # SuperTonic: dieci native, nessuna trasformazione. Una voce vera batte
    # sempre una spostata di semitoni, quindi le varianti qui non servono.
    ("supertonic-M1", 0.0, 1.00),
    ("supertonic-F1", 0.0, 1.00),
    ("supertonic-M2", 0.0, 1.00),
    ("supertonic-F2", 0.0, 1.00),
    ("supertonic-M3", 0.0, 1.00),
    ("supertonic-F3", 0.0, 1.00),
    ("supertonic-M4", 0.0, 1.00),
    ("supertonic-F4", 0.0, 1.00),
    ("supertonic-M5", 0.0, 1.00),
    ("supertonic-F5", 0.0, 1.00),
    # Kokoro: due native, come Piper, quindi gli stessi scostamenti. Sono otto
    # e non sette di proposito: con `pool_size = 6` ne restano due libere,
    # quindi `voce_neutra` prende la settima e **non** cade nel ramo di ripiego
    # — quello in cui la voce d'attesa somiglia a quella di un personaggio. Il
    # margine di una serve perche' `pool_size` e' un campo di config, e prima o
    # poi qualcuno lo mettera' a 7.
    # Le inglesi prima, e **senza trasformazioni**: sei voci native alternate
    # maschile/femminile bastano da sole, e un semitono spostato su una voce
    # nativa e' sempre un peggioramento quando se ne puo' fare a meno.
    ("kokoro-michael", 0.0, 1.00),
    ("kokoro-heart", 0.0, 1.00),
    ("kokoro-fenrir", 0.0, 1.00),
    ("kokoro-bella", 0.0, 1.00),
    ("kokoro-george", 0.0, 1.00),
    ("kokoro-emma", 0.0, 1.00),
    ("kokoro-nicola", 0.0, 1.00),  # maschile nativa
    ("kokoro-sara", 0.0, 1.00),  # femminile nativa
    ("kokoro-nicola", -2.5, 0.96),  # maschile piu' grave e lenta
    ("kokoro-sara", +2.0, 1.05),  # femminile piu' acuta e svelta
    ("kokoro-nicola", +2.5, 1.03),  # maschile piu' chiara
    ("kokoro-sara", -2.5, 0.97),  # femminile piu' scura
    ("kokoro-nicola", -4.0, 1.00),  # maschile molto grave
    ("kokoro-sara", +4.0, 1.00),  # femminile molto acuta
)

# Le basi di ciascun backend **in italiano**: serve a `build_pool` quando non si
# dichiara nulla, e a evitare che una sessione SuperTonic si ritrovi in pool una
# voce Piper. Per le altre lingue si passa da `basi_per`, che va a leggere il
# catalogo del motore.
FAMIGLIE = {
    "piper": tuple(k for k in NATIVE if k.startswith("it_IT-")),
    "supertonic": tuple(k for k in NATIVE if k.startswith("supertonic-")),
    "kokoro": tuple(k for k in NATIVE if k.startswith("kokoro-")),
}

# Gli scostamenti con cui si allarga un pool che ha poche voci native, per le
# lingue **non dichiarate** in `VARIANTS`. Prima tutte le native (una voce vera
# batte sempre una spostata di semitoni), poi la scala.
#
# E' la stessa scala delle due italiane di Piper, semplificata: li' maschile e
# femminile hanno scostamenti diversi perche' sono stati tarati a orecchio su
# quelle due voci, e a orecchio su una lingua che nessuno ascolta non si tara
# niente. Quindi qui la stessa scala per tutte, dichiarata come tale.
SCOSTAMENTI: tuple[tuple[float, float], ...] = (
    (0.0, 1.00),
    (-2.5, 0.96),
    (+2.5, 1.03),
    (-4.0, 1.00),
    (+4.0, 1.00),
)

# **Per quali lingue esiste una voce, motore per motore.** Il nome di una voce
# non dice la lingua — `supertonic-M1` potrebbe parlare qualunque cosa — quindi
# questa e' una dichiarazione e non una deduzione.
#
# Serve perche' tradurre verso una lingua per cui il motore montato non ha voci
# non da' errore: `build_pool` ripiega sulla famiglia del backend e la battuta
# esce **con una voce italiana che pronuncia il giapponese**, cioe' un modello
# fonemizzato con le regole sbagliate. E' la stessa forma del ripiego silenzioso
# gia' pagata con `preload_dlls()`: nessun contatore lo mostra, l'audio esce, la
# suite e' verde.
#
# **Nessun elenco di lingue sta qui.** Ognuno dei tre motori ha il suo catalogo,
# e sono diversi per costruzione: Piper monta un modello per lingua (51),
# SuperTonic e' un modello multilingue con dieci stili (31), Kokoro ha le lingue
# scritte nel nome delle sue voci (9). Copiarli qui sarebbe il secondo posto che
# dice la stessa cosa — la forma «una tabella scritta due volte, e la seconda non
# l'aggiorna nessuno» che questo progetto ha gia' pagato sette volte.
#
# Fino a ieri qui c'era invece scritto `piper: ("it",)` e `supertonic: ("it",)`,
# ed era **falso in entrambi i casi**: non un limite dei motori, un limite di
# questo file. Si traduceva in spagnolo e poi lo leggeva una voce italiana, senza
# nessun errore.
CATALOGHI: dict[str, str] = {
    "piper": "speak.backends.piper_voci",
    "supertonic": "speak.backends.supertonic",
    "kokoro": "speak.backends.kokoro",
}

# I motori che non pronunciano parole: un bip e il silenzio non hanno lingua, e
# avvisare che «non c'e' una voce giapponese» per un bip sarebbe rumore.
SENZA_LINGUA: tuple[str, ...] = ("tone", "silent", "none", "")


def famiglia_lingua(lingua: str) -> str:
    """`pt-BR`, `zh_CN`, `IT` -> il codice a due lettere con cui si indicizza.

    `zh-CN` e `pt-BR` sono varianti di una lingua che i cataloghi trattano
    intera, ed e' la stessa riga che `build_pool` usa per scegliere la famiglia.
    """
    return (lingua or "it").replace("_", "-").split("-")[0].lower()


def lingue_con_voce(backend: str) -> tuple[str, ...]:
    """Le lingue per cui `backend` ha almeno una voce nativa.

    Vuoto vuol dire «non si sa», non «nessuna»: un motore che questo modulo non
    conosce non deve far comparire un avviso inventato.

    **Si legge il catalogo del motore, non un elenco locale.** Il prezzo e' un
    import per motore, e si paga volentieri: nessuno di questi tre moduli tira
    dentro il pacchetto del motore al livello del modulo, quindi la domanda «che
    lingue parla?» si risponde senza avere il motore installato.
    """
    nome = (backend or "").strip().lower()
    modulo = CATALOGHI.get(nome)
    if modulo is None:
        return ()
    import importlib

    m = importlib.import_module(modulo)
    if nome == "supertonic":
        return tuple(m.LINGUE)
    if nome == "kokoro":
        return tuple(m.PER_LINGUA)
    return tuple(m.LINGUE)


def basi_per(backend: str, lingua: str = "it") -> tuple[str, ...]:
    """Le voci native di quel motore **in quella lingua**.

    E' la funzione che sceglie *quali* voci esistono; `build_pool` decide poi
    quante e con che trasformazioni. Sta separata perche' la usa anche il
    precaricamento (`speak.base._famiglia`): scaldare le voci italiane per poi
    parlare inglese vorrebbe dire pagare il caricamento due volte.

    **Dove c'e' una famiglia dichiarata, vince quella.** L'italiano di tutti e
    tre i motori e l'inglese di Kokoro sono le uniche combinazioni che qualcuno
    abbia ascoltato e su cui sono state fatte tutte le misure del progetto: il
    catalogo non le tocca, se no ogni numero di `CLAUDE.md` si riferirebbe a un
    pool diverso da quello che gira.
    """
    nome = (backend or "").strip().lower()
    fam = famiglia_lingua(lingua)
    if nome == "kokoro":
        # Kokoro passa **sempre** da `PER_LINGUA`, anche in italiano: la sua
        # famiglia in `FAMIGLIE` contiene le italiane e le inglesi insieme — sono
        # le otto dichiarate in `NATIVE` — e prenderla per l'italiano darebbe un
        # pool inglese con l'aria di essere quello di sempre.
        from speak.backends.kokoro import PER_LINGUA

        return PER_LINGUA.get(fam, ())
    if fam == "it" and nome in FAMIGLIE:
        return FAMIGLIE[nome]
    if nome == "supertonic":
        from speak.backends.supertonic import LINGUE

        # Dieci stili di parlante che valgono per tutte e trentuno le lingue:
        # la lingua non cambia le voci, cambia la fonemizzazione.
        return FAMIGLIE["supertonic"] if fam in LINGUE else ()
    if nome == "piper":
        from speak.backends.piper_voci import voci_per

        return voci_per(fam, 6)
    return FAMIGLIE.get(nome, ())


def ha_voce(backend: str, lingua: str) -> bool:
    """C'e' una voce di `backend` che parla `lingua`?

    Col dubbio si risponde di si', come per `Copertura.sa_fare`: un avviso su una
    cosa che funziona fa smettere di leggere gli avvisi veri.
    """
    nome = (backend or "").strip().lower()
    if nome in SENZA_LINGUA:
        return True
    note = lingue_con_voce(nome)
    if not note:
        return True
    return famiglia_lingua(lingua) in note


def nome_corto(base: str) -> str:
    """Il `voice_id` che si legge nei rapporti: `it_IT-paola-medium` -> `paola`.

    **L'indice del parlante ci resta attaccato**, e non e' un dettaglio: i
    novecentoquattro parlanti di `en_US-libritts-high` sono lo stesso modello, e
    senza l'indice due voci diverse avrebbero lo stesso nome — cioe' il pool
    crederebbe di averne data una sola e `assegnata()` risponderebbe di un'altra.
    """
    chiave, _, indice = base.partition("#")
    pezzi = chiave.split("-")
    corto = pezzi[1] if len(pezzi) > 1 else chiave
    return f"{corto}{indice}" if indice else corto


def genere(base: str) -> str:
    """`m`, `f`, o `?` quando il catalogo non lo dice.

    **`?` non e' pigrizia, e' quello che si sa.** Kokoro scrive il sesso nella
    seconda lettera del nome della voce e SuperTonic nei suoi (`M1`..`F5`);
    l'indice di Piper **non ha il campo**, quindi fuori dall'italiano — dove le
    due voci sono dichiarate a mano — resta `?` e il pool ripiega sull'ordine
    invece di alternare maschile e femminile. E' un peggioramento dichiarato:
    l'alternanza e' il motivo per cui due personaggi consecutivi si distinguono.
    """
    dichiarato = NATIVE.get(base)
    if dichiarato is not None:
        return dichiarato[0]
    for modulo in ("speak.backends.kokoro", "speak.backends.supertonic"):
        import importlib

        voci = getattr(importlib.import_module(modulo), "VOICES", {})
        if base in voci:
            return voci[base][1]
    return "?"


def conosciuta(base: str) -> bool:
    """Questa voce esiste in uno dei tre cataloghi?

    Serve perche' `--set tts.voices=<refuso>` deve dare un errore all'avvio e non
    un pool costruito su una voce che nessun motore sapra' aprire: sarebbe una
    sessione che muore alla prima battuta con la configurazione stampata verde.
    """
    if base in NATIVE:
        return True
    import importlib

    for modulo in ("speak.backends.kokoro", "speak.backends.supertonic"):
        if base in getattr(importlib.import_module(modulo), "VOICES", {}):
            return True
    from speak.backends.piper_voci import VOCI, normale

    chiave = base.split("#")[0]
    return chiave in VOCI.get(normale(chiave.split("_")[0]), ())


def varianti_per(basi: tuple[str, ...]) -> list[tuple[str, float, float]]:
    """Le varianti da mettere in pool per queste basi, in ordine di assegnazione.

    Dove `VARIANTS` le dichiara si usano quelle — sono le combinazioni tarate a
    orecchio, e cambiarle cambierebbe ogni misura scritta in `CLAUDE.md`. Per le
    basi che nessuno ha ascoltato si generano con `SCOSTAMENTI`, che e' la stessa
    forma: prima tutte le native, poi la scala.
    """
    ignote = [b for b in basi if not conosciuta(b)]
    if ignote:
        raise ValueError(f"voci sconosciute a tutti i cataloghi: {sorted(ignote)}")
    dichiarate = [v for v in VARIANTS if v[0] in basi]
    coperte = {v[0] for v in dichiarate}
    resto = [b for b in basi if b not in coperte]
    generate = [
        (b, semitoni, velocita)
        for semitoni, velocita in SCOSTAMENTI
        for b in resto
    ]
    return dichiarate + generate


def build_pool(
    voices: tuple[str, ...] | None = None,
    size: int = 6,
    backend: str = "piper",
    lingua: str = "it",
) -> list[VoiceSpec]:
    """Costruisce il pool, al piu' `size` voci, usando solo le basi disponibili.

    Senza `voices` si prendono le native del **backend indicato**, non tutte:
    un pool che mescolasse voci Piper e SuperTonic chiederebbe a un motore di
    sintetizzare con lo stile di un altro, e il personaggio a cui tocca la voce
    sbagliata resterebbe muto per tutta la sessione.

    **E nemmeno voci di lingue diverse.** Se si traduce, la lingua che conta e'
    quella di *arrivo*: dare a un personaggio una voce italiana per dire una
    battuta inglese non e' un difetto di accento, e' un modello fonemizzato con
    le regole sbagliate. Oggi solo Kokoro ha voci in piu' lingue; per gli altri
    `lingua` non cambia niente.
    """
    basi = tuple(voices) if voices else basi_per(backend, lingua)
    if not basi:
        basi = FAMIGLIE.get(backend, FAMIGLIE["piper"])
    pool: list[VoiceSpec] = []
    for base, semitones, rate in varianti_per(basi):
        gender = genere(base)
        suffix = "" if semitones == 0 else f"{semitones:+g}".replace(".", "_")
        pool.append(
            VoiceSpec(
                voice_id=f"{nome_corto(base)}{suffix}",
                backend=backend,
                base_voice=base,
                semitones=semitones,
                rate=rate,
                gender=gender,
            )
        )
        if len(pool) >= size:
            break
    if not pool:
        raise ValueError(f"nessuna voce costruibile da {sorted(basi)}")
    return pool


def voce_neutra(pool: list[VoiceSpec], backend: str = "piper",
                lingua: str = "it") -> VoiceSpec:
    """La voce con cui si parla mentre non si sa ancora chi sia.

    **Sta fuori dal pool assegnabile, ed e' il punto.** Se fosse una voce del
    pool, prima o poi diventerebbe la voce definitiva di qualcuno, e chi ascolta
    sentirebbe la voce «di attesa» trasformarsi in un personaggio: due cose
    diverse dette con lo stesso timbro. Fuori dal pool e' invece un segnale
    coerente — *questo non si sa ancora chi sia* — e nessuno se la tiene.

    Si prende la prima variante della famiglia che il pool ha lasciato libera:
    e' gia' ordinata per contrasto, quindi la prima scartata e' anche la piu'
    diversa da quelle in uso. Se la famiglia e' esaurita si ripiega sulla prima
    voce del pool abbassata di un semitono — un compromesso, e va detto: li' la
    voce di attesa somiglia a quella di un personaggio.

    Una battuta o due, poi si assegna comunque: si veda
    `SpeakerConfig.gender_defer_max_lines`.
    """
    prese = {v.voice_id for v in pool}
    # **La lingua conta anche qui**, e dimenticarlo sarebbe il difetto peggiore
    # della lista: la voce d'attesa e' quella che parla mentre non si sa chi sia,
    # cioe' la prima che si sente. Presa dalla famiglia italiana mentre la scena
    # e' in spagnolo, sarebbe l'unica battuta di ogni personaggio nuovo detta con
    # i fonemi sbagliati.
    basi = basi_per(backend, lingua) or FAMIGLIE.get(backend, FAMIGLIE["piper"])
    for base, semitones, rate in varianti_per(basi):
        suffix = "" if semitones == 0 else f"{semitones:+g}".replace(".", "_")
        vid = f"{nome_corto(base)}{suffix}"
        if vid in prese:
            continue
        return VoiceSpec(
            voice_id="neutra",
            backend=backend,
            base_voice=base,
            semitones=semitones,
            rate=rate,
            gender="?",
        )
    prima = pool[0]
    return VoiceSpec(
        voice_id="neutra",
        backend=backend,
        base_voice=prima.base_voice,
        semitones=prima.semitones - 1.0,
        rate=prima.rate,
        gender="?",
    )


def voce_per(
    pool: "VoicePool",
    speaker_id: str,
    personaggio,
    t: float = 0.0,
    *,
    neutra: VoiceSpec,
    defer_max: int = 3,
    ripiego: str = "m",
    anonima: bool = False,
) -> VoiceSpec:
    """La voce di questa battuta, rinviando l'assegnazione se il sesso non si sa.

    **Una voce data e' data per sempre**, quindi darla al primo respiro
    significa deciderla sull'intonazione di uno o due ritagli — e su questo audio
    l'intonazione di un ritaglio solo puo' essere quella della musica. Misurato:
    il personaggio con quindici battute della scena del concessionario, un uomo,
    riceveva `paola` e la teneva fino alla fine.

    Finche' il genere non si sa si parla con la voce neutra, che non e' del pool
    e nessuno terra'. Ma non all'infinito: dopo `defer_max` battute si assegna
    comunque, col `ripiego`. Restare in eterno sulla neutra vorrebbe dire tutti
    con la stessa voce, cioe' il difetto di partenza.

    **Il ripiego e' maschile, e non e' un pregiudizio: e' la forma della misura.**
    L'intonazione presa sul mix del gioco e' spostata verso l'alto dal fondo, e
    la taratura che ne esce sa dire "uomo" molto meglio di quanto sappia dire
    "donna" (`listen/speaker.py`). Con un ripiego alternato — l'ordine del pool,
    che alterna apposta per fare contrasto — il personaggio incerto prende una
    voce femminile una volta su due, e su questo materiale "incerto" vuol dire
    quasi sempre un uomo. Una voce femminile si da' solo quando la misura la
    dichiara, e in cambio una donna in scena rischia una voce maschile: si cambia
    con `speaker.gender_fallback` quando la scena lo richiede.

    Sta qui e non nella pipeline perche' il banco deve poter rigiocare **questa**
    politica: una taratura provata su una politica diversa da quella che gira
    misurerebbe un doppiaggio che non esiste.
    """
    if anonima:
        # Il tracker non ha fatto un nome. Dare comunque una voce del pool
        # significherebbe assegnarla a un'identita' che non si e' riconosciuta —
        # e quella voce resterebbe presa. La neutra dice la stessa cosa senza
        # consumare niente e senza mentire su chi sta parlando.
        return neutra
    if personaggio is None or pool.known(speaker_id):
        genere = getattr(personaggio, "gender", "?") if personaggio is not None else "?"
        return pool.voice_for(speaker_id, t, gender=genere)
    genere = personaggio.gender
    if genere == "?":
        if personaggio.battute < max(1, defer_max):
            return neutra
        genere = ripiego  # non si puo' piu' aspettare
    return pool.voice_for(speaker_id, t, gender=genere)


@dataclass
class VoiceAssignment:
    """Chi ha quale voce, e da quando."""

    speaker_id: str
    voice: VoiceSpec
    first_seen: float
    lines: int = 0


class VoicePool:
    """Assegna una voce a ogni personaggio nuovo e non gliela toglie piu'.

    Quando le voci finiscono si ricomincia dal fondo del pool: due personaggi
    finiscono con la stessa voce. E' brutto, ma e' meno brutto delle
    alternative — lasciare muto un personaggio, o rimescolare le assegnazioni
    gia' fatte e cambiare voce a chi ce l'aveva.
    """

    def __init__(self, voices: list[VoiceSpec] | None = None) -> None:
        self.voices = list(voices) if voices else build_pool()
        self._by_speaker: dict[str, VoiceAssignment] = {}
        self._alias: dict[str, str] = {}  # identita' assorbita -> identita' viva
        self._next = 0
        self.collisions = 0

    def __len__(self) -> int:
        return len(self._by_speaker)

    @property
    def assignments(self) -> list[VoiceAssignment]:
        return sorted(self._by_speaker.values(), key=lambda a: a.first_seen)

    def voice_for(self, speaker_id: str, t: float = 0.0, gender: str = "?") -> VoiceSpec:
        """Voce del personaggio, assegnandogliene una se e' la prima volta.

        **`gender` non e' una raffinatezza, e l'ascolto lo ha dimostrato.**
        L'ordine del pool alterna maschile e femminile di proposito: due
        personaggi consecutivi si distinguono molto di piu' se cambia il sesso
        della voce. Ma quell'alternanza presuppone di non sapere niente su chi
        parla, e appena si sa qualcosa diventa il difetto peggiore della lista.

        Misurato all'ascolto su una scena con tre uomini: il secondo personaggio
        confermato prendeva `paola`, e quando il tracker spezzava un personaggio
        in due identita' lo stesso uomo alternava una voce femminile e una
        maschile a seconda di come parlava. Un uomo con la voce di un altro uomo
        e' una scelta discutibile; un uomo che diventa donna a frase alterne e'
        un errore che chiude l'ascolto.

        Quindi: prima una voce libera dello stesso sesso, poi **una gia' presa
        dello stesso sesso**, e solo se il pool non ne ha proprio di quel sesso
        si ripiega sull'ordine. Con `?` — intonazione dentro la fascia in cui un
        uomo chiaro e una donna scura non si distinguono — si torna all'ordine
        del pool, che e' la scelta giusta quando davvero non si sa.

        **L'ordine di quelle due preferenze era invertito, e si e' sentito.**
        Prima si prendeva una voce *libera qualunque* prima di riciclarne una del
        sesso giusto. Dal vivo, scena con tre uomini e pool da sei (tre maschili
        e tre femminili, che si alternano): i tre personaggi prendono M1, M2 e
        M3, poi un frammento di Simeon chiede una voce maschile, non ne trova di
        libere e si porta a casa **F1**. `speaker.gender_fallback` diceva `m` e
        veniva rispettato — nella richiesta, non nella consegna.
        `'Oggi non c'e nulla, solo una moto.'` detta da una donna, in mezzo a
        battute dello stesso personaggio dette da un uomo.

        Riciclare vuol dire due personaggi con la stessa voce, ed e' un prezzo
        vero. Ma e' il prezzo che questo modulo ha gia' dichiarato di voler
        pagare due paragrafi piu' su: un uomo con la voce di un altro uomo e' una
        scelta discutibile, un uomo che diventa donna e' un errore che chiude
        l'ascolto.
        """
        speaker_id = self.risolvi(speaker_id)
        existing = self._by_speaker.get(speaker_id)
        if existing is not None:
            existing.lines += 1
            return existing.voice

        prese = {a.voice.voice_id for a in self._by_speaker.values()}
        libere = [v for v in self.voices if v.voice_id not in prese]
        scelta = None
        if gender in ("m", "f"):
            scelta = next((v for v in libere if v.gender == gender), None)
            if scelta is None:
                # **Si ricicla dentro il sesso giusto invece di uscirne.** Fra le
                # gia' prese si sceglie quella del personaggio che ha parlato
                # meno: la collisione cade su chi l'orecchio ha sentito meno, e
                # due personaggi affermati non diventano lo stesso.
                candidate = [v for v in self.voices if v.gender == gender]
                if candidate:
                    battute = {a.voice.voice_id: a.lines for a in self._by_speaker.values()}
                    scelta = min(candidate, key=lambda v: (battute.get(v.voice_id, 0),
                                                           self.voices.index(v)))
                    self.collisions += 1
        if scelta is None:
            scelta = libere[0] if libere else None
        if scelta is not None:
            voice = scelta
            self._next = max(self._next, self.voices.index(scelta) + 1)
        else:
            self.collisions += 1
            voice = self.voices[self._next % len(self.voices)]
            self._next += 1
        self._by_speaker[speaker_id] = VoiceAssignment(
            speaker_id=speaker_id, voice=voice, first_seen=t, lines=1
        )
        return voice

    def fissa(self, speaker_id: str, voice_id: str, t: float = 0.0) -> VoiceSpec | None:
        """Dichiara che questo personaggio ha **questa** voce, e basta.

        Serve a due cose, tutte e due possibili solo quando il nome arriva dal
        gioco (`vision/label.py`): la mappa scritta a mano in `label.voices`, e il
        ricordo delle sessioni precedenti (`label.cast_file`).

        **Senza, la voce non e' del personaggio: e' del turno.** L'assegnazione
        automatica da' le voci nell'ordine in cui i personaggi parlano, quindi chi
        apre la scena prende la prima del pool. Riaprendo il gioco da un altro
        punto, lo stesso personaggio ne prende un'altra. Con un nome stabile quel
        difetto si puo' togliere del tutto — ed e' il motivo per cui vale la pena
        leggere i nomi anche al di la' del mezzo secondo di latenza.

        Restituisce la voce fissata, o `None` se quel `voice_id` non sta nel pool
        — perche' un nome di voce sbagliato in configurazione dev'essere visibile,
        non silenziosamente ignorato.
        """
        speaker_id = self.risolvi(speaker_id)
        voce = next((v for v in self.voices if v.voice_id == voice_id), None)
        if voce is None:
            return None
        gia = self._by_speaker.get(speaker_id)
        self._by_speaker[speaker_id] = VoiceAssignment(
            speaker_id=speaker_id,
            voice=voce,
            first_seen=gia.first_seen if gia else t,
            lines=gia.lines if gia else 0,
        )
        return voce

    def known(self, speaker_id: str) -> bool:
        return self.risolvi(speaker_id) in self._by_speaker

    def assegnata(self, speaker_id: str) -> VoiceSpec | None:
        """La voce di questo personaggio, **senza dargliene una** se non ce l'ha.

        `voice_for` assegna: chiamarla per sapere e basta creerebbe la cosa che
        si voleva osservare, e il banco conterebbe voci che nessuno ha sentito."""
        a = self._by_speaker.get(self.risolvi(speaker_id))
        return a.voice if a is not None else None

    def risolvi(self, speaker_id: str) -> str:
        """L'identita' viva dietro un id, seguendo le fusioni fino in fondo."""
        visti = set()
        while speaker_id in self._alias and speaker_id not in visti:
            visti.add(speaker_id)
            speaker_id = self._alias[speaker_id]
        return speaker_id

    def merge(self, perdente: str, vincitore: str) -> None:
        """Due identita' erano la stessa persona: una voce sola, la sua.

        **Quale voce sopravvive non e' una scelta di questo oggetto**: arriva
        gia' decisa dal tracker, che sa chi ha piu' battute. Qui si esegue, e si
        esegue in modo che il vincitore **non cambi voce mai** — e' il punto
        dell'operazione. Chi ha parlato di piu' continua come prima; chi era un
        frammento lo raggiunge.

        La voce del perdente non si spreca: `libere` si calcola dalle
        assegnazioni vive, quindi cancellarla la rimette in circolo per il
        prossimo personaggio. In una scena con sedici identita' e sei voci
        questo e' l'unico motivo per cui ne resta ancora una da dare.
        """
        perdente, vincitore = self.risolvi(perdente), self.risolvi(vincitore)
        if perdente == vincitore:
            return
        vecchia = self._by_speaker.pop(perdente, None)
        self._alias[perdente] = vincitore
        viva = self._by_speaker.get(vincitore)
        if viva is None and vecchia is not None:
            # Il vincitore non ha ancora parlato: gli si passa la voce del
            # perdente invece di prenderne una nuova. Quella voce e' gia' stata
            # sentita, e toglierla sarebbe il cambio che si vuole evitare.
            self._by_speaker[vincitore] = VoiceAssignment(
                speaker_id=vincitore,
                voice=vecchia.voice,
                first_seen=vecchia.first_seen,
                lines=vecchia.lines,
            )
        elif viva is not None and vecchia is not None:
            viva.lines += vecchia.lines
            viva.first_seen = min(viva.first_seen, vecchia.first_seen)

    def reset(self) -> None:
        self._by_speaker.clear()
        self._alias.clear()
        self._next = 0
        self.collisions = 0

    def report(self) -> str:
        if not self._by_speaker:
            return "(nessun personaggio ancora sentito)"
        rows = [
            f"  {a.speaker_id:>4}  {a.voice.voice_id:<16} "
            f"{a.voice.base_voice:<22} {a.voice.semitones:+5.1f} st  {a.lines:>3} battute"
            for a in self.assignments
        ]
        return "\n".join(rows)
