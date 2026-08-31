"""Exhaustive coverage of action/commitment_gradient.py's ordinal step
boundaries and mandatory-escalation condition.

No test doubles anywhere in this file: BlastRadiusScore, ActionType, and
TriageGateConfig are all real (frozen dataclass / Enum) instances -- there
is nothing here that would need mocking in the first place, since none of
classify_commitment_level's inputs are services with side effects.
"""

from decision.contracts.blast_radius import BlastRadiusScore
from decision.contracts.decision_package import ActionType
from decision.triage_gate.config import TriageGateConfig
from action.commitment_gradient import classify_commitment_level

ALL_DIMENSIONS = (
    "reversibility", "cost", "relationship_impact", "commitment", "external_visibility",
)


def _score(**overrides):
    base = {dim: "LOW" for dim in ALL_DIMENSIONS}
    base.update(overrides)
    return BlastRadiusScore(**base)


# --- Level 0: informational floor -------------------------------------

def test_query_info_all_low_is_level_0():
    assert classify_commitment_level(ActionType.QUERY_INFO, _score()) == 0


def test_query_info_informational_floor_requires_every_dimension_at_low():
    """The floor is not "QUERY_INFO gets a discount" -- it requires the
    blast radius to genuinely be at the ordinal minimum across all five
    dimensions. A single elevated dimension disqualifies it."""
    for dim in ALL_DIMENSIONS:
        result = classify_commitment_level(ActionType.QUERY_INFO, _score(**{dim: "MEDIUM"}))
        assert result == 2, (dim, result)


# --- Level 1: material floor for non-QUERY_INFO actions ----------------

def test_execute_query_all_low_is_level_1():
    assert classify_commitment_level(ActionType.EXECUTE_QUERY, _score()) == 1


def test_mutate_state_all_low_is_now_level_5():
    """As of the config fix reconciling stage4_routing.py's escalation
    set with conservative_defaults.py's silence_is_unsafe=True marking
    for MUTATE_STATE, this is no longer a level-1 ordinal-scale example --
    it's an escalation action like the other four. See
    test_every_mandatory_escalation_action_hits_level_5_even_at_minimal_blast_radius,
    which now includes it."""
    assert classify_commitment_level(ActionType.MUTATE_STATE, _score()) == 5


# --- Levels 2/3/4: exhaustive per-dimension ordinal scaling -------------
# Each of the 5 dimensions is tested independently at each ordinal step,
# to confirm max() over to_ordinal_map() genuinely reads every dimension
# and not just one hardcoded key. Uses EXECUTE_QUERY, not MUTATE_STATE --
# MUTATE_STATE is now in mandatory_escalation_actions (see config.py) and
# would always read 5 regardless of blast radius, which would silently
# stop testing the ordinal scale at all.

def test_each_dimension_at_medium_drives_level_2():
    for dim in ALL_DIMENSIONS:
        result = classify_commitment_level(ActionType.EXECUTE_QUERY, _score(**{dim: "MEDIUM"}))
        assert result == 2, (dim, result)


def test_each_dimension_at_high_drives_level_3():
    for dim in ALL_DIMENSIONS:
        result = classify_commitment_level(ActionType.EXECUTE_QUERY, _score(**{dim: "HIGH"}))
        assert result == 3, (dim, result)


def test_each_dimension_at_critical_drives_level_4():
    for dim in ALL_DIMENSIONS:
        result = classify_commitment_level(ActionType.EXECUTE_QUERY, _score(**{dim: "CRITICAL"}))
        assert result == 4, (dim, result)


def test_worst_dimension_wins_not_first_or_last():
    """reversibility LOW, external_visibility CRITICAL -> must read 4,
    not 1 (first dim) or default to whichever key happens to be scanned
    first/last in an unordered structure."""
    score = _score(reversibility="LOW", external_visibility="CRITICAL")
    assert classify_commitment_level(ActionType.EXECUTE_QUERY, score) == 4


# --- Level 5: mandatory escalation, exhaustive over all 5 action types --

def test_every_mandatory_escalation_action_hits_level_5_even_at_minimal_blast_radius():
    """The whole point of level 5 (per action/README.md's "independent of
    what blast-radius alone concluded") is that escalation actions can't
    buy their way down with a mild blast radius. All-LOW is the case most
    likely to expose that bug if it existed.

    5 actions now, not 4 -- MUTATE_STATE joined this set when config.py
    was fixed to match conservative_defaults.py's silence_is_unsafe=True
    classification for it (the two safety tables previously disagreed)."""
    for action in (
        ActionType.MUTATE_STATE,
        ActionType.TERMINATE_SYSTEM,
        ActionType.OVERRIDE_SECURITY,
        ActionType.DEPLOY_PAYLOAD,
        ActionType.PURGE_RECORDS,
    ):
        assert classify_commitment_level(action, _score()) == 5, action


def test_mandatory_escalation_action_hits_5_even_with_critical_blast_radius():
    """The two independent routes to a high level (escalation set,
    CRITICAL ordinal) should agree, not silently disagree."""
    assert classify_commitment_level(
        ActionType.PURGE_RECORDS, _score(cost="CRITICAL")
    ) == 5


def test_non_escalation_action_never_reaches_5_from_blast_radius_alone():
    """CRITICAL on every dimension for a non-escalation action still caps
    at 4 -- level 5 is reserved for the escalation set, not reachable by
    blast radius severity alone. Uses EXECUTE_QUERY, the one action left
    outside the (now 5-member) escalation set."""
    score = _score(**{dim: "CRITICAL" for dim in ALL_DIMENSIONS})
    assert classify_commitment_level(ActionType.EXECUTE_QUERY, score) == 4


# --- Config is actually read, not a hardcoded DEFAULT_CONFIG shortcut --

def test_custom_config_mandatory_escalation_set_is_respected():
    """Proves the function reads its config parameter rather than always
    checking the module-level DEFAULT_CONFIG.

    Uses EXECUTE_QUERY, not MUTATE_STATE -- MUTATE_STATE is now *also* in
    DEFAULT_CONFIG's escalation set (see config.py fix), so a version of
    this test using it would still pass even if the function silently
    ignored the injected config and fell back to DEFAULT_CONFIG. That
    would be a false pass. EXECUTE_QUERY is not in DEFAULT_CONFIG's set,
    so scoring it as 5 here is only possible if the custom config was
    actually consulted."""
    custom_config = TriageGateConfig(
        mandatory_escalation_actions=frozenset({ActionType.EXECUTE_QUERY})
    )
    assert classify_commitment_level(ActionType.EXECUTE_QUERY, _score(), custom_config) == 5
    # And TERMINATE_SYSTEM, not in this custom escalation set (even though
    # it is in DEFAULT_CONFIG's), is scored on the ordinal scale --
    # confirms the custom set fully replaces the default rather than
    # merging with it.
    assert classify_commitment_level(ActionType.TERMINATE_SYSTEM, _score(), custom_config) == 1


# --- Purity: no mutation of any input --------------------------------

def test_blast_radius_score_is_not_mutated():
    score = _score(cost="HIGH")
    snapshot = BlastRadiusScore(**{dim: getattr(score, dim) for dim in ALL_DIMENSIONS})
    classify_commitment_level(ActionType.EXECUTE_QUERY, score)
    assert score == snapshot


def test_default_config_is_not_mutated():
    from decision.triage_gate.config import DEFAULT_CONFIG
    snapshot_actions = frozenset(DEFAULT_CONFIG.mandatory_escalation_actions)
    classify_commitment_level(ActionType.QUERY_INFO, _score())
    assert DEFAULT_CONFIG.mandatory_escalation_actions == snapshot_actions


# --- Fail-closed: invalid blast radius is rejected, not silently scored -

def test_invalid_blast_radius_dimension_raises_rather_than_silently_scoring():
    bad_score = BlastRadiusScore(
        reversibility="NOT_A_REAL_LEVEL", cost="LOW", relationship_impact="LOW",
        commitment="LOW", external_visibility="LOW",
    )
    raised = False
    try:
        classify_commitment_level(ActionType.EXECUTE_QUERY, bad_score)
    except ValueError:
        raised = True
    assert raised, "expected ValueError from BlastRadiusScore.validate()"
