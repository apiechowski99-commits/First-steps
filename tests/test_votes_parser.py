"""Testy parsera PDF głosowań eSesji i nazw z BIP."""

import unittest
from pathlib import Path

from corobiwladza import names, votes
from corobiwladza.bip_gdynia import parse_resolution_title, parse_session_title

FX = Path(__file__).parent / "fixtures"


class VoteParserTest(unittest.TestCase):
    def test_tax_vote(self):
        v = votes.parse((FX / "glosowanie_902_podatek.txt").read_text("utf-8"))
        self.assertEqual(v.summary, {"za": 27, "przeciw": 0, "wstrzymal_sie": 0, "brak_glosu": 0, "nieobecni": 1})
        self.assertEqual(v.names["nieobecni"], ["Anna Salomon"])
        self.assertEqual(len(v.names["za"]), 27)
        self.assertEqual(v.voted_at, "2026-10-28T13:26:04")
        self.assertEqual(v.generated_on, "2026-10-30")
        self.assertTrue(v.subject.endswith("podatku od nieruchomości na terenie Miasta Gdyni"))

    def test_summary_glued_to_subject_line(self):
        v = votes.parse((FX / "glosowanie_909_sumy_w_wierszu_tematu.txt").read_text("utf-8"))
        self.assertEqual(v.summary["brak_glosu"], 5)
        self.assertTrue(v.subject.endswith("Żłobek „Niezapominajka”"))

    def test_names_broken_across_lines_are_joined(self):
        v = votes.parse((FX / "glosowanie_900_budzet.txt").read_text("utf-8"))
        self.assertIn("Paweł Stolarczyk", v.names["za"])
        self.assertIn("Mariola Śrubarczyk - Cichowska", v.names["wstrzymal_sie"])

    def _broken(self, old, new):
        t = (FX / "glosowanie_902_podatek.txt").read_text("utf-8")
        self.assertIn(old, t)
        return t.replace(old, new, 1)

    def test_unexpected_line_is_error(self):
        with self.assertRaises(votes.VoteParseError):
            votes.parse(self._broken("Wyniki imienne:\nZA (27)", "Wyniki imienne:\nCoś dziwnego\nZA (27)"))

    def test_missing_section_is_error(self):
        with self.assertRaises(votes.VoteParseError):
            votes.parse(self._broken("BRAK GŁOSU (0)\n", ""))

    def test_missing_footer_is_error(self):
        with self.assertRaises(votes.VoteParseError):
            votes.parse(self._broken("Wygenerowano za pomocą app.esesja.pl", "Wygenerowano gdzie indziej"))

    def test_missing_vote_date_is_error(self):
        with self.assertRaises(votes.VoteParseError):
            votes.parse(self._broken("Głosowanie z dnia:", "Głosowanie dnia:"))

    def test_esesja_id(self):
        self.assertEqual(votes.esesja_vote_id("wyniki_glosowania_1968059"), "1968059")
        self.assertIsNone(votes.esesja_vote_id("cos_innego"))


class BipTitlesTest(unittest.TestCase):
    def test_session_titles(self):
        self.assertEqual(parse_session_title("XXXVI sesja Rady Miasta Gdyni z 28 października 2026 r."),
                         {"numer": "XXXVI", "rodzaj": "zwyczajna", "data": "2026-10-28"})
        self.assertEqual(parse_session_title("XXXIV nadzwyczajna sesja Rady Miasta Gdyni z 14 września 2026 r. ")["rodzaj"],
                         "nadzwyczajna")
        self.assertEqual(parse_session_title("XXVIII sesja Rady Miasta Gdyni z dnia 25 lutego 2026 r.")["data"],
                         "2026-02-25")

    def test_resolution_title(self):
        r = parse_resolution_title(
            "Uchwała nr <strong>XXXVI/902/26</strong> Rady Miasta Gdyni z dnia <strong>28.10.2026</strong> "
            "w sprawie <strong>określenia wysokości stawek podatku od nieruchomości na terenie Miasta Gdyni</strong>")
        self.assertEqual(r["numer"], "XXXVI/902/26")
        self.assertEqual(r["data"], "2026-10-28")
        self.assertEqual(r["tytul"], "Uchwała w sprawie określenia wysokości stawek podatku od nieruchomości na terenie Miasta Gdyni")


class NamesTest(unittest.TestCase):
    def test_display(self):
        self.assertEqual(names.display_from_bip("Kłopotek - Główczewska Natalia "), "Natalia Kłopotek-Główczewska")
        self.assertEqual(names.display_from_bip("da Silva de Oliveira Marcus"), "Marcus da Silva de Oliveira")

    def test_function(self):
        self.assertEqual(names.split_function("Śrubarczyk - Cichowska Mariola - Wiceprzewodnicząca Rady Miasta"),
                         ("Śrubarczyk - Cichowska Mariola", "Wiceprzewodnicząca Rady Miasta"))
        self.assertEqual(names.split_function("Anisowicz Norbert "), ("Anisowicz Norbert", None))

    def test_club_line(self):
        self.assertEqual(names.split_club_line("Biernacik Dawid - przewodniczący klubu"), ("Biernacik Dawid", True, None))
        self.assertEqual(names.split_club_line("Dudziński Marek (Prawo i Sprawiedliwość)"),
                         ("Dudziński Marek", False, "Prawo i Sprawiedliwość"))

    def test_slug(self):
        self.assertEqual(names.slug("Żynis Jakub"), "zynis-jakub")
        self.assertEqual(names.slug("Śrubarczyk - Cichowska Mariola"), "srubarczyk-cichowska-mariola")


if __name__ == "__main__":
    unittest.main()
