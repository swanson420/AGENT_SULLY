"""ADK agents exist and their tools run the real close path."""

from __future__ import annotations

from infra.adk.agent_binding import (
    closer_agent,
    root_agent,
    run_vendor_close,
    run_witnessed_close,
    witness_agent,
)


def test_adk_agents_are_real_instances():
    from google.adk.agents import LlmAgent, SequentialAgent

    assert isinstance(closer_agent, LlmAgent)
    assert isinstance(witness_agent, LlmAgent)
    assert isinstance(root_agent, SequentialAgent)
    assert closer_agent.name == "vendor_closer"
    assert witness_agent.name == "witnessed_closer"
    assert [agent.name for agent in root_agent.sub_agents] == [
        "vendor_closer",
        "witnessed_closer",
    ]


def test_vendor_close_tool_hits_real_ledger_path():
    pack = run_vendor_close("easy_save")
    assert pack["disposition"] == "SETTLED"
    assert pack["savings_usd"] == 8000
    assert pack["commitment_trigger"] == "none"
    assert pack["adversarial_check_scope"] == "synthetic_offer_text"
    assert pack["event_types"] == ["baseline", "offer", "offer_sent", "settlement"]


def test_witnessed_close_tool_uses_mandatory_escalation():
    pack = run_witnessed_close("easy_save")
    assert pack["disposition"] == "SETTLED"
    assert pack["savings_usd"] == 8000
    assert pack["commitment_level"] == 5
    assert pack["commitment_trigger"] == "mandatory_escalation"
    assert pack["event_types"][:4] == ["baseline", "human_ack", "offer", "offer_sent"]
