# make_import_graph.py
from __future__ import annotations
import ast
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
PKG = "combat"
SRC = ROOT / PKG

def module_name_from_path(py: Path) -> str:
    rel = py.relative_to(ROOT).with_suffix("")  # combat/foo.py
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)

def resolve_import(from_mod: str | None, node: ast.AST) -> set[str]:
    deps: set[str] = set()
    if isinstance(node, ast.Import):
        for a in node.names:
            deps.add(a.name)
    elif isinstance(node, ast.ImportFrom):
        # node.module can be None (e.g. "from . import x")
        base = node.module or ""
        if node.level and from_mod:
            # relative import: peel packages
            parent = from_mod.split(".")[:-node.level]
            base = ".".join(parent + ([base] if base else []))
        deps.add(base if base else from_mod or "")
    return deps

def main():
    edges = set()
    files = sorted(SRC.rglob("*.py"))

    for py in files:
        src = py.read_text(encoding="utf-8")
        mod = module_name_from_path(py)          # combat.xxx
        tree = ast.parse(src, filename=str(py))
        for n in ast.walk(tree):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for dep in resolve_import(mod, n):
                    dep = dep.strip(".")
                    # combat配下だけに絞る（外部依存は除外）
                    if dep == PKG or dep.startswith(PKG + "."):
                        if dep and dep != mod:
                            edges.add((mod, dep))

    # DOT出力
    dot = ["digraph imports {", '  rankdir="LR";', "  node [shape=box];"]
    for a, b in sorted(edges):
        dot.append(f'  "{a}" -> "{b}";')
    dot.append("}")
    (ROOT / "combat_imports.dot").write_text("\n".join(dot), encoding="utf-8")

    # Mermaid出力（Graphviz不要でそのまま表示できる）
    mm = ["graph LR"]
    for a, b in sorted(edges):
        mm.append(f"  {a.replace('.','_')}[{a}] --> {b.replace('.','_')}[{b}]")
    (ROOT / "combat_imports.mmd").write_text("\n".join(mm), encoding="utf-8")

    print("Wrote: combat_imports.dot, combat_imports.mmd")

if __name__ == "__main__":
    main()
