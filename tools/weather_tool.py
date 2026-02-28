import os
import requests
from dotenv import load_dotenv

load_dotenv()

def fetch_weather(location: str):
    url = f"http://api.weatherapi.com/v1/current.json?key={os.getenv('WEATHER_API_KEY')}&q={location}"
    response = requests.get(url)
    return response.json()