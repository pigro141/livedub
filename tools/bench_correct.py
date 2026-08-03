"""Cosa c'e' davvero da correggere, e cosa farebbe un correttore.

Serve a due domande, e la prima viene prima di qualunque modello.

## 1. Di che cosa e' fatto il problema (`--censimento`)

Le parole «non italiane» che escono dall'OCR non sono errori: sono un miscuglio,
e la composizione decide se vale la pena correggere. Misurato su tutte le sessioni
in `runs/`: nomi propri, onomatopee, forme italiane vere che il dizionario non
elenca, frammenti di HUD, e — in minoranza — errori veri.

**Questa e' la misura che va guardata prima di montare un LLM**, perche' dice
qual e' il massimo guadagno possibile. Se gli errori correggibili sono l'uno per
cento delle parole, un correttore che sbaglia una volta su dieci e' in perdita.

## 2. Cosa farebbe un correttore (`--prova`)

Passa le battute vere dentro `Revisore` e stampa cosa cambierebbe e dove si
astiene. Non c'e' verita' di riferimento — nessuno ha trascritto a mano quelle
4280 battute — quindi **questo banco non calcola un'accuratezza**: mostra le
proposte una per una perche' un essere umano le giudichi. Un numero calcolato
senza etichette sarebbe un numero inventato, e qui l'errore che conta e' proprio
quello che sembra giusto.

## Uso

    .\\.venv\\Scripts\\python.exe -m tools.bench_correct --censimento
    .\\.venv\\Scripts\\python.exe -m tools.bench_correct --candidati farto oulldozer andiamu
"""

from __future__ import annotations

import argparse
import collections
import glob
import json

from vision.correct import SEMPRE_BUONE, Revisore, candidati, make_correttore
from vision.lexicon import carica

SEGNI = ".,;:!?'\"()[]-–—…«»‘’“”%€$"


def battute() -> list[str]:
    """Tutte le battute dette nelle sessioni archiviate."""
    fuori = []
    for p in glob.glob("runs/**/speaker.jsonl", recursive=True):
        for riga in open(p, encoding="utf-8"):
            try:
                r = json.loads(riga)
            except Exception:
                continue
            if r.get("kind") == "detta" and r.get("text"):
                fuori.append(r["text"])
    return fuori


def censimento(lex, nomi: tuple[str, ...] = ()) -> None:
    testi = battute()
    noti = {n.lower() for n in nomi}
    tot = 0
    classi: dict[str, collections.Counter] = {
        "nome proprio (maiuscola a meta' frase)": collections.Counter(),
        "onomatopea o interiezione nota": collections.Counter(),
        "nome dichiarato": collections.Counter(),
        "candidato a correzione": collections.Counter(),
    }
    for t in testi:
        parole = t.split()
        for i, w in enumerate(parole):
            pulita = w.strip(SEGNI)
            if len(pulita) < 3 or not pulita.isalpha():
                continue
            tot += 1
            if lex.nota(pulita):
                continue
            basso = pulita.lower()
            primo = i == 0 or parole[i - 1].endswith((".", "!", "?"))
            if basso in noti:
                classi["nome dichiarato"][basso] += 1
            elif basso in SEMPRE_BUONE:
                classi["onomatopea o interiezione nota"][basso] += 1
            elif pulita[0].isupper() and not primo:
                classi["nome proprio (maiuscola a meta' frase)"][pulita] += 1
            else:
                classi["candidato a correzione"][basso] += 1

    fuori = sum(sum(c.values()) for c in classi.values())
    print(f"== censimento su {len(testi)} battute ==")
    print(f"  parole di almeno 3 lettere : {tot}")
    print(f"  fuori dal lessico          : {fuori}  ({fuori / max(1, tot) * 100:.1f}%)\n")
    for nome, c in classi.items():
        n = sum(c.values())
        print(f"  {nome:>40}: {n:5d}  ({n / max(1, tot) * 100:5.2f}% del testo,"
              f" {len(c)} distinte)")
    print("\n  i 30 candidati piu' frequenti — **si guardino a occhio**: fra questi")
    print("  ci sono ancora nomi propri scritti minuscoli e forme italiane vere")
    print("  che il dizionario non elenca, e nessuna delle due va corretta.")
    for w, n in classi["candidato a correzione"].most_common(30):
        print(f"    {n:4d}  {w}")


def mostra_candidati(lex, parole: list[str]) -> None:
    print("== fra quali parole sceglierebbe un correttore ==")
    print("  (e' l'insieme da cui si sceglie: un modello che *sceglie* non puo'")
    print("   inventare una non-parola, e la fiducia esce dal distacco fra i primi due)\n")
    for p in parole:
        cs = candidati(p, lex)
        print(f"  {p:>18} -> {', '.join(cs) if cs else '(nessun candidato vicino)'}")


def prova(lex, cfg, limite: int) -> None:
    rev = Revisore(
        lex,
        make_correttore(cfg),
        min_fiducia=cfg.min_confidence,
        max_distanza=cfg.max_distance,
        contesto_battute=cfg.context_lines,
    )
    n_cambi = n_astensioni = 0
    for t in battute()[:limite]:
        r = rev.rivedi(t)
        n_astensioni += len(r.astenuto)
        if r.cambi:
            n_cambi += len(r.cambi)
            print(f"  {r.cambi}  {t[:60]!r}")
    print(f"\n  cambi proposti: {n_cambi}   astensioni: {n_astensioni}")
    print("  Nessuna accuratezza qui: non c'e' una trascrizione di riferimento.")
    print("  Le proposte vanno lette a occhio, ed e' il punto — l'errore che conta")
    print("  e' quello che sembra giusto.")


def main() -> None:
    p = argparse.ArgumentParser(description="Cosa c'e' da correggere nell'OCR.")
    p.add_argument("--censimento", action="store_true")
    p.add_argument("--candidati", nargs="*", default=None)
    p.add_argument("--prova", action="store_true")
    p.add_argument("--limite", type=int, default=400)
    args = p.parse_args()

    lex = carica()
    print(f"lessico: {len(lex)} parole\n")
    if args.censimento:
        censimento(lex)
    if args.candidati is not None:
        mostra_candidati(lex, args.candidati or ["farto", "oulldozer", "andiamu",
                                                 "fratelio", "ciassico", "simeot"])
    if args.prova:
        from core.config import Config

        prova(lex, Config().correct, args.limite)
    if not (args.censimento or args.candidati is not None or args.prova):
        p.error("scegliere fra --censimento, --candidati e --prova")


if __name__ == "__main__":
    main()
