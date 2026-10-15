import json
import importlib
from types import SimpleNamespace
from pathlib import Path

from onto4.cli.main import main
from onto4.pipeline.loaders import load_context, load_formalization
from onto4.core import Verdict, evaluate


cli_main = importlib.import_module("onto4.cli.main")


ROOT = Path(__file__).parents[1]


def test_example_profiles_load_and_evaluate():
    expression = load_formalization(ROOT / "examples/formalizations/has_mass_integer_7.yaml")
    context = load_context(ROOT / "profiles/contexts/physical_objects.yaml")

    assert evaluate(expression, context).verdict is Verdict.C


def test_truth_and_evidence_load_as_separate_axes():
    expression = load_formalization(ROOT / "examples/formalizations/has_mass_car.yaml")
    context = load_context(ROOT / "profiles/contexts/verified_physical_objects.yaml")

    result = evaluate(expression, context)

    assert result.verdict is Verdict.T
    assert result.evidence.value == "TrueOnly"


def test_compare_command_emits_all_contexts(capsys):
    code = main(
        [
            "compare",
            str(ROOT / "examples/formalizations/identity_substance.yaml"),
            "--context",
            str(ROOT / "profiles/contexts/process.yaml"),
            "--context",
            str(ROOT / "profiles/contexts/substance.yaml"),
        ]
    )

    output = capsys.readouterr().out
    assert code == 0
    assert "process" in output
    assert "substance" in output
    assert "Onto4: C" in output
    assert "Onto4: U" in output


def test_json_renderer_handles_uncomputed_evidence(capsys):
    code = main(
        [
            "eval",
            str(ROOT / "examples/formalizations/has_mass_integer_7.yaml"),
            "--context",
            str(ROOT / "profiles/contexts/physical_objects.yaml"),
            "--format",
            "json",
        ]
    )

    output = capsys.readouterr().out
    assert code == 0
    assert '"verdict": "C"' in output
    assert '"evidence": null' in output


def test_ask_command_runs_model_backed_pass_without_model_verdict(monkeypatch, capsys):
    import onto4.cli.main as cli_main

    class FakeClient:
        def complete(self, messages, **kwargs):
            if "Formalize the supplied interpretation" in messages[1]["content"]:
                payload = {
                    "candidates": [
                        {
                            "id": "mass",
                            "label": "mass of integer 7",
                            "formalization_id": "has-mass",
                            "context_id": "physical_objects",
                            "formalization": {
                                "kind": "predicate",
                                "name": "has_mass",
                                "args": [{"name": "integer_7"}],
                            },
                        }
                    ]
                }
            else:
                payload = {
                    "id": "ask-space",
                    "source_text": "What is the mass of integer 7?",
                    "conceptual_depth": "ordinary",
                    "ambiguities": [],
                    "presuppositions": [],
                    "ontologies": [],
                    "readings": [],
                }
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    monkeypatch.setattr(cli_main, "OpenAICompatibleClient", lambda profile, bearer_token=None: FakeClient())
    code = cli_main.main(
        [
            "ask",
            "What is the mass of integer 7?",
            "--endpoint",
            "http://example.test/v1",
            "--model",
            "fixture-model",
            "--context",
            str(ROOT / "profiles/contexts/physical_objects.yaml"),
            "--format",
            "json",
        ]
    )

    output = capsys.readouterr().out
    assert code == 0
    assert '"disposition": "Complete"' in output
    assert '"verdict": "C"' in output


def test_ask_debug_reports_provider_stages_without_model_payload(monkeypatch, capsys):
    import onto4.cli.main as cli_main

    class FakeClient:
        def complete(self, messages, **kwargs):
            if "Formalize the supplied interpretation" in messages[1]["content"]:
                payload = {
                    "candidates": [
                        {
                            "id": "mass",
                            "label": "mass of integer 7",
                            "formalization_id": "has-mass",
                            "context_id": "physical_objects",
                            "formalization": {
                                "kind": "predicate",
                                "name": "has_mass",
                                "args": [{"name": "integer_7"}],
                            },
                        }
                    ]
                }
            else:
                payload = {
                    "id": "ask-space",
                    "source_text": "What is the mass of integer 7?",
                    "conceptual_depth": "ordinary",
                    "ambiguities": [],
                    "presuppositions": [],
                    "ontologies": [],
                    "readings": [],
                }
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    monkeypatch.setattr(cli_main, "OpenAICompatibleClient", lambda profile, bearer_token=None: FakeClient())
    code = cli_main.main(
        [
            "ask",
            "What is the mass of integer 7?",
            "--endpoint",
            "http://example.test/v1",
            "--model",
            "fixture-model",
            "--context",
            str(ROOT / "profiles/contexts/physical_objects.yaml"),
            "--debug",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "[onto4] interpretation: started" in captured.err
    assert "[onto4] interpretation: completed" in captured.err
    assert "[onto4] formalization: completed" in captured.err
    assert "choices" not in captured.err


def test_ask_command_reports_missing_bearer_token_without_traceback(monkeypatch, capsys):
    monkeypatch.delenv("ONTO4_API_TOKEN", raising=False)

    code = main(
        [
            "ask",
            "What is the mass of integer 7?",
            "--endpoint",
            "http://example.test/v1",
            "--model",
            "fixture-model",
            "--auth",
            "bearer",
            "--context",
            str(ROOT / "profiles/contexts/physical_objects.yaml"),
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "Ask error:" in captured.err
    assert "Traceback" not in captured.err


def test_ask_command_reports_missing_context_without_traceback(capsys, tmp_path):
    code = main(
        [
            "ask",
            "What is the mass of integer 7?",
            "--endpoint",
            "http://example.test/v1",
            "--model",
            "fixture-model",
            "--context",
            str(tmp_path / "missing.yaml"),
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "Ask error:" in captured.err
    assert "Traceback" not in captured.err


def test_ask_command_reports_invalid_context_yaml_without_traceback(capsys, tmp_path):
    invalid_context = tmp_path / "invalid.yaml"
    invalid_context.write_text("ontology: [", encoding="utf-8")

    code = main(
        [
            "ask",
            "What is the mass of integer 7?",
            "--endpoint",
            "http://example.test/v1",
            "--model",
            "fixture-model",
            "--context",
            str(invalid_context),
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "Ask error:" in captured.err
    assert "Traceback" not in captured.err


def test_interactive_ask_reports_stdin_eof_without_traceback(monkeypatch, capsys):
    def raise_eof(*args, **kwargs):
        raise EOFError

    monkeypatch.setattr(cli_main, "run_interactive_dialogue", raise_eof)

    code = cli_main.main(
        [
            "ask",
            "What is the mass of integer 7?",
            "--endpoint",
            "http://example.test/v1",
            "--model",
            "fixture-model",
            "--context",
            str(ROOT / "profiles/contexts/physical_objects.yaml"),
            "--interactive",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "Ask error:" in captured.err
    assert "Traceback" not in captured.err


def test_interactive_json_output_is_rejected_before_prompt_output(capsys, tmp_path):
    context = tmp_path / "context.yaml"
    context.write_text("ontology: {}\n", encoding="utf-8")

    code = cli_main.main(
        [
            "ask",
            "A statement",
            "--endpoint",
            "http://example.test/v1",
            "--model",
            "fixture-model",
            "--context",
            str(context),
            "--interactive",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "Interactive ask does not support --format json" in captured.err
    assert "Traceback" not in captured.err


def test_max_turns_output_does_not_repeat_unissued_question(capsys):
    result = SimpleNamespace(
        interpretation=SimpleNamespace(
            id="snapshot",
            conceptual_depth=SimpleNamespace(value="ordinary"),
        ),
        landscape=SimpleNamespace(status=SimpleNamespace(value="Mixed")),
        disposition=SimpleNamespace(value="AskClarification"),
        reason="material_ambiguity",
        assessments=(),
        clarification_question=SimpleNamespace(text="A question that is not issued", choices=()),
    )

    cli_main._print_ask_result(result, stop_reason="max_turns_reached")

    output = capsys.readouterr().out
    assert "Stop reason: max_turns_reached" in output
    assert "A question that is not issued" not in output
