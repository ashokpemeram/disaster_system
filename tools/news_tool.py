import os
import requests
from dotenv import load_dotenv

load_dotenv()

def fetch_news(location: str):
    url = f"https://newsapi.org/v2/everything?q={location}+disaster&apiKey={os.getenv('NEWS_API_KEY')}"
    response = requests.get(url)
    return response.json()