import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentloop.domain import Run
from agentloop.observability import graph_config, tracing_settings
from agentloop.runtime import Runtime
from agentloop.store import Store


class ObservabilityTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_export_is_disabled_by_default(self):
        self.assertFalse(tracing_settings()["enabled"])

    @patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": ""})
    def test_enabled_export_requires_key(self):
        with self.assertRaises(ValueError):
            tracing_settings()

    @patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "unit-test-placeholder", "LANGSMITH_PROJECT": "unit-test"})
    def test_key_is_not_in_trace_configuration(self):
        self.assertEqual({"enabled": True, "project_name": "unit-test"}, tracing_settings())
        config = graph_config(Run("Investigate"))
        self.assertNotIn("unit-test-placeholder", str(config))
        self.assertEqual("demo", config["metadata"]["planner"])

    @patch.dict(os.environ, {"LANGSMITH_TRACING": "false"})
    def test_runtime_uses_explicit_export_context(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Runtime(Store(str(Path(temp) / "trace.db")))
            run = runtime.start("Investigate")
            with patch("agentloop.runtime.tracing_context") as context:
                runtime.step(run.id)
            context.assert_called_once_with(enabled=False, project_name="agentloop-studio")


if __name__ == "__main__":
    unittest.main()
