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

# ADK/Gemini imports are deferred to the request handler (see /agent/run/{fixture})
# so a missing google-adk install or missing Vertex/Gemini credentials fails that
# one route instead of the whole app at import time.

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
        <h2>Live Gemini/ADK call (actually invokes the model)</h2>
        <ul><li><a href="/agent/run/easy_save">/agent/run/easy_save</a></li></ul>
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


@app.get("/agent/run/{fixture}")
async def run_agent(fixture: str, witnessed: bool = False):
    """Actually invoke Gemini through the ADK agent binding (infra/adk/agent_binding.py).

    Distinct from /demo/{fixture}: that route calls close_path() directly.
    This route runs the LlmAgent, which calls run_vendor_close/run_witnessed_close
    (thin wrappers around the same close_path pipeline) as a *tool* -- so the
    numbers are identical, but the model actually has to be reached to get them.
    """
    if fixture not in VALID_FIXTURES:
        raise HTTPException(
            status_code=404,
            detail=f"unknown fixture {fixture!r}; valid: {list(VALID_FIXTURES)}",
        )

    try:
        from google.genai import types
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        from infra.adk.agent_binding import closer_agent, witness_agent
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"ADK not available in this deployment: {exc}",
        ) from exc

    agent = witness_agent if witnessed else closer_agent
    app_name = "negotiation-agent-demo"
    user_id = "demo-user"

    session_service = InMemorySessionService()
    try:
        session = await session_service.create_session(app_name=app_name, user_id=user_id)
        runner = Runner(agent=agent, app_name=app_name, session_service=session_service)

        prompt = f"Close the {fixture!r} fixture."
        if witnessed:
            prompt += " Use the witnessed/mandatory-escalation path."
        message = types.Content(role="user", parts=[types.Part(text=prompt)])

        events = []
        final_text = None
        async for event in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=message
        ):
            ev = {"author": event.author, "is_final_response": event.is_final_response()}
            calls = event.get_function_calls()
            responses = event.get_function_responses()
            if calls:
                ev["function_calls"] = [
                    {"name": c.name, "args": dict(c.args or {})} for c in calls
                ]
            if responses:
                ev["function_responses"] = [
                    {"name": r.name, "response": r.response} for r in responses
                ]
            if event.content and event.content.parts:
                texts = [p.text for p in event.content.parts if getattr(p, "text", None)]
                if texts:
                    ev["text"] = "".join(texts)
                    if event.is_final_response():
                        final_text = ev["text"]
            events.append(ev)
    except Exception as exc:  # surface auth/quota/model errors as evidence, not a 500 traceback dump
        raise HTTPException(status_code=502, detail=f"Gemini/ADK call failed: {exc}") from exc

    return JSONResponse(
        content=json.loads(
            json.dumps(
                {
                    "fixture": fixture,
                    "witnessed": witnessed,
                    "agent": agent.name,
                    "model": agent.model,
                    "final_response": final_text,
                    "events": events,
                },
                default=str,
            )
        )
    )


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
