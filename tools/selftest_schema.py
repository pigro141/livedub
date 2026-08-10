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
    c.ok(not per_nome["label.colors"].modificabile, "e si sa che non e' una manopola")
    c.ok(per_nome["vision.roi"].modificabile, "la ROI invece si scrive (quaterna di numeri)")
    non_scrivibili = [k.percorso for k in elenco if not k.modificabile]
    c.eq(non_scrivibili, ["label.colors", "label.voices"],
         "e oggi sono i due dizionari di `label`")

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
