import os
import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .db import list_runs, get_run, DB_PATH

app = FastAPI(title="Cursor Agents MCP Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"]
    ,
    allow_headers=["*"]
)


class ListTasksRequest(BaseModel):
    limit: int = 100
    offset: int = 0


class TaskRequest(BaseModel):
    id: str


@app.get("/mcp")
async def mcp_manifest() -> Dict[str, Any]:
    return {
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
                    "properties": {
                        "id": {"type": "string"}
                    },
                    "required": ["id"]
                }
            }
        ]
    }


@app.post("/tools/list_tasks")
async def list_tasks_endpoint(body: ListTasksRequest) -> JSONResponse:
    runs = list_runs(limit=body.limit, offset=body.offset)
    # Ensure raw is parsed JSON if it looks like JSON text
    for r in runs:
        raw_val = r.get("raw")
        if isinstance(raw_val, str):
            try:
                r["raw"] = json.loads(raw_val)
            except Exception:
                pass
    return JSONResponse(content=runs)


@app.post("/tools/task")
async def task_endpoint(body: TaskRequest) -> JSONResponse:
    run = get_run(body.id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    raw_val = run.get("raw")
    if isinstance(raw_val, str):
        try:
            run["raw"] = json.loads(raw_val)
        except Exception:
            pass
    return JSONResponse(content=run)


@app.get("/")
async def root() -> Dict[str, Any]:
    return {"status": "ok", "db_path": DB_PATH, "message": "See /mcp and /tools endpoints"}