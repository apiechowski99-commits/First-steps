"""Testy sprawdzania opisów (krok 4) i „A co dla mnie?” (krok 5)."""

import unittest
from decimal import Decimal

from corobiwladza.descriptions import (_count_sentences, check_descriptions, check_wallet,
                                       compute_wallet, fmt_pln)

TEXT = ("UCHWAŁA NR XXXVI/902/26 ... 2) od budynków lub ich części: a) mieszkalnych - 1,24 zł od 1 m2\n"
        "powierzchni użytkowej, ... Uchwała wchodzi w życie z dniem 1 stycznia 2027 r.")


def session(with_text=True):
    return {"uchwaly": [{"numer": "XXXVI/902/26", "tresc": [{"pdf_url": "x"}] if with_text else []}]}


def opis(text, quotes):
    return {"uchwaly": {"XXXVI/902/26": {"zdania": [{"tekst": text, "cytaty": quotes}]}}}


class DescriptionsTest(unittest.TestCase):
    def errs(self, o, with_text=True):
        return check_descriptions(session(with_text), o, {"XXXVI/902/26": TEXT})

    def test_valid(self):
        o = opis("Od 1 stycznia 2027 r. za 1 m² mieszkania płaci się 1,24 zł rocznie.",
                 ["mieszkalnych - 1,24 zł od 1 m2 powierzchni użytkowej", "z dniem 1 stycznia 2027 r."])
        self.assertEqual(self.errs(o), [])

    def test_quote_across_line_break_is_found(self):
        o = opis("Stawka to 1,24 zł za 1 m².", ["1,24 zł od 1 m2 powierzchni użytkowej"])
        self.assertEqual(self.errs(o), [])

    def test_quote_not_in_pdf_is_error(self):
        o = opis("Stawka to 1,29 zł za 1 m².", ["mieszkalnych - 1,29 zł od 1 m2"])
        self.assertTrue(any("cytatu nie ma w PDF" in x for x in self.errs(o)))

    def test_sentence_without_quote_is_error(self):
        o = opis("Stawka to 1,24 zł za 1 m².", [])
        self.assertTrue(any("brak cytatu" in x for x in self.errs(o)))

    def test_evaluative_word_is_error(self):
        o = opis("To ważna zmiana stawki do 1,24 zł.", ["1,24 zł"])
        self.assertTrue(any("słowo oceniające" in x for x in self.errs(o)))

    def test_three_sentences_is_error(self):
        z = {"tekst": "Zdanie.", "cytaty": ["1,24 zł"]}
        o = {"uchwaly": {"XXXVI/902/26": {"zdania": [z, z, z]}}}
        self.assertTrue(any("dozwolone 1–2" in x for x in self.errs(o)))

    def test_two_sentences_in_one_item_is_error(self):
        o = opis("Rada ustaliła stawkę. Wynosi 1,24 zł.", ["1,24 zł"])
        self.assertTrue(any("dokładnie jedno zdanie" in x for x in self.errs(o)))

    def test_missing_description_for_text_is_error(self):
        self.assertTrue(any("nie ma opisu" in x for x in self.errs({"uchwaly": {}})))

    def test_description_without_text_is_error(self):
        o = opis("Rada coś zdecydowała.", ["1,24 zł"])
        self.assertTrue(any("brak opisu" in x for x in self.errs(o, with_text=False)))

    def test_no_text_and_no_description_is_ok(self):
        self.assertEqual(self.errs({"uchwaly": {}}, with_text=False), [])

    def test_sentence_counter_abbreviations(self):
        self.assertEqual(_count_sentences("Przy ul. Okrężnej, m.in. w 2025 r."), 1)
        self.assertEqual(_count_sentences("Pierwsze. Drugie."), 2)
        self.assertEqual(_count_sentences("Bez kropki"), 0)


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
