import ai_docs_kit


def test_version_is_a_non_empty_string():
    assert isinstance(ai_docs_kit.__version__, str)
    assert ai_docs_kit.__version__
