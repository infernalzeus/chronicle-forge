import unittest
from unittest.mock import patch, Mock

import research_gen
import script_gen


class ResearchSafetyTests(unittest.TestCase):
    def test_search_outage_stops_unsourced_generation(self):
        with patch("research_gen.requests.get", side_effect=OSError("offline")):
            with self.assertRaisesRegex(RuntimeError, "refusing"):
                research_gen.fetch_research("Netflix")

    def test_empty_search_stops_generation(self):
        response = Mock()
        response.json.return_value = {"query": {"search": []}}
        with patch("research_gen.requests.get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "No research"):
                research_gen.fetch_research("Netflix")

    def test_missing_article_is_not_treated_as_evidence(self):
        search, page = Mock(), Mock()
        search.json.return_value = {"query": {"search": [{"title": "Missing"}]}}
        page.json.return_value = {"query": {"pages": {"-1": {"missing": ""}}}}
        with patch("research_gen.requests.get", side_effect=[search, page]):
            with self.assertRaisesRegex(RuntimeError, "No usable research"):
                research_gen.fetch_research("Netflix")

    def test_success_preserves_source_urls_and_text(self):
        search, page = Mock(), Mock()
        search.json.return_value = {"query": {"search": [{"title": "Netflix"}]}}
        page.json.return_value = {"query": {"pages": {"1": {
            "title": "Netflix", "extract": "Documented history.", "fullurl": "https://en.wikipedia.org/wiki/Netflix"}}}}
        with patch("research_gen.requests.get", side_effect=[search, page]):
            result = research_gen.fetch_research("Netflix")
        self.assertEqual(result, {"summary": "=== Netflix ===\nDocumented history.",
                                  "sources": [{"title": "Netflix", "url": "https://en.wikipedia.org/wiki/Netflix"}]})

    def test_empty_research_rejected_before_model_call(self):
        with patch("script_gen.requests.post") as network:
            with self.assertRaisesRegex(ValueError, "Research is required"):
                script_gen.generate_narration("Netflix", 60, "  ")
        network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
