import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import pipeline
from scrapers import llm


def film(title, **fields):
    return {"section": "cine", "source": "Cine de prueba", "venue": "Sala", "title": title, **fields}


class StoreEventsTests(unittest.TestCase):
    def setUp(self):
        with patch.object(pipeline, "DB_PATH", ":memory:"):
            self.con = pipeline.init_db()
        self.addCleanup(self.con.close)
        pipeline.store_events(self.con, "cine", [film("Sigue en cartel"), film("Sale de cartel")])
        self.con.execute("UPDATE events SET first_seen='2026-01-01', last_seen='2026-01-02', kids_friendly=1, selective=1, tags_hash='cached'")
        self.con.commit()

    def rows(self):
        return self.con.execute("SELECT * FROM events ORDER BY id").fetchall()

    def test_replacement_preserves_first_seen_and_tags_for_existing_films(self):
        pipeline.store_events(self.con, "cine", [film("Sigue en cartel"), film("Estreno")], replace=True)
        rows = self.con.execute("SELECT title, first_seen, kids_friendly, tags_hash FROM events ORDER BY title").fetchall()
        self.assertEqual(rows, [
            ("Estreno", date.today().isoformat(), None, None),
            ("Sigue en cartel", "2026-01-01", 1, "cached"),
        ])

    def test_invalid_row_rolls_back_deletions_and_partial_updates(self):
        before = self.rows()
        with self.assertRaises(sqlite3.ProgrammingError):
            pipeline.store_events(self.con, "cine", [
                film("Sigue en cartel", description="changed"),
                film("Error", description={"invalid": "not a SQL value"}),
            ], replace=True)
        self.assertEqual(self.rows(), before)
        # A later successful section must not commit leftovers from the failure.
        pipeline.store_events(self.con, "teatro", [{"section": "teatro", "source": "Teatro", "title": "Obra"}])
        cinema = self.con.execute("SELECT * FROM events WHERE section='cine' ORDER BY id").fetchall()
        self.assertEqual(cinema, before)

    def test_changed_description_is_retagged_without_changing_first_seen(self):
        pipeline.store_events(self.con, "cine", [film("Sigue en cartel", description="Nueva descripción")], replace=True)
        self.assertEqual(
            self.con.execute("SELECT first_seen, kids_friendly, selective, tags_hash FROM events").fetchone(),
            ("2026-01-01", None, None, None),
        )

    def test_non_replacing_sections_also_roll_back_partial_writes(self):
        before = self.rows()
        with self.assertRaises(sqlite3.ProgrammingError):
            pipeline.store_events(self.con, "cine", [film("Nueva"), film("Error", description={})])
        self.assertEqual(self.rows(), before)

    def test_confirmed_empty_replacement_clears_only_that_section(self):
        pipeline.store_events(self.con, "teatro", [{"section": "teatro", "source": "Teatro", "title": "Obra"}])
        pipeline.store_events(self.con, "cine", [], replace=True)
        self.assertEqual(self.con.execute("SELECT title FROM events").fetchall(), [("Obra",)])

    def test_duplicate_entries_merge_nonempty_details(self):
        pipeline.store_events(self.con, "cine", [film("Estreno"), film("Estreno", description="Descripción")], replace=True)
        self.assertEqual(self.con.execute("SELECT title, description FROM events").fetchall(), [("Estreno", "Descripción")])


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 11)


class DateTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(llm, "date", FixedDate)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cross_year_exhibition_moves_end_to_next_year(self):
        event = llm.sanitize_dates({"date_start": "2026-07-09", "date_end": "2026-01-10"})
        self.assertEqual(event["date_end"], "2027-01-10")

    def test_old_end_date_is_discarded_if_one_year_is_not_enough(self):
        event = llm.sanitize_dates({"date_start": "2026-07-09", "date_end": "2024-10-10"})
        self.assertEqual(event["date_start"], "2026-07-09")
        self.assertIsNone(event["date_end"])

    def test_invalid_dates_do_not_discard_the_event(self):
        event = llm.sanitize_dates({"title": "Exposición", "date_start": "2026-02-30", "date_end": "wrong"})
        self.assertEqual(event, {"title": "Exposición", "date_start": None, "date_end": None})


if __name__ == "__main__":
    unittest.main()
