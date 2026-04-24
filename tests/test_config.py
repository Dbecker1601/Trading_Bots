import os
import unittest

from trading_bots.config import get_databento_api_key


class TestConfig(unittest.TestCase):
    def test_get_databento_api_key_returns_value(self) -> None:
        os.environ["DATABENTO_API_KEY"] = "db_live_test_key"
        self.assertEqual(get_databento_api_key(), "db_live_test_key")

    def test_get_databento_api_key_raises_when_missing(self) -> None:
        os.environ.pop("DATABENTO_API_KEY", None)
        with self.assertRaises(RuntimeError):
            get_databento_api_key()


if __name__ == "__main__":
    unittest.main()
