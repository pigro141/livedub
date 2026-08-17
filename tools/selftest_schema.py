"""Verifiche dell'elenco dei parametri da cui si genera il pannello.

Il pannello delle impostazioni non elenca i campi a mano, li **percorre**. Il
prezzo di quella scelta e' che se il percorso salta un campo, la UI mostra una
configurazione incompleta senza dirlo — che e' il difetto contro cui il percorso
esisteva. Quindi qui non si verifica «lo schema funziona», si verifica **che
copra tutto e che non menta**.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass

from core.config import Config
from core.schema import (
    SENZA_AIUTO_MAX,
    TITOLI,
    Campo,
    campi,
    e_caldo,
    sezioni,
)


def _tutti_i_percorsi(obj, prefisso: str = "") -> list[str]:
    """L'albero percorso a mano, per confrontarlo con quello dello schema.

    Deliberatamente scritto **due volte in modo diverso**: se lo schema e la sua
    verifica usassero la stessa funzione, la verifica non potrebbe fallire.
    """
    fuori: list[str] = []
    for f in fields(obj):
        v = getattr(obj, f.name)
        if is_dataclass(v):
            fuori.extend(_tutti_i_percorsi(v, f"{prefisso}{f.name}."))
        else:
            fuori.append(f"{prefisso}{f.name}")
    return fuori


def test_schema(c) -> None:
    c.group("schema")

    cfg = Config()
    elenco = campi(cfg)
    percorsi = [x.percorso for x in elenco]

    # -- copertura: nessun campo puo' restare fuori dal pannello --------------
    attesi = _tutti_i_percorsi(cfg)
    c.eq(sorted(percorsi), sorted(attesi), "lo schema copre esattamente l'albero di config")
    c.eq(len(percorsi), len(set(percorsi)), "nessun percorso compare due volte")
    c.ok(len(elenco) > 150, f"l'albero ha i suoi campi ({len(elenco)})")

    # -- ogni percorso e' vero: `Config.get` deve saperlo leggere -------------
    rotti = [p for p in percorsi if not _leggibile(cfg, p)]
    c.eq(rotti, [], "ogni percorso dello schema e' leggibile con Config.get")

    # -- il valore mostrato e' quello vero, non una copia stantia -------------
    cfg.set("vision.sat_max", 99)
    x = [k for k in campi(cfg) if k.percorso == "vision.sat_max"][0]
    c.eq(x.valore, 99, "lo schema legge il valore vivo, non il default")
    c.eq(x.default, 60, "e ricorda comunque il default")

    # -- i tipi ---------------------------------------------------------------
    per_nome = {k.percorso: k for k in elenco}
    c.eq(per_nome["vision.exclude_colored"].tipo, "bool", "un booleano e' un booleano")
    c.eq(per_nome["vision.sat_max"].tipo, "int", "un intero e' un intero")
    c.eq(per_nome["timing.rate_max"].tipo, "float", "un reale e' un reale")
    c.eq(per_nome["vision.roi"].tipo, "tuple", "la ROI e' una quaterna")
    c.eq(per_nome["tts.backend"].tipo, "str", "un nome di backend e' una stringa")

    # -- le spiegazioni: estratte, non riscritte ------------------------------
    # **La verifica non e' che ci sia del testo, e' che sia IL testo**: se
    # domani qualcuno le riscrivesse a mano, le misure sparirebbero senza che
    # nessun contatore lo dicesse. Quindi si cerca un pezzo che esiste solo nel
    # commento vero.
    aiuto = per_nome["vision.exclude_colored"].aiuto
    c.ok("1349" in aiuto, "la spiegazione porta con se' la misura che l'ha decisa")
    c.ok("Mafia" in aiuto, "e il caso che l'ha resa necessaria")
    c.ok(
        "misurato" in per_nome["vision.line_pad"].aiuto.lower(),
        "il margine del ritaglio dichiara di essere misurato",
    )
    senza = [k.percorso for k in elenco if not k.aiuto]
    c.ok(
        len(senza) <= SENZA_AIUTO_MAX,
        f"i campi senza spiegazione non sono aumentati ({len(senza)}, tetto {SENZA_AIUTO_MAX})",
    )
    # **Due campi non possono avere la stessa spiegazione.** E' il sintomo di un
    # blocco di commento incollato al campo sbagliato — successo davvero: il
    # commento di `mask_crop`, un campo tolto, era rimasto orfano e finiva
    # attaccato a `line_pad`, che nel pannello spiegava un'altra cosa. A trovarlo
    # e' stato **guardare il pannello**, non leggere il codice.
    from collections import Counter

    doppi = [t for t, n in Counter(k.aiuto for k in elenco if k.aiuto).items() if n > 1]
    c.eq(doppi, [], "nessuna spiegazione e' condivisa da due campi")
    c.ok(
        per_nome["vision.line_pad"].aiuto.startswith("Quanto margine"),
        "e `line_pad` spiega il margine, non la maschera del campo tolto",
    )
    c.ok(
        per_nome["vision.sat_max"].sommario.endswith("dialogo"),
        "il sommario e' una riga sola, per stare accanto alla manopola",
    )

    # -- le scelte, prese dalla convenzione gia' in uso -----------------------
    c.eq(
        per_nome["capture.backend"].scelte,
        ("auto", "wgc", "dxcam", "mss"),
        "`auto | wgc | dxcam | mss` diventa un elenco di scelte",
    )
    c.eq(per_nome["tts.device"].scelte, ("cpu", "cuda", "auto"), "e cosi' il dispositivo")
    # **I quattro selettori di tecnologia escono da qui**, non da un elenco
    # scritto a mano che divergerebbe al primo backend aggiunto.
    c.eq(
        per_nome["tts.backend"].scelte,
        ("piper", "supertonic", "kokoro", "tone", "silent"),
        "i motori di voce vengono dal commento del campo",
    )
    c.eq(
        per_nome["vision.ocr_backend"].scelte, ("ppocr", "oneocr", "none"),
        "e i motori di OCR dal commento **in coda** alla riga",
    )
    c.eq(
        per_nome["translate.backend"].scelte,
        ("locale", "llm", "ollama", "google", "nessuno"),
        "e i traduttori",
    )
    c.eq(
        per_nome["speaker.backend"].scelte, ("ecapa-onnx", "mfcc", "none"),
        "e le impronte di chi parla",
    )
    # **Il valore vero e' la prova che quella riga sia un elenco di valori.**
    # `translate.ollama_model` vale `translategemma:4b` e il suo commento dice
    # `4b | 12b | 27b`: sono le taglie, non i valori, e un menu costruito su di
    # loro scriverebbe `4b` dentro il nome del modello. Il caso e' vero e sta in
    # config: e' lui a tenere onesta questa regola.
    c.eq(
        per_nome["translate.ollama_model"].scelte, (),
        "un elenco che non contiene il valore vero non e' un menu di questo campo",
    )
    fuori_menu = [
        k.percorso for k in elenco if k.scelte and str(k.valore) not in k.scelte
    ]
    c.eq(fuori_menu, [], "e quindi nessun campo mostra un menu che perderebbe il suo valore")
    c.eq(
        per_nome["vision.sat_max"].scelte, (),
        "un numero non ha scelte, anche se il commento contiene delle barre",
    )
    # Una tabella in fondo a un commento non deve diventare un menu a tendina.
    con_tabella = per_nome["vision.exclude_colored"]
    c.eq(con_tabella.scelte, (), "le barre di una tabella non diventano scelte")

    # -- e i campi che manopola non sono ---------------------------------------
    # Il pannello deve saperlo **prima** di disegnarli: una casella che accetta
    # una modifica che non arriva da nessuna parte e' peggio di un campo assente.
    c.eq(per_nome["label.colors"].tipo, "dict", "un dizionario si dichiara per quello che e'")
    c.ok(per_nome["vision.roi"].modificabile, "la ROI si scrive (quaterna di numeri)")

    # **I due dizionari adesso si scrivono, ed erano la funzione principale.**
    # Erano gli unici campi spenti nel pannello, con scritto «non modificabile»:
    # onesto, perche' `_coerce` non li trattava, ma quei due *sono* la tabella
    # dei personaggi — «chi ha quale voce, deciso da te», che vince su ogni
    # assegnazione automatica. Restava dichiarabile solo scrivendo un profilo a
    # mano.
    #
    # La verifica che conta e' il giro di andata e ritorno: `modificabile` da'
    # solo un permesso, e un permesso senza `_coerce` dietro sarebbe di nuovo
    # una casella che accetta una modifica che non arriva da nessuna parte.
    non_scrivibili = [k.percorso for k in elenco if not k.modificabile]
    c.eq(non_scrivibili, [], "nessun campo resta senza manopola")
    prova = Config()
    prova.set("label.voices", {"Franklin": "riccardo"})
    c.eq(prova.label.voices, {"Franklin": "riccardo"}, "un dizionario si scrive come dizionario")
    prova.set("label.voices", "Franklin=riccardo, Lamar Davis=paola")
    c.eq(prova.label.voices, {"Franklin": "riccardo", "Lamar Davis": "paola"},
         "e da `--set`, con i nomi che hanno gli spazi dentro")
    try:
        prova.set("label.colors", "Franklin")
        c.ok(False, "una tabella senza `=` deve fermarsi, non indovinare")
    except ValueError:
        c.ok(True, "e una riga senza `=` e' un errore, non una chiave a caso")

    # -- caldo o freddo: **ogni** campo deve essere classificato ---------------
    # E' la meta' che protegge dal difetto peggiore: cambiare a caldo qualcosa
    # che si legge solo alla costruzione non da' errore, da' una sessione che
    # gira diversa da quella che la UI mostra.
    c.ok(not per_nome["tts.backend"].caldo, "il motore della voce vuole un riavvio")
    c.ok(not per_nome["vision.ocr_backend"].caldo, "e cosi' il motore dell'OCR")
    c.ok(not per_nome["audio.samplerate"].caldo, "e la frequenza dell'anello audio")
    c.ok(not per_nome["capture.fps"].caldo, "e il ritmo della cattura")
    c.ok(per_nome["vision.sat_max"].caldo, "una soglia di colore si cambia a caldo")
    c.ok(per_nome["vision.exclude_colored"].caldo, "e cosi' l'esclusione dei colorati")
    c.ok(per_nome["timing.rate_max"].caldo, "e il tetto della fretta")
    c.ok(per_nome["mix.duck_db"].caldo, "e quanto si abbassa il gioco")
    caldi = sum(1 for k in elenco if k.caldo)
    c.ok(0 < len(elenco) - caldi < len(elenco), f"i due gruppi esistono entrambi ({caldi} caldi)")

    # Un prefisso di sezione vale per tutta la sezione, un percorso solo per se'.
    c.ok(not e_caldo("audio.qualunque_cosa"), "il prefisso `audio.` copre la sezione")
    c.ok(e_caldo("vision.qualunque_cosa"), "ma `vision` non e' freddo in blocco")

    # -- le sezioni hanno tutte un titolo leggibile ---------------------------
    gruppi = sezioni(cfg)
    senza_titolo = [s for s in gruppi if s not in TITOLI]
    c.eq(senza_titolo, [], "ogni sezione ha un titolo per l'utente")
    c.eq(
        sum(len(v) for v in gruppi.values()), len(elenco),
        "raggruppare non perde ne' duplica campi",
    )
    c.ok(
        list(gruppi["vision"])[0].nome == "roi",
        "dentro una sezione resta l'ordine del sorgente, non l'alfabetico",
    )

    # -- e se il sorgente non c'e', si dichiara invece di morire ---------------
    # Succede in un pacchetto costruito senza `core/config.py` fra i dati:
    # l'exe partiva e moriva alla costruzione del pannello. Morire li' vorrebbe
    # dire un programma che non si apre per colpa dei testi d'aiuto; tacere
    # vorrebbe dire un pannello che sembra completo e ha perso tutte le misure.
    # Trovato facendo partire l'exe, non leggendo lo spec.
    import core.schema as _sch

    vero, _sch.SORGENTE = _sch.SORGENTE, _sch.SORGENTE.with_name("non-esiste.py")
    _sch._commenti.cache_clear()
    try:
        orfani = campi(Config())
        c.eq(len(orfani), len(elenco), "senza sorgente i campi ci sono ancora tutti")
        c.eq([k.aiuto for k in orfani if k.aiuto], [], "ma senza spiegazioni, e senza esplodere")
    finally:
        _sch.SORGENTE = vero
        _sch._commenti.cache_clear()
    c.ok(any(k.aiuto for k in campi(Config())), "e col sorgente al suo posto tornano")

    # -- e il giro di andata e ritorno: quello che lo schema mostra si puo' ----
    # riscrivere in config e ritrovarlo uguale. E' la regola della trasformata
    # contro la propria inversa, applicata a un pannello di impostazioni.
    prova = Config()
    for k in campi(prova):
        if not k.modificabile:
            continue
        prova.set(k.percorso, k.valore)
    c.eq(
        [k.valore for k in campi(prova)],
        [k.valore for k in campi(Config())],
        "rileggere e riscrivere ogni campo non cambia niente",
    )


def _leggibile(cfg: Config, percorso: str) -> bool:
    try:
        cfg.get(percorso)
        return True
    except KeyError:
        return False


def test_livelli(c) -> None:
    """I tre livelli dell'utente: base, medio, esperto.

    **Un elenco scritto a mano che si scolla dall'albero e' lo stesso difetto
    contro cui esiste `core/schema.py`.** Se qualcuno rinomina un campo, il
    livello base smette di mostrarlo e non se ne accorge nessuno: la finestra
    sembra piu' semplice e ha perso una manopola.
    """
    from core.config import Config
    from core.schema import BASE, LIVELLI, MEDIO, campi, livello, visibile_a

    c.group("schema")

    elenco = campi(Config())
    noti = {k.percorso for k in elenco}
    c.eq([p for p in BASE if p not in noti], [], "ogni campo del livello base esiste davvero")
    c.eq([p for p in MEDIO if p not in noti], [], "e ogni campo del livello medio")
    c.eq(len(set(BASE)), len(BASE), "nessun doppione nel livello base")
    c.ok(set(BASE) <= set(MEDIO), "il medio contiene il base: i livelli si annidano")

    # I tre livelli devono davvero **nascondere** qualcosa, se no non servono.
    quanti = {liv: sum(1 for k in elenco if visibile_a(k.percorso, liv)) for liv in LIVELLI}
    c.eq(quanti["esperto"], len(elenco), "il livello esperto mostra tutto")
    c.ok(quanti["base"] < quanti["medio"] < quanti["esperto"],
         f"e i tre sono davvero diversi ({quanti})")
    c.ok(8 <= quanti["base"] <= 14,
         f"il livello base sta in una schermata ({quanti['base']} parametri)")

    # Le cose senza cui il programma non si usa **devono** stare nel base.
    for percorso in ("vision.roi", "tts.backend", "vision.exclude_colored"):
        c.eq(livello(percorso), "base", f"{percorso} e' roba da primo avvio")
    # E le tarature no: sono il motivo per cui i livelli esistono.
    for percorso in ("speaker.merge_similarity", "vision.color_word_gap", "timing.learn_decay"):
        c.eq(livello(percorso), "esperto", f"{percorso} e' una taratura, non una manopola")


def test_limiti(c) -> None:
    """Gli intervalli dei valori (domande 27 e 28).

    **`Config.set` controlla il tipo, non il senso.** `capture.fps = -5` passa e
    ferma la cattura; `speaker.decide_after_ms = 99999` passa e rende il
    programma muto. Nessuno dei due da' errore, ed e' il difetto peggiore di
    questa categoria: la sessione gira, sembra rotta, e non c'e' niente da
    leggere.
    """
    from core.config import Config
    from core.schema import LIMITI, campi, fuori_scala

    c.group("schema")

    noti = {k.percorso for k in campi(Config())}
    c.eq([p for p in LIMITI if p not in noti], [], "ogni campo con un limite esiste davvero")

    # I due casi che hanno fatto nascere la regola.
    c.ok(fuori_scala("capture.fps", -5), "una frequenza negativa viene rifiutata")
    c.ok(fuori_scala("speaker.decide_after_ms", 99999), "e un'attesa da 100 secondi")
    # E i limiti fisici, dove il numero non e' un'opinione.
    c.ok(fuori_scala("vision.sat_max", 300), "una saturazione oltre 255 non vuol dire niente")
    c.ok(fuori_scala("mix.duck_db", 10), "un ducking positivo alzerebbe il gioco invece di abbassarlo")
    # **La fretta al triplo adesso si puo' chiedere, e prima no.** L'intervallo
    # di `timing.rate_max` e' stato portato da 2,0 a 3,0 e quello di
    # `tts.native_rate_max` da 2,5 a 3,0: il gradino misurato non si e' spostato
    # — a 1,30 WSOLA sostituisce la fine della battuta — ma il limite serve a
    # rendere possibile la prova, non a giudicarla. Restano i default, che sono
    # la misura, e resta un tetto: sopra 3,0 si rifiuta ancora, perche' la
    # catena chiude comunque la richiesta a `min(nativo * gain, 3.0)` e un campo
    # che accetta un numero che nessuno puo' consegnare e' un campo che mente.
    c.ok(not fuori_scala("timing.rate_max", 3.0), "il triplo si puo' chiedere a WSOLA")
    c.ok(not fuori_scala("tts.native_rate_max", 3.0), "e lo si puo' chiedere al motore")
    c.ok(fuori_scala("timing.rate_max", 3.5), "oltre il triplo no")
    c.ok(fuori_scala("tts.native_rate_max", 3.5), "ne' all'uno ne' all'altro")

    # **Il messaggio e' per l'utente**: dice cosa fare, non che c'e' stato un no.
    c.ok("fra 0 e 255" in fuori_scala("vision.sat_max", 300), "e dice qual e' l'intervallo")

    # E i valori veri devono passare tutti: un limite che rifiuta il default
    # sarebbe un limite sbagliato, e si accorgerebbe solo chi tocca quel campo.
    fuori = [
        f"{k.percorso}={k.valore}"
        for k in campi(Config())
        if k.tipo in ("int", "float") and fuori_scala(k.percorso, k.valore)
    ]
    c.eq(fuori, [], "nessun default di config e' fuori dal proprio intervallo")

    # E nemmeno i valori dei profili calibrati, che sono i veri valori in uso.
    from core.config import PROFILES_DIR

    for profilo in sorted(PROFILES_DIR.glob("*.json")):
        cfg = Config.load(profilo)
        rotti = [
            f"{k.percorso}={k.valore}"
            for k in campi(cfg)
            if k.tipo in ("int", "float") and fuori_scala(k.percorso, k.valore)
        ]
        c.eq(rotti, [], f"il profilo {profilo.name} sta dentro i limiti")
