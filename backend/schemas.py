"""Pydantic schemas for API validation - Path of the Fist"""

from constants import DEFAULT_ELO_RATING
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


# ==================== Event Schemas ====================

class EventBase(BaseModel):
    name: str


class EventCreate(EventBase):
    id: int


class EventResponse(EventBase):
    id: int

    class Config:
        from_attributes = True


class EventWithRelations(EventResponse):
    pass

    class Config:
        from_attributes = True


# ==================== Player Schemas ====================

class PlayerBase(BaseModel):
    gamertag: str
    rating: Optional[int] = DEFAULT_ELO_RATING


class PlayerCreate(PlayerBase):
    id: int


class PlayerResponse(PlayerBase):
    id: int

    class Config:
        from_attributes = True


class PlayerWithEvent(PlayerResponse):
    event: Optional[EventResponse] = None

    class Config:
        from_attributes = True


# ==================== Set Schemas ====================

class SetBase(BaseModel):
    player1_id: int
    player2_id: int
    eventid: int
    winnerid: Optional[int] = None
    completed_at: Optional[datetime] = None


class SetCreate(SetBase):
    id: int


class SetResponse(SetBase):
    id: int

    class Config:
        from_attributes = True


class SetWithPlayers(SetResponse):
    player1: Optional[PlayerResponse] = None
    player2: Optional[PlayerResponse] = None
    winner: Optional[PlayerResponse] = None
    event: Optional[EventResponse] = None

    class Config:
        from_attributes = True


class SetUpdate(BaseModel):
    winnerid: Optional[int] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== Update forward references ====================
EventWithRelations.update_forward_refs()
SetWithPlayers.update_forward_refs()
