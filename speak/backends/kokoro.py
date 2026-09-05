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


# **Le lingue che il catalogo ha e che questo motore non sa dire.** E' vuoto, e
# lo e' diventato: fino al 5 settembre 2026 conteneva `ja`, perche' `kokoro_onnx`
# fonemizza tutto con espeak-ng ed espeak il giapponese lo sbaglia in due modi
# che non sollevano mai — i kanji li **nomina** («Chinese letter» per ogni
# ideogramma, 8,75 fonemi per carattere contro gli 0,94-1,46 delle altre) e sulle
# sole kana perde **tutte le «a»**, perche' le scrive con simboli che il
# vocabolario di Kokoro non ha e il tokenizzatore butta in silenzio.
#
# Adesso il giapponese non passa piu' da espeak: `speak/backends/kokoro_ja.py` lo
# fonemizza con misaki (fugashi + UniDic), che e' la strada di Kokoro a monte. Le
# due misure e il controllo contro un'implementazione indipendente stanno tutti
# in quel file.
#
# **La tabella resta, e vuota vale piu' che piena.** Dice che oggi non c'e'
# nessuna lingua dichiarata dal catalogo che questo motore non sappia dire; e la
# guardia in `__init__` che la legge resta l'unico posto in cui una lingua nuova
# in quelle condizioni si dichiara invece di consegnare un doppiaggio fatto con
# la fonemizzazione sbagliata.
SENZA_FONEMI: frozenset[str] = frozenset()

# **Le lingue che non si fonemizzano con espeak, e chi le fonemizza al posto
# suo.** Il valore e' una funzione `(testo, vocabolario) -> fonemi`; il modulo si
# importa **pigramente** dentro `_fonemi`, perche' `misaki` e' un requisito di
# questo motore e non di chi importa questo file per leggerne i cataloghi — il
# selftest costruisce `KokoroTts` senza modelli e senza voler tirare dentro un
# dizionario da 249 MB.
G2P_ESTERNO: dict[str, str] = {
    "ja": "speak.backends.kokoro_ja",
    # **Il cinese e' arrivato dopo, e la ragione per cui era sfuggito vale piu'
    # della riga.** Col metro che aveva preso il giapponese — il rapporto
    # fonemi/carattere — il cinese risultava sano (4,00, nessuna commutazione di
    # lingua) e la spiegazione era buona: un hanzi e' una sillaba. Col metro
    # giusto, cioe' **quanti simboli il vocabolario butta via**, perde il 17,4%
    # e quel che perde sono le cifre dei toni: `妈`, `马` e `骂` uscivano tutte
    # come `mˈɑ`. Si veda `speak/backends/kokoro_zh.py`.
    "zh": "speak.backends.kokoro_zh",
}

# La battuta con cui si scalda il modello, per le lingue che non si scrivono in
# alfabeto latino: `preload` la fa passare dal g2p vero, e dare «Andiamo.» a
# misaki vorrebbe dire scaldare su una stringa che quel g2p non incontrera' mai.
FRASE_SCALDATA: dict[str, str] = {"ja": "行こう。", "zh": "我们走吧。"}


def _per_lingua() -> dict[str, tuple[str, ...]]:
    fuori: dict[str, list[str]] = {}
    for chiave, (nome, _g) in VOICES.items():
        lingua = _PREFISSI[nome[0]][0]
        if lingua in SENZA_FONEMI:
            continue
        fuori.setdefault(lingua, []).append(chiave)
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
# E chi non ha regole utilizzabili non compare qui nemmeno: una lingua con la
# fonemizzazione pronta e nessuna voce era il difetto scritto qui sopra, e la
# stessa tabella girata dall'altra parte — una voce con una fonemizzazione che
# legge un'altra cosa — era il giapponese, che adesso ha la sua.
#
# **Il giapponese non e' qui, e la sua assenza e' l'unica cosa che impedisce di
# chiederlo a espeak per sbaglio.** Questa tabella dice «con che codice espeak si
# fonemizza questa lingua», e per il giapponese la risposta non e' un codice
# espeak: e' `G2P_ESTERNO`. Tenercelo con dentro `"ja"` sarebbe stato un campo
# vero, letto, e sbagliato — che e' esattamente com'era prima, quando
# `SENZA_FONEMI` diceva «non lo so fare» e la riga sotto lo chiedeva lo stesso a
# espeak. Insieme le due tabelle **partizionano** le lingue delle voci, e la
# verifica `kokoro_ja` lo pretende: nessuna in tutte e due, nessuna in nessuna.
FONEMI_LINGUA: dict[str, str] = {
    _PREFISSI[n[0]][0]: _PREFISSI[n[0]][1] for n in reversed(_NOMI)
    if _PREFISSI[n[0]][0] not in SENZA_FONEMI
    and _PREFISSI[n[0]][0] not in G2P_ESTERNO
}

# Quanti fonemi il modello accetta in un colpo. Le battute vere di GTA V ne
# fanno un'ottantina, quindi il limite non si tocca mai — ma una battuta troncata
# in silenzio sarebbe una frase mangiata senza nessun segnale, quindi lo
# spezzettamento esiste lo stesso.
#
# **509 e non 510, e i due numeri non misurano la stessa cosa.** 510 e' la
# lunghezza massima della stringa di fonemi che `kokoro_onnx` dichiara; ma il
# vettore di stile si indicizza con `len(tok)` e ha **510 righe, cioe' 0..509**.
# Un pezzo da esattamente 510 fonemi da' 510 token e `stile[510]` e' fuori —
# misurato dal vivo in giapponese: `IndexError: index 510 is out of bounds for
# axis 0 with size 510`, con la catena ferma e la finestra in guasto. Il limite
# vero e' quello dell'indice, non quello dichiarato.
MAX_FONEMI = 509

# La punteggiatura su cui si spezza. **Non solo quella ASCII**: in giapponese la
# frase finisce con `。` e la virgola e' `、`, quindi con il solo `.` una battuta
# lunga non aveva **nessun** punto dove spezzarsi — un pezzo unico tagliato duro
# al limite, che e' esattamente come si arrivava all'IndexError. Ci sono anche
# l'arabo (`؟` `،`), il greco (`;` come punto interrogativo) e le forme a tutta
# larghezza, perche' la lingua d'arrivo adesso puo' essere una qualunque delle
# cinquantadue.
FINE_FRASE = "。．！？；!?;⁇⁈⁉‼？！"
PAUSA = "、，,،؛"

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
#
# ---------------------------------------------------------------------------
#
# **Spagnolo, francese e portoghese: misurati, e solo uno e' entrato.**
#
# Misura del 3 settembre 2026 sulle battute vere dei sottotitoli ufficiali del
# trailer di GTA VI (due tratti, 16-20 battute per lingua, 564-688 caratteri di
# parlato), una sintesi per battuta a `speed = 1,0`, durata presa **dopo**
# `taglia_silenzio`, mediana per voce:
#
#     lingua  voce             sesso   car/s   f0 mediana
#     it      kokoro-nicola      m     13,01    84,5 Hz
#     it      kokoro-sara        f     13,37   288,2 Hz
#     es      kokoro-es_alex     m     13,69   150,0 Hz
#     es      kokoro-es_santa    m     13,23   119,2 Hz
#     es      kokoro-es_dora     f     13,85   200,1 Hz
#     fr      kokoro-siwis       f     14,39   265,7 Hz
#     pt      kokoro-pt_alex     m     13,07   154,7 Hz
#     pt      kokoro-pt_santa    m     12,40   123,9 Hz
#     pt      kokoro-pt_dora     f     13,38   207,0 Hz
#
# **La misura si convalida da sola**: l'italiano, rifatto su sedici battute che
# non c'entrano niente con le ventiquattro da cui usci' il 12,93 archiviato,
# torna **13,01** — lo 0,6% di scarto. Senza quel caso nullo gli altri tre
# numeri sarebbero tre numeri; con quello sono tre misure.
#
# **La soglia era dichiarata prima della misura**, ed e' il 10%: la distanza che
# questo progetto ha gia' giudicato degna di due righe diverse (12,9 contro
# 14,37 = 11,4%). Il verdetto, contro il ripiego di 12,9:
#
#     es   la voce piu' lenta fa 13,23   +2,6%   dentro, non entra
#     pt   la voce piu' lenta fa 12,40   -3,9%   dentro, non entra
#     fr   l'unica voce fa      14,39   +11,6%   fuori, **entra**
#
# Spagnolo e portoghese **sono misurati e deliberatamente non scritti**: i loro
# numeri stanno a cavallo del ripiego, e riscriverne uno quasi uguale vorrebbe
# dire dichiarare una precisione che questa misura non ha. Sta scritto qui
# perche' «non misurato» e «misurato e uguale» sono due cose diverse, e la
# seconda non si ricerca.
#
# **E la voce femminile non ha bisogno di un meccanismo suo.** Era la seconda
# ipotesi, con la stessa soglia: femminile contro maschile fa **+2,7% (it),
# +2,9% (es), +5,1% (pt)** — un verso costante (la femminile e' sempre la piu'
# svelta) e un'ampiezza che non arriva a meta' della soglia. Quindi
# `chars_per_second` resta una proprieta' del **motore piu' la lingua** e non
# della singola voce, e `speak/pool.py` non guadagna un campo. Il francese non
# entra in questo confronto: Kokoro ne ha **una sola** voce ed e' femminile,
# quindi il suo 14,39 e' il passo di quella lingua per costruzione — non c'e'
# una maschile da cui distinguerlo, e dire «il francese e' piu' svelto» sarebbe
# dire una cosa che questa misura non puo' separare da «siwis e' svelta».
#
# ---------------------------------------------------------------------------
#
# **E il giapponese entra con il numero piu' lontano di tutti, che era
# prevedibile e va comunque misurato.** 12 frasi vere, le due voci giapponesi,
# `speed = 1,0`, durata **dopo** `taglia_silenzio`, fonemi da misaki:
#
#     lingua  voce               sesso   car/s (mediana)
#     ja      kokoro-ja_alpha      f      5,95
#     ja      kokoro-kumo          m      5,91
#
# Si dichiara **5,9**, il piu' basso dei due: una previsione corta si paga piu'
# cara di una lunga. Le due voci distano lo 0,7%, cioe' molto sotto la soglia del
# 10% con cui si e' deciso il francese — il passo resta una proprieta' del motore
# piu' la lingua, non della voce, esattamente come per le altre.
#
# **Non e' un motore lento, e' una scrittura densa**: `spoken_length()` conta i
# caratteri, e un ideogramma vale due o tre sillabe. E' la stessa ragione per cui
# nella tabella di SuperTonic in fondo stanno giapponese, coreano, hindi e arabo.
# Il caso nullo che rende questi numeri una misura e non due cifre: **rifacendo
# l'italiano** con lo stesso codice e lo stesso protocollo torna 13,38 contro i
# 12,93 e 13,01 archiviati, cioe' il 3,5%.
#
# La conseguenza sulla catena e' dichiarata: con 5,9 car/s una battuta giapponese
# occupa **piu' del doppio** del tempo di scena della stessa battuta italiana, e
# il budget si stringera' molto piu' spesso. E' il numero vero — usare i 12,9
# dell'italiano sarebbe la sesta volta della stessa unita' sbagliata, e stavolta
# con un fattore due invece che con un 11%.
#
# **E le altre due scritture dense stavano ancora sull'italiano.** Kokoro parla
# otto lingue e questa tabella ne aveva quattro: spagnolo e portoghese sono
# **misurati e deliberatamente non scritti** (+2,6% e -3,9%, sotto la soglia del
# 10%), ma cinese e hindi no — prendevano i 12,9 dell'italiano, cioe' due volte
# e mezzo e due volte troppo, nel verso che fa comprimere. Sono le stesse due
# scritture che in fondo alla tabella di SuperTonic stanno a 6,3 e 8,4.
#
# **Misurate come le altre, con le due correzioni che il giro ha imposto**
# (`tools/censisci_lingue.py --sintesi`, 2026-09-05). Prima: **tutte le voci del
# pool**, non la prima — su Piper due voci della stessa lingua distano l'ottanta
# per cento, e qui il cinese va da 4,15 a 5,43 su sei voci. Seconda: la frase di
# `speak/frasi.py` corre piu' delle battute vere, e di quanto si e' misurato
# invece di stimarlo — rifacendo l'italiano nei due modi con le stesse voci,
# **15,26 sulla frase contro 13,34 su dodici battute di scena, +14,4%**. Quindi
# le due righe nuove sono `mediana(frase) / 1,144`, sulla stessa scala del 12,9.
#
# Il controllo che le rende una misura: quel 13,34 e' l'ancora archiviata
# (12,9) riprodotta al **3,4%**. E resta una frase sola per lingua, come le
# trenta di SuperTonic e non come il francese (sedici-venti battute vere): un
# ordine di grandezza, non una taratura.
PASSO_LINGUA = {
    "it": 12.9,
    "en": 14.37,
    "fr": 14.39,
    "hi": 5.28,   # 4 voci, frase 6.04 (5.92-7.48)
    "ja": 5.9,
    "zh": 4.21,   # 6 voci, frase 4.81 (4.15-5.43)
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

    def a_pezzi(testo: str, segni: str) -> list[str]:
        for c in segni[1:]:
            testo = testo.replace(c, segni[0])
        pezzi: list[str] = []
        corrente = ""
        for parte in testo.split(segni[0]):
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
        return pezzi

    pezzi = a_pezzi(fonemi, "." + FINE_FRASE)
    # **Chi sfora ancora si spezza sulle pause, non si taglia.** Una battuta
    # senza fine frase — o in una lingua che la scrive in un modo che qui non e'
    # elencato — arrivava intera al taglio duro, cioe' perdeva la seconda meta'
    # in silenzio. La virgola e' un punto di respiro peggiore del punto, ed e'
    # comunque meglio che in mezzo a una parola.
    fine: list[str] = []
    for pezzo in pezzi:
        fine.extend(a_pezzi(pezzo, "," + PAUSA) if len(pezzo) > limite else [pezzo])
    # E se anche cosi' non basta (nessun segno affatto), si taglia a finestre —
    # **non si tiene solo la prima**. Era `p[:limite]`, cioe' la coda sparita in
    # silenzio: la stessa mezza frase detta come se fosse tutta contro cui
    # questo spezzettamento esiste. Tagliare male una parola si sente; perdere
    # meta' battuta no.
    duro: list[str] = []
    for pezzo in fine:
        duro.extend(pezzo[i:i + limite] for i in range(0, len(pezzo), limite))
    return [p for p in duro if p]


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
        # **E chi non ha regole si ferma qui, invece di ripiegare su se stesso.**
        # Il ripiego era `lingua`, cioe' il codice chiesto: togliere `ja` da
        # `FONEMI_LINGUA` non lo toglieva affatto a espeak — la tabella diceva
        # «non lo so fare» e la riga sotto glielo chiedeva lo stesso. Una cura
        # piu' stretta del difetto, con la suite verde; e per prenderla non basta
        # chiedersi «il difetto e' sparito?», ci vuole «cosa faceva prima che
        # adesso non fa piu'?». Solleva invece di ripiegare, perche' un ripiego
        # muto qui vuol dire consegnare un doppiaggio fatto con la
        # fonemizzazione sbagliata, e con i contatori verdi.
        if self.lingua_base in SENZA_FONEMI:
            raise ValueError(
                f"kokoro non sa dire «{self.lingua_base}»: espeak i suoi segni "
                "li nomina invece di leggerli (si veda SENZA_FONEMI). "
                "Il motore va scelto con core.motore.motore_per_lingua.")
        self.lingua = FONEMI_LINGUA.get(self.lingua_base, lingua)
        self.download = download
        self._k = None
        self._provider = "?"
        self._g2p = None

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

    # -- fonemizzazione ----------------------------------------------------

    def _fonemi(self, text: str) -> str:
        """I fonemi della battuta, da espeak o da chi lo sostituisce.

        **Un posto solo**, perche' la strada del giapponese e quella delle altre
        otto lingue devono restare la stessa strada: e' gia' costato due volte,
        in questo progetto, aprire un ramo parallelo che poi non ereditava le
        cure dell'altro (il ricampionamento e il taglio del silenzio, nella
        stessa sessione). Qui a valle ci sono `spezza_fonemi`, il tetto
        `MAX_FONEMI` e la guardia sull'indice dello stile, e le prendono tutte e
        due allo stesso modo.

        E chi non ha un g2p **solleva**, invece di ripiegare su espeak: un
        ripiego muto qui vuol dire consegnare una battuta fonemizzata con le
        regole di un'altra lingua, con l'audio che esce e i contatori verdi.
        """
        modulo = G2P_ESTERNO.get(self.lingua_base)
        if modulo is None:
            return self._engine().tokenizer.phonemize(text, lang=self.lingua)
        if self._g2p is None:
            from importlib import import_module

            self._g2p = import_module(modulo)
        return self._g2p.fonemi(text, self._engine().tokenizer.vocab)

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
                # **La frase di prova e' nella scrittura di questa lingua**, e
                # non e' un vezzo: scaldare con «Andiamo.» in giapponese
                # scalderebbe i kernel giusti passando pero' per un g2p che poi
                # non e' quello del vivo. Qui la strada e' `_fonemi`, cioe'
                # quella vera, e la prima battuta paga quello che pagherebbe.
                tok = k.tokenizer.tokenize(self._fonemi(FRASE_SCALDATA.get(
                    self.lingua_base, "Andiamo.")))
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
        fonemi = self._fonemi(text)
        pezzi: list[np.ndarray] = []
        for batch in spezza_fonemi(fonemi):
            tok = k.tokenizer.tokenize(batch)
            if not tok:
                continue
            # **La guardia sta dove sta l'indice.** `spezza_fonemi` conta i
            # *fonemi* e qui si indicizza con i *token*: sono la stessa cosa
            # finche' il tokenizzatore non decide altrimenti, e il giorno che
            # non lo sono l'errore esce dentro `sess.run` con un numero e
            # nessun nome. Una riga che non entra mai costa meno di una
            # sessione persa.
            if len(tok) >= len(stile):
                tok = tok[:len(stile) - 1]
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
