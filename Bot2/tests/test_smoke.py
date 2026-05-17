import tempfile
import unittest
from pathlib import Path

from trading_bots.smoke import load_env_file


class TestSmokeHelpers(unittest.TestCase):
    def test_load_env_file_sets_variables_and_ignores_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "# comment\n"
                "DATABENTO_API_KEY=test_key_123\n"
                "EMPTY=\n"
                "INVALID_LINE\n"
            )
            target_env: dict[str, str] = {}

            loaded_keys = load_env_file(str(env_path), environ=target_env)

            self.assertIn("DATABENTO_API_KEY", loaded_keys)
            self.assertEqual(target_env.get("DATABENTO_API_KEY"), "test_key_123")
            self.assertEqual(target_env.get("EMPTY"), "")
            self.assertNotIn("INVALID_LINE", target_env)

    def test_load_env_file_returns_empty_list_when_missing(self) -> None:
        target_env: dict[str, str] = {}

        loaded_keys = load_env_file("/tmp/does_not_exist.env", environ=target_env)

        self.assertEqual(loaded_keys, [])
        self.assertEqual(target_env, {})


if __name__ == "__main__":
    unittest.main()
