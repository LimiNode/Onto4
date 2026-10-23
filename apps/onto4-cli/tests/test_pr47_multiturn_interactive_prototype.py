import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
import sys

from onto4.core import (
    AssessmentContext,
    AtomicVerdictStore,
    OntologyProfile,
    PredicateCall,
    PredicateExpr,
    PredicateSignature,
    Verdict,
)
from onto4.providers import FormalizationRequest, InterpretationRequest
from onto4.reasoning import (
    Ambiguity,
    ConceptualDepth,
    FormalizationCandidate,
    InterpretationSpace,
    SemanticReading,
)


_SCRIPT_PATH = Path(__file__).parents[1] / "research" / "pr47_multiturn_interactive_prototype.py"
_SPEC = importlib.util.spec_from_file_location("pr47_multiturn_interactive_prototype", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_SCRIPT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCRIPT
_SPEC.loader.exec_module(_SCRIPT)


def _context() -> AssessmentContext:
    return AssessmentContext(
        ontology=OntologyProfile(
            name="identity",
            predicates={"identity_claim": PredicateSignature(())},
        ),
        verdicts=AtomicVerdictStore({"identity_claim()": Verdict.T}),
    )


def _space(identifier: str, *, ambiguous: bool) -> InterpretationSpace:
    return InterpretationSpace(
        id=identifier,
        source_text="Claim.",
        conceptual_depth=ConceptualDepth.Ordinary,
        ambiguities=(
            (Ambiguity("ambiguity-0", "identity", "identity criterion"),)
            if ambiguous
            else ()
        ),
        readings=(SemanticReading("reading-0", "identity", "identity claim"),),
    )


class _InterpretationProvider:
    def __init__(self, initial: InterpretationSpace):
        self.initial = initial

    def interpret(self, request: InterpretationRequest) -> InterpretationSpace:
        assert request.source_text == self.initial.source_text
        return self.initial


class _FormalizationProvider:
    def formalize(self, request: FormalizationRequest):
        return (
            FormalizationCandidate(
                id=f"candidate:{request.interpretation.id}",
                label="identity",
                formalization_id="identity-formalization",
                context_id="identity",
                reading_id="reading-0",
                formalization=PredicateExpr(PredicateCall("identity_claim", ())),
            ),
        )


@dataclass
class _RefinementProvider:
    successor: InterpretationSpace
    calls: int = 0

    def refine(self, interpretation, question, answer):
        self.calls += 1
        assert interpretation.id == "initial"
        assert answer == "I mean numerical identity."
        return self.successor


def _run(refinement, answers, *, max_turns=3):
    return _SCRIPT.run_bounded_dialogue(
        source_text="Claim.",
        interpretation_provider=_InterpretationProvider(_space("initial", ambiguous=True)),
        refinement_provider=refinement,
        formalization_provider=_FormalizationProvider(),
        contexts={"identity": _context()},
        answer_input=lambda _prompt: next(answers),
        output_fn=lambda _line: None,
        max_turns=max_turns,
    )


def test_multiturn_runner_accepts_real_answer_and_reports_vector_reduction():
    refinement = _RefinementProvider(_space("successor", ambiguous=False))
    answer = "I mean numerical identity."
    artifact = _run(refinement, iter((answer,)))

    assert refinement.calls == 1
    assert artifact["answers_consumed"] == 1
    assert artifact["turns"] == 1
    assert artifact["stop_reason"] == "complete"
    assert artifact["uncertainty_delta"]["ambiguity_count_delta"] == -1
    assert artifact["uncertainty_delta"]["structural_open_count_delta"] == -1
    assert artifact["uncertainty_delta"]["observed_reduction"] == "structural"
    assert artifact["progress"][0]["kind"] == "structural_resolution"
    assert answer not in json.dumps(artifact, ensure_ascii=False)
    assert artifact["provider_payloads_recorded"] is False
    assert artifact["production_admission_changed"] is False
    assert artifact["semantic_adjudication_receipt_created"] is False


def test_multiturn_runner_is_bounded_and_does_not_claim_semantic_identity():
    refinement = _RefinementProvider(_space("successor", ambiguous=False))
    artifact = _run(refinement, iter(("I mean numerical identity.",)))

    assert artifact["semantic_identity"] == "not_evaluated"
    assert len(artifact["uncertainty_trace"]) == 2
    assert artifact["uncertainty_trace"][0]["ambiguity_count"] == 1
    assert artifact["uncertainty_trace"][-1]["ambiguity_count"] == 0
    assert artifact["final"]["disposition"] == "Complete"


def test_multiturn_runner_stops_at_host_turn_bound():
    successor = InterpretationSpace(
        id="successor-open",
        source_text="Claim.",
        conceptual_depth=ConceptualDepth.Ordinary,
        ambiguities=(Ambiguity("ambiguity-0", "identity", "still open, refined"),),
        readings=(SemanticReading("reading-0", "identity", "identity claim"),),
    )
    artifact = _run(
        _RefinementProvider(successor),
        iter(("I mean numerical identity.",)),
        max_turns=1,
    )

    assert artifact["answers_consumed"] == 1
    assert artifact["turns"] == 1
    assert artifact["stop_reason"] == "max_turns_reached"
    assert artifact["final"]["ambiguity_count"] == 1
    assert artifact["uncertainty_delta"]["observed_reduction"] == "none_observed"


def test_redaction_helpers_remain_closed_for_multiturn_events():
    safe = _SCRIPT._event_payload(
        _SCRIPT.ProviderStageEvent(
            "private-stage",
            "private-phase",
            float("nan"),
            "PRIVATE_MODEL_OUTPUT",
        )
    )
    assert safe == {
        "stage": "unknown",
        "phase": "unknown",
        "elapsed_seconds": 0.0,
        "detail": "",
    }
    assert _SCRIPT._safe_endpoint("https://user:secret@example.test/v1") == (
        "https://example.test"
    )
    assert _SCRIPT._safe_model(
        r"F:\\AI\\models\\bonsai2-27b\\Ternary-Bonsai-2-27B-PQ2_0.gguf"
    ) == "Ternary-Bonsai-2-27B-PQ2_0.gguf"
