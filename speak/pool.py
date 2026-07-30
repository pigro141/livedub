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
)

# Le basi di ciascun backend: serve a `build_pool` quando non si dichiara nulla,
# e a evitare che una sessione SuperTonic si ritrovi in pool una voce Piper.
FAMIGLIE = {
    "piper": tuple(k for k in NATIVE if k.startswith("it_IT-")),
    "supertonic": tuple(k for k in NATIVE if k.startswith("supertonic-")),
}


def build_pool(
    voices: tuple[str, ...] | None = None, size: int = 6, backend: str = "piper"
) -> list[VoiceSpec]:
    """Costruisce il pool, al piu' `size` voci, usando solo le basi disponibili.

    Senza `voices` si prendono le native del **backend indicato**, non tutte:
    un pool che mescolasse voci Piper e SuperTonic chiederebbe a un motore di
    sintetizzare con lo stile di un altro, e il personaggio a cui tocca la voce
    sbagliata resterebbe muto per tutta la sessione.
    """
    allowed = set(voices) if voices else set(FAMIGLIE.get(backend, FAMIGLIE["piper"]))
    pool: list[VoiceSpec] = []
    for base, semitones, rate in VARIANTS:
        if base not in allowed:
            continue
        gender = NATIVE.get(base, ("?", 22050))[0]
        suffix = "" if semitones == 0 else f"{semitones:+g}".replace(".", "_")
        pool.append(
            VoiceSpec(
                voice_id=f"{base.split('-')[1]}{suffix}",
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
        raise ValueError(f"nessuna voce costruibile da {sorted(allowed)}")
    return pool


def voce_neutra(pool: list[VoiceSpec], backend: str = "piper") -> VoiceSpec:
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
    basi = set(FAMIGLIE.get(backend, FAMIGLIE["piper"]))
    for base, semitones, rate in VARIANTS:
        if base not in basi:
            continue
        suffix = "" if semitones == 0 else f"{semitones:+g}".replace(".", "_")
        vid = f"{base.split('-')[1]}{suffix}"
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

        Quindi: prima una voce libera dello stesso sesso, poi una libera
        qualunque, poi si ricicla. Con `?` — intonazione dentro la fascia in cui
        un uomo chiaro e una donna scura non si distinguono — si torna
        all'ordine del pool, che e' la scelta giusta quando davvero non si sa.
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
