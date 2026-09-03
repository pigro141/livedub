"""Le lingue di Google Translate, **scritte nel repo e non scaricate**.

Serve a una cosa sola: far scegliere la lingua da un elenco invece che da una
casella in cui digitare `ja`. Il codice ISO e' un valore che nessuno puo'
inventare — la stessa famiglia di `vision.roi` e di `translate.color`, per cui
`ui/qt_controlli.py` esiste.

## Perche' l'elenco sta qui e non si chiede alla rete

Google pubblica l'elenco da un endpoint. Prenderlo di la' vuol dire che **senza
rete il menu e' vuoto**, e un menu vuoto non da' errore: da' una finestra in cui
la lingua non si puo' scegliere e nessuno sa perche'. E' la forma del ripiego
silenzioso gia' pagata in questo progetto con `preload_dlls()`. Un elenco fermo
invecchia — Google aggiunge lingue — ma invecchia **in modo visibile**: manca una
voce, e si aggiunge una riga qui.

## I codici sono quelli di Google, e non sono gli unici in giro

`zh-CN`, `iw`, `jw`: Google usa questi. Argos usa `zh`, `he`, `jv`; il template
di TranslateGemma usava `zh-Hans`. Scrivere due tabelle vorrebbe dire due posti
che dicono la stessa cosa, e il secondo non lo aggiorna nessuno — quindi c'e'
**una** tabella, in codici Google, piu' un `ALIAS` che ci riporta dentro cio' che
e' stato scritto altrove. Un codice fuori da tutti e due **non si sostituisce**:
si mostra com'e', perche' un valore corretto di nascosto e' una sessione che gira
con una configurazione diversa da quella che si legge.

## Chi sa fare cosa: `copertura()`

Il pezzo che conta piu' dell'elenco. Google le fa tutte; `locale` (Argos) esiste
solo per **coppie** pubblicate; `llm` e `ollama` dipendono dal modello montato.
Un menu che offre centotrentatre lingue a un backend che ne fa due consegna una
battuta muta o non tradotta **senza dire perche'**, che e' esattamente il difetto
contro cui esiste il pannello delle impostazioni.

La forma scelta e' **mostrarle tutte e dichiarare**, non filtrare. Filtrare
richiederebbe un elenco chiuso per ogni backend, e per tre backend su quattro
quell'elenco **non esiste**: la lingua che Argos non ha installato si scarica ad
Avvia, e quello che un modello sappia davvero fare non e' misurato qui. Un
filtro costruito su un elenco inventato toglierebbe scelte che funzionano e
lascerebbe passare quelle che non funzionano, con l'aria di sapere. Quindi
`copertura()` torna un elenco chiuso **solo dove e' chiuso davvero** (Google), e
altrove torna `None` piu' la frase che dice da cosa dipende.
"""

from __future__ import annotations

from dataclasses import dataclass

# `auto` non e' una lingua: e' «riconoscila tu». Sta qui perche' e' un valore
# ammesso di `translate.source` e va trattato insieme alle altre, non a parte.
AUTO = "auto"


@dataclass(frozen=True, slots=True)
class Lingua:
    """Un codice, e come si chiama nelle due lingue che servono qui.

    L'italiano e' quello che l'utente legge nel menu; l'inglese e' quello che
    finisce **dentro il prompt** di TranslateGemma, che vuole il nome per esteso
    e non il codice (`translate/ollama.py`).
    """

    codice: str
    italiano: str
    inglese: str

    @property
    def etichetta(self) -> str:
        """`Giapponese (ja)` — il nome per chi legge, il codice per chi cerca."""
        return f"{self.italiano} ({self.codice})"


# Le lingue di Google Translate. **In ordine di codice nel sorgente e ordinate
# per nome alla fine**: cosi' aggiungerne una e' una riga sola e nessuno deve
# tenere l'ordine alfabetico italiano a mano — che e' il modo in cui un elenco
# scritto si scolla da se' stesso.
_GREZZE: tuple[Lingua, ...] = (
    Lingua("af", "Afrikaans", "Afrikaans"),
    Lingua("ak", "Twi", "Twi"),
    Lingua("am", "Amarico", "Amharic"),
    Lingua("ar", "Arabo", "Arabic"),
    Lingua("as", "Assamese", "Assamese"),
    Lingua("ay", "Aymara", "Aymara"),
    Lingua("az", "Azero", "Azerbaijani"),
    Lingua("be", "Bielorusso", "Belarusian"),
    Lingua("bg", "Bulgaro", "Bulgarian"),
    Lingua("bho", "Bhojpuri", "Bhojpuri"),
    Lingua("bm", "Bambara", "Bambara"),
    Lingua("bn", "Bengalese", "Bengali"),
    Lingua("bs", "Bosniaco", "Bosnian"),
    Lingua("ca", "Catalano", "Catalan"),
    Lingua("ceb", "Cebuano", "Cebuano"),
    Lingua("ckb", "Curdo (sorani)", "Kurdish (Sorani)"),
    Lingua("co", "Corso", "Corsican"),
    Lingua("cs", "Ceco", "Czech"),
    Lingua("cy", "Gallese", "Welsh"),
    Lingua("da", "Danese", "Danish"),
    Lingua("de", "Tedesco", "German"),
    Lingua("doi", "Dogri", "Dogri"),
    Lingua("dv", "Divehi", "Dhivehi"),
    Lingua("ee", "Ewe", "Ewe"),
    Lingua("el", "Greco", "Greek"),
    Lingua("en", "Inglese", "English"),
    Lingua("eo", "Esperanto", "Esperanto"),
    Lingua("es", "Spagnolo", "Spanish"),
    Lingua("et", "Estone", "Estonian"),
    Lingua("eu", "Basco", "Basque"),
    Lingua("fa", "Persiano", "Persian"),
    Lingua("fi", "Finlandese", "Finnish"),
    Lingua("fr", "Francese", "French"),
    Lingua("fy", "Frisone", "Frisian"),
    Lingua("ga", "Irlandese", "Irish"),
    Lingua("gd", "Gaelico scozzese", "Scots Gaelic"),
    Lingua("gl", "Galiziano", "Galician"),
    Lingua("gn", "Guarani", "Guarani"),
    Lingua("gom", "Konkani", "Konkani"),
    Lingua("gu", "Gujarati", "Gujarati"),
    Lingua("ha", "Hausa", "Hausa"),
    Lingua("haw", "Hawaiano", "Hawaiian"),
    Lingua("hi", "Hindi", "Hindi"),
    Lingua("hmn", "Hmong", "Hmong"),
    Lingua("hr", "Croato", "Croatian"),
    Lingua("ht", "Creolo haitiano", "Haitian Creole"),
    Lingua("hu", "Ungherese", "Hungarian"),
    Lingua("hy", "Armeno", "Armenian"),
    Lingua("id", "Indonesiano", "Indonesian"),
    Lingua("ig", "Igbo", "Igbo"),
    Lingua("ilo", "Ilocano", "Ilocano"),
    Lingua("is", "Islandese", "Icelandic"),
    Lingua("it", "Italiano", "Italian"),
    Lingua("iw", "Ebraico", "Hebrew"),
    Lingua("ja", "Giapponese", "Japanese"),
    Lingua("jw", "Giavanese", "Javanese"),
    Lingua("ka", "Georgiano", "Georgian"),
    Lingua("kk", "Kazako", "Kazakh"),
    Lingua("km", "Khmer", "Khmer"),
    Lingua("kn", "Kannada", "Kannada"),
    Lingua("ko", "Coreano", "Korean"),
    Lingua("kri", "Krio", "Krio"),
    Lingua("ku", "Curdo (kurmanji)", "Kurdish (Kurmanji)"),
    Lingua("ky", "Kirghiso", "Kyrgyz"),
    Lingua("la", "Latino", "Latin"),
    Lingua("lb", "Lussemburghese", "Luxembourgish"),
    Lingua("lg", "Luganda", "Luganda"),
    Lingua("ln", "Lingala", "Lingala"),
    Lingua("lo", "Lao", "Lao"),
    Lingua("lt", "Lituano", "Lithuanian"),
    Lingua("lus", "Mizo", "Mizo"),
    Lingua("lv", "Lettone", "Latvian"),
    Lingua("mai", "Maithili", "Maithili"),
    Lingua("mg", "Malgascio", "Malagasy"),
    Lingua("mi", "Maori", "Maori"),
    Lingua("mk", "Macedone", "Macedonian"),
    Lingua("ml", "Malayalam", "Malayalam"),
    Lingua("mn", "Mongolo", "Mongolian"),
    Lingua("mni-Mtei", "Meitei (manipuri)", "Meiteilon (Manipuri)"),
    Lingua("mr", "Marathi", "Marathi"),
    Lingua("ms", "Malese", "Malay"),
    Lingua("mt", "Maltese", "Maltese"),
    Lingua("my", "Birmano", "Myanmar (Burmese)"),
    Lingua("ne", "Nepalese", "Nepali"),
    Lingua("nl", "Olandese", "Dutch"),
    Lingua("no", "Norvegese", "Norwegian"),
    Lingua("nso", "Sepedi", "Sepedi"),
    Lingua("ny", "Chichewa", "Chichewa"),
    Lingua("om", "Oromo", "Oromo"),
    Lingua("or", "Odia", "Odia (Oriya)"),
    Lingua("pa", "Punjabi", "Punjabi"),
    Lingua("pl", "Polacco", "Polish"),
    Lingua("ps", "Pashtu", "Pashto"),
    Lingua("pt", "Portoghese", "Portuguese"),
    Lingua("qu", "Quechua", "Quechua"),
    Lingua("ro", "Rumeno", "Romanian"),
    Lingua("ru", "Russo", "Russian"),
    Lingua("rw", "Kinyarwanda", "Kinyarwanda"),
    Lingua("sa", "Sanscrito", "Sanskrit"),
    Lingua("sd", "Sindhi", "Sindhi"),
    Lingua("si", "Singalese", "Sinhala"),
    Lingua("sk", "Slovacco", "Slovak"),
    Lingua("sl", "Sloveno", "Slovenian"),
    Lingua("sm", "Samoano", "Samoan"),
    Lingua("sn", "Shona", "Shona"),
    Lingua("so", "Somalo", "Somali"),
    Lingua("sq", "Albanese", "Albanian"),
    Lingua("sr", "Serbo", "Serbian"),
    Lingua("st", "Sesotho", "Sesotho"),
    Lingua("su", "Sundanese", "Sundanese"),
    Lingua("sv", "Svedese", "Swedish"),
    Lingua("sw", "Swahili", "Swahili"),
    Lingua("ta", "Tamil", "Tamil"),
    Lingua("te", "Telugu", "Telugu"),
    Lingua("tg", "Tagiko", "Tajik"),
    Lingua("th", "Thai", "Thai"),
    Lingua("ti", "Tigrino", "Tigrinya"),
    Lingua("tk", "Turkmeno", "Turkmen"),
    Lingua("tl", "Filippino", "Filipino"),
    Lingua("tr", "Turco", "Turkish"),
    Lingua("ts", "Tsonga", "Tsonga"),
    Lingua("tt", "Tataro", "Tatar"),
    Lingua("ug", "Uiguro", "Uyghur"),
    Lingua("uk", "Ucraino", "Ukrainian"),
    Lingua("ur", "Urdu", "Urdu"),
    Lingua("uz", "Uzbeko", "Uzbek"),
    Lingua("vi", "Vietnamita", "Vietnamese"),
    Lingua("xh", "Xhosa", "Xhosa"),
    Lingua("yi", "Yiddish", "Yiddish"),
    Lingua("yo", "Yoruba", "Yoruba"),
    Lingua("zh-CN", "Cinese semplificato", "Chinese (Simplified)"),
    Lingua("zh-TW", "Cinese tradizionale", "Chinese (Traditional)"),
    Lingua("zu", "Zulu", "Zulu"),
)

# **In ordine alfabetico italiano**, che e' l'ordine in cui si cerca con l'occhio.
# Ordinare qui e non a mano vuol dire che una lingua aggiunta in fondo a `_GREZZE`
# compare al posto giusto senza che nessuno se lo ricordi.
LINGUE: tuple[Lingua, ...] = tuple(sorted(_GREZZE, key=lambda x: x.italiano.lower()))

PER_CODICE: dict[str, Lingua] = {x.codice: x for x in LINGUE}

# **I codici scritti altrove che vogliono dire una di queste.** Non e' cortesia:
# `zh-Hans` sta in un profilo o in un vecchio `--set`, e senza questa tabella
# diventerebbe una lingua sconosciuta — cioe' un avviso su una scelta che
# funziona. La chiave e' scritta in minuscolo perche' `normalizza` confronta
# cosi': `ZH-HANS` e `zh-hans` sono lo stesso refuso.
ALIAS: dict[str, str] = {
    "zh": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hant": "zh-TW",
    "zh-tw": "zh-TW",
    "he": "iw",            # ISO moderno -> quello che usa Google
    "jv": "jw",
    "nb": "no",
    "nn": "no",
    "fil": "tl",
    "pt-br": "pt",
    "pt-pt": "pt",
    "mni": "mni-Mtei",
    "mni-mtei": "mni-Mtei",
    "in": "id",            # vecchio codice Java per l'indonesiano
    "ji": "yi",
}


def normalizza(codice: str) -> str:
    """Il codice di questa tabella, se quello dato ne e' un altro nome.

    **Un codice che non si riconosce torna com'e'**, ripulito e basta. Mapparlo
    su un ripiego «ragionevole» sarebbe la sesta volta in questo progetto che una
    correzione silenziosa fa girare una sessione con un valore diverso da quello
    scritto: qui chi lo riceve deve poter dire «questa non la conosco».
    """
    pulito = (codice or "").strip()
    if not pulito:
        return ""
    if pulito in PER_CODICE or pulito == AUTO:
        return pulito
    basso = pulito.lower()
    if basso == AUTO:
        return AUTO
    if basso in ALIAS:
        return ALIAS[basso]
    # `IT` e `it-IT` sono l'italiano; `it_IT` pure, che e' come lo scrive Piper.
    corto = basso.replace("_", "-").split("-")[0]
    if basso in PER_CODICE:
        return basso
    if corto in PER_CODICE:
        return corto
    return pulito


def lingua(codice: str) -> Lingua | None:
    """La voce della tabella, o `None` se quel codice non c'e'."""
    return PER_CODICE.get(normalizza(codice))


def nome_it(codice: str) -> str:
    """Il nome italiano, o il codice stesso se non si conosce."""
    x = lingua(codice)
    return x.italiano if x is not None else (codice or "")


def nome_en(codice: str) -> str:
    """Il nome inglese — quello che va **dentro il prompt** di un modello.

    Un modello a cui si chiede «translate into ja» traduce peggio (o non
    traduce) rispetto a «translate into Japanese», e non lo dice: consegna una
    battuta plausibile nella lingua sbagliata. Il ripiego sul codice resta per le
    lingue fuori tabella, ma e' un ripiego e non il caso normale.
    """
    x = lingua(codice)
    return x.inglese if x is not None else (codice or "")


def etichetta(codice: str) -> str:
    """Come si scrive una lingua nel menu: `Giapponese (ja)`."""
    if normalizza(codice) == AUTO:
        return "auto — riconoscila da sola"
    x = lingua(codice)
    return x.etichetta if x is not None else f"{codice} (?)"


# ------------------------------------------------------ chi sa fare cosa --


@dataclass(frozen=True, slots=True)
class Copertura:
    """Quali lingue un backend dichiara di saper fare, e cosa dirne.

    `codici is None` **non vuol dire «tutte»**: vuol dire «non c'e' un elenco
    chiuso», ed e' la ragione per cui esiste `nota`. Confondere le due cose
    sarebbe promettere centotrentatre lingue a un modello che ne fa due.
    """

    codici: frozenset[str] | None
    auto: bool          # capisce `auto` come lingua di partenza?
    nota: str           # la frase che l'utente deve leggere, o vuota

    def sa_fare(self, codice: str) -> bool:
        """Vero se quel codice **non** e' fra quelli che questo backend non fa.

        Col dubbio si risponde di si': marcare una scelta che potrebbe
        funzionare e' rumore, e il rumore fa smettere di leggere gli avvisi
        veri — la stessa ragione per cui una riga di log di errore non e' rossa.
        """
        c = normalizza(codice)
        if c == AUTO:
            return self.auto
        if self.codici is None:
            return True
        return c in self.codici


# Tutte quelle della tabella: e' l'unico elenco davvero chiuso che ci sia qui.
TUTTE: frozenset[str] = frozenset(PER_CODICE)

# **Le note, una per backend, e ognuna dice da cosa dipende.** Sono scritte qui e
# non nella finestra perche' sono una regola: le regole di questo progetto stanno
# fuori da Qt, dove si possono verificare senza aprire niente.
_NOTE = {
    "locale": (
        "Argos traduce **coppie** installate: quella che manca si scarica ad "
        "Avvia, e se non e' pubblicata la battuta resta in lingua originale."
    ),
    "llm": (
        "Quali lingue faccia davvero dipende dal modello montato "
        "(`translate.llm_model`), e non e' misurato qui."
    ),
    "ollama": (
        "Quali lingue faccia davvero dipende dal modello montato "
        "(`translate.ollama_model`), e non e' misurato qui."
    ),
    "nessuno": "La traduzione e' spenta: questa scelta non fa niente.",
}

_SENZA_AUTO = (
    " `auto` non lo capisce: diventa `en` (`translate/locale.py`, `coppia()`)."
)

# **La stessa cosa detta per prima**, per chi ha `auto` scritto adesso.
#
# Il difetto non era che mancasse l'avviso: c'era, ed e' la coda di `_SENZA_AUTO`
# — cioe' il **fondo** di una riga lunga centosessanta caratteri, dentro
# un'etichetta `Elidibile` che si accorcia coi puntini. A schermo si leggeva
# «⚠ Argos traduce coppie installate:…» e la meta' che conta, quella che dice che
# la lingua di partenza **non e' quella scelta**, non compariva mai. Una misura
# che non puo' esprimere la risposta va cambiata, non interpretata: qui la
# risposta e' l'ordine delle parole.
# **Corta apposta.** L'etichetta che la porta e' larga poco piu' di duecento
# pixel: misurato a schermo, ci stanno una trentina di caratteri prima dei
# puntini. Quindi la risposta — *quale lingua verra' usata davvero* — sta nelle
# prime quattordici, e la spiegazione viene dopo, dove puo' anche non leggersi.
AUTO_DIVENTA = (
    "«auto» diventa «en»: si traduce dall'inglese, non dalla lingua che c'e' "
    "scritta a schermo."
)


def nota_per(backend: str, codice: str) -> str:
    """La frase da mettere sotto la casella per **questa** lingua di partenza.

    E' una regola, quindi sta qui e non in Qt: cosa dire dipende dal backend e
    dal codice, non da come e' fatta la finestra. Con `auto` su un backend che
    non lo capisce, la conseguenza viene **prima** della spiegazione — e' l'unica
    cosa che l'utente deve leggere, e nell'ordine di prima finiva sotto i
    puntini di sospensione.
    """
    cop = copertura(backend)
    if normalizza(codice) != AUTO or cop.auto:
        return cop.nota
    # La coda tecnica dice gia' la stessa cosa, e ripeterla farebbe una riga
    # ancora piu' lunga: si toglie di li' e si mette davanti, detta a parole.
    resto = cop.nota.replace(_SENZA_AUTO.strip(), "").strip()
    return AUTO_DIVENTA + (f" {resto}" if resto else "")


def copertura(backend: str) -> Copertura:
    """Cosa dichiara di saper fare il backend scelto.

    **`auto` e' la parte certa e vale per tre backend su quattro.** Solo Google
    riconosce la lingua da solo; gli altri ricevono una coppia gia' risolta, e
    `translate/locale.py::coppia()` trasforma `auto` in `en` — cioe' chi lascia
    `auto` con un backend offline traduce **dall'inglese**, qualunque cosa ci sia
    scritto a schermo. E' scritto nel codice da sempre; qui si vede.
    """
    nome = (backend or "").strip().lower()
    if nome in ("nessuno", "none", ""):
        return Copertura(codici=None, auto=True, nota=_NOTE["nessuno"])
    if nome == "google":
        # L'unico elenco chiuso: Google le fa tutte quelle di questa tabella e
        # niente altro. Un codice inventato viene marcato, ed e' giusto — li'
        # l'endpoint risponde con il testo non tradotto e nessuno lo direbbe.
        return Copertura(codici=TUTTE, auto=True, nota="")
    if nome in ("locale", "local", "argos"):
        return Copertura(codici=None, auto=False, nota=_NOTE["locale"] + _SENZA_AUTO)
    if nome == "prova":
        # Il traduttore finto del banco rimanda il testo in maiuscolo: la lingua
        # non la guarda nemmeno, e dirlo evita di leggere una prova come una misura.
        return Copertura(codici=None, auto=True,
                         nota="Traduttore finto: rimanda il testo in maiuscolo, "
                              "la lingua non la guarda.")
    nota = _NOTE.get(nome, "Backend sconosciuto: quali lingue faccia non si sa.")
    return Copertura(codici=None, auto=False, nota=nota + _SENZA_AUTO)
