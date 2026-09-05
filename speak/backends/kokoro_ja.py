"""Il g2p giapponese di Kokoro, che non e' espeak e non poteva esserlo.

`kokoro_onnx` fonemizza **tutto** con espeak-ng, e sul giapponese espeak sbaglia
in due modi indipendenti — nessuno dei due solleva, tutti e due misurati qui.

**Uno: i kanji non li legge, li nomina.** Su «こんにちは、今すぐここから出るべき
です。» il carattere `今` esce come `(en)tʃˈaɪniːz(ja)lˈetə`, cioe' il modello
pronuncia la frase inglese «Chinese letter» per ogni ideogramma. Il numero che
lo prende senza orecchio e' il rapporto fonemi/carattere:

    lingua                       espeak      car   fonemi   rapporto   commuta
    en, es, fr, it, pt      en-us..pt-br   39-47    44-47   0,94-1,21     no
    hi                                hi      41       60        1,46     no
    zh                               cmn      14       56        4,00     no
    **ja**                          **ja**    20      175    **8,75**   **si'**

**Due: anche senza un solo kanji, il giapponese perdeva tutte le «a».** Questo
non si vedeva nel rapporto ed e' peggio del primo, perche' colpisce anche il
testo che espeak dice di saper leggere. espeak-ja scrive /a/ come `ä` (vocale
centrale) piu' l'abbassamento `◌̞`, e **nessuno dei due sta nei 114 simboli del
vocabolario di Kokoro**: `Tokenizer.phonemize` filtra l'uscita di espeak con
`filter(lambda p: p in self.vocab, ...)` e li **butta via in silenzio**.
Misurato su sole kana, dove espeak non ha nessun ideogramma da nominare:

    ありがとう           grezzo  ˌäɽiɡätˈo̞ɯᵝ   ->  filtrato  ˌɽiɡtˈoɯᵝ
    こんにちは           grezzo  kˌo̞nnitɕˈihä  ->  filtrato  kˌonnitɕˈih
    わたしはがくせいです  grezzo  wˌätäɕˌihäɡ…  ->  filtrato  wˌtɕˌihɡ…

cioe' il 6,9% dei simboli buttati, e sono **tutte le «a» della lingua**. Nelle
altre sette lingue quel filtro non toglie niente (0,0%; il francese perde un
trattino). E' la forma di difetto che questo progetto insegue da sempre: la
sintesi non solleva, l'audio esce, i contatori restano verdi.

**La strada e' quella di Kokoro a monte: misaki.** `misaki.ja.JAG2P` nasce con
`version='cutlet'`, e quel ramo non tocca espeak — analizza la frase con fugashi
sul dizionario UniDic e mappa le kana in IPA. Qui si importa direttamente
`misaki.cutlet`, **non** `misaki.ja`, e per una ragione precisa: `misaki/ja.py`
fa `import pyopenjtalk` in cima al modulo, e `pyopenjtalk` su Windows non ha una
ruota — pip prova a compilarlo e muore su `CMAKE_C_COMPILER not set`. Il ramo che
serve non lo usa; importarlo lo pretenderebbe lo stesso. La verifica `kokoro_ja`
controlla che `misaki.cutlet` continui a non tirarsi dietro pyopenjtalk, perche'
il giorno che lo facesse questo file smetterebbe di importarsi del tutto.

**Il risultato, misurato con la stessa unita' delle altre lingue** (12 frasi,
`spoken_length()` diviso la durata **dopo** `taglia_silenzio`, `speed = 1,0`):

    rapporto fonemi/carattere   mediana 2,48   (era 8,75)   marcatori (en)/(ja): nessuno
    car/s  jf_alpha  mediana 5,95     jm_kumo  mediana 5,91

**E la misura si convalida da sola**: rifacendo l'italiano con lo stesso codice e
lo stesso protocollo torna 13,38 car/s contro i 12,93 e 13,01 archiviati — il
3,5%, cioe' lo strumento misura la stessa cosa che misurava allora.

**Il controllo che conta piu' del rapporto** e' pero' un altro, ed e' contro
un'implementazione **indipendente**: sulle sole kana, dove espeak non ha kanji da
nominare, misaki e espeak devono dire la stessa cosa. Non la dicono, e ha ragione
misaki — `こんにちは` -> `koɲɲiʨiβa` contro `kˌonnitɕˈih`, con la `は` finale letta
**come particella** (`wa`), che vuole l'analisi morfologica e che espeak non puo'
fare. Il rapporto dice «non sta piu' nominando gli ideogrammi»; solo questo
confronto dice «e cio' che dice e' giusto».

**Il costo e' tutto nel dizionario e nient'affatto nel giro.** `unidic-lite` pesa
249 MB su disco (`sys.dic` 179 + `matrix.bin` 68); l'analisi di una battuta costa
**0,073 ms**, contro i ~200 ms di sintesi di Kokoro. Non e' un costo di catena:
e' un costo di pacchetto, ed e' dichiarato in `livedub.spec`.
"""

from __future__ import annotations

from typing import Container

# I pacchetti che servono, e la riga da incollare se non ci sono. Nessuno di
# loro tira `onnxruntime` — verificato con `pip install --dry-run --report`, che
# aggiunge solo `addict` e `regex` — quindi stanno in `requirements.txt` normale
# e non fra quelli da installare con `--no-deps`.
PACCHETTI: tuple[str, ...] = ("misaki", "fugashi", "unidic-lite", "jaconv", "mojimoji")

RIGA_PIP = ".\\.venv\\Scripts\\python.exe -m pip install " + " ".join(PACCHETTI)

# **I due soli simboli che misaki puo' produrre e Kokoro non conosce**, ed e' il
# numero che rende innocuo il filtro qui sotto. Sono le parentesi giapponesi
# `【` `】` mappate su `[` `]`: punteggiatura, non fonemi. Tutto il resto
# dell'alfabeto di `HEPBURN` sta nel vocabolario, e che continui a starci lo dice
# la verifica `kokoro_ja` — non questo commento, che invecchierebbe da solo alla
# prima versione nuova di misaki.
FUORI_VOCABOLARIO = frozenset("[]")

_cutlet = None


def disponibile() -> bool:
    """Se questa macchina puo' dire il giapponese, senza sollevare per dirlo.

    Serve a chi deve **scegliere** (il banco, la finestra), non a chi deve
    parlare: chi deve parlare chiama `fonemi` e si prende l'errore con la riga
    da incollare, perche' li' un ripiego muto vorrebbe dire consegnare la
    battuta con la fonemizzazione sbagliata.
    """
    try:
        _motore()
    except Exception:
        return False
    return True


def _motore():
    """Il `Cutlet` di misaki, costruito una volta sola.

    Costa 2 ms (il dizionario si apre in memoria mappata) e non 249 MB di
    lettura, ma costruirlo a ogni battuta sarebbe comunque un costo pagato
    trenta volte al secondo per niente.
    """
    global _cutlet
    if _cutlet is not None:
        return _cutlet
    try:
        # **`misaki.cutlet` e non `misaki.ja`**: si veda la testata. L'altro
        # modulo importa `pyopenjtalk`, che su Windows non ha una ruota.
        from misaki.cutlet import Cutlet
    except ImportError as e:  # pragma: no cover - dipende dall'ambiente
        raise RuntimeError(
            "il giapponese di Kokoro vuole misaki: espeak i kanji li nomina "
            "invece di leggerli, e gli toglie anche tutte le «a». "
            f"Manca ({e}). Si installa con:\n    {RIGA_PIP}"
        ) from e
    _cutlet = Cutlet()
    return _cutlet


def fonemi(text: str, vocab: Container[str]) -> str:
    """I fonemi di una battuta giapponese, gia' filtrati sul vocabolario.

    **Il filtro sta qui e non dentro `tokenize()`**, ed e' la differenza fra un
    difetto e una scelta: `Tokenizer.tokenize` fa
    `[i for i in map(self.vocab.get, phonemes) if i is not None]`, cioe' butta
    quello che non conosce **senza dirlo**. La stessa riga che ha tolto tutte le
    «a» al giapponese di espeak toglierebbe qui qualunque simbolo nuovo di una
    versione futura di misaki, e non lo saprebbe nessuno. Filtrando prima, il
    confronto fra cio' che misaki produce e cio' che Kokoro accetta e' una
    tabella fissa (`FUORI_VOCABOLARIO`) che la suite controlla per intero.

    E' la stessa forma dell'uscita di `Tokenizer.phonemize`, che il filtro lo
    applica anche lei: cosi' la strada giapponese e le altre otto consegnano al
    tokenizzatore la stessa specie di stringa.
    """
    ps, _ = _motore()(text)
    return "".join(ch for ch in ps if ch in vocab).strip()
