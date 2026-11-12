"""Twarde sprawdzenia danych, bez AI i bez heurystyk.

Każda niezgodność to błąd. `run_all` zbiera wszystkie błędy i rzuca jeden
wyjątek CheckError z pełną listą, żeby od razu było widać skalę problemu.
Dane z błędem nie trafiają do pliku JSON ani na stronę.
"""

from __future__ import annotations

import datetime as dt
import math
import re

from .names import Resolver, UnknownName
from .votes import OPTIONS


class CheckError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} błęd(y/ów) w danych:\n- " + "\n- ".join(errors))


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(s: str) -> int:
    total, prev = 0, 0
    for ch in reversed(s):
        v = ROMAN[ch]
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


def _bip_date(s: str | None) -> str | None:
    """'30.10.2026' lub '17.09.2026 13:03' -> '2026-10-30'."""
    if not s:
        return None
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


# --- pojedyncze sprawdzenia; każde zwraca listę komunikatów o błędach ---

def check_councillors(councillors: list[dict], statutory_size: int) -> list[str]:
    errs = []
    if len(councillors) != statutory_size:
        errs.append(f"Lista radnych w BIP ma {len(councillors)} osób, a ustawowy skład to {statutory_size}")
    ids = [c["id"] for c in councillors]
    if len(set(ids)) != len(ids):
        errs.append("Powtórzony identyfikator radnego na liście")
    return errs


def check_clubs(clubs: list[dict], resolver: Resolver, councillors: list[dict]) -> list[str]:
    errs = []
    by_post = {c["bip_post_id"]: c["id"] for c in councillors}
    seen: dict[str, str] = {}
    for club in clubs:
        for m in club["czlonkowie"]:
            try:
                cid = resolver.resolve(m["bip_name"])
            except UnknownName:
                errs.append(f"Klub {club['nazwa']!r}: osoby {m['bip_name']!r} nie ma na liście radnych")
                continue
            if m.get("bip_post_id") and by_post.get(m["bip_post_id"]) != cid:
                errs.append(f"Klub {club['nazwa']!r}: link przy {m['bip_name']!r} prowadzi do innego profilu")
            if cid in seen:
                errs.append(f"{m['bip_name']!r} jest w dwóch klubach: {seen[cid]!r} i {club['nazwa']!r}")
            seen[cid] = club["nazwa"]
    missing = {c["id"] for c in councillors} - set(seen)
    for cid in sorted(missing):
        errs.append(f"Radny {cid!r} nie występuje na stronie klubów (także wśród niezrzeszonych)")
    return errs


def check_vote(vote: dict, resolver: Resolver, councillor_ids: set[str], label: str) -> list[str]:
    errs = []
    s, sec, nm = vote["sumy"], vote["sumy_sekcji"], vote["imiennie_pdf"]
    for opt in OPTIONS:
        if s[opt] != sec[opt]:
            errs.append(f"{label}: suma {opt} w nagłówku ({s[opt]}) ≠ liczba w sekcji ({sec[opt]})")
        if s[opt] != len(nm[opt]):
            errs.append(f"{label}: suma {opt} ({s[opt]}) ≠ liczba nazwisk ({len(nm[opt])})")
    total = sum(s.values())
    if total != len(councillor_ids):
        errs.append(f"{label}: suma wszystkich głosów i nieobecnych ({total}) ≠ liczba radnych ({len(councillor_ids)})")
    seen: dict[str, str] = {}
    for opt in OPTIONS:
        for name in nm[opt]:
            try:
                cid = resolver.resolve(name)
            except UnknownName:
                errs.append(f"{label}: nazwiska {name!r} nie ma na liście radnych ani w tabeli aliasów")
                continue
            if cid in seen:
                errs.append(f"{label}: {name!r} występuje dwa razy ({seen[cid]} i {opt})")
            seen[cid] = opt
    for cid in sorted(councillor_ids - set(seen)):
        errs.append(f"{label}: radny {cid!r} nie występuje w wynikach imiennych")
    return errs


def check_adopted_vote_math(vote: dict, statutory_size: int, label: str) -> list[str]:
    """Warunki konieczne dla każdej podjętej uchwały (art. 14 u.s.g.):
    zwykła większość (za > przeciw) i kworum (obecna co najmniej połowa ustawowego składu)."""
    errs = []
    s = vote["sumy"]
    if not s["za"] > s["przeciw"]:
        errs.append(f"{label}: uchwała jest w BIP jako podjęta, a ZA ({s['za']}) ≤ PRZECIW ({s['przeciw']})")
    present = sum(s.values()) - s["nieobecni"]
    if present < math.ceil(statutory_size / 2):
        errs.append(f"{label}: obecnych {present}, mniej niż połowa ustawowego składu ({statutory_size})")
    return errs


def check_dates(session: dict, res: dict) -> list[str]:
    errs = []
    label = res["numer"]
    sdate = session["data"]
    if res["data"] != sdate:
        errs.append(f"{label}: data uchwały {res['data']} ≠ data sesji {sdate}")
    num_roman, _, yy = res["numer"].split("/")
    if num_roman != session["numer"]:
        errs.append(f"{label}: numer sesji w numerze uchwały ({num_roman}) ≠ numer sesji ({session['numer']})")
    if yy != sdate[2:4]:
        errs.append(f"{label}: rok w numerze uchwały (/{yy}) ≠ rok sesji ({sdate[:4]})")
    v = res.get("glosowanie")
    if v:
        if v["data_czas"][:10] != sdate:
            errs.append(f"{label}: data głosowania {v['data_czas'][:10]} ≠ data sesji {sdate}")
        if v["pdf_wygenerowano"] < v["data_czas"][:10]:
            errs.append(f"{label}: PDF głosowania wygenerowano ({v['pdf_wygenerowano']}) przed głosowaniem")
    inserted = _bip_date(res.get("bip_wprowadzono"))
    if inserted and inserted < sdate:
        errs.append(f"{label}: uchwała wprowadzona do BIP ({inserted}) przed datą sesji")
    return errs


def check_numbering(resolutions: list[dict]) -> list[str]:
    nums = sorted(int(r["numer"].split("/")[1]) for r in resolutions)
    if not nums:
        return ["Brak uchwał z datą sesji w BIP"]
    errs = []
    if len(set(nums)) != len(nums):
        errs.append("Powtórzony numer uchwały")
    gaps = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums))
    if gaps:
        errs.append(f"Luka w numeracji uchwał sesji (brak w BIP nr: {gaps})")
    return errs


def check_vote_attachments(resolutions: list[dict]) -> list[str]:
    errs = []
    seen_ids: dict[str, str] = {}
    seen_sha: dict[str, str] = {}
    for r in resolutions:
        if len(r["pdf_glosowania"]) != 1:
            errs.append(f"{r['numer']}: oczekiwano 1 PDF „głosowanie”, jest {len(r['pdf_glosowania'])}")
        v = r.get("glosowanie")
        if not v:
            continue
        for val, seen, what in ((v.get("esesja_id"), seen_ids, "identyfikator eSesji"),
                                (v["sha256"], seen_sha, "ten sam plik PDF")):
            if val and val in seen:
                errs.append(f"{r['numer']}: {what} głosowania jak przy {seen[val]}")
            if val:
                seen[val] = r["numer"]
    return errs


def run_all(data: dict, resolver: Resolver, statutory_size: int) -> dict:
    """Uruchamia wszystkie sprawdzenia. Zwraca podsumowanie albo rzuca CheckError."""
    errs: list[str] = []
    councillors = data["radni"]
    cids = {c["id"] for c in councillors}
    errs += check_councillors(councillors, statutory_size)
    errs += check_clubs(data["kluby"], resolver, councillors)
    errs += check_numbering(data["uchwaly"])
    errs += check_vote_attachments(data["uchwaly"])
    n_votes = 0
    for r in data["uchwaly"]:
        errs += check_dates(data["sesja"], r)
        if r.get("glosowanie"):
            n_votes += 1
            errs += check_vote(r["glosowanie"], resolver, cids, r["numer"])
            errs += check_adopted_vote_math(r["glosowanie"], statutory_size, r["numer"])
    if errs:
        raise CheckError(errs)
    return {
        "wynik": "wszystkie sprawdzenia przeszły",
        "sprawdzono_glosowan": n_votes,
        "sprawdzono_uchwal": len(data["uchwaly"]),
        "sprawdzono_radnych": len(councillors),
        "lista_sprawdzen": [
            "sumy w nagłówku = liczby w sekcjach = liczba nazwisk (dla każdej opcji)",
            "suma głosów i nieobecnych = liczba radnych",
            "każde nazwisko na liście radnych BIP (dokładnie lub przez ręczny alias)",
            "każdy radny dokładnie raz w każdym głosowaniu",
            "podjęta uchwała: ZA > PRZECIW i kworum (art. 14 u.s.g.)",
            "data uchwały = data głosowania = data sesji; numer i rok sesji w numerze uchwały",
            "PDF wygenerowany nie wcześniej niż głosowanie; wpis w BIP nie przed sesją",
            "numeracja uchwał sesji bez luk i powtórzeń",
            "dokładnie 1 PDF głosowania na uchwałę, różne pliki i identyfikatory",
            "lista radnych = ustawowy skład; każdy radny w dokładnie jednym klubie lub wśród niezrzeszonych",
        ],
    }
