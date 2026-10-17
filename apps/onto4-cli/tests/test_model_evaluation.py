import json
from pathlib import Path

from onto4.cli.main import main
from onto4.core import PredicateCall, PredicateExpr, Term
from onto4.pipeline import ModelCaseExecutor
from onto4.pipeline.clarification_corpus import ClarificationCorpusCase
from onto4.pipeline.evaluation import EvaluationOutcome
from onto4.providers import (
    FixtureFormalizationProvider,
    FixtureInterpretationProvider,
    InterpretationRequest,
    ProviderTransportError,
)
from onto4.reasoning import Ambiguity, ConceptualDepth, FormalizationCandidate, InterpretationSpace
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
            {"turn_id": "answer", "role": "user", "text": "physical mass"},
        )}
    )

    execution = executor(case, request_timeout_seconds=1.0)

    assert execution.outcome is EvaluationOutcome.ASSESSMENT_COMPLETED
    assert execution.semantic_verdict == "C"


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

    class FakeClient:
        def complete(self, messages, **kwargs):
            prompt = messages[1]["content"]
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
