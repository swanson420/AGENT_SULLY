"""Sandbox mailbox — log and ledger only. No SMTP."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from action.settlement import AppendLedger

EVENT_TYPE = "offer_sent"
CHANNEL_SANDBOX = "sandbox_log"

logger = logging.getLogger("negotiation.mailbox")


class MailboxRefused(ValueError):
    """Unverified send observation — do not persist."""


@dataclass(frozen=True)
class MailboxRecord:
    event_type: str
    channel: str
    message: str
    evidence_event_ids: Tuple[str, ...]
    fixture: Optional[str]

    def to_payload(self) -> Mapping[str, Any]:
        return asdict(self)


def evaluate_send(
    *,
    channel: Any = CHANNEL_SANDBOX,
    message: str = "offer sent",
    evidence_event_ids: Sequence[str] = (),
    fixture: Optional[str] = None,
) -> MailboxRecord:
    if channel != CHANNEL_SANDBOX:
        raise MailboxRefused(f"unsupported mailbox channel: {channel!r}")
    if message != "offer sent":
        raise MailboxRefused("sandbox mailbox only records 'offer sent'")
    return MailboxRecord(
        event_type=EVENT_TYPE,
        channel=CHANNEL_SANDBOX,
        message=message,
        evidence_event_ids=tuple(str(item) for item in evidence_event_ids),
        fixture=fixture,
    )


def send_offer(
    ledger: AppendLedger,
    event_id: str,
    **kwargs: Any,
) -> MailboxRecord:
    record = evaluate_send(**kwargs)
    logger.info("%s channel=%s fixture=%s", record.message, record.channel, record.fixture)
    ledger.append(event_id, record.to_payload())
    return record
