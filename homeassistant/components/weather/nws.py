"""
Support for NWS weather service.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/weather.nws/
"""
import logging
from collections import OrderedDict
from datetime import timedelta

import async_timeout
import voluptuous as vol

from homeassistant.components.weather import (
    WeatherEntity, PLATFORM_SCHEMA, ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_PRECIPITATION, ATTR_FORECAST_TEMP, ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_SPEED, ATTR_FORECAST_WIND_BEARING)
from homeassistant.const import LENGTH_METERS, LENGTH_MILES
from homeassistant.const import (CONF_NAME, CONF_LATITUDE, CONF_LONGITUDE,
                                 LENGTH_METERS, LENGTH_MILES, TEMP_CELSIUS,
                                 TEMP_FAHRENHEIT)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.util import Throttle
from homeassistant.util.distance import convert as convert_distance
from homeassistant.util.temperature import convert as convert_temperature
REQUIREMENTS = ['pynws']

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = 'National Weather Service/NOAA'

ATTR_WEATHER_DESCRIPTION = 'https://www.weather.gov'

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=30)

CONF_STATION = 'station'
CONF_USERID = 'userid'

ATTR_FORECAST_PRECIP_PROB = 'precipitation_probability'

# Ordered so that a single condition can be chosen from multiple weather codes.
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

    ATTR_FORECAST_TIME: 'startTime',
    ATTR_FORECAST_WIND_SPEED: 'windSpeed'

}

_DIRECTIONS = ['N', 'NNE', 'NE', 'ENE',
               'E', 'ESE', 'SE', 'SSE',
               'S', 'SSW', 'SW', 'WSW',
               'W', 'WNW', 'NW', 'NNW']

WIND = {name: idx * 360 / 16 for idx, name in enumerate(_DIRECTIONS)}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_LATITUDE): cv.latitude,
    vol.Optional(CONF_LONGITUDE): cv.longitude,
    vol.Optional(CONF_STATION, default=''): cv.string,
    vol.Required(CONF_USERID): cv.string
})

def parse_icon(icon):
    """Parses icon html to weather codes"""
    icon_list = icon.split('/')
    time = icon_list[5]
    weather = [i.split('?')[0] for i in icon_list[6:]]
    code = [w.split(',')[0] for w in weather]
    chance = [int(w.split(',')[1]) if len(w.split(',')) == 2 else 0 for w in\
 weather]
    return time, tuple(zip(code, chance))

def convert_condition(code):
    """Converts NWS codes to HA condition"""

    time = code[0]
    weather = code[1]
    conditions = [w[0] for w in weather]
    # Precipitation probability not currently used.
    prec = [w[1] for w in weather]

    # Choose condition with highest priority.
    cond = next((key for key, value in CONDITION_CLASSES.items()
                 if any(condition in value for condition in conditions))
                , conditions[0])

    if cond == 'clear':
        if time == 'day':
            return 'sunny'
        if time == 'night':
            return 'clear-night'

    return cond, max(prec)

async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the nws platform."""
    latitude = config.get(CONF_LATITUDE, hass.config.latitude)
    longitude = config.get(CONF_LONGITUDE, hass.config.longitude)
    station = config.get(CONF_STATION).split(',')
    userid = config.get(CONF_USERID)
    
    if None in (latitude, longitude):
        _LOGGER.error("Latitude/longitude not set in Home Assistant config")
        return

    from pynws import Nws

    websession = async_get_clientsession(hass)
    nws = Nws(websession, latlon=(float(latitude), float(longitude)))

    if station == '':
        with async_timeout.timeout(10, loop=hass.loop):
            stations = await nws.station()
        nws.station = stations[0]
        _LOGGER.debug("Initialized for coordinates %s, %s -> station %s",
                      latitude, longitude, station[0])
    else:
        nws.station = station[0]
        _LOGGER.debug("Initialized station %s", station[0])

    async_add_entities([NWSWeather(nws, config)], True)


class NWSWeather(WeatherEntity):
    """Representation of a weather condition."""

    def __init__(self, nws, config):
        """Initialise the platform with a data instance and station name."""
        self._nws = nws
        self._station_name = config.get(CONF_NAME, self._nws.station)
        self._description = None
        self._observation = None
        self._forecast = None
        
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Update Condition."""
        with async_timeout.timeout(10, loop=self.hass.loop):
            _LOGGER.debug("Updating station observations %s",
                          self._nws.station)
            self._observation = await self._nws.observations()
            _LOGGER.debug("Updating forecast")
            self._forecast = await self._nws.forecast()

        _LOGGER.debug("Observations: %s", self._observation)
        _LOGGER.debug("Forecasts: %s", self._forecast)
        
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
        return self._observation[0]['temperature']['value']

    @property
    def pressure(self):
        """Return the current pressure."""
        pressure_pa = self._observation[0]['seaLevelPressure']['value']
        #convert Pa to in Hg
        if pressure_pa is not None:
            return round(pressure_pa / 3386.39, 2)
        return None

    @property
    def humidity(self):
        """Return the name of the sensor."""
        return self._observation[0]['relativeHumidity']['value']

    @property
    def wind_speed(self):
        """Return the current windspeed."""
        # covert to mi/hr from m/s
        wind_m_s = self._observation[0]['windSpeed']['value']
        if wind_m_s is not None:
            return round(wind_m_s * 2.237)
        return None

    @property
    def wind_bearing(self):
        """Return the current wind bearing (degrees)."""
        return self._observation[0]['windDirection']['value']

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
        code = parse_icon(self._observation[0]['icon'])
        cond, _ = convert_condition(code)
        return cond
    
    @property
    def visibility(self):
        #convert to mi from m
        vis = self._observation[0]['visibility']['value']
        if vis is not None:
            return convert_distance(vis, LENGTH_METERS, LENGTH_MILES)
        return None

    @property
    def forecast(self):
        forecast = []
        for forecast_entry in self._forecast:
            data = {attr: forecast_entry[name]
                    for attr, name in FORECAST_CLASSES.items()}

            tempF = forecast_entry['temperature']
            data[ATTR_FORECAST_TEMP] = convert_temperature(tempF,
                                                           TEMP_FAHRENHEIT,
                                                           TEMP_CELSIUS)

            code = parse_icon(forecast_entry['icon'])
            cond, precip = convert_condition(code)
            data[ATTR_FORECAST_CONDITION] = cond
            data[ATTR_FORECAST_PRECIP_PROB] = precip
            data[ATTR_FORECAST_WIND_BEARING] = \
                                    WIND[forecast_entry['windDirection']]

            data[ATTR_FORECAST_WIND_SPEED] = ' '.join(forecast_entry['windSpeed'].split(' ')[:-1])
            forecast.append(data)

        return forecast
