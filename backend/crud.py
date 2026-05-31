import requests
from time import sleep
from datetime import datetime, timezone
from typing import Optional, Sequence
from database import get_session, reset_driver
from schemas import EventCreate, PlayerCreate, SetCreate, CharacterCreate
from constants import DEFAULT_ELO_RATING
import logging
import os
from dotenv import load_dotenv
from neo4j.exceptions import ServiceUnavailable

_backend_dir = os.path.dirname(os.path.abspath(__file__))
_root_env = os.path.normpath(os.path.join(_backend_dir, "..", ".env"))
load_dotenv(_root_env)
_backend_env = os.path.join(_backend_dir, ".env")
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)

logger = logging.getLogger(__name__)

# ==================== START.GG API SYNC ====================

STARTGG_URL = "https://api.start.gg/gql/alpha"
COMBO_BREAKER_YEARS = (2022, 2023, 2024, 2025, 2026)


def _startgg_headers() -> dict[str, str]:
    token = (os.environ.get("STARTGG_TOKEN") or "").strip()
    if not token:
        raise ValueError("STARTGG_TOKEN environment variable must be set")
    return {"Authorization": f"Bearer {token}"}


def _startgg_post(query: str, variables: dict, timeout: int = 30) -> dict:
    """Send a GraphQL request to Start.gg with a small retry loop."""
    last_error: Optional[Exception] = None

    for attempt in range(5):
        try:
            response = requests.post(
                STARTGG_URL,
                json={"query": query, "variables": variables},
                headers=_startgg_headers(),
                timeout=timeout,
            )

            if response.status_code == 429:
                delay = min(2 ** attempt, 30)
                logger.warning("Start.gg rate limited; retrying in %s seconds", delay)
                sleep(delay)
                continue

            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(str(payload["errors"]))

            data = payload.get("data")
            if data is None:
                raise RuntimeError("Start.gg response did not include data")
            return data
        except Exception as exc:
            last_error = exc
            if attempt < 4:
                sleep(min(2 ** attempt, 10))

    if last_error:
        raise last_error
    raise RuntimeError("Unable to fetch data from Start.gg")


def _resolve_entrant_competitor(entrant: Optional[dict]) -> Optional[dict]:
    if not entrant:
        return None

    participants = entrant.get("participants") or []
    for participant in participants:
        player = participant.get("player") if participant else None
        if player and player.get("id") and player.get("gamerTag"):
            return {"id": player["id"], "gamertag": player["gamerTag"], "rating": DEFAULT_ELO_RATING}

    entrant_id = entrant.get("id")
    entrant_name = entrant.get("name")
    if entrant_id is not None and entrant_name:
        return {"id": entrant_id, "gamertag": entrant_name, "rating": DEFAULT_ELO_RATING}

    return None


def _default_combo_breaker_slug(year: int) -> str:
    return f"tournament/combo-breaker-{year}"


def _run_with_driver_retry(operation_name: str, operation):
    """Retry one time after resetting the Neo4j driver on routing failures."""
    for attempt in range(2):
        try:
            return operation()
        except Exception as exc:
            message = str(exc)
            recoverable = isinstance(exc, ServiceUnavailable) or "routing information" in message or "defunct connection" in message
            if attempt == 0 and recoverable:
                logger.warning("Neo4j routing issue during %s; resetting driver and retrying once.", operation_name)
                reset_driver()
                continue
            raise


def sync_event_from_startgg(
    event_id: int,
    event_name: str,
    tournament_slug: Optional[str] = None,
    tournament_name: Optional[str] = None,
    videogame_name: Optional[str] = None,
):
    """Create or update an event in the database."""
    def _write():
        session = get_session()
        try:
            result = session.run(
                """
                MERGE (e:Event {id: $event_id})
                ON CREATE SET e.name = $event_name
                SET e.name = $event_name,
                    e.tournament_slug = coalesce($tournament_slug, e.tournament_slug),
                    e.tournament_name = coalesce($tournament_name, e.tournament_name),
                    e.videogame_name = coalesce($videogame_name, e.videogame_name),
                    e.source = 'startgg'
                RETURN e
                """,
                event_id=event_id,
                event_name=event_name,
                tournament_slug=tournament_slug,
                tournament_name=tournament_name,
                videogame_name=videogame_name,
            )
            record = result.single()
            if record:
                logger.info(f"Event synced: {event_id} - {event_name}")
            return {"id": event_id, "name": event_name}
        finally:
            session.close()

    try:
        return _run_with_driver_retry(f"event {event_id}", _write)
    except Exception as e:
        logger.error(f"Error syncing event: {e}")
        raise


def sync_players_from_startgg(event_id: int, players_data: list):
    """Bulk insert/update players for an event."""
    if not players_data:
        return 0, 0

    def _write():
        session = get_session()
        try:
            session.run(
                """
                UNWIND $players AS player_data
                MERGE (p:Player {id: player_data.id})
                ON CREATE SET p.rating = player_data.rating
                SET p.gamertag = player_data.gamertag,
                    p.rating = coalesce(p.rating, player_data.rating)
                WITH collect(p) AS players
                MATCH (e:Event {id: $event_id})
                UNWIND players AS p
                MERGE (p)-[:PARTICIPATED_IN]->(e)
                """,
                players=players_data,
                event_id=event_id,
            )
            return len(players_data), 0
        finally:
            session.close()

    try:
        created_count, skipped_count = _run_with_driver_retry(f"players for event {event_id}", _write)
        logger.info(f"Synced players: {created_count} upserted, {skipped_count} skipped")
        return created_count, skipped_count
    except Exception as e:
        logger.error(f"Error syncing player batch for event {event_id}: {e}")
        return 0, len(players_data)


def sync_characters_from_startgg(event_id: int, characters_data: list):
    """Bulk insert/update playable characters for an event."""
    if not characters_data:
        return 0, 0

    def _write():
        session = get_session()
        try:
            session.run(
                """
                UNWIND $characters AS character_data
                MERGE (c:Character {id: character_data.id})
                SET c.name = character_data.name,
                    c.videogame_id = character_data.videogame_id,
                    c.videogame_name = character_data.videogame_name,
                    c.source = 'startgg'
                WITH collect(c) AS characters
                MATCH (e:Event {id: $event_id})
                UNWIND characters AS c
                MERGE (c)-[:PLAYABLE_IN]->(e)
                """,
                characters=characters_data,
                event_id=event_id,
            )
            return len(characters_data), 0
        finally:
            session.close()

    try:
        created_count, skipped_count = _run_with_driver_retry(f"characters for event {event_id}", _write)
        logger.info(f"Synced characters: {created_count} upserted, {skipped_count} skipped")
        return created_count, skipped_count
    except Exception as e:
        logger.error(f"Error syncing character batch for event {event_id}: {e}")
        return 0, len(characters_data)


def sync_sets_from_startgg(event_id: int, sets_data: list):
    """Bulk insert/update sets for an event."""
    if not sets_data:
        return 0, 0

    def _write():
        session = get_session()
        try:
            session.run(
                """
                UNWIND $sets AS set_data
                MERGE (s:Set {id: set_data.id})
                ON CREATE SET s.player1_id = set_data.p1_id,
                              s.player2_id = set_data.p2_id,
                              s.winner_id = set_data.winner_id,
                              s.completed_at = set_data.completed_at
                SET s.player1_id = set_data.p1_id,
                    s.player2_id = set_data.p2_id,
                    s.winner_id = set_data.winner_id,
                    s.completed_at = set_data.completed_at
                WITH s, set_data
                MATCH (e:Event {id: $event_id})
                MERGE (s)-[:PLAYED_IN]->(e)
                WITH s, set_data
                MATCH (p1:Player {id: set_data.p1_id})
                MATCH (p2:Player {id: set_data.p2_id})
                MERGE (s)-[:PLAYER1]->(p1)
                MERGE (s)-[:PLAYER2]->(p2)
                """,
                sets=[
                    {
                        "id": set_data["id"],
                        "p1_id": set_data.get("player1_id"),
                        "p2_id": set_data.get("player2_id"),
                        "winner_id": set_data.get("winnerid"),
                        "completed_at": set_data.get("completed_at"),
                    }
                    for set_data in sets_data
                ],
                event_id=event_id,
            )
            return len(sets_data), 0
        finally:
            session.close()

    try:
        created_count, skipped_count = _run_with_driver_retry(f"sets for event {event_id}", _write)
        logger.info(f"Synced sets: {created_count} upserted, {skipped_count} skipped")
        return created_count, skipped_count
    except Exception as e:
        logger.error(f"Error syncing set batch for event {event_id}: {e}")
        return 0, len(sets_data)


def fetch_tournament_events_from_api(tournament_slug: str) -> dict:
    """Fetch tournament metadata and event list from Start.gg."""
    query = """
    query TournamentEvents($slug: String!) {
      tournament(slug: $slug) {
        id
        name
        events {
          id
          name
          videogame {
            id
            name
            characters {
              id
              name
            }
          }
        }
      }
    }
    """

    data = _startgg_post(query, {"slug": tournament_slug})
    tournament = data.get("tournament")
    if not tournament:
        raise ValueError(f"Tournament not found for slug: {tournament_slug}")
    return tournament


def fetch_event_sets_from_api(event_id: int, per_page: int = 100) -> dict:
    """Fetch all sets for a single Start.gg event."""
    query = """
    query EventSets($eventId: ID!, $page: Int!, $perPage: Int!) {
      event(id: $eventId) {
        id
        name
        sets(page: $page, perPage: $perPage, sortType: STANDARD) {
          pageInfo {
            totalPages
          }
          nodes {
            id
            winnerId
            completedAt
            slots {
              entrant {
                id
                name
                participants {
                  player {
                    id
                    gamerTag
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    first_page = _startgg_post(query, {"eventId": event_id, "page": 1, "perPage": per_page})
    event_data = first_page.get("event")
    if not event_data:
        raise ValueError(f"Event not found for id: {event_id}")

    sets = event_data.get("sets") or {}
    total_pages = sets.get("pageInfo", {}).get("totalPages", 1) or 1
    nodes = list(sets.get("nodes") or [])

    for page in range(2, total_pages + 1):
        page_data = _startgg_post(query, {"eventId": event_id, "page": page, "perPage": per_page})
        page_event = page_data.get("event") or {}
        page_sets = page_event.get("sets") or {}
        nodes.extend(page_sets.get("nodes") or [])

    return {"event": event_data, "sets": nodes}


def sync_tournament_from_startgg(tournament_slug: str, per_page: int = 100):
    """Fetch a tournament's events and sync every event/set/player into Neo4j."""
    tournament = fetch_tournament_events_from_api(tournament_slug)
    tournament_name = tournament["name"]
    synced_events = 0
    synced_players = 0
    synced_sets = 0
    synced_characters = 0
    skipped_players = 0
    skipped_sets = 0
    skipped_characters = 0

    for event in tournament.get("events") or []:
        event_id = event["id"]
        event_name = event["name"]
        videogame = event.get("videogame") or {}
        videogame_id = videogame.get("id")
        videogame_name = videogame.get("name")

        logger.info(
            "Syncing event %s (%s) from %s",
            event_name,
            event_id,
            tournament_slug,
        )
        sync_event_from_startgg(
            event_id,
            event_name,
            tournament_slug=tournament_slug,
            tournament_name=tournament_name,
            videogame_name=videogame_name,
        )

        characters_list = [
            {
                "id": character["id"],
                "name": character["name"],
                "videogame_id": videogame_id,
                "videogame_name": videogame_name,
            }
            for character in videogame.get("characters") or []
            if character.get("id") is not None and character.get("name")
        ]
        if characters_list:
            created_characters, skipped_character_count = sync_characters_from_startgg(event_id, characters_list)
            synced_characters += created_characters
            skipped_characters += skipped_character_count

        try:
            event_payload = fetch_event_sets_from_api(event_id, per_page=per_page)
        except Exception as exc:
            logger.error("Error fetching sets for event %s: %s", event_id, exc)
            continue

        unique_players = {}
        batch_sets = []

        for set_record in event_payload["sets"]:
            slots = set_record.get("slots") or []
            if len(slots) < 2:
                skipped_sets += 1
                continue

            entrant_1 = slots[0].get("entrant")
            entrant_2 = slots[1].get("entrant")
            competitor_1 = _resolve_entrant_competitor(entrant_1)
            competitor_2 = _resolve_entrant_competitor(entrant_2)

            if not competitor_1 or not competitor_2:
                skipped_sets += 1
                continue

            winner_entrant_id = set_record.get("winnerId")
            resolved_winner_id = None
            if str(winner_entrant_id) == str((entrant_1 or {}).get("id")):
                resolved_winner_id = competitor_1["id"]
            elif str(winner_entrant_id) == str((entrant_2 or {}).get("id")):
                resolved_winner_id = competitor_2["id"]

            unique_players[competitor_1["id"]] = competitor_1
            unique_players[competitor_2["id"]] = competitor_2

            raw_time = set_record.get("completedAt")
            completed_at = None
            if raw_time:
                try:
                    completed_at = datetime.fromtimestamp(raw_time, tz=timezone.utc)
                except Exception:
                    completed_at = None

            batch_sets.append(
                {
                    "id": set_record["id"],
                    "player1_id": competitor_1["id"],
                    "player2_id": competitor_2["id"],
                    "winnerid": resolved_winner_id,
                    "completed_at": completed_at,
                }
            )

        if unique_players:
            players_list = list(unique_players.values())
            created_players, skipped_player_count = sync_players_from_startgg(event_id, players_list)
            synced_players += created_players
            skipped_players += skipped_player_count

        if batch_sets:
            created_sets, skipped_batch_sets = sync_sets_from_startgg(event_id, batch_sets)
            synced_sets += created_sets
            skipped_sets += skipped_batch_sets

        synced_events += 1
        sleep(0.5)

    logger.info(
        "Sync complete for %s: events=%s players=%s sets=%s characters=%s skipped_players=%s skipped_sets=%s skipped_characters=%s",
        tournament_slug,
        synced_events,
        synced_players,
        synced_sets,
        synced_characters,
        skipped_players,
        skipped_sets,
        skipped_characters,
    )
    return {
        "tournament_slug": tournament_slug,
        "tournament_name": tournament_name,
        "events_synced": synced_events,
        "players_synced": synced_players,
        "sets_synced": synced_sets,
        "characters_synced": synced_characters,
        "skipped_players": skipped_players,
        "skipped_sets": skipped_sets,
        "skipped_characters": skipped_characters,
    }


def sync_combo_breaker_years(years: Optional[Sequence[int]] = None):
    """Sync the requested Combo Breaker tournaments into Neo4j."""
    selected_years = tuple(years) if years else COMBO_BREAKER_YEARS
    results = []
    for year in selected_years:
        tournament_slug = _default_combo_breaker_slug(year)
        logger.info("Starting Combo Breaker %s sync", year)
        results.append(sync_tournament_from_startgg(tournament_slug))
    return results


def get_all_event_sets_from_api():
    """Backward-compatible helper that syncs the requested Combo Breaker years."""
    return sync_combo_breaker_years()


# ==================== EVENT CRUD ====================

def create_event(event: EventCreate):
    """Create a new event"""
    try:
        session = get_session()
        result = session.run(
            """
            CREATE (e:Event {id: $id, name: $name})
            RETURN {id: e.id, name: e.name} AS event
            """,
            id=event.id,
            name=event.name
        )
        record = result.single()
        session.close()
        logger.info(f"Created event: {event.id}")
        return record["event"] if record else None
    except Exception as e:
        logger.warning(f"Event {event.id} may already exist: {e}")
        return get_event(event.id)


def get_event(event_id: int):
    """Get a single event by ID"""
    session = get_session()
    result = session.run(
        "MATCH (e:Event {id: $id}) RETURN {id: e.id, name: e.name} AS event",
        id=event_id
    )
    record = result.single()
    session.close()
    return record["event"] if record else None


def get_all_events():
    """Get all events"""
    session = get_session()
    result = session.run(
        "MATCH (e:Event) RETURN {id: e.id, name: e.name} AS event"
    )
    events = [record["event"] for record in result]
    session.close()
    return events


# ==================== PLAYER CRUD ====================

def create_player(player: PlayerCreate):
    """Create a new player"""
    try:
        session = get_session()
        result = session.run(
            """
            CREATE (p:Player {id: $id, gamertag: $gamertag, rating: $rating})
            RETURN {id: p.id, gamertag: p.gamertag, rating: p.rating} AS player
            """,
            id=player.id,
            gamertag=player.gamertag,
            rating=player.rating if player.rating is not None else DEFAULT_ELO_RATING
        )
        record = result.single()
        
        # Link to event if provided
        if player.eventid:
            session.run(
                """
                MATCH (p:Player {id: $player_id})
                MATCH (e:Event {id: $event_id})
                CREATE (p)-[:PARTICIPATED_IN]->(e)
                """,
                player_id=player.id,
                event_id=player.eventid
            )
        
        session.close()
        logger.info(f"Created player: {player.id} - {player.gamertag}")
        return record["player"] if record else None
    except Exception as e:
        logger.warning(f"Player {player.id} may already exist: {e}")
        return get_player(player.id)


def get_player(player_id: int):
    """Get a single player by ID"""
    session = get_session()
    result = session.run(
        "MATCH (p:Player {id: $id}) RETURN {id: p.id, gamertag: p.gamertag, rating: p.rating} AS player",
        id=player_id
    )
    record = result.single()
    session.close()
    return record["player"] if record else None


def get_players_by_event(event_id: int):
    """Get all players for a specific event"""
    session = get_session()
    result = session.run(
        """
        MATCH (p:Player)-[:PARTICIPATED_IN]->(e:Event {id: $event_id})
        RETURN {id: p.id, gamertag: p.gamertag, rating: p.rating} AS player
        """,
        event_id=event_id
    )
    players = [record["player"] for record in result]
    session.close()
    return players


def get_all_players():
    """Get all players"""
    session = get_session()
    result = session.run(
        """
        MATCH (p:Player)
        WHERE p.id IS NOT NULL AND p.gamertag IS NOT NULL
        RETURN {id: p.id, gamertag: p.gamertag, rating: p.rating} AS player
        """
    )
    players = [record["player"] for record in result]
    session.close()
    return players


# ==================== CHARACTER CRUD ====================

def create_character(character: CharacterCreate):
    """Create a new playable character."""
    try:
        session = get_session()
        result = session.run(
            """
            MERGE (c:Character {id: $id})
            SET c.name = $name,
                c.videogame_id = $videogame_id,
                c.videogame_name = $videogame_name
            RETURN {
                id: c.id,
                name: c.name,
                videogame_id: c.videogame_id,
                videogame_name: c.videogame_name
            } AS character
            """,
            id=character.id,
            name=character.name,
            videogame_id=character.videogame_id,
            videogame_name=character.videogame_name,
        )
        record = result.single()

        if character.eventid:
            session.run(
                """
                MATCH (c:Character {id: $character_id})
                MATCH (e:Event {id: $event_id})
                MERGE (c)-[:PLAYABLE_IN]->(e)
                """,
                character_id=character.id,
                event_id=character.eventid,
            )

        session.close()
        logger.info(f"Created character: {character.id} - {character.name}")
        return record["character"] if record else None
    except Exception as e:
        logger.warning(f"Character {character.id} may already exist: {e}")
        return get_character(character.id)


def get_character(character_id: int):
    """Get a single character by ID."""
    session = get_session()
    result = session.run(
        """
        MATCH (c:Character {id: $id})
        RETURN {
            id: c.id,
            name: c.name,
            videogame_id: c.videogame_id,
            videogame_name: c.videogame_name
        } AS character
        """,
        id=character_id,
    )
    record = result.single()
    session.close()
    return record["character"] if record else None


def get_characters_by_event(event_id: int):
    """Get all playable characters for a specific event."""
    session = get_session()
    result = session.run(
        """
        MATCH (c:Character)-[:PLAYABLE_IN]->(e:Event {id: $event_id})
        RETURN {
            id: c.id,
            name: c.name,
            videogame_id: c.videogame_id,
            videogame_name: c.videogame_name
        } AS character
        ORDER BY character.name
        """,
        event_id=event_id,
    )
    characters = [record["character"] for record in result]
    session.close()
    return characters


def get_all_characters():
    """Get all playable characters."""
    session = get_session()
    result = session.run(
        """
        MATCH (c:Character)
        RETURN {
            id: c.id,
            name: c.name,
            videogame_id: c.videogame_id,
            videogame_name: c.videogame_name
        } AS character
        ORDER BY character.videogame_name, character.name
        """
    )
    characters = [record["character"] for record in result]
    session.close()
    return characters


def update_player_rating(player_id: int, new_rating: int):
    """Update a player's rating"""
    try:
        session = get_session()
        result = session.run(
            """
            MATCH (p:Player {id: $id})
            SET p.rating = $rating
            RETURN {id: p.id, gamertag: p.gamertag, rating: p.rating} AS player
            """,
            id=player_id,
            rating=new_rating
        )
        record = result.single()
        session.close()
        logger.info(f"Updated player {player_id} rating to {new_rating}")
        return record["player"] if record else None
    except Exception as e:
        logger.error(f"Error updating player rating: {e}")
        return None


# ==================== SET CRUD ====================

def create_set(set_data: SetCreate):
    """Create a new set"""
    try:
        session = get_session()
        result = session.run(
            """
            CREATE (s:Set {
                id: $id,
                player1_id: $p1_id,
                player2_id: $p2_id,
                winner_id: $winner_id,
                completed_at: $completed_at
            })
            WITH s
            MATCH (e:Event {id: $event_id})
            CREATE (s)-[:PLAYED_IN]->(e)
            WITH s
            MATCH (p1:Player {id: $p1_id})
            MATCH (p2:Player {id: $p2_id})
            CREATE (s)-[:PLAYER1]->(p1)
            CREATE (s)-[:PLAYER2]->(p2)
            RETURN {
                id: s.id,
                player1_id: s.player1_id,
                player2_id: s.player2_id,
                winner_id: s.winner_id,
                completed_at: s.completed_at
            } AS set_result
            """,
            id=set_data.id,
            p1_id=set_data.player1_id,
            p2_id=set_data.player2_id,
            winner_id=set_data.winnerid,
            event_id=set_data.eventid,
            completed_at=set_data.completed_at
        )
        record = result.single()
        session.close()
        logger.info(f"Created set: {set_data.id}")
        return record["set_result"] if record else None
    except Exception as e:
        logger.warning(f"Set {set_data.id} may already exist: {e}")
        return get_set(set_data.id)


def get_set(set_id: int):
    """Get a single set by ID"""
    session = get_session()
    result = session.run(
        """
        MATCH (s:Set {id: $id})
        RETURN {
            id: s.id,
            player1_id: s.player1_id,
            player2_id: s.player2_id,
            winner_id: s.winner_id,
            completed_at: s.completed_at
        } AS set_result
        """,
        id=set_id
    )
    record = result.single()
    session.close()
    return record["set_result"] if record else None


def get_sets_by_event(event_id: int):
    """Get all sets for a specific event"""
    session = get_session()
    result = session.run(
        """
        MATCH (s:Set)-[:PLAYED_IN]->(e:Event {id: $event_id})
        RETURN {
            id: s.id,
            player1_id: s.player1_id,
            player2_id: s.player2_id,
            winner_id: s.winner_id,
            completed_at: s.completed_at
        } AS set_result
        """,
        event_id=event_id
    )
    sets = [record["set_result"] for record in result]
    session.close()
    return sets


def get_all_sets():
    """Get all sets"""
    session = get_session()
    result = session.run(
        """
        MATCH (s:Set)
        RETURN {
            id: s.id,
            player1_id: s.player1_id,
            player2_id: s.player2_id,
            winner_id: s.winner_id,
            completed_at: s.completed_at
        } AS set_result
        """
    )
    sets = [record["set_result"] for record in result]
    session.close()
    return sets


def update_set_winner(set_id: int, winner_id: int):
    """Update the winner of a set"""
    try:
        session = get_session()
        result = session.run(
            """
            MATCH (s:Set {id: $set_id})
            SET s.winner_id = $winner_id, s.completed_at = $completed_at
            RETURN {
                id: s.id,
                player1_id: s.player1_id,
                player2_id: s.player2_id,
                winner_id: s.winner_id,
                completed_at: s.completed_at
            } AS set_result
            """,
            set_id=set_id,
            winner_id=winner_id,
            completed_at=datetime.now(timezone.utc).isoformat()
        )
        record = result.single()
        session.close()
        logger.info(f"Updated set {set_id} winner to {winner_id}")
        return record["set_result"] if record else None
    except Exception as e:
        logger.error(f"Error updating set winner: {e}")
        return None


def get_player_sets(player_id: int):
    """Get all sets involving a specific player (as player1, player2, or winner)"""
    session = get_session()
    result = session.run(
        """
        MATCH (s:Set)
        WHERE s.player1_id = $player_id OR s.player2_id = $player_id
        RETURN {
            id: s.id,
            player1_id: s.player1_id,
            player2_id: s.player2_id,
            winner_id: s.winner_id,
            completed_at: s.completed_at
        } AS set_result
        """,
        player_id=player_id
    )
    sets = [record["set_result"] for record in result]
    session.close()
    return sets


def get_player_wins(player_id: int):
    """Get all sets won by a specific player"""
    session = get_session()
    result = session.run(
        """
        MATCH (s:Set)
        WHERE s.winner_id = $player_id
        RETURN {
            id: s.id,
            player1_id: s.player1_id,
            player2_id: s.player2_id,
            winner_id: s.winner_id,
            completed_at: s.completed_at
        } AS set_result
        """,
        player_id=player_id
    )
    sets = [record["set_result"] for record in result]
    session.close()
    return sets


if __name__ == "__main__":
    # For testing: run sync manually
    try:
        result = get_all_event_sets_from_api()
        print(f"Sync result: {result}")
    except Exception as e:
        logger.error(f"Error in sync: {e}")
