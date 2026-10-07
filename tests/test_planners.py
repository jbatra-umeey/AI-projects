import io
import json
import os
import unittest
from unittest.mock import patch

from agentloop.domain import Decision, Run
from agentloop.planners import OllamaPlanner


class PlannerTests(unittest.TestCase):
    @patch.dict(os.environ, {"OLLAMA_MODEL": "test-model"})
    def test_ollama_contract_and_token_accounting(self):
        def respond(request, timeout):
            body = json.loads(request.data)
            self.assertEqual("test-model", body["model"])
            self.assertFalse(body["stream"])
            self.assertEqual("object", body["format"]["type"])
            self.assertEqual(30, timeout)
            return io.BytesIO(json.dumps({"response": json.dumps({"tool": "query_metrics", "rationale": "Measure first", "arguments": {}}),
                                          "prompt_eval_count": 20, "eval_count": 10}).encode())
        with patch("urllib.request.urlopen", side_effect=respond):
            run = Run("Investigate")
            decision = OllamaPlanner().decide(run)
        self.assertEqual("query_metrics", decision.tool)
        self.assertEqual(30, run.tokens)

    @patch.dict(os.environ, {"OLLAMA_MODEL": "test-model"})
    def test_ollama_malformed_response_is_rejected(self):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b'{"response":"not json"}')):
            with self.assertRaises(ValueError):
                OllamaPlanner().decide(Run("Investigate"))

    @patch.dict(os.environ, {"OLLAMA_MODEL": ""})
    def test_ollama_requires_explicit_local_model(self):
        with self.assertRaises(ValueError):
            OllamaPlanner()

    def test_decision_schema_rejects_extra_fields(self):
        with self.assertRaises(ValueError):
            Decision.parse({"tool": "query_metrics", "rationale": "x", "arguments": {}, "execute": True})


if __name__ == "__main__":
    unittest.main()
