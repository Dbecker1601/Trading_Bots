import datetime as dt
import unittest

from trading_bots.market_data import fetch_historical_bars


class _FakeTimeseries:
    def __init__(self) -> None:
        self.last_kwargs = None

    def get_range(self, **kwargs):
        self.last_kwargs = kwargs
        return {"ok": True, "kwargs": kwargs}


class _FakeClient:
    def __init__(self) -> None:
        self.timeseries = _FakeTimeseries()


class _FailingTimeseries:
    def get_range(self, **kwargs):
        raise ValueError("boom")


class _FailingClient:
    def __init__(self) -> None:
        self.timeseries = _FailingTimeseries()


class TestMarketData(unittest.TestCase):
    def test_fetch_historical_bars_calls_databento_with_expected_arguments(self) -> None:
        client = _FakeClient()
        start = dt.datetime(2026, 4, 1, 9, 30)
        end = dt.datetime(2026, 4, 1, 16, 0)

        result = fetch_historical_bars(
            client=client,
            symbols=["MNQ.c.0"],
            start=start,
            end=end,
        )

        self.assertEqual(result["ok"], True)
        self.assertIsNotNone(client.timeseries.last_kwargs)
        kwargs = client.timeseries.last_kwargs
        self.assertEqual(kwargs["dataset"], "GLBX.MDP3")
        self.assertEqual(kwargs["schema"], "ohlcv-1m")
        self.assertEqual(kwargs["symbols"], ["MNQ.c.0"])
        self.assertEqual(kwargs["stype_in"], "continuous")
        self.assertEqual(kwargs["start"], start.isoformat())
        self.assertEqual(kwargs["end"], end.isoformat())

    def test_fetch_historical_bars_raises_for_empty_symbols(self) -> None:
        with self.assertRaises(ValueError):
            fetch_historical_bars(
                client=_FakeClient(),
                symbols=[],
                start=dt.datetime(2026, 4, 1, 9, 30),
                end=dt.datetime(2026, 4, 1, 16, 0),
            )

    def test_fetch_historical_bars_wraps_sdk_errors(self) -> None:
        with self.assertRaises(RuntimeError):
            fetch_historical_bars(
                client=_FailingClient(),
                symbols=["MNQ.c.0"],
                start=dt.datetime(2026, 4, 1, 9, 30),
                end=dt.datetime(2026, 4, 1, 16, 0),
            )


if __name__ == "__main__":
    unittest.main()
