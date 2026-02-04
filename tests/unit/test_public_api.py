"""Tests for public API exports."""


def test_query_context_exported_from_shesha() -> None:
    """QueryContext is importable from shesha."""
    from shesha import QueryContext

    assert QueryContext is not None


def test_trace_writer_exported_from_rlm() -> None:
    """TraceWriter is importable from shesha.rlm."""
    from shesha.rlm import TraceWriter

    assert TraceWriter is not None
