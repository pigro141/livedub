"""Chi parla: da un'impronta a un personaggio, e da un personaggio a una voce.

Non serve sapere che quello e' Franklin. Serve che, dentro una partita, ogni
personaggio riceva una voce **subito** e la tenga: un personaggio con la voce
sbagliata e' una scelta discutibile, un personaggio che cambia voce a meta'
scena e' un errore evidente. I nomi non li da' nessuno — i sottotitoli non li
contengono — quindi le identita' sono progressive (`S0`, `S1`, ...) e vere solo
dentro la sessione.

## La forma di questo modulo viene da una misura, e la misura ha sorpreso

La prima domanda posta era: due ritagli brevi della stessa voce si somigliano
piu' di due ritagli brevi di voci diverse? Risposta sull'audio di GTA V: quasi
per niente. Sembrava la fine della strada.

Era la domanda sbagliata. **Il tracker non confronta mai due ritagli brevi fra
loro.** Confronta il poco che ha raccolto prima di dover parlare con il
*centroide* di un personaggio, costruito su tutte le sue battute intere: un
indizio debole contro una conoscenza solida, non due indizi deboli. Misurato su
82 battute di GTA V etichettate all'ascolto, tre personaggi, a esclusione:

    parlato disponibile     sceglie il personaggio giusto
        0,30 s                       86,6%
        0,50 s                       93,9%
        0,75 s                      100,0%
        1,00 s                      100,0%

Da qui **due regole che non sono opzioni**:

1. **un ritaglio breve sceglie, non dichiara.** A 0,30 s la somiglianza col
   proprio centroide sta sotto 0,40 tre volte su quattro: non perche' sia un
   altro personaggio, ma perche' e' corta. Chi creasse un personaggio nuovo su
   quel numero ne inventerebbe uno a ogni battuta, e sarebbe un difetto che
   all'ascolto sembra "cambia voce in continuazione" — cioe' esattamente il
   guasto peggiore, ottenuto per eccesso di zelo;

2. **si impara dalle battute intere.** Quando la battuta finisce il suo audio
   c'e' tutto: quello e' il momento di aggiornare il centroide e, se davvero non
   somiglia a nessuno, di aprire un personaggio nuovo. La decisione veloce paga
   il prezzo della fretta, la conoscenza no.

## Cosa questo modulo non fa

Non usa il colore della riga. Il piano assumeva che una riga grigia fosse un
secondo personaggio: misurato su 675 battute bianche in 17 sessioni, le grigie
sono 15 e **nessuna e' dialogo** — sono code del rumore dell'OCR. Un vincolo
costruito su quel segnale vincolerebbe rumore.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.config import SpeakerConfig

# Il pavimento della scelta veloce. Non e' una soglia di identita': serve solo a
# distinguere "il migliore e' plausibile" da "qui non c'e' voce", perche' un
# ritaglio di silenzio o di motore da' somiglianze intorno a zero con tutti.
PLAUSIBILE_SOPRA = 0.15


@dataclass
class Personaggio:
    """Un personaggio conosciuto: la somma delle sue impronte, e da quando."""

    speaker_id: str
    somma: np.ndarray
    battute: int = 0
    prima_volta: float = 0.0
    ultima_volta: float = 0.0
    f0: float = 0.0  # intonazione mediana, per il genere

    @property
    def centroide(self) -> np.ndarray:
        n = float(np.linalg.norm(self.somma))
        return self.somma / n if n > 1e-9 else self.somma

    @property
    def gender(self) -> str:
        """Maschile, femminile, o non si sa.

        La fascia morta fra 165 e 185 Hz e' voluta: li' dentro un uomo con la
        voce chiara e una donna con la voce scura non si distinguono, e
        rispondere "non so" fa scegliere al pool la prossima voce libera invece
        di quella sbagliata con convinzione.
        """
        if self.f0 <= 0:
            return "?"
        if self.f0 < 165.0:
            return "m"
        return "f" if self.f0 > 185.0 else "?"


@dataclass
class Decisione:
    """Cosa il tracker ha deciso, e con quanta fiducia."""

    speaker_id: str
    confidence: float
    is_new: bool = False
    provisional: bool = False  # deciso con poco parlato: si potra' solo imparare, non disdire


class SpeakerTracker:
    """Banca di centroidi, coseno, e due porte di ingresso invece di una.

    `scegli` e' la porta veloce: la usa chi deve parlare adesso e ha in mano
    quel poco che il personaggio ha detto finora. Non crea mai nessuno.

    `impara` e' la porta lenta: la usa chi ha in mano la battuta intera, a cose
    fatte. Aggiorna il centroide e, se serve, apre un personaggio nuovo.

    Tenerle separate e' l'intero contenuto di questo modulo. Una sola porta
    dovrebbe scegliere una soglia buona per entrambe, e non esiste: quella che
    non inventa personaggi a 0,3 s non ne riconosce di nuovi a 2 s.
    """

    def __init__(self, cfg: SpeakerConfig | None = None) -> None:
        self.cfg = cfg or SpeakerConfig()
        self.people: list[Personaggio] = []
        self._ultimo: str | None = None

    def __len__(self) -> int:
        return len(self.people)

    def get(self, speaker_id: str) -> Personaggio | None:
        return next((p for p in self.people if p.speaker_id == speaker_id), None)

    def reset(self) -> None:
        self.people.clear()
        self._ultimo = None

    # -- la porta veloce ---------------------------------------------------

    def scegli(self, embedding: np.ndarray | None, t: float = 0.0) -> Decisione:
        """Chi e', fra quelli che conosco? Non ne inventa di nuovi.

        Senza impronta — non c'era abbastanza parlato, o l'analisi non e' pronta
        — si risponde **l'ultimo che ha parlato**, non un personaggio nuovo. In
        un dialogo e' sbagliato circa una volta su due; inventare un personaggio
        e' sbagliato sempre, e per giunta consuma una voce del pool.
        """
        if embedding is None or not self.people or float(np.linalg.norm(embedding)) < 1e-9:
            # Nessuno da scegliere: si risponde un'identita' provvisoria **senza
            # aprire un posto in banca**. Aprirlo qui vorrebbe dire iscrivere un
            # personaggio la cui impronta non si conosce, e un centroide vuoto
            # non somiglia a niente per sempre: quel personaggio non si
            # ritroverebbe mai piu', e la sua voce resterebbe bruciata.
            return Decisione(self._ultimo or "S0", 0.0, provisional=True)

        punteggi = np.array([float(np.dot(embedding, p.centroide)) for p in self.people])
        k = int(np.argmax(punteggi))
        migliore = float(punteggi[k])
        if migliore < PLAUSIBILE_SOPRA and self._ultimo is not None:
            # Nessuno somiglia: quasi sempre vuol dire che il ritaglio non
            # contiene voce. Si resta su chi parlava, che e' l'ipotesi meno
            # dannosa, e la battuta intera dira' com'e' andata davvero.
            return Decisione(self._ultimo, migliore, provisional=True)
        self._ultimo = self.people[k].speaker_id
        return Decisione(self.people[k].speaker_id, migliore, provisional=True)

    # -- la porta lenta ----------------------------------------------------

    def impara(
        self, embedding: np.ndarray | None, t: float = 0.0, f0: float = 0.0
    ) -> Decisione:
        """La battuta e' finita e c'e' tutto il suo audio: adesso si conclude.

        E' l'unico punto in cui nasce un personaggio, ed e' voluto: qui il
        ritaglio e' lungo abbastanza perche' una somiglianza bassa voglia dire
        davvero "non l'ho mai sentito" e non "non ho sentito abbastanza".
        """
        if embedding is None or float(np.linalg.norm(embedding)) < 1e-9:
            return Decisione(self._ultimo or "S?", 0.0)
        if self.people:
            punteggi = np.array([float(np.dot(embedding, p.centroide)) for p in self.people])
            k = int(np.argmax(punteggi))
            if float(punteggi[k]) >= self.cfg.similarity:
                p = self.people[k]
                p.somma = p.somma + embedding
                p.battute += 1
                p.ultima_volta = t
                if f0 > 0:
                    # Mediana incrementale povera ma stabile: la media si fa
                    # portare via da un ritaglio in cui l'ottava e' stata
                    # sbagliata, e sbagliare ottava e' l'errore tipico di ogni
                    # stimatore di intonazione.
                    p.f0 = f0 if p.f0 <= 0 else 0.8 * p.f0 + 0.2 * f0
                self._ultimo = p.speaker_id
                return Decisione(p.speaker_id, float(punteggi[k]))
        if len(self.people) >= self.cfg.max_speakers:
            # Il pool e' pieno. Si attacca al migliore invece di rifiutare: due
            # personaggi con la stessa voce sono brutti, un personaggio muto no.
            if self.people:
                punteggi = np.array([float(np.dot(embedding, p.centroide)) for p in self.people])
                k = int(np.argmax(punteggi))
                self._ultimo = self.people[k].speaker_id
                return Decisione(self.people[k].speaker_id, float(punteggi[k]))
        return self._apri(embedding, t, f0=f0)

    # -- interno -----------------------------------------------------------

    def _apri(self, embedding: np.ndarray, t: float, *, f0: float = 0.0) -> Decisione:
        """Iscrive un personaggio. Solo dalla porta lenta, e solo con un'impronta
        vera: un centroide vuoto non somiglierebbe mai piu' a niente."""
        sid = f"S{len(self.people)}"
        self.people.append(
            Personaggio(
                speaker_id=sid,
                somma=embedding.copy(),
                battute=1,
                prima_volta=t,
                ultima_volta=t,
                f0=f0,
            )
        )
        self._ultimo = sid
        return Decisione(sid, 0.0, is_new=True)

    # -- lettura -----------------------------------------------------------

    def report(self) -> str:
        if not self.people:
            return "(nessun personaggio ancora sentito)"
        return "\n".join(
            f"  {p.speaker_id:>4}  {p.battute:>3} battute  "
            f"da {p.prima_volta:7.1f}s a {p.ultima_volta:7.1f}s  "
            f"f0 {p.f0:5.0f} Hz -> {p.gender}"
            for p in self.people
        )


# -- l'intonazione, che serve solo a scegliere maschile o femminile ---------


def stima_f0(x: np.ndarray, samplerate: int, lo: float = 60.0, hi: float = 300.0) -> float:
    """Intonazione mediana delle finestre sonore, in Hz. Zero se non si sa.

    Autocorrelazione su finestre di 40 ms. Non e' un estrattore raffinato e non
    deve esserlo: l'unica domanda a cui risponde e' "voce maschile o femminile",
    cioe' quale meta' del pool guardare. La mediana invece della media perche'
    sbagliare ottava e' l'errore tipico qui, e un solo raddoppio trascina una
    media abbastanza da cambiare risposta.
    """
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    n = int(0.04 * samplerate)
    hop = max(1, n // 2)
    if x.size < n:
        return 0.0
    a, b = int(samplerate / hi), int(samplerate / lo)
    if b <= a or b >= n:
        return 0.0
    valori = []
    for i in range(0, x.size - n, hop):
        w = x[i : i + n] - x[i : i + n].mean()
        if float(np.sqrt(np.mean(w**2))) < 0.005:
            continue
        r = np.correlate(w, w, "full")[n - 1 :]
        r = r / (r[0] + 1e-12)
        k = int(np.argmax(r[a:b])) + a
        if r[k] > 0.35:
            valori.append(samplerate / k)
    return float(np.median(valori)) if len(valori) >= 3 else 0.0
