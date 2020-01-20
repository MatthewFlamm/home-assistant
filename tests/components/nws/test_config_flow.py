"""Test the National Weather Service config flow."""
from unittest.mock import patch

import aiohttp
import pytest

from homeassistant import config_entries, setup
from homeassistant.components.nws import unique_id
from homeassistant.components.nws.const import DOMAIN

from tests.common import mock_coro


async def test_form(hass):
    """Test we get the form."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch(
        "homeassistant.components.nws.config_flow.validate_input",
        return_value=mock_coro(["ABC"]),
    ), patch(
        "homeassistant.components.nws.async_setup", return_value=mock_coro(True)
    ) as mock_setup, patch(
        "homeassistant.components.nws.async_setup_entry", return_value=mock_coro(True),
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"latitude": 50.0, "longitude": -75.0, "api_key": "test_key"},
        )

        assert result2["type"] == "form"

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"], {"station": "ABC"},
        )

        assert result3["type"] == "create_entry"
        assert result3["title"] == unique_id(50.0, -75.0)
        assert result3["data"] == {
            "latitude": 50.0,
            "longitude": -75.0,
            "api_key": "test_key",
            "station": "ABC",
        }

        await hass.async_block_till_done()
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


class UnspecifiedError(Exception):
    """Unspecified error for testing."""

    pass


@pytest.mark.parametrize(
    "error,result_error",
    [(aiohttp.ClientError, "cannot_connect"), (UnspecifiedError, "unknown")],
)
async def test_form_validate_errors(hass, error, result_error):
    """Test we handle errors in validation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.nws.config_flow.SimpleNWS.set_station",
        side_effect=error,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"latitude": 50, "longitude": -75, "api_key": "test_key"},
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": result_error}


async def test_duplicate_entry(hass):
    """Test we handle cannot have duplicate entries."""
    await setup.async_setup_component(hass, "persistent_notification", {})

    with patch("homeassistant.components.nws.config_flow.SimpleNWS") as mock_nws, patch(
        "homeassistant.components.nws.async_setup", return_value=mock_coro(True)
    ) as mock_setup, patch(
        "homeassistant.components.nws.async_setup_entry", return_value=mock_coro(True),
    ) as mock_setup_entry:
        instance = mock_nws.return_value
        instance.station = "ABC"
        instance.stations = ["ABC"]
        instance.set_station.return_value = mock_coro()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"latitude": 50, "longitude": -75, "api_key": "test_key"},
        )
        await hass.config_entries.flow.async_configure(
            result2["flow_id"], {"station": "ABC"},
        )
        assert mock_setup.call_count == 1
        assert mock_setup_entry.call_count == 1
        mock_setup.reset_mock()
        mock_setup_entry.reset_mock()

        result_entry2 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2_entry2 = await hass.config_entries.flow.async_configure(
            result_entry2["flow_id"],
            {"latitude": 50, "longitude": -75, "api_key": "test_key"},
        )

        await hass.async_block_till_done()
        assert mock_setup.call_count == 0
        assert mock_setup_entry.call_count == 0

    assert result2_entry2["type"] == "form"
    assert result2_entry2["errors"] == {"base": "already_configured"}
