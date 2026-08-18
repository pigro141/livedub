"""Rilevatore di cambiamento sulla ROI.

E' il cancello che sta davanti all'OCR. L'OCR e' la cosa cara del dominio video
e un sottotitolo resta a schermo per decine di frame: farlo girare a ogni frame
significherebbe rileggere cinquanta volte la stessa battuta.

Il diff invece deve costare quasi nulla, perche' gira a 30 Hz sempre. Due
scelte per ottenerlo: si lavora sulla sola luminanza, e la si sottocampiona di
`stride` in entrambe le direzioni — con stride 4 si guarda un pixel su sedici.
Un sottotitolo che compare cambia una frazione enorme della ROI, quindi la
perdita di risoluzione non costa sensibilita' dove serve.

Il rilevatore non dice solo "cambiato": distingue **comparsa**, **sparizione** e
**sostituzione**, che a valle sono tre cose diverse — la sparizione chiude una
battuta e ne fissa la durata reale, la sostituzione ne chiude una e ne apre
un'altra nello stesso istante.

**Cosa vuol dire "c'e' del testo".** La prima versione rispondeva con "almeno un
pixel sopra `ink_min_luma`". Su un fondo nero sintetico e' esatto; su un frame
di gioco un muro chiaro, una carrozzeria bianca o un cordolo lo soddisfano
sempre, quindi la risposta era **sempre si'** — e con `had_ink` e `has_ink`
entrambi veri ogni cambiamento diventava una sostituzione. Comparsa e sparizione
non scattavano mai, e con loro non arrivava mai il `t_off` preciso su cui poggia
la calibrazione del tempo.

Misurato su 3600 frame di gioco, la frazione di ROI riconosciuta come testo:

    criterio                             con sottotitolo   senza
    frazione sopra ink_min_luma            p50 0,058       p50 0,016   non separa
    maschera della pipeline (contrasto)    p50 0,055       p50 0,008   6,6x

Il contrasto locale e' quindi il criterio, e costa una blur su un array gia'
sottocampionato di sedici. La quantita' si conta **per colonna** e non per area:
una frazione dell'area dipende dall'altezza della ROI, e lo stesso sottotitolo
dentro una ROI quattro volte piu' alta darebbe un quarto del valore — che e'
esattamente come la prima versione di questa soglia e' passata verde sul video
vero e ha spento il banco sintetico.

    una riga di sottotitolo sintetico              0,54
    gioco, con sottotitolo (2000 frame)     minimo 0,243
    gioco, a schermo vuoto                 mediana 0,180

**E la stessa forma di errore c'era ancora, un piano piu' sopra.** L'inchiostro
si conta per colonna apposta, ma `ratio` — la frazione di pixel *cambiati*, che
e' il cancello vero — si e' sempre contata **sull'area intera**. Quella frazione
ha l'area al denominatore, quindi lo stesso sottotitolo diluito in un'area piu'
grande la fa scendere. Misurato facendo crescere l'area attorno a una riga vera:
0,0225 a 0,08 di altezza, 0,0043 a 0,70, **0,0032** a schermo intero — cioe'
sotto `diff_threshold`. A schermo intero il cancello non si apre mai: 14
fotogrammi in, 14 fermati, zero chiamate all'OCR, e senza nessun contatore che
lo dica.

**Il rimedio era un denominatore che non cresce con l'area** — celle di lato
fisso e la peggiore invece della media — ed e' stato tolto con le aree multiple:
serviva solo a loro, e un cancello con due soglie e due distribuzioni che nessuno
accende e' esattamente il genere di codice che qui si paga dopo. La misura resta
scritta qui sopra perche' la prossima area grande la ritrovi gia' fatta.

**I due gruppi non si separano del tutto**, e va detto: a schermo vuoto la coda
alta arriva a 1,1, cioe' la texture di una scena puo' avere l'aspetto di un
sottotitolo. La sparizione scatta quindi su circa meta' delle interruzioni vere
invece che su tutte — meglio di mai, non una soluzione. La soglia sta **sotto**
il minimo osservato con sottotitolo, perche' i due errori non costano uguale: un
falso "non c'e' testo" chiude una battuta ancora a schermo e la fa riaprire, un
falso "c'e' testo" ritarda solo la chiusura di `hold_frames`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class Change(Enum):
    NONE = "none"
    APPEARED = "appeared"
    VANISHED = "vanished"
    REPLACED = "replaced"


@dataclass(slots=True)
class DiffResult:
    change: Change
    ratio: float  # frazione di pixel campionati che sono cambiati
    ink: float  # pixel di testo per colonna della ROI sottocampionata, adesso

    @property
    def changed(self) -> bool:
        return self.change is not Change.NONE


class RoiDiff:
    """Confronta la ROI corrente con la precedente."""

    def __init__(
        self,
        threshold: float = 0.004,
        stride: int = 4,
        ink_min_luma: int = 110,
        *,
        contrast_min: float = 30.0,
        contrast_kernel: int = 63,
        ink_min_columns: float = 0.20,
        vanish_frames: int = 3,
    ) -> None:
        if stride < 1:
            raise ValueError(f"stride non valido: {stride}")
        self.threshold = float(threshold)
        self.stride = int(stride)
        self.ink_min_luma = int(ink_min_luma)
        self.contrast_min = float(contrast_min)
        # Il fondo locale si misura sulla stessa scala dell'immagine su cui si
        # lavora: il nucleo va rimpicciolito quanto la ROI, altrimenti guarda
        # una finestra sedici volte piu' larga di quella voluta.
        self.contrast_kernel = max(3, (int(contrast_kernel) // self.stride) | 1)
        self.ink_min_columns = float(ink_min_columns)
        self.vanish_frames = max(1, int(vanish_frames))
        self._previous: np.ndarray | None = None
        self._had_ink = False
        self._senza_inchiostro = 0
        self._sparizione_da_dire = False  # frame consecutivi senza testo
        self._sparizione_da_dire = False  # c'era testo: la sparizione andra' detta

    def reset(self) -> None:
        self._previous = None
        self._had_ink = False
        self._senza_inchiostro = 0
        self._sparizione_da_dire = False

    def update(self, roi: np.ndarray) -> DiffResult:
        sample = self._sample(roi)
        ink = self._ink(sample)
        has_ink = ink >= self.ink_min_columns

        if self._previous is None:
            self._previous = sample
            self._had_ink = has_ink
            # Il primo frame non e' un cambiamento: e' l'inizio delle
            # osservazioni. Se pero' c'e' gia' del testo, e' una comparsa —
            # altrimenti un sottotitolo gia' a schermo all'avvio non verrebbe
            # mai letto.
            return DiffResult(Change.APPEARED if has_ink else Change.NONE, 0.0, ink)

        if sample.shape != self._previous.shape:
            # Cambio di risoluzione a meta' sessione: si riparte da zero.
            self._previous = sample
            self._had_ink = has_ink
            return DiffResult(Change.APPEARED if has_ink else Change.NONE, 1.0, ink)

        delta = np.abs(sample - self._previous)
        ratio = self._variazione(delta)
        had_ink = self._had_ink
        self._previous = sample
        self._had_ink = has_ink
        # Il conteggio si aggiorna a ogni frame, anche quando il diff non vede
        # cambiamenti: una sparizione vera resta tale mentre lo schermo e' fermo,
        # e legarla al solo frame che cambia la renderebbe impossibile da
        # confermare proprio nelle scene tranquille.
        self._senza_inchiostro = 0 if has_ink else self._senza_inchiostro + 1
        if has_ink:
            self._sparizione_da_dire = True

        # **La conferma va decisa prima del cortocircuito su `ratio`.** Un
        # sottotitolo che sparisce lascia lo schermo *fermo*: dal secondo frame
        # vuoto in poi non cambia piu' niente, il diff uscirebbe subito con
        # `NONE`, e la sparizione non verrebbe confermata mai. Sarebbe il difetto
        # opposto a quello che si stava curando — battute che non si chiudono
        # piu' — e sarebbe passato inosservato perche' nei test lo schermo si
        # muove sempre.
        if (
            not has_ink
            and self._sparizione_da_dire
            and self._senza_inchiostro >= self.vanish_frames
        ):
            self._sparizione_da_dire = False
            return DiffResult(Change.VANISHED, ratio, ink)

        if ratio <= self.soglia:
            return DiffResult(Change.NONE, ratio, ink)
        if has_ink and not had_ink:
            change = Change.APPEARED
        elif had_ink and not has_ink:
            # Qui ci si arriva solo se la sparizione **non** e' ancora
            # confermata (il ramo sopra l'avrebbe gia' detta): si tace.
            # **Un frame solo non e' una sparizione.** Finche' non e' confermata
            # si tace: dire `NONE` lascia la battuta aperta, dire `VANISHED` la
            # chiude d'autorita' e la fa riaprire identica un attimo dopo. Fra i
            # due errori possibili, tenere aperta una battuta gia' sparita costa
            # `vanish_frames / fps` di durata in piu'; chiuderne una ancora a
            # schermo costa una voce doppia, che si sente.
            change = Change.NONE
        elif has_ink:
            change = Change.REPLACED
        else:
            # Cambia qualcosa ma non c'e' testo ne' prima ne' dopo: e' lo sfondo
            # del gioco che si muove sotto la ROI. Non riguarda i sottotitoli.
            change = Change.NONE
        return DiffResult(change, ratio, ink)

    @property
    def soglia(self) -> float:
        """Contro cosa si confronta `ratio`."""
        return self.threshold

    def _variazione(self, delta: np.ndarray) -> float:
        """Quanto e' cambiato: la frazione di pixel campionati che si sono mossi."""
        cambiato = delta > 16.0
        return float(cambiato.mean()) if cambiato.size else 0.0

    def _ink(self, sample: np.ndarray) -> float:
        """Pixel di testo per colonna della ROI sottocampionata.

        Stessa forma della maschera di `vision/lines.py`: chiaro in assoluto
        **e** chiaro rispetto al proprio intorno. Senza il secondo termine il
        cielo di mezzogiorno e' inchiostro.
        """
        if sample.size == 0:
            return 0.0
        absolute = sample > self.ink_min_luma
        if not absolute.any():
            return 0.0
        columns = sample.shape[1]
        try:
            import cv2
        except ImportError:  # pragma: no cover - opencv assente
            return float(absolute.sum() / columns)
        k = min(self.contrast_kernel, (min(sample.shape) - 1) | 1)
        if k < 3 or self.contrast_min <= 0:
            return float(absolute.sum() / columns)
        background = cv2.blur(sample, (k, k))
        return float((absolute & ((sample - background) > self.contrast_min)).sum() / columns)

    def _sample(self, roi: np.ndarray) -> np.ndarray:
        if roi.ndim == 3:
            small = roi[:: self.stride, :: self.stride, :3]
            return small.astype(np.float32).mean(axis=2)
        return roi[:: self.stride, :: self.stride].astype(np.float32)
