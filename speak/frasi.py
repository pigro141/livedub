"""Una frase per lingua, **nella sua scrittura**, per misurare il passo.

Sta qui e non dentro uno strumento perche' la usano in tre — il censimento
(`tools/censisci_voci.py`, `tools/censisci_lingue.py`) e il banco del passo 6
(`core/banco.py`) — e tre copie della stessa tabella sono tre copie che si
scollano. E' la stessa ragione per cui `lingua_parlata` sta in `core/banco.py`
invece che ripetuta in tre file.

**Perche' la scrittura conta.** Misurare il passo dello spagnolo su una frase
italiana non e' impreciso: e' misurare un'altra cosa. La fonemizzazione e'
esattamente cio' che si sta provando, e darle il testo sbagliato misura
l'errore che si cerca. Il caso limite e' stato misurato: dando a Kokoro
configurato per il giapponese la battuta italiana del banco, `misaki` la
restituisce **verbatim** (`Oggi recuperiamo…` -> `Oi recuperiamo…`, con la `gg`
buttata dal filtro sul vocabolario) e il passo che ne esce e' **12,95 car/s**,
cioe' il numero *italiano* — mentre il giapponese vero, misurato, fa 5,9. La
misura non era imprecisa: non poteva esprimere la risposta.

**Le frasi non sono tutte uguali per provenienza**, e va detto. Le trentaquattro
piu' vecchie vengono da `tools/censisci_voci.py` e sono quelle su cui sono state
misurate le tabelle `PASSO_LINGUA` dei backend: **non si toccano**, perche'
cambiarle vorrebbe dire che ogni numero misurato si riferisce a un'altra frase.
Alcune di loro sono scritte senza segni diacritici (`Manana por la manana`), che
era una scelta di allora; le venti aggiunte dopo hanno l'ortografia giusta,
perche' la fonemizzazione e' il soggetto della misura. La differenza sta scritta
qui invece che nascosta dietro una tabella dall'aria uniforme.

Il contenuto e' lo stesso in tutte: *domani mattina andiamo in centro a
prendere la macchina*. Una frase sola non e' una scena — chi doppia sul serio in
una di queste lingue rimisuri sul materiale vero.
"""

from __future__ import annotations

# Le trentaquattro storiche, **identiche** a quelle su cui sono stati misurati i
# `PASSO_LINGUA` dei tre backend. Copiarle qui e cambiarne una vorrebbe dire
# scollare la misura dal numero: si veda la testata.
_STORICHE: dict[str, str] = {
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

# Le venti aggiunte il 2026-09-05, cioe' le lingue che i cataloghi dichiarano e
# che **non erano misurabili perche' non c'era la frase**. Nessun `PASSO_LINGUA`
# dipende ancora da queste: chi ne misura una la scriva accanto al suo numero.
_AGGIUNTE: dict[str, str] = {
    "bn": "আগামীকাল সকালে আমরা গাড়ি আনতে শহরে যাব।",
    "ca": "Demà al matí anem al centre a recollir el cotxe.",
    "cy": "Bore yfory rydyn ni'n mynd i'r dref i nôl y car.",
    "eu": "Bihar goizean hirira joango gara autoa hartzera.",
    "fa": "فردا صبح برای گرفتن ماشین به مرکز شهر می‌رویم.",
    "hy": "Վաղը առավոտյան մենք քաղաք ենք գնում մեքենան վերցնելու։",
    "is": "Á morgun förum við í bæinn til að sækja bílinn.",
    "ka": "ხვალ დილით ქალაქში მივდივართ მანქანის წასაღებად.",
    "kk": "Ертең таңертең біз көлікті алуға қалаға барамыз.",
    "ku": "Sibê serê sibê em diçin navenda bajêr da ku otomobîlê bînin.",
    "lb": "Muer de Moie gi mir an d'Stad fir den Auto ze huelen.",
    "ml": "നാളെ രാവിലെ ഞങ്ങൾ കാർ എടുക്കാൻ നഗരത്തിലേക്ക് പോകും.",
    "mr": "उद्या सकाळी आम्ही गाडी आणायला शहरात जाऊ.",
    "ne": "भोलि बिहान हामी गाडी लिन सहर जान्छौं।",
    "no": "I morgen tidlig drar vi til byen for å hente bilen.",
    "sq": "Nesër në mëngjes shkojmë në qendër për të marrë makinën.",
    "sr": "Сутра ујутру идемо у центар по ауто.",
    "sw": "Kesho asubuhi tunakwenda katikati ya jiji kuchukua gari.",
    "te": "రేపు ఉదయం మేము కారు తీసుకోవడానికి నగరానికి వెళ్తాము.",
    "ur": "کل صبح ہم گاڑی لینے شہر جائیں گے۔",
}

FRASI: dict[str, str] = {**_STORICHE, **_AGGIUNTE}

# Quali frasi hanno gia' fatto da base a un numero scritto in un `PASSO_LINGUA`.
# Serve a chi legge una tabella e vuole sapere se sta guardando una misura o un
# ordine di grandezza.
STORICHE: frozenset[str] = frozenset(_STORICHE)


def famiglia(lingua: str) -> str:
    """`pt-BR`, `zh_CN`, `IT` -> il codice a due lettere con cui si indicizza.

    **La stessa riga di `speak.pool.famiglia_lingua`**, e non e' una copia per
    distrazione: quella sta li' perche' il pool la usa per scegliere le voci, e
    importarla qui legherebbe una tabella di testo al modulo delle voci. La
    verifica `frasi` pretende che le due diano sempre la stessa risposta.
    """
    return (lingua or "it").replace("_", "-").split("-")[0].lower()


def frase(lingua: str) -> str:
    """La frase di prova per quella lingua, o `""` se non ce n'e' una.

    **Vuoto vuol dire «non misurabile», non «misurato male».** Chi la riceve
    deve dichiarare che non ha misurato, non ripiegare sulla frase italiana: e'
    esattamente il ripiego che faceva uscire il passo italiano da una misura
    giapponese.
    """
    return FRASI.get(famiglia(lingua), "")
