"""
Support for NWS weather service.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/weather.nws/
"""
import logging
from datetime import timedelta
from collections import OrderedDict
import async_timeout
import voluptuous as vol

from homeassistant.components.weather import (
    WeatherEntity, PLATFORM_SCHEMA, ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TIME, ATTR_FORECAST_WIND_SPEED,
    ATTR_FORECAST_WIND_BEARING)

from homeassistant.const import \
    CONF_NAME, TEMP_CELSIUS, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.util import Throttle

REQUIREMENTS = ['pynws']

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = 'National Weather Service/NOAA'

ATTR_WEATHER_DESCRIPTION = 'https://www.weather.gov'

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=30)

CONF_STATION = 'station'

# ordered so that a single condition can be chosen from multiple weather codes
CONDITION_CLASSES = OrderedDict([
    ('snowy', ['snow', 'snow_sleet', 'sleet', 'blizzard']),
    ('snowy-rainy', ['rain_snow', 'rain_sleet', 'fzra', 'rain_fzra', 'snow_fzra']),
    ('hail', []),
    ('lightning-rainy', ['tsra', 'tsra_sct', 'tsra_hi']),
    ('lightning', []),
    ('pouring', []),
    ('rainy', ['rain', 'rain_showers', 'rain_showers_hi']),
    ('windy-variant', ['wind_bkn', 'wind_ovc']),
    ('windy', ['wind_skc', 'wind_few', 'wind_sct']),
    ('fog', ['fog']),
    ('clear', ['skc']),  # sunny and clear-night
    ('cloudy', ['bkn', 'ovc']),
    ('partlycloudy', ['few', 'sct'])
])

FORECAST_CLASSES = {
    ATTR_FORECAST_TEMP: 'temperature',
    ATTR_FORECAST_TIME: 'startTime',
    ATTR_FORECAST_WIND_SPEED: 'windSpeed',
    ATTR_FORECAST_WIND_BEARING: 'windDirection'
}


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_LATITUDE): cv.latitude,
    vol.Optional(CONF_LONGITUDE): cv.longitude,
    vol.Optional(CONF_STATION, default=''): cv.string
})

def convert_condition(code):
    """Converts NWS codes to HA condition"""
    time = code[0]
    weather = code[1]
    conditions = [w[0] for w in weather]
    # Precipitation probability not currently used.
    #prec = [w[1] for w in weather]

    # Choose condition with highest priority.
    cond = next((k for k, v in CONDITION_CLASSES.items()
                 if any(c in v for c in conditions)), conditions[0])

    if cond == 'clear':
        if time == 'day':
            return 'sunny'
        if time == 'night':
            return 'clear-night'

    return cond

async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the nws platform."""
    latitude = config.get(CONF_LATITUDE, hass.config.latitude)
    longitude = config.get(CONF_LONGITUDE, hass.config.longitude)
    stations = config.get(CONF_STATION).split(',')
    if stations[0] == '':
        stations = []

    if None in (latitude, longitude):
        _LOGGER.error("Latitude or longitude not set in Home Assistant config")
        return

    from pynws import NWS

    websession = async_get_clientsession(hass)
    with async_timeout.timeout(10, loop=hass.loop):
        nws = NWS((float(latitude), float(longitude)),
                  websession, stations=stations)
        await nws.get_station()
    _LOGGER.info("Initializing for coordinates %s, %s -> station %s",
                 latitude, longitude,
                 nws.stations)

    async_add_entities([NWSWeather(nws, config)], True)


class NWSWeather(WeatherEntity):
    """Representation of a weather condition."""

    def __init__(self, nws, config):
        """Initialise the platform with a data instance and station name."""
        self._nws = nws
        self._station_name = config.get(CONF_NAME, self._nws.station)
        self._description = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Update Condition."""
        with async_timeout.timeout(10, loop=self.hass.loop):
            _LOGGER.info("Updating stations %s",
                         self._nws.stations)
            await self._nws.observation_update()
            _LOGGER.info("Updating forecast")
            await self._nws.forecast_update()

        _LOGGER.info("%s",
                     self._nws.weather_code_all)

    @property
    def attribution(self):
        """Return the attribution."""
        return ATTRIBUTION

    @property
    def name(self):
        """Return the name of the station."""
        return self._station_name

    @property
    def temperature(self):
        """Return the current temperature."""
        return self._nws.temperature

    @property
    def pressure(self):
        """Return the current pressure."""
        if self._nws.pressure is not None:
            return round(self._nws.pressure / 3386.39, 2)
        return None

    @property
    def humidity(self):
        """Return the name of the sensor."""
        return self._nws.relative_humidity

    @property
    def wind_speed(self):
        """Return the current windspeed."""
        # covert to mi/hr from m/s
        if self._nws.wind_speed is not None:
            return round(self._nws.wind_speed * 2.237)
        return None

    @property
    def wind_bearing(self):
        """Return the current wind bearing (degrees)."""
        return self._nws.wind_direction

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        data = dict()
        if self._description:
            data[ATTR_WEATHER_DESCRIPTION] = self._description
        return data

    @property
    def condition(self):
        return convert_condition(self._nws.weather_code)

    @property
    def visibility(self):
        #convert to mi from m
        if self._nws.visibility is not None:
            return round(self._nws.visibility / 1609.34)
        return None

    @property
    def forecast(self):
        forecast = []
        for forecast_entry in self._nws.forecast:
            data = {attr: forecast_entry[name]
                    for attr, name in FORECAST_CLASSES.items()}
            data[ATTR_FORECAST_CONDITION] = convert_condition(forecast_entry['weather_code'])

            forecast.append(data)

        _LOGGER.info('%s', forecast[0])
        return forecast
