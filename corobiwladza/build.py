"""Potok: sesja -> uchwały -> głosowania -> nazwiska i kluby -> sprawdzenia -> JSON."""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path

from . import __version__, pdf, votes
from .bip_gdynia import BipGdynia
from .checks import run_all
from .fetch import USER_AGENT, Fetcher
from .names import Resolver

ROOT = Path(__file__).resolve().parent.parent


def load_city(city: str) -> dict:
    return json.loads((ROOT / "data" / "miasta" / f"{city}.json").read_text("utf-8"))


def aliases_of(cfg: dict) -> dict[str, str]:
    return {k: v for k, v in cfg.get("aliasy_nazwisk", {}).items() if not k.startswith("_")}


def text_cache_path(cache_dir: Path, sha: str) -> Path:
    p = Path(cache_dir) / "text"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{sha}.txt"


def extract_text_cached(cache_dir: Path, resp) -> str:
    path = text_cache_path(cache_dir, resp.sha256)
    if path.exists():
        return path.read_text("utf-8")
    t = pdf.text(resp.path)
    path.write_text(t, "utf-8")
    return t


# --- dopasowanie projektów z porządku obrad do podjętych uchwał ---

_STOP = {"w", "z", "i", "o", "na", "do", "od", "dla", "oraz", "sprawie", "uchwały", "uchwała",
         "projekt", "ref", "gdyni", "gdynia", "miasta", "gminy"}


def _tokens(s: str) -> set[str]:
    s = s.lower().replace("z mieniająca", "zmieniająca")
    return {t for t in re.findall(r"\w+", s) if t not in _STOP and len(t) > 1}


def match_agenda(agenda: list[dict], resolutions: list[dict], threshold: float = 0.75) -> None:
    """Łączy projekt z porządku obrad z uchwałą o tym samym przedmiocie (podobieństwo Jaccarda słów).

    Służy tylko do pokazania, z których projektów nie powstała uchwała. Każde
    połączenie jest zapisane z wynikiem podobieństwa, do wglądu.
    """
    pairs = []
    for i, a in enumerate(agenda):
        ta = _tokens(a["tytul_projektu"])
        for j, r in enumerate(resolutions):
            tr = _tokens(r["w_sprawie"])
            score = len(ta & tr) / len(ta | tr) if ta | tr else 0.0
            pairs.append((score, i, j))
    used_a, used_r = set(), set()
    for score, i, j in sorted(pairs, reverse=True):
        if score < threshold or i in used_a or j in used_r:
            continue
        used_a.add(i)
        used_r.add(j)
        agenda[i]["uchwala"] = resolutions[j]["numer"]
        agenda[i]["podobienstwo"] = round(score, 3)
        resolutions[j]["punkt_porzadku"] = agenda[i]["punkt"]
        resolutions[j]["pdf_projektu"] = agenda[i]["pdf_projektu"]
    for i, a in enumerate(agenda):
        a.setdefault("uchwala", None)
    for r in resolutions:
        r.setdefault("punkt_porzadku", None)
        r.setdefault("pdf_projektu", None)


def build_session(city: str, cache_dir: Path, post_id: str | None = None,
                  offline: bool = False, today: dt.date | None = None,
                  out_dir: Path | None = None, log=print) -> Path:
    t0 = time.monotonic()
    cfg = load_city(city)
    f = Fetcher(cache_dir, offline=offline)
    bip = BipGdynia(f, cfg)

    if post_id is None:
        latest = bip.latest_session(today or dt.date.today())
        post_id = latest["bip_post_id"]
        log(f"Ostatnia sesja w BIP: {latest['tytul']}")
    session = bip.session(post_id)
    log(f"Sesja {session['numer']} z {session['data']}: {len(session['porzadek_projekty'])} projektów w porządku obrad")

    resolutions, res_src = bip.resolutions_on(session["data"])
    resolutions.sort(key=lambda r: int(r["numer"].split("/")[1]))
    log(f"Uchwały z datą sesji w BIP: {len(resolutions)}")
    councillors, cou_src = bip.councillors()
    clubs, club_src = bip.clubs()

    for n, r in enumerate(resolutions, 1):
        if len(r["pdf_glosowania"]) == 1:
            resp = f.get(r["pdf_glosowania"][0])
            parsed = votes.parse(pdf.text(resp.path))
            r["glosowanie"] = {
                "pdf_url": resp.url, "sha256": resp.sha256, "pobrano": resp.fetched_at,
                "esesja_id": votes.esesja_vote_id(pdf.info(resp.path).get("Title", "")),
                "temat": parsed.subject, "data_czas": parsed.voted_at,
                "pdf_wygenerowano": parsed.generated_on,
                "sumy": parsed.summary, "sumy_sekcji": parsed.section_counts,
                "imiennie_pdf": parsed.names,
            }
        else:
            r["glosowanie"] = None
        texts = []
        for url in r["pdf_tresci"]:
            resp = f.get(url)
            full = extract_text_cached(cache_dir, resp)
            body, just = pdf.split_justification(full)
            info = pdf.info(resp.path)
            texts.append({
                "pdf_url": resp.url, "sha256": resp.sha256, "pobrano": resp.fetched_at,
                "tytul_pdf": info.get("Title"), "stron": int(info.get("Pages", "0") or 0),
                "znakow_tekstu": len(pdf.normalize_ws(full)),
                "ma_uzasadnienie": just is not None,
            })
        r["tresc"] = texts
        log(f"  [{n}/{len(resolutions)}] {r['numer']}: głosowanie {'tak' if r['glosowanie'] else 'BRAK'}, "
            f"treść {len(texts)} PDF")

    match_agenda(session["porzadek_projekty"], resolutions)

    data = {
        "meta": {
            "projekt": "Co robi władza? (corobiwladza.pl)",
            "wersja_narzedzia": __version__,
            "user_agent": USER_AGENT,
            "miasto": cfg["nazwa"], "organ": cfg["organ"], "kadencja": cfg["kadencja"],
            "ustawowy_sklad": cfg["ustawowy_sklad"],
            "zbudowano": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            "zrodla": {"sesja": session.pop("zrodlo"), "uchwaly": res_src, "radni": cou_src, "kluby": club_src},
            "zakres": ("Głosowania końcowe nad uchwałami podjętymi i opublikowanymi w BIP. "
                       "Bez głosowań nad poprawkami, projektami odrzuconymi i sprawami proceduralnymi."),
        },
        "sesja": session,
        "radni": councillors,
        "kluby": clubs,
        "uchwaly": resolutions,
    }

    resolver = Resolver(councillors, aliases_of(cfg))
    data["sprawdzenia"] = run_all(data, resolver, cfg["ustawowy_sklad"])

    # Po sprawdzeniach każde nazwisko na pewno ma identyfikator.
    club_of = {}
    for club in clubs:
        for m in club["czlonkowie"]:
            m["id"] = resolver.resolve(m["bip_name"])
            club_of[m["id"]] = club["nazwa"]
    for c in councillors:
        c["klub"] = club_of[c["id"]]
    for r in resolutions:
        if r["glosowanie"]:
            r["glosowanie"]["imiennie"] = {
                opt: [resolver.resolve(n) for n in names_] for opt, names_ in r["glosowanie"]["imiennie_pdf"].items()
            }

    elapsed = time.monotonic() - t0
    data["meta"]["pobieranie"] = {
        "zapytania_sieciowe": f.stats.network_requests, "z_cache": f.stats.cache_hits,
        "pobrano_bajtow": f.stats.bytes_downloaded, "czas_s": round(elapsed, 1),
        "w_tym_oczekiwanie_s": round(f.stats.seconds_waiting, 1),
    }
    out_dir = out_dir or ROOT / "data" / city / "sesje"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{session['data']}_{session['numer']}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")
    log(f"Zapisano {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} "
        f"({f.stats.network_requests} zapytań sieciowych, {f.stats.cache_hits} z cache, {elapsed:.0f} s)")
    return out
