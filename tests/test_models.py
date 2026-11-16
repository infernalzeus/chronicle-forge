import unittest
from unittest.mock import Mock, patch

import requests
import web_ui


class ModelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.client = web_ui.app.test_client()
        web_ui._update_state(running=False)

    def test_discovery_excludes_embeddings_and_labels_remote_aliases(self):
        tags = Mock()
        tags.json.return_value = {"models": [{"name": name} for name in
                                 ["embed:latest", "remote-alias", "local:latest"]]}
        details = []
        for info in [{"capabilities": ["embedding"]},
                     {"capabilities": ["completion"], "remote_host": "https://ollama.com"},
                     {"capabilities": ["completion"]}]:
            response = Mock()
            response.json.return_value = info
            details.append(response)
        with patch("web_ui.requests.get", return_value=tags), \
             patch("web_ui.requests.post", side_effect=details):
            result = self.client.get("/api/models")
        self.assertEqual(result.get_json()["models"], [
            {"name": "local:latest", "cloud": False},
            {"name": "remote-alias", "cloud": True}])

    def test_unreachable_ollama_returns_actionable_error(self):
        with patch("web_ui.requests.get", side_effect=requests.ConnectionError):
            result = self.client.get("/api/models")
        self.assertEqual(result.status_code, 503)
        self.assertIn("Ollama", result.get_json()["error"])

    def test_unknown_model_never_starts_pipeline(self):
        tags = Mock()
        tags.json.return_value = {"models": []}
        with patch("web_ui.requests.get", return_value=tags), \
             patch("web_ui.threading.Thread") as thread:
            result = self.client.post("/api/start", json={"topic": "History", "model": "missing"})
        self.assertEqual(result.status_code, 400)
        thread.assert_not_called()

    def test_selected_model_is_forwarded_to_pipeline_process(self):
        process = Mock(stdout=[], returncode=0)
        with patch("web_ui.subprocess.Popen", return_value=process) as launch:
            web_ui._run({"topic": "History", "model": "local:latest"})
        command = launch.call_args.args[0]
        self.assertEqual(command[command.index("--model") + 1], "local:latest")


if __name__ == "__main__":
    unittest.main()
