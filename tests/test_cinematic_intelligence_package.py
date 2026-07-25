"""Top-level cinematic_intelligence package: register_defaults() must
register every plugin type (prompt translators, quality metrics, repair
strategies) across all three registries in one call."""

from __future__ import annotations

import cinematic_intelligence as ci
from config_sdk import PROMPT_TRANSLATOR_REGISTRY, QUALITY_METRIC_REGISTRY, REPAIR_STRATEGY_REGISTRY


def test_register_defaults_registers_every_plugin_type():
    ci.register_defaults()

    assert "wan2.1" in PROMPT_TRANSLATOR_REGISTRY
    assert "identity_consistency" in QUALITY_METRIC_REGISTRY
    assert "prompt_repair" in REPAIR_STRATEGY_REGISTRY


def test_register_defaults_is_idempotent():
    ci.register_defaults()
    ci.register_defaults()  # must not raise
