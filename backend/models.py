from __future__ import annotations

import pydantic
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

    
class Player(BaseModel):
    id: Optional[int] = None
    gamerTag: Optional[str] = None
    sets: Optional[Set] = None


class SetSlot(BaseModel):
    id: int
    entrant: Player

class Set(BaseModel):
    id: int
    slots: list[SetSlot]


class Event(BaseModel):
    id: int
    name: str
    createdAt: datetime
    numEntrants: int
    sets: list[Set]
    entrants: list[Player]

class SetConnection(BaseModel):
    nodes: list[Set]

class Entrant(BaseModel):
    id: int
    event: Event
    name: str
    paginatedSets: SetConnection

class Tournament(BaseModel):
    id: int
    name: str
    countryCode: str
    