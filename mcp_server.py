"""A read-only MCP JSON-RPC stdio server exposing knowledge search."""
from __future__ import annotations

import json
import sys

import app

PROTOCOL_VERSION = "2024-11-05"
TOOLS = [{
    "name": "search_knowledge_base",
    "description": "Search indexed knowledge across domains and return source excerpts with page/chunk citations.",
    "inputSchema": {"type": "object", "properties": {
        "query": {"type": "string", "description": "Question or search phrase"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 8},
        "retrieval_mode": {"type": "string", "enum": ["hybrid", "bm25", "vector"]},
    }, "required": ["query"]},
}]


def _error(request_id, code: int, message: str):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(request: dict) -> dict | None:
    """Return a JSON-RPC response; notifications intentionally return no response."""
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
        return _error(request.get("id") if isinstance(request, dict) else None, -32600, "Invalid Request")
    method = request["method"]
    request_id = request.get("id")
    if request_id is None:
        # MCP notifications (including notifications/initialized) do not receive a response.
        return None
    params = request.get("params") or {}
    if not isinstance(params, dict):
        return _error(request_id, -32602, "Invalid params")
    if method == "initialize":
        result = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "kbqa", "version": "1.0.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        if params.get("name") != "search_knowledge_base":
            return _error(request_id, -32602, "Unknown tool")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict) or not isinstance(arguments.get("query"), str):
            return _error(request_id, -32602, "query must be a string")
        try:
            hits = app.query(arguments["query"], arguments.get("limit", 5), arguments.get("retrieval_mode", "hybrid"))
        except (ValueError, TypeError) as error:
            return _error(request_id, -32602, str(error))
        result = {"content": [{"type": "text", "text": json.dumps({"results": hits}, ensure_ascii=False)}], "isError": False}
    else:
        return _error(request_id, -32601, "Method not found")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main():
    app.seed()
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin.buffer:
        try:
            request = json.loads(line)
            response = handle(request)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except (json.JSONDecodeError, UnicodeDecodeError):
            sys.stdout.write(json.dumps(_error(None, -32700, "Parse error")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
