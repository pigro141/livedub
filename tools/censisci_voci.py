"""Il censimento delle voci: quali lingue parla davvero ciascun motore.

Due domande, due comandi, e sono **domande diverse**:

    python -m tools.censisci_voci                 # cosa dicono i cataloghi
    python -m tools.censisci_voci --piper         # rigenera il catalogo Piper dall'indice HF
    python -m tools.censisci_voci --misura        # e il passo? sintetizza e cronometra

**Cosa si dichiara e cosa si prova, che non e' la stessa cosa.** Il censimento
dichiara che *esiste una voce e che e' di quella lingua* — un'affermazione che
si verifica leggendo il catalogo del motore, senza ascoltare niente. Non
dichiara che la pronuncia sia buona: quella la giudica un orecchio che conosca
la lingua, e qui non ce n'e' uno.

`--misura` e' il controllo meccanico che costa poco e prende i casi rotti senza
orecchio: per ogni lingua si sintetizza una frase e si guarda **quanti caratteri
di parlato al secondo** ne escono. E' il metodo che ha gia' smascherato un ramo
che non ricampionava — il passo risultava 30 car/s, che non e' la velocita' di
parlato di nessuno. Un numero fuori scala e' l'unica traccia che lascia una
fonemizzazione fatta con le regole sbagliate: il modello risponde, l'audio esce,
i contatori restano verdi.

Il numero che ne esce va anche nelle tabelle `PASSO_LINGUA` dei backend, ed e'
il motivo per cui questo comando non e' solo una diagnosi: e' la quarta volta in
questo progetto che un passo misurato su una lingua viene applicato a un'altra,
e l'ultima ha fatto uscire ogni battuta compressa al tetto in una scena piena a
meta'.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from fuse.timing import spoken_length  # noqa: E402

# **Una frase per lingua, nella sua scrittura.** Non si puo' misurare il passo
# dello spagnolo su una frase italiana: la fonemizzazione e' esattamente cio' che
# si sta provando, e darle il testo sbagliato misurerebbe l'errore che si cerca.
#
# Sono corte apposta — la misura interessante e' il rapporto, non la lunghezza —
# e coprono famiglie diverse: latina, cirillica, greca, araba, devanagari, CJK.
FRASI: dict[str, str] = {
    "it": "Domani mattina andiamo a prendere la macchina in centro.",
    "en": "Tomorrow morning we are going downtown to pick up the car.",
    "es": "Manana por la manana vamos al centro a recoger el coche.",
    "fr": "Demain matin nous allons en ville chercher la voiture.",
    "de": "Morgen frueh fahren wir in die Stadt und holen das Auto.",
    "pt": "Amanha de manha vamos ao centro buscar o carro.",
    "nl": "Morgenochtend gaan we naar het centrum om de auto op te halen.",
    "pl": "Jutro rano jedziemy do centrum po samochod.",
    "cs": "Zitra rano jedeme do centra pro auto.",
    "sv": "I morgon bitti aker vi in till stan och hamtar bilen.",
    "tr": "Yarin sabah arabayi almak icin sehir merkezine gidiyoruz.",
    "ro": "Maine dimineata mergem in centru sa luam masina.",
    "hu": "Holnap reggel bemegyunk a varosba az autoert.",
    "ru": "Завтра утром мы поедем в центр за машиной.",
    "uk": "Завтра вранці ми поїдемо в центр по машину.",
    "bg": "Утре сутринта отиваме в центъра за колата.",
    "el": "Αύριο το πρωί πάμε στο κέντρο να πάρουμε το αυτοκίνητο.",
    "ar": "غدا صباحا سنذهب إلى وسط المدينة لإحضار السيارة.",
    "hi": "कल सुबह हम गाड़ी लेने शहर जाएंगे।",
    "ja": "明日の朝、車を取りに町へ行きます。",
    "ko": "내일 아침에 차를 가지러 시내에 갑니다.",
    "zh": "明天早上我们去市中心取车。",
    "vi": "Sang mai chung toi vao trung tam de lay xe.",
    "id": "Besok pagi kami ke pusat kota untuk mengambil mobil.",
    "fi": "Huomenna aamulla menemme keskustaan hakemaan auton.",
    "da": "I morgen tidlig koerer vi ind til byen efter bilen.",
    "sk": "Zajtra rano ideme do centra po auto.",
    "sl": "Jutri zjutraj gremo v center po avto.",
    "hr": "Sutra ujutro idemo u centar po auto.",
    "lt": "Rytoj ryta vaziuojame i centra pasiimti automobilio.",
    "lv": "Rit no rita brauksim uz centru pec masinas.",
    "et": "Homme hommikul soidame kesklinna autole jarele.",
    "he": "מחר בבוקר ניסע למרכז העיר לקחת את המכונית.",
}

# Fuori da questa fascia il numero non e' «un po' diverso», e' **impossibile**:
# nessuno parla a tre caratteri al secondo e nessuno ne dice quaranta. Un valore
# fuori scala vuol dire che la catena ha fatto qualcosa di diverso da quello che
# dice di fare — non che quella lingua sia strana.
PASSO_MIN, PASSO_MAX = 4.0, 30.0

# Le lingue a scrittura logografica sono l'eccezione **dichiarata**: un carattere
# cinese o giapponese vale una sillaba intera, quindi il passo misurato in
# caratteri e' per forza molto piu' basso. La fascia e' altra, e confonderle
# vorrebbe dire chiamare rotto cio' che funziona.
LOGOGRAFICHE = ("ja", "zh")
PASSO_MIN_LOGO, PASSO_MAX_LOGO = 1.0, 12.0


def fascia(lingua: str) -> tuple[float, float]:
    if lingua in LOGOGRAFICHE:
        return PASSO_MIN_LOGO, PASSO_MAX_LOGO
    return PASSO_MIN, PASSO_MAX


# ------------------------------------------------------- il catalogo Piper --


def rigenera_piper() -> None:
    """Riscrive `speak/backends/piper_voci.py` dall'indice ufficiale.

    Il catalogo sta nel repo apposta — un elenco che dipende dalla rete si
    svuota quando la rete non c'e', e un menu vuoto non da' errore — ma restare
    fermo per sempre e' un altro difetto: questo comando lo rifa' in dieci
    secondi, e il `git diff` dice cosa e' cambiato nell'indice.
    """
    import collections
    import json

    from huggingface_hub import hf_hub_download

    from speak.backends.piper import MODELS_DIR, REPO

    p = hf_hub_download(REPO, "voices.json", local_dir=str(MODELS_DIR))
    indice = json.load(open(p, encoding="utf-8"))
    qual = ("medium", "high", "low", "x_low")
    per_lingua = collections.defaultdict(list)
    for k, v in indice.items():
        per_lingua[v["language"]["family"]].append(k)
    print(f"indice: {len(indice)} voci in {len(per_lingua)} lingue")
    print("(la riscrittura del file si fa a mano: il catalogo e' codice "
          "sorgente, e un generatore che sovrascrive codice sorgente e' il modo "
          "di perdere i commenti scritti sopra)")
    for f in sorted(per_lingua):
        ks = sorted(per_lingua[f], key=lambda k: (indice[k]["num_speakers"] > 1,
                                                  qual.index(indice[k]["quality"]), k))
        print(f"  {f:4} {len(ks):3}  {indice[ks[0]]['language']['name_english']}")


# --------------------------------------------------------------- la misura --


def misura(backend: str, lingue: tuple[str, ...], frasi: int = 1) -> list[tuple]:
    """Per ogni lingua: quanti caratteri di parlato al secondo ne escono.

    Si costruisce **un motore per lingua** e non uno solo: la lingua non e' un
    argomento di `synthesize`, e' una cosa che il motore sa di se stesso — Piper
    monta un modello diverso, Kokoro cambia archivio di stili, SuperTonic cambia
    fonemizzatore. Riusare lo stesso oggetto misurerebbe la lingua di prima.
    """
    from core.config import Config
    from speak.base import make_tts, taglia_silenzio
    from speak.pool import build_pool

    fuori = []
    for lingua in lingue:
        testo = FRASI.get(lingua)
        if not testo:
            fuori.append((backend, lingua, None, None, "nessuna frase di prova"))
            continue
        cfg = Config()
        cfg.tts.backend = backend
        try:
            tts = make_tts(cfg.tts, lingua=lingua, preload=False)
            voci = build_pool(None, max(1, frasi), backend=backend, lingua=lingua)
            durate, costi, caratteri = [], [], []
            for voce in voci[:frasi]:
                t0 = time.perf_counter()
                s = tts.synthesize(testo, voce)
                costi.append((time.perf_counter() - t0) * 1000.0)
                audio = taglia_silenzio(np.asarray(s.audio), s.samplerate)
                durate.append(len(audio) / float(s.samplerate))
                caratteri.append(spoken_length(testo))
            secondi = statistics.median(durate)
            passo = (statistics.median(caratteri) / secondi) if secondi else 0.0
            basso, alto = fascia(lingua)
            nota = "" if basso <= passo <= alto else "FUORI SCALA"
            fuori.append((backend, lingua, passo, statistics.median(costi), nota))
        except Exception as e:  # noqa: BLE001 - qui si censisce, non si corregge
            fuori.append((backend, lingua, None, None, f"{type(e).__name__}: {e}"))
        print(f"  {fuori[-1][1]:4} "
              f"{('%.2f car/s' % fuori[-1][2]) if fuori[-1][2] else '—':>12}  "
              f"{('%.0f ms' % fuori[-1][3]) if fuori[-1][3] else '':>8}  {fuori[-1][4]}",
              flush=True)
    return fuori


def censimento() -> None:
    """Chi parla cosa, secondo i cataloghi. Nessun modello viene aperto."""
    from speak.pool import basi_per, lingue_con_voce

    for backend in ("piper", "supertonic", "kokoro"):
        lingue = lingue_con_voce(backend)
        voci = sum(len(basi_per(backend, x)) for x in lingue)
        print(f"{backend:11} {len(lingue):3} lingue, {voci:4} voci nel pool")
        print(f"            {' '.join(sorted(lingue))}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--piper", action="store_true",
                    help="rilegge l'indice ufficiale delle voci Piper")
    ap.add_argument("--misura", action="store_true",
                    help="sintetizza una frase per lingua e misura il passo")
    ap.add_argument("--backend", default="supertonic",
                    help="quale motore misurare (default: supertonic)")
    ap.add_argument("--lingue", default="",
                    help="quali lingue misurare, separate da virgola "
                         "(default: tutte quelle che hanno una frase di prova)")
    a = ap.parse_args(argv)

    if a.piper:
        rigenera_piper()
        return 0
    if not a.misura:
        censimento()
        return 0

    from speak.pool import lingue_con_voce

    note = set(lingue_con_voce(a.backend))
    scelte = tuple(x.strip() for x in a.lingue.split(",") if x.strip()) or \
        tuple(x for x in FRASI if x in note)
    print(f"{a.backend}: {len(scelte)} lingue")
    esiti = misura(a.backend, scelte)
    rotte = [e for e in esiti if e[4]]
    print(f"\nprovate {len(esiti)}, con un numero plausibile "
          f"{len(esiti) - len(rotte)}, da guardare {len(rotte)}")
    for e in rotte:
        print(f"  ! {e[1]}: {e[4]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
