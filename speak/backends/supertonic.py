"""Backend SuperTonic 3: dieci voci, e parlano trentuno lingue.

Il piano dichiarava che le due voci italiane di Piper erano il tetto del tier A
e che per superarlo serviva la GPU (F6, Qwen3-TTS). SuperTonic 3 lo supera
restando su CPU e in ONNX: **cinque voci maschili e cinque femminili** native,
senza trucchi di pitch. Per F3 — voci diverse per personaggi diversi — e' la
differenza fra poter assegnare e dover riciclare.

Misurato su questa macchina, italiano, contro Piper:

    modello                    RTF     sintesi di una battuta da 2,4 s
    Piper riccardo x_low      0,026    ~60 ms
    SuperTonic 3, 4 passi     0,095    ~230 ms
    SuperTonic 3, 8 passi     0,17     ~410 ms

Il costo e' reale e non e' in streaming: la battuta si sintetizza intera, quindi
la latenza cresce con la sua lunghezza. Quattro passi di diffusione bastano —
otto costano il doppio e la differenza va giudicata a orecchio, non a occhio.

**La velocita' non e' un gusto, e' una misura.** A `speed` 1,05 la stessa frase
dura il 47% piu' che con Piper, il cui ritmo all'ascolto era gia' giusto.
Misurato su quattro battute vere: Piper fa 17,4 caratteri al secondo, e
SuperTonic li pareggia a **speed 1,50** (17,1 car/s, scarto +2%). Da qui il
default: non un numero scelto perche' suona bene, ma quello che allinea il
ritmo a un riferimento verificato.

I modelli (~398 MB) finiscono nella cache di SuperTonic, non in `models/`: li
gestisce il pacchetto e non ha senso duplicarli.

**E le dieci voci non sono italiane: sono multilingui.** `supertonic-3` parla
trentuno lingue con gli stessi dieci stili di parlante — un download solo per
tutte, che e' l'opposto di Piper. Questo backend passava `lang="it"` fisso,
quindi ogni lingua diversa dall'italiano usciva fonemizzata con le regole
italiane: e' la forma di difetto piu' cara di questo progetto, perche' l'audio
esce e nessun contatore lo mostra.
"""

from __future__ import annotations

import time

import numpy as np

from core.types import VoiceSpec
from mix.stretch import pitch_shift, resample
from speak.base import Speech, taglia_silenzio

# Frequenza nativa del vocoder.
NATIVE_RATE = 44100

# **Le lingue sono trentuno, non una.** `supertonic-3` e' un modello
# multilingue: le stesse dieci voci parlano tutte queste lingue, e la scelta si
# fa con l'argomento `lang` di `synthesize`. Questo backend lo passava
# **fisso a `"it"`**, quindi tradurre verso lo spagnolo produceva spagnolo
# fonemizzato con le regole italiane: audio che esce, contatori verdi, e una
# voce che pronuncia un'altra lingua.
#
# L'elenco sta scritto qui e non chiesto al pacchetto per la regola gia' pagata
# con `translate/lingue.py` — un elenco che dipende da un import si svuota quando
# quell'import non c'e', e un menu vuoto non da' errore. Che le due copie non
# divergano lo tiene la verifica `lingue_voci`, che le confronta quando
# `supertonic` e' importabile: e' il modo di avere una tabella ferma senza avere
# una tabella scritta due volte.
#
# **Le dieci voci non sono per lingua**: sono stili di parlante, e valgono per
# tutte e trentuno. E' l'opposto di Piper, dove ogni lingua e' un modello suo.
LINGUE: tuple[str, ...] = (
    "ar", "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr", "hi",
    "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "nl", "pl", "pt", "ro",
    "ru", "sk", "sl", "sv", "tr", "uk", "vi",
)

# La lingua che il pacchetto usa quando non conosce quella chiesta. **Non e' un
# ripiego accettabile qui**: se una lingua non e' fra le trentuno si cambia
# motore, non si consegna una fonemizzazione «generica» dicendo che va bene.
SCONOSCIUTA = "na"

# Le dieci voci preimpostate. I nomi sono quelli dei file di stile del modello.
VOICES = {
    "supertonic-M1": ("M1", "m"),
    "supertonic-M2": ("M2", "m"),
    "supertonic-M3": ("M3", "m"),
    "supertonic-M4": ("M4", "m"),
    "supertonic-M5": ("M5", "m"),
    "supertonic-F1": ("F1", "f"),
    "supertonic-F2": ("F2", "f"),
    "supertonic-F3": ("F3", "f"),
    "supertonic-F4": ("F4", "f"),
    "supertonic-F5": ("F5", "f"),
}

# **1,05 e non 1,50, e la calibrazione precedente era vera e inservibile.**
#
# «A speed 1,50 SuperTonic pareggia il ritmo di Piper, 17,1 caratteri al secondo
# contro 17,4» era misurato bene. Misurava pero' la **durata**, e un modello che
# salta pezzi di frase diventa piu' corto esattamente come uno che parla svelto:
# la prova non poteva esprimere il modo in cui questo fallisce.
#
# Contando invece i nuclei sillabici — i picchi dell'inviluppo di energia — sulle
# stesse dodici battute vere:
#
#     velocita'   nuclei   quanti ne restano
#       1,00        93          100%
#       1,05        88           95%
#       1,15        71           76%
#       1,50        63           68%
#       2,00        47           60%
#
# Il controllo che rende leggibile la tabella e' **Piper sulle stesse battute
# nello stesso intervallo**: 58, 60, 56, 59 nuclei da rate 1,00 a 1,60, cioe'
# costanti mentre l'audio si accorcia di sei secondi. Piper accorcia
# articolando; SuperTonic accorcia **buttando via**. (Il conteggio assoluto non
# si confronta fra i due motori — dipende dalla dinamica della voce — ma
# l'andamento dentro ciascuno si'.)
#
# Piu' passi di diffusione non aiutano (a 8 e 16 il conto e' uguale o peggiore,
# e costano il doppio e il triplo), e il difetto c'e' su tutte le voci provate.
#
# Sopra questa soglia quindi non si va, e la fretta che serve alla catena la fa
# WSOLA — che sara' anche rozzo, ma quello che comprime lo tiene: a parita' di
# durata finale, `1,00 + WSOLA` conserva 82 nuclei contro i 76 di `1,50`.
DEFAULT_SPEED = 1.05

# **Quanto il modello accetta, e cosa succede se glielo si chiede lo stesso.**
# Fuori da questi due numeri SuperTonic non rallenta e non tronca: solleva
# `ValueError` e la sessione muore. Ed e' facile uscirne senza accorgersene,
# perche' la velocita' finale e' un prodotto di tre cose decise in tre posti
# diversi — il ritmo di base (1,50, pareggiato a Piper), la fretta chiesta dalla
# catena (fino a `tts.native_rate_max`, 1,45) e il carattere della voce. Con i
# default del progetto fa 2,08, e sfora al primo sottotitolo lungo: succedeva
# alla battuta 10 di 44.
VELOCITA_MIN, VELOCITA_MAX = 0.7, 2.0

# **E questo e' il tetto che conta**, piu' basso di quello che il modello
# accetta: sopra, il modello continua a rispondere e comincia a saltare sillabe.
# Il pacchetto lo dice a suo modo nel messaggio d'errore — «use values closer to
# 1.05 for more natural speech» — ma non lo impone, e "meno naturale" suona
# innocuo mentre quello che succede e' che spariscono parole.
VELOCITA_INTEGRA = 1.10

# Caratteri di parlato al secondo **per unita' di `speed`**, nell'unita' di
# `spoken_length()`.
#
# L'italiano e' misurato su **dodici battute vere** di scena. Le altre trenta su
# **una frase sola** ciascuna (`tools/censisci_voci.py --misura`), e la
# differenza va detta invece che nascosta dietro una tabella dall'aria uniforme:
# una frase neutra non e' una scena, quindi questi numeri sono un ordine di
# grandezza giusto e non una taratura. Chi doppia sul serio in una di queste
# lingue rimisuri la sua sul materiale vero.
#
# Il verso in cui sbagliano conta: una previsione **corta** si paga piu' cara di
# una lunga, perche' porta la catena a comprimere invece che a lasciare respiro.
#
# Le tre lingue in fondo alla tabella (ja 6,3, ko 7,3, hi 8,4, ar 8,8) non sono
# motori lenti: sono **scritture dense**, dove un carattere vale una sillaba
# intera. Il numero e' basso perche' l'unita' e' il carattere, e va confrontato
# con le altre lingue della stessa scrittura, mai con l'italiano.
PASSO_PER_UNITA = 13.6
PASSO_LINGUA: dict[str, float] = {
    "ar": 8.8,
    "bg": 12.8,
    "cs": 13.8,
    "da": 16.3,
    "de": 16.9,
    "el": 14.5,
    "en": 16.5,
    "es": 14.2,
    "et": 13.8,
    "fi": 15.0,
    "fr": 16.6,
    "hi": 8.4,
    "hr": 12.3,
    "hu": 15.1,
    "id": 15.3,
    "it": 13.6,
    "ja": 6.3,
    "ko": 7.3,
    "lt": 11.4,
    "lv": 13.1,
    "nl": 14.9,
    "pl": 15.8,
    "pt": 14.9,
    "ro": 14.1,
    "ru": 14.0,
    "sk": 15.0,
    "sl": 13.5,
    "sv": 12.7,
    "tr": 14.8,
    "uk": 13.1,
    "vi": 13.9,
}


def velocita_effettiva(base: float, rate: float, carattere: float) -> float:
    """La velocita' da chiedere al modello, dentro cio' che sa fare **intero**.

    Il tetto non e' quello che il modello accetta (2,0) ma quello oltre il quale
    comincia a perdere sillabe (`VELOCITA_INTEGRA`): il primo lo protegge da un
    errore, il secondo protegge chi ascolta da una frase mangiata. Fra i due c'e'
    tutta la differenza fra "il modello ha risposto" e "il modello ha detto la
    battuta".

    Il residuo non si perde: chi chiama misura la durata che esce e la porta a
    quella voluta con WSOLA, che comprime rozzamente ma non butta via niente. A
    parita' di durata finale conserva piu' contenuto che chiedere la stessa
    fretta al modello — misurato, 82 nuclei sillabici contro 76.
    """
    return min(VELOCITA_INTEGRA, max(VELOCITA_MIN, base * rate * carattere))


class SupertonicTts:
    """Sintesi SuperTonic 3, con gli stili caricati su richiesta."""

    name = "supertonic"

    def __init__(
        self,
        samplerate: int = 22050,
        steps: int = 4,
        speed: float = DEFAULT_SPEED,
        download: bool = True,
        lingua: str = "it",
    ) -> None:
        self.samplerate = samplerate
        self.steps = max(1, int(steps))
        self.speed = float(speed)
        self.download = download
        # La lingua **del testo che verra' detto**: se si traduce, quella di
        # arrivo. Fuori dalle trentuno si ripiega sull'italiano invece che sul
        # `na` del pacchetto, perche' `speak.pool.ha_voce` ha gia' detto di no e
        # chi e' arrivato fin qui l'ha scavalcato di proposito.
        base = (lingua or "it").replace("_", "-").split("-")[0].lower()
        self.lingua = base if base in LINGUE else "it"
        self._tts = None
        self._styles: dict[str, object] = {}

    @property
    def chars_per_second(self) -> float:
        """Lettere e cifre al secondo, nell'unita' di `spoken_length()`.

        **Il passo e' lineare nella velocita' chiesta**, e non era ovvio: il
        `length_scale` di Piper non lo e' affatto, tanto che la pipeline si porta
        un anello di correzione apposta. Misurato sulle stesse dodici battute
        vere, 320 caratteri, **al netto del silenzio** (si veda
        `speak.base.taglia_silenzio`: prima era il 39% dell'uscita, e contarlo
        faceva sembrare questo motore un terzo piu' lento di quello che e'):

            speed 1,05   ->  14,3 car/s     (13,6 per unita')

        Il passo si dichiara come prodotto invece che come costante: chi cambia
        `tts.speed` non deve anche ricordarsi di cambiare la stima delle durate,
        che e' il genere di accoppiamento che si dimentica sempre. A 1,05 fa 14,3
        contro i 14,8 di Piper — **il ritmo e' pari**, e senza chiedere a nessuno
        dei due di correre.

        **E cambia con la lingua**, per la stessa ragione gia' pagata quattro
        volte in questo progetto: il 13,6 e' misurato sull'italiano, e usarlo su
        una lingua piu' densa fa credere ogni battuta piu' lunga di quanto sia,
        cioe' comprimere al tetto una scena che aveva tutto il tempo. Le altre
        vengono da `tools/censisci_voci.py --misura`, stesso metodo.
        """
        return PASSO_LINGUA.get(self.lingua, PASSO_PER_UNITA) * self.speed

    # -- caricamento -------------------------------------------------------

    def _engine(self):
        if self._tts is None:
            try:
                import supertonic
            except ImportError as e:  # pragma: no cover - dipende dall'ambiente
                raise RuntimeError(
                    "supertonic non installato: "
                    "`.\\.venv\\Scripts\\python.exe -m pip install supertonic`"
                ) from e
            self._tts = supertonic.TTS(auto_download=self.download)
        return self._tts

    def _style(self, base_voice: str):
        cached = self._styles.get(base_voice)
        if cached is not None:
            return cached
        nome = VOICES.get(base_voice, (None, None))[0]
        if nome is None:
            raise ValueError(
                f"voce SuperTonic sconosciuta: {base_voice!r} (note: {sorted(VOICES)})"
            )
        style = self._engine().get_voice_style(nome)
        self._styles[base_voice] = style
        return style

    def preload(self, names: list[str]) -> None:
        """Carica in anticipo. Il primo `synthesize` costruisce le sessioni ONNX
        e paga tutto il caricamento: non deve capitare sulla prima battuta."""
        for n in names:
            try:
                self._style(n)
            except Exception:
                pass

    # -- sintesi -----------------------------------------------------------

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        text = text.strip()
        if not text:
            return Speech(np.zeros(0, np.float32), self.samplerate, voice.voice_id, text=text)

        style = self._style(voice.base_voice)
        effective = velocita_effettiva(self.speed, rate, voice.rate)

        t0 = time.perf_counter()
        wav, _ = self._engine().synthesize(
            text, style, total_steps=self.steps, speed=effective, lang=self.lingua
        )
        total_ms = (time.perf_counter() - t0) * 1000.0

        audio = np.asarray(wav, dtype=np.float32).reshape(-1)
        # **Prima di ogni altra cosa, via l'imbottitura.** Il 39% di cio' che
        # esce e' silenzio, e ogni stadio a valle lo tratterebbe come parlato:
        # lo scheduler ci calcolerebbe sopra le finestre, WSOLA lo comprimerebbe,
        # e il correttore della velocita' chiederebbe al modello di dirlo piu' in
        # fretta. Si taglia qui, dove si sa ancora che cos'e'.
        audio = taglia_silenzio(audio, NATIVE_RATE)
        if audio.size and voice.semitones:
            audio = pitch_shift(audio, voice.semitones, samplerate=NATIVE_RATE)
        if NATIVE_RATE != self.samplerate:
            audio = resample(audio, NATIVE_RATE, self.samplerate)

        return Speech(
            audio=audio,
            samplerate=self.samplerate,
            voice_id=voice.voice_id,
            # Non c'e' streaming: il primo campione esiste quando esiste tutto.
            # Dichiararlo pari al totale e' l'unica cosa onesta — riportare un
            # numero piccolo qui farebbe sembrare la latenza migliore di com'e'.
            first_sample_ms=total_ms,
            total_ms=total_ms,
            text=text,
        )
