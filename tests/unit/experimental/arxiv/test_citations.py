"""Tests for citation extraction and LLM-tell phrase detection."""

from __future__ import annotations


class TestExtractFromBib:
    """Tests for .bib file citation extraction."""

    def test_extract_single_entry(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        bib = """
@article{smith2023quantum,
    author = {Smith, John and Doe, Alice},
    title = {Quantum Error Correction Survey},
    journal = {Physical Review Letters},
    year = {2023},
    eprint = {2301.04567},
}
"""
        cites = extract_citations_from_bib(bib)
        assert len(cites) == 1
        assert cites[0].key == "smith2023quantum"
        assert cites[0].title == "Quantum Error Correction Survey"
        assert cites[0].year == "2023"
        assert cites[0].arxiv_id == "2301.04567"

    def test_extract_multiple_entries(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        bib = """
@article{a, author={A}, title={Paper A}, year={2023}}
@inproceedings{b, author={B}, title={Paper B}, year={2024}}
"""
        cites = extract_citations_from_bib(bib)
        assert len(cites) == 2

    def test_extract_arxiv_id_from_eprint(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        bib = """
@article{x, author={X}, title={T}, year={2023}, eprint={2501.12345}, archivePrefix={arXiv}}
"""
        cites = extract_citations_from_bib(bib)
        assert cites[0].arxiv_id == "2501.12345"

    def test_extract_doi(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        bib = """
@article{x, author={X}, title={T}, year={2023}, doi={10.1234/example}}
"""
        cites = extract_citations_from_bib(bib)
        assert cites[0].doi == "10.1234/example"

    def test_empty_bib(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        assert extract_citations_from_bib("") == []

    def test_malformed_bib_does_not_crash(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        # Malformed BibTeX should return empty, not crash
        result = extract_citations_from_bib("this is not valid bibtex {{{")
        assert isinstance(result, list)


class TestExtractFromBbl:
    """Tests for .bbl file citation extraction."""

    def test_extract_bibitem(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bbl

        bbl = r"""
\begin{thebibliography}{10}

\bibitem{smith2023}
J.~Smith and A.~Doe.
\newblock Quantum error correction survey.
\newblock {\em Physical Review Letters}, 2023.

\bibitem{jones2024}
K.~Jones.
\newblock Surface codes revisited.
\newblock arXiv:2401.67890, 2024.

\end{thebibliography}
"""
        cites = extract_citations_from_bbl(bbl)
        assert len(cites) == 2
        assert cites[0].key == "smith2023"
        assert cites[1].key == "jones2024"

    def test_extract_arxiv_id_from_bbl_text(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bbl

        bbl = r"""
\begin{thebibliography}{1}
\bibitem{x}
Author. Title. arXiv:2301.04567, 2023.
\end{thebibliography}
"""
        cites = extract_citations_from_bbl(bbl)
        assert len(cites) == 1
        assert cites[0].arxiv_id == "2301.04567"

    def test_empty_bbl(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bbl

        assert extract_citations_from_bbl("") == []


class TestDetectLLMPhrases:
    """Tests for LLM-tell phrase detection."""

    def test_detect_knowledge_update_phrase(self) -> None:
        from shesha.experimental.arxiv.citations import detect_llm_phrases

        text = "Line one.\nAs of my last knowledge update, this is true.\nLine three."
        results = detect_llm_phrases(text)
        assert len(results) == 1
        line_num, phrase = results[0]
        assert line_num == 2
        assert "knowledge update" in phrase.lower()

    def test_detect_important_to_note(self) -> None:
        from shesha.experimental.arxiv.citations import detect_llm_phrases

        text = "It is important to note that the results suggest otherwise."
        results = detect_llm_phrases(text)
        assert len(results) == 1

    def test_no_false_positives_on_clean_text(self) -> None:
        from shesha.experimental.arxiv.citations import detect_llm_phrases

        text = (
            "We present a novel method for quantum error correction.\nOur results show improvement."
        )
        results = detect_llm_phrases(text)
        assert results == []

    def test_detect_multiple_phrases(self) -> None:
        from shesha.experimental.arxiv.citations import detect_llm_phrases

        text = (
            "As of my last knowledge update, X.\nNormal line.\nI cannot provide specific details.\n"
        )
        results = detect_llm_phrases(text)
        assert len(results) == 2

    def test_case_insensitive(self) -> None:
        from shesha.experimental.arxiv.citations import detect_llm_phrases

        text = "AS OF MY LAST KNOWLEDGE UPDATE, things changed."
        results = detect_llm_phrases(text)
        assert len(results) == 1


class TestExtractFromText:
    """Tests for plain text (PDF-extracted) citation extraction."""

    def test_extract_arxiv_ids_from_text(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_text

        text = (
            "We build on prior work [1] and extend the results of arXiv:2301.04567.\n"
            "See also 2502.67890v2 for related approaches.\n"
        )
        cites = extract_citations_from_text(text)
        assert len(cites) == 2
        ids = {c.arxiv_id for c in cites}
        assert "2301.04567" in ids
        assert "2502.67890v2" in ids

    def test_empty_text(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_text

        assert extract_citations_from_text("") == []

    def test_no_arxiv_ids(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_text

        text = "This paper has no arXiv references, only DOIs like 10.1234/example."
        assert extract_citations_from_text(text) == []

    def test_deduplicates_ids(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_text

        text = "We cite arXiv:2301.04567 here and again arXiv:2301.04567 there."
        cites = extract_citations_from_text(text)
        assert len(cites) == 1
