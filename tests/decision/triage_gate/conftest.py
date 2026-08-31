"""
Hermetic Test Harness Configuration & Shared Fixtures.

Guarantees function-scoped fixture isolation, prevents cross-test state leakage,
and provides standardized mock and concrete transport drivers for triage gate testing.
"""
from typing import Any, Dict, Generator, List, Mapping, Optional
from unittest.mock import MagicMock
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.config import DEFAULT_CONFIG, TriageGateConfig
from decision.triage_gate.ledger_client import (
    ConcreteLedgerClient,
    LedgerTransportConfig,
)
from decision.triage_gate.telemetry import TransportTelemetrySink
from decision.triage_gate.triage import TriagePipelineOrchestrator
from decision.triage_gate.stages.stage1_surfacing import StrictUnknownSurfacingStage
from decision.triage_gate.stages.stage2_resolvability import StrictResolvabilityStage
from decision.triage_gate.stages.stage3_blast_radius import StrictBlastRadiusStage
from decision.triage_gate.stages.stage4_routing import StrictRoutingStage
from decision.triage_gate.stages.stage5_audit import StrictAuditStage


class MockTransportDriver:
    """
    Hermetic transport driver simulating remote ledger RPC endpoints.
    Provides function-scoped state isolation with explicit resets.
    """

    def __init__(self) -> None:
        self.events_db: Dict[str, Mapping[str, Any]] = {}
        self.audit_records: List[str] = []
        self.fetch_call_count = 0
        self.post_call_count = 0
        self.simulated_fault: Optional[Exception] = None

    def reset(self) -> None:
        """Purges all in-memory database entries and execution counters."""
        self.events_db.clear()
        self.audit_records.clear()
        self.fetch_call_count = 0
        self.post_call_count = 0
        self.simulated_fault = None

    def seed_event(self, event_id: str, payload: Mapping[str, Any], precedents: Optional[Mapping[str, str]] = None) -> None:
        self.events_db[event_id] = {
            "event_id": event_id,
            "payload": payload,
            "precedents": precedents or {},
        }

    def fetch_event(self, endpoint: str, token: str, event_id: str, timeout: float) -> Optional[Mapping[str, Any]]:
        self.fetch_call_count += 1
        if self.simulated_fault:
            raise self.simulated_fault
        return self.events_db.get(event_id)

    def post_audit_record(self, endpoint: str, token: str, payload: str, timeout: float) -> bool:
        self.post_call_count += 1
        if self.simulated_fault:
            raise self.simulated_fault
        self.audit_records.append(payload)
        return True


@pytest.fixture
def mock_driver() -> Generator[MockTransportDriver, None, None]:
    """Provides a clean, function-scoped mock driver with mandatory pre/post resets."""
    driver = MockTransportDriver()
    driver.reset()
    yield driver
    driver.reset()


@pytest.fixture
def valid_transport_config() -> LedgerTransportConfig:
    """Provides a baseline, validated transport configuration."""
    config = LedgerTransportConfig(
        endpoint_url="https://ledger.internal:8443/v1",
        auth_token="calibrated_entropy_token_999",
        timeout_seconds=5.0,
        max_retries=2,
        backoff_factor=0.1,
        backoff_max_seconds=1.0,
        jitter_factor=1.0,
    )
    config.validate()
    return config


@pytest.fixture
def isolated_telemetry_sink() -> TransportTelemetrySink:
    """Provides a dedicated, non-shared telemetry sink instance for isolated metrics checking."""
    return TransportTelemetrySink(capacity=100)


@pytest.fixture
def concrete_ledger_client(
    valid_transport_config: LedgerTransportConfig,
    mock_driver: MockTransportDriver,
    isolated_telemetry_sink: TransportTelemetrySink,
) -> ConcreteLedgerClient:
    """Provides a ConcreteLedgerClient wired to the function-scoped mock driver and telemetry sink."""
    return ConcreteLedgerClient(
        transport_config=valid_transport_config,
        transport_driver=mock_driver,
        sleep_fn=lambda _: None,  # Zero-delay sleep for fast test execution
        telemetry_sink=isolated_telemetry_sink,
    )


@pytest.fixture
def standard_orchestrator(
    concrete_ledger_client: ConcreteLedgerClient,
) -> TriagePipelineOrchestrator:
    """Provides a fully wired 5-stage pipeline orchestrator using default configuration."""
    config = DEFAULT_CONFIG
    return TriagePipelineOrchestrator(
        surfacing_stage=StrictUnknownSurfacingStage(),
        resolvability_stage=StrictResolvabilityStage(),
        blast_radius_stage=StrictBlastRadiusStage(config),
        routing_stage=StrictRoutingStage(config),
        audit_stage=StrictAuditStage(),
        ledger=concrete_ledger_client,
        config=config,
    )
