"""Adapter BIP Urzędu Miasta Gdyni (api.um.gdynia.pl, publiczne API JSON za stroną BIP).

Adapter tylko pobiera i rozbiera dane. Nie sprawdza ich spójności, to robi
moduł checks.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re

from . import names
from .fetch import Fetcher

MONTHS_GEN = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
    "lipca": 7, "sierpnia": 8, "września": 9, "października": 10, "listopada": 11, "grudnia": 12,
}

_SESSION_TITLE = re.compile(
    r"^(?P<num>[IVXLC]+)\s+(?:(?P<kind>nadzwyczajna|uroczysta)\s+)?sesja\s+Rady\s+Miasta\s+Gdyni"
    r"\s+z\s+(?:dnia\s+)?(?P<d>\d{1,2})\s+(?P<m>\w+)\s+(?P<y>\d{4})\s*r\.?\s*$",
    flags=re.I,
)
_RES_TITLE = re.compile(
    r"^Uchwała nr (?P<num>[IVXLC]+/\d+/\d{2}) Rady Miasta Gdyni z dnia "
    r"(?P<d>\d{2})\.(?P<m>\d{2})\.(?P<y>\d{4}) w sprawie (?P<subject>.+)$"
)


class BipFormatError(ValueError):
    pass


def strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).replace("\u00a0", " ")


def parse_session_title(title: str) -> dict:
    t = re.sub(r"\s+", " ", title).strip()
    m = _SESSION_TITLE.match(t)
    if not m or m.group("m").lower() not in MONTHS_GEN:
        raise BipFormatError(f"Nie rozpoznaję tytułu sesji: {title!r}")
    date = dt.date(int(m.group("y")), MONTHS_GEN[m.group("m").lower()], int(m.group("d")))
    return {"numer": m.group("num").upper(), "rodzaj": (m.group("kind") or "zwyczajna").lower(),
            "data": date.isoformat()}


def parse_resolution_title(title_html: str) -> dict:
    t = re.sub(r"\s+", " ", strip_tags(title_html)).strip()
    m = _RES_TITLE.match(t)
    if not m:
        raise BipFormatError(f"Nie rozpoznaję tytułu uchwały: {t!r}")
    subject = m.group("subject").strip()
    if subject.lower().startswith("zmieniająca"):
        display = "Uchwała " + subject
    else:
        display = "Uchwała w sprawie " + subject
    return {
        "numer": m.group("num"),
        "data": f"{m.group('y')}-{m.group('m')}-{m.group('d')}",
        "w_sprawie": subject,
        "tytul_bip": t,
        "tytul": display.rstrip("."),
    }


def parse_agenda(content_html: str) -> list[dict]:
    """Projekty uchwał z porządku obrad: każdy link do PDF to jeden projekt."""
    aneks_at = content_html.find("Aneks do porządku obrad")
    items = []
    for m in re.finditer(r'<a\s+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', content_html, flags=re.S | re.I):
        before = content_html[: m.start()]
        label_raw = re.split(r"<br\s*/?>", before, flags=re.I)[-1]
        label = re.sub(r"\s+", " ", strip_tags(label_raw)).strip()
        m_num = re.match(r"^\d+(?:\.\d+)*", label)  # „5.5 z” (literówka w BIP) -> „5.5”
        label = m_num.group(0) if m_num else label.rstrip(".")
        in_aneks = aneks_at != -1 and m.start() > aneks_at
        items.append({
            "punkt": ("Aneks " if in_aneks else "") + label,
            "tytul_projektu": re.sub(r"\s+", " ", strip_tags(m.group(2))).strip(),
            "pdf_projektu": html.unescape(m.group(1)),
        })
    return items


def parse_clubs(content_html: str) -> list[dict]:
    clubs = []
    parts = re.split(r"<h2[^>]*>(.*?)</h2>", content_html, flags=re.S | re.I)
    # parts = [przed, nagłówek1, treść1, nagłówek2, treść2, ...]
    for header, body in zip(parts[1::2], parts[2::2]):
        club_name = re.sub(r"\s+", " ", strip_tags(header)).strip()
        members = []
        for chunk in re.split(r"<br\s*/?>", body, flags=re.I):
            line = re.sub(r"\s+", " ", strip_tags(chunk)).strip()
            if not line:
                continue
            link = re.search(r'href="[^"]*,(\d+)"', chunk)
            bip_name, chair, note = names.split_club_line(line)
            members.append({"bip_name": bip_name, "przewodniczacy_klubu": chair,
                            "dopisek_bip": note, "bip_post_id": link.group(1) if link else None})
        clubs.append({"nazwa": club_name, "czlonkowie": members})
    return clubs


class BipGdynia:
    def __init__(self, fetcher: Fetcher, cfg: dict):
        self.f = fetcher
        self.cfg = cfg["bip"]
        self.api = self.cfg["api"]

    def _json(self, path: str, params: dict | None = None):
        r = self.f.get(self.api + path, params)
        return r.json(), r

    def source(self, r) -> dict:
        return {"url": r.url, "pobrano": r.fetched_at, "sha256": r.sha256}

    def session_posts(self) -> list[dict]:
        """Wszystkie posty sesji bieżącej kadencji (z kategorii lat)."""
        sub, _ = self._json(f"/contents/subcategories/{self.cfg['kategoria_sesji_kadencji']}", {"bip": 1})
        out = []
        for cat in (sub.get("subcategories") or {}).get("categories") or []:
            posts, r = self._json(f"/contents/posts/category/{cat['id']}", {"limit": 100, "basic": 1})
            for p in (posts.get("posts") or {}).get("contents") or []:
                try:
                    meta = parse_session_title(p["title"])
                except BipFormatError:
                    continue  # np. harmonogram sesji – to nie jest sesja
                out.append({"bip_post_id": p["id"], "tytul": p["title"].strip(),
                            "url": p["url"], **meta})
        return sorted(out, key=lambda s: s["data"])

    def latest_session(self, today: dt.date) -> dict:
        past = [s for s in self.session_posts() if s["data"] <= today.isoformat()]
        if not past:
            raise BipFormatError("Brak sesji z datą nie późniejszą niż dziś")
        return past[-1]

    def session(self, post_id: str) -> dict:
        data, r = self._json(f"/contents/posts/{post_id}")
        p = data["posts"][0]
        meta = parse_session_title(p["title"])
        return {
            "bip_post_id": p["id"], "tytul": p["title"].strip(), "url": p["url"], **meta,
            "porzadek_projekty": parse_agenda(p.get("content") or ""),
            "bip_opublikowano": p["publication_date"], "bip_aktualizacja": p["update_date"],
            "zrodlo": self.source(r),
        }

    def resolutions_on(self, date_iso: str) -> tuple[list[dict], dict]:
        y, m, d = date_iso.split("-")
        form = json.dumps({"number": "", "date": f"{d}.{m}.{y}", "category": ""}, ensure_ascii=False)
        data, r = self._json("/contents/search_ordinances", {"form": form})
        out = []
        for it in data.get("ordinances") or []:
            meta = parse_resolution_title(it["title"])
            if meta["data"] != date_iso:
                continue
            votes = [a for a in it["attachments"] if a["name"].strip().lower() == "głosowanie"]
            texts = [a for a in it["attachments"] if a not in votes]
            out.append({
                **meta,
                "pdf_glosowania": [a["url"] for a in votes],
                "pdf_tresci": [a["url"] for a in texts],
                "bip_wprowadzono": it.get("insert_date"),
                "bip_data_wytworzenia": it.get("date_of_manufacture"),
            })
        return out, self.source(r)

    def councillors(self) -> tuple[list[dict], dict]:
        data, r = self._json(f"/contents/posts/category/{self.cfg['kategoria_radnych']}", {"limit": 100, "basic": 1})
        posts = data["posts"]
        if int(posts["pages"]["itemCount"]) != len(posts["contents"]):
            raise BipFormatError("Lista radnych ma więcej niż jedną stronę wyników")
        out = []
        for p in posts["contents"]:
            bip_name, function = names.split_function(p["title"])
            out.append({
                "id": names.slug(bip_name), "bip_post_id": p["id"], "bip_name": bip_name,
                "imie_nazwisko": names.display_from_bip(bip_name),
                "funkcja": function, "bip_url": p["url"],
            })
        return out, self.source(r)

    def clubs(self) -> tuple[list[dict], dict]:
        data, r = self._json(f"/contents/posts/{self.cfg['post_klubow']}")
        p = data["posts"][0]
        return parse_clubs(p.get("content") or ""), {**self.source(r), "url_strony": p["url"],
                                                     "bip_aktualizacja": p["update_date"]}
