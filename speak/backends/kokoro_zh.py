"""Il g2p cinese di Kokoro, che non e' espeak per la stessa ragione del giapponese.

E' il gemello di `kokoro_ja.py`, e vale la pena dire **perche' e' stato scritto
dopo**: il cinese, misurato col metro che aveva smascherato il giapponese —
il rapporto fonemi/carattere — sembrava sano. 4,00 contro gli 0,94-1,46 delle
lingue latine, nessun marcatore `(en)`/`(zh)` dentro la stringa, e la
spiegazione era buona: un hanzi e' una sillaba, quindi vale piu' fonemi di una
lettera. Archiviato come «plausibile, mai ascoltato».

**Era sbagliato, e il metro giusto era l'altro.** Il secondo difetto del
giapponese — quello che il rapporto non poteva vedere — era **quanti simboli il
vocabolario di Kokoro butta via**: `Tokenizer.phonemize` filtra l'uscita di
espeak con `filter(lambda p: p in self.vocab, ...)`, in silenzio. Girato su
tutte e otto le lingue, quel numero e' **0,0% per sei** e non lo e' per due:

    lingua   espeak    fonemi crudi   persi dal filtro   cosa si perde
    en, es, fr, hi, it, pt   45-61      0   ( 0,0%)      niente
    **zh**       cmn          69       12   (17,4%)      `1` `2` `5` `-`
    **ja**       ja           27        6   (22,2%)      `a` e l'abbassamento

Quelle cifre sono **i toni del mandarino**. espeak-cmn scrive il tono come un
numero in coda alla sillaba, e nessuno dei numeri sta nei 114 simboli di Kokoro:
il filtro li toglie tutti, e la sillaba resta senza. In una lingua tonale il tono
non e' un accento, e' **quale parola e'**. La prova sta in quattro caratteri che
si scrivono diversi, si dicono diversi e uscivano identici:

    妈  (mamma)     espeak `mˈɑ5`   ->  filtrato  `mˈɑ`
    麻  (canapa)    espeak `mˈɑɜ`   ->  filtrato  `mˈɑɜ`
    马  (cavallo)   espeak `mˈɑ2`   ->  filtrato  `mˈɑ`
    骂  (insultare) espeak `mˈɑ5`   ->  filtrato  `mˈɑ`

Tre parole diverse, un solo suono. Nessun errore, nessun contatore, la suite
verde: si consegnava un doppiaggio che diceva un'altra cosa.

**Con `misaki.zh` i toni ci sono, e sono simboli che Kokoro conosce.** Non
cifre: le frecce `→ ↗ ↓ ↘`, che stanno nel vocabolario. Misurato sulle stesse
quattro parole, `ma→` `ma↗` `ma↓` `ma↘`, e **zero simboli persi** sull'intera
frase di prova. E' la stessa strada che Kokoro usa a monte.

**Il costo e' il dizionario, come per il giapponese.** 159,7 MB, e la parte
grossa non e' il segmentatore: `pypinyin-dict` pesa 112,9 MB e `jieba` 43,1. Non
e' facoltativo — `misaki/zh_frontend.py` importa `large_pinyin`, che e'
esattamente cio' che disambigua i caratteri polifonici, cioe' il motivo per cui
esiste un g2p invece di una tabella.
"""

from __future__ import annotations

from typing import Container

# I pacchetti che servono, e la riga da incollare se non ci sono. Verificato con
# `pip install --dry-run`: tira solo `cn2an`, `jieba`, `ordered-set`, `proces`,
# `pypinyin` e `pypinyin-dict` — **nessun `onnxruntime` e nessun torch**, che qui
# e' la sola cosa che potrebbe fare danno (`onnxruntime` e `onnxruntime-gpu` non
# convivono, e tirarne uno spegnerebbe la CUDA in silenzio). Quindi stanno in
# `requirements.txt` normale.
PACCHETTI: tuple[str, ...] = ("misaki[zh]",)

RIGA_PIP = ".\\.venv\\Scripts\\python.exe -m pip install " + " ".join(PACCHETTI)

# **Quello che misaki puo' produrre e Kokoro non conosce.** Misurato: sulla frase
# di prova e sulle parole tonali, **niente** — le frecce dei toni stanno tutte
# nel vocabolario. Resta un insieme vuoto e non una riga tolta, perche' la
# verifica `kokoro_zh` confronta l'alfabeto di misaki col vocabolario a ogni
# giro: il giorno che una versione nuova aggiunge un simbolo, quel confronto lo
# dice qui invece di lasciarlo buttare in silenzio da `tokenize()`.
FUORI_VOCABOLARIO: frozenset[str] = frozenset()

_g2p = None


def disponibile() -> bool:
    """Se questa macchina puo' dire il cinese, senza sollevare per dirlo.

    Serve a chi deve **scegliere** (il banco, la finestra), non a chi deve
    parlare: chi deve parlare chiama `fonemi` e si prende l'errore con la riga
    da incollare, perche' li' un ripiego muto vuol dire consegnare la battuta
    senza i toni, cioe' dicendo altre parole.
    """
    try:
        _motore()
    except Exception:
        return False
    return True


def _motore():
    """Lo `ZHG2P` di misaki, costruito una volta sola.

    Costruirlo apre il dizionario dei termini polifonici: si paga una volta e
    non trenta volte al secondo.
    """
    global _g2p
    if _g2p is not None:
        return _g2p
    try:
        from misaki import zh
    except ImportError as e:  # pragma: no cover - dipende dall'ambiente
        raise RuntimeError(
            "il cinese di Kokoro vuole misaki: espeak scrive i toni come cifre, "
            "e il vocabolario di Kokoro le butta via — 妈, 马 e 骂 uscivano "
            f"tutte uguali. Manca ({e}). Si installa con:\n    {RIGA_PIP}"
        ) from e
    _g2p = zh.ZHG2P()
    return _g2p


def fonemi(text: str, vocab: Container[str]) -> str:
    """I fonemi di una battuta cinese, gia' filtrati sul vocabolario.

    **Il filtro sta qui e non dentro `tokenize()`**, per la stessa ragione
    scritta in `kokoro_ja.fonemi`: `Tokenizer.tokenize` scarta quello che non
    conosce **senza dirlo**, ed e' quella riga ad aver tolto i toni al cinese e
    le «a» al giapponese. Filtrando qui, la differenza fra cio' che misaki
    produce e cio' che Kokoro accetta e' una tabella fissa
    (`FUORI_VOCABOLARIO`, oggi vuota) che la suite controlla per intero.
    """
    ps, _ = _motore()(text)
    return "".join(ch for ch in ps if ch in vocab).strip()
