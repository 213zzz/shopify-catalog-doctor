import csv
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from shopify_catalog_doctor import InputError, main, validate_product_csv


CURRENT_HEADERS = [
    "URL handle",
    "Title",
    "Status",
    "Option1 name",
    "Option1 value",
    "SKU",
    "Price",
    "Compare-at price",
    "Published on online store",
    "Product image URL",
    "Image alt text",
]


class CatalogDoctorTests(unittest.TestCase):
    def report(self, headers, rows, **options):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "products.csv"
            with path.open("w", encoding="utf-8", newline="") as target:
                writer = csv.writer(target, lineterminator="\n")
                writer.writerow(headers)
                writer.writerows(rows)
            return validate_product_csv(path, **options)

    def codes(self, report):
        return {finding["code"] for finding in report["findings"]}

    def test_current_format_passes(self):
        report = self.report(
            CURRENT_HEADERS,
            [
                ["silver-ring", "Silver Ring", "active", "Size", "6", "RING-6", "49.00", "69.00", "true", "https://example.com/ring.jpg", "Silver ring"],
                ["silver-ring", "", "", "", "7", "RING-7", "49.00", "69.00", "", "", ""],
            ],
        )
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})

    def test_common_catalog_problems_are_reported(self):
        report = self.report(
            CURRENT_HEADERS,
            [
                ["bad handle", "Ring", "active", "Size", "6", "RING", "49", "39", "yes", "http://example.com/ring.jpg", ""],
                ["bad handle", "", "", "", "7", "RING", "49", "", "", "", ""],
            ],
        )
        self.assertTrue(
            {"handle.invalid", "value.boolean", "price.compare_at", "image.http", "image.alt_missing", "sku.duplicate"}.issubset(self.codes(report))
        )

    def test_legacy_headers_are_supported(self):
        report = self.report(
            ["Handle", "Title", "Option1 Name", "Option1 Value", "Variant SKU", "Variant Price", "Published"],
            [["plain-chain", "Plain Chain", "Title", "Default Title", "CHAIN-1", "25.00", "TRUE"]],
        )
        self.assertEqual(report["summary"]["errors"], 0)

    def test_simple_create_does_not_require_option_columns(self):
        report = self.report(
            ["URL handle", "Title", "SKU", "Price"],
            [["ring", "Ring", "RING-1", "20"]],
        )
        self.assertNotIn("header.variant_options_missing", self.codes(report))
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})

    def test_multirow_create_requires_option_columns(self):
        report = self.report(
            ["URL handle", "Title", "SKU", "Price"],
            [["ring", "Ring", "RING-1", "20"], ["ring", "", "RING-2", "20"]],
        )
        self.assertIn("header.variant_options_missing", self.codes(report))

    def test_json_report_cannot_overwrite_input_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "products.csv"
            original = "Title\nRing\n"
            path.write_text(original, encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code = main([str(path), "--json", str(path)])
            self.assertEqual(exit_code, 2)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_unclosed_quote_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.csv"
            path.write_text('Title\n"Broken\n', encoding="utf-8")
            with self.assertRaises(InputError):
                validate_product_csv(path)

    def test_unicode_digits_do_not_crash_integer_checks(self):
        headers = CURRENT_HEADERS + ["Weight value (grams)", "Image position"]
        row = ["ring", "Ring", "active", "Title", "Default Title", "RING", "20", "", "true", "", ""] + ["²", "²"]
        report = self.report(headers, [row])
        self.assertTrue({"weight.invalid", "image.position"}.issubset(self.codes(report)))

    def test_require_sku_checks_option_only_variant_rows(self):
        report = self.report(
            CURRENT_HEADERS,
            [
                ["ring", "Ring", "active", "Size", "6", "RING-6", "20", "", "true", "", ""],
                ["ring", "", "", "", "7", "", "", "", "", "", ""],
            ],
            require_sku=True,
        )
        self.assertIn("sku.missing", self.codes(report))

    def test_every_variant_has_all_product_options(self):
        headers = CURRENT_HEADERS[:5] + ["Option2 name", "Option2 value"] + CURRENT_HEADERS[5:]
        report = self.report(
            headers,
            [
                ["ring", "Ring", "active", "Color", "Silver", "Size", "6", "RING-S-6", "20", "", "true", "", ""],
                ["ring", "", "", "", "Gold", "", "", "RING-G", "20", "", "", "", ""],
            ],
        )
        self.assertIn("variant.option_missing", self.codes(report))

    def test_option2_only_row_is_still_a_variant(self):
        headers = CURRENT_HEADERS[:5] + ["Option2 name", "Option2 value"] + CURRENT_HEADERS[5:]
        report = self.report(
            headers,
            [
                ["ring", "Ring", "active", "Color", "Silver", "Size", "6", "RING-S-6", "20", "", "true", "", ""],
                ["ring", "", "", "", "", "", "7", "", "", "", "", "", ""],
            ],
            require_sku=True,
        )
        self.assertTrue({"variant.option_missing", "sku.missing"}.issubset(self.codes(report)))


if __name__ == "__main__":
    unittest.main()
