"""L'audio del gioco in ingresso, il doppiaggio in uscita.

WASAPI in loopback: si "ascolta" cio' che un dispositivo di uscita sta
riproducendo, senza cavi e senza microfoni. E' il modo di prendere l'audio del
gioco esattamente com'e', e insieme il punto in cui e' piu' facile creare un
anello: se si cattura lo stesso dispositivo su cui si suona, il doppiaggio
rientra, viene ri-doppiato, e si ottiene un fischio invece di una voce.

Per questo `Loopback` e `Player` non scelgono niente da soli. Il dispositivo di
cattura e quello di uscita si passano espliciti, e chi li sceglie sa cosa sta
facendo: nel banco di prova si cattura VoiceMeeter (dove entra il gioco) e si
suona sulle cuffie di sistema, che sono due percorsi diversi e non si toccano.

**Blocchi e latenza.** Il blocco decide la latenza minima della catena: 480
campioni a 48 kHz sono 10 ms, ed e' il pavimento sotto cui non si scende
qualunque cosa faccia il resto. Non conviene farlo piu' piccolo — le riletture
costano piu' del tempo che risparmiano — ne' molto piu' grande, perche' entra
diritto nel budget del doppiaggio.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Device:
    """Un dispositivo audio, come lo vede WASAPI."""

    index: int
    name: str
    channels: int
    samplerate: int
    is_loopback: bool = False

    def __str__(self) -> str:
        verso = "loopback" if self.is_loopback else "uscita"
        return f"[{self.index}] {self.name} ({verso}, {self.channels}ch @ {self.samplerate} Hz)"


def _pa():
    import pyaudiowpatch as pa

    return pa


def list_devices() -> tuple[list[Device], Device | None]:
    """(dispositivi di loopback, uscita predefinita di Windows)."""
    pa = _pa()
    p = pa.PyAudio()
    try:
        wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
        loops = [
            Device(
                index=int(d["index"]),
                name=str(d["name"]),
                channels=int(d["maxInputChannels"]),
                samplerate=int(d["defaultSampleRate"]),
                is_loopback=True,
            )
            for d in p.get_loopback_device_info_generator()
        ]
        di = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
        default = Device(
            index=int(di["index"]),
            name=str(di["name"]),
            channels=int(di["maxOutputChannels"]),
            samplerate=int(di["defaultSampleRate"]),
        )
        return loops, default
    finally:
        p.terminate()


def find_loopback(needle: str) -> Device:
    """Il dispositivo di loopback il cui nome contiene `needle`.

    Si cerca per nome e non per indice: gli indici WASAPI cambiano quando si
    attacca una cuffia, e un indice scritto in configurazione e' un modo di
    catturare il dispositivo sbagliato senza nessun errore.
    """
    loops, _ = list_devices()
    ago = needle.lower().strip()
    esatti = [d for d in loops if ago in d.name.lower()]
    if not esatti:
        nomi = "\n  ".join(d.name for d in loops)
        raise RuntimeError(f"nessun loopback con '{needle}'. Disponibili:\n  {nomi}")
    return esatti[0]


def uscite() -> list[Device]:
    """I dispositivi su cui si puo' **suonare**, che non sono i loopback.

    Esiste perche' non c'era, e la sua mancanza aveva rotto `--output` in tutti
    e due i programmi dal vivo: cercavano il nome dentro l'elenco dei
    **loopback**, che WASAPI espone come dispositivi di *ingresso* con zero
    canali di uscita. Il risultato non era «non trovato»: era
    `OSError -9998 Invalid number of channels` se il nome corrispondeva, e il
    silenzioso ritorno alla predefinita se non corrispondeva — cioe' il
    doppiaggio che suona da un'altra parte senza dirlo, che e' il modo in cui si
    crea l'anello contro cui esiste questo file.
    """
    pa = _pa()
    p = pa.PyAudio()
    try:
        wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
        fuori: list[Device] = []
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            if d["hostApi"] != wasapi["index"] or d.get("isLoopbackDevice"):
                continue
            if int(d["maxOutputChannels"]) <= 0:
                continue
            fuori.append(
                Device(
                    index=int(d["index"]),
                    name=str(d["name"]),
                    channels=int(d["maxOutputChannels"]),
                    samplerate=int(d["defaultSampleRate"]),
                )
            )
        return fuori
    finally:
        p.terminate()


def find_output(needle: str) -> Device:
    """Il dispositivo di uscita il cui nome contiene `needle`.

    Solleva **elencando** invece di ripiegare sulla predefinita: chi scrive
    `--output cuffie` e si ritrova il doppiaggio negli altoparlanti non ha modo
    di accorgersene, e un ripiego che non si dichiara e' peggio di un errore.
    """
    tutte = uscite()
    ago = needle.lower().strip()
    esatti = [d for d in tutte if ago in d.name.lower()]
    if not esatti:
        nomi = "\n  ".join(d.name for d in tutte)
        raise RuntimeError(f"nessuna uscita con '{needle}'. Disponibili:\n  {nomi}")
    return esatti[0]


class Loopback:
    """Cattura cio' che un dispositivo di uscita sta riproducendo."""

    def __init__(self, device: Device, block: int = 480, samplerate: int | None = None) -> None:
        pa = _pa()
        self.device = device
        self.block = block
        self.samplerate = samplerate or device.samplerate
        self.channels = min(2, device.channels)
        self._p = pa.PyAudio()
        self._stream = self._p.open(
            format=pa.paFloat32,
            channels=self.channels,
            rate=self.samplerate,
            input=True,
            input_device_index=device.index,
            frames_per_buffer=block,
        )

    def read(self) -> np.ndarray:
        """Un blocco `(block, channels)`. Un overflow non ferma la sessione."""
        raw = self._stream.read(self.block, exception_on_overflow=False)
        data = np.frombuffer(raw, dtype=np.float32)
        return data.reshape(-1, self.channels) if self.channels > 1 else data

    def close(self) -> None:
        for chiudi in (self._stream.stop_stream, self._stream.close, self._p.terminate):
            try:
                chiudi()
            except Exception:
                pass

    def __enter__(self) -> "Loopback":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class Player:
    """Manda l'uscita a un dispositivo. Stereo, float32."""

    def __init__(self, device: Device, block: int = 480, samplerate: int | None = None) -> None:
        pa = _pa()
        self.device = device
        self.block = block
        self.samplerate = samplerate or device.samplerate
        self._p = pa.PyAudio()
        self._stream = self._p.open(
            format=pa.paFloat32,
            channels=2,
            rate=self.samplerate,
            output=True,
            output_device_index=device.index,
            frames_per_buffer=block,
        )

    def write(self, stereo: np.ndarray) -> None:
        data = np.asarray(stereo, dtype=np.float32)
        if data.ndim == 1:
            data = np.stack([data, data], axis=1)
        self._stream.write(np.ascontiguousarray(data).tobytes())

    def close(self) -> None:
        for chiudi in (self._stream.stop_stream, self._stream.close, self._p.terminate):
            try:
                chiudi()
            except Exception:
                pass

    def __enter__(self) -> "Player":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
