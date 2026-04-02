"""Entry point for ``python -m henri``."""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

BANNER = r"""
  .          ...                .       .
 .      . . ..:++=====-:.    .       .. .
  .     ..:=+#%##***##%%%+==-:.       ...  ..
       ..+#%###*********+=*%#%#+... .
   ....-#%%#=:.............:+##%%*:.......
   ...-%%%+:................:**%%##=::.... .
   ...-%%*-:................:+##%%%*:::....
   ...:#%*-:...............:-+#%%@@+:.....
 . ...:+%*-:........:==-::::-*%%##*:......  .
   ...:*%#==-=+=:..:=-+-:.::-+%*+=-:::...  .
   ...:-*%++==--=..........:-+#+--:::::..
   ...:::#=:...:-..::......:-*%-:::::::..  .
   ...:::*#-...::..::.:....:-#%=-=:::::...
  ....:::+@*-..-+#*+-::-:::-+#%%+:::::::.
   ...:::+%%*--=##*##*+*+=++*#%@#-:::.:..
 .....:::#%%%%%%%#-::-+%%*###%%%+::...:..   .
.. ...::-%%%%@@%**++=:..=##%%%*-=::::::.... .
   ...:::=%%%@@@+-.....:=%%%+..:#%=::::....
   ...::::::=*+=##+==+*#*+:...:+*@@#-::......
   ...::::::::::=+**===:....:=+-#%%%%%+-.....
   ...:::::::::=%#=-=:..:=+##*:#%####%%#*-...
  ....:::::-+*%@@@@%***#%%#=:.#######*##*-..
 . ..-+##%%%%%%%%@@%%#%%##+..*######****=:..
   .=#%%%%#%%%%%%%%%%%%%#*-.+##******++*=...
 ..:*#%%%%###%%*-:..=*#**#==#*******+===-...
 .:+**###%%%%#:..  ...-*+:-*******++===+-...
 ..:=+***###*:..     .....-++++++==--=+=:...
 ....::-=**+-..        ...::::--::..:.:.....
...... .......   .     ...... ...::.::::...
  .                         .  ........... .

    HENRI — Humanitarian Early-warning Network
             Resilience Intelligence
"""


def _print_banner() -> None:
    print(BANNER, file=sys.stderr)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="henri",
        description="HENRI — Humanitarian Early-warning Network Resilience Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=BANNER,
    )
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run_all", help="Full pipeline: extract → analyse → report")
    p_run.add_argument("--dry", action="store_true", help="Show plan without executing")
    p_run.add_argument("--fixtures", action="store_true", help="Use fixture data only")
    p_run.add_argument("--source", type=str, default=None,
                       help="Comma-separated sources: snow,grafana,netbox,osint")
    p_run.add_argument("--field-only", action="store_true",
                       help="Generate field-region report only")

    p_report = sub.add_parser("report", help="Regenerate report from existing data")
    p_report.add_argument("--field-only", action="store_true")

    args = parser.parse_args()
    command = args.command or "run_all"

    from henri.logging import setup_logging, new_correlation_id
    setup_logging()
    new_correlation_id()

    if command == "run_all":
        _print_banner()
        from henri.run_all import run_pipeline
        _VALID_SOURCES = {"snow", "grafana", "netbox", "osint"}
        sources = None
        if args.source:
            sources = set(args.source.split(","))
            invalid = sources - _VALID_SOURCES
            if invalid:
                parser.error(f"Invalid sources: {', '.join(sorted(invalid))}. "
                             f"Valid: {', '.join(sorted(_VALID_SOURCES))}")
        result = run_pipeline(
            dry=args.dry,
            fixtures=args.fixtures,
            sources=sources,
            field_only=getattr(args, "field_only", False),
        )
        if result["steps_failed"]:
            sys.exit(1)

    elif command == "report":
        _print_banner()
        from henri.run_all import regenerate_reports
        regenerate_reports(field_only_only=getattr(args, "field_only", False))


if __name__ == "__main__":
    main()
