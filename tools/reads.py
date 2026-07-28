"""Il flusso di letture, su file: registrarlo una volta, riusarlo mille.

Lo stabilizzatore (`vision/subtitles.py`) e' l'unico stadio del dominio video
che non si puo' giudicare guardando cosa ne esce, perche' *sceglie lui* cosa ne
esce. Per studiarlo serve il suo **ingresso**: tutte le alimentazioni, comprese
quelle che ha scartato.

Il formato e' JSONL, una riga per alimentazione del tracker — non per frame: i
frame che il diff blocca non alimentano niente e non compaiono, e la riga con
`certain: true` e' la prova indipendente ("l'inchiostro e' sparito") che il
tracker tratta diversamente. Rispettare questa distinzione e' l'unico modo per
cui rifare girare il tracker da file dia **esattamente** gli stessi eventi che
darebbe dal video.

Costa: un video di 50 s produce ~1200 alimentazioni e poche centinaia di kB,
contro i ~55 s di OCR necessari a ricrearle.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.types import LineClass, OcrLine, SubtitleEvent


def encode(t: float, candidates: list[SubtitleEvent], certain: bool) -> dict:
    """Una alimentazione del tracker, in forma serializzabile."""
    return {
        "t": round(float(t), 4),
        "certain": bool(certain),
        "cands": [
            {
                "text": ev.text,
                "cls": ev.cls.value,
                "lines": [
                    {
                        "text": ln.text,
                        "cls": ln.cls.value,
                        "bbox": [int(v) for v in ln.bbox],
                        "luma": round(float(ln.luma), 2),
                        "sat": round(float(ln.sat), 2),
                        "conf": round(float(ln.conf), 4),
                    }
                    for ln in ev.lines
                ],
            }
            for ev in candidates
        ],
    }


def decode(record: dict) -> tuple[float, list[SubtitleEvent], bool]:
    """L'inverso di `encode`. Ricostruisce gli eventi come li vedeva il tracker.

    `t_on` viene dal `t` della riga e non da un campo suo: e' cosi' che lo
    costruisce `merge_lines`, e ricostruirlo altrimenti introdurrebbe una
    differenza fra il banco e la pipeline proprio nel dato che il banco misura.
    """
    t = float(record["t"])
    candidates = [
        SubtitleEvent(
            text=c["text"],
            cls=LineClass(c["cls"]),
            t_on=t,
            lines=tuple(
                OcrLine(
                    text=ln["text"],
                    cls=LineClass(ln["cls"]),
                    bbox=tuple(ln["bbox"]),
                    luma=ln.get("luma", 0.0),
                    sat=ln.get("sat", 0.0),
                    conf=ln.get("conf", 1.0),
                )
                for ln in c.get("lines", ())
            ),
        )
        for c in record.get("cands", ())
    ]
    return t, candidates, bool(record.get("certain", False))


class Recorder:
    """Rubinetto da passare a `SubtitleReader(tap=...)`."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.records: list[dict] = []

    def __call__(self, t: float, candidates: list[SubtitleEvent], certain: bool) -> None:
        self.records.append(encode(t, candidates, certain))

    def write(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            for record in self.records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self.path


def load(path: str | Path) -> list[tuple[float, list[SubtitleEvent], bool]]:
    """Rilegge un file di letture."""
    out = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(decode(json.loads(line)))
    return out
