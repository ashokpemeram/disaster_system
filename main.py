from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.coordinator import CoordinatorAgent
from utils import serialize_mongo

app = FastAPI()

# Allow Flutter app (emulator/device/desktop) to reach this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

coordinator = CoordinatorAgent()

class LocationRequest(BaseModel):
    location: str

@app.post("/assess")
def assess(request: LocationRequest):
    result = coordinator.handle_request(request.location)
    return serialize_mongo(result)


# @app.post("/assess")
# def assess(request: LocationRequest):
#     result = coordinator.handle_request(request.location)

#     clean_response = {
#         "location": result["risk"]["location"],
#         "overall_risk": result["risk"]["overall_risk"],
#         "temperature_c": result["risk"]["weather"]["raw_data"]["current"]["temp_c"],
#         "condition": result["risk"]["weather"]["raw_data"]["current"]["condition"]["text"],
#         "alert": result.get("alert_message", None)
#     }

#     return clean_response