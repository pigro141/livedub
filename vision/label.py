"""Chi parla, quando e' il gioco a scriverlo.

Molti giochi mettono il nome di chi parla dentro il sottotitolo — `Franklin: Come
va, bello?` — oppure danno a ogni personaggio un colore. Quando c'e', quel
segnale e' **migliore di qualunque riconoscimento**: e' la verita' dichiarata dal
gioco invece di una somiglianza calcolata su mezzo secondo di audio sporcato dalla
musica.

## Perche' vale la pena, in millisecondi

Oggi per sapere chi parla si aspettano `speaker.decide_after_ms` — **500 ms** — che
sono l'attesa perche' nell'anello ci sia abbastanza parlato da confrontare. In una
catena il cui totale sta fra 670 e 1150 ms, quella e' la voce piu' grossa: misurato
su Kokoro, il riconoscimento costa **il doppio della sintesi**.

Con l'etichetta non si aspetta niente e non si calcola niente: il nome e' li'.
Quindi non e' una comodita' per giochi esotici, e' la strada piu' corta verso una
latenza dimezzata — su qualunque gioco che scriva i nomi.

## Le due forme, e perche' sono configurabili e non indovinate

Non esiste un modo standard di scrivere chi parla, quindi non si indovina: si
**dichiara**. Chi usa il programma sa che gioco sta giocando.

1. **Il prefisso nel testo.** Tre forme pronte (`nome:`, `[nome]`, `nome -`) piu'
   una regex libera per i casi strani. Il nome viene **tolto** dal testo prima di
   parlare: leggere ad alta voce «Franklin due punti come va bello» sarebbe peggio
   che non avere la feature.
2. **Il colore della riga.** Si dichiara un colore per personaggio e si prende il
   piu' vicino, con una soglia oltre la quale non si decide. Serve il colore medio
   dell'inchiostro, che `vision/lines.py` adesso porta fuori: luminanza e
   saturazione da sole non bastano, perche' un blu e un rosso della stessa
   intensita' le hanno identiche — la misura non poteva esprimere la risposta.

## Il guardiano dei falsi positivi, che e' la parte seria

Un prefisso e' una regola sul **testo**, e il testo qui arriva da un OCR che
sbaglia. `Si, era lui: adesso lo so` diventerebbe il personaggio «Si, era lui» —
e ogni falso positivo non e' solo un nome sbagliato: **crea un personaggio**, cioe'
brucia una voce del pool e la toglie a qualcuno che parla davvero.

Da qui tre guardie, in ordine di forza:

- **l'elenco dichiarato** (`names`): se chi configura sa chi sono i personaggi, si
  accetta **solo** quelli. E' la guardia forte, ed e' quella da preferire sempre;
- **la forma**: lunghezza massima, niente punteggiatura di frase dentro il nome,
  e del testo deve restare qualcosa;
- **la costanza**: un nome visto una volta sola in tutta la sessione e' quasi
  sempre un errore di lettura, ma non si puo' sapere alla prima battuta — quindi
  qui non si filtra, si **conta** (`vision.label.seen`), e chi legge i log vede
  subito se l'elenco e' sbagliato.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# **Le forme pronte.** Sono i modi in cui i giochi scrivono chi parla: si sceglie
# la propria con `label.form`, e se il gioco ne usa un'altra c'e' `label.regex`.
# `nome` e `testo` sono i due gruppi che la pipeline usa; una regex
# personalizzata deve dichiararli uguali.
FORME: dict[str, str] = {
    # `Franklin: come va` — di gran lunga la piu' diffusa. Prende anche
    # `FRANKLIN:` e `Franklin :`.
    "nome:": r"^\s*(?P<nome>[^\s:][^:]{0,%(max)d}?)\s*:\s*(?P<testo>\S.*)$",
    # `[Franklin] come va`, `(Franklin) come va`, `<Franklin> come va`.
    "[nome]": r"^\s*[\[(<]\s*(?P<nome>[^\])>]{1,%(max)d})\s*[\])>]\s*(?P<testo>\S.*)$",
    # `Franklin - come va`, con trattino, mezza lineetta o lineetta.
    "nome-": r"^\s*(?P<nome>[^\s\-–—][^\-–—]{0,%(max)d}?)\s*[-–—]\s*(?P<testo>\S.*)$",
    # `- Franklin: come va` — il trattino di dialogo davanti al nome, comune nei
    # sottotitoli tradotti e nei giochi europei.
    "-nome:": r"^\s*[-–—]\s*(?P<nome>[^\s:][^:]{0,%(max)d}?)\s*:\s*(?P<testo>\S.*)$",
    # `Franklin >> come va`, `Franklin » come va`.
    "nome>>": r"^\s*(?P<nome>[^\s>»]{1,%(max)d}?)\s*(?:>>|»|>)\s*(?P<testo>\S.*)$",
    # `FRANKLIN come va` — il nome tutto maiuscolo senza separatore, che alcuni
    # giochi usano. **E' la piu' fragile di tutte** e va usata solo con
    # `label.names` pieno: senza, qualunque parola maiuscola iniziale diventa un
    # personaggio, e una frase che comincia con un'esclamazione ne inventa uno.
    "NOME": r"^\s*(?P<nome>[A-ZÀ-Ý][A-ZÀ-Ý' .]{1,%(max)d}?)\s+(?P<testo>[A-ZÀ-Ýa-zà-ÿ].*)$",
    # `Franklin (arrabbiato): come va` — nome piu' annotazione fra parentesi. La
    # nota si butta: non e' ne' il nome ne' il testo da dire.
    "nome(nota):": r"^\s*(?P<nome>[^\s:(]{1,%(max)d}?)\s*\([^)]*\)\s*:\s*(?P<testo>\S.*)$",
}

# Punteggiatura che dentro un nome non ci sta: se c'e', quello non e' un nome ma
# una frase che per caso conteneva il separatore.
VIETATI = set(".!?;,\"…")


@dataclass(frozen=True, slots=True)
class Etichetta:
    """Il nome trovato e il testo ripulito."""

    nome: str
    testo: str
    da_colore: bool = False


def _normalizza(s: str) -> str:
    """Forma di confronto per i nomi: senza accenti, minuscola, senza spazi.

    La stessa idea dello stabilizzatore dei sottotitoli: l'OCR sbaglia gli spazi
    e gli accenti prima di sbagliare le lettere, e un elenco dichiarato a mano non
    deve fallire perche' l'utente ha scritto «Michael» dove lo schermo dice
    «MICHAEL ».
    """
    piatto = unicodedata.normalize("NFKD", s)
    piatto = "".join(c for c in piatto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", piatto.lower())


class LabelReader:
    """Estrae chi parla dal sottotitolo, come dichiarato in configurazione."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self._re: re.Pattern | None = None
        self._noti: dict[str, str] = {}
        self.visti: dict[str, int] = {}

        if not cfg.enabled:
            return

        if cfg.regex:
            sorgente = cfg.regex
        elif cfg.form in FORME:
            sorgente = FORME[cfg.form] % {"max": max(1, cfg.max_name_len)}
        else:
            raise ValueError(
                f"vision.label.form sconosciuta: {cfg.form!r} "
                f"(note: {', '.join(FORME)}; oppure usare vision.label.regex)"
            )
        self._re = re.compile(sorgente, re.UNICODE)
        if "nome" not in self._re.groupindex or "testo" not in self._re.groupindex:
            raise ValueError(
                "la regex di vision.label deve dichiarare i gruppi (?P<nome>...) "
                "e (?P<testo>...)"
            )
        # L'elenco dichiarato, indicizzato per forma di confronto.
        for n in cfg.names:
            self._noti[_normalizza(n)] = n

    # -- il prefisso nel testo --------------------------------------------

    def dal_testo(self, testo: str) -> Etichetta | None:
        """Il nome scritto dentro il sottotitolo, o `None` se non c'e'.

        Restituisce `None` anche quando *sembra* esserci ma non supera le
        guardie: fra non riconoscere un nome e inventarne uno, il secondo costa
        molto di piu' — crea un personaggio e gli assegna una voce del pool.
        """
        if self._re is None or not testo:
            return None
        m = self._re.match(testo)
        if m is None:
            return None
        nome = (m.group("nome") or "").strip()
        resto = (m.group("testo") or "").strip()
        if not nome or not resto:
            return None
        if len(nome) > self.cfg.max_name_len:
            return None
        if any(ch in VIETATI for ch in nome):
            return None
        if not any(ch.isalpha() for ch in nome):
            return None

        chiave = _normalizza(nome)
        if not chiave:
            return None
        if self._noti:
            # **La guardia forte**: se l'elenco c'e', vale solo quello. Un nome
            # fuori elenco non e' un personaggio nuovo, e' un OCR che ha letto
            # male — e trattarlo da personaggio brucia una voce.
            canonico = self._noti.get(chiave)
            if canonico is None:
                return None
            nome = canonico
        elif self.cfg.require_names:
            return None

        self.visti[nome] = self.visti.get(nome, 0) + 1
        return Etichetta(nome=nome, testo=resto)

    # -- il colore della riga ---------------------------------------------

    def dal_colore(self, rgb: tuple[float, float, float]) -> str | None:
        """Il personaggio il cui colore dichiarato e' piu' vicino, o `None`.

        La soglia non e' un dettaglio: senza, il piu' vicino c'e' **sempre**, e
        un sottotitolo bianco finirebbe attribuito al personaggio meno lontano
        dal bianco. Oltre `color_tolerance` non si decide, che e' la stessa
        regola di `name_min_score` — sotto la soglia si dice "non lo so" invece
        di dire una cosa a caso.
        """
        if not self.cfg.colors:
            return None
        migliore, distanza = None, float("inf")
        for nome, colore in self.cfg.colors.items():
            c = _colore(colore)
            if c is None:
                continue
            d = sum((a - b) ** 2 for a, b in zip(rgb, c)) ** 0.5
            if d < distanza:
                migliore, distanza = nome, d
        if migliore is None or distanza > self.cfg.color_tolerance:
            return None
        self.visti[migliore] = self.visti.get(migliore, 0) + 1
        return migliore

    def leggi(self, testo: str, rgb: tuple[float, float, float] | None = None) -> Etichetta | None:
        """Prima il testo, poi il colore. Il testo vince perche' porta un nome.

        Il colore dice *quale* personaggio fra quelli dichiarati; il prefisso dice
        anche come si chiama, e va tolto da cio' che si pronuncia. Se ci sono tutti
        e due, il prefisso e' piu' informativo.
        """
        e = self.dal_testo(testo)
        if e is not None:
            return e
        if rgb is not None:
            nome = self.dal_colore(rgb)
            if nome is not None:
                return Etichetta(nome=nome, testo=testo, da_colore=True)
        return None


def _colore(v) -> tuple[float, float, float] | None:
    """Accetta `#rrggbb`, `rrggbb` o una terna. `None` se non si capisce."""
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return (float(v[0]), float(v[1]), float(v[2]))
    if isinstance(v, str):
        s = v.strip().lstrip("#")
        if len(s) == 6:
            try:
                return tuple(float(int(s[i : i + 2], 16)) for i in (0, 2, 4))  # type: ignore[return-value]
            except ValueError:
                return None
    return None
