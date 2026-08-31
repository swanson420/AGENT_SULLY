from fastapi import FastAPI
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from infra.adk.agent_binding import root_agent

app = FastAPI(title="Agent Sully")


def _extract_text(events) -> str:
    for event in reversed(events):
        if getattr(event, "content", None) and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    return part.text
    return "no text content in final event"


@app.get("/close/{fixture}")
async def close(fixture: str = "easy_save"):
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="agent_sully", user_id="demo", session_id="demo"
    )
    runner = Runner(
        agent=root_agent, app_name="agent_sully", session_service=session_service
    )
    content = types.Content(
        role="user", parts=[types.Part(text=f"Close fixture {fixture}")]
    )
    events = [
        event
        async for event in runner.run_async(
            user_id="demo", session_id="demo", new_message=content
        )
    ]
    return {"fixture": fixture, "gemini_response": _extract_text(events)}
