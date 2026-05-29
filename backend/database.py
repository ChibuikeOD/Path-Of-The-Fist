import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

# Fallback to backend/.env if Neo4j variables are not defined in root .env
if not os.environ.get("NEO4J_PASSWORD"):
    backend_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(backend_env):
        load_dotenv(backend_env)

# Neo4j configuration
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")

if not NEO4J_PASSWORD:
    raise ValueError("NEO4J_PASSWORD environment variable must be set")

def _create_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# Initialize Neo4j driver
driver = _create_driver()

def get_session():
    """Get a new Neo4j session"""
    return driver.session()

def reset_driver():
    """Close and recreate the Neo4j driver."""
    global driver
    if driver:
        driver.close()
    driver = _create_driver()
    return driver

def close_driver():
    """Close the Neo4j driver"""
    if driver:
        driver.close()

# Test connection
try:
    with driver.session() as session:
        session.run("RETURN 1")
    print("SUCCESS: Connected to Neo4j successfully")
except Exception as e:
    print(f"ERROR: Failed to connect to Neo4j: {e}")
