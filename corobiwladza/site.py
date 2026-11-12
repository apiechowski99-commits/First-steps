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
         "brak_glosu": "Brak głosu", "nieobecni": "Nieobecni"}
LABEL_ONE = {"za": "za", "przeciw": "przeciw", "wstrzymal_sie": "wstrzymał(a) się",
             "brak_glosu": "brak głosu", "nieobecni": "nieobecny(-a)"}
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


def vote_bar(v: dict, size: int, label: str) -> str:
    s = v["sumy"]
    segs = "".join(
        f'<span class="seg seg-{o}" style="width:{s[o] / size * 100:.4f}%"></span>' for o in OPTIONS if s[o]
    )
    aria = ", ".join(f"{LABEL[o]}: {s[o]}" for o in OPTIONS)
    legend = "".join(
        f'<li><span class="key seg-{o}"></span>{LABEL[o]} <b>{s[o]}</b></li>' for o in OPTIONS
    )
    return (f'<div class="bar" role="img" aria-label="{e(label)}. {e(aria)}">{segs}</div>'
            f'<ul class="legend">{legend}</ul>')


def club_table(v: dict, clubs: list[dict]) -> str:
    """Zwięzła lista klubów (alfabetycznie). Pokazujemy tylko opcje z co najmniej jednym głosem, dla każdego klubu tak samo."""
    vote_of = {cid: o for o in OPTIONS for cid in v["imiennie"][o]}
    rows = []
    for club in sorted(clubs, key=lambda c: c["nazwa"]):
        counts = {o: 0 for o in OPTIONS}
        for m in club["czlonkowie"]:
            counts[vote_of[m["id"]]] += 1
        parts = " · ".join(f"{LABEL[o]} {counts[o]}" for o in OPTIONS if counts[o])
        rows.append(f"<li><b>{e(club['nazwa'])}</b> <small>({len(club['czlonkowie'])} os.)</small>: {parts}</li>")
    return f'<h4>Według klubów</h4><ul class="clubs">{"".join(rows)}</ul>'


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


def resolution_card(r: dict, d: dict, opisy: dict, people: dict, wallet: str | None) -> str:
    v = r["glosowanie"]
    size = len(d["radni"])
    desc = description_for(opisy, r)
    text_url = r["tresc"][0]["pdf_url"] if r["tresc"] else None
    if desc["brak"]:
        desc_html = f'<p class="nodesc"><b>Brak opisu.</b> {e(desc["powod"])}</p>'
    else:
        sents = []
        for z in desc["zdania"]:
            sents.append(f'{e(z["tekst"])} <a class="src" href="{e(text_url)}" title="Cytaty w źródle: '
                         f'{e(" | ".join(z["cytaty"]))}">źródło</a>')
        desc_html = f'<p class="desc">{" ".join(sents)}</p>'
    zg = is_unanimous(v)
    point = f" · pkt {e(r['punkt_porzadku'])} porządku obrad" if r.get("punkt_porzadku") else " · spoza opublikowanego porządku obrad"
    links = [f'<a href="{e(v["pdf_url"])}">Wyniki głosowania (PDF)</a>']
    if text_url:
        links.insert(0, f'<a href="{e(text_url)}">Treść uchwały (PDF)</a>')
    if r.get("pdf_projektu"):
        links.append(f'<a href="{e(r["pdf_projektu"])}">Projekt uchwały (PDF)</a>')
    anchor = r["numer"].replace("/", "-")
    return f"""<article class="card" id="{anchor}" data-zgodna="{1 if zg else 0}">
<p class="meta">Uchwała nr {e(r['numer'])}{point}</p>
<h2>{e(r['tytul'])}</h2>
{desc_html}
<p class="tag">{'Zgodne: nikt nie był przeciw ani się nie wstrzymał' if zg else 'Sporne: były głosy przeciw lub wstrzymujące się'}</p>
{vote_bar(v, size, 'Wynik głosowania')}
<p class="when">Głosowanie: {pl_short(v['data_czas'])}, godz. {v['data_czas'][11:16]} · <a href="{e(v['pdf_url'])}">źródło liczb</a></p>
{wallet or ''}
<details><summary>Jak głosowali radni</summary>
{club_table(v, d['kluby'])}
{names_list(v, people)}
</details>
<p class="links">{' · '.join(links)}</p>
</article>"""


def councillor_page(c: dict, d: dict) -> str:
    rows, counts = [], {o: 0 for o in OPTIONS}
    for r in d["uchwaly"]:
        v = r["glosowanie"]
        opt = next(o for o in OPTIONS if c["id"] in v["imiennie"][o])
        counts[opt] += 1
        anchor = r["numer"].replace("/", "-")
        rows.append(f'<tr><td><a href="../index.html#{anchor}">{e(r["numer"])}</a></td>'
                    f'<td>{e(r["tytul"])}</td><td class="v v-{opt}">{LABEL_ONE[opt]}</td></tr>')
    summary = "".join(f"<li>{LABEL[o]}: <b>{counts[o]}</b></li>" for o in OPTIONS)
    s = d["sesja"]
    club_src = d["meta"]["zrodla"]["kluby"]
    body = f"""<section class="person">
<p class="meta">Radny / radna Rady Miasta Gdyni, kadencja {e(d['meta']['kadencja'])}</p>
<h1>{e(c['imie_nazwisko'])}</h1>
{f'<p>{e(c["funkcja"])}</p>' if c.get('funkcja') else ''}
<p>Klub: <b>{e(c['klub'])}</b> <small>(stan na {e(club_src['bip_aktualizacja'][:10])} wg <a href="{e(club_src['url_strony'])}">BIP</a>)</small></p>
<p><a href="{e(c['bip_url'])}">Profil w BIP</a></p>
<h2>Głosowania na sesji {e(s['numer'])} ({pl_date(s['data'])})</h2>
<ul class="counts">{summary}</ul>
<div class="scroll"><table class="votes"><thead><tr><th scope=col>Uchwała</th><th scope=col>W sprawie</th><th scope=col>Głos</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="note">Źródło: PDF „głosowanie” przy każdej uchwale w BIP. Pokazujemy tylko publiczną działalność radnych.</p>
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

    cards = "\n".join(resolution_card(r, d, opisy, people, wallets.get(r["numer"])) for r in res)
    missing = [a for a in s["porzadek_projekty"] if not a["uchwala"]]
    missing_html = ""
    if missing:
        items = "".join(f'<li>pkt {e(a["punkt"])}: {e(a["tytul_projektu"])} – <a href="{e(a["pdf_projektu"])}">projekt (PDF)</a></li>'
                        for a in missing)
        missing_html = f"""<section class="missing"><h2>Projekty z porządku obrad bez uchwały w BIP</h2>
<p>Te projekty były w <a href="{e(s['url'])}">porządku obrad</a>, ale w BIP nie ma uchwały z tej sesji o tym przedmiocie.
BIP nie podaje, co się z nimi stało (np. czy zdjęto je z porządku obrad, czy je odrzucono).</p><ul>{items}</ul></section>"""

    body = f"""<section class="session">
<p class="meta">{e(d['meta']['organ'])} · kadencja {e(d['meta']['kadencja'])}</p>
<h1>{e(s['numer'])} sesja, {pl_date(s['data'])}</h1>
<p>Na tej sesji rada podjęła <b>{len(res)}</b> {plural(len(res), 'uchwałę', 'uchwały', 'uchwał')}. Poniżej każda decyzja: co zmienia (prostym językiem), jak głosowali radni i gdzie jest źródło.</p>
<p class="small">Dane z BIP pobrane: {date_txt}. Źródła: <a href="{e(s['url'])}">porządek obrad</a>,
<a href="{e(d['meta']['zrodla']['uchwaly']['url'])}">lista uchwał (API BIP)</a>. <a href="o-danych.html">Jak to sprawdzamy</a>.</p>
</section>
<div class="filter" hidden>
<p id="f-label">Pokaż:</p>
<div role="group" aria-labelledby="f-label">
<button type="button" data-f="all" aria-pressed="true">Wszystkie ({len(res)})</button>
<button type="button" data-f="1" aria-pressed="false">Zgodne ({n_zg})</button>
<button type="button" data-f="0" aria-pressed="false">Sporne ({len(res) - n_zg})</button>
</div>
<p class="small">Zgodne: nikt nie głosował przeciw ani się nie wstrzymał. Sporne: co najmniej jeden głos przeciw lub wstrzymujący się. Ta sama reguła dla każdej uchwały i każdego klubu.</p>
</div>
<p class="small" id="f-count" aria-live="polite"></p>
{cards}
{missing_html}"""
    (out / "index.html").write_text(
        page(f"{s['numer']} sesja Rady Miasta Gdyni – Co robi władza?", body,
             description=f"Decyzje Rady Miasta Gdyni z {pl_date(s['data'])} prostym językiem, z głosowaniami imiennymi i źródłami."),
        "utf-8")

    for c in d["radni"]:
        (out / "radni" / f"{c['id']}.html").write_text(councillor_page(c, d), "utf-8")
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
<p>Opisy mają 1–2 zdania i powstają tylko z treści uchwały i jej uzasadnienia. {e(opisy['metoda'])}
Każde zdanie ma cytaty z PDF uchwały. Program sprawdza, czy każdy cytat naprawdę jest w tekście PDF, i odrzuca słowa oceniające.
Gdy BIP nie publikuje treści uchwały, piszemy „brak opisu”.</p>
<h2>Słowniczek</h2>
<ul>
<li><b>Za / Przeciw / Wstrzymali się</b> – tak radni zagłosowali.</li>
<li><b>Brak głosu</b> i <b>Nieobecni</b> – dwie osobne grupy w PDF z eSesji. PDF nie wyjaśnia różnicy między nimi.</li>
<li><b>Zgodne</b> – 0 głosów przeciw i 0 wstrzymujących się. <b>Sporne</b> – wszystkie pozostałe.</li>
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
