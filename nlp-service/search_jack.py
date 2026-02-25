from pymongo import MongoClient
import json
from bson import json_util

client = MongoClient("mongodb://localhost:27017/")
db = client["sample_shop"]

# Search for any name containing "Jack"
print("\n--- Searching for any name containing 'Jack' ---")
results = list(db["customers"].find({
    "$or": [
        {"first_name": {"$regex": "Jack", "$options": "i"}},
        {"last_name": {"$regex": "Jack", "$options": "i"}}
    ]
}))
print(json.dumps(results, indent=2, default=json_util.default))

# Search for any user with name "Jack" in 'users' collection too, just in case
print("\n--- Searching 'users' collection for 'Jack' ---")
user_results = list(db["users"].find({
    "name": {"$regex": "Jack", "$options": "i"}
}))
print(json.dumps(user_results, indent=2, default=json_util.default))
if not user_results:
     user_results = list(db["users"].find({
        "username": {"$regex": "Jack", "$options": "i"}
    }))
     print(json.dumps(user_results, indent=2, default=json_util.default))
