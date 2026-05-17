import os

from trading_bots.env import load_project_env


def get_databento_api_key() -> str:
    """Return Databento API key from environment.

    Raises:
        RuntimeError: If DATABENTO_API_KEY is missing.
    """
    load_project_env()
    key = os.getenv("DATABENTO_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "DATABENTO_API_KEY fehlt. Lege ihn lokal in .env ab oder setze ihn als Environment-Variable."
        )
    return key
