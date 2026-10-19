import json
from pathlib import Path

import pytest

from onto4.cli.main import main
from onto4.core import PredicateCall, PredicateExpr, Term
from onto4.pipeline import (
    ModelCaseExecutor,
    host_semantic_target_bindings,
    load_clarification_corpus,
    load_semantic_target_catalog,
)
from onto4.pipeline.model_evaluation import _ReplayPolicy
from onto4.pipeline.clarification_corpus import ClarificationCorpusCase
from onto4.pipeline.evaluation import EvaluationOutcome
from onto4.providers import (
    FixtureFormalizationProvider,
    FixtureInterpretationProvider,
    InterpretationRequest,
    OpenAICompatibleInterpretationProvider,
    ProviderTransportError,
)
from onto4.providers.diagnostics import ProviderStageEvent
from onto4.reasoning import (
    Ambiguity,
    ClarificationKind,
    ClarificationQuestion,
    ConceptualDepth,
    FormalizationCandidate,
    InterpretationSpace,
    SemanticReading,
)
from onto4.pipeline.loaders import load_context


ROOT = Path(__file__).parents[1]


def _case(*, mode="single_pass"):
    return ClarificationCorpusCase(
        case_id="safe-case",
        utterance="What is the mass of integer 7?",
        context="physical_objects",
        hidden_interpretation={"secret": "not for receipts"},
        expected_clarification=None,
        expected_after_answer={"verdict": "C"},
        mode=mode,
    )


def _executor():
    context = load_context(ROOT / "profiles/contexts/physical_objects.yaml")
    interpretation = InterpretationSpace(
        "safe-space",
        "What is the mass of integer 7?",
        ConceptualDepth.Ordinary,
    )
    candidate = FormalizationCandidate(
        "mass",
        "mass of integer 7",
        "has-mass",
        "physical_objects",
        # The fixture provider is used only to exercise the host runner seam.
        None,
    )
    return ModelCaseExecutor(
        FixtureInterpretationProvider({("What is the mass of integer 7?", None): interpretation}),
        FixtureFormalizationProvider({"safe-space": (candidate,)}),
        {"physical_objects": context},
    )


def test_model_case_executor_records_safe_outcome_without_payloads():
    execution = _executor()(_case(), request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.CLARIFICATION_REQUESTED
    assert execution.semantic_verdict is None
    assert execution.detail_code == "model_backed"


def test_replay_telemetry_does_not_call_empty_candidates_generated():
    telemetry = {}

    class EmptyPolicy:
        def questions(self, _context):
            return ()

    policy = _ReplayPolicy(EmptyPolicy(), telemetry=telemetry)
    assert policy.questions(object()) == ()
    assert telemetry["question_candidate_generated"] is False
    assert telemetry["question_candidate_count"] == 0


def test_replay_admission_is_counted_once_for_selection_and_validation():
    question = ClarificationQuestion(
        "meaning:ambiguity-0",
        ClarificationKind.Meaning,
        "Clarify",
        ("ambiguity-0",),
        target_family="mass",
    )
    telemetry = {}
    policy = _ReplayPolicy(
        type("Base", (), {"questions": lambda self, _context: (question,)})(),
        expected_intents=(
            type("Intent", (), {
                "kind": ClarificationKind.Meaning,
                "target_family": "mass",
                "target_ids": ("ambiguity-0",),
            })(),
        ),
        telemetry=telemetry,
    )
    assert policy.questions(object()) == (question,)
    policy.record_question_selected(question)
    policy.validate_issued(question)
    assert telemetry["admitted_turns"] == 1


def test_model_case_executor_forwards_requested_conceptual_depth():
    observed = []

    class Provider:
        def interpret(self, request):
            observed.append(request.conceptual_depth)
            return InterpretationSpace(
                "depth-space",
                request.source_text,
                ConceptualDepth.Ordinary,
            )

    executor = ModelCaseExecutor(
        Provider(),
        FixtureFormalizationProvider({}),
        {"physical_objects": load_context(ROOT / "profiles/contexts/physical_objects.yaml")},
        requested_conceptual_depth=ConceptualDepth.Ordinary,
    )

    executor(_case(), request_timeout_seconds=1.0)

    assert observed == [ConceptualDepth.Ordinary]


def test_model_case_executor_only_exposes_context_projection_when_contextual():
    observed = []

    class Provider:
        def interpret(self, request):
            observed.append(request.state)
            return InterpretationSpace(
                "context-space",
                request.source_text,
                ConceptualDepth.Ordinary,
            )

    context = load_context(ROOT / "profiles/contexts/physical_objects.yaml")
    executor = ModelCaseExecutor(
        Provider(),
        FixtureFormalizationProvider({}),
        {"physical_objects": context},
    )

    executor(_case(), request_timeout_seconds=1.0)
    contextual_case = ClarificationCorpusCase(
        **{**_case().__dict__, "model_input": "contextual"}
    )
    aware_executor = ModelCaseExecutor(
        Provider(),
        FixtureFormalizationProvider({}),
        {"physical_objects": context},
        interpretation_context_mode="context_aware",
    )
    aware_executor(contextual_case, request_timeout_seconds=1.0)

    assert "context_projections" not in observed[0]
    assert observed[1]["context_id"] == "physical_objects"
    assert observed[1]["context_projections"]["physical_objects"]["ontology"] == (
        "physical_objects"
    )


def test_model_case_executor_classifies_transport_failure():
    class BrokenInterpretationProvider:
        def interpret(self, request):
            raise ProviderTransportError("network failed")

    context = load_context(ROOT / "profiles/contexts/physical_objects.yaml")
    execution = ModelCaseExecutor(
        BrokenInterpretationProvider(),
        FixtureFormalizationProvider({}),
        {"physical_objects": context},
    )(_case(), request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.TRANSPORT_ERROR
    assert execution.detail_code == "ProviderTransportError"


def test_model_case_executor_allowlists_stage_details():
    executor = _executor()
    executor._last_events = [
        ProviderStageEvent("interpretation", "started", 0.0),
        ProviderStageEvent(
            "interpretation",
            "response_received",
            0.1,
            "finish_reason=stop, completion_tokens=12",
        ),
        ProviderStageEvent(
            "interpretation",
            "completed",
            0.2,
            "Bearer SECRET and raw model content",
        ),
    ]

    details = executor._metadata()[3]

    assert details == {"interpretation": "finish_reason=stop, completion_tokens=12"}
    assert "SECRET" not in str(details)


def test_model_case_executor_allowlists_stage_names_and_phases():
    executor = _executor()
    executor._last_events = [
        ProviderStageEvent("stage-secret", "phase-secret", 0.1, "secret detail"),
        ProviderStageEvent(["unhashable-secret"], {"phase": "secret"}, 0.2),
    ]

    calls, timings, outcomes, details = executor._metadata()

    assert calls == 0
    assert set(timings) == {"other"}
    assert outcomes == {"other": "other"}
    assert details == {}
    safe = str((calls, timings, outcomes, details))
    assert "secret" not in safe.lower()


def test_model_case_executor_records_refinement_stage_without_collapsing_it():
    executor = _executor()
    executor._last_events = [
        ProviderStageEvent("refinement", "started", 0.0),
        ProviderStageEvent("refinement", "completed", 0.25, "schema_valid"),
    ]

    calls, timings, outcomes, details = executor._metadata()

    assert calls == 1
    assert timings == {"refinement": 0.25}
    assert outcomes == {"refinement": "completed"}
    assert details == {"refinement": "schema_valid"}


def test_model_case_executor_runs_dialogue_with_fake_refinement():
    context = load_context(ROOT / "profiles/contexts/physical_objects.yaml")
    initial = InterpretationSpace(
        "dialogue-space",
        "What is the mass of integer 7?",
        ConceptualDepth.Ordinary,
        ambiguities=(Ambiguity("ambiguity-0", "mass", "meaning"),),
    )
    successor = InterpretationSpace(
        "dialogue-successor",
        initial.source_text,
        initial.conceptual_depth,
    )

    class RefiningProvider:
        def interpret(self, request):
            return initial

        def refine(self, interpretation, question, answer):
            assert answer == "physical mass"
            return successor

    candidate = FormalizationCandidate(
        "mass",
        "mass",
        "has-mass",
        "physical_objects",
        PredicateExpr(PredicateCall("has_mass", (Term("integer_7"),))),
    )
    executor = ModelCaseExecutor(
        RefiningProvider(),
        FixtureFormalizationProvider(
            {"dialogue-space": (candidate,), "dialogue-successor": (candidate,)}
        ),
        {"physical_objects": context},
    )
    case = ClarificationCorpusCase(
            **{**_case(mode="dialogue").__dict__, "dialogue": (
                {"turn_id": "initial", "role": "user", "text": "What is the mass of integer 7?"},
                {
                    "turn_id": "question", "role": "assistant", "text": "Clarify the meaning.",
                    "question_kind": "Meaning", "target_family": "mass", "target_ids": ["ambiguity-0"],
                },
                {"turn_id": "answer", "role": "user", "text": "physical mass"},
        )}
    )

    execution = executor(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.ASSESSMENT_COMPLETED
    assert execution.semantic_verdict == "C"


def test_model_case_executor_runs_dialogue_with_typed_delta_refinement():
    context = load_context(ROOT / "profiles/contexts/physical_objects.yaml")
    initial = InterpretationSpace(
        "dialogue-space",
        "What is the mass of integer 7?",
        ConceptualDepth.Ordinary,
        ambiguities=(Ambiguity("ambiguity-0", "mass", "physical or abstract"),),
        readings=(SemanticReading("reading-0", "physical", "physical mass"),),
    )

    class InterpretationProvider:
        def interpret(self, request):
            return initial

        def refine(self, *args, **kwargs):
            raise AssertionError("full snapshot refinement must not run")

    class Formalizer:
        def formalize(self, request):
            return (
                FormalizationCandidate(
                    f"candidate:{request.interpretation.id}",
                    "mass",
                    "has-mass",
                    request.context_id,
                    PredicateExpr(PredicateCall("has_mass", (Term("integer_7"),))),
                    reading_id=request.reading.id,
                ),
            )

    class DeltaProvider:
        def propose_refinement_deltas(self, *args, **boundary):
            assert boundary["allowed_reading_ids"] == ("reading-0",)
            assert boundary["allowed_ambiguity_ids"] == ("ambiguity-0",)
            return ({
                "operation": "select_reading",
                "target_id": "reading-0",
                "resolved_ambiguity_ids": ["ambiguity-0"],
            },)

    executor = ModelCaseExecutor(
        InterpretationProvider(),
        Formalizer(),
        {"physical_objects": context},
        refinement_mode="typed_delta",
        refinement_delta_provider=DeltaProvider(),
    )
    case = ClarificationCorpusCase(
        **{
            **_case(mode="dialogue").__dict__,
            "dialogue": (
                {
                    "turn_id": "initial",
                    "role": "user",
                    "text": "What is the mass of integer 7?",
                },
                {
                    "turn_id": "question",
                    "role": "assistant",
                    "text": "Clarify mass.",
                    "question_kind": "Meaning",
                    "target_family": "mass",
                    "target_ids": ["ambiguity-0"],
                },
                {"turn_id": "answer", "role": "user", "text": "physical mass"},
            ),
        }
    )

    execution = executor(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.ASSESSMENT_COMPLETED
    assert execution.diagnostics["ambiguity_count"] == 0
    assert execution.diagnostics["refinement_operations"] == {"select_reading": 1}
    assert execution.diagnostics["refinement_effects"] == {"applied": 1}
    assert execution.diagnostics["refinement_commits"] == 1
    assert execution.diagnostics["refinement_proposed"] == 1


def test_model_case_executor_isolates_case_context():
    context = load_context(ROOT / "profiles/contexts/physical_objects.yaml")
    interpretation = InterpretationSpace(
        "scoped-space",
        "What is the mass of integer 7?",
        ConceptualDepth.Ordinary,
        readings=(SemanticReading("reading-0", "ordinary", "ordinary"),),
    )
    calls = []

    class RecordingFormalizer:
        def formalize(self, request):
            calls.append(request.context_id)
            return (FormalizationCandidate(
                "candidate",
                "candidate",
                "has-mass",
                request.context_id or "none",
                None,
                reading_id=request.reading.id if request.reading else None,
            ),)

    class Provider:
        def interpret(self, request):
            return interpretation

    executor = ModelCaseExecutor(
        Provider(), RecordingFormalizer(),
        {"physical_objects": context, "other_context": context},
    )
    execution = executor(_case(), request_timeout_seconds=1.0)

    assert calls == ["physical_objects"]
    assert execution.outcome is EvaluationOutcome.CLARIFICATION_REQUESTED


def test_model_case_executor_reports_missing_case_context():
    execution = ModelCaseExecutor(
        FixtureInterpretationProvider({}),
        FixtureFormalizationProvider({}),
        {},
    )(_case(), request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.CONTEXT_UNAVAILABLE


def _dialogue_case(*, expected_kind="Meaning", turns=None):
    case = _case(mode="dialogue")
    return ClarificationCorpusCase(
        **{
            **case.__dict__,
            "expected_clarification": {"kind": expected_kind, "target": "mass"},
            "dialogue": tuple(turns or (
                {"turn_id": "initial", "role": "user", "text": case.utterance},
                {
                    "turn_id": "question", "role": "assistant", "text": "Clarify",
                    "question_kind": expected_kind, "target_family": "mass", "target_ids": ["ambiguity-0"],
                },
                {"turn_id": "answer", "role": "user", "text": "physical mass"},
            )),
        }
    )


def _ambiguous_dialogue_executor(
    *, ambiguity_count=1, ambiguity_ids=None, ambiguity_terms=None,
    semantic_target_bindings=None, grounded_target_ids=True,
):
    context = load_context(ROOT / "profiles/contexts/physical_objects.yaml")
    ids = tuple(ambiguity_ids or (f"ambiguity-{index}" for index in range(ambiguity_count)))
    terms = tuple(ambiguity_terms or ("mass", "identity")[:ambiguity_count])
    initial = InterpretationSpace(
        "dialogue-space", "What is the mass of integer 7?", ConceptualDepth.Ordinary,
        ambiguities=tuple(
            Ambiguity(item_id, term, "meaning", item_id if grounded_target_ids else None)
            for item_id, term in zip(ids, terms)
        ),
    )
    successor = InterpretationSpace(
        "dialogue-successor", initial.source_text, initial.conceptual_depth,
    )

    class Provider:
        def interpret(self, request):
            return initial

        def refine(self, interpretation, question, answer):
            return successor

    candidate = FormalizationCandidate(
        "mass", "mass", "has-mass", "physical_objects",
        PredicateExpr(PredicateCall("has_mass", (Term("integer_7"),))),
    )
    return ModelCaseExecutor(
        Provider(),
        FixtureFormalizationProvider({"dialogue-space": (candidate,), "dialogue-successor": (candidate,)}),
        {"physical_objects": context},
        semantic_target_bindings=semantic_target_bindings or {},
    )


def test_dialogue_replay_rejects_wrong_question_intent():
    execution = _ambiguous_dialogue_executor()(
        _dialogue_case(expected_kind="Ontology"), request_timeout_seconds=1.0
    )

    assert execution.outcome is EvaluationOutcome.QUESTION_INTENT_MISMATCH


def test_dialogue_replay_uses_host_binding_instead_of_model_ambiguity_term():
    case = _dialogue_case()
    case = ClarificationCorpusCase(
        **{
            **case.__dict__,
            "expected_clarification": {"kind": "Meaning", "target_family": "stable-mass"},
            "dialogue": (
                {"turn_id": "initial", "role": "user", "text": case.utterance},
                {
                    "turn_id": "question", "role": "assistant", "text": "Clarify",
                    "question_kind": "Meaning", "target_family": "stable-mass",
                    "target_ids": ["ambiguity-0"],
                },
                {"turn_id": "answer", "role": "user", "text": "physical mass"},
            ),
        }
    )
    execution = _ambiguous_dialogue_executor(
        ambiguity_terms=("free-form model wording",),
        semantic_target_bindings={(case.case_id, "ambiguity-0"): "stable-mass"},
    )(case, request_timeout_seconds=1.0)
    assert execution.outcome is EvaluationOutcome.ASSESSMENT_COMPLETED
    assert execution.diagnostics["question_target_family_match"] is True


def test_dialogue_replay_rejects_wrong_target_family():
    case = ClarificationCorpusCase(
        **{
            **_dialogue_case().__dict__,
            "dialogue": (
                {"turn_id": "initial", "role": "user", "text": "What is the mass of integer 7?"},
                {
                    "turn_id": "question", "role": "assistant", "text": "Clarify",
                    "question_kind": "Meaning", "target_family": "identity",
                    "target_ids": ["ambiguity-0"],
                },
                {"turn_id": "answer", "role": "user", "text": "physical mass"},
            ),
        }
    )

    execution = _ambiguous_dialogue_executor()(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.QUESTION_INTENT_MISMATCH


def test_dialogue_replay_does_not_reorder_host_questions_for_script():
    case = _dialogue_case(
        turns=(
            {"turn_id": "initial", "role": "user", "text": "What is the mass of integer 7?"},
            {
                "turn_id": "question", "role": "assistant", "text": "Clarify identity",
                "question_kind": "Meaning", "target_family": "identity",
                "target_ids": ["ambiguity-1"],
            },
            {"turn_id": "answer", "role": "user", "text": "personal identity"},
        )
    )

    execution = _ambiguous_dialogue_executor(ambiguity_count=2)(
        case, request_timeout_seconds=1.0
    )

    assert execution.outcome is EvaluationOutcome.QUESTION_INTENT_MISMATCH


def test_dialogue_replay_rejects_wrong_semantic_target_even_when_family_is_unique():
    execution = _ambiguous_dialogue_executor(ambiguity_ids=("runtime-mass",))(
        _dialogue_case(), request_timeout_seconds=1.0
    )

    assert execution.outcome is EvaluationOutcome.QUESTION_INTENT_UNVERIFIED


def test_model_case_executor_rejects_unscoped_semantic_binding_keys():
    with pytest.raises(ValueError, match="case_id, target_id"):
        _ambiguous_dialogue_executor(
            semantic_target_bindings={"ambiguity-0": "stable-mass"},
        )


def test_strict_binding_does_not_ground_same_structural_id_without_host_reference():
    case = _dialogue_case()
    executor = _ambiguous_dialogue_executor(
        grounded_target_ids=False,
        semantic_target_bindings={(case.case_id, "ambiguity-0"): "stable-mass"},
    )
    executor.strict_semantic_target_binding = True

    execution = executor(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.QUESTION_INTENT_UNVERIFIED


def test_strict_binding_with_empty_map_fails_closed_instead_of_using_term():
    case = _dialogue_case()
    executor = _ambiguous_dialogue_executor()
    executor.strict_semantic_target_binding = True

    execution = executor(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.QUESTION_INTENT_UNVERIFIED


def test_target_family_match_uses_independent_corpus_oracle():
    case = _dialogue_case()
    case = ClarificationCorpusCase(
        **{
            **case.__dict__,
            "expected_clarification": {
                "kind": "Meaning",
                "target": "mass",
                "target_family": "causal_identity",
            },
        }
    )
    execution = _ambiguous_dialogue_executor()(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.ASSESSMENT_COMPLETED
    assert execution.diagnostics["question_script_target_family_match"] is True
    assert execution.diagnostics["question_target_family_match"] is False


def test_dialogue_replay_refuses_unbound_question_intent():
    case = _dialogue_case()
    case = ClarificationCorpusCase(
        **{
            **case.__dict__,
            "dialogue": (
                {"turn_id": "initial", "role": "user", "text": case.utterance},
                {"turn_id": "question", "role": "assistant", "text": "Clarify"},
                {"turn_id": "answer", "role": "user", "text": "physical mass"},
            ),
        }
    )

    execution = _ambiguous_dialogue_executor()(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.QUESTION_INTENT_UNVERIFIED


def test_dialogue_replay_does_not_count_early_complete_as_scenario_success():
    case = _dialogue_case()
    case = ClarificationCorpusCase(
        **{
            **case.__dict__,
            "dialogue": (
                {"turn_id": "initial", "role": "user", "text": case.utterance},
                {
                    "turn_id": "question-1", "role": "assistant", "text": "Clarify",
                    "question_kind": "Meaning", "target_family": "mass",
                    "target_ids": ["ambiguity-0"],
                },
                {"turn_id": "answer", "role": "user", "text": "physical mass"},
                {
                    "turn_id": "question-2", "role": "assistant", "text": "Clarify again",
                    "question_kind": "Meaning", "target_family": "identity",
                    "target_ids": ["ambiguity-1"],
                },
            ),
        }
    )

    execution = _ambiguous_dialogue_executor()(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.DIALOGUE_INCOMPLETE


def test_dialogue_replay_reports_missing_script_answer():
    execution = _ambiguous_dialogue_executor()(
        _dialogue_case(turns=(
            {"turn_id": "initial", "role": "user", "text": "What is the mass of integer 7?"},
            {
                "turn_id": "question", "role": "assistant", "text": "Clarify",
                "question_kind": "Meaning", "target_family": "mass", "target_ids": ["ambiguity-0"],
            },
        )),
        request_timeout_seconds=1.0,
    )

    assert execution.outcome is EvaluationOutcome.SCRIPT_EXHAUSTED


def test_dialogue_mode_without_script_is_explicitly_incomplete():
    case = ClarificationCorpusCase(
        **{**_case(mode="dialogue").__dict__, "dialogue": ()}
    )

    execution = _ambiguous_dialogue_executor()(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.SCRIPT_EXHAUSTED


def test_dialogue_replay_rejects_early_complete_when_question_is_expected():
    context = load_context(ROOT / "profiles/contexts/physical_objects.yaml")
    interpretation = InterpretationSpace(
        "complete-space", "What is the mass of integer 7?", ConceptualDepth.Ordinary,
    )
    candidate = FormalizationCandidate(
        "mass", "mass", "has-mass", "physical_objects",
        PredicateExpr(PredicateCall("has_mass", (Term("integer_7"),))),
    )
    case = _dialogue_case()
    class Provider:
        def interpret(self, request):
            return interpretation
    execution = ModelCaseExecutor(
        Provider(), FixtureFormalizationProvider({"complete-space": (candidate,)}),
        {"physical_objects": context},
    )(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.QUESTION_INTENT_MISMATCH


def test_model_backed_cli_uses_same_runner_and_safe_receipt(monkeypatch, tmp_path, capsys):
    corpus = tmp_path / "corpus.yaml"
    corpus.write_text(
        """version: 2
name: fake-model
visibility: {model_input: utterance_only}
context_profiles: {physical_objects: test}
cases:
  - case_id: safe-case
    utterance: What is the mass of integer 7?
    context: physical_objects
    expected_clarification: none
    expected_after_answer: {verdict: C}
""",
        encoding="utf-8",
    )
    receipt = tmp_path / "receipts.jsonl"
    report = tmp_path / "report.md"
    target_catalog = tmp_path / "targets.yaml"
    target_catalog.write_text(
        "version: 1\nname: public\ncases:\n  - case_id: safe-case\n"
        "    targets:\n      - id: public-mass\n        kind: Meaning\n"
        "        description: Public mass distinction.\n",
        encoding="utf-8",
    )
    prompts = []

    class FakeClient:
        def complete(self, messages, **kwargs):
            prompt = messages[1]["content"]
            prompts.append(prompt)
            if "Formalize the supplied interpretation" in prompt:
                payload = {
                    "candidates": [{
                        "id": "mass",
                        "label": "mass",
                        "formalization_id": "has-mass",
                        "context_id": "physical_objects",
                        "formalization": None,
                    }],
                }
            else:
                payload = {
                    "id": "space",
                    "source_text": "What is the mass of integer 7?",
                    "conceptual_depth": "ordinary",
                    "ambiguities": [],
                    "presuppositions": [],
                    "ontologies": [],
                    "readings": [],
                }
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    monkeypatch.setattr("onto4.cli.main.OpenAICompatibleClient", lambda profile, bearer_token=None: FakeClient())
    code = main([
        "eval-corpus",
        "--mode", "model-backed",
        "--corpus", str(corpus),
        "--target-catalog", str(target_catalog),
        "--receipt", str(receipt),
        "--report", str(report),
        "--endpoint", "http://provider.test/v1",
        "--model", "fake-model",
        "--context", str(ROOT / "profiles/contexts/physical_objects.yaml"),
    ])

    captured = capsys.readouterr()
    assert code == 0
    assert '"cases": 1' in captured.out
    safe_receipt = receipt.read_text(encoding="utf-8")
    assert "What is the mass" not in safe_receipt
    assert "fake-model" not in safe_receipt.splitlines()[1]
    assert "ONTO4_API_TOKEN" not in safe_receipt
    assert "public-mass" in prompts[0]


def test_adapter_backed_two_turn_binding_preserves_public_catalog_and_oracle_boundary():
    corpus = load_clarification_corpus(
        ROOT / "eval/clarification/bounded-dialogue-v1.yaml"
    )
    case = next(item for item in corpus.cases if item.case_id == "intrinsic-time-bounded")
    _, target_catalog = load_semantic_target_catalog(
        ROOT / "eval/clarification/bounded-dialogue-targets-v1.yaml"
    )

    class Client:
        def __init__(self):
            self.calls = 0
            self.prompts = []

        def complete(self, messages, **kwargs):
            self.prompts.append(messages[1]["content"])
            payloads = (
                {
                    "source_text": case.utterance,
                    "conceptual_depth": "ordinary",
                    "ambiguities": [{
                        "term": "intrinsic present",
                        "description": "the phrase has more than one temporal reading",
                        "target_id": "ambiguity-present",
                    }],
                    "presuppositions": [],
                    "ontologies": [],
                    "readings": [],
                },
                {
                    "source_text": case.utterance,
                    "conceptual_depth": "ordinary",
                    "ambiguities": [],
                    "presuppositions": [],
                    "ontologies": [{
                        "label": "observer-independent time",
                        "description": "the sequence has a present independently of observation",
                        "target_id": "ambiguity-observer",
                    }],
                    "readings": [],
                },
                {
                    "source_text": case.utterance,
                    "conceptual_depth": "ordinary",
                    "ambiguities": [],
                    "presuppositions": [],
                    "ontologies": [],
                    "readings": [],
                },
            )
            payload = payloads[self.calls]
            self.calls += 1
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    class Formalizer:
        def formalize(self, request):
            return (
                FormalizationCandidate(
                    "time-order",
                    "time order",
                    "time-order",
                    "relational_time",
                    PredicateExpr(
                        PredicateCall(
                            "earlier_than",
                            (Term("past_t"), Term("now")),
                        )
                    ),
                ),
            )

    client = Client()
    adapter = OpenAICompatibleInterpretationProvider(client)
    executor = ModelCaseExecutor(
        adapter,
        Formalizer(),
        {"relational_time": load_context(ROOT / "profiles/contexts/relational_time.yaml")},
        semantic_target_bindings=host_semantic_target_bindings(corpus),
        strict_semantic_target_binding=True,
        host_target_catalog=target_catalog,
    )

    execution = executor(case, request_timeout_seconds=2.0)

    assert execution.outcome is EvaluationOutcome.NEED_EVIDENCE
    assert execution.diagnostics["questions_issued"] == 2
    assert execution.diagnostics["answers_consumed"] == 2
    assert execution.diagnostics["reassessment_performed"] is True
    assert client.calls == 3
    assert "ambiguity-present" in client.prompts[0]
    assert "ambiguity-observer" in client.prompts[1]
    assert "ambiguity-observer" in client.prompts[2]
    all_prompts = "\n".join(client.prompts)
    assert "target_family" not in all_prompts
    assert "expected_clarification" not in all_prompts
    assert "observer_independence" not in all_prompts
