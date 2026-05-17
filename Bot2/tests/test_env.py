import tempfile
import unittest
from pathlib import Path

from trading_bots.env import load_env_file


class TestEnvLoader(unittest.TestCase):
    def test_load_env_file_does_not_override_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("DATABENTO_API_KEY=file_value\n", encoding="utf-8")
            environ = {"DATABENTO_API_KEY": "existing_value"}

            loaded = load_env_file(env_path, environ=environ)

            self.assertEqual(loaded, ["DATABENTO_API_KEY"])
            self.assertEqual(environ["DATABENTO_API_KEY"], "existing_value")

    def test_load_env_file_can_override_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("DATABENTO_API_KEY=file_value\n", encoding="utf-8")
            environ = {"DATABENTO_API_KEY": "existing_value"}

            load_env_file(env_path, environ=environ, override=True)

            self.assertEqual(environ["DATABENTO_API_KEY"], "file_value")


if __name__ == "__main__":
    unittest.main()
