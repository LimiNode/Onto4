import pytest

from onto4.providers import (
    AbstentionPolicy,
    DecisionProfile,
    DeterministicDecisionPolicy,
    FixtureBatchDecisionProvider,
    FixtureDecisionProvider,
    TypedDecision,
)


def profile(*, abstention_policy=AbstentionPolicy.Allowed):
    return DecisionProfile(
        id="clarification-routing",
        version="2026-10-03",
        choices=("EnoughToFormalize", "NeedClarification", "NeedEvidence"),
        calibration_metadata={"bands": {"low": 0.4, "high": 0.8}},
        abstention_policy=abstention_policy,
    )


def test_profile_versions_request_schema_and_policy_consumption():
    decision_profile = profile()
    request = decision_profile.request("Is clarification needed?", state={"turn": 1})
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: TypedDecision(choice="NeedClarification", confidence=0.2)},
    )

    decision = provider.decide(request)

    assert request.profile == decision_profile.id
    assert request.profile_version == decision_profile.version
    assert request.choices == decision_profile.choices
    assert DeterministicDecisionPolicy(decision_profile).select(decision) == "NeedClarification"
    assert not hasattr(decision, "verdict")


def test_abstention_is_explicit_and_profile_scoped():
    decision_profile = profile()
    request = decision_profile.request("Choose a clarification")
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: TypedDecision(abstained=True, confidence=0.3)},
    )

    decision = provider.decide(request)

    assert decision.abstained is True
    assert DeterministicDecisionPolicy(decision_profile).select(decision) is None


def test_forbidden_abstention_fails_closed():
    decision_profile = profile(abstention_policy=AbstentionPolicy.Forbidden)
    request = decision_profile.request("Choose a clarification")
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: TypedDecision(abstained=True)},
    )

    with pytest.raises(ValueError, match="does not allow abstention"):
        provider.decide(request)


def test_profile_version_or_choice_schema_mismatch_fails_closed():
    decision_profile = profile()
    request = decision_profile.request("Choose a clarification")
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: TypedDecision(choice="NeedClarification")},
    )

    with pytest.raises(ValueError, match="profile"):
        provider.decide(
            request.__class__(
                profile=request.profile,
                profile_version="old",
                question=request.question,
                choices=request.choices,
            )
        )
    with pytest.raises(ValueError, match="profile"):
        provider.decide(
            request.__class__(
                profile=request.profile,
                profile_version=request.profile_version,
                question=request.question,
                choices=("NeedClarification",),
            )
        )


def test_batch_provider_supports_fan_out_over_shared_state():
    decision_profile = profile()
    requests = (
        decision_profile.request("Is meaning clear?", state={"turn": 2}),
        decision_profile.request("Is evidence sufficient?", state={"turn": 2}),
    )
    provider = FixtureBatchDecisionProvider(
        decision_profile,
        {
            requests[0].question: TypedDecision(choice="EnoughToFormalize"),
            requests[1].question: TypedDecision(choice="NeedEvidence"),
        },
    )

    decisions = provider.decide_many(requests)

    assert tuple(decision.choice for decision in decisions) == (
        "EnoughToFormalize",
        "NeedEvidence",
    )
    assert all(request.state == {"turn": 2} for request in requests)
