import requests
from models import Player
from database import supabase

def get_all_player_sets(player_id: int):
    # This function is a placeholder for fetching all sets of a player from the database

    sets = supabase.table('sets').select('*').eq('player_id', player_id).execute()
    player_sets = sets.data
    return player_sets

def get_all__sets():
    # This function is a placeholder for fetching all sets of a player from the database
    sets = supabase.table('sets').select('*').execute()
    setData = sets.data
    return setData

# This function calculates the rating of a player based on their sets. It can be called when a new set is added or when we want to recalculate the rating from scratch.
def CalculateRatingFromScratch():
    sets = get_all__sets()
    total_sets = len(sets)
    wins = 0

    for s in sets:
        p1 = s["player1_id"]
        p2 = s["player2_id"]
        winner = s["winnerid"]

        player1 = supabase.table('players').select('*').eq('id', p1).execute().data[0]
        player2 = supabase.table('players').select('*').eq('id', p2).execute().data[0]
        if winner == p1:
            wins += 1
            # Update player1 rating
            new_rating = calculate_new_rating(player1['rating'], player2['rating'], True)
            supabase.table('players').update({'rating': new_rating}).eq('id', p1).execute()
            # Update player2 rating
            new_rating = calculate_new_rating(player2['rating'], player1['rating'], False)
            supabase.table('players').update({'rating': new_rating}).eq('id', p2).execute()
        elif winner == p2:
            # Update player1 rating
            new_rating = calculate_new_rating(player1['rating'], player2['rating'], False)
            supabase.table('players').update({'rating': new_rating}).eq('id', p1).execute()
            # Update player2 rating
            new_rating = calculate_new_rating(player2['rating'], player1['rating'], True)
            supabase.table('players').update({'rating': new_rating}).eq('id', p2).execute()
    print(f"Calculated ratings for {total_sets} sets with {wins} wins.")

def calculate_new_rating(player_rating, opponent_rating, did_win):
    # This function is for calculating the new rating of a player based on the Elo rating system. It takes the player's current rating, the opponent's rating, and whether the player won or lost the set as input and returns the new rating.
    K = 32  # K-factor for Elo rating system
    expected_score = 1 / (1 + 10 ** ((opponent_rating - player_rating) / 400))
    actual_score = 1 if did_win else 0
    new_rating = player_rating + K * (actual_score - expected_score)
    return round(new_rating)

if __name__ == "__main__":
    CalculateRatingFromScratch()

#need to grab all the sets in the database and calculate the rating for each player based on their wins and losses against other players. This can be done by iterating through all the sets and updating the ratings of the players involved in each set using a rating algorithm like Elo or Glicko.
#should be sorted by least recent sets first, so we can calculate the ratings in the correct order. We can also add a timestamp to each set to keep track of when it was played and use that to sort the sets.
