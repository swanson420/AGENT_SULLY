"""Cloud Run entrypoint: HTTP wrapper around the existing close_path pipeline.

Serves the same deterministic replay the submission-pack demonstrates
(PYTHONPATH=. python -m action.close_path <fixture>) over HTTP, plus the
frozen demo packs from submission-pack/ for side-by-side comparison. No
new pipeline logic lives here -- this only exposes what action/close_path.py
already computes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from action.close_path import close_path, witnessed_close_path
from scenarios.vendor_renewal.scenario import VALID_FIXTURES

app = FastAPI(title="Negotiation Agent - Vendor Renewal PoV")

SUBMISSION_PACK_DIR = Path(__file__).resolve().parent.parent / "submission-pack"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    fixture_links = "".join(
        f'<li><a href="/demo/{f}">/demo/{f}</a></li>' for f in VALID_FIXTURES
    )
    return f"""
    <html>
      <head><title>Negotiation Agent - Vendor Renewal PoV</title></head>
      <body style="font-family: sans-serif; max-width: 720px; margin: 40px auto;">
        <h1>Negotiation Agent &mdash; Vendor Renewal PoV</h1>
        <p>Governed close of one B2B SaaS renewal. Every dollar on the pack is
        computed from ledger events; nothing is invented.</p>
        <h2>Live replay (runs the actual pipeline now)</h2>
        <ul>{fixture_links}
          <li><a href="/demo/easy_save?witnessed=true">/demo/easy_save?witnessed=true</a></li>
        </ul>
        <h2>Frozen submission packs</h2>
        <ul><li><a href="/packs">/packs</a></li></ul>
        <p><a href="/health">/health</a></p>
      </body>
    </html>
    """


@app.get("/demo/{fixture}")
def run_demo(fixture: str, witnessed: bool = False):
    if fixture not in VALID_FIXTURES:
        raise HTTPException(
            status_code=404,
            detail=f"unknown fixture {fixture!r}; valid: {list(VALID_FIXTURES)}",
        )
    result = witnessed_close_path(fixture) if witnessed else close_path(fixture)
    return JSONResponse(content=json.loads(json.dumps(result.export, default=str)))


@app.get("/packs")
def list_packs():
    if not SUBMISSION_PACK_DIR.is_dir():
        return {"packs": []}
    return {
        "packs": sorted(
            p.name for p in SUBMISSION_PACK_DIR.glob("demo-*.json")
        )
    }


@app.get("/packs/{name}")
def read_pack(name: str):
    path = SUBMISSION_PACK_DIR / name
    if not path.is_file() or path.suffix != ".json" or not path.name.startswith("demo-"):
        raise HTTPException(status_code=404, detail="pack not found")
    return JSONResponse(content=json.loads(path.read_text()))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
