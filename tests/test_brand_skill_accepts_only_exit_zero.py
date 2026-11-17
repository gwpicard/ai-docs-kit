import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_brand_skill_test_does_not_accept_exit_code_one_from_the_build():
    tree = ast.parse((ROOT / "tests/test_brand_skill.py").read_text(encoding="utf-8"))
    loose = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and any(isinstance(op, ast.In) for op in node.ops)
        and any(
            isinstance(c, ast.Tuple | ast.List | ast.Set) and {getattr(e, "value", None) for e in c.elts} >= {0, 1}
            for c in node.comparators
        )
    ]
    assert not loose, f"tests/test_brand_skill.py accepts exit code 0 or 1 at line(s) {loose}; require == 0"
