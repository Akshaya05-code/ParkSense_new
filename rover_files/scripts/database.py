from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime
import sys

class Database:
    def __init__(self, mongo_uri="mongodb+srv://akshayareddy:akshaya20@clusterprac.w63oe.mongodb.net/?retryWrites=true&w=majority&appName=Clusterprac", 
                 db_name="parksense", car_logs_collection="car_logs", visitors_collection="visitors", rover_logs_collection="rover_logs"):
        try:
            self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[db_name]
            self.car_logs = self.db[car_logs_collection]
            self.visitors = self.db[visitors_collection]
            self.rover_logs = self.db[rover_logs_collection]
            self.client.admin.command('ping')
            print("MongoDB Atlas connection successful!")
        except ConnectionFailure as e:
            print(f"MongoDB Atlas connection failed! Error: {e}")
            print("Please check the connection string, network, or MongoDB Atlas status.")
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error during MongoDB connection: {e}")
            sys.exit(1)

    def upsert_number_platesaaa(self, number_plate, slot):
        try:
            result = self.car_logs.update_one(
                {"number_plate": number_plate},
                {
                    "$set": {
                        "timestamp": datetime.utcnow(),
                        "number_plate": number_plate,
                        "slots": slot
                    }
                },
                upsert=True
            )
            if result.matched_count > 0:
                print(f"Updated plate: {number_plate} in slot {slot}")
            else:
                print(f"Inserted new number plate: {number_plate} with slot {slot}")
            return True
        except Exception as e:
            print(f"Failed to upsert number plate {number_plate}: {e}")
            return False

    def check_number_plate(self, number_plate):
        try:
            return self.car_logs.find_one({"number_plate": number_plate}) is not None
        except Exception as e:
            print(f"Failed to check number plate {number_plate}: {e}")
            return False

    def upsert_number_plate(self, number_plate, slot):
        try:
            visitor_entry = self.visitors.find_one({
                'car_number': number_plate,
                'exit_time': {'$exists': False}
            })
            status = 'authorized' if visitor_entry else 'unauthorized'
            
            existing_log = self.car_logs.find_one({
                'number_plate': number_plate,
                'slots': slot,
                'status': {'$in': ['authorized', 'unauthorized']}
            })

            if existing_log:
                print(f"Car {number_plate} already logged in slot {slot}. Skipping...")
                return
            
            log_entry = {
                'timestamp': datetime.utcnow(),
                'number_plate': number_plate,
                'slots': slot,
                'status': status
            }
            self.car_logs.insert_one(log_entry)
            print(f"Car {number_plate} logged as {status} in slot {slot}.")
        except Exception as e:
            print(f"Failed to log car entry for {number_plate}: {e}")

    def insert_telemetry(self, data):
        try:
            # Update the single telemetry document and increment trip_count
            result = self.rover_logs.update_one(
                {"_id": "telemetry"},
                {
                    "$set": {
                        "timestamp": datetime.utcnow(),
                        "gps": data["gps"],
                        "battery": data["battery"],
                        "heading": data["heading"],
                        "velocity": data["velocity"],
                        "mode": data["mode"],
                        "armed": data["armed"],
                        "system_status": data["system_status"]
                    },
                    "$inc": {"trip_count": 1}  # Increment trip_count
                },
                upsert=True
            )
            if result.matched_count > 0:
                print("Updated telemetry document")
            else:
                print("Created new telemetry document")
                # Ensure trip_count is initialized if document is created
                self.rover_logs.update_one(
                    {"_id": "telemetry"},
                    {"$setOnInsert": {"trip_count": 0}},
                    upsert=True
                )
            return True
        except Exception as e:
            print(f"Failed to update telemetry data: {e}")
            return False

    def close(self):
        try:
            self.client.close()
            print("MongoDB connection closed.")
        except Exception as e:
            print(f"Error closing MongoDB connection: {e}")
