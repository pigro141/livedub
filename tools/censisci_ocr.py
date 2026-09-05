"""Quali **scritture** sanno leggere i riconoscitori montati su questa macchina.

`translate.source` accetta una qualunque delle 133 lingue di Google, e nessuno
dei due backend OCR dichiara che cosa sa leggere. Il modello di serie di
RapidOCR e' addestrato su **cinese e inglese**; OneOCR e' quello dello Strumento
di cattura di Windows. Chi mette `translate.source=ru` non prende nessun errore:
prende una sessione in cui non si legge niente, e sembra un difetto della ROI.

**Qui si misura, non si deduce.** Si disegna una riga di sottotitolo finta in
dieci scritture, la si passa ai backend disponibili e si conta il CER. Da qui
esce la tabella di `vision/scritture.py`, che e' cio' che il menu legge.

    .\\.venv\\Scripts\\python.exe -m tools.censisci_ocr                  # la tabella
    .\\.venv\\Scripts\\python.exe -m tools.censisci_ocr --backend oneocr # uno solo
    .\\.venv\\Scripts\\python.exe -m tools.censisci_ocr --png runs\\scritture

## Il disegnatore e' Qt, e non e' un dettaglio

PIL qui **non puo' esprimere la risposta** per quattro scritture su dieci: la
Pillow installata non ha libraqm (`PIL.features.check("raqm")` -> `False`),
quindi non compone — l'arabo esce in forme isolate e da sinistra a destra,
l'ebraico in ordine rovesciato, devanagari e thai senza riordino ne' segni
attaccati. Misurato: la stessa riga araba occupa **266 px disegnata da Qt e 311
da PIL**, cioe' il 17% in piu', che e' la larghezza che la legatura toglie —
mentre la riga **latina**, dove non c'e' niente da comporre, sta a 571 contro
576, cioe' l'1%. E' il caso nullo: senza, il 17% sarebbe solo «due disegnatori
diversi». Un CER alto letto sul disegno di PIL direbbe «l'OCR non sa l'arabo»
quando la frase giusta e' «nessuno sa che cosa sia quel disegno».

Qt compone con HarfBuzz, quindi si disegna con Qt e PIL resta come ripiego
**dichiarato**: se Qt non c'e', le quattro scritture composte restano *non
misurate* invece di prendere un numero falso.

## Il controllo positivo, che dice se la misura funziona

La riga latina deve uscire con un CER vicino a zero. Se non esce, il difetto e'
nel banco — nel disegno, nel ritaglio, nel modo in cui si chiama il backend — e
tutti gli altri numeri non vogliono dire niente. Si stampa per prima apposta.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Prova:
    """Una scrittura, e la riga con cui si prova."""

    scrittura: str      # il nome nel sistema, come in `vision/scritture.py`
    lingua: str         # un codice Google che la usa, per il messaggio del menu
    testo: str
    qt: str             # famiglia di caratteri per Qt
    pil: str            # file in C:\Windows\Fonts per il ripiego
    composta: bool      # serve la composizione (legature, riordino, RTL)?


# Le righe sono **frasi da sottotitolo**, non pangrammi: la domanda e' se una
# battuta di gioco si legge, e una sequenza di lettere rare risponderebbe a
# un'altra domanda. Sono tutte la stessa frase, cosi' la lunghezza non e' una
# variabile in piu' fra una scrittura e l'altra.
PROVE: tuple[Prova, ...] = (
    Prova("latina", "it", "Non ho tempo per queste cose.",
          "Arial", "arialbd.ttf", False),
    Prova("cirillica", "ru", "У меня нет времени на это.",
          "Arial", "arialbd.ttf", False),
    Prova("greca", "el", "Δεν έχω χρόνο για αυτά.",
          "Arial", "arialbd.ttf", False),
    Prova("giapponese", "ja", "こんなことをしている暇はない。",
          "Yu Gothic", "YuGothB.ttc", False),
    Prova("cinese", "zh-CN", "我没有时间做这些事。",
          "Microsoft YaHei", "msyhbd.ttc", False),
    Prova("coreana", "ko", "이런 일을 할 시간이 없어.",
          "Malgun Gothic", "malgunbd.ttf", False),
    Prova("araba", "ar", "ليس لدي وقت لهذا.",
          "Arial", "arialbd.ttf", True),
    Prova("ebraica", "iw", "אין לי זמן לזה.",
          "Arial", "arialbd.ttf", True),
    Prova("devanagari", "hi", "मेरे पास समय नहीं है।",
          "Nirmala UI", "Nirmala.ttc", True),
    Prova("thai", "th", "ฉันไม่มีเวลาสำหรับเรื่องนี้",
          "Leelawadee UI", "LEELAWDB.TTF", True),
)


# ------------------------------------------------------------ il disegno --


def _app_qt():
    """Il `QGuiApplication` che serve a dipingere. Uno solo per processo."""
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


def disegna_qt(p: Prova, punti: int = 36) -> np.ndarray:
    """La riga, bianca su nero, composta da HarfBuzz.

    Bianco su nero e non il contrario perche' e' cosi' che arriva ai backend
    nella catena vera: `lines.classify_lines` consegna una maschera in cui
    l'inchiostro e' acceso.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

    _app_qt()
    f = QFont(p.qt)
    f.setPixelSize(punti)
    f.setBold(True)
    fm = QFontMetrics(f)
    larghezza = fm.boundingRect(p.testo).width() + 40
    altezza = fm.height() + 20
    img = QImage(larghezza, altezza, QImage.Format_RGB888)
    img.fill(QColor(0, 0, 0))
    pit = QPainter(img)
    pit.setFont(f)
    pit.setPen(QColor(255, 255, 255))
    pit.drawText(img.rect(), Qt.AlignCenter, p.testo)
    pit.end()
    riga = img.bytesPerLine()
    a = np.frombuffer(img.constBits(), np.uint8)
    a = a.reshape(altezza, riga)[:, : larghezza * 3].reshape(altezza, larghezza, 3)
    return a.copy()


def disegna_pil(p: Prova, punti: int = 36) -> np.ndarray:
    """Il ripiego. **Non compone**: si usa solo dove non serve comporre."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(f"C:\\Windows\\Fonts\\{p.pil}", punti)
    x0, y0, x1, y1 = font.getbbox(p.testo)
    img = Image.new("RGB", (x1 - x0 + 40, y1 - y0 + 24), (0, 0, 0))
    ImageDraw.Draw(img).text((20 - x0, 12 - y0), p.testo, font=font, fill=(255, 255, 255))
    return np.asarray(img)


def controllo_composizione() -> str:
    """Quanto largo viene l'arabo coi due disegnatori, **col suo caso nullo**.

    Se i due numeri coincidessero vorrebbe dire che nemmeno Qt sta componendo, e
    allora le quattro scritture composte andrebbero dichiarate non misurate anche
    con Qt. Ma un numero solo non basta: due disegnatori diversi danno larghezze
    diverse comunque — carattere di ripiego, spaziatura, margini. Quindi accanto
    all'arabo si stampa **la riga latina**, dove non c'e' niente da comporre: e'
    la stessa coppia di disegnatori sulla stessa domanda, meno la composizione.
    Solo lo scarto fra i due scarti dice qualcosa.
    """
    def largo(nome: str) -> tuple[int, int] | None:
        p = next(x for x in PROVE if x.scrittura == nome)
        try:
            return disegna_qt(p).shape[1], disegna_pil(p).shape[1]
        except Exception:  # pragma: no cover - dipende dall'ambiente
            return None

    ar, la = largo("araba"), largo("latina")
    if ar is None or la is None:
        return "non misurabile: uno dei due disegnatori non parte"
    return (f"riga araba Qt {ar[0]} px / PIL {ar[1]} px ({(ar[1] / ar[0] - 1) * 100:+.0f}%), "
            f"caso nullo sulla latina {la[0]} / {la[1]} "
            f"({(la[1] / la[0] - 1) * 100:+.0f}%)")


# ------------------------------------------------------------- la misura --


def cer(atteso: str, letto: str) -> float:
    """Character Error Rate: distanza di edit / lunghezza dell'atteso.

    Si tolgono gli spazi da tutti e due: dove il sottotitolo va a capo l'OCR
    consegna un numero di spazi che dipende dal ritaglio, e contarli farebbe
    salire il CER di una scrittura che l'OCR ha letto benissimo.
    """
    a = "".join(atteso.split())
    b = "".join(letto.split())
    if not a:
        return 0.0 if not b else 1.0
    riga = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        nuova = [i]
        for j, cb in enumerate(b, 1):
            nuova.append(min(riga[j] + 1, nuova[j - 1] + 1,
                             riga[j - 1] + (ca != cb)))
        riga = nuova
    return riga[-1] / len(a)


def _backend(nome: str):
    from vision.ocr import make_ocr

    return make_ocr(nome)


def misura(nomi: tuple[str, ...], png: str = "") -> int:
    from vision.ocr import italian_only

    try:
        _app_qt()
        disegnatore, quale = disegna_qt, "Qt"
    except Exception as e:  # pragma: no cover - dipende dall'ambiente
        print(f"! Qt non si apre ({e}): disegno con PIL, che non compone")
        disegnatore, quale = disegna_pil, "PIL"

    print(f"disegnatore: {quale}")
    print(f"controllo:   {controllo_composizione()}")
    print()

    motori = {}
    for n in nomi:
        try:
            motori[n] = _backend(n)
        except Exception as e:
            print(f"! «{n}» non parte su questa macchina: {e}")
            print(f"  -> le sue righe restano **non misurate**, non si inventano")
    if not motori:
        return 1

    intestazione = f"{'scrittura':12} {'lingua':7}"
    for n in motori:
        intestazione += f" {n:>10} {'CER':>7}"
    print(intestazione)
    print("-" * len(intestazione))

    letture: dict[str, dict[str, str]] = {n: {} for n in motori}
    for p in PROVE:
        if p.composta and quale != "Qt":
            print(f"{p.scrittura:12} {p.lingua:7}  non misurata: "
                  f"{quale} non compone questa scrittura")
            continue
        try:
            img = disegnatore(p)
        except Exception as e:
            print(f"{p.scrittura:12} {p.lingua:7}  non misurata: disegno fallito ({e})")
            continue
        if png:
            _salva(img, png, p.scrittura)
        riga = f"{p.scrittura:12} {p.lingua:7}"
        for n, m in motori.items():
            testo, _conf = m.read(img)
            letture[n][p.scrittura] = testo
            riga += f" {testo[:10]:>10} {cer(p.testo, testo):>7.2f}"
        print(riga)

    # **L'altra meta' della risposta, e non e' una curiosita'.** Quello che il
    # backend legge non e' quello che la catena riceve: `vision/reader.py` passa
    # ogni riga da `italian_only`, che tiene solo lettere latine. Misurare il
    # solo OCR direbbe «OneOCR legge dieci scritture su dieci» e sarebbe vero e
    # inutile — di nove non arriva niente al sintetizzatore.
    print()
    print("cosa ne resta dopo `italian_only` (il filtro che la catena applica sempre):")
    for n, viste in letture.items():
        vivi = [s for s, t in viste.items() if italian_only(t).strip()]
        print(f"  {n:8} sopravvivono {len(vivi)}/{len(viste)}: {', '.join(vivi)}")
    return 0


def _salva(img: np.ndarray, cartella: str, nome: str) -> None:
    from pathlib import Path

    from PIL import Image

    d = Path(cartella)
    d.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).save(d / f"{nome}.png")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backend", action="append", default=None,
                   help="ppocr | oneocr (ripetibile; di serie tutti e due)")
    p.add_argument("--png", default="", help="cartella in cui salvare i disegni")
    a = p.parse_args(argv)
    nomi = tuple(a.backend or ("ppocr", "oneocr"))
    return misura(nomi, a.png)


if __name__ == "__main__":
    sys.exit(main())
