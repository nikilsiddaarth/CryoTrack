import unittest
from datetime import date, datetime
from decimal import Decimal

from app import app, maybe_paginate, rows_to_dicts, serialize_value


class ApiAndResponseTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_core_api_routes_are_registered(self):
        paths = {rule.rule for rule in app.url_map.iter_rules()}
        expected_paths = {
            "/api/health",
            "/api/dashboard/stats",
            "/api/products",
            "/api/batches",
            "/api/shipments",
            "/api/monitoring/alerts",
            "/api/monitoring/readings",
            "/api/inventory",
            "/api/deliveries",
        }
        self.assertTrue(expected_paths.issubset(paths))

    def test_numeric_and_date_values_are_json_serializable(self):
        self.assertEqual(serialize_value(Decimal("12.50")), 12.5)
        self.assertEqual(serialize_value(Decimal("12")), 12)
        self.assertEqual(serialize_value(date(2026, 11, 3)), "2026-11-03")
        self.assertEqual(
            serialize_value(datetime(2026, 11, 3, 10, 30)),
            "2026-11-03T10:30:00",
        )
        self.assertIsNone(serialize_value(None))

    def test_rows_to_dicts_converts_column_names_to_lowercase(self):
        class FakeCursor:
            description = [("PRODUCT_ID",), ("PRODUCT_NAME",)]

            def fetchall(self):
                return [(7, "Vaccine")]

        self.assertEqual(
            rows_to_dicts(FakeCursor()),
            [{"product_id": 7, "product_name": "Vaccine"}],
        )

    def test_pagination_returns_requested_page(self):
        with app.test_request_context("/?paginate=1&page=2&page_size=5"):
            response = maybe_paginate([{"id": i} for i in range(1, 13)])
            payload = response.get_json()
            self.assertEqual(payload["total"], 12)
            self.assertEqual(payload["page"], 2)
            self.assertEqual(payload["page_size"], 5)
            self.assertEqual([row["id"] for row in payload["items"]], [6, 7, 8, 9, 10])

    def test_pagination_caps_page_size(self):
        with app.test_request_context("/?paginate=1&page_size=500"):
            response = maybe_paginate([{"id": 1}])
            payload = response.get_json()
            self.assertEqual(payload["page_size"], 200)


if __name__ == "__main__":
    unittest.main()
