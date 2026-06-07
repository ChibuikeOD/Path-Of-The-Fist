from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel

import os
import sys
import logging

# Ensure backend directory is in the Python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Import models and crud
import crud
import summarizer
from database import close_driver
from schemas import (
    EventCreate, EventResponse, EventWithRelations,
    PlayerCreate, PlayerResponse, PlayerWithEvent,
    CharacterCreate, CharacterResponse,
    SetCreate, SetResponse, SetWithPlayers, SetUpdate
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Path of the Fist API",
    description="Tournament Management and Data API",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== STARTUP/SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("Application starting up...")
    logger.info("Neo4j driver initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Application shutting down...")
    close_driver()



# ==================== HEALTH CHECK ====================

@app.get("/health", tags=["Health"])
async def health_check():
    """Check API health"""
    return {"status": "ok", "message": "API is running"}


# ==================== EVENTS ENDPOINTS ====================

@app.get("/events/", response_model=List[EventResponse], tags=["Events"])
async def list_events():
    """Get all events"""
    events = crud.get_all_events()
    return events


@app.get("/events/{event_id}", response_model=EventWithRelations, tags=["Events"])
async def get_event(event_id: int):
    """Get a single event with all players and sets"""
    event = crud.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.post("/events/", response_model=EventResponse, status_code=status.HTTP_201_CREATED, tags=["Events"])
async def create_event(event: EventCreate):
    """Create a new event"""
    try:
        db_event = crud.create_event(event)
        return db_event
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ==================== PLAYERS ENDPOINTS ====================

@app.get("/players/", response_model=List[PlayerResponse], tags=["Players"])
async def list_players():
    """Get all players"""
    players = crud.get_all_players()
    return players


@app.get("/players/{player_id}", response_model=PlayerWithEvent, tags=["Players"])
async def get_player(player_id: int):
    """Get a single player"""
    player = crud.get_player(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


@app.get("/players/event/{event_id}", response_model=List[PlayerResponse], tags=["Players"])
async def get_players_by_event(event_id: int):
    """Get all players in an event"""
    players = crud.get_players_by_event(event_id)
    return players


@app.post("/players/", response_model=PlayerResponse, status_code=status.HTTP_201_CREATED, tags=["Players"])
async def create_player(player: PlayerCreate):
    """Create a new player"""
    try:
        db_player = crud.create_player(player)
        return db_player
    except Exception as e:
        logger.error(f"Error creating player: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/players/{player_id}/rating", response_model=PlayerResponse, tags=["Players"])
async def update_player_rating(player_id: int, new_rating: int):
    """Update a player's rating"""
    player = crud.update_player_rating(player_id, new_rating)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


@app.get("/players/{player_id}/sets", response_model=List[SetResponse], tags=["Players"])
async def get_player_sets(player_id: int):
    """Get all sets involving a player"""
    sets = crud.get_player_sets(player_id)
    return sets


@app.get("/players/{player_id}/wins", response_model=List[SetResponse], tags=["Players"])
async def get_player_wins(player_id: int):
    """Get all sets won by a player"""
    sets = crud.get_player_wins(player_id)
    return sets


# ==================== CHARACTERS ENDPOINTS ====================

@app.get("/characters/", response_model=List[CharacterResponse], tags=["Characters"])
async def list_characters():
    """Get all playable characters"""
    characters = crud.get_all_characters()
    return characters


@app.get("/characters/{character_id}", response_model=CharacterResponse, tags=["Characters"])
async def get_character(character_id: int):
    """Get a single playable character"""
    character = crud.get_character(character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@app.get("/characters/event/{event_id}", response_model=List[CharacterResponse], tags=["Characters"])
async def get_characters_by_event(event_id: int):
    """Get all playable characters for an event"""
    characters = crud.get_characters_by_event(event_id)
    return characters


@app.post("/characters/", response_model=CharacterResponse, status_code=status.HTTP_201_CREATED, tags=["Characters"])
async def create_character(character: CharacterCreate):
    """Create a new playable character"""
    try:
        db_character = crud.create_character(character)
        return db_character
    except Exception as e:
        logger.error(f"Error creating character: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ==================== SETS ENDPOINTS ====================

@app.get("/sets/", response_model=List[SetResponse], tags=["Sets"])
async def list_sets():
    """Get all sets"""
    sets = crud.get_all_sets()
    return sets


@app.get("/sets/{set_id}", response_model=SetWithPlayers, tags=["Sets"])
async def get_set(set_id: int):
    """Get a single set with player details"""
    set_record = crud.get_set(set_id)
    if not set_record:
        raise HTTPException(status_code=404, detail="Set not found")
    return set_record


@app.get("/sets/event/{event_id}", response_model=List[SetResponse], tags=["Sets"])
async def get_sets_by_event(event_id: int):
    """Get all sets in an event"""
    sets = crud.get_sets_by_event(event_id)
    return sets


@app.post("/sets/", response_model=SetResponse, status_code=status.HTTP_201_CREATED, tags=["Sets"])
async def create_set(set_data: SetCreate):
    """Create a new set"""
    try:
        db_set = crud.create_set(set_data)
        return db_set
    except Exception as e:
        logger.error(f"Error creating set: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/sets/{set_id}", response_model=SetResponse, tags=["Sets"])
async def update_set(set_id: int, set_update: SetUpdate):
    """Update set details (e.g., declare winner)"""
    set_record = crud.get_set(set_id)
    if not set_record:
        raise HTTPException(status_code=404, detail="Set not found")

    if set_update.winnerid is not None:
        set_record = crud.update_set_winner(set_id, set_update.winnerid)

    return set_record


# ==================== SYNC ENDPOINTS ====================

class SyncStartGGRequest(BaseModel):
    years: Optional[List[int]] = None


@app.post("/sync/startgg", tags=["Sync"])
async def sync_startgg_data(req: Optional[SyncStartGGRequest] = None):
    """Sync Combo Breaker data from start.gg into the graph database."""
    try:
        logger.info("Starting start.gg sync...")
        result = crud.sync_combo_breaker_years(req.years if req else None)
        try:
            logger.info("Running summarizer to update event summaries...")
            summarizer.run_summarizer()
        except Exception as sum_err:
            logger.error(f"Failed to run summarizer after sync: {sum_err}")
        try:
            logger.info("Clearing database metadata cache...")
            clear_database_metadata_cache()
        except Exception as cache_err:
            logger.error(f"Failed to clear metadata cache: {cache_err}")
        return {
            "status": "success",
            "message": "Sync completed successfully",
            "result": result
        }
    except Exception as e:
        logger.error(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


# ==================== CHAT (GraphRAG) ====================

from graphRAG import generate_answer, generate_answer_stream, clear_database_metadata_cache


class ChatRequest(BaseModel):
    question: str


@app.post("/chat", tags=["Chat"])
async def chat(req: ChatRequest):
    """Ask a question about tournament data using GraphRAG."""
    try:
        answer, context, system_prompt = generate_answer(req.question)
        return {
            "answer": answer,
            "context": context,
            "system_prompt": system_prompt
        }
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream", tags=["Chat"])
async def chat_stream(req: ChatRequest):
    """Stream a question about tournament data using GraphRAG."""
    try:
        return StreamingResponse(
            generate_answer_stream(req.question),
            media_type="application/x-ndjson",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    except Exception as e:
        logger.error(f"Chat stream error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TTSRequest(BaseModel):
    text: str


@app.post("/tts", tags=["TTS"])
async def text_to_speech(req: TTSRequest):
    """Generate speech from text using ElevenLabs API and return the audio stream."""
    import requests
    elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "Anr9GtYh2VRXxiPplzxM").strip()
    
    if not elevenlabs_api_key:
        raise HTTPException(status_code=500, detail="ElevenLabs API key is not configured in backend environment.")
        
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": elevenlabs_api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": req.text,
        "model_id": "eleven_monolingual_v1",
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, stream=True)
        if response.status_code != 200:
            logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=response.status_code, detail=f"ElevenLabs error: {response.text}")
            
        def iter_audio():
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
                    
        return StreamingResponse(iter_audio(), media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ROOT ====================

@app.get("/", tags=["Root"])
async def root():
    """API root endpoint"""
    return {
        "message": "Path of the Fist - Tournament Management API",
        "docs": "/docs",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
