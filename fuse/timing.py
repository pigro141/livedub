"""Quanto dura una battuta, deciso prima di saperlo.

Il sottotitolo compare a `T` e sparisce a `T + D`, ma `D` si conosce solo quando
sparisce — cioe' quando la battuta e' gia' stata detta, o non lo e' stata
affatto. Tutto F2 nasce da questo sfasamento, e la risposta e' in tre pezzi che
lavorano su scale di tempo diverse:

1. **la previsione** (`DurationModel`) — `D = a + b*n_caratteri`, coefficienti
   misurati offline con `tools/bench_timing.py` e corretti mentre gira;
2. **l'aggancio all'originale** — l'onset del VAD sul canale centrale dice
   quando il personaggio comincia davvero a parlare, ed e' piu' preciso della
   comparsa del sottotitolo. Non e' qui: sta nel dominio audio, e arriva dopo;
3. **la correzione in volo** — mentre la voce suona il sottotitolo sparisce, e a
   quel punto `D` e' un fatto: si stira il residuo con WSOLA.

## La previsione e' debole, e va detto qui e non nei commenti di chi la usa

Misurato sulla registrazione, la lunghezza del testo spiega circa un terzo della
varianza della durata. Non e' un difetto dell'adattamento: e' che il tempo di
permanenza di un sottotitolo lo decide il ritmo della conversazione, e la
lunghezza del testo ne e' solo un indizio. Da qui due conseguenze di progetto:

- la previsione serve a **partire**, non a decidere. Chi la usa deve essere
  pronto a essere smentito a meta' battuta, ed e' esattamente il motivo per cui
  la correzione in volo non e' un ornamento ma la parte portante;
- `never_drop` non e' negoziabile. Quando la correzione non basta si **sfora**:
  una battuta detta in ritardo e' un difetto, una battuta non detta e' un buco.

## Il ritardo costante non e' un debito, e la tabella che lo dice

Il budget di una battuta era `finestra prevista - tempo gia' passato`, e dentro
quel tempo passato c'era anche cio' che si paga **su ogni battuta allo stesso
modo**: mezzo secondo di attesa per sapere chi parla, piu' la sintesi. Chiedere a
ogni riga di recuperarlo da sola significa comprimerle tutte per un ritardo che
tornera' identico alla riga dopo — e infatti `dub.rate_x1000` risultava inchiodato
al tetto su **tutti** i percentili con SuperTonic, e a 1,146 di mediana con Piper.

Misurato sulle 44 battute della scena del concessionario, stessa registrazione,
stesse voci assegnate in tutte e quattro le passate (il percorso di chi parla non
c'entra ed e' rimasto identico: e' il controllo che rende confrontabili le righe):

    accettato   compressione p50   battute al tetto   latenza p50   p95    sfori
       0 ms          1,146               25%            576 ms    1174 ms    16
     250 ms          1,000               14%            587 ms    1272 ms     6
     500 ms          1,000               18%            592 ms    1371 ms     9
     750 ms          1,000               11%            592 ms    1370 ms     7

**250 ms e' il ginocchio**: porta la battuta mediana a non essere compressa
affatto, e costa undici millisecondi di latenza percepita. Oltre, si continua a
pagare latenza senza comprare quasi niente — e il motivo e' che il ritardo
scusato entra anche nell'arretrato della coda: piu' si scusa, piu' le battute
durano, piu' la coda cresce, e le battute ancora al tetto sono proprio quelle
prese dentro una raffica, dove a dominare non e' piu' l'attesa ma l'arretrato
vero.

**La deriva, che era il rischio, non c'e'**: le ultime dieci battute sono in
ritardo *meno* delle prime dieci (-185 ms a 250 ms di scusa). Il parlato italiano
occupa il 65% della scena, quindi la coda ha dove smaltire — ma su una scena
molto piu' fitta questo numero va riguardato, ed e' la prima cosa da rimisurare
se il doppiaggio comincia a slittare.

## L'aggiornamento in linea, e perche' e' prudente

I coefficienti si aggiornano mentre la sessione gira, con somme pesate che
dimenticano lentamente il passato: una scena concitata e una scena lenta hanno
ritmi diversi, e i coefficienti di ieri sera non li descrivono entrambi.

Ma un aggiornamento in linea e' anche il posto ideale per rovinare tutto in
silenzio, quindi ha tre guardie: si ignorano le durate implausibili (una
battuta riaperta a meta' produce frammenti, e un frammento non e' una battuta
corta); non si tocca niente finche' i campioni non bastano; e la retta imparata
non puo' allontanarsi dai coefficienti del profilo piu' di quanto dichiarato.
Le prime due impediscono di imparare spazzatura, la terza impedisce di
imparare **bene** una cosa sbagliata.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import TimingConfig


def spoken_length(text: str) -> int:
    """Quanto e' lunga una battuta, ai fini del tempo che occupa.

    **Solo lettere e cifre**, come la forma di confronto dello stabilizzatore.
    Non e' una scelta di eleganza: la stessa battuta letta due volte da'
    `'Ma domani...'` e `'Madomani.'`, e l'OCR non sbaglia solo la punteggiatura
    — si mangia anche lo spazio. Contando lettere, cifre e spazi le due letture
    danno 9 e 8; contando le sole lettere danno 8 e 8. Far dipendere la durata
    prevista da quanto era sfocato il frame e' precisamente il difetto da
    evitare, e gli spazi ne sono una fonte quanto i punti.

    Il prezzo e' che una frase di parole corte e una di parole lunghe con lo
    stesso numero di lettere ricevono la stessa previsione. E' un errore piccolo
    rispetto a quello che la previsione ha di suo.
    """
    return sum(1 for ch in text if ch.isalnum())


@dataclass(frozen=True, slots=True)
class Plan:
    """Come dire una battuta: quanto tempo c'e' e a che velocita' starci dentro."""

    budget: float  # secondi disponibili prima della scadenza prevista
    rate: float  # velocita' da chiedere al sintetizzatore
    overflow: float  # secondi di sforamento previsti; 0 se ci sta
    predicted: float  # la durata prevista da cui viene tutto

    @property
    def fits(self) -> bool:
        return self.overflow <= 0.0


class DurationModel:
    """`D = a + b * n`, misurata offline e corretta mentre gira."""

    def __init__(self, cfg: TimingConfig) -> None:
        self.cfg = cfg
        self.a = float(cfg.predict_a)
        self.b = float(cfg.predict_b)
        self._a0, self._b0 = self.a, self.b  # i valori del profilo, come ancora
        # Somme pesate per la retta ai minimi quadrati, con oblio.
        self._w = self._sn = self._sd = self._snn = self._snd = 0.0
        self.samples = 0
        self.ignored = 0

    # -- previsione --------------------------------------------------------

    def predict(self, text: str) -> float:
        """La durata prevista, mai negativa e mai assurda."""
        n = spoken_length(text)
        return max(self.cfg.min_duration, min(self.cfg.max_duration, self.a + self.b * n))

    def plan(self, text: str, spoken: float, elapsed: float = 0.0) -> Plan:
        """Da quanto durerebbe la sintesi a che velocita' chiederla.

        `spoken` e' quanto durerebbe la battuta alla velocita' nominale della
        voce; `elapsed` e' quanto tempo della finestra e' gia' andato — l'attesa
        dell'embedding, il ritardo del riconoscimento, la coda — e va sottratto,
        perche' il budget e' quello che resta, non quello che c'era.

        **Ma non tutto quel tempo e' perduto allo stesso modo.** La parte che
        torna identica a ogni battuta — mezzo secondo di attesa per sapere chi
        parla, piu' la sintesi — non e' un debito di *questa* battuta: e' uno
        spostamento del doppiaggio nel suo complesso, e chiedere a ogni riga di
        recuperarlo da sola vuol dire comprimerle tutte per un ritardo che
        tornera' comunque. `accepted_delay_ms` e' quanto di quel tempo si accetta
        senza rincorrerlo; quello che resta — l'arretrato della coda, che varia
        da battuta a battuta — si recupera come prima.
        """
        predicted = self.predict(text)
        scusato = max(0.0, self.cfg.accepted_delay_ms / 1000.0)
        budget = max(0.0, predicted - max(0.0, elapsed - scusato))
        if spoken <= 0.0 or budget <= 0.0:
            return Plan(budget=budget, rate=1.0, overflow=max(0.0, spoken - budget), predicted=predicted)

        wanted = spoken / budget  # >1 significa "vai piu' svelto"
        rate = min(self.cfg.rate_max, max(self.cfg.rate_min, wanted))
        overflow = max(0.0, spoken / rate - budget)
        if overflow > 0 and not self.cfg.never_drop:
            overflow = 0.0  # chi non sfora scarta, ed e' una scelta che non e' nostra
        return Plan(budget=budget, rate=rate, overflow=overflow, predicted=predicted)

    # -- apprendimento -----------------------------------------------------

    def observe(self, text: str, duration: float) -> bool:
        """Una durata vera. Restituisce `True` se e' stata usata.

        Una battuta riaperta a meta' produce due durate corte, e sono false: si
        scartano per la stessa ragione per cui `tools/bench_timing.py` le tiene
        fuori dalla regressione, cioe' che non sono durate di battute.
        """
        n = spoken_length(text)
        if not (self.cfg.min_duration <= duration <= self.cfg.max_duration) or n <= 0:
            self.ignored += 1
            return False

        decay = self.cfg.learn_decay
        self._w = self._w * decay + 1.0
        self._sn = self._sn * decay + n
        self._sd = self._sd * decay + duration
        self._snn = self._snn * decay + n * n
        self._snd = self._snd * decay + n * duration
        self.samples += 1
        if self.samples >= self.cfg.learn_min_samples:
            self._refit()
        return True

    def _refit(self) -> None:
        """Ricalcola la retta, e non lascia che si allontani troppo dal profilo."""
        denom = self._w * self._snn - self._sn * self._sn
        if abs(denom) < 1e-9:  # tutte le battute della stessa lunghezza
            return
        b = (self._w * self._snd - self._sn * self._sd) / denom
        a = (self._sd - b * self._sn) / self._w
        drift = self.cfg.learn_max_drift
        self.a = _clamp(a, self._a0 - drift, self._a0 + drift)
        # La pendenza si muove in proporzione: `b` e' in secondi per carattere, e
        # una fascia assoluta larga uguale per entrambi sarebbe enorme per lei.
        self.b = _clamp(b, self._b0 * (1.0 - drift), self._b0 * (1.0 + drift))

    def __repr__(self) -> str:  # comodo nei log
        return f"DurationModel(D = {self.a:.3f} + {self.b:.4f}*n, campioni={self.samples})"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(min(lo, hi), min(max(lo, hi), x))
