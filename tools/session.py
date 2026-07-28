"""Cosa resta di una sessione dal vivo, dopo che e' finita.

Una prova d'ascolto senza artefatti produce impressioni, e le impressioni non si
riaprono: *«qui la voce e' andata di corsa»* non dice quale battuta, ne' quanto,
ne' perche'. Ed e' gia' successo che il numero colpevole fosse in bella vista e
sembrasse innocuo — `rate_x1000` a 1350 al p50, cioe' ogni battuta al massimo
dell'accelerazione, letto per quello che era solo dopo aver messo insieme
l'ascolto e la tabella.

Quindi ogni sessione lascia tre cose in `runs/<data>/`:

    mix.wav       l'uscita esattamente come l'ha sentita l'orecchio
    events.jsonl  una riga per battuta, con tutti i tempi
    config.json   cosa l'ha prodotta

## La riga che rende gli altri due utili: `t_wav`

Gli istanti delle battute vivono sull'orologio della sessione, che parte
all'avvio del programma; il file WAV comincia quando comincia l'audio, cioe'
dopo l'apertura dei device. Sono due origini diverse, ed e' **la stessa forma di
errore** che dal vivo aveva gia' fatto nascere la prima battuta venti secondi
avanti nella linea temporale del mixer.

Qui l'origine del WAV si registra invece di assumerla, e ogni battuta porta con
se' la propria posizione **dentro il file**. Cosi' una lamentela diventa un
`seek`: si apre il WAV a quel secondo e si sente esattamente la battuta che la
riga descrive, senza fare aritmetica fra due orologi in testa.
"""

from __future__ import annotations

import json
import wave
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np


class Session:
    """Registra una sessione dal vivo su disco.

    L'audio si accumula in memoria e si scrive alla fine: il thread audio non
    deve fare niente di lento, e un `append` a una lista costa quanto niente
    mentre una scrittura su disco no. Il prezzo e' la memoria — dichiarato in
    `max_minutes`, oltre il quale si smette di registrare **dicendolo**, perche'
    un WAV che finisce a meta' senza avvisare somiglia troppo a una sessione
    andata storta.
    """

    def __init__(
        self,
        root: str | Path = "runs",
        samplerate: int = 48000,
        max_minutes: float = 30.0,
    ) -> None:
        self.dir = Path(root) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.samplerate = samplerate
        self.max_samples = int(max_minutes * 60 * samplerate)
        self._blocks: list[np.ndarray] = []
        self._n = 0
        self._pieno = False
        self._lines = (self.dir / "events.jsonl").open("w", encoding="utf-8")
        # L'origine del WAV: `None` finche' non arriva il primo blocco. Non e'
        # l'istante in cui si costruisce questo oggetto, ed e' proprio quella
        # differenza che sposterebbe ogni `t_wav` di qualche secondo.
        self.t0: float | None = None

    # -- audio -------------------------------------------------------------

    def audio(self, block: np.ndarray, t: float) -> None:
        """Un blocco di uscita, con l'istante a cui il mixer lo ha prodotto."""
        if self.t0 is None:
            self.t0 = t
        if self._pieno:
            return
        if self._n >= self.max_samples:
            self._pieno = True
            print("! registrazione audio interrotta: raggiunto il limite di durata")
            return
        self._blocks.append(np.asarray(block, dtype=np.float32).copy())
        self._n += len(block)

    # -- battute -----------------------------------------------------------

    def line(self, riga) -> None:
        """Una battuta doppiata, con la sua posizione dentro il WAV."""
        record = asdict(riga)
        record["t_wav"] = None if self.t0 is None else round(riga.t_scheduled - self.t0, 3)
        record["latency_ms"] = round(riga.latency_ms, 1)
        record["live_latency_ms"] = round(riga.live_latency_ms, 1)
        self._lines.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._lines.flush()  # una sessione interrotta deve lasciare cio' che aveva

    def mark(self, t: float, nota: str = "") -> None:
        """Il giudizio umano, timbrato: «questa era sbagliata».

        Va nello stesso file delle battute e sulla stessa scala, perche' il
        punto e' proprio poterli confrontare.
        """
        self._lines.write(
            json.dumps(
                {
                    "kind": "mark",
                    "t_wav": None if self.t0 is None else round(t - self.t0, 3),
                    "nota": nota,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        self._lines.flush()

    # -- chiusura ----------------------------------------------------------

    def close(self, cfg=None, report: str = "") -> Path:
        self._lines.close()
        if cfg is not None:
            (self.dir / "config.json").write_text(
                json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
            )
        if report:
            (self.dir / "report.txt").write_text(report, encoding="utf-8")
        if self._blocks:
            data = np.concatenate(self._blocks, axis=0)
            path = self.dir / "mix.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(2 if data.ndim == 2 else 1)
                w.setsampwidth(2)
                w.setframerate(self.samplerate)
                # int16 con un margine: il limitatore del mixer tiene i picchi
                # sotto 1.0, ma un arrotondamento a fondo scala suonerebbe come
                # una distorsione che il mixer non ha prodotto.
                w.writeframes((np.clip(data, -1.0, 1.0) * 32000.0).astype("<i2").tobytes())
        return self.dir
