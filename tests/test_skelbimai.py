import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rrr_agent.client import RrrApiError
from rrr_agent.preke import load_draft, save_draft
from rrr_agent.skelbimai import apply_public_photos, build_drafts, upload_draft


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
        self.assertEqual({draft["detale"]["mechanic"] for draft in drafts}, {6})
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
        part = drafts[0]["detale"]
        self.assertEqual(part["internal_notes"], "Lentyna A")
        self.assertNotIn("Matmenys", part["internal_notes"])
        self.assertEqual(part["weight"], 2.5)
        self.assertEqual(part["length"], 40)
        self.assertNotIn("width", part)
        self.assertEqual(part["height"], 15)
        self.assertEqual(part["_matmenys"]["svoris"], "2.5")

    def test_local_photo_becomes_public_url(self):
        draft = {"detale": {"photo": "/nuotraukos/a.jpg", "photos": ["/nuotraukos/a.jpg", "https://example.com/b.jpg"]}}
        apply_public_photos(draft, "https://nuotraukos.example")
        self.assertEqual(draft["detale"]["photo"], "https://nuotraukos.example/a.jpg")
        self.assertEqual(
            draft["detale"]["photos"],
            ["https://nuotraukos.example/a.jpg", "https://example.com/b.jpg"],
        )

    def test_existing_part_is_updated(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def post(self, path, fields=None):
                self.calls.append(path)
                if path == "/crm/importPart":
                    raise RrrApiError("PART exist", "R400", {"part_id": 683, "msg": "PART exist"})
                return {"status_code": "R200", "msg": "OK", "part_id": fields["part_id"]}

        with TemporaryDirectory() as folder:
            path = Path(folder) / "dalis.json"
            save_draft(
                path,
                {
                    "_pavadinimas": "Defender",
                    "detale": {
                        "car_id": 4,
                        "category_id": 164,
                        "quality": 0,
                        "status": 0,
                        "price": 50,
                        "photo": "https://example.com/a.jpg",
                        "photos": ["https://example.com/a.jpg"],
                    },
                },
            )
            client = FakeClient()
            result = upload_draft(path, client)
            self.assertEqual(result["part_id"], 683)
            self.assertTrue(result["atnaujinta"])
            self.assertEqual(client.calls, ["/crm/importPart", "/crm/updatePart"])
            self.assertEqual(load_draft(path)["detale"]["ovoko_id"], 683)

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
