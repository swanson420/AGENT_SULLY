from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import Any, List, Tuple
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
    Assumption,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.config import DEFAULT_CONFIG
from decision.triage_gate.ledger_client import (
    ConcreteLedgerClient,
    LedgerTransportConfig,
)
from decision.triage_gate.provenance import ProvenanceEngine
from decision.triage_gate.telemetry import TransportTelemetrySink
from decision.triage_gate.triage import TriagePipelineOrchestrator
from decision.triage_gate.stages.stage1_surfacing import StrictUnknownSurfacingStage
from decision.triage_gate.stages.stage2_resolvability import StrictResolvabilityStage
from decision.triage_gate.stages.stage3_blast_radius import StrictBlastRadiusStage
from decision.triage_gate.stages.stage4_routing import StrictRoutingStage
from decision.triage_gate.stages.stage5_audit import StrictAuditStage
from tests.decision.triage_gate.conftest import MockTransportDriver


def test_e2e_pipeline_telemetry_saturation_under_heavy_concurrency() -> None:
    """
    Control Invariant: 32 parallel worker threads dispatching end-to-end triage evaluations
    against a saturated fixed-capacity telemetry ring buffer must preserve zero-leakage,
    zero-deadlock, and clean atomic eviction metrics under high-throughput concurrency.
    """
    mock_driver = MockTransportDriver()
    telemetry_capacity = 256
    telemetry_sink = TransportTelemetrySink(capacity=telemetry_capacity)

    transport_config = LedgerTransportConfig(
        endpoint_url="https://ledger.internal:8443/v1",
        auth_token="calibrated_entropy_token_999",
        timeout_seconds=5.0,
        max_retries=2,
        backoff_factor=0.01,
        backoff_max_seconds=0.1,
        jitter_factor=1.0,
    )
    transport_config.validate()

    ledger_client = ConcreteLedgerClient(
        transport_config=transport_config,
        transport_driver=mock_driver,
        sleep_fn=lambda _: None,
        telemetry_sink=telemetry_sink,
    )

    orchestrator = TriagePipelineOrchestrator(
        surfacing_stage=StrictUnknownSurfacingStage(),
        resolvability_stage=StrictResolvabilityStage(),
        blast_radius_stage=StrictBlastRadiusStage(DEFAULT_CONFIG),
        routing_stage=StrictRoutingStage(DEFAULT_CONFIG),
        audit_stage=StrictAuditStage(),
        ledger=ledger_client,
        config=DEFAULT_CONFIG,
    )

    num_workers = 32
    evaluations_per_worker = 20
    total_evaluations = num_workers * evaluations_per_worker

    for i in range(total_evaluations):
        event_id = f"evt-sat-{i}"
        payload = {
            "worker_idx": i,
            "blast_radius": {
                "reversibility": "LOW",
                "cost": "LOW",
                "relationship_impact": "LOW",
                "commitment": "LOW",
                "external_visibility": "LOW",
            },
        }
        mock_driver.seed_event(event_id, payload)

    barrier = threading.Barrier(parties=num_workers)

    def worker_task(worker_id: int) -> List[Tuple[RouteType, str]]:
        worker_results = []
        barrier.wait(timeout=5.0)

        for j in range(evaluations_per_worker):
            idx = (worker_id * evaluations_per_worker) + j
            event_id = f"evt-sat-{idx}"
            payload = {
                "worker_idx": idx,
                "blast_radius": {
                    "reversibility": "LOW",
                    "cost": "LOW",
                    "relationship_impact": "LOW",
                    "commitment": "LOW",
                    "external_visibility": "LOW",
                },
            }

            context = WorkingContext(
                source_event_ids=(event_id,),
                raw_payload=payload,
                commitment_level="LOW",
                unknowns=(),
                assumptions=(
                    Assumption(
                        description="Grounded worker payload",
                        confidence=0.95,
                        grounded=True,
                    ),
                ),
            )

            route, record = orchestrator.execute(context, ActionType.QUERY_INFO)
            worker_results.append((route, record.audit_hash))

        return worker_results

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker_task, wid) for wid in range(num_workers)]
        all_results = []
        for f in as_completed(futures):
            all_results.extend(f.result())

    assert len(all_results) == total_evaluations
    for route, audit_hash in all_results:
        assert route == RouteType.ACT_SILENTLY
        assert len(audit_hash) == 64

    assert len(mock_driver.audit_records) == total_evaluations
    assert mock_driver.post_call_count == total_evaluations

    assert len(telemetry_sink.get_recent_events()) == telemetry_capacity
    stats = telemetry_sink.get_stats()
    assert stats["total_retries"] == 0
    assert stats["total_exhaustions"] == 0
