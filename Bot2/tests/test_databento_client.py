import os
import sys
import types
import unittest
from unittest.mock import patch

from trading_bots.databento_client import create_databento_client


class TestDatabentoClientFactory(unittest.TestCase):
    def test_create_databento_client_uses_custom_factory(self) -> None:
        os.environ["DATABENTO_API_KEY"] = "db_custom_key"

        def factory(*, api_key: str):
            return {"api_key": api_key, "kind": "custom"}

        client = create_databento_client(client_factory=factory)

        self.assertEqual(client["kind"], "custom")
        self.assertEqual(client["api_key"], "db_custom_key")

    def test_create_databento_client_uses_databento_historical_by_default(self) -> None:
        os.environ["DATABENTO_API_KEY"] = "db_default_key"

        fake_databento = types.ModuleType("databento")

        class FakeHistorical:
            def __init__(self, key: str) -> None:
                self.key = key

        fake_databento.Historical = FakeHistorical

        with patch.dict(sys.modules, {"databento": fake_databento}):
            client = create_databento_client()

        self.assertIsInstance(client, FakeHistorical)
        self.assertEqual(client.key, "db_default_key")

    def test_create_databento_client_raises_when_sdk_missing(self) -> None:
        os.environ["DATABENTO_API_KEY"] = "db_missing_sdk_key"

        with patch.dict(sys.modules, {"databento": None}):
            with self.assertRaises(RuntimeError):
                create_databento_client()


if __name__ == "__main__":
    unittest.main()
