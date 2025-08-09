import os
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from .db import get_runs, get_run_by_id, get_recent_prs, _resolve_db_path

# Load environment variables
load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Cursor Agents MCP")
APP_DESC = os.getenv("APP_DESC", "Expose scraped Cursor Agent runs and PRs as MCP tools")
DB_PATH = _resolve_db_path()

app = FastAPI(title=APP_NAME, description=APP_DESC, version="0.1.0")

class ListTasksBody(BaseModel):
    limit: Optional[int] = 25

class TaskBody(BaseModel):
    id: Optional[str] = None

class ReviewPRsBody(BaseModel):
    limit: Optional[int] = 20

@app.get("/mcp", response_class=JSONResponse)
async def mcp_manifest() -> Dict[str, Any]:
    return {
        "name": APP_NAME,
        "description": APP_DESC,
        "environment": {"db_path": DB_PATH},
        "tools": [
            {
                "name": "list_tasks",
                "description": "List recent Cursor Agent runs scraped from cursor.com/agents",
                "path": "/tools/list_tasks",
                "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
            },
            {
                "name": "task",
                "description": "Fetch one run by ID (or most recent if not specified)",
                "path": "/tools/task",
                "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
            },
            {
                "name": "review_prs",
                "description": "List recent PRs referenced by runs",
                "path": "/tools/review_prs",
                "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
            },
        ],
    }

@app.post("/tools/list_tasks")
async def list_tasks(body: ListTasksBody) -> Dict[str, Any]:
    limit = int(body.limit or 25)
    return {"content": get_runs(limit=limit)}

@app.post("/tools/task")
async def task(body: TaskBody) -> Dict[str, Any]:
    if body.id:
        return {"content": get_run_by_id(body.id)}
    runs = get_runs(limit=1)
    return {"content": runs[0] if runs else None}

@app.post("/tools/review_prs")
async def review_prs(body: ReviewPRsBody) -> Dict[str, Any]:
    limit = int(body.limit or 20)
    return {"content": get_recent_prs(limit=limit)}