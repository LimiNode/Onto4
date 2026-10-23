import importlib.util
from pathlib import Path
import sys

import pytest

from onto4.providers.openai_adapters import ProviderSchemaError


_RUNNER_PATH = Path(__file__).parents[1] / "research" / "pr40_semantic_binding_runner.py"
_SPEC = importlib.util.spec_from_file_location("pr40_semantic_binding_runner", _RUNNER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_RUNNER = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _RUNNER
_SPEC.loader.exec_module(_RUNNER)


def test_explicit_binding_envelope_rejects_private_oracle_field():
    with pytest.raises(ProviderSchemaError, match="unknown fields"):
        _RUNNER._parse_explicit_envelope(
            {
                "successor": {},
                "binding_claim": {},
                "expected_intent": "private",
            }
        )


def test_explicit_binding_envelope_rejects_arbitrary_extra_field():
    with pytest.raises(ProviderSchemaError, match="unknown fields"):
        _RUNNER._parse_explicit_envelope(
            {
                "successor": {},
                "binding_claim": {},
                "debug": "accepted by accident",
            }
        )


def test_prompt_digest_is_for_template_not_version_label():
    import hashlib

    digest = hashlib.sha256(
        (
            _RUNNER.EXPLICIT_BINDING_SYSTEM_PROMPT
            + "\n"
            + _RUNNER.EXPLICIT_BINDING_PROMPT_TEMPLATE
        ).encode("utf-8")
    ).hexdigest()
    version_digest = hashlib.sha256(_RUNNER.PROMPT_VERSION.encode("utf-8")).hexdigest()
    assert digest != version_digest
