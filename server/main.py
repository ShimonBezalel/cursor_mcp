from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()

app = FastAPI(title="Example MCP Server", version="0.1.0")

# Static MCP manifest
MANIFEST: Dict[str, Any] = {
    "name": "example-mcp-server",
    "display_name": "Example MCP Server",
    "version": "0.1.0",
    "description": "Static manifest endpoint for MCP discovery.",
    "capabilities": {},
}


@app.get("/mcp", response_class=JSONResponse)
async def get_mcp_manifest() -> Dict[str, Any]:
    return MANIFEST