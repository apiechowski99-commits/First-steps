"""Parser PDF „Wyniki głosowania” generowanych przez eSesję (app.esesja.pl).

Format jest ścisły. Każdy nieoczekiwany wiersz to błąd (VoteParseError),
nie ostrzeżenie. Lepiej przerwać niż zgadywać.
"""

from __future__ import annotations

import dataclasses
import re

# Kolejność opcji taka jak w PDF eSesji.
OPTIONS = ("za", "przeciw", "wstrzymal_sie", "brak_glosu", "nieobecni")
OPTION_LABELS_PDF = {
    "ZA": "za",
    "PRZECIW": "przeciw",
    "WSTRZYMUJĘ SIĘ": "wstrzymal_sie",
    "BRAK GŁOSU": "brak_glosu",
    "NIEOBECNI": "nieobecni",
}

_SUMMARY = re.compile(
    r"ZA:\s*(\d+),\s*PRZECIW:\s*(\d+),\s*WSTRZYMUJĘ SIĘ:\s*(\d+),\s*"
    r"BRAK GŁOSU:\s*(\d+),\s*NIEOBECNI:\s*(\d+)"
)
_SECTION = re.compile(r"^(ZA|PRZECIW|WSTRZYMUJĘ SIĘ|BRAK GŁOSU|NIEOBECNI) \((\d+)\)$")
_VOTED_AT = re.compile(r"^Głosowanie z dnia:\s*(\d{2})\.(\d{2})\.(\d{4}),\s*(\d{2}:\d{2}:\d{2})$")
_FOOTER = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})\s*\|\s*Wygenerowano za pomocą app\.esesja\.pl$")


class VoteParseError(ValueError):
    pass


@dataclasses.dataclass
class ParsedVote:
    subject: str
    summary: dict[str, int]          # sumy z wiersza „ZA: …, PRZECIW: …”
    section_counts: dict[str, int]   # liczby z nagłówków „ZA (27)”
    names: dict[str, list[str]]      # nazwiska w kolejności z PDF
    voted_at: str                    # ISO 8601, czas lokalny z PDF
    generated_on: str                # data wygenerowania PDF (ISO)


def _iso(d: str, m: str, y: str) -> str:
    return f"{y}-{m}-{d}"


def parse(text: str) -> ParsedVote:
    lines = [ln.strip() for ln in text.replace("\f", "\n").splitlines()]
    footers = [m for ln in lines if (m := _FOOTER.match(ln))]
    if not footers:
        raise VoteParseError("Brak stopki „Wygenerowano za pomocą app.esesja.pl”")
    if len({m.groups() for m in footers}) != 1:
        raise VoteParseError("Różne daty wygenerowania na stronach PDF")
    generated_on = _iso(*footers[0].groups())
    lines = [ln for ln in lines if ln and not _FOOTER.match(ln)]

    if not lines or lines[0] != "Wyniki głosowania":
        raise VoteParseError("PDF nie zaczyna się od „Wyniki głosowania”")

    # Temat: od „Głosowano w sprawie:” do wiersza z sumami.
    if not lines[1].startswith("Głosowano w sprawie:"):
        raise VoteParseError("Brak wiersza „Głosowano w sprawie:”")
    # Wiersz z sumami bywa doklejony do ostatniego wiersza tematu, więc
    # szukamy sum na końcu wiersza, a resztę wiersza dołączamy do tematu.
    subject_parts = []
    rest = lines[1][len("Głosowano w sprawie:"):].strip()
    i = 1
    summary = None
    while True:
        m = _SUMMARY.search(rest)
        if m and m.end() == len(rest):
            subject_parts.append(rest[: m.start()].strip())
            summary = dict(zip(OPTIONS, map(int, m.groups())))
            break
        if m:
            raise VoteParseError(f"Tekst po sumach głosów: {rest[m.end():]!r}")
        subject_parts.append(rest)
        i += 1
        if i == len(lines):
            raise VoteParseError("Brak wiersza z sumami głosów")
        rest = lines[i]
    subject = " ".join(p for p in subject_parts if p)
    i += 1

    if i >= len(lines) or lines[i] != "Wyniki imienne:":
        raise VoteParseError("Brak nagłówka „Wyniki imienne:”")
    i += 1

    section_counts: dict[str, int] = {}
    buffers: dict[str, list[str]] = {}
    current = None
    voted_at = None
    for ln in lines[i:]:
        if m := _SECTION.match(ln):
            key = OPTION_LABELS_PDF[m.group(1)]
            if key in section_counts:
                raise VoteParseError(f"Sekcja {m.group(1)} występuje dwa razy")
            section_counts[key] = int(m.group(2))
            buffers[key] = []
            current = key
        elif m := _VOTED_AT.match(ln):
            if voted_at:
                raise VoteParseError("Dwie daty głosowania w jednym PDF")
            voted_at = f"{_iso(*m.groups()[:3])}T{m.group(4)}"
            current = None
        elif current is not None:
            buffers[current].append(ln)
        else:
            raise VoteParseError(f"Nieoczekiwany wiersz: {ln!r}")

    if list(section_counts) != list(OPTIONS):
        raise VoteParseError(f"Sekcje w złej kolejności lub brak sekcji: {list(section_counts)}")
    if not voted_at:
        raise VoteParseError("Brak daty głosowania")

    names = {}
    for key, buf in buffers.items():
        joined = " ".join(buf)
        names[key] = [re.sub(r"\s+", " ", n).strip() for n in joined.split(",") if n.strip()]
    return ParsedVote(subject, summary, section_counts, names, voted_at, generated_on)


def esesja_vote_id(pdf_title: str) -> str | None:
    """Tytuł PDF to „wyniki_glosowania_<id>”; id to najpewniej numer głosowania w eSesji."""
    m = re.fullmatch(r"wyniki_glosowania_(\d+)", pdf_title or "")
    return m.group(1) if m else None
