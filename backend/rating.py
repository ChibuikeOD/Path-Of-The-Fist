import math
from database import get_session
from constants import DEFAULT_ELO_RATING

def get_all_sets_paginated():
    """
    Fetches every set from the database in chronological order.
    """
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
        ORDER BY s.completed_at ASC
        """
    )
    all_sets = [record["set_result"] for record in result]
    session.close()
    return all_sets

def calculate_new_rating(player_rating, opponent_rating, did_win):
    """
    Standard Elo formula.
    """
    K = 32  # Standard K-factor
    expected_score = 1 / (1 + 10 ** ((opponent_rating - player_rating) / 400))
    actual_score = 1 if did_win else 0
    new_rating = player_rating + K * (actual_score - expected_score)
    return round(new_rating)

def CalculateRatingFromScratch():
    session = get_session()
    
    # 1. Pull ALL players into memory 
    print("Caching players...")
    players_result = session.run(
        """
        MATCH (p:Player)
        WHERE p.id IS NOT NULL AND p.gamertag IS NOT NULL
        RETURN {id: p.id, gamertag: p.gamertag, rating: p.rating} AS player
        """
    )
    
    # Dictionary for O(1) lookups: {id: {player_obj}}
    player_cache = {}
    for record in players_result:
        player = record["player"]
        if not player:
            continue
        # Rebuild the ladder from a clean baseline each time.
        player["rating"] = DEFAULT_ELO_RATING
        player_cache[player.get("id")] = player
    
    
    # 2. Get all sets 
    print("Fetching sets in chronological order...")
    sets = get_all_sets_paginated()
    
    if not sets:
        print("No sets found in database.")
        return

    print(f"Calculating ratings for {len(sets)} sets...")
    
    for s in sets:
        p1_id = s["player1_id"]
        p2_id = s["player2_id"]
        winner_id = s["winner_id"]

        # Safety check: ensure both players exist in cache
        p1 = player_cache.get(p1_id)
        p2 = player_cache.get(p2_id)
        
        if not p1 or not p2 or winner_id is None:
            continue

        # Current ratings from cache
        r1 = p1["rating"]
        r2 = p2["rating"]

        # Determine win/loss
        p1_won = (winner_id == p1_id)

        # Update cache with new ratings
        p1['rating'] = calculate_new_rating(r1, r2, p1_won)
        p2['rating'] = calculate_new_rating(r2, r1, not p1_won)

    # 3. Bulk update back to Neo4j
    print("Updating database with final ratings...")
    final_players = list(player_cache.values())
    
    # Chunking the upsert to prevent payload size errors on massive player lists
    chunk_size = 500
    for i in range(0, len(final_players), chunk_size):
        chunk = final_players[i : i + chunk_size]
        session.run(
            "UNWIND $players AS p MATCH (node:Player {id: p.id}) SET node.rating = p.rating",
            players=chunk
        )
        
    session.close()

    print(f"Elo sync complete. Processed {len(sets)} matches.")

if __name__ == "__main__":
    CalculateRatingFromScratch()
