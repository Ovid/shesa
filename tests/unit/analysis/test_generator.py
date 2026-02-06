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
