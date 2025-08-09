import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# Reuse DB helpers
from db import list_runs, get_run, DB_PATH  # type: ignore

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "7399"))


def json_response(handler: BaseHTTPRequestHandler, status: int, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return json_response(self, 200, {"status": "ok", "db_path": DB_PATH, "message": "See /mcp and /tools endpoints"})
        if parsed.path == "/mcp":
            manifest = {
                "name": "cursor-agents-review",
                "version": "0.1.0",
                "description": "MCP tools for listing and inspecting Cursor agent runs and PRs",
                "tools": [
                    {
                        "name": "list_tasks",
                        "description": "List recent agent runs (tasks)",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
                                "offset": {"type": "integer", "minimum": 0, "default": 0}
                            }
                        }
                    },
                    {
                        "name": "task",
                        "description": "Get a single run by id",
                        "input_schema": {
                            "type": "object",
                            "properties": {"id": {"type": "string"}},
                            "required": ["id"]
                        }
                    }
                ]
            }
            return json_response(self, 200, manifest)

        return json_response(self, 404, {"detail": "not found"})

    def do_POST(self):  # noqa: N802
        try:
            parsed = urlparse(self.path)
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                body = json.loads(raw_body.decode("utf-8") or "{}")
            except Exception:
                return json_response(self, 400, {"detail": "invalid JSON"})

            if parsed.path == "/tools/list_tasks":
                limit = body.get("limit", 100)
                offset = body.get("offset", 0)
                try:
                    limit = int(limit)
                    offset = int(offset)
                except Exception:
                    return json_response(self, 400, {"detail": "limit/offset must be integers"})
                runs = list_runs(limit=limit, offset=offset)
                # Parse raw JSON string if needed
                for r in runs:
                    raw_val = r.get("raw")
                    if isinstance(raw_val, str):
                        try:
                            r["raw"] = json.loads(raw_val)
                        except Exception:
                            pass
                return json_response(self, 200, runs)

            if parsed.path == "/tools/task":
                run_id = body.get("id")
                if not run_id or not isinstance(run_id, str):
                    return json_response(self, 400, {"detail": "id is required"})
                run = get_run(run_id)
                if not run:
                    return json_response(self, 404, {"detail": "run not found"})
                raw_val = run.get("raw")
                if isinstance(raw_val, str):
                    try:
                        run["raw"] = json.loads(raw_val)
                    except Exception:
                        pass
                return json_response(self, 200, run)

            return json_response(self, 404, {"detail": "not found"})
        except Exception as e:
            return json_response(self, 500, {"detail": "internal error", "error": str(e)})


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Serving MCP stdlib server on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()