"""The tests for the IPMA weather component."""
import unittest
from unittest.mock import patch
from collections import namedtuple

from homeassistant.components import weather
from homeassistant.components.nws.weather import ATTR_FORECAST_PRECIP_PROB
from homeassistant.components.weather import (
    ATTR_WEATHER_HUMIDITY, ATTR_WEATHER_PRESSURE, ATTR_WEATHER_TEMPERATURE,
    ATTR_WEATHER_VISIBILITY, ATTR_WEATHER_WIND_BEARING,
    ATTR_WEATHER_WIND_SPEED)
from homeassistant.components.weather import (ATTR_FORECAST,
                                              ATTR_FORECAST_CONDITION,
                                              ATTR_FORECAST_TEMP,
                                              ATTR_FORECAST_TIME,
                                              ATTR_FORECAST_WIND_BEARING,
                                              ATTR_FORECAST_WIND_SPEED)
                                              
from homeassistant.const import (LENGTH_METERS, LENGTH_MILES, PRECISION_WHOLE,
                                 PRESSURE_INHG, PRESSURE_PA,
                                 TEMP_CELSIUS, TEMP_FAHRENHEIT)
from homeassistant.helpers.temperature import display_temp
from homeassistant.util.pressure import convert as convert_pressure
from homeassistant.util.distance import convert as convert_distance
from homeassistant.util.unit_system import IMPERIAL_SYSTEM
from homeassistant.util.temperature import convert as convert_temperature
from homeassistant.setup import setup_component

from tests.common import get_test_home_assistant, MockDependency


OBS = [{'temperature': {'value': 7, 'qualityControl': 'qc:V'},
        'relativeHumidity': {'value': 10, 'qualityControl': 'qc:V'},
        'windChill': {'value': 10, 'qualityControl':'qc:V'},
        'heatIndex': {'value': 10, 'qualityControl':'qc:V'},
        'windDirection': {'value': 180, 'qualityControl':'qc:V'},
        'visibility': {'value': 10000, 'qualityControl':'qc:V'},
        'windSpeed': {'value': 10, 'qualityControl':'qc:V'},
        'seaLevelPressure': {'value': 30000, 'qualityControl':'qc:V'},
        'windGust': {'value': 10, 'qualityControl':'qc:V'},
        'dewpoint': {'value': 10, 'qualityControl':'qc:V'},
        'icon': 'https://api.weather.gov/icons/land/night/ovc?size=medium',
        'textDescription': 'Cloudy'}]

FORE = [{'endTime': '2018-12-21T18:00:00-05:00',
         'windSpeed': '8 to 10 mph',
         'windDirection': 'S',
         'shortForecast': 'Chance Showers And Thunderstorms',
         'isDaytime': True,
         'startTime': '2018-12-21T15:00:00-05:00',
         'temperatureTrend': None,
         'temperature': 41,
         'temperatureUnit': 'F',
         'detailedForecast': '',
         'name': 'This Afternoon',
         'number': 1,
         'icon': 'https://api.weather.gov/icons/land/day/skc/tsra,40/ovc?size=medium'}]

STN = 'STNA'

class MockNws():
    """Mock Station from pynws."""
    def __init__(self, websession, latlon, userid):
        pass
    @classmethod
    '''async def get(cls, websession, latlon):
        """Mock Factory."""
        return MockNws()
    '''
    async def observations(self):
        """Mock Observation."""
        return OBS

    async def forecast(self):
        """Mock Forecast."""
        return FORE

    async def stations(self):
        """Mock stations."""
        return [STN]
    
    '''@property
    def local(self):
        """Mock location."""
        return "HomeWeather"
    '''

class TestNWS(unittest.TestCase):
    """Test the NWS weather component."""

    def setUp(self):
        """Set up things to be run when tests are started."""
        self.hass = get_test_home_assistant()
        self.hass.config.units = IMPERIAL_SYSTEM
        self.lat = self.hass.config.latitude = 40.00
        self.lon = self.hass.config.longitude = -8.00

    def tearDown(self):
        """Stop down everything that was started."""
        self.hass.stop()

    @MockDependency("pynws")
    @patch("pynws.Nws", new=MockNws)
    def test_setup_w_name(self, mock_pynws):
        """Test for successfully setting up the NWS platform with name."""
        assert setup_component(self.hass, weather.DOMAIN, {
            'weather': {
                'name': 'HomeWeather',
                'platform': 'nws',
                'userid': 'test@test.com',
                'api_key': 'test_email',
            }
        })

        state = self.hass.states.get('weather.homeweather')
        assert state.state == 'cloudy'

        data = state.attributes
        temp_f = convert_temperature(7, TEMP_CELSIUS, TEMP_FAHRENHEIT)
        assert data.get(ATTR_WEATHER_TEMPERATURE) == \
            display_temp(self.hass, temp_f, TEMP_FAHRENHEIT, PRECISION_WHOLE)
        assert data.get(ATTR_WEATHER_HUMIDITY) == 10
        assert data.get(ATTR_WEATHER_PRESSURE) == round(convert_pressure(30000, PRESSURE_PA, PRESSURE_INHG), 2)
        assert data.get(ATTR_WEATHER_WIND_SPEED) == round(10 * 2.237)
        assert data.get(ATTR_WEATHER_WIND_BEARING) == 180
        assert data.get(ATTR_WEATHER_VISIBILITY) == round(convert_distance(10000, LENGTH_METERS, LENGTH_MILES))
        assert state.attributes.get('friendly_name') == 'HomeWeather'
        
        forecast = data.get(ATTR_FORECAST)
        assert forecast[0].get(ATTR_FORECAST_CONDITION) == 'lightning-rainy'
        assert forecast[0].get(ATTR_FORECAST_PRECIP_PROB) == 40
        assert forecast[0].get(ATTR_FORECAST_TEMP) == 41
        assert forecast[0].get(ATTR_FORECAST_TIME) == '2018-12-21T15:00:00-05:00'
        assert forecast[0].get(ATTR_FORECAST_WIND_BEARING) == 180
        assert forecast[0].get(ATTR_FORECAST_WIND_SPEED) == 9

    @MockDependency("pynws")
    @patch("pynws.Nws", new=MockNws)
    def test_setup_w_station(self, mock_pynws):
        """Test for successfully setting up the NWS platform."""
        assert setup_component(self.hass, weather.DOMAIN, {
            'weather': {
                'platform': 'nws',
                'station': 'STNB',
                'userid': 'test@test.com',
                'api_key': 'test_email',
            }
        })

        state = self.hass.states.get('weather.stnb')
        assert state.state == 'cloudy'

        data = state.attributes
        temp_f = convert_temperature(7, TEMP_CELSIUS, TEMP_FAHRENHEIT)
        assert data.get(ATTR_WEATHER_TEMPERATURE) == \
            display_temp(self.hass, temp_f, TEMP_FAHRENHEIT, PRECISION_WHOLE)
        assert data.get(ATTR_WEATHER_HUMIDITY) == 10
        assert data.get(ATTR_WEATHER_PRESSURE) == round(convert_pressure(30000, PRESSURE_PA, PRESSURE_INHG), 2)
        assert data.get(ATTR_WEATHER_WIND_SPEED) == round(10 * 2.237)
        assert data.get(ATTR_WEATHER_WIND_BEARING) == 180
        assert data.get(ATTR_WEATHER_VISIBILITY) == round(convert_distance(10000, LENGTH_METERS, LENGTH_MILES))
        assert state.attributes.get('friendly_name') == 'STNB'
        
        forecast = data.get(ATTR_FORECAST)
        assert forecast[0].get(ATTR_FORECAST_CONDITION) == 'lightning-rainy'
        assert forecast[0].get(ATTR_FORECAST_PRECIP_PROB) == 40
        assert forecast[0].get(ATTR_FORECAST_TEMP) == 41
        assert forecast[0].get(ATTR_FORECAST_TIME) == '2018-12-21T15:00:00-05:00'
        assert forecast[0].get(ATTR_FORECAST_WIND_BEARING) == 180
        assert forecast[0].get(ATTR_FORECAST_WIND_SPEED) == 9

    @MockDependency("pynws")
    @patch("pynws.Nws", new=MockNws)
    def test_setup_get_stn(self, mock_pynws):
        """Test for successfully setting up the NS platform."""
        assert setup_component(self.hass, weather.DOMAIN, {
            'weather': {
                'platform': 'nws',
                'userid': 'test@test.com',
                'api_key': 'test_email',
            }
        })

        state = self.hass.states.get('weather.' + STN)
        assert state.state == 'cloudy'

        data = state.attributes
        temp_f = convert_temperature(7, TEMP_CELSIUS, TEMP_FAHRENHEIT)
        assert data.get(ATTR_WEATHER_TEMPERATURE) == \
            display_temp(self.hass, temp_f, TEMP_FAHRENHEIT, PRECISION_WHOLE)
        assert data.get(ATTR_WEATHER_HUMIDITY) == 10
        assert data.get(ATTR_WEATHER_PRESSURE) == round(convert_pressure(30000, PRESSURE_PA, PRESSURE_INHG), 2)
        assert data.get(ATTR_WEATHER_WIND_SPEED) == round(10 * 2.237)
        assert data.get(ATTR_WEATHER_WIND_BEARING) == 180
        assert data.get(ATTR_WEATHER_VISIBILITY) == round(convert_distance(10000, LENGTH_METERS, LENGTH_MILES))
        assert state.attributes.get('friendly_name') == STN
        
        forecast = data.get(ATTR_FORECAST)
        assert forecast[0].get(ATTR_FORECAST_CONDITION) == 'lightning-rainy'
        assert forecast[0].get(ATTR_FORECAST_PRECIP_PROB) == 40
        assert forecast[0].get(ATTR_FORECAST_TEMP) == 41
        assert forecast[0].get(ATTR_FORECAST_TIME) == '2018-12-21T15:00:00-05:00'
        assert forecast[0].get(ATTR_FORECAST_WIND_BEARING) == 180
        assert forecast[0].get(ATTR_FORECAST_WIND_SPEED) == 9
