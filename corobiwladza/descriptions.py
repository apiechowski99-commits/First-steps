"""Sprawdzanie opisów „po ludzku” (krok 4) i danych „A co dla mnie?” (krok 5).

Zasady, sprawdzane automatycznie:
- uchwała bez treści w BIP dostaje wyłącznie „brak opisu” (bez zgadywania),
- uchwała z treścią ma opis z 1–2 zdań,
- każde zdanie ma co najmniej jeden cytat, a każdy cytat występuje w tekście PDF,
- w opisie nie ma słów oceniających z listy STOP_WORDS.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .checks import CheckError
from .pdf import normalize_ws

NO_DESCRIPTION = "brak opisu"

# Słowa oceniające, których nie używamy w opisach (rdzenie, bez względu na wielkość liter).
STOP_WORDS = [
    r"ważn", r"istotn", r"kluczow", r"dobr[yaeo]", r"zł[yaeo]\b", r"korzystn", r"niekorzystn",
    r"świetn", r"doskonał", r"fataln", r"kontrowersyjn", r"spor(?:n|y\b)", r"niestety", r"na szczęście",
    r"skandal", r"sukces", r"porażk", r"słuszn", r"niesłuszn", r"ogromn", r"olbrzymi", r"bardzo",
    r"potrzebn", r"konieczn", r"niezbędn", r"pilnie", r"wreszcie", r"aż\b", r"tylko\b", r"zaledwie",
]
_STOP_RE = re.compile(r"\b(?:" + "|".join(STOP_WORDS) + r")", flags=re.I)
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


def _count_sentences(text: str) -> int:
    """Liczy zdania. Kropka po skrócie (ul., np., m.in., r. …) nie kończy zdania w środku tekstu."""
    t = text.strip()
    if not t or t[-1] not in ".!?":
        return 0
    inner = re.sub(r"\b(?:ul|np|m\.in|ok|tzw|r|nr|pkt|ust|al|godz|zł)\.", "_", t[:-1])
    return 1 + len(_SENTENCE_END.findall(inner))


def check_descriptions(session: dict, opisy: dict, texts: dict[str, str]) -> list[str]:
    """texts: numer uchwały -> pełny tekst wszystkich jej PDF z treścią."""
    errs = []
    entries = opisy.get("uchwaly", {})
    numbers = {r["numer"] for r in session["uchwaly"]}
    for extra in sorted(set(entries) - numbers):
        errs.append(f"Opis dla uchwały {extra}, której nie ma w danych sesji")
    for r in session["uchwaly"]:
        num = r["numer"]
        entry = entries.get(num)
        if not r["tresc"]:
            if entry and entry.get("zdania"):
                errs.append(f"{num}: brak treści uchwały w BIP, a jest opis. Ma być „{NO_DESCRIPTION}”")
            continue
        if not entry or not entry.get("zdania"):
            errs.append(f"{num}: jest treść uchwały, a nie ma opisu")
            continue
        zd = entry["zdania"]
        if not 1 <= len(zd) <= 2:
            errs.append(f"{num}: opis ma {len(zd)} zdań (dozwolone 1–2)")
        haystack = normalize_ws(texts[num])
        for i, z in enumerate(zd, 1):
            if _count_sentences(z["tekst"]) != 1:
                errs.append(f"{num}, zdanie {i}: to nie jest dokładnie jedno zdanie: {z['tekst']!r}")
            if m := _STOP_RE.search(z["tekst"]):
                errs.append(f"{num}, zdanie {i}: słowo oceniające {m.group(0)!r}")
            if not z.get("cytaty"):
                errs.append(f"{num}, zdanie {i}: brak cytatu-źródła")
            for q in z.get("cytaty", []):
                if normalize_ws(q) not in haystack:
                    errs.append(f"{num}, zdanie {i}: cytatu nie ma w PDF uchwały: {q!r}")
    return errs


def description_for(opisy: dict, resolution: dict) -> dict:
    """Opis do wyświetlenia: zdania albo „brak opisu” z powodem."""
    if not resolution["tresc"]:
        return {"brak": True, "powod": "BIP nie publikuje treści tej uchwały, jest tylko wynik głosowania."}
    entry = opisy["uchwaly"][resolution["numer"]]
    return {"brak": False, "zdania": entry["zdania"]}


# --- krok 5: „A co dla mnie?” ---

def parse_pl_decimal(s: str) -> Decimal:
    return Decimal(s.replace(" ", "").replace(",", "."))


def fmt_pln(d: Decimal) -> str:
    q = d.quantize(Decimal("0.01"))
    whole, frac = f"{q:.2f}".split(".")
    groups = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return " ".join(groups) + "," + frac + " zł"


def check_wallet(cdm: dict, doc_texts: dict[str, str]) -> list[str]:
    errs = []
    docs = cdm["dokumenty"]
    for key in docs:
        if key not in doc_texts:
            errs.append(f"A co dla mnie: brak tekstu dokumentu {key!r}")
    for rate in cdm["stawki"]:
        for year, v in rate["wartosci"].items():
            hay = normalize_ws(doc_texts.get(v["dokument"], ""))
            if normalize_ws(v["cytat"]) not in hay:
                errs.append(f"A co dla mnie: stawka {rate['id']} ({year}) – cytatu nie ma w {v['dokument']}: {v['cytat']!r}")
            if v["wartosc"] not in v["cytat"]:
                errs.append(f"A co dla mnie: stawka {rate['id']} ({year}) – wartość {v['wartosc']} nie występuje w cytacie")
    rate_ids = {r["id"] for r in cdm["stawki"]}
    for g in cdm["grupy"]:
        for part in g["przyklad"]["skladniki"]:
            if part["stawka"] not in rate_ids:
                errs.append(f"A co dla mnie: grupa {g['kto']!r} używa nieznanej stawki {part['stawka']!r}")
    for item in cdm.get("fakty", []):
        for q in item["cytaty"]:
            hay = normalize_ws(doc_texts.get(q["dokument"], ""))
            if normalize_ws(q["cytat"]) not in hay:
                errs.append(f"A co dla mnie: cytatu nie ma w {q['dokument']}: {q['cytat']!r}")
    return errs


def compute_wallet(cdm: dict) -> list[dict]:
    """Przykłady liczone wprost: powierzchnia × stawka, osobno dla każdego roku."""
    rates = {r["id"]: r for r in cdm["stawki"]}
    years = cdm["lata"]
    out = []
    for g in cdm["grupy"]:
        rows, totals = [], {y: Decimal("0") for y in years}
        for part in g["przyklad"]["skladniki"]:
            r = rates[part["stawka"]]
            area = Decimal(str(part["m2"]))
            row = {"opis": part["opis"], "m2": part["m2"], "stawka": r, "lata": {}}
            for y in years:
                rv = parse_pl_decimal(r["wartosci"][y]["wartosc"])
                amount = area * rv
                totals[y] += amount
                row["lata"][y] = {"stawka": r["wartosci"][y]["wartosc"], "kwota": amount}
            rows.append(row)
        out.append({"grupa": g, "wiersze": rows, "razem": totals,
                    "roznica": totals[years[-1]] - totals[years[0]]})
    return out
