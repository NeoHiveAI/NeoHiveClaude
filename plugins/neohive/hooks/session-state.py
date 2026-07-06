#!/usr/bin/env python3
"""NeoHive per-session state file (HIVE-237 / F1).

Records every NeoHive MCP tool call of a Claude Code session: recall, context,
store, forget, stats, and list_hives. For recall it captures which memory ids
came back, their scores, the query, and a timestamp; for the other tools it
records the call, its salient arguments (the "what/why" of the usage), and
timing. This is the quiet foundation the visible-value features read (statusline
pulse, end-of-session recap, citation tracking, the stop-hook reconciliation,
and the dashboards) and the raw signal for overall NeoHive usage analytics.

Recall keeps a richer entry shape than the other tools because only the recall
response carries per-memory ids+scores. The recall-only consumers that predate
this usage-ledger expansion (statusline, recap, citation tracking) filter on
``tool == "recall"`` and are unaffected by the additional event types; the
``summarize`` aggregate likewise keeps ``recalls`` meaning recalls only.

THE MODEL NEVER READS THIS FILE. The model already gets its behavioural nudge
from the one-line recall hint appended to the MCP response (HIVE-162). This file
is consumed only by other hooks and UI surfaces, so it costs zero model tokens.

Format: JSON Lines, one object per NeoHive MCP tool call. Each entry carries a
``tool`` field naming the call and identifying factors so a reader can tell what
kind of session and what kind of call it was:
  * client  always "claude-code" here (this file is only written by Claude
            Code hooks); the server-side query_log records the real interface
            for hookless clients like Desktop / Codex / Cursor.
  * trigger what caused the call: "assistant" (the model called the tool itself,
            via the PostToolUse hook) or "user-prompt" (the per-prompt recall
            fired automatically by the UserPromptSubmit hook).
JSONL is deliberate:
  * Each entry is emitted as one line via a single O_APPEND write() syscall (see
    append_entry), which the kernel serialises per regular-file inode. So the two
    writers (the PostToolUse stamp hook for model-initiated tool calls, and the
    UserPromptSubmit auto-context hook) can append to the same file without a
    lock or a read-modify-write race, and a line never interleaves with the
    other writer's line regardless of its size.
  * "One entry per tool call" maps to one line.
  * A single truncated/garbled line (e.g. a crash mid-append) costs at most one
    entry; the reader skips it and keeps the rest. Corrupt state degrades to
    empty, never to an error. This is an acceptance criterion of the ticket.

Location: ~/.claude/neohive/sessions/<session_id>.jsonl
  The base is environment-independent on purpose. The obvious home is the plugin
  data dir ($CLAUDE_PLUGIN_DATA), but that variable is not guaranteed to reach
  every consumer: the statusline command (an E1 consumer) does not receive it.
  If the writer keyed off $CLAUDE_PLUGIN_DATA and the statusline reader fell back
  to a different base, they would resolve different paths and the statusline
  would silently read nothing. So the path is a pure function of session_id
  under a fixed base. Do NOT move this to $CLAUDE_PLUGIN_DATA without making
  every consumer (including the statusline) resolve the identical path.

  Override the base with NEOHIVE_SESSION_STATE_DIR (must be set identically for
  every writer and reader; used by the tests).

Subcommands:
  stamp-posttool                     read a PostToolUse hook payload on stdin
                                     (tool_name / tool_input / tool_response /
                                     session_id), recognise any NeoHive MCP tool,
                                     append one entry (recall parses ids+scores;
                                     other tools record args+timing).
                                     Best-effort, never errors.
  stamp-recall-sse --session ID      read a raw MCP JSON-RPC / SSE recall
                   --query Q         response on stdin, append one entry. Used by
                                     the UserPromptSubmit auto-context hook.
  read --session ID [--summary]      print the session's entries as a JSON array,
                                     or aggregate stats with --summary. Returns
                                     an empty array / zeroed summary on a missing
                                     or corrupt file. This is the read helper
                                     other hooks consume.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Matches the recall heading emitted by formatRecallResults() in
# server/src/orchestrator/index.ts, e.g. "### Memory #1 (id: 1234, score: 0.812)".
_HEADING_RE = re.compile(r"### Memory #\d+ \(id: (\d+), score: ([0-9.]+)\)")
_HIVE_RE = re.compile(r"\*\*Hive\*\*:\s*([^\n|]+)")
# The server-measured duration lives in the appended recall/context hint, which
# renders it two ways: "... in 42ms across ..." when there are matches, and
# "(42ms)" (no "in " prefix) for a no-match recall. Match a bare "<n>ms" so both
# shapes are captured; parse_duration scopes the search to the hint segment.
_DURATION_RE = re.compile(r"(\d+)ms")
# memory_store's response opens with "Memory stored successfully (id: N, ...)".
_STORED_ID_RE = re.compile(r"stored successfully \(id: (\d+)")


def session_dir():
    override = os.environ.get("NEOHIVE_SESSION_STATE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "neohive" / "sessions"


def state_path(session_id):
    """Resolve the per-session file path. Returns None for an unusable id.

    The session id is sanitised to a flat filename so a hostile or malformed id
    can never escape the sessions directory (path traversal) or name a
    subdirectory."""
    if not session_id:
        return None
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id)).strip(".")
    if not safe:
        return None
    return session_dir() / f"{safe}.jsonl"


def _iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_entry(session_id, entry):
    """Append one entry as a JSON line, atomically against the other writer.

    The two hook writers (the PostToolUse stamp and the UserPromptSubmit
    auto-context recall) append to the same file with no lock, so a line must
    never interleave with the other writer's line. We emit the whole line in a
    single ``os.write()`` to an ``O_APPEND`` fd: the kernel serialises each
    write() syscall to a regular file under the inode lock and O_APPEND places
    it at end-of-file, so one write() lands as one contiguous line regardless of
    its size. Python's buffered text writer ('a' mode) could split a large line
    (e.g. a recall with an unusually long id/score list) into several write()
    calls and lose that guarantee, so we bypass it and write the bytes directly.

    Best-effort: returns False on any failure rather than raising, so a hook can
    never error a session over state bookkeeping."""
    path = state_path(session_id)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        return True
    except Exception:
        return False


def read_entries(session_id):
    """Return the session's entries as a list. Missing file -> []. Each line is
    parsed independently; unparseable lines are skipped so a corrupt or
    truncated line never invalidates the rest."""
    path = state_path(session_id)
    if path is None or not path.exists():
        return []
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return entries


def summarize(entries):
    """Aggregate the entries into the small shape downstream surfaces (E1/E2)
    need without re-reading the file.

    "recalls" counts recall entries only (its meaning predates the usage-ledger
    expansion and the recall-only consumers depend on it); "events" is the total
    NeoHive tool calls and "byTool" the per-tool breakdown for usage analytics.
    Only recall entries carry results, so uniqueMemoryIds/topScore are recall-
    derived. lastQuery is the most recent entry that carried a query (recall or
    context); lastTs is the timestamp of the most recent entry of any tool."""
    unique_ids = set()
    top_score = None
    by_tool = {}
    last = None
    last_query = None
    for e in entries:
        tool = e.get("tool")
        by_tool[tool] = by_tool.get(tool, 0) + 1
        for r in e.get("results", []) or []:
            # Skip non-dict elements defensively: read_entries' per-line try/except
            # does not cover summarize (it runs after the read returns), so a hand-
            # edited or mangled results array (e.g. [null]) would otherwise raise
            # AttributeError here and break the whole summary for E1/E2/F2.
            if not isinstance(r, dict):
                continue
            mid = r.get("id")
            if mid is not None:
                unique_ids.add(mid)
            score = r.get("score")
            if isinstance(score, (int, float)) and (top_score is None or score > top_score):
                top_score = score
        if e.get("query"):
            last_query = e.get("query")
        last = e
    return {
        "events": len(entries),
        "recalls": by_tool.get("recall", 0),
        "byTool": by_tool,
        "uniqueMemoryIds": len(unique_ids),
        "topScore": top_score,
        "lastQuery": last_query,
        "lastTs": (last or {}).get("ts"),
    }


# ── recall-response parsing ─────────────────────────────────────────────────


def _collect_text(obj):
    """Flatten a tool_response of unknown shape (string, MCP content list, or
    {content:[...]} dict) into plain text. The heading regex only matches the
    server's own format, so over-collecting noise here is harmless."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return "\n".join(_collect_text(x) for x in obj)
    if isinstance(obj, dict):
        text = obj.get("text")
        if isinstance(text, str):
            return text
        if "content" in obj:
            return _collect_text(obj["content"])
        return "\n".join(_collect_text(v) for v in obj.values())
    return str(obj)


def parse_results(text):
    """Pull (id, score, hive) per memory from a recall response. Splits on the
    per-memory heading so the optional cross-hive '**Hive**: X' suffix is
    attributed to the right memory."""
    results = []
    for block in re.split(r"(?=### Memory #)", text):
        m = _HEADING_RE.search(block)
        if not m:
            continue
        hive = None
        hm = _HIVE_RE.search(block)
        if hm:
            hive = hm.group(1).strip() or None
        results.append({"id": int(m.group(1)), "score": float(m.group(2)), "hive": hive})
    return results


def parse_duration(text):
    """Pull the server-measured duration (ms) from the appended hint, or None.

    Scoped to the hint segment (everything after the last "Hint:") for two
    reasons: the no-match hint writes "(42ms)" rather than "in 42ms", so an
    "in <n>ms"-only pattern silently missed every empty recall; and a returned
    memory whose body mentions "<n>ms" must not shadow the real timing. When the
    response carries no hint (hints disabled), there is no server duration to
    recover, so this correctly returns None instead of a memory's stray "<n>ms".
    """
    hint_start = text.rfind("Hint:")
    if hint_start == -1:
        return None
    m = _DURATION_RE.search(text, hint_start)
    return int(m.group(1)) if m else None


def parse_stored_id(text):
    """Pull the created memory id from a memory_store response, or None. Mirrors
    the server, which logs the same id (it has it in hand); recorded so a session
    can be linked to the memories it produced (provenance/audit)."""
    m = _STORED_ID_RE.search(text)
    return int(m.group(1)) if m else None


def extract_query(tool_input):
    """Recover the query string from a recall tool_input, tolerating both the
    flat arguments object and a nested {arguments:{...}} wrapper."""
    args = _tool_args(tool_input)
    q = args.get("query")
    if isinstance(q, str) and q:
        return q
    qs = args.get("queries")
    if isinstance(qs, list) and qs:
        return " · ".join(str(x) for x in qs)
    return None


# This file is only ever written by the NeoHive plugin's hooks, which run under
# Claude Code, so the interface is always "claude-code" (the per-session server
# ledger in query_log is what distinguishes Desktop / Codex / Cursor / etc.).
# Recording it anyway keeps each entry self-describing for downstream readers.
CLIENT = "claude-code"


# Maps the MCP tool suffix (the part after the user-configured server key in
# "mcp__<server>__<suffix>") to the normalised short name recorded in the "tool"
# field. memory_recall stays "recall" for backward compatibility with the
# recall-only consumers (statusline pulse, recap, citation tracking) that
# predate the usage-ledger expansion and filter on tool == "recall".
_TOOL_NAMES = {
    "memory_recall": "recall",
    "memory_context": "context",
    "memory_store": "store",
    "memory_forget": "forget",
    "memory_stats": "stats",
    "list_hives": "list-hives",
}


def _tool_args(tool_input):
    """Unwrap a tool_input to its arguments dict, tolerating both the flat
    arguments object and a nested {arguments:{...}} wrapper (same shapes
    extract_query handles)."""
    if not isinstance(tool_input, dict):
        return {}
    args = tool_input.get("arguments")
    if isinstance(args, dict):
        return args
    return tool_input


def summarize_args(tool, tool_input):
    """Pull the salient inputs per non-recall tool for the usage ledger: the
    "what/why" of the call. Returns {} for tools that take no recordable args
    (list_hives), so the caller can omit the field entirely."""
    args = _tool_args(tool_input)
    if tool == "store":
        return {"type": args.get("type"), "tags": args.get("tags"), "importance": args.get("importance")}
    if tool == "forget":
        return {
            "memoryId": args.get("memory_id"),
            "reason": args.get("reason"),
            "supersededBy": args.get("superseded_by"),
        }
    if tool == "stats":
        return {"hive": args.get("hive")}
    return {}


def _append_event(session_id, tool, tool_input, text):
    """Append one usage entry for a non-recall NeoHive MCP tool. The PostToolUse
    hook only fires on model-initiated calls, so trigger is always "assistant".

    Recall has its own richer builder (_append_recall) because only its response
    carries per-memory ids+scores. context is a read like recall, so its task is
    recorded under "query" for uniform "what was asked" reading, but it has no
    per-memory ids to parse. durationMs is parsed from the recall hint text and
    is therefore null for tools whose response carries no "in <n>ms" hint."""
    entry = {
        "ts": _iso_now(),
        "tool": tool,
        "trigger": "assistant",
        "client": CLIENT,
        "durationMs": parse_duration(text),
        "source": "mcp",
    }
    if tool == "context":
        entry["query"] = _tool_args(tool_input).get("task")
    else:
        args = summarize_args(tool, tool_input)
        if tool == "store":
            # The created memory id is in the response text; log it (free, in hand)
            # to link the session to what it produced. Matches the server's args.
            stored_id = parse_stored_id(text)
            if stored_id is not None:
                args = {**args, "storedId": stored_id}
        if args:
            entry["args"] = args
    return append_entry(session_id, entry)


def _append_recall(session_id, query, text, trigger):
    """Append one recall entry.

    trigger differentiates what caused the recall within the session:
      "assistant"   the model called memory_recall itself (PostToolUse hook)
      "user-prompt" the per-prompt recall fired automatically (UserPromptSubmit hook)
    """
    entry = {
        "ts": _iso_now(),
        "tool": "recall",
        "trigger": trigger,
        "client": CLIENT,
        "query": query,
        "durationMs": parse_duration(text),
        "source": "mcp",
        "results": parse_results(text),
    }
    return append_entry(session_id, entry)


def _mcp_response_text(raw):
    """Extract the text content from a raw MCP JSON-RPC / SSE response body."""
    raw = (raw or "").strip()
    payload = None
    for line in raw.splitlines():
        if line.startswith("data: "):
            payload = line[6:]
            break
    if payload is None:
        payload = raw
    d = json.loads(payload)
    result = d.get("result", {})
    contents = result.get("content", [])
    return "\n".join(c["text"] for c in contents if c.get("type") == "text")


# ── CLI ─────────────────────────────────────────────────────────────────────


def _arg(name, default=None):
    flag = "--" + name
    argv = sys.argv
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def cmd_stamp_posttool():
    data = json.loads(sys.stdin.read())
    tool_name = data.get("tool_name", "") or ""
    # The MCP server key is user-configured, so match on the tool suffix
    # ("mcp__<server>__<suffix>") rather than a hardcoded server name. Anything
    # that is not a recognised NeoHive tool is ignored (the hooks.json matcher
    # may over-match; this is the authoritative filter).
    tool = _TOOL_NAMES.get(tool_name.rsplit("__", 1)[-1])
    if tool is None:
        return
    session_id = data.get("session_id")
    if not session_id:
        return
    text = _collect_text(data.get("tool_response"))
    tool_input = data.get("tool_input") or {}
    if tool == "recall":
        _append_recall(session_id, extract_query(tool_input), text, trigger="assistant")
    else:
        _append_event(session_id, tool, tool_input, text)


def cmd_stamp_recall_sse():
    session_id = _arg("session")
    if not session_id:
        return
    text = _mcp_response_text(sys.stdin.read())
    _append_recall(session_id, _arg("query"), text, trigger="user-prompt")


def cmd_read():
    session_id = _arg("session")
    entries = read_entries(session_id)
    if "--summary" in sys.argv:
        print(json.dumps(summarize(entries)))
    else:
        print(json.dumps(entries))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if cmd == "stamp-posttool":
            cmd_stamp_posttool()
        elif cmd == "stamp-recall-sse":
            cmd_stamp_recall_sse()
        elif cmd == "read":
            cmd_read()
        else:
            sys.stderr.write("unknown subcommand: %r\n" % cmd)
            return 2
    except Exception:
        # Stamping is best-effort; never error a session over state bookkeeping.
        # 'read' degrades to empty above, so a failure here means a malformed
        # stamp payload, which we simply drop.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
