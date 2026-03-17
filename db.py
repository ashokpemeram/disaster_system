import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["disaster_system"]

weather_collection = db["weather_reports"]
news_collection = db["news_reports"]
risk_collection = db["risk_assessments"]
alert_collection = db["alerts"]
aid_request_collection = db["aid_requests"]
area_collection = db["disaster_areas"]
sos_request_collection = db["sos_requests"]
