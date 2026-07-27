"""Il pool di voci e la loro assegnazione ai personaggi.

Il problema che risolve: i sottotitoli non dicono chi parla, quindi i
personaggi si scoprono uno alla volta, in ordine di apparizione, e ognuno deve
ricevere una voce **subito** e **tenerla** per tutta la sessione. Un personaggio
che cambia voce a meta' scena e' peggio di un personaggio con la voce sbagliata:
il secondo e' una scelta discutibile, il primo e' un errore evidente.

Il vincolo duro e' che le voci italiane di Piper sono **due**: `paola` e
`riccardo`. Con due voci non si doppia una banda di rapinatori. Il pool si
allarga quindi per trasformazione — spostando l'intonazione di qualche semitono
e cambiando un po' la velocita' si ottengono varianti che l'orecchio separa
senza fatica, perche' in una conversazione conta il *contrasto* fra le voci piu'
della loro identita' assoluta.

L'ordine di assegnazione non e' casuale: le varianti piu' distanti dal timbro di
partenza vengono date per ultime. Cosi' una scena con due soli personaggi usa le
due voci native, che sono le migliori, e le varianti entrano solo quando servono
davvero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.types import VoiceSpec

# Le due voci native, con la loro frequenza di uscita e il genere.
NATIVE = {
    "it_IT-paola-medium": ("f", 22050),
    "it_IT-riccardo-x_low": ("m", 16000),
}

# Varianti, in ordine di assegnazione: prima le native, poi gli scostamenti
# piccoli, poi quelli grandi. (voce_base, semitoni, velocita')
VARIANTS: tuple[tuple[str, float, float], ...] = (
    ("it_IT-riccardo-x_low", 0.0, 1.00),  # maschile nativa
    ("it_IT-paola-medium", 0.0, 1.00),  # femminile nativa
    ("it_IT-riccardo-x_low", -2.5, 0.96),  # maschile piu' grave e lenta
    ("it_IT-paola-medium", +2.0, 1.05),  # femminile piu' acuta e svelta
    ("it_IT-riccardo-x_low", +2.5, 1.03),  # maschile piu' chiara
    ("it_IT-paola-medium", -2.5, 0.97),  # femminile piu' scura
    ("it_IT-riccardo-x_low", -4.0, 1.00),  # maschile molto grave
    ("it_IT-paola-medium", +4.0, 1.00),  # femminile molto acuta
)


def build_pool(voices: tuple[str, ...] | None = None, size: int = 6) -> list[VoiceSpec]:
    """Costruisce il pool, al piu' `size` voci, usando solo le basi disponibili."""
    allowed = set(voices) if voices else set(NATIVE)
    pool: list[VoiceSpec] = []
    for base, semitones, rate in VARIANTS:
        if base not in allowed:
            continue
        gender = NATIVE.get(base, ("?", 22050))[0]
        suffix = "" if semitones == 0 else f"{semitones:+g}".replace(".", "_")
        pool.append(
            VoiceSpec(
                voice_id=f"{base.split('-')[1]}{suffix}",
                backend="piper",
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
        self._next = 0
        self.collisions = 0

    def __len__(self) -> int:
        return len(self._by_speaker)

    @property
    def assignments(self) -> list[VoiceAssignment]:
        return sorted(self._by_speaker.values(), key=lambda a: a.first_seen)

    def voice_for(self, speaker_id: str, t: float = 0.0) -> VoiceSpec:
        """Voce del personaggio, assegnandogliene una se e' la prima volta."""
        existing = self._by_speaker.get(speaker_id)
        if existing is not None:
            existing.lines += 1
            return existing.voice

        if self._next >= len(self.voices):
            self.collisions += 1
        voice = self.voices[self._next % len(self.voices)]
        self._next += 1
        self._by_speaker[speaker_id] = VoiceAssignment(
            speaker_id=speaker_id, voice=voice, first_seen=t, lines=1
        )
        return voice

    def known(self, speaker_id: str) -> bool:
        return speaker_id in self._by_speaker

    def reset(self) -> None:
        self._by_speaker.clear()
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
