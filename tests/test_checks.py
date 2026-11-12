"""Testy twardych sprawdzeń z kroku 3 (uruchom: python3 -m unittest -v).

Każdy test psuje poprawny zestaw danych w jeden sposób i oczekuje błędu
(CheckError), nie ostrzeżenia.
"""

import copy
import json
import unittest
from pathlib import Path

from corobiwladza import checks, votes
from corobiwladza.checks import CheckError, run_all
from corobiwladza.names import Resolver

FX = Path(__file__).parent / "fixtures"
ALIASES = {"Marcus da Silva": "da Silva de Oliveira Marcus"}
SIZE = 28


def load_base():
    fx = json.loads((FX / "radni_kluby_gdynia.json").read_text("utf-8"))
    radni, kluby = fx["radni"], fx["kluby"]

    def vote_from(fixture, numer):
        p = votes.parse((FX / fixture).read_text("utf-8"))
        return {
            "numer": numer, "data": "2026-10-28",
            "pdf_glosowania": [f"https://example.invalid/{numer}.pdf"],
            "bip_wprowadzono": "30.10.2026",
            "glosowanie": {
                "sha256": numer, "esesja_id": numer, "temat": p.subject,
                "data_czas": p.voted_at, "pdf_wygenerowano": p.generated_on,
                "sumy": p.summary, "sumy_sekcji": p.section_counts, "imiennie_pdf": p.names,
            },
        }

    data = {
        "sesja": {"numer": "XXXVI", "data": "2026-10-28"},
        "radni": radni,
        "kluby": kluby,
        # Trzy prawdziwe PDF głosowań pod kolejnymi numerami (900, 901, 902),
        # żeby numeracja w zestawie testowym była ciągła.
        "uchwaly": [
            vote_from("glosowanie_900_budzet.txt", "XXXVI/900/26"),
            vote_from("glosowanie_902_podatek.txt", "XXXVI/901/26"),
            vote_from("glosowanie_909_sumy_w_wierszu_tematu.txt", "XXXVI/902/26"),
        ],
    }
    return data, Resolver(radni, ALIASES)


class ChecksTest(unittest.TestCase):
    def setUp(self):
        self.data, self.resolver = load_base()

    def run_checks(self, data=None):
        return run_all(data or self.data, self.resolver, SIZE)

    def assertFails(self, data, fragment):
        with self.assertRaises(CheckError) as ctx:
            self.run_checks(data)
        joined = "\n".join(ctx.exception.errors)
        self.assertIn(fragment, joined, msg=joined)

    def mutated(self):
        return copy.deepcopy(self.data)

    # --- poprawne dane przechodzą ---

    def test_valid_data_passes(self):
        summary = self.run_checks()
        self.assertEqual(summary["sprawdzono_glosowan"], 3)
        self.assertEqual(summary["sprawdzono_radnych"], 28)

    # --- sumy kontra listy nazwisk ---

    def test_header_sum_differs_from_section(self):
        d = self.mutated()
        d["uchwaly"][0]["glosowanie"]["sumy"]["za"] = 13
        self.assertFails(d, "suma za w nagłówku (13) ≠ liczba w sekcji (12)")

    def test_names_count_differs_from_sum(self):
        d = self.mutated()
        d["uchwaly"][0]["glosowanie"]["imiennie_pdf"]["za"].pop()
        self.assertFails(d, "suma za (12) ≠ liczba nazwisk (11)")

    def test_total_differs_from_council_size(self):
        d = self.mutated()
        v = d["uchwaly"][1]["glosowanie"]
        v["imiennie_pdf"]["nieobecni"] = []
        v["sumy"]["nieobecni"] = v["sumy_sekcji"]["nieobecni"] = 0
        self.assertFails(d, "suma wszystkich głosów i nieobecnych (27) ≠ liczba radnych (28)")

    # --- nazwiska na liście radnych ---

    def test_unknown_name_is_error(self):
        d = self.mutated()
        d["uchwaly"][0]["glosowanie"]["imiennie_pdf"]["za"][0] = "Jan Kowalski"
        self.assertFails(d, "nazwiska 'Jan Kowalski' nie ma na liście radnych")

    def test_one_letter_difference_is_error(self):
        d = self.mutated()
        d["uchwaly"][0]["glosowanie"]["imiennie_pdf"]["za"][0] = "Dawid Biernacki"
        self.assertFails(d, "'Dawid Biernacki' nie ma na liście radnych")

    def test_name_order_and_hyphens_do_not_matter(self):
        r = self.resolver
        self.assertEqual(r.resolve("Natalia Kłopotek Główczewska"), r.resolve("Kłopotek - Główczewska Natalia"))
        self.assertEqual(r.resolve("Mariola Śrubarczyk - Cichowska"), r.resolve("Śrubarczyk-Cichowska Mariola"))

    def test_alias_required_for_shortened_name(self):
        no_alias = Resolver(self.data["radni"], {})
        with self.assertRaises(KeyError):
            no_alias.resolve("Marcus da Silva")
        self.assertEqual(self.resolver.resolve("Marcus da Silva"), "da-silva-de-oliveira-marcus")

    def test_alias_to_unknown_person_is_rejected(self):
        with self.assertRaises(ValueError):
            Resolver(self.data["radni"], {"Jan Kowalski": "Kowalski Jan"})

    def test_same_person_twice_in_vote(self):
        d = self.mutated()
        v = d["uchwaly"][0]["glosowanie"]
        moved = v["imiennie_pdf"]["nieobecni"][0]
        v["imiennie_pdf"]["za"][-1] = moved
        self.assertFails(d, "występuje dwa razy")
        self.assertFails(d, "nie występuje w wynikach imiennych")

    # --- daty i numery ---

    def test_vote_date_differs_from_session(self):
        d = self.mutated()
        d["uchwaly"][0]["glosowanie"]["data_czas"] = "2026-10-29T12:36:00"
        self.assertFails(d, "data głosowania 2026-10-29 ≠ data sesji 2026-10-28")

    def test_resolution_date_differs_from_session(self):
        d = self.mutated()
        d["uchwaly"][0]["data"] = "2026-10-27"
        self.assertFails(d, "data uchwały 2026-10-27 ≠ data sesji 2026-10-28")

    def test_resolution_number_from_other_session(self):
        d = self.mutated()
        d["uchwaly"][0]["numer"] = "XXXV/900/26"
        self.assertFails(d, "numer sesji w numerze uchwały (XXXV) ≠ numer sesji (XXXVI)")

    def test_resolution_number_wrong_year(self):
        d = self.mutated()
        d["uchwaly"][0]["numer"] = "XXXVI/900/25"
        self.assertFails(d, "rok w numerze uchwały (/25)")

    def test_pdf_generated_before_vote(self):
        d = self.mutated()
        d["uchwaly"][0]["glosowanie"]["pdf_wygenerowano"] = "2026-10-27"
        self.assertFails(d, "PDF głosowania wygenerowano (2026-10-27) przed głosowaniem")

    def test_bip_entry_before_session(self):
        d = self.mutated()
        d["uchwaly"][0]["bip_wprowadzono"] = "27.10.2026"
        self.assertFails(d, "wprowadzona do BIP (2026-10-27) przed datą sesji")

    def test_numbering_gap(self):
        d = self.mutated()
        d["uchwaly"][2]["numer"] = "XXXVI/905/26"
        self.assertFails(d, "Luka w numeracji uchwał sesji (brak w BIP nr: [902, 903, 904])")

    # --- logika podjętej uchwały ---

    def test_adopted_with_more_against_than_for(self):
        d = self.mutated()
        v = d["uchwaly"][0]["glosowanie"]
        # zamieniamy ZA i PRZECIW (12 za, 0 przeciw -> 0 za, 12 przeciw)
        v["imiennie_pdf"]["za"], v["imiennie_pdf"]["przeciw"] = [], v["imiennie_pdf"]["za"]
        v["sumy"].update(za=0, przeciw=12)
        v["sumy_sekcji"].update(za=0, przeciw=12)
        self.assertFails(d, "ZA (0) ≤ PRZECIW (12)")

    def test_no_quorum(self):
        d = self.mutated()
        v = d["uchwaly"][1]["glosowanie"]
        moved = v["imiennie_pdf"]["za"][:14]
        v["imiennie_pdf"]["za"] = v["imiennie_pdf"]["za"][14:]
        v["imiennie_pdf"]["nieobecni"] += moved
        v["sumy"].update(za=13, nieobecni=15)
        v["sumy_sekcji"].update(za=13, nieobecni=15)
        self.assertFails(d, "obecnych 13, mniej niż połowa ustawowego składu (28)")

    # --- załączniki ---

    def test_two_vote_pdfs_for_one_resolution(self):
        d = self.mutated()
        d["uchwaly"][0]["pdf_glosowania"].append("https://example.invalid/drugi.pdf")
        self.assertFails(d, "oczekiwano 1 PDF „głosowanie”, jest 2")

    def test_same_vote_pdf_for_two_resolutions(self):
        d = self.mutated()
        d["uchwaly"][1]["glosowanie"]["esesja_id"] = d["uchwaly"][0]["glosowanie"]["esesja_id"]
        self.assertFails(d, "identyfikator eSesji głosowania jak przy XXXVI/900/26")

    # --- radni i kluby ---

    def test_councillor_list_differs_from_statutory_size(self):
        d = self.mutated()
        d["radni"] = d["radni"][:-1]
        with self.assertRaises(CheckError) as ctx:
            run_all(d, Resolver(d["radni"], ALIASES), SIZE)
        self.assertIn("Lista radnych w BIP ma 27 osób, a ustawowy skład to 28", ctx.exception.errors[0])

    def test_councillor_in_two_clubs(self):
        d = self.mutated()
        d["kluby"][1]["czlonkowie"].append(dict(d["kluby"][0]["czlonkowie"][0]))
        self.assertFails(d, "jest w dwóch klubach")

    def test_councillor_without_club(self):
        d = self.mutated()
        d["kluby"][3]["czlonkowie"].pop()
        self.assertFails(d, "nie występuje na stronie klubów")

    def test_club_link_to_other_profile(self):
        d = self.mutated()
        d["kluby"][0]["czlonkowie"][0]["bip_post_id"] = d["kluby"][0]["czlonkowie"][1]["bip_post_id"]
        self.assertFails(d, "prowadzi do innego profilu")

    def test_all_errors_reported_at_once(self):
        d = self.mutated()
        d["uchwaly"][0]["data"] = "2026-10-27"
        d["uchwaly"][1]["glosowanie"]["imiennie_pdf"]["za"][0] = "Jan Kowalski"
        with self.assertRaises(CheckError) as ctx:
            self.run_checks(d)
        self.assertGreaterEqual(len(ctx.exception.errors), 2)


class RomanTest(unittest.TestCase):
    def test_roman(self):
        self.assertEqual(checks.roman_to_int("XXXVI"), 36)
        self.assertEqual(checks.roman_to_int("XXIX"), 29)


if __name__ == "__main__":
    unittest.main()
