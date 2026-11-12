"""Wiersz poleceń: python -m corobiwladza <polecenie>."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build import ROOT, build_session
from .checks import CheckError


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="corobiwladza", description="Co robi władza? – prototyp dla Gdyni")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("pobierz", help="pobierz ostatnią (lub wskazaną) sesję, sprawdź i zapisz JSON")
    b.add_argument("--miasto", default="gdynia")
    b.add_argument("--sesja-post-id", help="id posta sesji w BIP (domyślnie: ostatnia sesja)")
    b.add_argument("--offline", action="store_true", help="tylko z cache, bez sieci")
    b.add_argument("--cache", default=str(ROOT / "cache"))

    s = sub.add_parser("strona", help="zbuduj stronę statyczną z danych JSON")
    s.add_argument("--miasto", default="gdynia")
    s.add_argument("--cache", default=str(ROOT / "cache"))
    s.add_argument("--wyjscie", default=str(ROOT / "site"))

    args = p.parse_args(argv)
    try:
        if args.cmd == "pobierz":
            build_session(args.miasto, Path(args.cache), args.sesja_post_id, offline=args.offline)
        elif args.cmd == "strona":
            from .site import build_site
            build_site(args.miasto, Path(args.cache), Path(args.wyjscie))
    except CheckError as e:
        print(f"BŁĄD SPRAWDZEŃ – nic nie zapisano.\n{e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
