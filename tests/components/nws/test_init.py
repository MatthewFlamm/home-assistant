"""Tests for init module."""
from homeassistant.components import nws
from homeassistant.components.nws.const import DOMAIN

from tests.components.nws.const import MOCK_ENTRY


async def test_successful_config_entry(hass, mock_simple_nws):
    """Test that nws config entry is configured successfully."""
    entry = MOCK_ENTRY
    entry.add_to_hass(hass)
    assert await nws.async_setup(hass, {}) is True
    assert await nws.async_setup_entry(hass, entry) is True


async def test_unload(hass, mock_simple_nws):
    """Test a successful unload of entry."""
    entry = MOCK_ENTRY
    entry.add_to_hass(hass)
    assert await nws.async_setup(hass, {}) is True
    assert await nws.async_setup_entry(hass, entry) is True
    await hass.async_block_till_done()

    assert len(hass.data[DOMAIN]) == 1
    entry_id = list(hass.data[DOMAIN].keys())[0]
    assert entry_id is not None

    # Unload config entry.
    assert await hass.config_entries.async_unload(entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN].get(entry_id) is None
