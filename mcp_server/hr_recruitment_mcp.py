#!/usr/bin/env python3
"""
Minimal MCP-style stdio server (JSON-RPC over newline-delimited JSON).
Exposes tools backed by the same SQLite DB as the FastAPI app (read-only queries).

Run (from repo root, with backend deps / DB present):
  python3 mcp_server/hr_recruitment_mcp.py

Configure in Cursor MCP settings as a custom stdio command pointing to this script.
Requires Python 3.10+ for pattern matching; for 3.9, replace match with if/elif.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "backend" / "hr_agent.db"


def _send(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _handle(req: dict[str, Any], db_path: Path) -> dict[str, Any]:
    method = req.get("method")
    _id = req.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": _id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "hr-recruitment-mcp", "version": "0.1.0"},
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": _id,
            "result": {
                "tools": [
                    {
                        "name": "list_candidates",
                        "description": "List candidates with stage and scores from SQLite.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "limit": {"type": "integer", "default": 50},
                            },
                        },
                    }
                ]
            },
        }
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = (params.get("arguments") or {}) if isinstance(params.get("arguments"), dict) else {}
        if name != "list_candidates":
            return {
                "jsonrpc": "2.0",
                "id": _id,
                "error": {"code": -32601, "message": f"unknown tool {name}"},
            }
        lim = int(args.get("limit", 50))
        lim = max(1, min(lim, 200))
        if not db_path.is_file():
            text = f"Database not found at {db_path}"
        else:
            con = sqlite3.connect(str(db_path))
            try:
                rows = con.execute(
                    "SELECT id, full_name, email, stage, ats_score, technical_total_score FROM candidates ORDER BY created_at DESC LIMIT ?",
                    (lim,),
                ).fetchall()
                text = json.dumps(
                    [
                        {
                            "id": r[0],
                            "full_name": r[1],
                            "email": r[2],
                            "stage": r[3],
                            "ats_score": r[4],
                            "technical_total_score": r[5],
                        }
                        for r in rows
                    ],
                    indent=2,
                )
            finally:
                con.close()
        return {
            "jsonrpc": "2.0",
            "id": _id,
            "result": {"content": [{"type": "text", "text": text}]},
        }
    return {
        "jsonrpc": "2.0",
        "id": _id,
        "error": {"code": -32601, "message": f"unknown method {method}"},
    }


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _handle(req, db_path)
        _send(resp)


if __name__ == "__main__":
    main()
