"""
BIRDSΣY3 — Universal Database Module
Directly connects to MongoDB (birdsey3 / birdseye_db) on localhost:27017.
Maintains automatic graceful fallback if the MongoDB daemon is ever unavailable.
"""

import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Read MongoDB configuration from environment variables or defaults
MONGO_URI = os.getenv("MONGODB_URL") or os.getenv("MONGO_URI") or "mongodb://localhost:27017"
DB_NAME = os.getenv("DATABASE_NAME") or os.getenv("MONGO_DB_NAME") or "birdsey3"

client = None
database = None
tiles_collection = None
searches_collection = None
provenance_collection = None

# 1. Attempt Primary MongoDB Connection
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    # Ping the server to verify active connection
    client.admin.command("ping")
    database = client[DB_NAME]
    
    # Check if this database has tiles, or fallback to birdseye_db if needed
    if database["tiles"].count_documents({}) == 0:
        if "birdseye_db" in client.list_database_names() and client["birdseye_db"]["tiles"].count_documents({}) > 0:
            DB_NAME = "birdseye_db"
            database = client[DB_NAME]

    tiles_collection = database["tiles"]
    searches_collection = database["searches"]
    provenance_collection = database["provenance"]

    count = tiles_collection.count_documents({})
    print(f"[MongoDB CONNECTED] Database: '{DB_NAME}' | URI: {MONGO_URI} | Active Tiles: {count}")

except Exception as err:
    print(f"[MongoDB WARNING] Could not connect to {MONGO_URI}: {err}")
    print("   Switching to file-backed local catalog fallback...")
    
    # Local fallback implementation if MongoDB daemon is offline
    import json

    class LocalCursor:
        def __init__(self, items):
            self.items = items
        def __iter__(self):
            return iter(self.items)
        def __len__(self):
            return len(self.items)
        def limit(self, n):
            return LocalCursor(self.items[:n])
        def sort(self, *args, **kwargs):
            return self

    class LocalCollection:
        def __init__(self, name, filepath=None):
            self.name = name
            self.filepath = filepath
            self.docs = []
            if self.filepath and os.path.exists(self.filepath):
                try:
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        self.docs = json.load(f)
                except Exception:
                    self.docs = []

        def find(self, query=None, projection=None):
            query = query or {}
            results = []
            for d in self.docs:
                match = all(d.get(k) == v for k, v in query.items())
                if match:
                    if projection:
                        include = [k for k, v in projection.items() if v == 1 and k != '_id']
                        if include:
                            proj = {k: d[k] for k in include if k in d}
                        else:
                            proj = {k: v for k, v in d.items() if projection.get(k, 1) != 0}
                        results.append(proj if proj else d.copy())
                    else:
                        results.append(d.copy())
            return LocalCursor(results)

        def find_one(self, query=None, projection=None):
            items = list(self.find(query, projection))
            return items[0] if items else None

        def count_documents(self, query=None):
            return len(list(self.find(query)))

        def insert_one(self, doc):
            self.docs.append(doc)
            return type('InsertResult', (), {'inserted_id': doc.get('_id')})()

        def update_one(self, query, update, upsert=False):
            vals = update.get('$set', update)
            for d in self.docs:
                if all(d.get(k) == v for k, v in query.items()):
                    d.update(vals)
                    return
            if upsert:
                new_d = query.copy()
                new_d.update(vals)
                self.docs.append(new_d)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    cat_path = os.path.join(base_dir, "data", "tiles_catalog.json")
    if not os.path.exists(cat_path):
        cat_path = os.path.join(os.path.dirname(base_dir), "data", "tiles_catalog.json")

    searches_collection = LocalCollection("searches")
    tiles_collection = LocalCollection("tiles", cat_path)
    provenance_collection = LocalCollection("provenance")