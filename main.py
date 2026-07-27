"""livedub — doppiaggio italiano live dei sottotitoli di gioco.

    python main.py --dump-config
    python main.py --set tts.backend=tone --dump-config
    python main.py --profile gtav --ui

Stato: F0. La configurazione, il backbone misurabile e il banco di prova sono
in piedi; la catena live si accende in F1.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import PROFILES_DIR as PROFILES  # noqa: E402
from core.config import Config, load_profile  # noqa: E402

VERSION = "0.1.0-F0"


def build_config(args: argparse.Namespace) -> Config:
    cfg = load_profile(args.profile, args.overrides)
    if args.ui:
        cfg.ui.enabled = True
    return cfg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="livedub", description="Doppiaggio italiano live dei sottotitoli di gioco."
    )
    ap.add_argument("--profile", default="gtav", help="profilo del gioco (profiles/<nome>.json)")
    ap.add_argument(
        "--set",
        action="append",
        dest="overrides",
        metavar="CHIAVE=VALORE",
        help="scavalca un campo di config, es. --set vision.sat_max=70",
    )
    ap.add_argument("--dump-config", action="store_true", help="stampa la config e termina")
    ap.add_argument("--ui", action="store_true", help="apre la finestra di supervisione")
    ap.add_argument("--version", action="version", version=f"livedub {VERSION}")
    args = ap.parse_args(argv)

    try:
        cfg = build_config(args)
    except (KeyError, ValueError) as e:
        print(f"config: {e}", file=sys.stderr)
        return 2

    if args.dump_config:
        profile_path = PROFILES / f"{cfg.profile}.json"
        origin = profile_path if profile_path.exists() else "(default, nessun profilo su disco)"
        print(f"# livedub {VERSION} — profilo: {cfg.profile} <- {origin}")
        print(cfg.dump())
        return 0

    print(f"livedub {VERSION}: la catena live arriva in F1.", file=sys.stderr)
    print("Per ora: --dump-config, oppure `python -m tools.replay --demo`.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
