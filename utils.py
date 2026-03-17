from bson import ObjectId
from datetime import datetime
from math import atan2, cos, radians, sin, sqrt
import random

def serialize_mongo(data):
    if isinstance(data, list):
        return [serialize_mongo(item) for item in data]

    if isinstance(data, dict):
        new_data = {}
        for key, value in data.items():
            if isinstance(value, ObjectId):
                new_data[key] = str(value)
            elif isinstance(value, (dict, list)):
                new_data[key] = serialize_mongo(value)
            else:
                new_data[key] = value
        return new_data

    return data


_BASE36_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def base36_encode(value: int) -> str:
    if value == 0:
        return "0"
    digits = []
    while value > 0:
        value, rem = divmod(value, 36)
        digits.append(_BASE36_ALPHABET[rem])
    return "".join(reversed(digits))


def generate_area_id(existing_ids=None, now=None) -> str:
    if existing_ids is None:
        existing_ids = set()
    timestamp = now or datetime.utcnow()
    date_part = f"{timestamp.year}{timestamp.month:02d}{timestamp.day:02d}"

    while True:
        value = random.randrange(36**4)
        suffix = base36_encode(value).rjust(4, "0")
        area_id = f"AREA-{date_part}-{suffix}"
        if area_id not in existing_ids:
            existing_ids.add(area_id)
            return area_id


def haversine_distance_m(lat1, lon1, lat2, lon2) -> float:
    radius_m = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return radius_m * c
