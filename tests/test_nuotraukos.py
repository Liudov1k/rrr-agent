import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rrr_agent.nuotraukos import image_extension, parse_multipart, resolve_photo, save_image
from rrr_agent.preke import check_draft

JPEG = b"\xff\xd8\xff" + b"nuotrauka" + b"\xff\xd9"


class PhotoStorageTest(unittest.TestCase):
    def test_saves_jpeg_and_reads_it_back(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            url = save_image(JPEG, root)
            path = resolve_photo(url, root)
            self.assertEqual(path.read_bytes(), JPEG)
            self.assertEqual(image_extension(JPEG), "jpg")

    def test_rejects_text_and_path_escape(self):
        with self.assertRaises(ValueError):
            save_image(b"tai ne nuotrauka")
        with TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                resolve_photo("/nuotraukos/../../.env", Path(folder))

    def test_phone_photo_path_is_allowed_in_draft(self):
        errors, warnings = check_draft(
            {
                "detale": {
                    "car_id": 10,
                    "category_id": 42,
                    "quality": 0,
                    "status": 0,
                    "price": 20,
                    "photo": "/nuotraukos/abc.jpg",
                }
            }
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_multipart_extracts_file(self):
        body = (
            b"--riba\r\n"
            b'Content-Disposition: form-data; name="nuotrauka"; filename="a.jpg"\r\n'
            b"Content-Type: image/jpeg\r\n\r\n"
            + JPEG
            + b"\r\n--riba--\r\n"
        )
        files = parse_multipart("multipart/form-data; boundary=riba", body)
        self.assertEqual(files, [("a.jpg", JPEG)])


if __name__ == "__main__":
    unittest.main()
