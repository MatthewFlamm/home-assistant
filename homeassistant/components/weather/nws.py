"""
Support for NWS weather service.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/weather.nws/
"""
from collections import OrderedDict
from datetime import timedelta
import logging

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

ATTRIBUTION = 'Data from National Weather Service/NOAA'

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=30)

CONF_STATION = 'station'
CONF_USERID = 'userid'

ATTR_FORECAST_DETAIL_DESCRIPTION = 'detailed_description'
ATTR_FORECAST_PRECIP_PROB = 'precipitation_probability'
ATTR_FORECAST_DAYTIME = 'daytime'
# Ordered so that a single condition can be chosen from multiple weather codes.
# Known NWS conditions that do not map: cold
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

WIND_DIRECTIONS = ['N', 'NNE', 'NE', 'ENE',
                   'E', 'ESE', 'SE', 'SSE',
                   'S', 'SSW', 'SW', 'WSW',
                   'W', 'WNW', 'NW', 'NNW']

WIND = {name: idx * 360 / 16 for idx, name in enumerate(WIND_DIRECTIONS)}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_LATITUDE): cv.latitude,
    vol.Optional(CONF_LONGITUDE): cv.longitude,
    vol.Optional(CONF_STATION, default=''): cv.string,
    vol.Required(CONF_USERID): cv.string
})

def parse_icon(icon):
    """
    Parses icon url to NWS weather codes

    Example:
    https://api.weather.gov/icons/land/day/skc/tsra,40/ovc?size=medium
    
    Example return:
    ('day', (('skc', 0), ('tsra', 40),))
    """

    icon_list = icon.split('/')
    time = icon_list[5]
    weather = [i.split('?')[0] for i in icon_list[6:]]
    code = [w.split(',')[0] for w in weather]
    chance = [int(w.split(',')[1]) if len(w.split(',')) == 2 else 0 for w in\
 weather]
    return time, tuple(zip(code, chance))

def convert_condition(time, weather):
    """
    Converts NWS codes to HA condition

    Chooses first condition in CONDITION_CLASSES that exists in weather code
    """

    conditions = [w[0] for w in weather]
    prec_prob = [w[1] for w in weather]

    # Choose condition with highest priority.
    cond = next((key for key, value in CONDITION_CLASSES.items()
                 if any(condition in value for condition in conditions))
                , conditions[0])
    
    if cond == 'clear':
        if time == 'day':
            return 'sunny', max(prec_prob)
        if time == 'night':
            return 'clear-night', max(prec_prob)
    return cond, max(prec_prob)

async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the nws platform."""
    latitude = config.get(CONF_LATITUDE, hass.config.latitude)
    longitude = config.get(CONF_LONGITUDE, hass.config.longitude)
    station = config.get(CONF_STATION)
    userid = config.get(CONF_USERID)
    
    if None in (latitude, longitude):
        _LOGGER.error("Latitude/longitude not set in Home Assistant config")
        return

    from pynws import Nws

    websession = async_get_clientsession(hass)
    nws = Nws(websession, latlon=(float(latitude), float(longitude)))

    _LOGGER.debug("Setting up station: %s", station)
    if station == '':
        with async_timeout.timeout(10, loop=hass.loop):
            stations = await nws.stations()
        nws.station = stations[0]
        _LOGGER.debug("Initialized for coordinates %s, %s -> station %s",
                      latitude, longitude, stations[0])
    else:
        nws.station = station
        _LOGGER.debug("Initialized station %s", station[0])

    async_add_entities([NWSWeather(nws, config)], True)


class NWSWeather(WeatherEntity):
    """Representation of a weather condition."""

    def __init__(self, nws, config):
        """Initialise the platform with a data instance and station name."""
        self._nws = nws
        self._station_name = config.get(CONF_NAME, self._nws.station)
        self._observation = None
        self._forecast = None
        self._description=None

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
        temp_f = self._observation[0]['temperature']['value']
        if temp_f is not None:
            return convert_temperature(temp_f, TEMP_CELSIUS, TEMP_FAHRENHEIT)
        return None
    
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
        return TEMP_FAHRENHEIT

    @property
    def condition(self):
        time, weather = parse_icon(self._observation[0]['icon'])
        cond, precip_prob = convert_condition(time, weather)
        return cond
    
    @property
    def visibility(self):
        #convert to mi from m
        vis = self._observation[0]['visibility']['value']
        if vis is not None:
            return round(convert_distance(vis, LENGTH_METERS, LENGTH_MILES), 1)
        return None

    @property
    def forecast(self):
        forecast = []
        for forecast_entry in self._forecast:
            data = {attr: forecast_entry[name]
                    for attr, name in FORECAST_CLASSES.items()}

            data[ATTR_FORECAST_TEMP] = forecast_entry['temperature']
            
            time, weather = parse_icon(forecast_entry['icon'])
            cond, precip = convert_condition(time, weather)
            data[ATTR_FORECAST_CONDITION] = cond
            if precip>0:
                data[ATTR_FORECAST_PRECIP_PROB] = precip
            data[ATTR_FORECAST_WIND_BEARING] = \
                    WIND[forecast_entry['windDirection']]

            data[ATTR_FORECAST_WIND_SPEED] = ' '.join(forecast_entry['windSpeed'].split(' ')[:-1])
            if not forecast_entry['isDaytime']:
                data[ATTR_FORECAST_DAYTIME] = 'Night'
            else:
                data[ATTR_FORECAST_DAYTIME] = 'Day'
            data[ATTR_FORECAST_DETAIL_DESCRIPTION] = forecast_entry['detailedForecast']
            forecast.append(data)
        return forecast

    
    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        data = dict()

        if self._description:
            data[ATTR_WEATHER_DESCRIPTION] = self._description

        return data
