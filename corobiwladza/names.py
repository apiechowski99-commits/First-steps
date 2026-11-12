"""Dopasowanie nazwisk bez zgadywania.

Klucz osoby to posortowany zbiór członów imienia i nazwiska (małe litery,
dzielone po spacjach i myślnikach). Dzięki temu „Natalia Kłopotek Główczewska”
(PDF) i „Kłopotek - Główczewska Natalia” (BIP) to ta sama osoba. Kolejność
i myślniki nie mają znaczenia, ale litery muszą się zgadzać co do joty.

Wszystko inne (np. „Marcus da Silva” vs „da Silva de Oliveira Marcus”)
wymaga wpisu w ręcznie sprawdzonej tabeli aliasów w data/miasta/<miasto>.json.
"""

from __future__ import annotations

import re
import unicodedata

_FUNCTION = re.compile(r"\s+-\s+((?:Wice)?[Pp]rzewodnicz\w+ Rady Miasta)\s*$")
_CLUB_CHAIR = re.compile(r"\s+-\s+przewodnicz\w+ klubu\s*$", flags=re.I)
_PAREN = re.compile(r"\s*\(([^)]*)\)\s*$")


def clean(name: str) -> str:
    name = unicodedata.normalize("NFC", name).replace(" ", " ")
    name = re.sub(r"\s*-\s*", " - ", name)
    return re.sub(r"\s+", " ", name).strip()


def key(name: str) -> str:
    parts = re.split(r"[\s\-]+", clean(name).lower())
    return " ".join(sorted(p for p in parts if p))


def split_function(bip_title: str) -> tuple[str, str | None]:
    """„Zastawna Beata - Przewodnicząca Rady Miasta” -> („Zastawna Beata”, „Przewodnicząca Rady Miasta”)."""
    t = clean(bip_title)
    m = _FUNCTION.search(t)
    if m:
        return t[: m.start()].strip(), m.group(1)
    return t, None


def split_club_line(line: str) -> tuple[str, bool, str | None]:
    """Wiersz ze strony klubów -> (nazwisko imię, czy przewodniczy klubowi, dopisek w nawiasie)."""
    t = clean(line)
    note = None
    m = _PAREN.search(t)
    if m:
        note, t = m.group(1).strip(), t[: m.start()].strip()
    chair = bool(_CLUB_CHAIR.search(t))
    t = _CLUB_CHAIR.sub("", t).strip()
    return t, chair, note


def display_from_bip(bip_name: str) -> str:
    """BIP podaje „Nazwisko(-a) Imię”; wyświetlamy „Imię Nazwisko”, dwuczłonowe z łącznikiem bez spacji."""
    t = clean(bip_name)
    *surname, first = t.split(" ")
    surname_s = re.sub(r"\s*-\s*", "-", " ".join(surname))
    return f"{first} {surname_s}"


_PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def slug(s: str) -> str:
    s = clean(s).translate(_PL).lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


class UnknownName(KeyError):
    pass


class Resolver:
    """Zamienia nazwisko z dowolnego źródła na identyfikator radnego. Brak dopasowania = wyjątek."""

    def __init__(self, councillors: list[dict], aliases: dict[str, str]):
        self.by_key: dict[str, str] = {}
        for c in councillors:
            k = key(c["bip_name"])
            if k in self.by_key:
                raise ValueError(f"Dwie osoby z tym samym kluczem nazwiska: {k!r}")
            self.by_key[k] = c["id"]
        self.alias_keys: dict[str, str] = {}
        for alias, bip_name in aliases.items():
            target = self.by_key.get(key(bip_name))
            if target is None:
                raise ValueError(f"Alias {alias!r} wskazuje na osobę spoza listy: {bip_name!r}")
            self.alias_keys[key(alias)] = target

    def resolve(self, name: str) -> str:
        k = key(name)
        if k in self.by_key:
            return self.by_key[k]
        if k in self.alias_keys:
            return self.alias_keys[k]
        raise UnknownName(name)
