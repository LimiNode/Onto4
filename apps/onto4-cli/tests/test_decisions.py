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


def decision(decision_profile, *, choice=None, abstained=False, confidence=None, **identity):
    return TypedDecision(
        profile_id=identity.get("profile_id", decision_profile.id),
        profile_version=identity.get("profile_version", decision_profile.version),
        choice=choice,
        abstained=abstained,
        confidence=confidence,
    )


def test_profile_versions_request_schema_and_low_confidence_signal_is_consumable():
    decision_profile = profile()
    request = decision_profile.request("Is clarification needed?", state={"turn": 1})
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, choice="NeedClarification", confidence=0.2)},
    )

    result = provider.decide(request)

    assert request.profile == decision_profile.id
    assert request.profile_version == decision_profile.version
    assert request.choices == decision_profile.choices
    assert DeterministicDecisionPolicy(decision_profile).select(result) == "NeedClarification"
    assert not hasattr(result, "verdict")


def test_abstention_is_explicit_and_profile_scoped():
    decision_profile = profile()
    request = decision_profile.request("Choose a clarification")
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, abstained=True, confidence=0.3)},
    )

    result = provider.decide(request)

    assert result.abstained is True
    assert DeterministicDecisionPolicy(decision_profile).select(result) is None


def test_forbidden_abstention_fails_closed():
    decision_profile = profile(abstention_policy=AbstentionPolicy.Forbidden)
    request = decision_profile.request("Choose a clarification")
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, abstained=True)},
    )

    with pytest.raises(ValueError, match="does not allow abstention"):
        provider.decide(request)


def test_profile_version_or_choice_schema_mismatch_fails_closed():
    decision_profile = profile()
    request = decision_profile.request("Choose a clarification")
    provider = FixtureDecisionProvider(
        decision_profile,
        {request.question: decision(decision_profile, choice="NeedClarification")},
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


def test_invalid_abstention_shapes_fail_closed():
    decision_profile = profile()

    with pytest.raises(ValueError, match="choice"):
        decision_profile.validate(
            decision(decision_profile, choice=None, abstained=False)
        )
    with pytest.raises(ValueError, match="abstained"):
        decision_profile.validate(
            decision(decision_profile, choice="NeedEvidence", abstained=True)
        )


def test_missing_or_wrong_decision_profile_provenance_fails_closed():
    decision_profile = profile()

    with pytest.raises(ValueError, match="profile"):
        decision_profile.validate(
            TypedDecision(
                profile_id=None,
                profile_version=None,
                choice="NeedClarification",
            )
        )
    with pytest.raises(ValueError, match="profile"):
        decision_profile.validate(
            decision(decision_profile, choice="NeedClarification", profile_id="other")
        )
    with pytest.raises(ValueError, match="version"):
        decision_profile.validate(
            decision(decision_profile, choice="NeedClarification", profile_version="old")
        )


def test_same_choice_schema_under_another_profile_is_not_accepted():
    decision_profile = profile()
    other_profile = DecisionProfile(
        id="other-profile",
        version=decision_profile.version,
        choices=decision_profile.choices,
    )
    with pytest.raises(ValueError, match="profile"):
        decision_profile.validate(
            decision(other_profile, choice="NeedClarification")
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
            requests[0].question: decision(decision_profile, choice="EnoughToFormalize"),
            requests[1].question: decision(decision_profile, choice="NeedEvidence"),
        },
    )

    decisions = provider.decide_many(requests)

    assert tuple(decision.choice for decision in decisions) == (
        "EnoughToFormalize",
        "NeedEvidence",
    )
    assert all(request.state == {"turn": 2} for request in requests)


def test_batch_provider_rejects_mixed_state():
    decision_profile = profile()
    requests = (
        decision_profile.request("q1", state={"turn": 1}),
        decision_profile.request("q2", state={"turn": 2}),
    )
    provider = FixtureBatchDecisionProvider(
        decision_profile,
        {
            "q1": decision(decision_profile, choice="EnoughToFormalize"),
            "q2": decision(decision_profile, choice="NeedEvidence"),
        },
    )

    with pytest.raises(ValueError, match="shared state"):
        provider.decide_many(requests)
