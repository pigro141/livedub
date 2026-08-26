"""Backend Kokoro-82M: qualita' alta, ma solo se ha una GPU.

Misurato su questa macchina (i9-11900K + RTX 4060), 24 battute vere della scena
del concessionario, costo a muro, prima sintesi scartata:

    pesi           dove      costo p50   p95      RTF     car/s
    fp32 (326 MB)  CPU         725 ms    998 ms   0,338   12,9
    fp32 (326 MB)  CUDA        207 ms    253 ms   0,102   12,9
    int8 (92 MB)   CPU        2950 ms   3957 ms   1,357   13,0

Tre conseguenze, tutte scritte perche' nessuna e' ovvia:

**Su CPU non e' vivibile.** 725 ms di sola sintesi portano la latenza percepita
attorno a 1250 ms, contro i 951 gia' giudicati troppi dal vivo. Su CUDA costa
207 ms, cioe' quanto SuperTonic, con una coda molto piu' stretta (p95 253 contro
998). Per questo il backend guarda `tts.device` e **dichiara su stderr** quando
ripiega sulla CPU: un ripiego silenzioso qui vorrebbe dire consegnare un
doppiaggio in ritardo senza che nessun numero lo dica.

**Il quantizzato e' piu' lento del fp32, non piu' veloce** — quattro volte. Int8
su CPU senza kernel dedicati costa in conversioni piu' di quanto risparmi in
moltiplicazioni. Resta nella tabella `PESI` perche' su un'altra macchina il
conto potrebbe tornare, ma il default e' `fp32` e la ragione e' misurata.

**Il prezzo della GPU e' 1128 MB di VRAM**, su una scheda da 8 GB che deve far
girare anche il gioco. E' il numero da riguardare per primo se GTA V comincia a
scattare.

Le voci italiane sono **due**, come Piper: `if_sara` e `im_nicola`. Il pool si
riallarga per trasformazione (si veda `speak/pool.py`), non perche' sia bello ma
perche' non c'e' altro.

**`kokoro_onnx.create()` non si usa, ed e' voluto.** Nel suo ramo "newer export"
passa `speed` come `np.int32`: con questi pesi solleva subito, ma con un altro
export troncherebbe 1,1 a 1 **in silenzio**, e la leva della velocita' nativa
smetterebbe di fare qualunque cosa senza che niente lo segnali. La sessione si
guida direttamente, come `listen/embed.py` fa con ECAPA; del pacchetto si usa
quello per cui e' buono, cioe' la fonemizzazione e il vocabolario.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from core import percorsi
from core.types import VoiceSpec
from mix.stretch import pitch_shift, resample
from speak.base import Speech, taglia_silenzio

# La frequenza del vocoder Kokoro. Non e' negoziabile e non coincide con quella
# di lavoro (22050): il ricampionamento in coda non e' un dettaglio, senza il
# personaggio parlerebbe come un disco andato a rilento.
NATIVE_RATE = 24000

MODELS_DIR = percorsi.modelli("kokoro")
REPO = "onnx-community/Kokoro-82M-v1.0-ONNX"

# I set di pesi disponibili nel repo HF. Il default e' `fp32` per misura, non
# per prudenza: si veda la tabella in cima.
PESI = {
    "fp32": "onnx/model.onnx",
    "fp16": "onnx/model_fp16.onnx",
    "int8": "onnx/model_quantized.onnx",
    "q8f16": "onnx/model_q8f16.onnx",
}
DEFAULT_PESI = "fp32"

# **Le cinquantaquattro voci del modello, e il nome le classifica.** La prima
# lettera e' la lingua (`a` American, `b` British, `e` Spanish, `f` French,
# `h` Hindi, `i` Italian, `j` Japanese, `p` Portoghese brasiliano, `z` Mandarino),
# la seconda il sesso. Quindi qui non si indovina niente: la lingua e il genere
# di una voce Kokoro **stanno scritti nel suo nome**, ed e' il contrario di
# Piper, dove l'indice non dice il sesso e fuori dall'italiano resta `?`.
#
# Si scaricano solo le voci della lingua che si parlera' (510 KB l'una) invece
# del `voices-v1.0.bin` da 26 MB — e la stessa scelta e' il motivo per cui
# `voices_path` deve guardare **cosa** c'e' nell'archivio, non che ci sia.
#
# `voices/af.bin` esiste nel repo e non e' qui: e' la miscela storica della
# v0.19, non una voce del set v1.0.
_PREFISSI = {
    "a": ("en", "en-us"), "b": ("en", "en-gb"), "e": ("es", "es"),
    "f": ("fr", "fr-fr"), "h": ("hi", "hi"), "i": ("it", "it"),
    "j": ("ja", "ja"), "p": ("pt", "pt-br"), "z": ("zh", "cmn"),
}

_NOMI: tuple[str, ...] = (
    "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore",
    "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
    "am_onyx", "am_puck", "am_santa",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    "ef_dora", "em_alex", "em_santa",
    "ff_siwis",
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
    "if_sara", "im_nicola",
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    "pf_dora", "pm_alex", "pm_santa",
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
)

# Le tabelle si **ricavano** dai nomi invece di essere riscritte: un elenco
# scritto due volte e' un elenco di cui la seconda copia non aggiorna nessuno,
# e in questo progetto e' gia' successo sette volte.
#
# **Il nome corto non basta piu'.** Con le sole voci italiane e inglesi era
# unico; sulle cinquantaquattro ci sono tre `santa`, due `dora`, due `alex` e
# due `alpha` in lingue diverse. Chi collide prende davanti il codice della sua
# lingua, e chi non collide resta com'era — cosi' `kokoro-nicola`,
# `kokoro-heart` e le altre gia' misurate non cambiano nome.
def _chiavi() -> dict[str, tuple[str, str]]:
    from collections import Counter

    quanti = Counter(n.split("_", 1)[1] for n in _NOMI)
    fuori: dict[str, tuple[str, str]] = {}
    for n in _NOMI:
        corto = n.split("_", 1)[1]
        lingua = _PREFISSI[n[0]][0]
        chiave = f"kokoro-{corto}" if quanti[corto] == 1 else f"kokoro-{lingua}_{corto}"
        if chiave in fuori:  # pragma: no cover - lo prende la verifica `lingue_voci`
            raise ValueError(f"due voci Kokoro con la stessa chiave: {chiave}")
        fuori[chiave] = (n, n[1])
    return fuori


VOICES: dict[str, tuple[str, str]] = _chiavi()

# **Le famiglie per lingua**: `build_pool` prende quella giusta invece di
# mescolare voci di lingue diverse nello stesso pool — che darebbe a un
# personaggio una voce che pronuncia l'altra lingua. L'ordine alterna maschile e
# femminile, perche' due personaggi consecutivi si distinguono molto di piu' se
# cambia il genere che se cambia il timbro.
#
# **Le voci gia' scelte restano davanti.** Le sei inglesi qui sotto sono quelle
# con il voto piu' alto nella scheda ufficiale del modello (A, A-, B-, C+, C+,
# C) e sono le sole di questo motore che qualcuno abbia ascoltato: le altre
# ventidue entrano dopo, perche' «esiste una voce in questa lingua» e «e' una
# voce buona» sono due affermazioni diverse e qui se ne dichiara solo la prima.
PREFERITE: dict[str, tuple[str, ...]] = {
    "en": (
        "kokoro-michael", "kokoro-heart", "kokoro-fenrir",
        "kokoro-bella", "kokoro-george", "kokoro-emma",
    ),
}


def _per_lingua() -> dict[str, tuple[str, ...]]:
    fuori: dict[str, list[str]] = {}
    for chiave, (nome, _g) in VOICES.items():
        fuori.setdefault(_PREFISSI[nome[0]][0], []).append(chiave)
    ordinate: dict[str, tuple[str, ...]] = {}
    for lingua, voci in fuori.items():
        teste = [v for v in PREFERITE.get(lingua, ()) if v in voci]
        resto = [v for v in voci if v not in teste]
        m = [v for v in resto if VOICES[v][1] == "m"]
        f = [v for v in resto if VOICES[v][1] == "f"]
        alterne: list[str] = list(teste)
        for i in range(max(len(m), len(f))):
            if i < len(m):
                alterne.append(m[i])
            if i < len(f):
                alterne.append(f[i])
        ordinate[lingua] = tuple(alterne)
    return ordinate


PER_LINGUA: dict[str, tuple[str, ...]] = _per_lingua()

LINGUA = "it"

# La lingua che `espeak` deve fonemizzare, per codice ISO. **Non e' un dettaglio
# di cortesia**: fonemizzare l'inglese con le regole italiane produce parlato
# comprensibile a meta', e sembrerebbe un difetto del modello.
#
# Si ricava dai prefissi delle voci, cosi' una lingua non puo' avere voci senza
# avere anche le sue regole di fonemizzazione — che era il modo esatto in cui
# questo file mentiva prima: `FONEMI_LINGUA` elencava gia' es/fr/de/pt e le voci
# no, quindi la fonemizzazione era pronta per lingue che il pool non sapeva
# parlare, e le voci di sette lingue restavano invisibili.
FONEMI_LINGUA: dict[str, str] = {
    _PREFISSI[n[0]][0]: _PREFISSI[n[0]][1] for n in reversed(_NOMI)
}

# Quanti fonemi il modello accetta in un colpo. Le battute vere di GTA V ne
# fanno un'ottantina, quindi il limite non si tocca mai — ma una battuta troncata
# in silenzio sarebbe una frase mangiata senza nessun segnale, quindi lo
# spezzettamento esiste lo stesso.
MAX_FONEMI = 510

# **Quanto il modello accetta, e cosa succede se glielo si chiede lo stesso.**
# Fuori da questi due numeri `kokoro_onnx` solleva un `AssertionError`. La
# velocita' finale e' un prodotto di tre cose decise in tre posti diversi, e la
# catena puo' chiedere fino a `rate=3.0` (`core/pipeline.py`, `min(nativo *
# self._native_gain, 3.0)`) — **non** fino a `tts.native_rate_max`.
VELOCITA_MIN, VELOCITA_MAX = 0.5, 2.0

# **E questo e' il tetto che conta.** Misurato contando i nuclei sillabici
# (picchi dell'inviluppo di energia) su 14 battute vere, contro il caso nullo
# della stessa battuta a velocita' 1 ricampionata — che per costruzione non ha
# perso niente, e serve perche' il contatore da solo perde nuclei sull'audio
# compresso:
#
#     speed   nuclei Kokoro   caso nullo   scarto
#      1,20        90,9%         89,6%      +1,3   articola
#      1,30        84,4%        ~82  %       ~0    articola
#      1,35        48,1%           -       precipizio
#      1,40        45,5%         75,3%     -29,8   mangia sillabe
#
# Fra 1,30 e 1,35 c'e' un salto, non una degradazione: a 1,35 la durata scende
# **sotto** quella richiesta, che e' la firma di chi butta via invece di correre.
# Letto contro il 100% invece che contro il caso nullo, lo stesso conto avrebbe
# accusato Kokoro gia' a 1,20.
#
# 1,30 contro l'1,10 di SuperTonic e' una notizia buona: piu' fretta assorbita
# dal motore, che **articola**, e meno scaricata su WSOLA, che schiaccia.
VELOCITA_INTEGRA = 1.30

DEFAULT_SPEED = 1.0

# Lettere e cifre al secondo per unita' di velocita', nell'unita' di
# `spoken_length()` — solo caratteri alfanumerici, e **dopo `taglia_silenzio`**.
# Misurato su 24 battute vere, 686 caratteri: 12,93 con `im_nicola` e 13,30 con
# `if_sara`, a `speed = 1,0`. Si dichiara il valore maschile perche' e' il piu'
# lento dei due e una previsione corta si paga piu' cara di una lunga.
#
# **L'unita' e' la meta' del numero.** Contando *tutti* i caratteri la stessa
# passata darebbe 15,5, ed e' esattamente da quella confusione che veniva il
# 17,4 di config rimasto sbagliato per anni.
PASSO_PER_UNITA = 12.9

# **E il passo cambia con la lingua, che non era ovvio e si e' sentito.**
#
# Il 12,9 qui sopra e' misurato sull'italiano. Traducendo in inglese, la catena
# continuava a usarlo: `stima = n / 12,9` faceva credere ogni battuta piu' lunga
# di quanto fosse, il budget usciva stretto, e WSOLA comprimeva **al tetto** —
# `dub.rate_x1000` a 1250 su tutti i percentili — mentre il parlato riempiva
# appena il 49% della scena. Compressione autoinflitta da una stima sbagliata:
# c'era tutto il tempo del mondo e la voce correva lo stesso.
#
# Misurato in due modi che concordano nel verso:
#
#     banco, 10 frasi x 2 voci   14,37 car/s   (13,73 michael, 15,00 heart)
#     sessione dal vivo, 18 battute   16,73 car/s
#
# Si dichiara il valore del banco, che e' il piu' controllato e il piu' basso dei
# due: una previsione corta si paga piu' cara di una lunga, perche' porta a
# comprimere invece che a lasciare respiro.
#
# **Chi aggiunge una lingua misuri la sua**, con `spoken_length()` e dopo
# `taglia_silenzio`: un numero preso da un'altra lingua e' esattamente il difetto
# che questa tabella esiste per chiudere.
PASSO_LINGUA = {
    "it": 12.9,
    "en": 14.37,
}


def model_path(quale: str = DEFAULT_PESI, download: bool = True) -> Path:
    """Percorso del set di pesi, scaricandolo alla prima richiesta.

    Finisce in `models/`, che e' gitignorato: 326 MB, materiale della macchina.
    """
    sub = PESI.get(quale)
    if sub is None:
        raise ValueError(f"pesi Kokoro sconosciuti: {quale!r} (noti: {sorted(PESI)})")
    local = MODELS_DIR / sub
    if local.exists():
        return local
    if not download:
        raise FileNotFoundError(f"pesi non presenti: {local}")

    from huggingface_hub import hf_hub_download

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    hf_hub_download(REPO, sub, local_dir=str(MODELS_DIR))
    return local


def nomi_richiesti(lingua: str = LINGUA) -> tuple[str, ...]:
    """I nomi HF delle voci che servono per parlare quella lingua.

    Sono quelle e non tutte: cinquantaquattro stili fanno 27 MB, e ventotto sono
    inglesi. Chi doppia in italiano non ha nessun motivo di avere sul disco le
    voci mandarine.
    """
    chiavi = PER_LINGUA.get((lingua or LINGUA).replace("_", "-").split("-")[0].lower())
    if not chiavi:
        chiavi = PER_LINGUA[LINGUA]
    return tuple(VOICES[c][0] for c in chiavi)


def voices_path(download: bool = True, lingua: str = LINGUA) -> Path:
    """L'archivio degli stili, con dentro **almeno** le voci di questa lingua.

    `kokoro_onnx` vuole un file che `np.load` sappia aprire; il repo HF tiene le
    voci una per file. Si scaricano solo quelle che servono e si impacchettano,
    cosi' non si tirano giu' 26 MB di voci giapponesi e hindi per doppiare in
    italiano.

    **Si controlla che l'archivio contenga quello che serve, non che esista.**
    La prima versione tornava indietro appena il file c'era: aggiungendo le voci
    inglesi, il file vecchio — con dentro le sole due italiane — e' rimasto buono
    agli occhi di questa funzione, e la prima voce inglese e' morta con un
    `KeyError` dentro `kokoro_onnx`, lontanissimo da dove stava il difetto. Con
    cinquantaquattro voci in nove lingue quel difetto non e' piu' un caso di
    frontiera: e' la **norma**, perche' cambiare lingua cambia le voci che
    servono a ogni sessione.
    E l'archivio si **allarga** invece di essere rifatto: chi ha gia' scaricato
    le due italiane e passa allo spagnolo paga tre file, non cinquantaquattro.
    """
    local = MODELS_DIR / "voices.npz"
    servono = set(nomi_richiesti(lingua))
    gia: dict[str, np.ndarray] = {}
    if local.exists():
        try:
            with np.load(local) as z:
                if servono <= set(z.files):
                    return local
                gia = {n: z[n] for n in z.files}
        except Exception:  # pragma: no cover - archivio corrotto: si rifa'
            gia = {}
    if not download:
        raise FileNotFoundError(
            f"voci non presenti o incomplete in {local}: mancano "
            f"{sorted(servono - set(gia))}"
        )

    from huggingface_hub import hf_hub_download

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    stili = dict(gia)
    for nome in sorted(servono - set(gia)):
        p = hf_hub_download(REPO, f"voices/{nome}.bin", local_dir=str(MODELS_DIR))
        crudo = np.fromfile(p, dtype=np.float32)
        # Il reshape e' la verifica: un file troncato darebbe un array plausibile
        # e uno stile spostato di qualche riga, cioe' una voce sbagliata invece
        # di un errore.
        if crudo.size % 256:
            raise ValueError(f"voce {nome} malformata: {crudo.size} float, non multiplo di 256")
        stili[nome] = crudo.reshape(-1, 1, 256)
    np.savez(local, **stili)
    return local


def spezza_fonemi(fonemi: str, limite: int = MAX_FONEMI) -> list[str]:
    """Spezza sulla punteggiatura quando la battuta supera il limite.

    Funzione pura, e non per eleganza: cosi' la si prova nel selftest senza il
    modello. Con le battute vere non entra mai in funzione — ma un troncamento
    silenzioso sarebbe mezza frase detta come se fosse tutta, che e' il difetto
    che nessuna misura di durata puo' vedere.
    """
    fonemi = fonemi.strip()
    if len(fonemi) <= limite:
        return [fonemi] if fonemi else []

    pezzi: list[str] = []
    corrente = ""
    for parte in fonemi.replace(";", ".").replace("!", ".").replace("?", ".").split("."):
        parte = parte.strip()
        if not parte:
            continue
        if corrente and len(corrente) + len(parte) + 1 > limite:
            pezzi.append(corrente)
            corrente = parte
        else:
            corrente = f"{corrente} {parte}".strip()
    if corrente:
        pezzi.append(corrente)
    # Se anche un pezzo solo sfora (una battuta senza punteggiatura), si taglia
    # duro: meglio un pezzo in meno che un `AssertionError` a meta' scena.
    return [p[:limite] for p in pezzi if p]


def velocita_effettiva(base: float, rate: float, carattere: float) -> float:
    """La velocita' da chiedere al modello, dentro cio' che sa fare **intero**.

    Il tetto non e' quello che il modello accetta (2,0) ma quello oltre il quale
    comincia a perdere sillabe (`VELOCITA_INTEGRA`, 1,30): il primo lo protegge
    da un errore, il secondo protegge chi ascolta da una frase mangiata.

    Il residuo non si perde: chi chiama misura la durata che esce e la porta a
    quella voluta con WSOLA, che comprime rozzamente ma non butta via niente.
    """
    return min(VELOCITA_INTEGRA, max(VELOCITA_MIN, base * rate * carattere))


class KokoroTts:
    """Sintesi Kokoro-82M, con la sessione e gli stili caricati su richiesta."""

    name = "kokoro"

    def __init__(
        self,
        samplerate: int = 22050,
        speed: float = DEFAULT_SPEED,
        pesi: str = DEFAULT_PESI,
        device: str = "auto",
        lingua: str = LINGUA,
        download: bool = True,
    ) -> None:
        self.samplerate = samplerate
        self.speed = float(speed)
        self.pesi = pesi
        self.device = device
        # La lingua **del testo che verra' detto**, non quella del gioco: se si
        # traduce, e' quella di arrivo. Fonemizzare l'inglese con le regole
        # italiane da' parlato comprensibile a meta' e sembra un difetto del
        # modello.
        self.lingua_base = (lingua or "it").split("-")[0]
        self.lingua = FONEMI_LINGUA.get(self.lingua_base, lingua)
        self.download = download
        self._k = None
        self._provider = "?"

    @property
    def chars_per_second(self) -> float:
        """Lettere e cifre al secondo, nell'unita' di `spoken_length()`.

        Dichiarato come prodotto e non come costante, come per SuperTonic: chi
        cambia `tts.speed` non deve anche ricordarsi di cambiare la stima delle
        durate, che e' il genere di accoppiamento che si dimentica sempre.

        12,9 contro i 14,8 di Piper: Kokoro parla **piu' adagio**, quindi la
        catena gli chiedera' fretta piu' spesso. E' il motivo per cui il tetto
        misurato a 1,30 conta piu' qui che altrove.
        """
        # **Per lingua**: si veda `PASSO_LINGUA`. Usare il numero italiano
        # sull'inglese faceva comprimere al tetto una scena piena a meta'.
        return PASSO_LINGUA.get(self.lingua_base, PASSO_PER_UNITA) * self.speed

    # -- caricamento -------------------------------------------------------

    def _provider_voluto(self) -> list[str]:
        """Quali provider ONNX chiedere, e cosa dire se non ci sono.

        `tts.device` era dichiarato in config e **non lo leggeva nessuno**. Qui
        comincia a valere qualcosa, e vale solo per questo backend: Piper e
        SuperTonic girano su CPU per scelta e non lo guardano.

        La scelta — e il `preload_dlls()` senza il quale ORT ripiega sulla CPU in
        silenzio — sta in `core/onnx.py`, perche' non e' di questo backend: e' di
        chiunque apra una sessione ONNX, e finche' e' vissuta qui ci sono cascati
        in due.
        """
        from core.onnx import provider_voluti

        # Il costo va detto: chi ascolta il ripiego deve sapere che sta ascoltando
        # il ripiego, non concluderne che Kokoro e' lento.
        return provider_voluti(
            self.device,
            chi="kokoro",
            costo="~725 ms a battuta invece di ~207: dal vivo si sente",
        )

    def _engine(self):
        if self._k is not None:
            return self._k
        try:
            import onnxruntime as rt
            from kokoro_onnx import Kokoro
        except ImportError as e:  # pragma: no cover - dipende dall'ambiente
            raise RuntimeError(
                "kokoro-onnx non installato: "
                "`.\\.venv\\Scripts\\python.exe -m pip install kokoro-onnx`"
            ) from e

        from core.onnx import verifica_provider

        providers = self._provider_voluto()
        sess = rt.InferenceSession(
            str(model_path(self.pesi, self.download)), providers=providers
        )
        self._provider = verifica_provider(sess, "kokoro", providers)
        self._k = Kokoro.from_session(
            sess, str(voices_path(self.download, self.lingua_base))
        )
        return self._k

    def _stile(self, base_voice: str):
        nome = VOICES.get(base_voice, (None, None))[0]
        if nome is None:
            raise ValueError(
                f"voce Kokoro sconosciuta: {base_voice!r} (note: {sorted(VOICES)})"
            )
        return self._engine().get_voice_style(nome)

    def preload(self, names: list[str]) -> None:
        """Carica in anticipo, **e sintetizza una volta a vuoto**.

        Caricare gli stili non basta e la differenza e' misurata: con il solo
        caricamento la prima battuta costava 745 ms contro i 275 delle
        successive, perche' su CUDA la prima inferenza compila i kernel. Quei
        470 ms sarebbero caduti sulla prima battuta di una partita — cioe' sulla
        sola che nessuno puo' recuperare, visto che dopo di lei non c'e' ancora
        coda da cui rubare tempo.
        """
        scaldato = False
        for n in names:
            try:
                stile = self._stile(n)
            except Exception:
                continue
            if scaldato:
                continue
            try:
                k = self._engine()
                tok = k.tokenizer.tokenize(k.tokenizer.phonemize("Andiamo.", lang=self.lingua))
                if tok:
                    k.sess.run(
                        None,
                        {
                            "input_ids": [[0, *tok, 0]],
                            "style": np.asarray(stile[len(tok)], np.float32),
                            "speed": np.array([self.speed], dtype=np.float32),
                        },
                    )
                    scaldato = True
            except Exception:
                pass

    # -- sintesi -----------------------------------------------------------

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        text = text.strip()
        if not text:
            return Speech(np.zeros(0, np.float32), self.samplerate, voice.voice_id, text=text)

        k = self._engine()
        stile = self._stile(voice.base_voice)
        effective = velocita_effettiva(self.speed, rate, voice.rate)

        t0 = time.perf_counter()
        fonemi = k.tokenizer.phonemize(text, lang=self.lingua)
        pezzi: list[np.ndarray] = []
        for batch in spezza_fonemi(fonemi):
            tok = k.tokenizer.tokenize(batch)
            if not tok:
                continue
            uscita = k.sess.run(
                None,
                {
                    "input_ids": [[0, *tok, 0]],
                    "style": np.asarray(stile[len(tok)], np.float32),
                    "speed": np.array([effective], dtype=np.float32),
                },
            )[0]
            pezzi.append(np.asarray(uscita, dtype=np.float32).reshape(-1))
        total_ms = (time.perf_counter() - t0) * 1000.0

        audio = np.concatenate(pezzi) if pezzi else np.zeros(0, np.float32)
        # Via l'imbottitura prima di ogni altra cosa, dove si sa ancora che
        # cos'e' quel silenzio: a valle ogni stadio lo tratterebbe come parlato.
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
            # `create_stream()` esiste ma e' asyncio, e la pipeline e' sincrona —
            # ma il motivo vero e' che non servirebbe: `Speech.audio` e' un array
            # unico e il mixer programma la battuta intera.
            first_sample_ms=total_ms,
            total_ms=total_ms,
            text=text,
        )
