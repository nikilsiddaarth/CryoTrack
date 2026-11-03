import os
import unittest

from app import get_db_connection


class OracleConnectionTests(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("ORACLE_PASSWORD") and os.getenv("ORACLE_PASSWORD") != "YOUR_ORACLE_PASSWORD",
        "Set valid Oracle credentials in the project .env before running this integration test.",
    )
    def test_oracle_connection_and_dual_query(self):
        connection = get_db_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.close()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
