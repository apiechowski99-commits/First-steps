"""Strona statyczna: lista decyzji, paski głosowań, filtr, profile radnych, źródła.

Strona nie ładuje nic z zewnątrz (żadnych czcionek, skryptów ani liczników).
Działa też bez JavaScriptu; skrypt dodaje tylko filtr.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import shutil
from pathlib import Path

from .build import ROOT, extract_text_cached
from .checks import CheckError
from .descriptions import (check_descriptions, check_wallet, compute_wallet, description_for,
                           fmt_pln)
from .fetch import Fetcher
from .votes import OPTIONS

ASSETS = Path(__file__).parent / "assets"

LABEL = {"za": "Za", "przeciw": "Przeciw", "wstrzymal_sie": "Wstrzymali się",
         "brak_glosu": "Nie głosowali", "nieobecni": "Nieobecni"}
LABEL_LOW = {"za": "za", "przeciw": "przeciw", "wstrzymal_sie": "wstrzymali się",
             "brak_glosu": "nie głosowali", "nieobecni": "nieobecni"}
LABEL_ONE = {"za": "Głosował(a) za", "przeciw": "Głosował(a) przeciw", "wstrzymal_sie": "Wstrzymał(a) się",
             "brak_glosu": "Nie głosował(a)", "nieobecni": "Nieobecny(-a)"}
MONTHS = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
          "września", "października", "listopada", "grudnia"]

e = html.escape


def plural(n: int, one: str, few: str, many: str) -> str:
    """Polska odmiana: 1 uchwała, 2–4 uchwały, 5 uchwał, 22 uchwały, 12 uchwał."""
    if n == 1:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def pl_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso[:10])
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def pl_short(iso: str) -> str:
    d = dt.date.fromisoformat(iso[:10])
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def is_unanimous(vote: dict) -> bool:
    """Reguła filtra (jedna dla wszystkich): zgodne = 0 przeciw i 0 wstrzymujących się."""
    return vote["sumy"]["przeciw"] == 0 and vote["sumy"]["wstrzymal_sie"] == 0


def page(title: str, body: str, depth: int = 0, description: str = "") -> str:
    up = "../" * depth
    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="stylesheet" href="{up}style.css">
</head>
<body>
<a class="skip" href="#tresc">Przejdź do treści</a>
<header class="top"><a class="brand" href="{up}index.html">Co robi władza?</a>
<nav><a href="{up}index.html">Decyzje</a><a href="{up}radni/index.html">Radni</a><a href="{up}o-danych.html">O danych</a></nav></header>
<main id="tresc">
{body}
</main>
<footer class="foot">
<p><strong>Co robi władza?</strong> (corobiwladza.pl) to niezależny prototyp. Nie jest to serwis Urzędu Miasta Gdyni.
Wszystkie dane pochodzą z <a href="https://bip.um.gdynia.pl">Biuletynu Informacji Publicznej UM Gdyni</a>.</p>
<p>Dane i opisy: <a href="https://creativecommons.org/licenses/by/4.0/deed.pl">CC BY 4.0</a>, podaj źródło: Co robi władza? (corobiwladza.pl).
Kod: <a href="https://joinup.ec.europa.eu/page/eupl-text-11-12">EUPL-1.2</a>.</p>
</footer>
<script src="{up}filtr.js" defer></script>
</body>
</html>
"""


def vote_bar(v: dict, size: int) -> str:
    s = v["sumy"]
    segs = "".join(
        f'<span class="seg seg-{o}" style="width:{s[o] / size * 100:.4f}%"></span>' for o in OPTIONS if s[o]
    )
    aria = ", ".join(f"{LABEL[o]}: {s[o]}" for o in OPTIONS)
    return f'<div class="bar" role="img" aria-label="Wynik głosowania. {e(aria)}">{segs}</div>'


def legend_html() -> str:
    items = "".join(f'<li><span class="key seg-{o}"></span>{LABEL[o]}</li>' for o in OPTIONS)
    return f'<ul class="legend">{items}</ul>'


def vote_sentence(v: dict, size: int) -> str:
    """Zdanie o wyniku, budowane według stałej reguły (ta sama dla każdej uchwały)."""
    s = v["sumy"]
    parts = [f"Za: {s['za']} z {size} radnych",
             "Przeciw: nikt" if s["przeciw"] == 0 else f"Przeciw: {s['przeciw']}"]
    for o in ("wstrzymal_sie", "brak_glosu", "nieobecni"):
        if s[o]:
            parts.append(f"{LABEL[o]}: {s[o]}")
    return "<b>Przyjęta.</b> " + " · ".join(parts)


def club_lines(v: dict, clubs: list[dict]) -> str:
    """Jak głosowały kluby (alfabetycznie, dla każdego klubu tak samo)."""
    vote_of = {cid: o for o in OPTIONS for cid in v["imiennie"][o]}
    rows = []
    for club in sorted(clubs, key=lambda c: c["nazwa"]):
        counts = {o: 0 for o in OPTIONS}
        for m in club["czlonkowie"]:
            counts[vote_of[m["id"]]] += 1
        parts = ", ".join(f"{LABEL_LOW[o]} {counts[o]}" for o in OPTIONS if counts[o])
        rows.append(f"<li><b>{e(club['nazwa'])}</b>: {parts}</li>")
    return f'<ul class="clubs">{"".join(rows)}</ul>'


def names_list(v: dict, people: dict, up: str = "") -> str:
    parts = []
    for o in OPTIONS:
        ids = sorted(v["imiennie"][o], key=lambda i: people[i]["bip_name"])
        if not ids:
            continue
        items = ", ".join(f'<a href="{up}radni/{i}.html">{e(people[i]["imie_nazwisko"])}</a>' for i in ids)
        parts.append(f"<p><b>{LABEL[o]} ({len(ids)}):</b> {items}</p>")
    return "".join(parts)


def wallet_html(cdm: dict, doc_urls: dict[str, str]) -> str:
    calc = compute_wallet(cdm)
    y0, y1 = cdm["lata"]

    def src(doc: str, label: str = "źródło") -> str:
        return f'<a class="src" href="{e(doc_urls[doc])}">{e(label)}</a>'

    rate_rows = []
    for r in cdm["stawki"]:
        a, b = r["wartosci"][y0], r["wartosci"][y1]
        rate_rows.append(
            f"<tr><th scope=row>{e(r['nazwa'])}<br><small>{e(r['jednostka'])}</small></th>"
            f"<td>{e(a['wartosc'])} zł {src(a['dokument'])}</td><td>{e(b['wartosc'])} zł {src(b['dokument'])}</td></tr>")
    groups = []
    for c in calc:
        g = c["grupa"]
        lines = []
        for w in c["wiersze"]:
            lines.append(
                f"<li>{e(w['opis'])}: {w['m2']} m² × {e(w['lata'][y1]['stawka'])} zł = <b>{fmt_pln(w['lata'][y1]['kwota'])}</b>"
                f" <small>(w {y0}: {w['m2']} m² × {e(w['lata'][y0]['stawka'])} zł = {fmt_pln(w['lata'][y0]['kwota'])})</small></li>")
        diff = c["roznica"]
        sign = "+" if diff > 0 else ""
        groups.append(
            f'<div class="group"><h4>{e(g["kto"])}</h4><p class="ex">Przykład: {e(g["przyklad"]["tytul"])}</p>'
            f"<ul>{''.join(lines)}</ul>"
            f"<p>Razem rocznie: <b>{fmt_pln(c['razem'][y1])}</b> w {y1}, {fmt_pln(c['razem'][y0])} w {y0} "
            f"(różnica: {sign}{fmt_pln(diff)}).</p><p class=note>{e(g['uwaga'])}</p></div>")
    facts = []
    for f in cdm["fakty"]:
        links = " ".join(src(q["dokument"]) for q in f["cytaty"])
        facts.append(f"<li>{e(f['tekst'])} {links}</li>")
    return f"""<section class="wallet" aria-labelledby="w-{e(cdm['uchwala'])}">
<h3 id="w-{e(cdm['uchwala'])}">A co dla mnie?</h3>
<p>{e(cdm['tytul'])}. Przykłady to proste mnożenie: powierzchnia × stawka. Twoja kwota zależy od Twojej powierzchni.</p>
<div class="scroll"><table class="rates"><thead><tr><th scope=col>Co</th><th scope=col>{y0}</th><th scope=col>{y1}</th></tr></thead>
<tbody>{''.join(rate_rows)}</tbody></table></div>
{''.join(groups)}
<ul class="facts">{''.join(facts)}</ul>
</section>"""


def dup_note(r: dict, opisy: dict) -> str:
    """Gdy kilka uchwał ma ten sam nagłówek, dopisujemy krótki numer, żeby je odróżnić."""
    head = opisy["uchwaly"][r["numer"]]["naglowek"]["tekst"]
    same = sum(1 for x in opisy["uchwaly"].values() if x.get("naglowek", {}).get("tekst") == head)
    return f' <small class="nr">(uchwała nr {e(r["numer"])})</small>' if same > 1 else ""


def _src(url: str, quotes: list[str]) -> str:
    return (f'<a class="src" href="{e(url)}" title="Cytaty w źródle: {e(" | ".join(quotes))}">źródło</a>')


def resolution_card(r: dict, d: dict, opisy: dict, people: dict, wallet: str | None) -> str:
    v = r["glosowanie"]
    size = len(d["radni"])
    desc = description_for(opisy, r)
    text_url = r["tresc"][0]["pdf_url"] if r["tresc"] else None
    head = desc["naglowek"]
    head_src = _src(text_url or v["pdf_url"], head["cytaty"]) if text_url else ""
    parts = [f'<h3 class="head">{e(head["tekst"])}{dup_note(r, opisy)} {head_src}</h3>']
    if desc["brak"]:
        parts.append('<p class="nodesc">Treści tej uchwały nie ma w BIP, jest tylko wynik głosowania.</p>')
    else:
        k = desc["kogo_dotyczy"]
        parts.append(f'<p class="who"><b>Kogo dotyczy:</b> {e(k["tekst"])} {_src(text_url, k["cytaty"])}</p>')
        sents = " ".join(f'{e(z["tekst"])} {_src(text_url, z["cytaty"])}' for z in desc["zdania"])
        parts.append(f'<p class="desc">{sents}</p>')
        if desc.get("kontekst"):
            c = desc["kontekst"]
            parts.append(f'<p class="ctx"><b>Warto wiedzieć:</b> {e(c["tekst"])} {_src(text_url, c["cytaty"])}</p>')
    zg = is_unanimous(v)
    clubs = "" if zg else f'<p class="small">Jak głosowały kluby:</p>{club_lines(v, d["kluby"])}'
    parts.append(f"""<div class="vote">{vote_bar(v, size)}
<p class="vs">{vote_sentence(v, size)} <a class="src" href="{e(v['pdf_url'])}">źródło</a></p>
{clubs}</div>""")
    if wallet:
        parts.append(wallet)
    point = f"pkt {e(r['punkt_porzadku'])} porządku obrad" if r.get("punkt_porzadku") else "spoza opublikowanego porządku obrad"
    links = [f'<a href="{e(v["pdf_url"])}">Wyniki głosowania (PDF)</a>']
    if text_url:
        links.insert(0, f'<a href="{e(text_url)}">Treść uchwały (PDF)</a>')
    if r.get("pdf_projektu"):
        links.append(f'<a href="{e(r["pdf_projektu"])}">Projekt uchwały (PDF)</a>')
    parts.append(f"""<details><summary>Kto jak głosował</summary>{names_list(v, people)}</details>
<details><summary>Dokumenty i oficjalny tytuł</summary>
<p class="small">Uchwała nr {e(r['numer'])} · {point} · głosowanie {pl_short(v['data_czas'])}, godz. {v['data_czas'][11:16]}</p>
<p class="small">Oficjalny tytuł: {e(r['tytul'])}</p>
<p class="links">{' · '.join(links)}</p></details>""")
    anchor = r["numer"].replace("/", "-")
    return f'<article class="card" id="{anchor}" data-zgodna="{1 if zg else 0}">\n' + "\n".join(parts) + "\n</article>"


def theme_sections(d: dict, opisy: dict, people: dict, wallets: dict) -> tuple[str, str]:
    """Uchwały pogrupowane w stałe tematy (zawsze ta sama kolejność); w temacie według numeru."""
    by_theme: dict[str, list] = {}
    for r in d["uchwaly"]:
        by_theme.setdefault(opisy["uchwaly"][r["numer"]]["temat"], []).append(r)
    texts_url = {r["numer"]: r["tresc"][0]["pdf_url"] for r in d["uchwaly"] if r["tresc"]}
    sections, toc = [], []
    for t in opisy["tematy"]:
        items = sorted(by_theme.get(t["id"], []), key=lambda r: int(r["numer"].split("/")[1]))
        if not items:
            continue
        intro = ""
        if t.get("wstep"):
            w = t["wstep"]
            intro = f'<p class="intro">{e(w["tekst"])} {_src(texts_url[t["wstep_zrodlo"]], w["cytaty"])}</p>'
        elif t.get("uwaga"):
            intro = f'<p class="intro">{e(t["uwaga"])}</p>'
        cards = "\n".join(resolution_card(r, d, opisy, people, wallets.get(r["numer"])) for r in items)
        sections.append(f'<section class="theme" id="t-{t["id"]}"><h2>{e(t["nazwa"])} <small>({len(items)})</small></h2>\n{intro}\n{cards}</section>')
        toc.append(f'<li><a href="#t-{t["id"]}">{e(t["nazwa"])}</a> <small>({len(items)})</small></li>')
    return "\n".join(sections), f'<ul class="toc">{"".join(toc)}</ul>'


def councillor_page(c: dict, d: dict, opisy: dict) -> str:
    groups = {o: [] for o in OPTIONS}
    for r in d["uchwaly"]:
        v = r["glosowanie"]
        opt = next(o for o in OPTIONS if c["id"] in v["imiennie"][o])
        anchor = r["numer"].replace("/", "-")
        head = opisy["uchwaly"][r["numer"]]["naglowek"]["tekst"]
        groups[opt].append(f'<li><a href="../index.html#{anchor}">{e(head)}</a>{dup_note(r, opisy)}</li>')
    s = d["sesja"]
    n = len(d["uchwaly"])
    club_src = d["meta"]["zrodla"]["kluby"]
    summary = "".join(f"<li>{LABEL_ONE[o]}: <b>{len(groups[o])}</b></li>" for o in OPTIONS)
    lists = []
    for o in ("przeciw", "wstrzymal_sie", "brak_glosu", "nieobecni"):
        if groups[o]:
            lists.append(f'<h2>{LABEL_ONE[o]} ({len(groups[o])})</h2><ul class="plain">{"".join(groups[o])}</ul>')
    if groups["za"]:
        lists.append(f'<details><summary>{LABEL_ONE["za"]} ({len(groups["za"])})</summary><ul class="plain">{"".join(groups["za"])}</ul></details>')
    body = f"""<section class="person">
<p class="meta">Radny / radna Rady Miasta Gdyni, kadencja {e(d['meta']['kadencja'])}</p>
<h1>{e(c['imie_nazwisko'])}</h1>
{f'<p>{e(c["funkcja"])}</p>' if c.get('funkcja') else ''}
<p>Klub: <b>{e(c['klub'])}</b> <small>(stan na {e(club_src['bip_aktualizacja'][:10])} wg <a href="{e(club_src['url_strony'])}">BIP</a>)</small></p>
<p>Na sesji {pl_date(s['data'])} rada głosowała nad {n} {plural(n, 'uchwałą', 'uchwałami', 'uchwałami')}.</p>
<ul class="counts">{summary}</ul>
{''.join(lists)}
<p class="note">Źródło: PDF „głosowanie” przy każdej uchwale w BIP. Pokazujemy tylko publiczną działalność radnych.
<a href="{e(c['bip_url'])}">Profil w BIP</a>.</p>
</section>"""
    return page(f"{c['imie_nazwisko']} – głosowania", body, depth=1,
                description=f"Jak {c['imie_nazwisko']} głosował(a) na sesji Rady Miasta Gdyni {pl_date(s['data'])}")


def fetch_texts(d: dict, cache: Path) -> dict[str, str]:
    f = Fetcher(cache)
    out = {}
    for r in d["uchwaly"]:
        parts = []
        for t in r["tresc"]:
            resp = f.get(t["pdf_url"])
            if resp.sha256 != t["sha256"]:
                raise CheckError([f"{r['numer']}: PDF treści zmienił się od pobrania (SHA-256 inne)"])
            parts.append(extract_text_cached(cache, resp))
        out[r["numer"]] = "\n".join(parts)
    return out


def build_site(city: str, cache: Path, out: Path) -> None:
    sessions = sorted((ROOT / "data" / city / "sesje").glob("*.json"))
    if not sessions:
        raise SystemExit("Brak danych sesji: uruchom najpierw `python -m corobiwladza pobierz`.")
    sfile = sessions[-1]
    d = json.loads(sfile.read_text("utf-8"))
    opisy = json.loads((ROOT / "data" / city / "opisy" / sfile.name).read_text("utf-8"))
    people = {c["id"]: c for c in d["radni"]}

    texts = fetch_texts(d, cache)
    errs = check_descriptions(d, opisy, texts)

    wallets = {}
    for wf in sorted((ROOT / "data" / city / "co-dla-mnie").glob("*.json")):
        cdm = json.loads(wf.read_text("utf-8"))
        res = next((r for r in d["uchwaly"] if r["numer"] == cdm["uchwala"]), None)
        if res is None:
            errs.append(f"A co dla mnie: uchwały {cdm['uchwala']} nie ma w sesji")
            continue
        f = Fetcher(cache)
        doc_urls, doc_texts = {}, {}
        for key, doc in cdm["dokumenty"].items():
            url = {"tresc_uchwaly_sesji": res["tresc"][0]["pdf_url"] if res["tresc"] else None,
                   "projekt_uchwaly_sesji": res.get("pdf_projektu")}.get(doc.get("zrodlo"), doc.get("url"))
            if not url:
                errs.append(f"A co dla mnie: brak adresu dokumentu {key}")
                continue
            doc_urls[key] = url
            doc_texts[key] = extract_text_cached(cache, f.get(url))
        errs += check_wallet(cdm, doc_texts)
        if not errs:
            wallets[cdm["uchwala"]] = wallet_html(cdm, doc_urls)
    if errs:
        raise CheckError(errs)

    if out.exists():
        shutil.rmtree(out)
    (out / "radni").mkdir(parents=True)
    for name in ("style.css", "filtr.js"):
        shutil.copy(ASSETS / name, out / name)

    s = d["sesja"]
    res = d["uchwaly"]
    n_zg = sum(is_unanimous(r["glosowanie"]) for r in res)
    fetched = sorted(x["pobrano"] for r in res for x in [r["glosowanie"], *r["tresc"]])
    fetched += [src["pobrano"] for src in d["meta"]["zrodla"].values()]
    data_date = pl_short(min(fetched))
    data_date_to = pl_short(max(fetched))
    date_txt = data_date if data_date == data_date_to else f"{data_date}–{data_date_to}"

    sections, toc = theme_sections(d, opisy, people, wallets)
    missing = [a for a in s["porzadek_projekty"] if not a["uchwala"]]
    missing_html = ""
    if missing:
        items = "".join(f'<li>{e(a["tytul_projektu"])} – <a href="{e(a["pdf_projektu"])}">projekt (PDF)</a></li>'
                        for a in missing)
        missing_html = f"""<section class="missing"><h2>Czego nie wiemy</h2>
<p>Te projekty były w <a href="{e(s['url'])}">planie sesji</a>, ale w BIP nie ma z nich uchwały.
BIP nie podaje, co się z nimi stało (np. czy zdjęto je z planu sesji, czy rada je odrzuciła).</p><ul>{items}</ul>
<p>BIP nie publikuje też głosowań nad poprawkami do uchwał.</p></section>"""

    body = f"""<section class="session">
<p class="meta">{e(d['meta']['organ'])}</p>
<h1>Co zdecydowała rada {pl_date(s['data'])}</h1>
<p>Na tej sesji rada podjęła <b>{len(res)}</b> {plural(len(res), 'uchwałę', 'uchwały', 'uchwał')}. Przy każdej: co zmienia, kogo dotyczy i jak głosowali radni. Każde zdanie ma link do źródła.</p>
<nav aria-label="Tematy"><h2 class="small-h">W skrócie</h2>{toc}</nav>
<details class="howto"><summary>Jak czytać pasek głosowania</summary>{legend_html()}
<p class="small">„Nie głosowali” to osoby oznaczone w protokole głosowania jako „brak głosu”. „Nieobecni” to osoby, których nie było na głosowaniu.</p></details>
<p class="small">Dane z BIP: {date_txt}. <a href="o-danych.html">Skąd są dane i jak je sprawdzamy</a>.</p>
</section>
<div class="filter" hidden>
<p id="f-label">Pokaż:</p>
<div role="group" aria-labelledby="f-label">
<button type="button" data-f="all" aria-pressed="true">Wszystkie ({len(res)})</button>
<button type="button" data-f="1" aria-pressed="false">Bez sprzeciwu ({n_zg})</button>
<button type="button" data-f="0" aria-pressed="false">Z głosami przeciw lub wstrzymującymi ({len(res) - n_zg})</button>
</div>
</div>
<p class="small" id="f-count" aria-live="polite"></p>
{sections}
{missing_html}"""
    (out / "index.html").write_text(
        page(f"{s['numer']} sesja Rady Miasta Gdyni – Co robi władza?", body,
             description=f"Decyzje Rady Miasta Gdyni z {pl_date(s['data'])} prostym językiem, z głosowaniami imiennymi i źródłami."),
        "utf-8")

    for c in d["radni"]:
        (out / "radni" / f"{c['id']}.html").write_text(councillor_page(c, d, opisy), "utf-8")
    rows = "".join(
        f'<li><a href="{c["id"]}.html">{e(c["imie_nazwisko"])}</a> <small>– {e(c["klub"])}'
        f'{", " + e(c["funkcja"]) if c.get("funkcja") else ""}</small></li>'
        for c in sorted(d["radni"], key=lambda c: c["bip_name"]))
    club_src = d["meta"]["zrodla"]["kluby"]
    (out / "radni" / "index.html").write_text(page("Radni – Co robi władza?", f"""<section>
<h1>Radni Rady Miasta Gdyni</h1>
<p>{len(d['radni'])} osób, kolejność alfabetyczna według nazwiska. Kluby: stan na {e(club_src['bip_aktualizacja'][:10])} wg <a href="{e(club_src['url_strony'])}">BIP</a>.
Lista radnych: <a href="https://bip.um.gdynia.pl/radni-ix-kadencji-2024-2029,9175">BIP</a>.</p>
<ul class="people">{rows}</ul></section>""", depth=1, description="Radni Rady Miasta Gdyni i ich głosowania"), "utf-8")

    checks = "".join(f"<li>{e(x)}</li>" for x in d["sprawdzenia"]["lista_sprawdzen"])
    pob = d["meta"]["pobieranie"]
    (out / "o-danych.html").write_text(page("O danych – Co robi władza?", f"""<section class="about">
<h1>O danych</h1>
<h2>Skąd są dane</h2>
<ul>
<li>Porządek obrad, uchwały, PDF z wynikami głosowań, lista radnych i kluby: <a href="https://bip.um.gdynia.pl">BIP Urzędu Miasta Gdyni</a> (przez publiczne API, z którego korzysta strona BIP).</li>
<li>PDF „głosowanie” jest wygenerowany przez system eSesja (app.esesja.pl) i opublikowany przez miasto w BIP.</li>
<li>Portal gdynia.esesja.pl blokuje programy pobierające (zabezpieczenie anty-botowe), więc z niego nie korzystamy.</li>
</ul>
<h2>Czego tu nie ma</h2>
<p>{e(d['meta']['zakres'])} BIP publikuje głosowanie tylko przy podjętej uchwale.</p>
<h2>Jak sprawdzamy dane</h2>
<p>Przed zbudowaniem strony program sprawdza dane bez udziału AI. Każda niezgodność zatrzymuje budowę. Sprawdzenia:</p>
<ul>{checks}</ul>
<p>Wynik: {e(d['sprawdzenia']['wynik'])} ({d['sprawdzenia']['sprawdzono_glosowan']} głosowań, {d['sprawdzenia']['sprawdzono_radnych']} radnych).</p>
<h2>Opisy „po ludzku”</h2>
<p>Przy każdej uchwale jest prosty nagłówek, informacja „kogo dotyczy”, opis w 1–2 zdaniach i czasem „warto wiedzieć”. Wszystko powstaje tylko z treści uchwały i jej uzasadnienia. {e(opisy['metoda'])}
Każde zdanie ma cytaty z PDF uchwały. Program sprawdza, czy każdy cytat naprawdę jest w tekście PDF, i odrzuca słowa oceniające.
Gdy BIP nie publikuje treści uchwały (np. skargi i petycje), pokazujemy tylko nagłówek z tytułu w BIP i wynik głosowania.</p>
<h2>Słowniczek</h2>
<ul>
<li><b>Za / Przeciw / Wstrzymali się</b> – tak radni zagłosowali.</li>
<li><b>Nie głosowali</b> – w PDF z eSesji grupa „brak głosu”. <b>Nieobecni</b> – osobna grupa w tym samym PDF. PDF nie wyjaśnia dokładniej różnicy.</li>
<li><b>Bez sprzeciwu</b> – 0 głosów przeciw i 0 wstrzymujących się. Pozostałe to uchwały z głosami przeciw lub wstrzymującymi.</li>
<li><b>Tematy</b> – uchwały są zawsze w tych samych grupach i w tej samej kolejności, a w grupie według numeru uchwały.</li>
</ul>
<h2>Dane osobowe</h2>
<p>Pokazujemy tylko publiczną działalność radnych: imię i nazwisko, funkcję w radzie, klub i głosowania. Osoby prywatne w tytułach uchwał BIP oznacza jako „XX”; zostawiamy to bez zmian.</p>
<h2>Pobieranie</h2>
<p>Program pobiera najwyżej 1 plik na sekundę i przedstawia się jako CoRobiWladza (corobiwladza.pl). Ostatnie zbudowanie danych: {e(d['meta']['zbudowano'][:10])}
({pob['zapytania_sieciowe']} zapytań do sieci, {pob['z_cache']} z pamięci podręcznej).</p>
<h2>Licencja</h2>
<p>Dane w formacie JSON, opisy i teksty tej strony: <a href="https://creativecommons.org/licenses/by/4.0/deed.pl">CC BY 4.0</a>.
Możesz z nich korzystać, także komercyjnie, jeśli podasz źródło: Co robi władza? (corobiwladza.pl).
Kod programu: <a href="https://joinup.ec.europa.eu/page/eupl-text-11-12">EUPL-1.2</a>.
Uchwały i ich projekty nie podlegają prawu autorskiemu (art. 4 ustawy o prawie autorskim i prawach pokrewnych).</p>
</section>""", description="Skąd pochodzą dane i jak je sprawdzamy"), "utf-8")
    print(f"Strona zapisana w {out} ({len(res)} {plural(len(res), 'uchwała', 'uchwały', 'uchwał')}, {len(d['radni'])} profili radnych)")
