import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rrr_agent.client import form_fields
from rrr_agent.preke import car_payload, check_draft, load_draft, part_payload, save_draft


class FormFieldsTest(unittest.TestCase):
    def test_photos_become_repeated_fields(self):
        fields = form_fields(
            {
                "price": 45,
                "notes": "",
                "photos": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
                "optional": None,
            }
        )
        self.assertEqual(
            fields,
            [
                ("price", "45"),
                ("photos[]", "https://example.com/a.jpg"),
                ("photos[]", "https://example.com/b.jpg"),
            ],
        )


class DraftTest(unittest.TestCase):
    def test_example_reports_missing_ids(self):
        draft = load_draft(Path("prekes/pavyzdys.json"))
        errors, warnings = check_draft(draft)
        self.assertTrue(any("car_model" in error for error in errors))
        self.assertTrue(any("category_id" in error for error in errors))
        self.assertEqual(warnings, [])

    def test_ready_part_uses_existing_car(self):
        draft = {
            "detale": {
                "car_id": 10,
                "category_id": 42,
                "quality": 0,
                "status": 0,
                "price": 45,
                "photo": "https://example.com/a.jpg",
            }
        }
        errors, warnings = check_draft(draft)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(part_payload(draft)["photo"], "https://example.com/a.jpg")
        self.assertEqual(part_payload(draft)["photos"], ["https://example.com/a.jpg"])
        self.assertIsNone(car_payload(draft))

    def test_local_file_photo_is_rejected(self):
        draft = {
            "detale": {
                "car_id": 10,
                "category_id": 42,
                "quality": 0,
                "status": 0,
                "price": 10,
                "photo": "C:/nuotraukos/a.jpg",
            }
        }
        errors, _warnings = check_draft(draft)
        self.assertTrue(any("http" in error for error in errors))

    def test_roundtrip_keeps_ovoko_id(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "preke.json"
            draft = {
                "detale": {"car_id": 1, "category_id": 2, "quality": 0, "status": 0, "ovoko_id": 99}
            }
            save_draft(path, draft)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["detale"]["ovoko_id"], 99)


if __name__ == "__main__":
    unittest.main()
