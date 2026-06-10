import json
import os
import time
import re
import requests
from typing import Iterator
from neo4j import GraphDatabase
from database import driver
from constants import DEFAULT_ELO_RATING

class NonRetryableError(Exception):
    pass


# #region agent log
_DEBUG_LOG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "debug-e51cb9.log")
)


def _agent_log(message: str, data: dict, hypothesis_id: str, run_id: str = "repro") -> None:
    try:
        payload = {
            "sessionId": "e51cb9",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": "backend/graphRAG.py",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass

# #endregion


from dotenv import load_dotenv

load_dotenv()
_backend_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
CHAT_PROVIDER = os.environ.get("CHAT_PROVIDER", "deepseek").strip().lower()

# Demo/mock system variables and functions removed for production.


def _json_line(event_type: str, **payload) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", 
    "with", "by", "about", "against", "between", "into", "through", "during", 
    "before", "after", "above", "below", "to", "from", "up", "down", "in", "out", 
    "on", "off", "over", "under", "again", "further", "then", "once", "here", 
    "there", "when", "where", "why", "how", "all", "any", "both", "each", "few", 
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", 
    "same", "so", "than", "too", "very", "s", "t", "can", "will", "just", "don", 
    "should", "now", "i", "me", "my", "myself", "we", "our", "ours", "ourselves", 
    "you", "your", "yours", "yourself", "yourselves", "he", "him", "his", "himself", 
    "she", "her", "hers", "herself", "it", "its", "itself", "they", "them", "their", 
    "theirs", "themselves", "what", "which", "who", "whom", "this", "that", "these", 
    "those", "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", 
    "had", "having", "do", "does", "did", "doing", "did", "won", "lost", "play", 
    "played", "player", "players", "game", "games", "match", "matches", "tournament", 
    "upset", "upsets", "bracket", "win", "wins", "loss", "losses", "run", "runs",
    "street", "fighter", "sf6", "sfv", "sf4", "smash", "melee", "ultimate", 
    "ssbm", "ssbu", "guilty", "gear", "strive", "ggst", "tekken", "tk", "tk8", 
    "mortal", "kombat", "mk", "fist", "combo", "breaker", "cb", "cb2025", "2025", 
    "champion", "championship", "champ", "champs", "winner", "winners", "loser", 
    "losers", "underdog", "favorite", "favorites",
    # Additional generic query and dictionary words to prevent false positive player matching
    "data", "info", "details", "stats", "statistics", "history", "record", "records",
    "know", "knows", "knowing", "think", "thinks", "thought", "whether", "either", "neither",
    "have", "has", "had", "having", "do", "does", "did", "done",
    "get", "gets", "got", "getting", "find", "finds", "found", "show", "shows", "shown",
    "tell", "tells", "told", "give", "gives", "gave", "given", "list", "lists", "listed",
    "see", "sees", "saw", "seen", "look", "looks", "available", "exist", "exists",
    "year", "years", "date", "dates", "time", "times", "day", "days",
    "many", "much", "anyway", "actually", "sure", "yes", "no",
    "nobody", "anyone", "someone", "everyone", "somebody", "anybody",
    "real", "life", "world", "earth", "people", "person",
    "best", "worst", "good", "bad", "great", "awesome", "cool", "super",
    "name", "names", "named", "character", "characters",
    "2022", "2023", "2024", "2026",
    "cb2022", "cb2023", "cb2024", "cb2026"
}


_EVENT_ALIASES = {
    "sf6": "Street Fighter 6",
    "street fighter 6": "Street Fighter 6",
    "tekken 8": "TEKKEN 8",
    "tk8": "TEKKEN 8",
    "strive": "Guilty Gear -Strive-",
    "guilty gear strive": "Guilty Gear -Strive-",
    "ggst": "Guilty Gear -Strive-",
    "melee": "Super Smash Bros. Melee",
    "ssbm": "Super Smash Bros. Melee",
    "ultimate": "Super Smash Bros. Ultimate",
    "ssbu": "Super Smash Bros. Ultimate",
    "umvc3": "Ultimate Marvel vs. Capcom 3",
    "marvel 3": "Ultimate Marvel vs. Capcom 3",
    "mk1": "Mortal Kombat 1",
    "mortal kombat 1": "Mortal Kombat 1",
    "ki": "Killer Instinct",
    "killer instinct": "Killer Instinct",
    "kofxv": "The King of Fighters XV",
    "kof xv": "The King of Fighters XV",
    "3rd strike": "Street Fighter III: 3rd Strike",
    "third strike": "Street Fighter III: 3rd Strike",
    "sf3": "Street Fighter III: 3rd Strike",
}


def detect_mentioned_players(query: str) -> list[str]:
    """Dynamically query Neo4j for players matching clean words in query."""
    words = [w.lower() for w in re.sub(r'[^a-zA-Z0-9\s]', ' ', query).split()]
    filtered_keywords = [w for w in words if w not in _STOP_WORDS and len(w) >= 3]
    if not filtered_keywords:
        return []

    try:
        with driver.session() as session:
            res = session.run(
                """
                MATCH (p:Player)
                WHERE p.gamertag IS NOT NULL AND any(kw IN $keywords WHERE toLower(p.gamertag) CONTAINS kw)
                RETURN p.gamertag AS gamertag
                """,
                keywords=filtered_keywords
            )
            raw_matches = [r["gamertag"] for r in res if r["gamertag"]]

        query_lower = query.lower()
        mentioned = set()
        for player in raw_matches:
            player_lower = player.lower()
            if ' ' not in player_lower:
                if player_lower in words and player_lower not in _STOP_WORDS:
                    mentioned.add(player)
            elif player_lower in query_lower:
                mentioned.add(player)
            else:
                player_words = player_lower.split()
                for w in player_words:
                    if len(w) >= 3 and w not in _STOP_WORDS and w in words:
                        mentioned.add(player)
                        break
        return list(mentioned)
    except Exception as e:
        print(f"Error dynamically detecting players: {e}")
        return []


def detect_mentioned_events(query: str) -> list[str]:
    """Dynamically query Neo4j for events matching clean words/aliases in query."""
    words = [w.lower() for w in re.sub(r'[^a-zA-Z0-9\s]', ' ', query).split()]
    filtered_keywords = [w for w in words if w not in _STOP_WORDS and len(w) >= 3]

    query_lower = query.lower()
    alias_matches = set()
    for alias, canonical in _EVENT_ALIASES.items():
        if alias in query_lower:
            alias_matches.add(canonical)

    if not filtered_keywords and not alias_matches:
        return []

    try:
        with driver.session() as session:
            res = session.run(
                """
                MATCH (e:Event)
                WHERE e.name IS NOT NULL AND (
                    any(kw IN $keywords WHERE toLower(e.name) CONTAINS kw)
                    OR toLower(e.name) IN $alias_names
                )
                RETURN DISTINCT e.name AS name
                """,
                keywords=filtered_keywords,
                alias_names=[n.lower() for n in alias_matches]
            )
            event_names = [r["name"] for r in res if r["name"]]

        final_events = set()
        for name in event_names:
            name_lower = name.lower()
            if name in alias_matches:
                final_events.add(name)
                continue
            if name_lower in query_lower:
                final_events.add(name)
                continue

            clean_name_words = re.sub(r'[^a-z0-9\s]', ' ', name_lower).split()
            for w in clean_name_words:
                if w in {"strive", "melee", "ultimate", "brawlhalla", "multiversus", "brawl"} and w in query_lower:
                    final_events.add(name)
                    break
        return list(final_events)
    except Exception as e:
        print(f"Error dynamically detecting events: {e}")
        return []


def detect_mentioned_years(query: str) -> list[str]:
    """Extract mentioned tournament years (2022-2026)."""
    return list(set(re.findall(r'\b(2022|2023|2024|2025|2026)\b', query)))


def is_character_question(query: str) -> bool:
    """Detect questions that need Character-node context."""
    query_lower = query.lower()
    character_terms = {
        "character", "characters", "main", "mains", "picks", "pick", "played",
        "uses", "use", "selected", "selection", "prominent", "popular", "roster",
        "performance", "perform", "performed", "best", "worst", "winrate", "win rate",
    }
    return any(re.search(rf"\b{re.escape(term)}\b", query_lower) for term in character_terms)


def is_character_performance_question(query: str) -> bool:
    """Detect questions asking for character results rather than roster availability."""
    query_lower = query.lower()
    performance_terms = {
        "performance", "perform", "performed", "best", "worst", "strongest",
        "weakest", "winrate", "win rate", "wins", "losses", "results",
    }
    character_terms = {"character", "characters", "main", "mains", "pick", "picks"}
    has_performance = any(re.search(rf"\b{re.escape(term)}\b", query_lower) for term in performance_terms)
    has_character = any(re.search(rf"\b{re.escape(term)}\b", query_lower) for term in character_terms)
    return has_performance and (has_character or is_character_question(query))


def detect_mentioned_characters(query: str) -> list[str]:
    """Dynamically query Neo4j for character names matching clean words in query."""
    words = [w.lower() for w in re.sub(r'[^a-zA-Z0-9\s]', ' ', query).split()]
    filtered_keywords = [w for w in words if w not in _STOP_WORDS and len(w) >= 2]
    if not filtered_keywords:
        return []

    try:
        with driver.session() as session:
            res = session.run(
                """
                MATCH (c:Character)
                WHERE c.name IS NOT NULL AND any(kw IN $keywords WHERE toLower(c.name) CONTAINS kw)
                RETURN DISTINCT c.name AS name
                """,
                keywords=filtered_keywords,
            )
            raw_matches = [r["name"] for r in res if r["name"]]

        query_lower = query.lower()
        mentioned = set()
        for character in raw_matches:
            character_lower = character.lower()
            clean_character_words = re.sub(r'[^a-z0-9\s]', ' ', character_lower).split()
            if character_lower in query_lower:
                mentioned.add(character)
                continue
            for w in clean_character_words:
                if len(w) >= 2 and w not in _STOP_WORDS and w in words:
                    mentioned.add(character)
                    break
        return list(mentioned)
    except Exception as e:
        print(f"Error dynamically detecting characters: {e}")
        return []


def get_local_context(player_names: list[str]) -> str:
    """Retrieves the 2-hop neighborhood context for the specified player names."""
    t0 = time.time()
    _agent_log("neo4j_local_context_start", {"players": player_names}, "A_local")
    context_lines = []

    player_details_cypher = """
    MATCH (p:Player)
    WHERE p.gamertag IN $player_names
    OPTIONAL MATCH (p)-[:PARTICIPATED_IN]->(e:Event)
    RETURN p.gamertag AS gamertag,
           coalesce(p.rating, $default_rating) AS rating,
           coalesce(p.wins, 0) AS wins,
           coalesce(p.losses, 0) AS losses,
           collect(DISTINCT e.tournament_name + ' ' + e.name) AS events
    """

    player_sets_cypher = """
    MATCH (p:Player)
    WHERE p.gamertag IN $player_names
    MATCH (s:Set)-[:PLAYER1|PLAYER2]->(p)
    MATCH (s)-[:PLAYER1]->(p1:Player)
    MATCH (s)-[:PLAYER2]->(p2:Player)
    MATCH (s)-[:PLAYED_IN]->(e:Event)
    OPTIONAL MATCH (winner:Player {id: s.winner_id})

    // Fetch SetPlayer and character info
    OPTIONAL MATCH (s)-[:HAS_ENTRY]->(sp1:SetPlayer)-[:PLAYER]->(p1)
    OPTIONAL MATCH (sp1)-[:USED_CHARACTER]->(c1:Character)
    OPTIONAL MATCH (s)-[:HAS_ENTRY]->(sp2:SetPlayer)-[:PLAYER]->(p2)
    OPTIONAL MATCH (sp2)-[:USED_CHARACTER]->(c2:Character)

    RETURN p1.gamertag AS p1,
           coalesce(p1.rating, $default_rating) AS p1_rating,
           p2.gamertag AS p2,
           coalesce(p2.rating, $default_rating) AS p2_rating,
           coalesce(winner.gamertag, 'Unknown') AS winner,
           e.name AS event,
           e.tournament_name AS tournament,
           s.completed_at AS completed_at,
           collect(DISTINCT c1.name) AS p1_chars,
           collect(DISTINCT c2.name) AS p2_chars
    ORDER BY completed_at DESC
    LIMIT 25
    """

    player_character_cypher = """
    MATCH (p:Player)
    WHERE p.gamertag IN $player_names
    OPTIONAL MATCH (sp:SetPlayer)-[:PLAYER]->(p)
    OPTIONAL MATCH (sp)-[:USED_CHARACTER]->(c:Character)
    WITH p, c, count(sp) AS set_count
    WHERE c IS NOT NULL
    RETURN p.gamertag AS gamertag,
           collect({
               character: c.name,
               videogame: c.videogame_name,
               count: set_count
           }) AS character_usage
    """

    try:
        with driver.session() as session:
            details_res = session.run(
                player_details_cypher,
                player_names=player_names,
                default_rating=DEFAULT_ELO_RATING,
            )
            for record in details_res:
                events_str = ", ".join(record["events"]) if record["events"] else "None"
                context_lines.append(
                    f"### Player Profile: {record['gamertag']}\n"
                    f"* **Rating**: {record['rating']}\n"
                    f"* **Record**: {record['wins']} Wins - {record['losses']} Losses\n"
                    f"* **Events Participated**: {events_str}\n"
                )

            sets_res = session.run(
                player_sets_cypher,
                player_names=player_names,
                default_rating=DEFAULT_ELO_RATING,
            )
            sets_lines = []
            for record in sets_res:
                p1_c = f" using {', '.join(record['p1_chars'])}" if record.get('p1_chars') else ""
                p2_c = f" using {', '.join(record['p2_chars'])}" if record.get('p2_chars') else ""
                line = (
                    f"- {record['p1']}{p1_c} (Rating: {record['p1_rating']}) vs {record['p2']}{p2_c} (Rating: {record['p2_rating']}), "
                    f"winner: {record['winner']}, event: {record['event']} ({record['tournament']})."
                )
                sets_lines.append(line)

            if sets_lines:
                context_lines.append("### Relevant Matches")
                context_lines.extend(sets_lines)
            else:
                context_lines.append("### Relevant Matches\n* No matches found in database.")

            character_res = session.run(player_character_cypher, player_names=player_names)
            context_lines.append("### Player Character Data")
            found_character_usage = False
            for record in character_res:
                usage = [u for u in (record.get("character_usage") or []) if u and u.get("character")]
                if usage:
                    found_character_usage = True
                    for u in usage:
                        context_lines.append(
                            f"* {record['gamertag']} used {u['character']} ({u['videogame']}) in {u['count']} set(s)."
                        )
                else:
                    context_lines.append(
                        f"* No set-level character selections were recorded for {record['gamertag']}."
                    )
            if not found_character_usage:
                context_lines.append(
                    "* The graph contains character rosters, but no dynamic character selections have been synchronized for these players."
                )
    except Exception as exc:
        print(f"Neo4j query failed ({exc}); using fallback local context.")
        _agent_log("neo4j_local_context_fallback", {"error": str(exc)}, "A_local")
        return ""

    context_str = "\n".join(context_lines)
    _agent_log(
        "neo4j_local_context_done",
        {"line_count": len(context_lines), "elapsed_ms": int((time.time() - t0) * 1000)},
        "A_local",
    )
    return context_str


def get_character_context(event_names: list[str] = None, years: list[str] = None) -> str:
    """Retrieve Character-node context for roster/prominence questions."""
    conditions = []
    params = {}
    if event_names:
        conditions.append("e.name IN $event_names")
        params["event_names"] = event_names
    if years:
        conditions.append("any(yr IN $years WHERE e.tournament_name CONTAINS yr)")
        params["years"] = years

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cypher = f"""
    MATCH (c:Character)-[:PLAYABLE_IN]->(e:Event)
    {where_clause}
    WITH c,
         count(DISTINCT e) AS event_count,
         collect(DISTINCT e.name) AS events,
         collect(DISTINCT e.tournament_name) AS tournaments
    RETURN c.name AS character,
           c.videogame_name AS videogame,
           event_count,
           events,
           tournaments
    ORDER BY event_count DESC, character ASC
    LIMIT 25
    """

    try:
        with driver.session() as session:
            rows = session.run(cypher, **params).data()
    except Exception as exc:
        print(f"Neo4j character query failed ({exc}); omitting character context.")
        return ""

    if not rows:
        return (
            "### Character Data\n"
            "* No Character nodes matched the requested event/year filters.\n"
        )

    lines = [
        "### Character Data",
        "* Character nodes represent playable roster availability per event and dynamic usage in tournament sets.",
        "* Prominence metric available in this graph: number of matched events where the character is playable.",
        "#### Most Prominent Characters By Roster Availability",
    ]
    for idx, row in enumerate(rows, 1):
        tournaments = ", ".join(row["tournaments"] or [])
        events = ", ".join(row["events"] or [])
        lines.append(
            f"{idx}. {row['character']} ({row['videogame']}) - playable in "
            f"{row['event_count']} matched event(s); tournaments: {tournaments}; events: {events}"
        )

    return "\n".join(lines)


def get_character_performance_context(
    event_names: list[str] = None,
    years: list[str] = None,
    character_names: list[str] = None,
) -> str:
    """Retrieve character performance metrics directly from SetPlayer character usage."""
    conditions = []
    params = {}
    if event_names:
        conditions.append("e.name IN $event_names")
        params["event_names"] = event_names
    if years:
        conditions.append("any(yr IN $years WHERE e.tournament_name CONTAINS yr)")
        params["years"] = years
    if character_names:
        conditions.append("c.name IN $character_names")
        params["character_names"] = character_names

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    cypher = f"""
    MATCH (c:Character)<-[:USED_CHARACTER]-(sp:SetPlayer)<-[:HAS_ENTRY]-(s:Set)
    MATCH (s)-[:PLAYED_IN]->(e:Event)
    MATCH (sp)-[:PLAYER]->(p:Player)
    {where_clause}
    WITH c, sp, s, p
    RETURN c.name AS character,
           c.videogame_name AS videogame,
           count(DISTINCT s) AS sets,
           sum(CASE WHEN sp.result = 'win' THEN 1 ELSE 0 END) AS wins,
           count(DISTINCT p) AS unique_players,
           collect(DISTINCT p.gamertag)[0..8] AS sample_players
    ORDER BY wins DESC, sets DESC, character ASC
    LIMIT 25
    """

    try:
        with driver.session() as session:
            rows = session.run(cypher, **params).data()
    except Exception as exc:
        print(f"Neo4j character performance query failed ({exc}); omitting performance context.")
        return ""

    lines = [
        "### Character Performance Data",
        "* Character performance is dynamically computed from set-level character choices recorded in the database.",
    ]

    if not rows:
        lines.extend([
            "* No character performance rows matched the current graph and filters.",
            "* The current Combo Breaker graph has character roster availability, but no character choices have been sync'd or reported for these matches.",
        ])
        return "\n".join(lines)

    lines.append("#### Character Results From Set-level Match Data")
    for idx, row in enumerate(rows, 1):
        sets = row["sets"] or 0
        wins = row["wins"] or 0
        win_rate = (wins / sets * 100) if sets else 0
        players = ", ".join(row["sample_players"] or [])
        lines.append(
            f"{idx}. {row['character']} ({row['videogame']}) - {wins}/{sets} set wins "
            f"({win_rate:.1f}%); unique players: {row['unique_players']}; sample players: {players}"
        )

    return "\n".join(lines)


def get_global_context(
    event_names: list[str] = None,
    years: list[str] = None,
    include_characters: bool = False,
    include_character_performance: bool = False,
    character_names: list[str] = None,
) -> str:
    """Retrieves event summaries, filtering by matched names/years or limiting default ones to save tokens."""
    t0 = time.time()
    _agent_log("neo4j_global_context_start", {"events": event_names, "years": years}, "A_global")
    
    context_lines = []

    if event_names or years:
        conditions = ["e.summary IS NOT NULL"]
        params = {}
        if event_names:
            conditions.append("e.name IN $event_names")
            params["event_names"] = event_names
        if years:
            conditions.append("any(yr IN $years WHERE e.tournament_name CONTAINS yr)")
            params["years"] = years

        cypher = f"""
        MATCH (e:Event)
        WHERE {" AND ".join(conditions)}
        RETURN e.tournament_name AS tournament, e.summary AS summary
        """
    else:
        # Default: limit to top 8 events by player count from COMBO BREAKER tournaments (any year)
        cypher = """
        MATCH (e:Event)
        WHERE e.tournament_name STARTS WITH 'COMBO BREAKER' AND e.summary IS NOT NULL
        OPTIONAL MATCH (p:Player)-[:PARTICIPATED_IN]->(e)
        WITH e, count(p) AS player_count
        RETURN e.tournament_name AS tournament, e.summary AS summary
        ORDER BY player_count DESC
        LIMIT 8
        """
        params = {}

    try:
        with driver.session() as session:
            res = session.run(cypher, **params)
            for record in res:
                tourney = record["tournament"] or "Unknown Tournament"
                summary = record["summary"]
                # Prepend tournament info to the summary
                context_lines.append(f"## TOURNAMENT: {tourney}\n{summary}")
    except Exception as exc:
        print(f"Neo4j query failed ({exc}); returning empty context.")
        _agent_log("neo4j_global_context_fallback", {"error": str(exc)}, "A_global")
        return ""

    if not context_lines:
        print("No event summaries found in Neo4j.")

    # Fetch top players by wins for the specific events/years
    if event_names or years:
        conditions_wins = []
        params_wins = {}
        if event_names:
            conditions_wins.append("e.name IN $event_names")
            params_wins["event_names"] = event_names
        if years:
            conditions_wins.append("any(yr IN $years WHERE e.tournament_name CONTAINS yr)")
            params_wins["years"] = years

        where_clause = "WHERE " + " AND ".join(conditions_wins) if conditions_wins else ""
        cypher_wins = f"""
        MATCH (s:Set)-[:PLAYED_IN]->(e:Event)
        {where_clause}
        MATCH (s)-[:PLAYER1|PLAYER2]->(p:Player)
        WHERE s.winner_id = p.id
        RETURN p.gamertag AS name, count(s) AS wins
        ORDER BY wins DESC
        LIMIT 10
        """
        try:
            with driver.session() as session:
                wins_res = session.run(cypher_wins, **params_wins)
                filtered_wins = [f"{r['name']} ({r['wins']} wins)" for r in wins_res]
                if filtered_wins:
                    years_str = f" for {', '.join(years)}" if years else ""
                    events_str = f" in {', '.join(event_names)}" if event_names else ""
                    context_lines.append(
                        f"### Top Players by Wins{years_str}{events_str}\n"
                        f"* {', '.join(filtered_wins)}"
                    )
        except Exception as exc:
            print(f"Neo4j wins query failed ({exc}); omitting filtered wins from context.")

    if include_character_performance:
        performance_context = get_character_performance_context(
            event_names=event_names,
            years=years,
            character_names=character_names,
        )
        if performance_context:
            context_lines.append(performance_context)

    if include_characters:
        character_context = get_character_context(event_names=event_names, years=years)
        if character_context:
            context_lines.append(character_context)

    context_str = "\n\n".join(context_lines)
    _agent_log(
        "neo4j_global_context_done",
        {"line_count": len(context_lines), "elapsed_ms": int((time.time() - t0) * 1000)},
        "A_global",
    )
    return context_str


# Keep get_tournament_context as a fallback wrapper
def get_tournament_context():
    return get_global_context()


_DATABASE_METADATA_CACHE = None

def clear_database_metadata_cache():
    global _DATABASE_METADATA_CACHE
    _DATABASE_METADATA_CACHE = None

def get_database_metadata() -> str:
    global _DATABASE_METADATA_CACHE
    if _DATABASE_METADATA_CACHE is not None:
        return _DATABASE_METADATA_CACHE
        
    try:
        with driver.session() as session:
            # Fetch unique tournaments
            tourneys_res = session.run("MATCH (e:Event) WHERE e.tournament_name IS NOT NULL RETURN DISTINCT e.tournament_name AS name ORDER BY name")
            tourneys = [r["name"] for r in tourneys_res]
            
            # Fetch unique games
            games_res = session.run("MATCH (e:Event) WHERE e.name IS NOT NULL RETURN DISTINCT e.name AS name ORDER BY name")
            games = [r["name"] for r in games_res]

            character_games_res = session.run(
                """
                MATCH (c:Character)
                WHERE c.videogame_name IS NOT NULL
                RETURN c.videogame_name AS game, count(DISTINCT c) AS characters
                ORDER BY game
                """
            )
            character_games = [
                f"{r['game']} ({r['characters']} characters)"
                for r in character_games_res
            ]

            # Fetch top 10 players by wins (Global)
            wins_res = session.run(
                """
                MATCH (p:Player)
                WHERE p.wins IS NOT NULL AND p.wins > 0
                RETURN p.gamertag AS name, p.wins AS wins, coalesce(p.losses, 0) AS losses
                ORDER BY wins DESC
                LIMIT 10
                """
            )
            top_wins = [f"{r['name']} ({r['wins']}W-{r['losses']}L)" for r in wins_res]

            # Fetch top 10 players by rating (Global)
            ratings_res = session.run(
                """
                MATCH (p:Player)
                WHERE p.rating IS NOT NULL
                RETURN p.gamertag AS name, p.rating AS rating
                ORDER BY rating DESC
                LIMIT 10
                """
            )
            top_ratings = [f"{r['name']} (Rating: {r['rating']})" for r in ratings_res]
        
        metadata_lines = [
            "### DATABASE METADATA",
            f"* **Available Tournaments**: {', '.join(tourneys)}",
            f"* **Available Games**: {', '.join(games)}",
            f"* **Games With Character Rosters**: {', '.join(character_games)}",
        ]
        if top_wins:
            metadata_lines.append(f"* **Top 10 Players by Wins (Global)**: {', '.join(top_wins)}")
        if top_ratings:
            metadata_lines.append(f"* **Top 10 Highest Rated Players (Global)**: {', '.join(top_ratings)}")
        metadata_lines.append("")

        _DATABASE_METADATA_CACHE = "\n".join(metadata_lines)
    except Exception as e:
        print(f"Error fetching database metadata: {e}")
        _DATABASE_METADATA_CACHE = ""
        
    return _DATABASE_METADATA_CACHE


def build_rag_context(question: str) -> tuple[str, str]:
    """Detects players/events/years and builds context + commentator persona prompt."""
    mentioned_players = detect_mentioned_players(question)
    mentioned_events = detect_mentioned_events(question)
    mentioned_years = detect_mentioned_years(question)
    mentioned_characters = detect_mentioned_characters(question)
    include_characters = is_character_question(question)
    include_character_performance = is_character_performance_question(question)
    if include_character_performance and mentioned_characters:
        mentioned_players = []

    if mentioned_players:
        print(f"Routing to Local Search (Players detected: {mentioned_players})")
        _agent_log("routing_local", {"detected_players": mentioned_players, "question": question}, "routing")
        tournament_data = get_local_context(mentioned_players)
        if include_character_performance:
            performance_context = get_character_performance_context(
                event_names=mentioned_events,
                years=mentioned_years,
                character_names=mentioned_characters,
            )
            if performance_context:
                tournament_data = f"{tournament_data}\n\n{performance_context}" if tournament_data else performance_context
        if include_characters and (mentioned_events or mentioned_years):
            character_context = get_character_context(event_names=mentioned_events, years=mentioned_years)
            if character_context:
                tournament_data = f"{tournament_data}\n\n{character_context}" if tournament_data else character_context
    else:
        print(f"Routing to Global Search (Events: {mentioned_events}, Years: {mentioned_years})")
        _agent_log(
            "routing_global",
            {"question": question, "events": mentioned_events, "years": mentioned_years},
            "routing"
        )
        tournament_data = get_global_context(
            event_names=mentioned_events,
            years=mentioned_years,
            include_characters=include_characters,
            include_character_performance=include_character_performance,
            character_names=mentioned_characters,
        )

    # Prepend database metadata so the model always knows which tournaments/games are available
    db_metadata = get_database_metadata()
    if db_metadata:
        tournament_data = db_metadata + "\n" + tournament_data

    system_message = """
### PERSONA
You are the Voice of Combo Breaker (covering 2022 - 2026)—a high-energy, elite esports commentator. You transform raw tournament data into legendary narratives with punchy, evocative verbs.

### COMMENTARY DIRECTIVES
1. Hype Dial: Use high-energy verbs (Ascended, Dismantled, Clutched, Decimated) and stage atmosphere details.
2. Data Integrity: You are strictly forbidden from inventing winners.
3. Elo Ratings: Highlight rivalries between similarly rated players. Crucially, you must ONLY identify a match as an upset when the data explicitly shows a lower-rated player defeating a higher-rated player.
4. Character Data: Character nodes represent playable rosters for an event/game. Treat "most prominent character" as roster availability across the matched events unless the context explicitly provides usage, pick, main, or performance data.
5. Character Performance: Only discuss character performance, win rates, strongest characters, or weakest characters from the "Character Performance Data" section. If that section says no performance rows exist, clearly say the current graph cannot measure character performance yet because player-character or set-level pick data is missing.
6. Player Mains: Do not infer a player's main from general knowledge, popularity, nationality, team, match wins, or roster availability. Only answer player-main or character-pick questions when the context includes an explicit Player->Character relationship or set-level character selection. If that data is absent, say the graph does not currently store that information.
7. Output: Do not show analysis steps, just provide the hype narrative output. Do not use markdown bold (**) in the output.
"""
    return tournament_data, system_message


def _message_text_from_chat_output(out) -> str:
    """Extract assistant text from chat_completion (handles some TGI/Qwen variants)."""
    if not getattr(out, "choices", None):
        return ""
    msg = out.choices[0].message
    text = (getattr(msg, "content", None) or "").strip()
    if text:
        return text
    for attr in ("reasoning_content", "reasoning"):
        alt = getattr(msg, attr, None)
        if alt:
            return f"[Thinking Process]\n{str(alt).strip()}"
    return ""


def _call_deepseek_chat_completion(system_message: str, user_message: str, start_time: float, question: str, tournament_data: str) -> str:
    """Call DeepSeek's OpenAI-compatible chat completions API."""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    candidate_urls = [
        f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
        f"{DEEPSEEK_BASE_URL}/chat/completions",
    ]

    last_error = None
    for url in candidate_urls:
        for attempt in range(1, 6):
            request_timeout = 30.0

            payload = {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.4,
                "max_tokens": 1500,
                "stream": False,
            }

            try:
                response = requests.post(url, headers=headers, json=payload, timeout=request_timeout)
                if response.status_code in (429, 503):
                    wait = min(2 * attempt, 10)
                    print(f"  [WAIT] DeepSeek returned {response.status_code}, retry {attempt}/5 in {wait}s...")
                    time.sleep(wait)
                    continue
                if 400 <= response.status_code < 500:
                    print(f"  [ERROR] DeepSeek returned client error {response.status_code} for URL {url}. Skipping retries.")
                    last_error = requests.exceptions.HTTPError(response=response)
                    break
                response.raise_for_status()
                data = response.json()
                
                # Check for error in JSON response
                if "error" in data:
                    print(f"  [ERROR] DeepSeek API returned JSON error: {data['error']}. Skipping retries.")
                    raise NonRetryableError(f"DeepSeek API error: {data['error']}")
                    
                choices = data.get("choices") or []
                if not choices:
                    print("  [ERROR] DeepSeek response did not include choices. Skipping retries.")
                    raise NonRetryableError(f"DeepSeek response did not include choices: {data}")
                    
                message = choices[0].get("message") or {}
                text = (message.get("content") or "").strip()
                if not text:
                    # Sometimes content is empty but reasoning is present. If neither is present, it's an error.
                    reasoning = ""
                    for attr in ("reasoning_content", "reasoning"):
                        if attr in message and message[attr]:
                            reasoning = str(message[attr]).strip()
                            break
                    if reasoning:
                        text = f"[Thinking Process]\n{reasoning}"
                    else:
                        print("  [ERROR] DeepSeek response did not include message content. Skipping retries.")
                        raise NonRetryableError("DeepSeek response did not include message content")
                return text
            except NonRetryableError as exc:
                last_error = exc
                break
            except Exception as exc:
                last_error = exc
                if attempt < 5:
                    wait = min(2 * attempt, 10)
                    print(f"  [WAIT] DeepSeek connection error ({type(exc).__name__}), retry {attempt}/5 in {wait}s...")
                    time.sleep(wait)
                    continue
                break

    raise RuntimeError(f"DeepSeek chat completion failed: {last_error}")


def _call_deepseek_chat_completion_stream(system_message: str, user_message: str, start_time: float, question: str, tournament_data: str):
    """Yield DeepSeek chat tokens from the streaming API."""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    candidate_urls = [
        f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
        f"{DEEPSEEK_BASE_URL}/chat/completions",
    ]

    last_error = None
    stream_succeeded = False

    for url in candidate_urls:
        if stream_succeeded:
            break
        for attempt in range(1, 6):
            request_timeout = 30.0

            payload = {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.4,
                "max_tokens": 1500,
                "stream": True,
            }

            try:
                response = requests.post(url, headers=headers, json=payload, stream=True, timeout=request_timeout)
                if response.status_code in (429, 503):
                    wait = min(2 * attempt, 10)
                    print(f"  [WAIT] DeepSeek returned {response.status_code}, retry {attempt}/5 in {wait}s...")
                    time.sleep(wait)
                    continue
                if 400 <= response.status_code < 500:
                    print(f"  [ERROR] DeepSeek returned client error {response.status_code} for URL {url}. Skipping retries.")
                    last_error = requests.exceptions.HTTPError(response=response)
                    break
                response.raise_for_status()
                has_started_reasoning = False
                has_generated_any_content = False
                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    raw_line_stripped = raw_line.strip()
                    if not raw_line_stripped:
                        continue
                    if raw_line_stripped == "data: [DONE]":
                        stream_succeeded = True
                        return
                    if not raw_line_stripped.startswith("data: "):
                        # check if it is a JSON error
                        try:
                            err_data = json.loads(raw_line_stripped)
                            if "error" in err_data:
                                print(f"  [ERROR] DeepSeek streaming returned JSON error: {err_data['error']}. Skipping retries.")
                                raise NonRetryableError(f"DeepSeek API error: {err_data['error']}")
                        except json.JSONDecodeError:
                            pass
                        continue
                    chunk = json.loads(raw_line_stripped[6:].strip())
                    if "error" in chunk:
                        print(f"  [ERROR] DeepSeek streaming returned JSON error: {chunk['error']}. Skipping retries.")
                        raise NonRetryableError(f"DeepSeek API error: {chunk['error']}")
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content") or ""
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                    if reasoning:
                        if not has_started_reasoning:
                            has_started_reasoning = True
                            yield "[Thinking Process]\n"
                        yield reasoning
                    elif text:
                        if has_started_reasoning:
                            has_started_reasoning = False
                            yield "\n\n[Answer]\n"
                        has_generated_any_content = True
                        yield text
                stream_succeeded = True
                return
            except NonRetryableError as exc:
                last_error = exc
                break
            except Exception as exc:
                last_error = exc
                if attempt < 5:
                    wait = min(2 * attempt, 10)
                    print(f"  [WAIT] DeepSeek connection error ({type(exc).__name__}), retry {attempt}/5 in {wait}s...")
                    time.sleep(wait)
                    continue
                break

    if not stream_succeeded:
        print(f"Streaming failed or skipped (error: {last_error}). Falling back to non-streaming...")
        try:
            ans = _call_deepseek_chat_completion(system_message, user_message, start_time, question, tournament_data)
            yield ans
        except Exception as exc:
            raise RuntimeError(f"DeepSeek chat completion streaming and fallback both failed. Streaming error: {last_error}. Fallback error: {exc}")


# Hugging Face inference logic removed


def generate_answer(question):
    start_time = time.time()
    print("Fetching graph data...")
    tournament_data, system_message = build_rag_context(question)

    provider = CHAT_PROVIDER
    use_deepseek = provider in {"deepseek", "auto"} and bool(DEEPSEEK_API_KEY)

    if use_deepseek:
        user_message = (
            f"TOURNAMENT DATA:\n{tournament_data}\n\nUSER QUESTION:\n{question}\n\n"
            "Provide a hyper-concise hype summary (max 3 sentences) based only on the data above."
        )
        print("Calling DeepSeek Inference...")
        _agent_log(
            "deepseek_chat_start",
            {"model": DEEPSEEK_MODEL, "tournament_chars": len(tournament_data), "question_chars": len(question)},
            "B",
        )
        t1 = time.time()
        try:
            text = _call_deepseek_chat_completion(system_message, user_message, start_time, question, tournament_data)
            elapsed = time.time() - t1
            print(f"DeepSeek latency: {elapsed:.2f}s ({elapsed/60:.1f} min)")
            _agent_log(
                "deepseek_chat_done",
                {"answer_chars": len(text), "elapsed_ms": int((time.time() - t1) * 1000)},
                "D",
            )
            return text, tournament_data, system_message
        except Exception as exc:
            print(f"DeepSeek inference failed ({exc}); returning error.")
            _agent_log("deepseek_chat_failed", {"error": str(exc)}, "C")
            return f"Error: DeepSeek inference failed: {exc}", tournament_data, system_message

    print("Chat provider not configured for DeepSeek.")
    return "Error: No chat provider configured (DEEPSEEK_API_KEY is missing).", tournament_data, system_message


def generate_answer_stream(question):
    """Stream the generated answer as newline-delimited JSON events, enforcing a time budget."""
    start_time = time.time()
    yield _json_line("status", text="Reading bracket data...")
    print("Fetching graph data...")
    tournament_data, system_message = build_rag_context(question)

    user_message = (
        f"TOURNAMENT DATA:\n{tournament_data}\n\nUSER QUESTION:\n{question}\n\n"
        "Provide a hyper-concise hype summary (max 3 sentences) based only on the data above."
    )

    provider = CHAT_PROVIDER
    use_deepseek = provider in {"deepseek", "auto"} and bool(DEEPSEEK_API_KEY)

    if use_deepseek:
        yield _json_line("status", text="Generating answer...")
        print("Calling DeepSeek Inference (streaming)...")
        _agent_log(
            "deepseek_chat_start",
            {
                "model": DEEPSEEK_MODEL,
                "tournament_chars": len(tournament_data),
                "question_chars": len(question),
                "streaming": True,
            },
            "B",
        )
        t1 = time.time()
        try:
            for token in _call_deepseek_chat_completion_stream(system_message, user_message, start_time, question, tournament_data):
                yield _json_line("delta", text=token)
            elapsed_ms = int((time.time() - t1) * 1000)
            _agent_log(
                "deepseek_chat_done",
                {"answer_chars": 0, "elapsed_ms": elapsed_ms, "streaming": True},
                "D",
            )
            yield _json_line("done", elapsed_ms=elapsed_ms)
            yield _json_line(
                "meta",
                context=tournament_data,
                system_prompt=system_message,
                provider=provider,
            )
            return
        except Exception as exc:
            _agent_log("deepseek_chat_failed", {"error": str(exc), "streaming": True}, "C")
            print(f"DeepSeek streaming failed ({exc}); returning error.")
            yield _json_line("delta", text=f"Error: DeepSeek streaming failed: {exc}")
            yield _json_line("done", elapsed_ms=int((time.time() - t1) * 1000), fallback=True)
            yield _json_line(
                "meta",
                context=tournament_data,
                system_prompt=system_message,
                provider=provider,
            )
            return

    yield _json_line("delta", text="Error: No chat provider configured (DEEPSEEK_API_KEY is missing).")
    yield _json_line("done", elapsed_ms=0, fallback=True)
    yield _json_line(
        "meta",
        context=tournament_data,
        system_prompt=system_message,
        provider=provider,
    )


if __name__ == "__main__":
    user_query = "Were there any upsets in the tournament?"
    answer, context, prompt = generate_answer(user_query)

    print("\n--- Final Answer ---")
    try:
        print(answer)
    except UnicodeEncodeError:
        print(answer.encode('ascii', errors='replace').decode('ascii'))
    print("\n--- Context ---")
    try:
        print(context[:200] + "...")
    except UnicodeEncodeError:
        print(context[:200].encode('ascii', errors='replace').decode('ascii') + "...")
