import requests
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

import crud
from database import get_session

print("1. Testing Neo4j connection...")
session = get_session()
result = session.run("RETURN 1")
print("2. Neo4j connection OK:", result.single())
session.close()

print("3. Starting sync...")
result = crud.get_all_event_sets_from_api()
print(f"Sync result: {result}")