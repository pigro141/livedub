"""Il catalogo delle voci Piper, **scritto nel repo e non chiesto alla rete**.

Piper pubblica 175 voci in 51 lingue su `rhasspy/piper-voices`, con un indice
(`voices.json`) che dichiara per ognuna lingua, qualita' e numero di parlanti.
Fino a ieri di quell'indice questo progetto conosceva **due righe** — le due
italiane — quindi si traduceva in spagnolo e poi lo leggeva una voce italiana:
un modello fonemizzato con le regole sbagliate, senza nessun errore.

**Perche' l'elenco sta qui e non si scarica.** E' la stessa scelta gia' fatta
per le 133 lingue di Google (`translate/lingue.py`): un elenco che dipende dalla
rete si svuota quando la rete non c'e', e un menu vuoto **non da' errore**. Un
elenco fermo invecchia, ma invecchia in modo visibile — e `tools/censisci_voci.py
--piper` lo rigenera dall'indice ufficiale in dieci secondi.

**Il percorso dentro il repo non e' una tabella, e' una regola.** La chiave di
una voce e' `<codice>-<nome>-<qualita>` e il file sta in
`<famiglia>/<codice>/<nome>/<qualita>/<chiave>.onnx`: verificato su tutte e 175
le voci dell'indice, zero eccezioni. Quindi non c'e' nessuna seconda tabella da
tenere allineata — la stessa forma che ha gia' fatto sbagliare `translate/ollama.py`,
dove tredici nomi di lingua scritti a mano rispondevano `ja` al posto di
«Japanese».

**I modelli a piu' parlanti sono ventisei e valgono 2562 voci.** Un modello solo
ne contiene fino a 904 (`en_US-libritts-high`), scelte con `speaker_id`: e' un
download solo per N voci **native**, che e' sempre meglio di N trasformazioni di
semitono. Si scrivono `chiave#indice` e sono l'unica strada per sei lingue —
bengalese, estone, giapponese, curdo, marathi e serbo — dove Piper **non ha
nemmeno un modello a un parlante**.

**Il sesso della voce l'indice non lo dice, e non si indovina.** Non c'e' un
campo, e dedurlo dal nome proprio richiederebbe un elenco di nomi in cinquanta
lingue. Quindi fuori dall'italiano il genere e' `?`, e il pool ripiega
sull'ordine invece di alternare maschile e femminile: e' un peggioramento
dichiarato, non un difetto nascosto. Misurarlo sarebbe possibile (la f0 di una
frase sintetizzata), ma costerebbe di scaricare tutte e 175 le voci.
"""

from __future__ import annotations

# Le voci di ogni lingua, **in ordine di preferenza**: prima quelle a un solo
# parlante (curate una per una) e a parita' di qualita' `medium` prima di
# `high`, `low` e `x_low`; i modelli a piu' parlanti in fondo, perche' li' la
# qualita' della singola voce non l'ha guardata nessuno.
#
# La chiave della famiglia e' il codice a due lettere, che e' quello con cui
# arriva `translate.target`.
VOCI: dict[str, tuple[str, ...]] = {
    # Arabic
    'ar': (
        'ar_JO-kareem-medium', 'ar_JO-kareem-low',
    ),
    # Bulgarian
    'bg': (
        'bg_BG-dimitar-medium',
    ),
    # Bengali
    'bn': (
        'bn_BD-google-medium',
    ),
    # Catalan
    'ca': (
        'ca_ES-upc_ona-medium', 'ca_ES-upc_ona-x_low',
        'ca_ES-upc_pau-x_low',
    ),
    # Czech
    'cs': (
        'cs_CZ-jirka-medium', 'cs_CZ-kasandra-medium', 'cs_CZ-jirka-low',
    ),
    # Welsh
    'cy': (
        'cy_GB-gwryw_gogleddol-medium', 'cy_GB-bu_tts-medium',
    ),
    # Danish
    'da': (
        'da_DK-talesyntese-medium',
    ),
    # German
    'de': (
        'de_DE-thorsten-medium', 'de_DE-thorsten-high',
        'de_DE-karlsson-low', 'de_DE-kerstin-low', 'de_DE-pavoque-low',
        'de_DE-ramona-low', 'de_DE-thorsten-low', 'de_DE-eva_k-x_low',
        'de_DE-mls-medium', 'de_DE-thorsten_emotional-medium',
    ),
    # Greek
    'el': (
        'el_GR-joy-medium', 'el_GR-rapunzelina-medium',
        'el_GR-rapunzelina-low',
    ),
    # English
    'en': (
        'en_GB-alan-medium', 'en_GB-alba-medium', 'en_GB-cori-medium',
        'en_GB-jenny_dioco-medium', 'en_GB-northern_english_male-medium',
        'en_US-amy-medium', 'en_US-bryce-medium', 'en_US-hfc_female-medium',
        'en_US-hfc_male-medium', 'en_US-joe-medium', 'en_US-john-medium',
        'en_US-kristin-medium', 'en_US-kusal-medium', 'en_US-lessac-medium',
        'en_US-ljspeech-medium', 'en_US-mike-medium', 'en_US-norman-medium',
        'en_US-reza_ibrahim-medium', 'en_US-ryan-medium',
        'en_US-sam-medium', 'en_GB-cori-high', 'en_US-lessac-high',
        'en_US-ljspeech-high', 'en_US-ryan-high', 'en_GB-alan-low',
        'en_GB-southern_english_female-low', 'en_US-amy-low',
        'en_US-danny-low', 'en_US-kathleen-low', 'en_US-lessac-low',
        'en_US-ryan-low', 'en_GB-aru-medium', 'en_GB-semaine-medium',
        'en_GB-vctk-medium', 'en_US-arctic-medium', 'en_US-l2arctic-medium',
        'en_US-libritts_r-medium', 'en_US-libritts-high',
    ),
    # Spanish
    'es': (
        'es_ES-davefx-medium', 'es_MX-ald-medium', 'es_AR-daniela-high',
        'es_MX-claude-high', 'es_ES-mls_10246-low', 'es_ES-mls_9972-low',
        'es_ES-carlfm-x_low', 'es_MX-ald-x_low', 'es_ES-sharvard-medium',
    ),
    # Estonian
    'et': (
        'et_EE-news-medium',
    ),
    # Basque
    'eu': (
        'eu_ES-antton-medium', 'eu_ES-maider-medium',
    ),
    # Farsi
    'fa': (
        'fa_IR-amir-medium', 'fa_IR-ganji-medium',
        'fa_IR-ganji_adabi-medium', 'fa_IR-gyro-medium',
        'fa_IR-reza_ibrahim-medium',
    ),
    # Finnish
    'fi': (
        'fi_FI-harri-medium', 'fi_FI-harri-low',
    ),
    # French
    'fr': (
        'fr_FR-siwis-medium', 'fr_FR-tom-medium', 'fr_FR-gilles-low',
        'fr_FR-mls_1840-low', 'fr_FR-siwis-low', 'fr_FR-mls-medium',
        'fr_FR-upmc-medium',
    ),
    # Hebrew
    'he': (
        'he_IL-saspeech-medium',
    ),
    # Hindi
    'hi': (
        'hi_IN-pratham-medium', 'hi_IN-priyamvada-medium',
        'hi_IN-rohan-medium',
    ),
    # Hungarian
    'hu': (
        'hu_HU-anna-medium', 'hu_HU-berta-medium', 'hu_HU-imre-medium',
    ),
    # Armenian
    'hy': (
        'hy_AM-gor-medium',
    ),
    # Indonesian
    'id': (
        'id_ID-news_tts-medium',
    ),
    # Icelandic
    'is': (
        'is_IS-bui-medium', 'is_IS-salka-medium', 'is_IS-steinn-medium',
        'is_IS-ugla-medium',
    ),
    # Italian
    'it': (
        'it_IT-paola-medium', 'it_IT-serena-medium', 'it_IT-serena-high',
        'it_IT-riccardo-x_low',
    ),
    # Japanese
    'ja': (
        'ja_JA-hi_fi_captain-medium',
    ),
    # Georgian
    'ka': (
        'ka_GE-natia-medium',
    ),
    # Kazakh
    'kk': (
        'kk_KZ-iseke-x_low', 'kk_KZ-raya-x_low', 'kk_KZ-issai-high',
    ),
    # Korean
    'ko': (
        'ko_KR-kss-medium',
    ),
    # Kurmanji Kurdish
    'ku': (
        'ku_TR-berfin_renas-medium',
    ),
    # Luxembourgish
    'lb': (
        'lb_LU-marylux-medium',
    ),
    # Latvian
    'lv': (
        'lv_LV-aivars-medium',
    ),
    # Malayalam
    'ml': (
        'ml_IN-arjun-medium', 'ml_IN-meera-medium',
    ),
    # Marathi
    'mr': (
        'mr_IN-google-medium',
    ),
    # Nepali
    'ne': (
        'ne_NP-chitwan-medium', 'ne_NP-google-medium', 'ne_NP-google-x_low',
    ),
    # Dutch
    'nl': (
        'nl_BE-nathalie-medium', 'nl_BE-rdh-medium', 'nl_NL-alex-medium',
        'nl_NL-pim-medium', 'nl_NL-ronnie-medium', 'nl_NL-mls_5809-low',
        'nl_NL-mls_7432-low', 'nl_BE-nathalie-x_low', 'nl_BE-rdh-x_low',
        'nl_NL-mls-medium',
    ),
    # Norwegian
    'no': (
        'no_NO-talesyntese-medium', 'no_NO-nvcc-medium',
    ),
    # Polish
    'pl': (
        'pl_PL-darkman-medium', 'pl_PL-gosia-medium',
        'pl_PL-mc_speech-medium', 'pl_PL-bass-high', 'pl_PL-mls_6892-low',
    ),
    # Portuguese
    'pt': (
        'pt_BR-cadu-medium', 'pt_BR-faber-medium', 'pt_BR-jeff-medium',
        'pt_PT-tugão-medium', 'pt_BR-edresson-low',
    ),
    # Romanian
    'ro': (
        'ro_RO-mihai-medium',
    ),
    # Russian
    'ru': (
        'ru_RU-denis-medium', 'ru_RU-dmitri-medium', 'ru_RU-irina-medium',
        'ru_RU-ruslan-medium',
    ),
    # Slovak
    'sk': (
        'sk_SK-lili-medium',
    ),
    # Slovenian
    'sl': (
        'sl_SI-artur-medium',
    ),
    # Albanian
    'sq': (
        'sq_AL-edon-medium',
    ),
    # Serbian
    'sr': (
        'sr_RS-serbski_institut-medium',
    ),
    # Swedish
    'sv': (
        'sv_SE-alma-medium', 'sv_SE-lisa-medium', 'sv_SE-nst-medium',
    ),
    # Swahili
    'sw': (
        'sw_CD-lanfrica-medium',
    ),
    # Telugu
    'te': (
        'te_IN-maya-medium', 'te_IN-padmavathi-medium',
        'te_IN-venkatesh-medium',
    ),
    # Turkish
    'tr': (
        'tr_TR-dfki-medium',
    ),
    # Ukrainian
    'uk': (
        'uk_UA-mykyta-high', 'uk_UA-oleksa-high', 'uk_UA-tetiana-high',
        'uk_UA-lada-x_low', 'uk_UA-ukrainian_tts-medium',
    ),
    # Urdu
    'ur': (
        'ur_PK-aegis_female-medium', 'ur_PK-fasih-medium',
    ),
    # Vietnamese
    'vi': (
        'vi_VN-vais1000-medium', 'vi_VN-25hours_single-low',
        'vi_VN-vivos-x_low',
    ),
    # Chinese
    'zh': (
        'zh_CN-chaowen-medium', 'zh_CN-huayan-medium',
        'zh_CN-xiao_ya-medium', 'zh_CN-huayan-x_low',
    ),
}

# Quante voci contiene ciascun modello a piu' parlanti. Serve a sapere fin dove
# puo' arrivare `chiave#indice` senza chiedere niente al disco: un `speaker_id`
# fuori scala non da' errore in Piper, da' **la voce sbagliata**.
MULTI: dict[str, int] = {
    'bn_BD-google-medium': 16,
    'cy_GB-bu_tts-medium': 7,
    'de_DE-mls-medium': 236,
    'de_DE-thorsten_emotional-medium': 8,
    'en_GB-aru-medium': 12,
    'en_GB-semaine-medium': 4,
    'en_GB-vctk-medium': 109,
    'en_US-arctic-medium': 18,
    'en_US-l2arctic-medium': 24,
    'en_US-libritts-high': 904,
    'en_US-libritts_r-medium': 904,
    'es_ES-sharvard-medium': 2,
    'et_EE-news-medium': 4,
    'fr_FR-mls-medium': 125,
    'fr_FR-upmc-medium': 2,
    'ja_JA-hi_fi_captain-medium': 2,
    'kk_KZ-issai-high': 6,
    'ku_TR-berfin_renas-medium': 2,
    'mr_IN-google-medium': 9,
    'ne_NP-google-medium': 18,
    'ne_NP-google-x_low': 18,
    'nl_NL-mls-medium': 52,
    'no_NO-nvcc-medium': 10,
    'sr_RS-serbski_institut-medium': 2,
    'uk_UA-ukrainian_tts-medium': 3,
    'vi_VN-vivos-x_low': 65,
}

# **Cinque voci non si fonemizzano con espeak, e non e' un dettaglio.** Il
# `phoneme_type` sta nel `.onnx.json` di ogni voce e non nell'indice: e' stato
# letto scaricando tutti e 175 quei file (7 KB l'uno), e queste sono le sole
# cinque che non dicono `espeak`.
#
# La riga che conta e' `japanese`: `piper-tts` conosce quattro tipi — espeak,
# text, pinyin, hebrew — e **non quello**. La voce giapponese esiste
# nell'indice, il modello si scarica, e alla prima sintesi solleva
# `ValueError: 'japanese' is not a valid PhonemeType`. Un catalogo che
# dichiarasse «Piper parla giapponese» sarebbe vero sull'indice e falso in
# questo programma, che e' esattamente la forma di verde falso che questo file
# esiste per togliere.
#
# `pinyin` invece funziona, ma solo con `g2pw` installato (non e' nei
# requisiti): le due voci cinesi che lo usano vanno **in fondo**, dopo quelle
# `espeak` della stessa lingua, cosi' chi doppia in cinese non ci inciampa.
# `hebrew` funziona senza nient'altro — misurato, 9,14 car/s — e `text` pure.
SPECIALI: dict[str, str] = {
    "he_IL-saspeech-medium": "hebrew",
    "ja_JA-hi_fi_captain-medium": "japanese",
    "uk_UA-ukrainian_tts-medium": "text",
    "zh_CN-chaowen-medium": "pinyin",
    "zh_CN-xiao_ya-medium": "pinyin",
}

# I tipi che `piper-tts` sa fonemizzare da solo, e quelli che chiedono un
# pacchetto in piu'. Una voce del primo gruppo si usa, una del secondo si tiene
# in fondo, una fuori da tutti e due **non si offre**.
FONEMI_OK: frozenset[str] = frozenset({"espeak", "text", "hebrew"})
FONEMI_CON_EXTRA: dict[str, str] = {"pinyin": "g2pw"}

# Le lingue con almeno una voce **utilizzabile**. Si ricava, non si scrive: un
# secondo elenco e' un elenco che prima o poi non aggiorna nessuno. Il
# giapponese cade qui, ed e' l'unica lingua dell'indice che cade.
LINGUE: tuple[str, ...] = tuple(
    sorted(f for f, ks in VOCI.items()
           if any(SPECIALI.get(k, "espeak") in FONEMI_OK for k in ks))
)


def normale(lingua: str) -> str:
    """`pt-BR`, `zh_CN`, `IT` -> la famiglia a due lettere che il catalogo usa."""
    return (lingua or "it").replace("_", "-").split("-")[0].lower()


def sottopercorso(base: str) -> str:
    """Dove sta quella voce dentro `rhasspy/piper-voices`.

    Si ricava dalla chiave e non da una tabella: si veda la testata.
    """
    chiave = base.split("#")[0]
    pezzi = chiave.split("-")
    if len(pezzi) != 3:
        raise ValueError(f"chiave Piper malformata: {base!r}")
    codice, nome, qualita = pezzi
    return f"{codice.split('_')[0]}/{codice}/{nome}/{qualita}"


def parlante(base: str) -> int:
    """L'indice del parlante dentro un modello a piu' voci. Zero se non c'e'."""
    if "#" not in base:
        return 0
    chiave, n = base.split("#", 1)
    indice = int(n)
    quanti = MULTI.get(chiave, 1)
    if not 0 <= indice < quanti:
        # Un `speaker_id` fuori scala Piper non lo rifiuta: sceglie un vettore
        # qualunque, cioe' consegna **una voce diversa da quella chiesta** con
        # l'audio che esce e i contatori verdi.
        raise ValueError(
            f"parlante {indice} fuori da {chiave!r}, che ne ha {quanti}"
        )
    return indice


def voci_per(lingua: str, quante: int = 6) -> tuple[str, ...]:
    """Al piu' `quante` voci native per quella lingua, in ordine di preferenza.

    **Le native prima delle trasformate, e i download contati.** Ogni modello a
    un parlante e' un file da 28-114 MB: prenderne sei per una lingua vorrebbe
    dire mezzo giga per una scena. Quindi si prendono i modelli a un parlante
    che ci sono e, se non bastano, si aprono i parlanti del primo modello
    multiplo — che di download ne costa **uno solo** per tutte le sue voci.

    Vuoto vuol dire «Piper non parla questa lingua», ed e' una risposta: chi la
    riceve deve cambiare motore, non ripiegare sull'italiano.
    """
    disponibili = VOCI.get(normale(lingua), ())
    # **Un parlante solo per persona.** `de_DE-thorsten-medium` e
    # `de_DE-thorsten-high` sono la **stessa voce** a due qualita': metterle tutte
    # e due in pool vorrebbe dire due personaggi con la voce identica, che e'
    # precisamente il difetto che il pool esiste per evitare. L'indice e'
    # ordinato per qualita', quindi la prima che si incontra e' la migliore.
    # **Si offre solo cio' che questo programma sa fonemizzare da solo.** Le due
    # voci `pinyin` restano fuori dal pool anche se il tipo esiste: senza `g2pw`
    # — che non e' nei requisiti — muoiono alla prima sintesi, e una voce che
    # muore a meta' scena e' peggio di una voce in meno. Il cinese ha comunque le
    # sue voci `espeak`; chi installa `g2pw` guadagna le altre due, e sta scritto
    # in `FONEMI_CON_EXTRA` invece che in nessun posto.
    disponibili = tuple(k for k in disponibili
                        if SPECIALI.get(k, "espeak") in FONEMI_OK)
    visti: set[str] = set()
    singole: list[str] = []
    for k in disponibili:
        if k in MULTI:
            continue
        chi = k.split("-")[1]
        if chi in visti:
            continue
        visti.add(chi)
        singole.append(k)
    scelte = singole[: max(1, quante)] if singole else []
    if len(scelte) < quante:
        for k in disponibili:
            if k not in MULTI:
                continue
            for i in range(min(MULTI[k], quante - len(scelte))):
                scelte.append(f"{k}#{i}")
            if len(scelte) >= quante:
                break
    return tuple(scelte[:quante])
