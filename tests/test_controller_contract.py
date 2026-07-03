"""Contrato mínimo de SW-001 sem depender de um display Qt no CI."""

from __future__ import annotations

import ast
from pathlib import Path


def test_validate_session_declares_bool_and_returns_true_and_false():
    source_path = Path(__file__).parents[1] / "serial_monitor" / "app" / "bootstrap.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "validate_session"
    )

    assert isinstance(function.returns, ast.Name)
    assert function.returns.id == "bool"

    returned_constants = {
        node.value.value
        for node in ast.walk(function)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
    }
    assert returned_constants == {False, True}
