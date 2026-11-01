import unittest

from rrr_agent.skelbimai import build_drafts


PART = {
    "category_id": 42,
    "quality": 0,
    "status": 0,
    "price": 45,
    "notes": "Priekinis bamperis",
    "manufacturer_code": "8R0807217",
    "photo": "https://example.com/bamperis.jpg",
    "photos": ["https://example.com/bamperis.jpg"],
}


class ListingsTest(unittest.TestCase):
    def test_same_part_is_copied_for_each_car(self):
        drafts = build_drafts(
            {
                "detale": PART,
                "automobiliai": [
                    {"pavadinimas": "VW Golf 2014", "car_id": 10},
                    {"pavadinimas": "Audi A4 2016", "car_id": 11},
                    {"pavadinimas": "Škoda Octavia 2015", "car_id": 12},
                ],
            }
        )
        self.assertEqual(len(drafts), 3)
        notes = {draft["detale"]["notes"] for draft in drafts}
        prices = {draft["detale"]["price"] for draft in drafts}
        codes = {draft["detale"]["manufacturer_code"] for draft in drafts}
        car_ids = [draft["detale"]["car_id"] for draft in drafts]
        external_ids = [draft["detale"]["external_id"] for draft in drafts]
        self.assertEqual(notes, {"Priekinis bamperis"})
        self.assertEqual(prices, {45})
        self.assertEqual(codes, {"8R0807217"})
        self.assertEqual(car_ids, [10, 11, 12])
        self.assertEqual(len(set(external_ids)), 3)

    def test_duplicate_car_is_rejected(self):
        with self.assertRaises(ValueError):
            build_drafts(
                {
                    "detale": PART,
                    "automobiliai": [
                        {"pavadinimas": "Golf", "car_id": 10},
                        {"pavadinimas": "Tas pats Golf", "car_id": 10},
                    ],
                }
            )

    def test_dimensions_are_kept_with_the_part(self):
        drafts = build_drafts(
            {
                "detale": {**PART, "internal_notes": "Lentyna A"},
                "matmenys": {"svoris": "2,5", "ilgis": "40", "plotis": "", "aukstis": "15"},
                "automobiliai": [{"pavadinimas": "Defender", "car_id": 7}],
            }
        )
        notes = drafts[0]["detale"]["internal_notes"]
        self.assertIn("Lentyna A", notes)
        self.assertIn("svoris 2.5 kg", notes)
        self.assertIn("ilgis 40 cm", notes)
        self.assertIn("aukštis 15 cm", notes)
        self.assertNotIn("plotis", notes)
        self.assertEqual(drafts[0]["detale"]["_matmenys"]["svoris"], "2.5")

    def test_new_car_needs_model_year_and_status(self):
        with self.assertRaises(ValueError):
            build_drafts(
                {
                    "detale": PART,
                    "automobiliai": [{"pavadinimas": "Golf", "car_model": 5}],
                }
            )


if __name__ == "__main__":
    unittest.main()
