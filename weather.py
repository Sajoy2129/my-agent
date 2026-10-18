"""Weather lookup using the free Open-Meteo API (no API key needed).

find_location() and get_weather() are copied from the weather_checker project.
"""

import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 10
FORECAST_DAYS = 3  # days to show after today

# Temperature units: Open-Meteo's name and the display symbol.
UNITS = {
    "C": {"api_name": "celsius", "symbol": "°C"},
    "F": {"api_name": "fahrenheit", "symbol": "°F"},
}
DEFAULT_UNIT = "C"


def find_location(city):
    """Look up a city's coordinates. Return None if the city is not found."""
    params = {"name": city, "count": 1, "language": "en", "format": "json"}
    response = requests.get(GEOCODING_URL, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()

    # Open-Meteo leaves out the "results" key entirely when nothing matches.
    results = response.json().get("results")
    if not results:
        return None

    place = results[0]
    return {
        "name": place["name"],
        "country": place.get("country", ""),
        "latitude": place["latitude"],
        "longitude": place["longitude"],
    }


def get_weather(latitude, longitude, unit=DEFAULT_UNIT):
    """Fetch current conditions, today's high/low and the next days' forecast."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": UNITS[unit]["api_name"],  # the API converts for us
        "timezone": "auto",  # "today" in the city's own timezone
        "forecast_days": 1 + FORECAST_DAYS,  # today plus the days ahead
    }
    response = requests.get(FORECAST_URL, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    daily = data["daily"]

    # Daily values are lists with one entry per day: index 0 is today.
    forecast = [
        {
            "date": daily["time"][day],
            "high": daily["temperature_2m_max"][day],
            "low": daily["temperature_2m_min"][day],
        }
        for day in range(1, 1 + FORECAST_DAYS)
    ]

    return {
        "temperature": data["current"]["temperature_2m"],
        "wind_speed": data["current"]["wind_speed_10m"],
        "high": daily["temperature_2m_max"][0],
        "low": daily["temperature_2m_min"][0],
        "forecast": forecast,
    }


def get_weather_for_city(city, unit=DEFAULT_UNIT):
    """Return weather for a city name as one dictionary.

    Raises ValueError if the city or unit is invalid, and
    requests.RequestException if Open-Meteo can't be reached.
    """
    if unit not in UNITS:
        raise ValueError(f"Unit must be 'C' or 'F', got {unit!r}.")
    location = find_location(city)
    if location is None:
        raise ValueError(f"City not found: {city}")

    weather = get_weather(location["latitude"], location["longitude"], unit)
    return {
        "location": f"{location['name']}, {location['country']}".rstrip(", "),
        "unit": UNITS[unit]["symbol"],
        "wind_speed_unit": "km/h",
        **weather,
    }
