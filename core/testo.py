"""La chiave con cui due scritte si confrontano — **in qualunque scrittura**.

## Il difetto, e perche' non dava errore

Due posti fanno la stessa cosa e la fanno con la stessa riga:
`re.sub(r"[^a-z0-9]", "", ...)` dopo aver sciolto gli accenti.
`core/pipeline.py::_lettere` la usa per il cancello anti-doppioni,
`vision/label.py::_normalizza` per riconoscere il nome di chi parla.

Su una battuta latina funziona. Su `У меня нет времени` torna **la stringa
vuota**, e il chiamante ha scritto — giustamente — `if not chiave: return False`:
il cancello si **spegne**. Non salta, non protesta, non conta niente. Su una
scena giapponese o russa ogni battuta ripetuta dall'OCR viene detta due volte, e
`dub.repeated` resta a zero — che e' esattamente il sintomo con cui la settima
volta di questa stessa forma e' stata trovata (la traduzione che confrontava
`abbracciami` con `hugme`).

Il nome di chi parla e' anche peggio: `_normalizza("ミカエル")` e' vuota, quindi
**tutti** i nomi non latini collassano sulla stessa chiave vuota e diventano lo
stesso personaggio — un solo `speaker_id` per tutto il cast, con una voce sola.

## La regola giusta: si toglie cio' che non porta informazione, non cio' che non e' latino

`str.isalnum()` risponde di si' su `У`, su `меня`, su `한`, su `ة` e su `٣`.
Quindi la chiave e' «tieni gli alfanumerici Unicode, sciogli gli accenti,
minuscolo».

**Sull'italiano da esattamente la stessa risposta di prima**, ed e' il vincolo
che rende questa una correzione e non un cambio di comportamento: la verifica
rigira la vecchia regola accanto alla nuova su tredici scritte vere prese da
questo repo e pretende che coincidano.

Dove **non** coincide, e' deliberato e migliora: le lettere latine che `NFKD` non
scioglie in ASCII sparivano. Misurato, `'Straße' -> 'strae'`, `'Blåbær' ->
'blabr'`, `'Łódź' -> 'odz'` — cioe' in tedesco, norvegese e polacco il cancello
anti-doppioni confrontava parole a cui mancava una lettera su sei. Adesso sono
`'strasse'`, `'blabær'`, `'łodz'`.

## Cosa **non** e' cambiato, ed e' deliberato

`vision/ocr.py::italian_only` continua a buttare i glifi non latini: quello e' un
filtro sul **contenuto letto**, scritto contro i glifi CJK che RapidOCR inventa
sullo scenario, ed e' misurato. Questa e' un'altra domanda — «due scritte sono
la stessa?» — e rispondere «no» perche' non sono latine e' la stessa confusione
di unita' gia' pagata sette volte qui.

## E `NFKD` prima di `casefold`, in quest'ordine

`casefold` e non `lower`: in tedesco `ß` e `SS` sono la stessa parola per il
confronto, e `lower` no. Ma `casefold` va fatto **dopo** aver sciolto gli
accenti, se no `İ` (la i turca con il punto) si scioglie in `i` piu' un segno che
`casefold` non ha piu' modo di guardare.
"""

from __future__ import annotations

import unicodedata


def chiave(testo: str) -> str:
    """Solo lettere e cifre, minuscole, accenti sciolti. **In ogni scrittura.**

    Fra due letture della stessa battuta cio' che cambia di piu' e' la
    punteggiatura che l'OCR inventa sui bordi dei glifi: `'Via! Via!'` e
    `'Via, Via.'` sono la stessa frase, e un confronto letterale direbbe di no.
    Stessa normalizzazione di `NormalizeTextForHash` in RSTGameTranslation, meno
    l'ipotesi che il gioco scriva in latino.
    """
    piatto = unicodedata.normalize("NFKD", testo or "")
    # `isalnum()` su un carattere combinante e' `False`, quindi lo scioglimento
    # degli accenti e la selezione sono la stessa passata: non serve un secondo
    # filtro su `unicodedata.combining`.
    return "".join(c for c in piatto if c.isalnum()).casefold()


def vuota(testo: str) -> bool:
    """Vero se non resta niente da confrontare.

    Esiste per essere **chiamata al posto di `if not chiave(...)`**: quel
    controllo e' il punto in cui il cancello si spegne, e con un nome suo si
    vede nel sorgente che spegnersi e' una decisione e non un caso.
    """
    return not chiave(testo)
