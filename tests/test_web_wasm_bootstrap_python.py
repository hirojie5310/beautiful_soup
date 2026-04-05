# tests/test_web_wasm_bootstrap_python.py
from __future__ import annotations

from pathlib import Path


def test_bootstrap_python_file_is_syntax_valid() -> None:
    source = Path("web_wasm/bootstrap_runtime.py").read_text(encoding="utf-8")
    compile(source, "<web_wasm_bootstrap>", "exec")


def test_main_js_loads_external_bootstrap_python_file() -> None:
    source = Path("web_wasm/pyodide_runtime.js").read_text(encoding="utf-8")
    assert 'fetch("./bootstrap_runtime.py")' in source
    assert "runPythonAsync(bootstrapPython)" in source
