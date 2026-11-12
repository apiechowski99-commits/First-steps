"""Wyciąganie tekstu i metadanych z PDF przez poppler-utils (pdftotext, pdfinfo)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


class PdfError(RuntimeError):
    pass


def _need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise PdfError(f"Brak programu {tool!r}. Zainstaluj poppler-utils.")
    return path


def text(path: Path, layout: bool = False) -> str:
    args = [_need("pdftotext"), "-enc", "UTF-8"]
    if layout:
        args.append("-layout")
    args += [str(path), "-"]
    res = subprocess.run(args, capture_output=True, timeout=300)
    if res.returncode != 0:
        raise PdfError(f"pdftotext: {res.stderr.decode('utf-8', 'replace')[:300]}")
    return res.stdout.decode("utf-8", errors="replace")


def info(path: Path) -> dict[str, str]:
    res = subprocess.run([_need("pdfinfo"), "-enc", "UTF-8", str(path)],
                         capture_output=True, timeout=60)
    if res.returncode != 0:
        raise PdfError(f"pdfinfo: {res.stderr.decode('utf-8', 'replace')[:300]}")
    out = {}
    for line in res.stdout.decode("utf-8", errors="replace").splitlines():
        m = re.match(r"^([^:]+):\s*(.*)$", line)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def normalize_ws(s: str) -> str:
    """Do porównywania cytatów: łączy przeniesienia wyrazów i zbija białe znaki."""
    s = s.replace(" ", " ").replace("­", "")
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)  # przeniesienie wyrazu na koniec wiersza
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def split_justification(full_text: str) -> tuple[str, str | None]:
    """Dzieli tekst uchwały na treść i uzasadnienie (nagłówek „UZASADNIENIE”)."""
    m = re.search(r"^\s*UZASADNIENIE\s*$", full_text, flags=re.M)
    if not m:
        return full_text, None
    return full_text[: m.start()], full_text[m.end():]
