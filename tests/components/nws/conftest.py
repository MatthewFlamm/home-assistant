"""Fixtures for National Weather Service tests."""
from unittest.mock import patch

import pytest

from tests.common import mock_coro
from tests.components.nws.const import DEFAULT_FORECAST, DEFAULT_OBSERVATION


@pytest.fixture()
async def mock_simple_nws():
    """Mock pynws SimpleNWS with default values."""
    with patch("homeassistant.components.nws.SimpleNWS") as mock_nws:
        instance = mock_nws()
        instance.set_station.return_value = mock_coro()
        instance.update_observation.return_value = mock_coro()
        instance.update_forecast.return_value = mock_coro()
        instance.update_forecast_hourly.return_value = mock_coro()
        instance.station.return_value = "ABC"
        instance.stations.return_value = ["ABC"]
        instance.observation.return_value = DEFAULT_OBSERVATION
        instance.forecast.return_value = DEFAULT_FORECAST
        instance.forecast_hourly.return_value = DEFAULT_FORECAST
        yield mock_nws
