"""Neo4j Node definitions for Path of the Fist"""

from constants import DEFAULT_ELO_RATING

# ==================== Event Node ====================
class Event:
    """Event node in Neo4j"""
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name
    
    @staticmethod
    def from_dict(data: dict):
        return Event(data.get('id'), data.get('name'))


# ==================== Player Node ====================
class Player:
    """Player node in Neo4j"""
    def __init__(self, id: int, gamertag: str, rating: int = DEFAULT_ELO_RATING):
        self.id = id
        self.gamertag = gamertag
        self.rating = rating
    
    @staticmethod
    def from_dict(data: dict):
        return Player(
            data.get('id'),
            data.get('gamertag'),
            data.get('rating', DEFAULT_ELO_RATING)
        )


# ==================== Set Node ====================
class Set:
    """Set (match) node in Neo4j"""
    def __init__(self, id: int, player1_id: int, player2_id: int, 
                 event_id: int, winner_id: int = None, completed_at: str = None):
        self.id = id
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.event_id = event_id
        self.winner_id = winner_id
        self.completed_at = completed_at
    
    @staticmethod
    def from_dict(data: dict):
        return Set(
            data.get('id'),
            data.get('player1_id'),
            data.get('player2_id'),
            data.get('event_id'),
            data.get('winner_id'),
            data.get('completed_at')
        )


# ==================== Relationships ====================
# PARTICIPATED_IN: Player -> Event
# PLAYED_IN: Set -> Event
# PLAYER1: Set -> Player
# PLAYER2: Set -> Player
