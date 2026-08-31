"""≥3 dispatch requires a granted human_ack. Level 2 does not."""

from __future__ import annotations

import pytest

from action.close_path import (
    BASELINE_EVENT_ID,
    HUMAN_ACK_EVENT_ID,
    OFFER_EVENT_ID,
    close_path,
)
from action.dispatch_gate import ACK_THRESHOLD, DispatchBlocked, assert_dispatch_allowed
from action.human_ack import HumanAckRefused, write_human_ack
from ledger.ledger import Ledger


def _unused_aggregator(event_ids, lookup):
    return {}, ""


def test_level_below_threshold_does_not_need_ack():
    ledger = Ledger(aggregator=_unused_aggregator)
    assert_dispatch_allowed(2, ledger)


def test_level_at_threshold_without_ack_blocks():
    ledger = Ledger(aggregator=_unused_aggregator)
    with pytest.raises(DispatchBlocked) as blocked:
        assert_dispatch_allowed(ACK_THRESHOLD, ledger)
    assert blocked.value.commitment_level == ACK_THRESHOLD
    assert ledger.entries == ()


def test_granted_ack_opens_dispatch():
    ledger = Ledger(aggregator=_unused_aggregator)
    write_human_ack(ledger, HUMAN_ACK_EVENT_ID, granted=True)
    assert_dispatch_allowed(5, ledger)


def test_ungranted_ack_is_not_writable():
    ledger = Ledger(aggregator=_unused_aggregator)
    with pytest.raises(HumanAckRefused):
        write_human_ack(ledger, HUMAN_ACK_EVENT_ID, granted=False)
    assert ledger.entries == ()


def test_close_path_level_2_writes_offer_without_ack():
    result = close_path("easy_save", classify_fn=lambda: 2)
    types = [event["event_type"] for event in result.export["events"]]
    assert types[0] == "baseline"
    assert types[1] == "offer"
    assert OFFER_EVENT_ID in [event["event_id"] for event in result.export["events"]]


def test_close_path_level_4_without_ack_leaves_only_baseline():
    ledger = Ledger(aggregator=_unused_aggregator)
    with pytest.raises(DispatchBlocked):
        close_path("easy_save", ledger=ledger, classify_fn=lambda: 4)
    assert [entry["event_id"] for entry in ledger.entries] == [BASELINE_EVENT_ID]
    assert ledger.get_event(OFFER_EVENT_ID) is None


def test_close_path_level_4_with_ack_writes_offer_after_ack():
    result = close_path("easy_save", classify_fn=lambda: 4, grant_human_ack=True)
    types = [event["event_type"] for event in result.export["events"]]
    ids = [event["event_id"] for event in result.export["events"]]
    assert types[:5] == ["baseline", "human_ack", "offer", "offer_sent", "counterparty_reply"]
    assert ids[1] == HUMAN_ACK_EVENT_ID
    assert ids[2] == OFFER_EVENT_ID
    assert result.export["events"][2]["prev_hash"] == result.export["events"][1]["hash"]
    assert result.offer.commitment_level == 4
    assert result.disposition.name == "SETTLED"
