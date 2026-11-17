from pathlib import Path

from ai_docs_kit.review.plan import export_review_schema

COMMITTED = Path(__file__).resolve().parents[1] / "docs" / "schemas" / "review"


def test_committed_review_schema_matches_fresh_export(tmp_path: Path) -> None:
    fresh = export_review_schema(tmp_path)
    assert (COMMITTED / fresh.name).read_bytes() == fresh.read_bytes()
