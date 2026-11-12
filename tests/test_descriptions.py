"""Testy sprawdzania opisów (krok 4) i „A co dla mnie?” (krok 5)."""

import unittest
from decimal import Decimal

from corobiwladza.descriptions import (_count_sentences, check_descriptions, check_wallet,
                                       compute_wallet, fmt_pln)

TEXT = ("UCHWAŁA NR XXXVI/902/26 ... 2) od budynków lub ich części: a) mieszkalnych - 1,24 zł od 1 m2\n"
        "powierzchni użytkowej, ... na terenie Miasta Gdyni. Uchwała wchodzi w życie z dniem 1 stycznia 2027 r.")
TITLE = "Uchwała nr XXXVI/939/26 Rady Miasta Gdyni z dnia 28.10.2026 w sprawie skargi XX z 4 października 2026 r."
THEMES = [{"id": "pieniadze", "nazwa": "Podatki"}, {"id": "skargi", "nazwa": "Skargi"}]


def session(with_text=True):
    return {"uchwaly": [{"numer": "XXXVI/902/26", "tytul_bip": TITLE,
                         "tresc": [{"pdf_url": "x"}] if with_text else []}]}


def z(text, *quotes):
    return {"tekst": text, "cytaty": list(quotes)}


def entry(**over):
    base = {"temat": "pieniadze",
            "naglowek": z("Podatek od mieszkania: 1,24 zł za m².", "mieszkalnych - 1,24 zł od 1 m2"),
            "kogo_dotyczy": z("Właściciele mieszkań w Gdyni.", "na terenie Miasta Gdyni"),
            "zdania": [z("Od 1 stycznia 2027 r. za 1 m² mieszkania płaci się 1,24 zł rocznie.",
                         "mieszkalnych - 1,24 zł od 1 m2 powierzchni użytkowej", "z dniem 1 stycznia 2027 r.")]}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def opis(**over):
    return {"tematy": THEMES, "uchwaly": {"XXXVI/902/26": entry(**over)}}


class DescriptionsTest(unittest.TestCase):
    def errs(self, o, with_text=True):
        return check_descriptions(session(with_text), o, {"XXXVI/902/26": TEXT})

    def assertError(self, o, fragment, with_text=True):
        errs = self.errs(o, with_text)
        self.assertTrue(any(fragment in x for x in errs), msg=errs)

    def test_valid(self):
        self.assertEqual(self.errs(opis()), [])

    def test_quote_across_line_break_is_found(self):
        self.assertEqual(self.errs(opis(zdania=[z("Stawka to 1,24 zł za 1 m².", "1,24 zł od 1 m2 powierzchni użytkowej")])), [])

    def test_quote_not_in_pdf_is_error(self):
        self.assertError(opis(zdania=[z("Stawka to 1,29 zł za 1 m².", "mieszkalnych - 1,29 zł od 1 m2")]), "cytatu nie ma w PDF")

    def test_sentence_without_quote_is_error(self):
        self.assertError(opis(zdania=[z("Stawka to 1,24 zł za 1 m².")]), "brak cytatu")

    def test_evaluative_word_is_error(self):
        self.assertError(opis(zdania=[z("To ważna zmiana stawki do 1,24 zł.", "1,24 zł")]), "słowo oceniające")

    def test_three_sentences_is_error(self):
        one = z("Stawka to 1,24 zł.", "1,24 zł")
        self.assertError(opis(zdania=[one, one, one]), "dozwolone 1–2")

    def test_two_sentences_in_one_item_is_error(self):
        self.assertError(opis(zdania=[z("Rada ustaliła stawkę. Wynosi 1,24 zł.", "1,24 zł")]), "dokładnie jedno zdanie")

    def test_missing_entry_is_error(self):
        self.assertError({"tematy": THEMES, "uchwaly": {}}, "brak wpisu")

    def test_missing_description_for_text_is_error(self):
        self.assertError(opis(zdania=None), "nie ma opisu")

    def test_missing_headline_is_error(self):
        self.assertError(opis(naglowek=None), "brak nagłówka")

    def test_headline_too_long_is_error(self):
        self.assertError(opis(naglowek=z("Podatek " + "od mieszkania " * 10 + "1,24 zł.", "1,24 zł")), "za długie")

    def test_headline_quote_must_be_in_pdf(self):
        self.assertError(opis(naglowek=z("Podatek 1,29 zł.", "1,29 zł od 1 m2")), "nagłówek: cytatu nie ma w PDF")

    def test_missing_audience_is_error(self):
        self.assertError(opis(kogo_dotyczy=None), "brak pola „kogo dotyczy”")

    def test_context_quote_checked(self):
        self.assertError(opis(kontekst=z("Wcześniej było 1,20 zł.", "1,20 zł")), "kontekst: cytatu nie ma w PDF")

    def test_unknown_theme_is_error(self):
        self.assertError(opis(temat="sport"), "nieznany temat")

    def test_no_text_allows_only_headline_from_bip_title(self):
        ok = {"tematy": THEMES, "uchwaly": {"XXXVI/902/26": {
            "temat": "skargi",
            "naglowek": {**z("Skarga z 4 października 2026 r.", "skargi XX z 4 października 2026 r."), "zrodlo": "tytul_bip"}}}}
        self.assertEqual(self.errs(ok, with_text=False), [])

    def test_no_text_with_description_is_error(self):
        self.assertError(opis(), "brak treści uchwały w BIP", with_text=False)

    def test_no_text_headline_not_from_title_is_error(self):
        bad = {"tematy": THEMES, "uchwaly": {"XXXVI/902/26": {
            "temat": "skargi", "naglowek": {**z("Skarga na prezydenta.", "skargi na prezydenta"), "zrodlo": "tytul_bip"}}}}
        self.assertError(bad, "cytatu nie ma w tytule BIP", with_text=False)

    def test_theme_intro_quote_checked(self):
        o = opis()
        o["tematy"] = [{"id": "pieniadze", "nazwa": "Podatki", "wstep": z("Stawki rosną.", "stawki rosną co roku"),
                        "wstep_zrodlo": "XXXVI/902/26"}]
        self.assertError(o, "Temat pieniadze, wstęp: cytatu nie ma")

    def test_sentence_counter_abbreviations(self):
        self.assertEqual(_count_sentences("Przy ul. Okrężnej, m.in. w 2025 r."), 1)
        self.assertEqual(_count_sentences("Ul. Zielna: dopisano działki."), 1)
        self.assertEqual(_count_sentences("Pierwsze. Drugie."), 2)
        self.assertEqual(_count_sentences("Bez kropki"), 0)


class VoteSentenceTest(unittest.TestCase):
    def test_plain_vote_sentence(self):
        from corobiwladza.site import vote_sentence
        v = {"sumy": {"za": 12, "przeciw": 0, "wstrzymal_sie": 15, "brak_glosu": 0, "nieobecni": 1}}
        self.assertEqual(vote_sentence(v, 28),
                         "<b>Przyjęta.</b> Za: 12 z 28 radnych · Przeciw: nikt · Wstrzymali się: 15 · Nieobecni: 1")


WALLET = {
    "lata": ["2026", "2027"],
    "dokumenty": {"a": {}, "b": {}},
    "stawki": [{"id": "m", "nazwa": "mieszkanie", "jednostka": "zł/m²", "wartosci": {
        "2026": {"wartosc": "1,20", "dokument": "a", "cytat": "mieszkalnych - 1,20 zł"},
        "2027": {"wartosc": "1,24", "dokument": "b", "cytat": "mieszkalnych - 1,24 zł"}}}],
    "grupy": [{"kto": "Właściciel", "uwaga": "", "przyklad": {"tytul": "50 m²", "skladniki": [
        {"opis": "mieszkanie", "m2": 50, "stawka": "m"}]}}],
    "fakty": [],
}


class WalletTest(unittest.TestCase):
    TEXTS = {"a": "a) mieszkalnych - 1,20 zł od 1 m2", "b": "a) mieszkalnych - 1,24 zł od 1 m2"}

    def test_valid_and_computed(self):
        self.assertEqual(check_wallet(WALLET, self.TEXTS), [])
        c = compute_wallet(WALLET)[0]
        self.assertEqual(c["razem"]["2027"], Decimal("62.00"))
        self.assertEqual(c["razem"]["2026"], Decimal("60.00"))
        self.assertEqual(c["roznica"], Decimal("2.00"))

    def test_rate_not_in_quote_is_error(self):
        import copy
        w = copy.deepcopy(WALLET)
        w["stawki"][0]["wartosci"]["2027"]["wartosc"] = "1,29"
        self.assertTrue(any("nie występuje w cytacie" in x for x in check_wallet(w, self.TEXTS)))

    def test_quote_not_in_document_is_error(self):
        texts = dict(self.TEXTS, b="a) mieszkalnych - 1,29 zł od 1 m2")
        self.assertTrue(any("cytatu nie ma w b" in x for x in check_wallet(WALLET, texts)))

    def test_money_format(self):
        self.assertEqual(fmt_pln(Decimal("1459.6")), "1 459,60 zł")


if __name__ == "__main__":
    unittest.main()
