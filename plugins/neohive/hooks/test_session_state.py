#!/usr/bin/env python3
"""Tests for session-state.py (HIVE-237 / F1).

Stdlib only, no test framework dependency. Run:

    python3 test_session_state.py

Each test isolates state via NEOHIVE_SESSION_STATE_DIR pointed at a tempdir,
which both the writer and reader honour (the production caveat: that var must be
identical for every consumer)."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

# session-state.py has a hyphen, so load it by path rather than import.
_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("session_state", _HERE / "session-state.py")
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)

# A single-hive recall response, exactly as formatRecallResults() emits it.
SINGLE_HIVE = (
    "### Memory #1 (id: 1234, score: 0.812)\n"
    "**Type**: insight | **Importance**: 5/10 | **Accessed**: 3x\n"
    "**Tags**: sync, clone\n\n"
    "Clone credentials are read from the keychain.\n\n"
    "---\n\n"
    "### Memory #2 (id: 1190, score: 0.774)\n"
    "**Type**: directive | **Importance**: 8/10 | **Accessed**: 0x\n\n"
    "Always return await in data-layer methods.\n"
)

# A cross-hive recall response carries the '| **Hive**: X' suffix per memory.
CROSS_HIVE = (
    "### Memory #1 (id: 7, score: 0.901)\n"
    "**Type**: insight | **Importance**: 5/10 | **Accessed**: 0x | **Hive**: HiveMindRepo\n\n"
    "alpha\n\n"
    "---\n\n"
    "### Memory #2 (id: 8, score: 0.640)\n"
    "**Type**: convention | **Importance**: 4/10 | **Accessed**: 1x | **Hive**: Knowledge\n\n"
    "beta\n"
)

HINT = "\nHint: 2 results in 42ms across 1 hive; top score 0.812. Keep reaching for memory_recall first."


class SessionStateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["NEOHIVE_SESSION_STATE_DIR"] = self._tmp.name

    def tearDown(self):
        os.environ.pop("NEOHIVE_SESSION_STATE_DIR", None)
        self._tmp.cleanup()

    # ── acceptance: missing file degrades to empty ──────────────────────────
    def test_missing_file_returns_empty(self):
        self.assertEqual(ss.read_entries("no-such-session"), [])
        self.assertEqual(ss.summarize(ss.read_entries("no-such-session"))["recalls"], 0)

    # ── acceptance: one entry per recall, with ids + scores ─────────────────
    def test_parse_results_ids_and_scores(self):
        results = ss.parse_results(SINGLE_HIVE)
        self.assertEqual(
            results,
            [
                {"id": 1234, "score": 0.812, "hive": None},
                {"id": 1190, "score": 0.774, "hive": None},
            ],
        )

    def test_cross_hive_attribution(self):
        results = ss.parse_results(CROSS_HIVE)
        self.assertEqual([r["hive"] for r in results], ["HiveMindRepo", "Knowledge"])
        self.assertEqual([r["id"] for r in results], [7, 8])

    def test_duration_parsed_from_hint(self):
        self.assertEqual(ss.parse_duration(SINGLE_HIVE + HINT), 42)
        self.assertIsNone(ss.parse_duration(SINGLE_HIVE))
        # No-match recalls render the duration as "(Nms)", not "in Nms".
        self.assertEqual(ss.parse_duration("\nHint: no matches in 1 hive (37ms). Try rephrasing."), 37)
        # A memory body that mentions "<n>ms" must not shadow the real hint timing.
        self.assertEqual(ss.parse_duration("prior run took 999ms\n\n---\n" + HINT), 42)
        # No hint present (hints disabled) yields None even if content mentions ms.
        self.assertIsNone(ss.parse_duration("some memory that took 500ms to write"))

    def test_append_then_read_roundtrip(self):
        ss._append_recall("sess-A", "clone credentials", SINGLE_HIVE + HINT, trigger="assistant")
        entries = ss.read_entries("sess-A")
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["tool"], "recall")
        self.assertEqual(e["query"], "clone credentials")
        self.assertEqual(e["durationMs"], 42)
        self.assertEqual([r["id"] for r in e["results"]], [1234, 1190])
        self.assertIn("ts", e)
        # identifying factors: which interface and what triggered the recall
        self.assertEqual(e["client"], "claude-code")
        self.assertEqual(e["trigger"], "assistant")

    # ── acceptance: corrupt state degrades to empty, never errors ───────────
    def test_corrupt_line_is_skipped(self):
        path = ss.state_path("sess-corrupt")
        path.parent.mkdir(parents=True, exist_ok=True)
        good = json.dumps({"tool": "recall", "results": [{"id": 1, "score": 0.5}]})
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(good + "\n")
            fh.write("{not valid json at all\n")  # garbled line
            fh.write('{"tool":"recall","results":[{"id":2,"score":0.6}\n')  # truncated
            fh.write(good + "\n")
        entries = ss.read_entries("sess-corrupt")
        self.assertEqual(len(entries), 2)  # two good lines survive, bad ones skipped

    # ── multiple writers append to the same file ────────────────────────────
    def test_multi_writer_append(self):
        ss._append_recall("sess-multi", "q1", SINGLE_HIVE, trigger="assistant")
        ss._append_recall("sess-multi", "q2", CROSS_HIVE, trigger="user-prompt")
        entries = ss.read_entries("sess-multi")
        self.assertEqual([e["query"] for e in entries], ["q1", "q2"])
        self.assertEqual([e["trigger"] for e in entries], ["assistant", "user-prompt"])

    # ── stamp-posttool path (model-initiated recall) ────────────────────────
    def test_stamp_posttool_content_list(self):
        payload = {
            "session_id": "sess-pt",
            "tool_name": "mcp__neohive__memory_recall",
            "tool_input": {"query": "how does sync clone work", "limit": 5},
            "tool_response": {"content": [{"type": "text", "text": SINGLE_HIVE + HINT}]},
        }
        self._run_stdin("stamp-posttool", json.dumps(payload))
        entries = ss.read_entries("sess-pt")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["query"], "how does sync clone work")
        self.assertEqual(entries[0]["trigger"], "assistant")
        self.assertEqual(entries[0]["client"], "claude-code")
        self.assertEqual([r["id"] for r in entries[0]["results"]], [1234, 1190])

    def test_stamp_posttool_string_response(self):
        payload = {
            "session_id": "sess-str",
            "tool_name": "mcp__hivemind__memory_recall",  # legacy server key still matches
            "tool_input": {"queries": ["a", "b"]},
            "tool_response": CROSS_HIVE,
        }
        self._run_stdin("stamp-posttool", json.dumps(payload))
        entries = ss.read_entries("sess-str")
        self.assertEqual(entries[0]["query"], "a · b")
        self.assertEqual([r["hive"] for r in entries[0]["results"]], ["HiveMindRepo", "Knowledge"])

    def test_stamp_posttool_ignores_non_neohive_tool(self):
        # A tool that is not a NeoHive MCP tool is never recorded.
        payload = {
            "session_id": "sess-ignore",
            "tool_name": "mcp__other__do_thing",
            "tool_input": {"x": 1},
            "tool_response": {"content": [{"type": "text", "text": SINGLE_HIVE}]},
        }
        self._run_stdin("stamp-posttool", json.dumps(payload))
        self.assertEqual(ss.read_entries("sess-ignore"), [])

    # ── usage ledger: every NeoHive MCP tool is recorded, not only recall ───
    def test_stamp_posttool_context_recorded(self):
        payload = {
            "session_id": "sess-ctx",
            "tool_name": "mcp__neohive__memory_context",
            "tool_input": {"task": "debugging sync OOM"},
            "tool_response": {"content": [{"type": "text", "text": SINGLE_HIVE}]},
        }
        self._run_stdin("stamp-posttool", json.dumps(payload))
        entries = ss.read_entries("sess-ctx")
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["tool"], "context")
        self.assertEqual(e["trigger"], "assistant")
        self.assertEqual(e["query"], "debugging sync OOM")  # task recorded as the query
        self.assertNotIn("results", e)  # context has no per-memory ids to parse

    def test_stamp_posttool_store_recorded(self):
        payload = {
            "session_id": "sess-store",
            "tool_name": "mcp__neohive__memory_store",
            "tool_input": {"content": "x", "type": "insight", "tags": ["a"], "importance": 8},
            # The real memory_store response opens with the created id; the hook
            # parses it into args.storedId (matches the server's logged id).
            "tool_response": {
                "content": [{"type": "text", "text": "Memory stored successfully (id: 99, type: insight, importance: 8, hive: h1)"}]
            },
        }
        self._run_stdin("stamp-posttool", json.dumps(payload))
        e = ss.read_entries("sess-store")[0]
        self.assertEqual(e["tool"], "store")
        self.assertEqual(e["trigger"], "assistant")
        self.assertEqual(e["args"], {"type": "insight", "tags": ["a"], "importance": 8, "storedId": 99})

    def test_stamp_posttool_store_without_parsable_id_omits_storedId(self):
        # If the response text has no parseable id, storedId is simply omitted
        # (best-effort, never errors): the other args still record.
        payload = {
            "session_id": "sess-store-noid",
            "tool_name": "mcp__neohive__memory_store",
            "tool_input": {"content": "x", "type": "note", "tags": [], "importance": 5},
            "tool_response": {"content": [{"type": "text", "text": "stored ok"}]},
        }
        self._run_stdin("stamp-posttool", json.dumps(payload))
        e = ss.read_entries("sess-store-noid")[0]
        self.assertNotIn("storedId", e["args"])
        self.assertEqual(e["args"]["type"], "note")

    def test_stamp_posttool_forget_recorded_nested_arguments(self):
        # Tolerates the nested {arguments:{...}} wrapper like extract_query does.
        payload = {
            "session_id": "sess-forget",
            "tool_name": "mcp__neohive__memory_forget",
            "tool_input": {"arguments": {"memory_id": 42, "reason": "stale", "superseded_by": 50}},
            "tool_response": "ok",
        }
        self._run_stdin("stamp-posttool", json.dumps(payload))
        e = ss.read_entries("sess-forget")[0]
        self.assertEqual(e["tool"], "forget")
        self.assertEqual(e["args"], {"memoryId": 42, "reason": "stale", "supersededBy": 50})

    def test_stamp_posttool_list_hives_recorded(self):
        payload = {
            "session_id": "sess-lh",
            "tool_name": "mcp__neohive__list_hives",
            "tool_input": {},
            "tool_response": "ok",
        }
        self._run_stdin("stamp-posttool", json.dumps(payload))
        e = ss.read_entries("sess-lh")[0]
        self.assertEqual(e["tool"], "list-hives")
        self.assertEqual(e["trigger"], "assistant")
        self.assertNotIn("args", e)  # list_hives takes no arguments

    def test_stamp_posttool_stats_recorded(self):
        payload = {
            "session_id": "sess-stats",
            "tool_name": "mcp__neohive__memory_stats",
            "tool_input": {"hive": "abc"},
            "tool_response": "ok",
        }
        self._run_stdin("stamp-posttool", json.dumps(payload))
        e = ss.read_entries("sess-stats")[0]
        self.assertEqual(e["tool"], "stats")
        self.assertEqual(e["args"], {"hive": "abc"})

    def test_summarize_counts_recalls_separately_from_events(self):
        ss._append_recall("sess-mix", "q1", SINGLE_HIVE + HINT, trigger="assistant")
        ss._append_event("sess-mix", "store", {"type": "insight"}, "")
        ss._append_event("sess-mix", "list-hives", {}, "")
        s = ss.summarize(ss.read_entries("sess-mix"))
        self.assertEqual(s["events"], 3)
        self.assertEqual(s["recalls"], 1)  # named field still means recalls only
        self.assertEqual(s["byTool"], {"recall": 1, "store": 1, "list-hives": 1})
        self.assertEqual(s["uniqueMemoryIds"], 2)  # only recall contributes ids
        self.assertEqual(s["lastQuery"], "q1")  # last entry carrying a query

    # ── stamp-recall-sse path (UserPromptSubmit auto-context) ───────────────
    def test_stamp_recall_sse(self):
        rpc = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": SINGLE_HIVE}]}}
        sse = "event: message\ndata: " + json.dumps(rpc) + "\n\n"
        self._run_stdin("stamp-recall-sse", sse, extra=["--session", "sess-sse", "--query", "boot"])
        entries = ss.read_entries("sess-sse")
        self.assertEqual(entries[0]["query"], "boot")
        self.assertEqual(entries[0]["trigger"], "user-prompt")
        self.assertEqual([r["id"] for r in entries[0]["results"]], [1234, 1190])

    # ── path safety ─────────────────────────────────────────────────────────
    def test_path_traversal_is_neutralised(self):
        path = ss.state_path("../../etc/evil")
        # Stays inside the sessions dir as a single flat file: separators are
        # stripped so the id can never escape to a parent dir. A literal '..'
        # surviving inside the flat name is harmless (it is not a path component).
        self.assertEqual(path.parent, ss.session_dir())
        self.assertNotIn("/", path.name)

    def test_empty_session_id_has_no_path(self):
        self.assertIsNone(ss.state_path(""))
        self.assertIsNone(ss.state_path(None))

    # ── CLI: read / read --summary emit the documented JSON shapes ──────────
    # Exercises the cmd_read consumer contract (F2/E1/E2 invoke this), which the
    # API-level read_entries/summarize tests do not cover: argv parsing + stdout.
    def test_cmd_read_cli_entries_and_summary(self):
        sid = "cli-session"
        ss._append_recall(sid, "clone credentials", SINGLE_HIVE + HINT, trigger="user-prompt")
        ss._append_event(
            sid,
            "store",
            {"arguments": {"type": "decision", "tags": ["x"], "importance": 7}},
            "Memory stored successfully (id: 42, type: decision)",
        )

        entries = self._run_capture("read", ["--session", sid])
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["tool"], "recall")
        self.assertEqual(entries[0]["results"][0]["id"], 1234)
        self.assertEqual(entries[1]["tool"], "store")
        self.assertEqual(entries[1]["args"]["storedId"], 42)

        summary = self._run_capture("read", ["--session", sid, "--summary"])
        self.assertEqual(summary["events"], 2)
        self.assertEqual(summary["recalls"], 1)
        self.assertEqual(summary["byTool"], {"recall": 1, "store": 1})
        self.assertEqual(summary["uniqueMemoryIds"], 2)
        self.assertEqual(summary["lastQuery"], "clone credentials")

    # helper: drive a CLI subcommand and capture its stdout as parsed JSON
    def _run_capture(self, cmd, extra=None):
        import io
        import sys

        argv = ["session-state.py", cmd] + (extra or [])
        old_argv, old_stdout = sys.argv, sys.stdout
        sys.argv = argv
        sys.stdout = io.StringIO()
        try:
            ss.main()
            out = sys.stdout.getvalue()
        finally:
            sys.argv, sys.stdout = old_argv, old_stdout
        return json.loads(out)

    # helper: drive a CLI subcommand with given stdin
    def _run_stdin(self, cmd, stdin_text, extra=None):
        import io
        import sys

        argv = ["session-state.py", cmd] + (extra or [])
        old_argv, old_stdin = sys.argv, sys.stdin
        sys.argv = argv
        sys.stdin = io.StringIO(stdin_text)
        try:
            ss.main()
        finally:
            sys.argv, sys.stdin = old_argv, old_stdin


if __name__ == "__main__":
    unittest.main(verbosity=2)
