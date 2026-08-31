"""ADK agents bound to the vendor-renewal close path.

The model does not invent savings. Tools call evaluate_offer / drive /
mailbox. A live Runner is optional and requires GOOGLE_API_KEY.
"""

from __future__ import annotations

from typing import Any, Mapping

from google.adk.agents import LlmAgent, SequentialAgent

from action.close_path import close_path, witnessed_close_path


def _pack(result) -> Mapping[str, Any]:
    export = result.export
    return {
        "fixture": export.get("fixture"),
        "disposition": export.get("disposition"),
        "offer_usd": export.get("offer_usd"),
        "term_months": export.get("term_months"),
        "savings_usd": export.get("metrics", {}).get("total_savings_usd"),
        "commitment_level": export.get("commitment_level"),
        "commitment_trigger": export.get("commitment_trigger"),
        "adversarial_check_scope": export.get("adversarial_check_scope"),
        "event_types": [event.get("event_type") for event in export.get("events", ())],
    }


def run_vendor_close(fixture: str = "easy_save") -> Mapping[str, Any]:
    """Run the default close path (EXECUTE_QUERY, no human_ack)."""
    return _pack(close_path(fixture))


def run_witnessed_close(fixture: str = "easy_save") -> Mapping[str, Any]:
    """Run MUTATE_STATE close path with an in-process granted human_ack."""
    return _pack(witnessed_close_path(fixture))


closer_agent = LlmAgent(
    name="vendor_closer",
    model="gemini-2.5-flash",
    description="Closes a vendor-renewal fixture through the audited ledger path.",
    instruction=(
        "Call run_vendor_close for a named fixture. "
        "Do not invent savings. Report only the tool result."
    ),
    tools=[run_vendor_close],
)

witness_agent = LlmAgent(
    name="witnessed_closer",
    model="gemini-2.5-flash",
    description="Closes a vendor-renewal fixture on the mandatory-escalation path.",
    instruction=(
        "Call run_witnessed_close when a human acknowledgement is part of the story. "
        "Do not invent savings. Report only the tool result."
    ),
    tools=[run_witnessed_close],
)

root_agent = SequentialAgent(
    name="negotiation_root",
    description="Runs the closer then the witnessed closer against the same wedge.",
    sub_agents=[closer_agent, witness_agent],
)
