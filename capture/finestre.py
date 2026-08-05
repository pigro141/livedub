"""Le finestre aperte, per farne scegliere una all'utente.

Catturare **una finestra** invece dello schermo intero non e' una comodita': e'
la differenza fra un OCR che legge il gioco e un OCR che legge anche tutto
quello che gli capita davanti — comprese le finestre di questo programma. Per
sceglierla bisogna prima elencarle, e questo modulo fa solo quello.

Si usa `EnumWindows` con ctypes e non una libreria: e' una decina di righe di
API di Windows, e una dipendenza in piu' per una decina di righe e' una
dipendenza in meno che si puo' rompere.

**Cosa si tiene fuori dall'elenco, e perche'.** Le finestre invisibili, quelle
senza titolo, gli strumenti (`WS_EX_TOOLWINDOW`), le finestre di grandezza
ridicola e — la sola che non e' ovvia — **le nostre**: l'overlay del tradotto e
la finestra di livedub. Offrire all'utente di catturare la finestra che disegna
il tradotto vorrebbe dire offrirgli un anello di reazione, cioe' il difetto che
la cattura per finestra esiste per chiudere.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

# I titoli che non offriamo mai: sono nostri.
NOSTRE = ("livedub",)


@dataclass(frozen=True, slots=True)
class Finestra:
    """Una finestra a schermo, con quello che serve per catturarla."""

    hwnd: int
    titolo: str
    processo: str
    larghezza: int
    altezza: int

    def __str__(self) -> str:
        return f"{self.titolo}  [{self.processo}]  {self.larghezza}x{self.altezza}"


def _nascosta(hwnd: int) -> bool:
    """La finestra e' *cloaked*: esiste, si dichiara visibile, e non si vede.

    Non e' un caso di scuola. `IsWindowVisible` da solo mette in cima
    all'elenco «Esperienza input di Windows» — una finestra 2560x1440 di
    `TextInputHost.exe` che copre lo schermo intero e non si vede — e siccome
    l'elenco e' ordinato per area, la prima proposta sarebbe quella. Le finestre
    delle app moderne e quelle su un desktop virtuale diverso stanno nello
    stesso caso, e a chiederlo e' il compositore, non `user32`.
    """
    DWMWA_CLOAKED = 14
    val = ctypes.c_int(0)
    try:
        ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val)
        )
    except Exception:  # pragma: no cover - dwmapi c'e' da Vista
        return False
    return ok == 0 and val.value != 0


def _nome_processo(hwnd: int) -> str:
    """Il nome dell'eseguibile, che spesso dice piu' del titolo.

    `Grand Theft Auto V` lo si riconosce dal titolo; una finestra intitolata
    `Senza nome` no, e il suo `notepad.exe` si'.
    """
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        n = wintypes.DWORD(260)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        k32.CloseHandle(h)


def elenco(min_lato: int = 200) -> list[Finestra]:
    """Le finestre catturabili, dalla piu' grande alla piu' piccola.

    Ordinate per area perche' il gioco e' quasi sempre la finestra piu' grande:
    la prima della lista e' quella giusta nove volte su dieci, e una lista in
    cui la risposta e' in cima si legge in un secondo.
    """
    u32 = ctypes.windll.user32
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    trovate: list[Finestra] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visita(hwnd, _lparam):
        if not u32.IsWindowVisible(hwnd) or _nascosta(hwnd):
            return True
        if u32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        n = u32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, buf, n + 1)
        titolo = buf.value.strip()
        if not titolo or any(x in titolo.lower() for x in NOSTRE):
            return True
        r = wintypes.RECT()
        if not u32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < min_lato or h < min_lato:
            return True
        trovate.append(Finestra(int(hwnd), titolo, _nome_processo(hwnd), w, h))
        return True

    u32.EnumWindows(visita, 0)
    trovate.sort(key=lambda f: f.larghezza * f.altezza, reverse=True)
    return trovate


def rettangolo(hwnd: int) -> tuple[int, int, int, int] | None:
    """Dove sta la finestra sullo schermo, in pixel: `(x, y, w, h)`.

    Serve all'overlay, che deve posarsi **sulla finestra** e non sullo schermo:
    se il gioco si sposta, il sottotitolo tradotto lo segue senza che nessuno
    ritari niente.
    """
    r = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def rettangolo_client(hwnd: int) -> tuple[int, int, int, int] | None:
    """L'**area cliente** della finestra, in coordinate di schermo.

    E non `GetWindowRect`, e la differenza non e' un dettaglio: WGC consegna il
    contenuto **senza** bordi e barra del titolo. Misurato su una finestra di
    Chrome, `GetWindowRect` dice 1294x1399 e la cattura arriva 1280x1392: sette
    pixel di scarto, che e' esattamente di quanto l'overlay cadrebbe spostato
    rispetto al sottotitolo. Si prende quindi il rettangolo cliente e lo si
    porta in coordinate di schermo con `ClientToScreen`, che e' il sistema in cui
    va piazzata la finestra dell'overlay.
    """
    u32 = ctypes.windll.user32
    r = wintypes.RECT()
    if not u32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    p = wintypes.POINT(r.left, r.top)
    if not u32.ClientToScreen(hwnd, ctypes.byref(p)):
        return None
    return (int(p.x), int(p.y), int(r.right - r.left), int(r.bottom - r.top))


def viva(hwnd: int) -> bool:
    """La finestra esiste ancora? Il gioco si chiude, e va detto."""
    return bool(ctypes.windll.user32.IsWindow(hwnd))
