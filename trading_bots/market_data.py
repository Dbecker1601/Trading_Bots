import datetime as dt
from typing import Any, Iterable


def _to_iso(value: dt.datetime) -> str:
    if not isinstance(value, dt.datetime):
        raise ValueError("start/end müssen datetime-Werte sein")
    return value.isoformat()


def fetch_historical_bars(
    client: Any,
    symbols: Iterable[str],
    start: dt.datetime,
    end: dt.datetime,
    dataset: str = "GLBX.MDP3",
    schema: str = "ohlcv-1m",
    stype_in: str = "continuous",
) -> Any:
    """Fetch historical bars from Databento with basic validation and error handling."""
    symbols_list = [s for s in symbols if str(s).strip()]
    if not symbols_list:
        raise ValueError("symbols darf nicht leer sein")

    start_iso = _to_iso(start)
    end_iso = _to_iso(end)
    if start >= end:
        raise ValueError("start muss vor end liegen")

    try:
        return client.timeseries.get_range(
            dataset=dataset,
            schema=schema,
            symbols=symbols_list,
            stype_in=stype_in,
            start=start_iso,
            end=end_iso,
        )
    except Exception as exc:
        raise RuntimeError(f"Databento-Abruf fehlgeschlagen: {exc}") from exc
