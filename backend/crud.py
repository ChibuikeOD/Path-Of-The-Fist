import requests
from models import Player
from database import supabase


headers =  { "Authorization": "Bearer 9fc2cfc179ba7fb1bd55d055c4b86444" }
URL = "https://api.start.gg/gql/alpha"

def get_combo_breaker_sets_by_id(player_id: int):
    current_page = 1
    total_pages = 1
    per_page = 50
    gamer_tag = "Unknown"
    event_id = "1287308"

    query = """
    query PlayerSetHistory($playerId: ID!, $eventId: [ID], $page: Int!, $perPage: Int!){
        player(id: $playerId){
            gamerTag
            sets(page: $page, perPage: $perPage, filters: { eventIds: $eventId }){
                pageInfo { totalPages }
                nodes{
                    id
                    winnerId
                    slots{
                        entrant {
                            id # THIS is the Entrant ID that matches winnerId
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

    while current_page <= total_pages:
        variables = {
            "playerId": player_id, 
            "page": current_page, 
            "perPage": per_page, 
            "eventId": [event_id] 
        }
        
        try:
            response = requests.post(URL, json={"query": query, "variables": variables}, headers=headers)
            res_json = response.json()
            player_node = res_json.get("data", {}).get("player")

            if not player_node: break
            
            gamer_tag = player_node['gamerTag']
            sets_data = player_node.get("sets", {})
            total_pages = sets_data.get("pageInfo", {}).get("totalPages", 1)
            nodes = sets_data.get("nodes", [])

            batch_sets = []
            unique_players = {}

            for s in nodes:
                slots = s.get("slots") or []
                if len(slots) < 2: continue 

                winner_entrant_id = s.get("winnerId")
                
                # Get Entrant and Player data for both slots
                ent1 = slots[0].get("entrant")
                ent2 = slots[1].get("entrant")

                if ent1 and ent2:
                    p1_data = ent1.get("participants", [{}])[0].get("player")
                    p2_data = ent2.get("participants", [{}])[0].get("player")
                    
                    if p1_data and p2_data:
                        # RESOLUTION LOGIC: Compare winnerId to Entrant IDs
                        resolved_winner_player_id = None
                        
                        # Use str() to ensure the comparison doesn't fail on type mismatch
                        if str(winner_entrant_id) == str(ent1.get("id")):
                            resolved_winner_player_id = p1_data["id"]
                        elif str(winner_entrant_id) == str(ent2.get("id")):
                            resolved_winner_player_id = p2_data["id"]

                        batch_sets.append({
                            "id": s["id"],
                            "player1_id": p1_data["id"],
                            "player2_id": p2_data["id"],
                            "winnerid": resolved_winner_player_id 
                        })
                        
                        unique_players[p1_data["id"]] = {"id": p1_data["id"], "gamertag": p1_data["gamerTag"]}
                        unique_players[p2_data["id"]] = {"id": p2_data["id"], "gamertag": p2_data["gamerTag"]}

            # Batch Upsert
            if unique_players:
                supabase.table("players").upsert(list(unique_players.values())).execute()
            if batch_sets:
                supabase.table("sets").upsert(batch_sets).execute()
                print(f"Page {current_page}: Synced {len(batch_sets)} sets for {gamer_tag}")

            current_page += 1
        except Exception as e:
            print(f"Error: {str(e)}")
            break

    return gamer_tag

#this is tbe function i used for inserting players into the database, it is not used for anything else but i left ii in for reference purposes.
# It is not currently being called anywhere in the codebase.
def get_players_by_event():

    slug = "tournament/combo-breaker-2025/event/street-fighter-6"
    per_page = 100 # Lower perPage is safer for the Alpha API to avoid timeouts
    current_page = 1
    total_pages = 1 

    query = """
    query getPlayersByEvent($slug: String!, $page: Int!, $perPage: Int!) {
      event(slug: $slug) {
        entrants(query: { page: $page, perPage: $perPage }) {
          pageInfo {
            totalPages
            total
          }
          nodes {
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
    """

    while current_page <= total_pages:
        variables = {
            "slug": slug,
            "page": current_page,
            "perPage": per_page
        }

        response = requests.post(URL, json={"query": query, "variables": variables}, headers=headers)
        
        if response.status_code != 200:
            print(f"Error on page {current_page}: {response.text}")
            break

        res_json = response.json()
        data = res_json.get("data")
        
        if not data or not data.get("event"):
            print(f"No data returned for page {current_page}. Errors: {res_json.get('errors')}")
            break

        entrants_data = data["event"]["entrants"]
        total_pages = entrants_data["pageInfo"]["totalPages"]
        player_nodes = entrants_data["nodes"]

        # 1. Parse the list efficiently
        player_data = []
        for node in player_nodes:
            participants = node.get("participants") or []
            if participants and participants[0].get("player"):
                p = participants[0]["player"]
                player_data.append({
                    "id": p["id"],
                    "gamertag": p["gamerTag"]
                })

        # 2. Batch Upsert to Supabase
        if player_data:
            try:
                supabase.table("players").upsert(player_data).execute()
                print(f"Page {current_page}/{total_pages}: Upserted {len(player_data)} players.")
            except Exception as e:
                print(f"Supabase Error on page {current_page}: {str(e)}")

        current_page += 1

    return "Import Complete"

def populate_player_sets():
    players = supabase.table("players").select("id").execute().data
    
    for player in players:
        player_id = player["id"]
        try:
            gamerTag = get_combo_breaker_sets_by_id(player_id)
            print(f"Player ID {player_id} has gamerTag: {gamerTag}")
        except Exception as e:
            print(f"Error fetcing sets for player ID {player_id}: {str(e)}")

if __name__ == "__main__":
    results = populate_player_sets()
    print(results)

