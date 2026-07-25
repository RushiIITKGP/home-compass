"""
Fetches the rules PDF from Google Drive via the @isaacphi/mcp-gdrive
MCP server (spawned with npx) — the same MultiServerMCPClient machinery
setup.py uses for the project's own servers. One-time OAuth setup in
compliance/README.md; the keys JSON lives in GDRIVE_CREDS_DIR and the
first run opens a browser to authorize.

Usage: python compliance/drive_fetch.py "fhas_part12_rules"
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent / "data"
_DRIVE_ID = r"[A-Za-z0-9_-]{20,}"  # Drive file ids are long; 20+ chars avoids matching words


def resolve_creds() -> dict:
    """Credentials for the MCP server. Reads client id/secret from
    gcp-oauth.keys.json in GDRIVE_CREDS_DIR when the .env vars aren't set,
    so setting GDRIVE_CREDS_DIR alone is enough."""
    creds_dir = Path(os.environ.get("GDRIVE_CREDS_DIR") or (Path.home() / ".gdrive-mcp"))
    client_id = os.environ.get("GDRIVE_CLIENT_ID", "")
    client_secret = os.environ.get("GDRIVE_CLIENT_SECRET", "")

    if not (client_id and client_secret):
        keys_file = creds_dir / "gcp-oauth.keys.json"
        if keys_file.exists():
            data = json.loads(keys_file.read_text())
            creds = data.get("installed") or data.get("web") or {}
            client_id = client_id or creds.get("client_id", "")
            client_secret = client_secret or creds.get("client_secret", "")

    return {"CLIENT_ID": client_id, "CLIENT_SECRET": client_secret, "GDRIVE_CREDS_DIR": str(creds_dir)}


def _as_text(payload) -> str:
    """MCP results come back either as a plain string or as a list of
    content blocks [{"type": "text", "text": ...}] — return the text."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        return "\n".join(
            item["text"] for item in payload
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return ""


async def fetch_pdf_from_drive(name_query: str) -> Path:
    """Search Drive for a PDF, download it into compliance/data/, return the path."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    servers = {"gdrive": {"command": "npx", "args": ["-y", "@isaacphi/mcp-gdrive"],
                          "transport": "stdio", "env": resolve_creds()}}
    tools = {t.name: t for t in await MultiServerMCPClient(servers).get_tools()}

    # Search -> pull the file id out of the text result. (Its own content-
    # block "id" is a LangChain artifact, not a Drive id — match on the
    # documented "name.pdf (id: XXXX)" shape instead.)
    search_text = _as_text(await tools["gdrive_search"].ainvoke({"query": name_query}))
    match = re.search(rf"(\S+\.pdf).*?\(id:\s*({_DRIVE_ID})\)", search_text, re.IGNORECASE)
    if not match:
        raise RuntimeError(f"no PDF matching {name_query!r} in Drive; search returned: {search_text[:300]}")
    file_name, file_id = match.group(1), match.group(2)

    # Read -> the PDF comes back base64-encoded (possibly after a header
    # line); grab the first base64 run that decodes to PDF bytes.
    read_text = _as_text(await tools["gdrive_read_file"].ainvoke({"fileId": file_id}))
    pdf_bytes = None
    for run in re.findall(r"[A-Za-z0-9+/=\s]{500,}", read_text) or [read_text]:
        try:
            decoded = base64.b64decode("".join(run.split()), validate=True)
        except Exception:
            continue
        if decoded.startswith(b"%PDF"):
            pdf_bytes = decoded
            break
    if pdf_bytes is None:
        raise RuntimeError(f"couldn't decode PDF from {file_name!r}; got: {read_text[:300]!r}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / file_name
    out_path.write_bytes(pdf_bytes)
    print(f"fetched {file_name} from Google Drive -> {out_path}")
    return out_path


if __name__ == "__main__":
    asyncio.run(fetch_pdf_from_drive(sys.argv[1] if len(sys.argv) > 1 else "fhas_part12_rules"))
