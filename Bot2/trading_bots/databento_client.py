from typing import Any, Callable

from trading_bots.config import get_databento_api_key


def create_databento_client(
    client_factory: Callable[..., Any] | None = None,
) -> Any:
    """Create a Databento client without exposing the API key in code/logs.

    Args:
        client_factory: Optional dependency-injected factory callable.
            It will be called as client_factory(api_key=<key>). Useful for tests.

    Returns:
        An initialized Databento client instance.

    Raises:
        RuntimeError: If the Databento SDK is missing or key is unavailable.
    """
    api_key = get_databento_api_key()

    if client_factory is not None:
        return client_factory(api_key=api_key)

    try:
        import databento as db  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Databento SDK fehlt. Installiere es mit: pip install databento"
        ) from exc

    return db.Historical(api_key)
