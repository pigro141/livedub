"""Le lingue parlate, ricavate dal codice e scritte nel README e nella vetrina.

Esiste per una ragione sola, ed e' la stessa contro cui e' scritto mezzo
`CLAUDE.md`: **una tabella scritta due volte, e la seconda non l'aggiorna
nessuno**. In questo repo quella forma e' gia' costata sette volte — le tredici
lingue a mano nel prompt di `translate/ollama.py`, il percorso HF di una voce
Piper, le voci di Kokoro in cache che non sapevano di essere scadute. Un elenco
di cinquantatre lingue in **otto** file di vetrina — sette README e la pagina —
e' il candidato perfetto per la ottava.

Quindi l'elenco **non si scrive**: si ricava da `speak.pool.lingue_con_voce`,
che a sua volta legge il catalogo di ogni motore, e i nomi per esteso da
`translate.lingue`. Chi aggiunge una lingua a un motore non deve ricordarsi di
niente: rilancia lo strumento, e se non lo fa la suite lo dice.

    .\\.venv\\Scripts\\python.exe -m tools.tabella_lingue              # riscrive gli otto blocchi
    .\\.venv\\Scripts\\python.exe -m tools.tabella_lingue --controlla  # dice solo se si sono scollati
    .\\.venv\\Scripts\\python.exe -m tools.tabella_lingue --stampa     # li stampa e non tocca niente

## I due posti, e perche' hanno due forme

I **sette** README (`README.md` piu' `docs/readme/README.<sigla>.md`) sono
Markdown e li legge GitHub: il blocco e' una tabella dentro un `<details>`, fra
due commenti HTML. Ci sono tutti e sette perche' un lettore tedesco legge il
suo: dichiarargli cinquantatre lingue e non elencargliele mai vorrebbe dire
consegnare la risposta a chi legge l'inglese e basta. Della cornice cambia solo
il sommario, le due intestazioni e la riga di riepilogo — stanno in `TESTI`, qui
sotto, che e' l'unico posto dove questo file scrive prosa.

`site/i18n/en.js` e' **insieme la struttura della vetrina e il suo testo
inglese**, e gli altri sei cataloghi sono dizionari `{ stringa inglese ->
tradotta }` che gli stanno sopra. Da qui il vincolo che ha deciso la forma del
blocco: **cio' che viene generato non deve essere traducibile**. Se lo fosse,
ogni lingua aggiunta a un motore cambierebbe una chiave in `en.js` e
sbriciolerebbe sei cataloghi che oggi sono completi — e la pagina lo
dichiarerebbe con la riga «N stringhe su M sono ancora in inglese».

Percio' qui si genera **solo l'array `righe`** del blocco `t: "lingue"`: codici
ISO, nomi in inglese e spunte. Il resto di quel blocco — il riassunto del
`<details>` e le intestazioni delle colonne — e' scritto a mano, e' stabile, e
sta nei cataloghi come tutto il resto. I nomi delle lingue restano in inglese in
tutte e sette le lingue della pagina: sono **dati letti dal codice**, come il
nome di un dispositivo o la chiave di un modello. Passarli da un traduttore
automatico e' esattamente come `uk — Ucraino` diventato «Regno Unito —
ucraino» dentro la finestra.

## Cosa questo strumento **non** puo' dire

Dichiara che una voce **esiste** e che e' **di quella lingua**, che e' cio' che
i cataloghi dei motori pubblicano. Non dice niente sulla pronuncia: nessuno ha
ascoltato cinquantatre lingue, e le misure meccaniche fatte davvero (supertonic
31 su 31, piper 1 su 50, kokoro 0 su 8) stanno scritte accanto alla tabella e
non le produce questo file.

E i numeri dichiarati nella prosa attorno — «50 with piper, 31 with supertonic,
8 with kokoro» e le celle della tabella dei motori — non si riscrivono: si
**controllano** (`dichiarazioni`). Riscrivere la prosa vorrebbe dire ritradurla
in tredici file a ogni giro; controllarla costa una regex ancorata al nome del
motore — che e' l'unica parola di quelle tabelle che non si traduce — e
fallisce dove il numero e' scritto, che e' il posto in cui serve guardare.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from speak.pool import lingue_con_voce  # noqa: E402
from translate.lingue import nome_en  # noqa: E402

README = RADICE / "README.md"
SITO = RADICE / "site" / "i18n" / "en.js"

#: I sette README, per sigla. Quello inglese sta in radice, gli altri sotto
#: `docs/readme/`. Ci sono tutti e sette perche' un lettore tedesco legge il
#: **suo**: dichiarargli 53 lingue e non elencargliele mai vorrebbe dire che la
#: consegna vale per una lingua sola.
READMES: dict[str, Path] = {
    "en": README,
    **{s: RADICE / "docs" / "readme" / f"README.{s}.md"
       for s in ("it", "de", "es", "fr", "ja", "zh")},
}

#: I tre motori che parlano, nell'ordine in cui il README li presenta: prima il
#: default. `tone` e `silent` non stanno qui perche' un bip non ha lingua.
MOTORI: tuple[str, ...] = ("piper", "supertonic", "kokoro")

INIZIO_MD = "<!-- lingue: inizio -->"
FINE_MD = "<!-- lingue: fine -->"
INIZIO_JS = "/* lingue: inizio */"
FINE_JS = "/* lingue: fine */"

_AVVISO = "generato da `tools/tabella_lingue.py`, non si scrive a mano"
_SPUNTA = "✓"

#: Le tre frasi che stanno **dentro** il blocco generato, nelle sette lingue dei
#: README. Stanno qui e non nei file perche' sono l'unica prosa che il
#: generatore riscrive a ogni giro: tenerle nei file vorrebbe dire riscriverle
#: e quindi perderle. Il resto della sezione — il paragrafo che introduce
#: l'elenco e la nota sotto — e' scritto a mano nel README e non si tocca.
#:
#: `riepilogo` e' costruito apposta senza grammatica: `{esclusive}` e
#: `{comuni}` arrivano gia' impaginati come elenchi con dentro i nomi dei
#: motori, cosi' la stessa frase regge in sette lingue senza accordi di numero
#: — che e' l'unico modo di generare prosa senza scrivere sciocchezze in sei
#: lingue che nessuno qui rilegge.
#:
#: `vicino` e' la regex con cui si ritrova, in quel README, la frase «N con
#: <motore>». Non e' una sola per tutti: il giapponese e il cinese scrivono il
#: numero **dopo** il nome del motore, e una regex sola avrebbe smesso di
#: trovare la frase invece di trovarla sbagliata.
TESTI: dict[str, dict[str, object]] = {
    "en": {
        "sommario": "<b>All {n} languages, engine by engine</b> — {spunta} means that "
                    "engine has at least one voice of its own in that language.",
        "colonne": ("code", "language"),
        "riepilogo": "Reading down a column gives that engine's catalogue. "
                     "Spoken by one engine only: {esclusive}. "
                     "Spoken by all three: {comuni}.",
        "vicino": r"(\d+) with {m}",
    },
    "it": {
        "sommario": "<b>Tutte le {n} lingue, motore per motore</b> — {spunta} vuol dire "
                    "che quel motore ha almeno una voce sua in quella lingua.",
        "colonne": ("codice", "lingua"),
        "riepilogo": "Leggendo una colonna si ha il catalogo di quel motore. "
                     "Lingue che parla un motore solo: {esclusive}. "
                     "Lingue che parlano tutti e tre: {comuni}.",
        "vicino": r"(\d+) con {m}",
    },
    "de": {
        "sommario": "<b>Alle {n} Sprachen, Motor für Motor</b> — {spunta} heißt, dass "
                    "dieser Motor mindestens eine eigene Stimme in dieser Sprache hat.",
        "colonne": ("Code", "Sprache"),
        "riepilogo": "Eine Spalte gelesen ergibt den Katalog dieses Motors. "
                     "Nur von einem Motor gesprochen: {esclusive}. "
                     "Von allen dreien gesprochen: {comuni}.",
        "vicino": r"(\d+) mit {m}",
    },
    "es": {
        "sommario": "<b>Los {n} idiomas, motor por motor</b> — {spunta} significa que ese "
                    "motor tiene al menos una voz propia en ese idioma.",
        "colonne": ("código", "idioma"),
        "riepilogo": "Leer una columna da el catálogo de ese motor. "
                     "Habladas por un solo motor: {esclusive}. "
                     "Habladas por los tres: {comuni}.",
        "vicino": r"(\d+) con {m}",
    },
    "fr": {
        "sommario": "<b>Les {n} langues, moteur par moteur</b> — {spunta} signifie que ce "
                    "moteur a au moins une voix à lui dans cette langue.",
        "colonne": ("code", "langue"),
        "riepilogo": "Lire une colonne donne le catalogue de ce moteur. "
                     "Parlées par un seul moteur : {esclusive}. "
                     "Parlées par les trois : {comuni}.",
        "vicino": r"(\d+) avec {m}",
    },
    "ja": {
        "sommario": "<b>{n} 言語すべて、エンジンごと</b> — {spunta} は、そのエンジンが"
                    "その言語に自前の声を少なくとも一つ持っているという意味です。",
        "colonne": ("コード", "言語"),
        "riepilogo": "列を縦に読めば、そのエンジンのカタログになります。"
                     "一つのエンジンだけが話す言語: {esclusive}。"
                     "三つとも話す言語: {comuni}。",
        "vicino": r"{m} で (\d+)",
    },
    "zh": {
        "sommario": "<b>全部 {n} 种语言，逐个引擎</b> — {spunta} 表示该引擎在这种语言里"
                    "至少有一把自己的嗓音。",
        "colonne": ("代码", "语言"),
        "riepilogo": "竖着读一列，就是那个引擎的目录。"
                     "只有一个引擎会说的：{esclusive}。"
                     "三个引擎都会说的：{comuni}。",
        "vicino": r"{m} (\d+) 种",
    },
}


# ============================================================== i dati =====


@dataclass(frozen=True)
class Riga:
    """Una lingua, con i motori che hanno almeno una voce nativa in essa."""

    codice: str
    inglese: str
    motori: tuple[str, ...]


@dataclass(frozen=True)
class Dati:
    per_motore: dict[str, tuple[str, ...]]
    righe: tuple[Riga, ...]

    def solo(self, motore: str) -> tuple[Riga, ...]:
        return tuple(r for r in self.righe if r.motori == (motore,))

    def tutti(self) -> tuple[Riga, ...]:
        return tuple(r for r in self.righe if len(r.motori) == len(MOTORI))


def dati() -> Dati:
    """Le lingue di ogni motore, lette dal catalogo del motore stesso.

    L'ordine e' **alfabetico per nome inglese** e non per codice: chi apre
    questa tabella cerca «Portuguese», non `pt`.
    """
    per_motore = {m: tuple(sorted(lingue_con_voce(m))) for m in MOTORI}
    codici = sorted(set().union(*(set(v) for v in per_motore.values())))
    righe = tuple(
        sorted(
            (
                Riga(
                    codice=c,
                    inglese=nome_en(c),
                    motori=tuple(m for m in MOTORI if c in per_motore[m]),
                )
                for c in codici
            ),
            key=lambda r: (r.inglese.lower(), r.codice),
        )
    )
    return Dati(per_motore=per_motore, righe=righe)


# =========================================================== il README =====


def blocco_readme(d: Dati, sigla: str = "en") -> list[str]:
    """Il blocco Markdown per un README: la tabella dentro un `<details>`.

    **I nomi delle lingue restano in inglese in tutte e sette.** Sono dati
    letti dal codice, e passarli da un traduttore automatico e' esattamente
    come `uk — Ucraino` diventato «Regno Unito — ucraino» dentro la finestra.
    Quello che cambia lingua e' la cornice: il sommario, le due intestazioni e
    la riga di riepilogo.
    """
    t = TESTI[sigla]
    colonne = t["colonne"]
    righe: list[str] = [f"<!-- {_AVVISO} -->", ""]
    righe.append("<details>")
    righe.append(
        "<summary>"
        + str(t["sommario"]).format(n=len(d.righe), spunta=_SPUNTA)
        + "</summary>"
    )
    righe.append("")
    righe.append(f"| {colonne[0]} | {colonne[1]} | " + " | ".join(MOTORI) + " |")
    righe.append("|---|---|" + ":---:|" * len(MOTORI))
    for r in d.righe:
        celle = [_SPUNTA if m in r.motori else "" for m in MOTORI]
        righe.append(f"| `{r.codice}` | {r.inglese} | " + " | ".join(celle) + " |")
    righe.append("")

    esclusive = " · ".join(
        f"`{m}` {len(d.solo(m))}"
        + (f" ({', '.join(x.inglese for x in d.solo(m))})"
           if 0 < len(d.solo(m)) <= 4 else "")
        for m in MOTORI
    )
    tutti = [x.inglese for x in d.tutti()]
    comuni = f"{len(tutti)} — {', '.join(tutti)}" if tutti else "0"
    righe.append(str(t["riepilogo"]).format(esclusive=esclusive, comuni=comuni))
    righe.append("")
    righe.append("</details>")
    return righe


# =========================================================== la vetrina ====


def blocco_sito(d: Dati) -> list[str]:
    """L'array `righe` del blocco `t: "lingue"`, e nient'altro.

    Rientro a 14 spazi: e' quello degli altri elementi di un blocco dentro
    `sezioni[].blocchi[]` in `site/i18n/en.js`.
    """
    fuori: list[str] = [f"              /* {_AVVISO} */"]
    ultimo = len(d.righe) - 1
    for i, r in enumerate(d.righe):
        celle = ", ".join(
            '"%s"' % (_SPUNTA if m in r.motori else "") for m in MOTORI
        )
        virgola = "" if i == ultimo else ","
        fuori.append(f'              ["{r.codice}", "{r.inglese}", {celle}]{virgola}')
    return fuori


# ================================== i numeri dichiarati nella prosa ========
#
# Non si riscrivono, si controllano: si veda la testata. Ogni voce e'
# `(file, cosa dice, regex con un gruppo, quale numero deve uscire)`, e la
# regex e' **ancorata al nome del motore** perche' il messaggio di errore possa
# dire dove guardare.


def dichiarazioni(d: Dati) -> list[tuple[Path, str, str, int]]:
    n = {m: len(d.per_motore[m]) for m in MOTORI}
    unione = len(d.righe)
    voci: list[tuple[Path, str, str, int]] = []

    for sigla, percorso in READMES.items():
        for m in MOTORI:
            # La riga della tabella dei motori. La regex regge in tutte e sette
            # le lingue perche' il nome del motore **non si traduce**: e' una
            # chiave, come un comando.
            voci.append(
                (
                    percorso,
                    f"la riga «{m}» della tabella dei motori",
                    r"\|\s*\*\*" + m + r"\*\*[^|]*\|\s*\*\*(\d+)\*\*\s*\|",
                    n[m],
                )
            )
            voci.append(
                (
                    percorso,
                    f"«N con {m}», nel sommario in cima e nelle tre liste",
                    str(TESTI[sigla]["vicino"]).format(m=m),
                    n[m],
                )
            )
        # La riga dell'unione: si riconosce dalla **forma** — due celle piene e
        # tre vuote — e non dalla parola, che e' l'unica di quella tabella a
        # essere tradotta (`unione`, `Vereinigung`, `合計`...).
        voci.append(
            (
                percorso,
                "la riga dell'unione, in fondo alla tabella dei motori",
                r"\|\s*\*\*[^|*]+\*\*\s*\|\s*\*\*(\d+)\*\*\s*\|\s*\|\s*\|\s*\|",
                unione,
            )
        )

    for m in MOTORI:
        voci.append(
            (
                SITO,
                f"la riga «{m}» della tabella dei motori",
                r'"<b>' + m + r"</b>[^\"]*\",\s*\"<b>(\d+)</b>\"",
                n[m],
            )
        )
        voci.append(
            (
                SITO,
                f"«N with {m}», nel riassunto delle tre liste",
                r"(\d+) with " + m,
                n[m],
            )
        )
    voci.append(
        (
            SITO,
            "la riga «union» della tabella dei motori",
            r'"<b>union</b>",\s*"<b>(\d+)</b>"',
            unione,
        )
    )
    voci.append(
        (
            SITO,
            "«it speaks out loud in N languages», la marca in testata",
            r"it speaks out loud in <b>(\d+) languages</b>",
            unione,
        )
    )
    return voci


def _pezzi(d: Dati) -> list[tuple[Path, str, str, list[str]]]:
    """I blocchi generati: file, marcatore d'inizio, di fine, contenuto."""
    pezzi = [
        (p, INIZIO_MD, FINE_MD, blocco_readme(d, sigla))
        for sigla, p in READMES.items()
    ]
    pezzi.append((SITO, INIZIO_JS, FINE_JS, blocco_sito(d)))
    return pezzi


# ============================================== leggere e riscrivere =======


def _leggi(p: Path) -> tuple[str, str]:
    """Il testo com'e' sul disco, e il suo a-capo. I file di questo repo sono
    CRLF: riscriverli in LF farebbe apparire modificato tutto il file."""
    with open(p, encoding="utf-8", newline="") as f:
        testo = f.read()
    return testo, ("\r\n" if "\r\n" in testo else "\n")


def _scrivi(p: Path, testo: str) -> None:
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(testo)


def sostituisci(testo: str, inizio: str, fine: str, righe: list[str], acapo: str) -> str:
    """Il contenuto fra i due marcatori, sostituito. I marcatori restano."""
    i = testo.find(inizio)
    j = testo.find(fine)
    if i < 0 or j < 0 or j < i:
        raise ValueError(f"marcatori non trovati o invertiti: {inizio!r} / {fine!r}")
    dentro = acapo + acapo.join(righe) + acapo
    return testo[: i + len(inizio)] + dentro + testo[j:]


def dentro(testo: str, inizio: str, fine: str) -> str:
    i = testo.find(inizio)
    j = testo.find(fine)
    if i < 0 or j < 0 or j < i:
        raise ValueError(f"marcatori non trovati o invertiti: {inizio!r} / {fine!r}")
    return testo[i + len(inizio) : j]


def scrivi(d: Dati | None = None) -> list[str]:
    """Riscrive gli otto blocchi. Torna l'elenco dei file cambiati davvero."""
    d = d or dati()
    cambiati: list[str] = []
    for percorso, inizio, fine, righe in _pezzi(d):
        testo, acapo = _leggi(percorso)
        nuovo = sostituisci(testo, inizio, fine, righe, acapo)
        if nuovo != testo:
            _scrivi(percorso, nuovo)
            cambiati.append(percorso.name)
    return cambiati


def controlla(d: Dati | None = None) -> list[str]:
    """Cosa si e' scollato dal codice. Elenco vuoto = tutto allineato."""
    d = d or dati()
    guai: list[str] = []

    for percorso, inizio, fine, righe in _pezzi(d):
        try:
            testo, acapo = _leggi(percorso)
            atteso = acapo + acapo.join(righe) + acapo
            trovato = dentro(testo, inizio, fine)
        except (OSError, ValueError) as e:
            guai.append(f"{percorso.name}: {e}")
            continue
        if trovato != atteso:
            guai.append(
                f"{percorso.name}: il blocco fra i marcatori non e' quello che il "
                f"codice produce adesso — rilancia `python -m tools.tabella_lingue`"
            )

    for percorso, cosa, regex, atteso in dichiarazioni(d):
        try:
            testo, _ = _leggi(percorso)
        except OSError as e:
            guai.append(f"{percorso.name}: {e}")
            continue
        trovati = re.findall(regex, testo)
        if not trovati:
            guai.append(f"{percorso.name}: non trovo piu' {cosa} ({regex})")
            continue
        sbagliati = sorted({t for t in trovati if int(t) != atteso})
        if sbagliati:
            guai.append(
                f"{percorso.name}: {cosa} dice {', '.join(sbagliati)} "
                f"ma il codice dice {atteso}"
            )
    return guai


# ================================================================= CLI =====


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="La tabella delle lingue parlate, ricavata dal codice."
    )
    ap.add_argument(
        "--controlla",
        action="store_true",
        help="non tocca niente: dice se README e vetrina sono ancora allineati",
    )
    ap.add_argument(
        "--stampa",
        action="store_true",
        help="stampa i due blocchi sullo schermo, senza scrivere",
    )
    args = ap.parse_args(argv)

    # La console di Windows e' cp1252, e qui passano una spunta, sette lingue di
    # cornice e delle regex giapponesi: senza questa riga `--stampa` **muore**
    # invece di stampare, e un attrezzo che esplode sul suo stesso risultato
    # e' un attrezzo che nessuno rilancia.
    for flusso in (sys.stdout, sys.stderr):
        try:
            flusso.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    d = dati()
    quante = {m: len(d.per_motore[m]) for m in MOTORI}
    riassunto = ", ".join(f"{m} {quante[m]}" for m in MOTORI)
    print(f"{riassunto}, unione {len(d.righe)}")

    if args.stampa:
        for percorso, _inizio, _fine, righe in _pezzi(d):
            print(f"\n--- {percorso.relative_to(RADICE).as_posix()} ---")
            print("\n".join(righe))
        return 0

    if args.controlla:
        guai = controlla(d)
        if guai:
            print(f"\n{len(guai)} cose scollate dal codice:")
            for g in guai:
                print(f"  - {g}")
            return 1
        print("README e vetrina dicono quello che dice il codice.")
        return 0

    cambiati = scrivi(d)
    print("riscritti: " + (", ".join(cambiati) if cambiati else "niente da cambiare"))
    guai = controlla(d)
    for g in guai:
        print(f"  ! {g}")
    return 1 if guai else 0


if __name__ == "__main__":
    raise SystemExit(main())
