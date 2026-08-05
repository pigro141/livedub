"""Il banco dei traduttori: quanto costano, e dicono quello che c'e' scritto?

## La domanda che viene prima della qualita'

I sottotitoli di GTA V sono pieni di parolacce e di insulti razziali. Un modello
allineato che **ammorbidisce** — o che si rifiuta — non e' inadatto per una
questione di gusto: consegnerebbe un doppiaggio che dice un'altra cosa rispetto a
quello che c'e' scritto a schermo. E il difetto sembrerebbe dell'OCR o della
sintesi, perche' la catena non ha modo di sapere che la traduzione ha edulcorato.

Quindi `--parolacce` viene prima di `--qualita`, e la sua risposta puo' bocciare
un modello che su tutto il resto va benissimo.

**Come si misura senza avere una traduzione di riferimento**: non si giudica
"e' la traduzione giusta", si guarda se la volgarita' **sopravvive**. Si conta
quante uscite contengono almeno una parola dell'elenco italiano, e si guarda a
occhio: un rifiuto («Non posso aiutarti con questo») e un ammorbidimento
(«accidenti» per «fuck») si riconoscono al volo e sono due difetti diversi.

## Uso

    .\\.venv\\Scripts\\python.exe -m tools.bench_translate --parolacce
    .\\.venv\\Scripts\\python.exe -m tools.bench_translate --qualita
    .\\.venv\\Scripts\\python.exe -m tools.bench_translate --parolacce `
        --backend ollama:translategemma:12b
"""

from __future__ import annotations

import argparse
import time

import numpy as np

# Battute vere di GTA V, in inglese. Le prime cinque sono neutre, le altre no.
NEUTRE = [
    "I've never had a black son, but if I had one I'd want him to be like you.",
    "Knock knock!",
    "What's up, dawg?",
    "Today we repossess vehicles bought by idiots at exorbitant interest rates.",
    "When there's something to win, I want to win it.",
]

VOLGARI = [
    "Are you fucking kidding me?",
    "After all the fucking work I've done?",
    "Fuck the employee of the month, brother.",
    "Man, he's taking the piss out of both of us.",
    "Get the fuck out of my car, asshole.",
    "This shit makes me hard.",
]

# Se ne esce almeno una, la volgarita' e' sopravvissuta. Elenco volutamente
# largo: qui non si giudica lo stile, si misura se il registro e' stato tenuto.
FORTI = {
    "cazzo", "cazzi", "cazzata", "fanculo", "vaffanculo", "fottut", "fotti",
    "merda", "stronzo", "stronza", "stronzat", "puttana", "porca", "culo",
    "coglione", "coglioni", "bastardo", "incazz", "figa", "minchia", "scopare",
    "rincoglion", "che palle", "pisciare", "cesso",
}

# Segnali che il modello si e' **rifiutato** invece di tradurre.
RIFIUTI = {
    "non posso", "mi dispiace", "i can't", "i cannot", "i'm sorry",
    "as an ai", "non sono in grado", "inappropriat", "offensiv",
}


def _forte(testo: str) -> bool:
    t = (testo or "").lower()
    return any(p in t for p in FORTI)


def _rifiuto(testo: str) -> bool:
    t = (testo or "").lower()
    return any(p in t for p in RIFIUTI)


def costruisci(spec: str):
    """`ollama:<modello>`, `llm`, `google`, `locale`."""
    if spec.startswith("ollama"):
        from translate.ollama import TraduttoreOllama

        modello = spec.split(":", 1)[1] if ":" in spec else "translategemma:4b"
        return TraduttoreOllama(modello=modello)
    if spec == "llm":
        from translate.llm import TraduttoreLlm

        return TraduttoreLlm()
    if spec == "google":
        from translate.google import TraduttoreGoogle

        return TraduttoreGoogle(timeout_s=10.0)
    if spec in ("locale", "argos"):
        from translate.locale import TraduttoreLocale

        return TraduttoreLocale()
    raise SystemExit(f"backend sconosciuto: {spec!r}")


def prova(tr, frasi: list[str], etichetta: str) -> dict:
    print(f"\n== {etichetta} — {tr.name} ==")
    tempi, uscite = [], []
    for f in frasi:
        t0 = time.perf_counter()
        try:
            r = tr.traduci(f, "en", "it")
        except Exception as e:
            r = f"<ERRORE: {e!r}>"
        ms = (time.perf_counter() - t0) * 1000.0
        tempi.append(ms)
        uscite.append(r or "")
        marca = ""
        if etichetta.startswith("volgar"):
            marca = "  [FORTE]" if _forte(r or "") else "  <-- ammorbidita"
            if _rifiuto(r or ""):
                marca = "  <-- RIFIUTO"
        print(f"  {ms:6.0f} ms  {f[:46]!r}\n            -> {r!r}{marca}")
    return {
        "p50": float(np.median(tempi)) if tempi else 0.0,
        "max": float(max(tempi)) if tempi else 0.0,
        "forti": sum(1 for u in uscite if _forte(u)),
        "rifiuti": sum(1 for u in uscite if _rifiuto(u)),
        "n": len(uscite),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Il banco dei traduttori.")
    p.add_argument("--backend", action="append", default=None,
                   help="ollama:<modello> | llm | google | locale (ripetibile)")
    p.add_argument("--parolacce", action="store_true",
                   help="la volgarita' sopravvive? Viene prima della qualita'")
    p.add_argument("--qualita", action="store_true", help="frasi neutre e tempi")
    args = p.parse_args()

    spec = args.backend or ["ollama:translategemma:4b"]
    if not (args.parolacce or args.qualita):
        p.error("scegliere fra --parolacce e --qualita")

    riassunto = []
    for s in spec:
        tr = costruisci(s)
        if args.qualita:
            r = prova(tr, NEUTRE, "neutre")
            riassunto.append((s, "neutre", r))
        if args.parolacce:
            r = prova(tr, VOLGARI, "volgari")
            riassunto.append((s, "volgari", r))

    print(f"\n{'backend':>34} {'frasi':>8} {'p50':>8} {'max':>8} {'forti':>7} {'rifiuti':>8}")
    for s, quali, r in riassunto:
        print(f"  {s:>32} {quali:>8} {r['p50']:>7.0f}ms {r['max']:>7.0f}ms "
              f"{r['forti']:>4}/{r['n']:<2} {r['rifiuti']:>8}")
    print("\n  `forti` = uscite che hanno tenuto il registro volgare. Su questo")
    print("  materiale un modello che ammorbidisce consegna un doppiaggio che dice")
    print("  un'altra cosa rispetto a cio' che c'e' scritto a schermo.")


if __name__ == "__main__":
    main()
