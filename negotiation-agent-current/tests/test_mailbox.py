"""Sandbox mailbox: log + ledger. No other channel."""

from __future__ import annotations

import pytest

from action.mailbox import MailboxRefused, send_offer
from ledger.ledger import Ledger


def _unused_aggregator(event_ids, lookup):
    return {}, ""


def test_send_offer_appends_offer_sent():
    ledger = Ledger(aggregator=_unused_aggregator)
    record = send_offer(ledger, "evt-offer-sent-1", fixture="easy_save")
    assert record.message == "offer sent"
    assert record.channel == "sandbox_log"
    assert ledger.entries[0]["payload"]["event_type"] == "offer_sent"


def test_smtp_channel_is_refused():
    ledger = Ledger(aggregator=_unused_aggregator)
    with pytest.raises(MailboxRefused):
        send_offer(ledger, "evt-offer-sent-1", channel="smtp")
    assert ledger.entries == ()
