"""Tests for analysis generator."""

from unittest.mock import MagicMock

from shesha.analysis import AnalysisGenerator


class TestAnalysisPromptLoading:
    """Tests for prompt loading."""

    def test_load_prompt_returns_string(self):
        """_load_prompt returns prompt content as string."""
        mock_shesha = MagicMock()
        generator = AnalysisGenerator(mock_shesha)

        prompt = generator._load_prompt("generate")

        assert isinstance(prompt, str)
        assert len(prompt) > 100  # Should have substantial content

    def test_load_prompt_contains_json_schema(self):
        """_load_prompt for generate contains JSON schema example."""
        mock_shesha = MagicMock()
        generator = AnalysisGenerator(mock_shesha)

        prompt = generator._load_prompt("generate")

        assert "overview" in prompt
        assert "components" in prompt
        assert "external_dependencies" in prompt


class TestAnalysisGeneratorStructure:
    """Tests for AnalysisGenerator class structure."""

    def test_generator_can_be_imported(self):
        """AnalysisGenerator can be imported from shesha.analysis."""
        assert AnalysisGenerator is not None

    def test_generator_takes_shesha_instance(self):
        """AnalysisGenerator constructor takes a Shesha instance."""
        mock_shesha = MagicMock()
        generator = AnalysisGenerator(mock_shesha)

        assert generator._shesha is mock_shesha


class TestAnalysisGeneration:
    """Tests for generate() method."""

    def test_generate_returns_repo_analysis(self):
        """generate() returns a RepoAnalysis object."""
        from shesha.models import RepoAnalysis

        # Mock the shesha instance and project
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        # Mock query result with valid JSON
        mock_result = MagicMock()
        mock_result.answer = """
        ```json
        {
          "overview": "A test application.",
          "components": [
            {
              "name": "API",
              "path": "api/",
              "description": "REST API",
              "apis": [{"type": "rest", "endpoints": ["/health"]}],
              "models": ["User"],
              "entry_points": ["api/main.py"],
              "internal_dependencies": [],
              "auth": null,
              "data_persistence": null
            }
          ],
          "external_dependencies": []
        }
        ```
        """
        mock_project.query.return_value = mock_result

        # Mock repo ingester for SHA
        mock_shesha.get_project_sha.return_value = "abc123def"

        generator = AnalysisGenerator(mock_shesha)
        result = generator.generate("test-project")

        assert isinstance(result, RepoAnalysis)
        assert result.overview == "A test application."
        assert result.head_sha == "abc123def"
        assert result.version == "1"
        assert len(result.components) == 1
        assert result.components[0].name == "API"

    def test_generate_calls_project_query(self):
        """generate() calls project.query with the generate prompt."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        mock_result = MagicMock()
        mock_result.answer = '{"overview": "Test", "components": [], "external_dependencies": []}'
        mock_project.query.return_value = mock_result
        mock_shesha.get_project_sha.return_value = "sha123"

        generator = AnalysisGenerator(mock_shesha)
        generator.generate("test-project")

        mock_shesha.get_project.assert_called_once_with("test-project")
        mock_project.query.assert_called_once()

        # Verify prompt contains expected content
        call_args = mock_project.query.call_args
        prompt = call_args[0][0]
        assert "overview" in prompt
        assert "components" in prompt

    def test_generate_handles_missing_sha(self):
        """generate() handles missing SHA gracefully."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        mock_result = MagicMock()
        mock_result.answer = '{"overview": "Test", "components": [], "external_dependencies": []}'
        mock_project.query.return_value = mock_result
        mock_shesha.get_project_sha.return_value = None

        generator = AnalysisGenerator(mock_shesha)
        result = generator.generate("test-project")

        assert result.head_sha == ""  # Empty string when no SHA

    def test_generate_handles_invalid_json(self):
        """generate() falls back to raw answer when JSON extraction fails."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        # Response with no valid JSON - just plain text
        mock_result = MagicMock()
        mock_result.answer = "This is a plain text response with no JSON."
        mock_project.query.return_value = mock_result
        mock_shesha.get_project_sha.return_value = "sha456"

        generator = AnalysisGenerator(mock_shesha)
        result = generator.generate("test-project")

        # Fallback: raw answer becomes overview, empty components/deps
        assert result.overview == "This is a plain text response with no JSON."
        assert result.components == []
        assert result.external_dependencies == []
