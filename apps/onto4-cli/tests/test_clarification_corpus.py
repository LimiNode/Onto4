from pathlib import Path

from onto4.core import (
    AssessmentContext,
    OntologyProfile,
    PredicateCall,
    PredicateExpr,
    PredicateSignature,
    Verdict,
)
from onto4.core.evidence import AtomicVerdictStore
from onto4.pipeline import (
    ClarificationSession,
    answer_reasoning_clarification,
    build_clarification_request,
    issue_reasoning_clarification,
    load_clarification_corpus,
    reassess_reasoning_session_per_reading,
    start_reasoning_session_per_reading,
)
from onto4.providers import (
    AbstentionPolicy,
    DecisionProfile,
    FixtureDecisionProvider,
    FormalizationRequest,
    TypedDecision,
)
from onto4.reasoning import (
    ConceptualDepth,
    CrossCandidateStatus,
    FixtureClarificationPolicy,
    FormalizationCandidate,
    InterpretationSpace,
    SemanticReading,
)


ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "eval/clarification/corpus.yaml"
EPISTEMIC_CORPUS = ROOT / "eval/clarification/epistemic-ontology-v1.yaml"


def test_clarification_corpus_loads_and_hides_oracle_fields_from_public_input():
    corpus = load_clarification_corpus(CORPUS)

    assert corpus.version == 1
    assert corpus.model_input == "utterance_only"
    assert len(corpus.cases) == 13
    assert len({case.case_id for case in corpus.cases}) == len(corpus.cases)
    assert any(case.expected_clarification is None for case in corpus.cases)
    for case in corpus.cases:
        public = case.public_input()
        assert "utterance" in public
        assert "hidden_interpretation" not in public
        assert "expected_clarification" not in public
        assert "expected_after_answer" not in public
        assert "context" not in public


def test_epistemic_ontology_corpus_is_recorded_and_hides_its_oracle():
    corpus = load_clarification_corpus(EPISTEMIC_CORPUS)

    assert corpus.version == 1
    assert corpus.name == "epistemic-ontology-v1"
    assert corpus.model_input == "utterance_only"
    assert len(corpus.cases) == 27
    assert len({case.case_id for case in corpus.cases}) == 27
    assert sum(
        case.expected_clarification is not None for case in corpus.cases
    ) >= 8
    assert any(
        case.expected_after_answer.get("verdict") == "U"
        for case in corpus.cases
    )
    assert any(
        case.expected_after_answer.get("verdict") == "C"
        for case in corpus.cases
    )
    assert any(
        case.expected_after_answer.get("reason_family")
        == "ontology_commitment"
        for case in corpus.cases
    )
    dialogue_cases = [
        case for case in corpus.cases if case.case_id == "genetic-essentialism-dialogue"
    ]
    assert len(dialogue_cases) == 1
    assert dialogue_cases[0].context == "identity_and_genome"
    assert dialogue_cases[0].expected_after_answer["disposition"] == (
        "dialogue_reassessment_required"
    )
    for case in corpus.cases:
        public = case.public_input()
        assert public["utterance"] == case.utterance
        assert "evaluation_class" not in public
        assert "expected_clarification" not in public
        assert "expected_after_answer" not in public
        assert "oracle_notes" not in public
        assert "context" not in public


def test_contextual_visibility_explicitly_allows_context(tmp_path):
    corpus_path = tmp_path / "contextual.yaml"
    corpus_path.write_text(
        """
version: 1
name: contextual
visibility:
  model_input: contextual
cases:
  - case_id: one
    utterance: claim
    context: supplied-context
    expected_after_answer: {}
""",
        encoding="utf-8",
    )

    corpus = load_clarification_corpus(corpus_path)

    assert corpus.model_input == "contextual"
    assert corpus.cases[0].public_input() == {
        "utterance": "claim",
        "context": "supplied-context",
    }


class CorpusFormalizationProvider:
    def __init__(self):
        self.requests = []

    def formalize(self, request: FormalizationRequest):
        self.requests.append(request)
        assert request.reading is not None
        expression_name = (
            "closed_position"
            if request.reading.label == "closed_position"
            else "locked"
        )
        return (
            FormalizationCandidate(
                id=f"candidate:{request.reading.id}:{request.context_id}",
                label=request.reading.label,
                formalization_id=f"formal:{request.reading.id}",
                context_id=request.context_id,
                formalization=PredicateExpr(PredicateCall(expression_name, ())),
                reading_id=request.reading.id,
            ),
        )


def _profile() -> DecisionProfile:
    return DecisionProfile(
        id="corpus",
        version="1",
        choices=(
            "NeedMeaningClarification",
            "NeedOntologyClarification",
            "NeedReferenceClarification",
            "NeedContextClarification",
            "NeedPresuppositionClarification",
            "NeedFormalizationClarification",
        ),
        abstention_policy=AbstentionPolicy.Allowed,
    )


def test_corpus_fixture_runs_conflict_answer_and_explicit_reassessment():
    initial = InterpretationSpace(
        id="corpus-initial",
        source_text="Дверь закрыта.",
        conceptual_depth=ConceptualDepth.Ordinary,
        readings=(
            SemanticReading("reading-0", "closed_position", "полотно не открыто"),
            SemanticReading("reading-1", "locked", "замок препятствует открытию"),
        ),
    )
    successor = InterpretationSpace(
        id="corpus-successor",
        source_text=initial.source_text,
        conceptual_depth=initial.conceptual_depth,
        readings=(initial.readings[0],),
    )
    contexts = {
        "physical_objects": AssessmentContext(
            ontology=OntologyProfile(
                name="physical_objects",
                predicates={
                    "closed_position": PredicateSignature(()),
                    "locked": PredicateSignature(()),
                },
            ),
            verdicts=AtomicVerdictStore(
                {"closed_position()": Verdict.T, "locked()": Verdict.F}
            ),
        )
    }
    provider = CorpusFormalizationProvider()
    policy = FixtureClarificationPolicy(
        transitions={
            ("corpus-initial", "meaning:formalization", "reading-0"): successor
        }
    )
    initial_result = start_reasoning_session_per_reading(
        ClarificationSession(initial),
        formalization_provider=provider,
        contexts=contexts,
        clarification_policy=policy,
    )

    assessment = initial_result.session.assessment
    assert assessment is not None
    assert assessment.ask_result.landscape.status is CrossCandidateStatus.FormalizationConflict
    decision_profile = _profile()
    request = build_clarification_request(
        assessment.clarification_context(), decision_profile
    )
    decision_provider = FixtureDecisionProvider(
        decision_profile,
        {
            request.question: TypedDecision(
                profile_id=decision_profile.id,
                profile_version=decision_profile.version,
                choice="NeedMeaningClarification",
            )
        },
    )
    issued = issue_reasoning_clarification(
        initial_result.session,
        profile=decision_profile,
        provider=decision_provider,
        clarification_policy=policy,
    )
    assert issued.session.clarification.pending is not None
    answered = answer_reasoning_clarification(
        issued.session,
        answer="reading-0",
        clarification_policy=policy,
    )
    assert answered.session.clarification.interpretation is successor
    assert answered.session.assessment is None

    reassessed = reassess_reasoning_session_per_reading(
        answered.session,
        formalization_provider=provider,
        contexts=contexts,
        clarification_policy=policy,
    )
    assert reassessed.session.assessment is not None
    assert reassessed.session.assessment.ask_result.landscape.status is CrossCandidateStatus.StableAcrossCandidates
    assert reassessed.session.assessment.ask_result.disposition.value == "Complete"
    assert len(provider.requests) == 3
