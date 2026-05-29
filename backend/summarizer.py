import logging
from database import get_session
from constants import DEFAULT_ELO_RATING

logger = logging.getLogger(__name__)

def run_summarizer():
    """Programmatically aggregates event statistics and writes a summary property to Event nodes."""
    logger.info("Starting Event Community Summarizer...")
    session = get_session()

    try:
        # 1. Fetch all active events
        events_res = session.run("MATCH (e:Event) WHERE e.id IS NOT NULL RETURN e.id AS id, e.name AS name")
        events = [{"id": record["id"], "name": record["name"]} for record in events_res]

        for event in events:
            event_id = event["id"]
            event_name = event["name"]

            logger.info(f"Summarizing event: {event_name} (ID: {event_id})...")

            # 2. Get total player count
            player_count_res = session.run(
                "MATCH (p:Player)-[:PARTICIPATED_IN]->(e:Event {id: $event_id}) RETURN count(p) AS count",
                event_id=event_id
            )
            total_players = player_count_res.single()["count"]

            # 3. Get total matches (sets) count
            sets_count_res = session.run(
                "MATCH (s:Set)-[:PLAYED_IN]->(e:Event {id: $event_id}) RETURN count(s) AS count",
                event_id=event_id
            )
            total_sets = sets_count_res.single()["count"]

            # 4. Get top 5 players by rating
            top_players_res = session.run(
                """
                MATCH (p:Player)-[:PARTICIPATED_IN]->(e:Event {id: $event_id})
                RETURN p.gamertag AS gamertag, coalesce(p.rating, $default_rating) AS rating
                ORDER BY rating DESC LIMIT 5
                """,
                event_id=event_id,
                default_rating=DEFAULT_ELO_RATING,
            )
            top_players = [{"gamertag": r["gamertag"], "rating": r["rating"]} for r in top_players_res]

            # 5. Resolve champion (winner of the latest match)
            champion_res = session.run(
                """
                MATCH (s:Set)-[:PLAYED_IN]->(e:Event {id: $event_id})
                MATCH (w:Player {id: s.winner_id})
                RETURN w.gamertag AS champion
                ORDER BY s.completed_at DESC LIMIT 1
                """,
                event_id=event_id
            )
            champion_record = champion_res.single()
            champion = champion_record["champion"] if champion_record else "Unknown / Still in progress"

            # 6. Calculate top upsets
            upsets_res = session.run(
                """
                MATCH (s:Set)-[:PLAYED_IN]->(e:Event {id: $event_id})
                MATCH (s)-[:PLAYER1]->(p1:Player)
                MATCH (s)-[:PLAYER2]->(p2:Player)
                WHERE s.winner_id IS NOT NULL
                RETURN p1.id AS p1_id, p1.gamertag AS p1_name, coalesce(p1.rating, $default_rating) AS p1_rating,
                       p2.id AS p2_id, p2.gamertag AS p2_name, coalesce(p2.rating, $default_rating) AS p2_rating,
                       s.winner_id AS winner_id
                """,
                event_id=event_id,
                default_rating=DEFAULT_ELO_RATING,
            )

            all_upsets = []
            for r in upsets_res:
                p1_won = (r["winner_id"] == r["p1_id"])
                winner_name = r["p1_name"] if p1_won else r["p2_name"]
                winner_rating = r["p1_rating"] if p1_won else r["p2_rating"]
                loser_name = r["p2_name"] if p1_won else r["p1_name"]
                loser_rating = r["p2_rating"] if p1_won else r["p1_rating"]

                if winner_rating < loser_rating:
                    diff = loser_rating - winner_rating
                    all_upsets.append({
                        "winner": winner_name,
                        "winner_rating": winner_rating,
                        "loser": loser_name,
                        "loser_rating": loser_rating,
                        "diff": diff
                    })

            # Sort by rating difference descending and take top 10
            all_upsets.sort(key=lambda x: x["diff"], reverse=True)
            top_upsets = all_upsets[:10]

            # 7. Assemble markdown summary
            lines = [
                f"### Event Summary: {event_name}",
                f"* **Total Players**: {total_players}",
                f"* **Total Sets Played**: {total_sets}",
                f"* **Champion**: {champion}",
                "",
                "#### Top 5 Rated Players",
            ]
            for idx, p in enumerate(top_players, 1):
                lines.append(f"{idx}. {p['gamertag']} (Rating: {p['rating']})")

            lines.append("")
            lines.append("#### Top Upsets (Underdog defeats Favorite)")
            if top_upsets:
                for u in top_upsets:
                    lines.append(f"* {u['winner']} (Rating: {u['winner_rating']}) defeated {u['loser']} (Rating: {u['loser_rating']}) (Rating Diff: {u['diff']})")
            else:
                lines.append("* No upsets recorded.")

            summary_str = "\n".join(lines)

            # 8. Write summary property back to the Event node
            session.run(
                """
                MATCH (e:Event {id: $event_id})
                SET e.summary = $summary
                """,
                event_id=event_id,
                summary=summary_str
            )
            logger.info(f"Summary written for event: {event_name}")

    except Exception as e:
        logger.error(f"Error generating event summaries: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_summarizer()
