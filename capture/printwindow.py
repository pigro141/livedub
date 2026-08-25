"""Catturare **una finestra sola** senza nessuna libreria da far accettare.

## Perche' esiste

La cattura per finestra e' «la scelta che viene prima di tutte le altre»:
catturando lo schermo, nel fotogramma che va all'OCR finisce anche cio' che sta
davanti al gioco — comprese le nostre finestre — e il programma legge se stesso.

Il modo buono e' Windows Graphics Capture, e su questa macchina non si puo'
usare: `windows_capture` porta una libreria nativa, e Smart App Control la
blocca in **tutte** le versioni provate (2.0.1, 2.0.0, 1.5.0, 1.4.4). Provato
anche il secondo candidato, `winrt-Windows.Graphics.Capture` di pywinrt, in
tutte le versioni pubblicate (3.2.1, 3.1.0, 3.0.0, 2.3.0, 2.0.1): bloccato pure
lui, e con lui `winrt-runtime`. Non e' «quella libreria»: e' **ogni file nuovo**,
perche' il criterio guarda la reputazione della singola copia e una copia appena
scaricata non ne ha.

Da qui la strada che non ha nessun file da far accettare: `PrintWindow` con
`PW_RENDERFULLCONTENT`, che sta in `user32.dll` — una DLL di Windows, quindi
fuori dal criterio per costruzione. Nessun pacchetto, nessuna reputazione,
niente da scaricare.

## Cosa costa, misurato

Dieci passate per riga, questa macchina:

    finestra                    grandezza      intero      fascia (13%)
    ---------------------------------------------------------------------
    Chrome (contenuto GPU)      1278x1391     17,6 ms         6,2 ms
    Impostazioni (UWP)          1278x1391     18,3 ms         5,8 ms
    Blocco note                  730x1113     11,7 ms        10,7 ms
    Terminale                   1113x627       6,4 ms         5,9 ms

La fascia si prende spostando l'origine del DC (`SetWindowOrgEx`) invece di
copiare tutto: la finestra la disegna comunque per intero — quel costo e' suo —
ma `GetDIBits` copia solo la striscia che si legge, ed e' li' che stanno i
millisecondi. E' la stessa idea di `capture.solo_roi`, applicata a una finestra
invece che allo schermo.

## Il difetto vero, e perche' si dichiara invece di nasconderlo

`PW_RENDERFULLCONTENT` chiede al compositore il contenuto **ridisegnato** della
finestra. Funziona per tutto quello che passa da DirectComposition — i browser,
le app UWP, le finestre normali: verificato sull'immagine, il contenuto della
pagina di Chrome arriva intero e non solo la cornice. Un gioco Direct3D con una
catena di scambio *flip model* pero' non ha una superficie di redirezione, e
allora `PrintWindow` **riesce e restituisce nero**.

Nero non e' un errore: e' un fotogramma valido su cui l'OCR non legge niente, la
sessione resta accesa, i contatori restano verdi e a schermo non succede piu'
niente. E' precisamente la forma di difetto che questo progetto paga piu' cara,
quindi qui **non passa in silenzio**: `nero` guarda i primi fotogrammi buoni e,
se sono neri, lo dichiara — e chi ha chiamato puo' dirlo e tornare allo schermo
intero invece di leggere il buio per tutta la partita.

Non si dichiara al **primo** fotogramma: una finestra appena catturata puo'
darne uno vuoto prima di aver disegnato. Si guardano i primi `_PROVE` e basta
che **uno** porti dei pixel.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

import numpy as np

from capture.screen import Grab, ScreenSource

_u32 = ctypes.windll.user32
_g32 = ctypes.windll.gdi32

# «Ridisegna il contenuto vero», e non «copia la superficie di redirezione».
# Senza questo flag una finestra accelerata torna nera **sempre**, misurato:
# Chrome 0,0% di pixel non neri senza, 31,1% con.
PW_RENDERFULLCONTENT = 0x00000002

# Quanti fotogrammi si guardano prima di dire «e' nero». Non uno: appena aperta,
# una cattura puo' dare un fotogramma vuoto prima che la finestra abbia
# disegnato, e chiamarlo subito nero sarebbe una rinuncia dichiarata a torto —
# cioe' lo stesso difetto girato dall'altra parte.
_PROVE = 8


class _BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BI(ctypes.Structure):
    _fields_ = [("bmiHeader", _BIH), ("bmiColors", wintypes.DWORD * 3)]


class PrintWindowSource(ScreenSource):
    """La finestra scelta, un fotogramma alla volta, senza librerie in piu'.

    **Sincrona, al contrario di WGC.** Windows Graphics Capture consegna i
    fotogrammi da solo e `grab()` legge l'ultimo arrivato; qui il fotogramma si
    va a **prendere**, quindi il costo lo paga il ciclo video nel momento in cui
    chiama. In cambio non c'e' nessun thread nativo da fermare, nessuna cattura
    che resta accesa fra un Avvia e l'altro e nessun oggetto nativo che muore se
    lo si rilascia — cioe' cadono i tre rattoppi che `FinestraSource` si porta
    dietro.

    **`fresh` e' sempre vero**, e non e' una bugia comoda: qui un fotogramma si
    prende ogni volta che lo si chiede, quindi e' sempre nuovo *nel senso in cui
    lo intende chi legge* (l'ha appena disegnato la finestra). A dire se il
    contenuto e' cambiato ci pensa gia' `vision.diff`, che confronta i pixel e
    non si fida di nessuno.
    """

    name = "finestra-gdi"

    def __init__(self, hwnd: int, fascia: tuple[float, float] | None = None) -> None:
        self.hwnd = int(hwnd)
        # La striscia da copiare, in **frazioni** dell'altezza del contenuto:
        # `(0.80, 0.98)`. Frazioni e non pixel perche' la finestra puo' cambiare
        # misura a sessione accesa — un gioco che passa a schermo intero — e una
        # striscia in pixel finirebbe a leggere un altro punto **senza errore**,
        # che e' il modo in cui questa forma di difetto si nasconde.
        self.fascia = fascia
        self._chiusa = False
        self._viste = 0        # quanti fotogrammi si sono guardati
        self._con_pixel = 0    # quanti ne avevano

    # -- il fotogramma -----------------------------------------------------

    def _misura(self) -> tuple[int, int] | None:
        """L'area **cliente**, in pixel. E' il sistema in cui disegna PrintWindow."""
        r = wintypes.RECT()
        if not _u32.GetClientRect(self.hwnd, ctypes.byref(r)):
            return None
        w, h = int(r.right - r.left), int(r.bottom - r.top)
        return (w, h) if w > 0 and h > 0 else None

    def grab(self) -> Grab:
        t0 = time.perf_counter()
        if not _u32.IsWindow(self.hwnd):
            self._chiusa = True
            return Grab(frame=None, t=t0, fresh=False)
        misura = self._misura()
        if misura is None:
            return Grab(frame=None, t=t0, fresh=False)
        w, h = misura
        alto, quanto = self._striscia(h)
        pezzo = self._dipingi(w, alto, quanto)
        if pezzo is None:
            return Grab(frame=None, t=t0, fresh=False)
        if quanto == h:
            frame = pezzo
        else:
            # **Si reincolla in una tela grande quanto la finestra**, e non si
            # consegna la sola striscia: la ROI, il ritaglio dell'overlay e tutto
            # cio' che sta a valle sono in coordinate del fotogramma intero.
            # Consegnarne uno piu' piccolo vorrebbe dire cambiare quel sistema in
            # cinque posti, dove il primo che se ne dimentica legge il punto
            # sbagliato **senza errore**. E' la stessa scelta di `SoloRoi`.
            frame = np.zeros((h, w, pezzo.shape[2]), pezzo.dtype)
            frame[alto:alto + quanto] = pezzo
        if self._viste < _PROVE:
            self._viste += 1
            # Si guarda **la striscia** e non la tela: la tela e' nera per
            # costruzione fuori dalla fascia, e contarla direbbe «nero» proprio
            # quando la cattura funziona.
            if int(pezzo.max()) > 8:
                self._con_pixel += 1
        return Grab(frame=frame, t=t0, fresh=True)

    def _striscia(self, h: int) -> tuple[int, int]:
        """Da che riga e per quante, in pixel, dato quanto e' alta la finestra ora."""
        if not self.fascia:
            return 0, h
        su, giu = self.fascia
        alto = max(0, min(h - 1, int(su * h)))
        basso = max(alto + 1, min(h, int(giu * h)))
        return alto, basso - alto

    def _dipingi(self, w: int, alto: int, quanto: int) -> np.ndarray | None:
        """Disegna la finestra in un bitmap di memoria e ne porta via i byte.

        Le risorse GDI si liberano **sempre**, anche se `PrintWindow` fallisce:
        sono handle di sistema e un giro video ne chiederebbe trenta al secondo.
        Misurato con `GetGuiResources` su 500 giri di fila (2,9 s, 5,9 ms l'uno):
        oggetti GDI e USER vivi **zero prima e zero dopo**. Una perdita qui non
        darebbe un errore — darebbe un programma che dopo un'ora di partita
        smette di disegnare.
        """
        hdc = _u32.GetWindowDC(self.hwnd)
        if not hdc:
            return None
        mdc = bmp = None
        try:
            mdc = _g32.CreateCompatibleDC(hdc)
            bmp = _g32.CreateCompatibleBitmap(hdc, w, quanto)
            if not mdc or not bmp:
                return None
            _g32.SelectObject(mdc, bmp)
            if alto:
                # L'origine del DC si sposta in su: la finestra disegna dov'e'
                # sempre stata e nel bitmap finisce la sola striscia voluta.
                _g32.SetWindowOrgEx(mdc, 0, int(alto), None)
            if not _u32.PrintWindow(self.hwnd, mdc, PW_RENDERFULLCONTENT):
                return None
            bi = _BI()
            bi.bmiHeader.biSize = ctypes.sizeof(_BIH)
            bi.bmiHeader.biWidth = w
            bi.bmiHeader.biHeight = -quanto   # negativo = prima riga in cima
            bi.bmiHeader.biPlanes = 1
            bi.bmiHeader.biBitCount = 32
            buf = ctypes.create_string_buffer(w * quanto * 4)
            if not _g32.GetDIBits(mdc, bmp, 0, quanto, buf, ctypes.byref(bi), 0):
                return None
            # Copia e non vista sul buffer di ctypes: `frombuffer` non lo
            # possiede, e il resto della catena tiene i fotogrammi.
            a = np.frombuffer(buf, dtype=np.uint8).reshape(quanto, w, 4)
            return np.ascontiguousarray(a[:, :, :3])
        finally:
            if bmp:
                _g32.DeleteObject(bmp)
            if mdc:
                _g32.DeleteDC(mdc)
            _u32.ReleaseDC(self.hwnd, hdc)

    # -- cosa si puo' dire di questa cattura -------------------------------

    @property
    def chiusa(self) -> bool:
        """Il gioco e' stato chiuso. Va detto, non dedotto dal silenzio."""
        return self._chiusa or not _u32.IsWindow(self.hwnd)

    @property
    def nero(self) -> bool:
        """I primi fotogrammi erano **tutti** neri: qui non si leggera' mai niente.

        Risponde `False` finche' non ne ha guardati abbastanza, perche' «non lo
        so ancora» e «va bene» portano il chiamante a fare la stessa cosa —
        aspettare — mentre «e' nero» lo porta a cambiare strada. Dichiararlo
        troppo presto vorrebbe dire abbandonare una cattura che stava per
        funzionare.
        """
        return self._viste >= _PROVE and self._con_pixel == 0

    @property
    def deciso(self) -> bool:
        """Ha visto abbastanza fotogrammi per rispondere a `nero`."""
        return self._viste >= _PROVE

    def close(self) -> None:
        self._chiusa = True
