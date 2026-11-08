"""Extracción con claude -p, enlaces propios, publicación por fuente y portada.

Sin red ni modelo: claude_json y subprocess se sustituyen.
"""

import json
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import curate
import pipeline
from scrapers import llm, tagger
from scrapers.llm import Fuente


def db():
    with patch.object(pipeline, "DB_PATH", ":memory:"):
        return pipeline.init_db()


class ClaudeCommandTests(unittest.TestCase):
    def test_runs_claude_p_without_tools_and_returns_structured_output(self):
        reply = json.dumps({"is_error": False, "structured_output": {"events": []}})
        with patch.object(llm.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = reply
            self.assertEqual(llm.claude_json("hola", {"type": "object"}), {"events": []})
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[1], "-p")
        for flag in ("--json-schema", "--no-session-persistence", "--strict-mcp-config"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertEqual(run.call_args.kwargs["input"], "hola")

    def test_error_reply_raises(self):
        with patch.object(llm.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps({"is_error": True, "result": "límite"})
            with self.assertRaises(llm.ClaudeError):
                llm.claude_json("hola", {})

    def test_no_anthropic_sdk(self):
        source = (llm.ROOT / "scrapers" / "llm.py").read_text() + (llm.ROOT / "requirements.txt").read_text()
        self.assertNotIn("import anthropic", source)
        self.assertNotIn("anthropic==", source)


PAGE = """<html><body><nav><a href="/menu">Menú principal</a></nav><main>
<h2><a href="/expo/hopper">Hopper en Madrid</a></h2><p>Del 1 de noviembre al 1 de febrero</p>
<a href="/expo/hopper"><img src="x.jpg"></a><a href="/expo/hopper">Ver más</a>
<a href="https://otra.org/entradas#comprar">Entradas</a><a href="#top">Arriba</a>
</main></body></html>"""


class LinkTests(unittest.TestCase):
    def test_links_are_marked_once_and_menus_dropped(self):
        text, links = llm.page_text(PAGE, "https://museo.es/expos")
        self.assertIn("Hopper en Madrid ⟨https://museo.es/expo/hopper⟩", text)
        self.assertEqual(text.count("https://museo.es/expo/hopper"), 1)
        self.assertNotIn("menu", " ".join(links.values()))
        self.assertIn("https://otra.org/entradas", links.values())

    def test_model_url_must_exist_in_page(self):
        _, links = llm.page_text(PAGE, "https://museo.es/expos")
        page = "https://museo.es/expos"
        self.assertEqual(llm.own_url("/expo/hopper/", links, page), "https://museo.es/expo/hopper")
        self.assertEqual(llm.own_url("https://museo.es/expo/inventada", links, page), page)
        self.assertEqual(llm.own_url(None, links, page), page)

    def test_agenda_events_land_in_their_section(self):
        fuente = Fuente("Fundación", "https://f.es/agenda", "agenda")
        raw = [{"title": "Concierto", "tipo": "musica", "url": None, "date_start": None, "date_end": None},
               {"title": "Expo", "tipo": "exposicion", "url": None, "date_start": None, "date_end": None},
               {"title": " ", "tipo": "charla"}]
        events = llm.to_events(fuente, raw, {})
        self.assertEqual([(e["title"], e["section"]) for e in events], [("Concierto", "musica"), ("Expo", "museo")])
        self.assertEqual(events[0]["source_url"], "https://f.es/agenda")

    def test_fixed_kind_overrides_model_tipo(self):
        fuente = Fuente("Teatro", "https://t.es/", "teatro")
        events = llm.to_events(fuente, [{"title": "Obra", "tipo": "musica"}], {})
        self.assertEqual(events[0]["section"], "teatro")


def ev(title, source="Museo", url="https://m.es/", section="museo", **fields):
    return {"title": title, "source": source, "source_url": url, "section": section, **fields}


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.con = db()
        self.addCleanup(self.con.close)
        self.museo = Fuente("Museo", "https://m.es/", "museo")
        self.cine = Fuente("Cine", "https://c.es/", "cine")

    def titles(self):
        return sorted(r["title"] for r in pipeline.published(self.con))

    def age(self, days_ago):
        """Lleva la pasada actual al pasado para simular la semana siguiente."""
        old = date.fromordinal(date.today().toordinal() - days_ago).isoformat()
        self.con.execute("UPDATE events SET last_seen = ?, first_seen = ?", (old, old))
        self.con.execute("UPDATE sources SET last_ok = ?", (old,))
        self.con.commit()

    def test_failed_source_keeps_its_events(self):
        pipeline.store_source(self.con, self.museo, [ev("Hopper")])
        pipeline.store_source(self.con, self.cine, [ev("Película", "Cine", "https://c.es/", "cine")])
        self.age(7)
        pipeline.mark_failed(self.con, self.museo, "TimeoutError")
        pipeline.store_source(self.con, self.cine, [ev("Estreno", "Cine", "https://c.es/", "cine")])
        self.assertEqual(self.titles(), ["Estreno", "Hopper"])

    def test_event_dropped_by_its_source_disappears(self):
        pipeline.store_source(self.con, self.museo, [ev("Hopper"), ev("Wyeth")])
        self.age(7)
        pipeline.store_source(self.con, self.museo, [ev("Hopper")])
        self.assertEqual(self.titles(), ["Hopper"])

    def test_cinema_replacement_only_touches_that_cinema(self):
        otro = Fuente("Otro cine", "https://o.es/", "cine")
        pipeline.store_source(self.con, self.cine, [ev("A", "Cine", "https://c.es/", "cine")])
        pipeline.store_source(self.con, otro, [ev("B", "Otro cine", "https://o.es/", "cine")])
        pipeline.store_source(self.con, self.cine, [ev("C", "Cine", "https://c.es/", "cine")])
        self.assertEqual(self.titles(), ["B", "C"])

    def test_legacy_rows_follow_the_global_last_pass(self):
        self.con.execute("INSERT INTO events (id, section, title, source, first_seen, last_seen) "
                         "VALUES ('x', 'museo', 'Antigua', 'Viejo', '2026-10-30', '2026-10-30')")
        self.assertEqual(self.titles(), ["Antigua"])
        pipeline.store_source(self.con, self.museo, [ev("Hopper")])
        self.assertEqual(self.titles(), ["Hopper"])

    def test_cba_rows_are_renamed_keeping_tags(self):
        con = sqlite3.connect(":memory:")
        old_id = pipeline.event_id("CBA", "Expo", None)
        con.execute("CREATE TABLE events (id TEXT PRIMARY KEY, section TEXT NOT NULL, title TEXT NOT NULL, venue TEXT, "
                    "date_start DATE, date_end DATE, description TEXT, url TEXT, source TEXT, first_seen DATE NOT NULL, "
                    "last_seen DATE NOT NULL, kids_friendly INTEGER, selective INTEGER, tags_hash TEXT)")
        con.execute("INSERT INTO events VALUES (?, 'museo', 'Expo', NULL, NULL, NULL, NULL, NULL, 'CBA', "
                    "'2026-09-01', '2026-10-30', 0, 1, 'h')", (old_id,))
        with patch.object(pipeline, "DB_PATH", ":memory:"), patch.object(pipeline.sqlite3, "connect", return_value=con):
            pipeline.init_db()
        row = con.execute("SELECT id, source, selective, first_seen FROM events").fetchone()
        self.assertEqual(row, (pipeline.event_id("Círculo de Bellas Artes", "Expo", None),
                               "Círculo de Bellas Artes", 1, "2026-09-01"))


class RunTests(unittest.TestCase):
    def run_with(self, results, previous=None):
        con = db()
        self.addCleanup(con.close)
        fuentes = [Fuente(n, f"https://{n}.es/", "museo") for n in results]
        for name, count in (previous or {}).items():
            con.execute("INSERT INTO sources (url, name, last_ok, last_count) VALUES (?, ?, '2026-10-30', ?)",
                        (f"https://{name}.es/", name, count))

        def fake_extract(f):
            out = results[f.name]
            if isinstance(out, Exception):
                raise out
            return [ev(t, f.name, f.url) for t in out]

        with patch.object(pipeline, "all_sources", return_value=fuentes), \
             patch("scrapers.llm.extract", side_effect=fake_extract), \
             patch("scrapers.tagger.tag_events"):
            return pipeline.run(con), con

    def test_suspicious_empty_source_is_treated_as_failure(self):
        summary, con = self.run_with({"a": ["Expo"], "b": []}, previous={"b": 5})
        self.assertEqual([n for n, _ in summary["failed"]], ["b"])
        self.assertIn("vacía", con.execute("SELECT last_error FROM sources WHERE name='b'").fetchone()[0])

    def test_all_sources_failing_raises(self):
        with self.assertRaises(RuntimeError):
            self.run_with({"a": RuntimeError("sin sesión"), "b": RuntimeError("sin sesión")})


class TaggerTests(unittest.TestCase):
    def test_tags_come_from_claude_json(self):
        with patch.object(tagger, "claude_json", return_value={"tags": [{"i": 1, "kids_friendly": 1, "selective": 0}]}):
            out = tagger._tag_batch([{"title": "a"}, {"title": "b"}], "gusto", "niños")
        self.assertEqual(out, [{"kids_friendly": 0, "selective": 0}, {"kids_friendly": 1, "selective": 0}])


class CurateTests(unittest.TestCase):
    def row(self, **kw):
        base = {"section": "charla", "date_start": None, "date_end": None}
        return {**base, **kw}

    def test_this_week_window(self):
        today, end = "2026-11-13", "2026-11-22"
        on = lambda **kw: curate.on_this_week(self.row(**kw), today, end)
        self.assertTrue(on(date_start="2026-11-14"))
        self.assertFalse(on(date_start="2026-11-30"))
        self.assertFalse(on(date_start="2026-11-12"))
        self.assertTrue(on(section="museo", date_start="2026-09-01", date_end="2026-11-15"))
        self.assertFalse(on(section="museo", date_start="2026-12-01", date_end="2027-02-01"))
        self.assertTrue(on(section="cine"))
        self.assertTrue(on(section="galeria"))
        self.assertFalse(on(section="teatro"))

    def test_validate_drops_unknown_and_repeated_ids(self):
        answer = {"semana": [{"id": "a", "por_que": " Porque  sí. "}, {"id": "zz", "por_que": "x"},
                             {"id": "a", "por_que": "otra vez"}],
                  "ninos": [{"id": "a", "por_que": "repetido"}, {"id": "b", "por_que": "Dibujos grandes."}]}
        self.assertEqual(curate.validate(answer, {"a", "b"}),
                         {"semana": [{"id": "a", "por_que": "Porque sí."}],
                          "ninos": [{"id": "b", "por_que": "Dibujos grandes."}]})

    def test_validate_needs_at_least_one_pick(self):
        with self.assertRaises(ValueError):
            curate.validate({"semana": [{"id": "zz", "por_que": "x"}], "ninos": []}, {"a"})


if __name__ == "__main__":
    unittest.main()
