import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trading_bots.config import get_databento_api_key


class TestConfig(unittest.TestCase):
    def test_get_databento_api_key_returns_value(self) -> None:
        os.environ["DATABENTO_API_KEY"] = "db_live_test_key"
        self.assertEqual(get_databento_api_key(), "db_live_test_key")

    def test_get_databento_api_key_raises_when_missing(self) -> None:
        os.environ.pop("DATABENTO_API_KEY", None)
        with patch("trading_bots.config.load_project_env", return_value=[]), self.assertRaises(RuntimeError):
            get_databento_api_key()

    def test_get_databento_api_key_loads_project_env_without_exposing_value(self) -> None:
        os.environ.pop("DATABENTO_API_KEY", None)
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("DATABENTO_API_KEY=db_from_file\n", encoding="utf-8")

            with patch("trading_bots.env.find_project_env", return_value=env_path):
                self.assertEqual(get_databento_api_key(), "db_from_file")


if __name__ == "__main__":
    unittest.main()
