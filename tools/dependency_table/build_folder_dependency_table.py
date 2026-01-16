from __future__ import annotations

import ast
from pathlib import Path
import pandas as pd


def collect_py_files(root: Path) -> list[Path]:
    return [
        p for p in root.rglob("*.py")
        if p.is_file() and p.name != "__init__.py"
    ]


def file_to_module(root: Path, py_file: Path) -> str:
    """
    a/b/c.py -> a.b.c
    a/b/__init__.py -> a.b
    """
    rel = py_file.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def all_module_prefixes(modules: set[str]) -> set[str]:
    prefixes = set()
    for m in modules:
        segs = m.split(".")
        for i in range(1, len(segs) + 1):
            prefixes.add(".".join(segs[:i]))
    return prefixes


def normalize_to_project_module(name: str, project_prefixes: set[str]) -> str | None:
    """
    import名を、プロジェクト内に存在する最長prefixへ正規化
    例: pkg.sub.mod.util -> pkg.sub.mod（存在する最長prefix）
    """
    cur = name
    while cur:
        if cur in project_prefixes:
            return cur
        if "." not in cur:
            return None
        cur = cur.rsplit(".", 1)[0]
    return None


def resolve_importfrom_base(current_module: str, level: int, module: str | None) -> str:
    """
    ImportFrom の base module を絶対名に近い形へ解決
    """
    cur_parts = current_module.split(".") if current_module else []
    pkg_parts = cur_parts[:-1]  # current_module の package 部分

    if level == 0:
        base = module.split(".") if module else []
    else:
        # level=1 -> 同一package, level=2 -> 1つ上, ...
        up = max(0, len(pkg_parts) - (level - 1))
        base = pkg_parts[:up]
        if module:
            base += module.split(".")
    return ".".join(base)


def extract_project_imports(
    py_file: Path,
    project_prefixes: set[str],
    current_module: str,
    exclude_self: bool = True,
) -> set[str]:
    """
    1ファイルから「自作モジュールのみ」のimport依存を抽出
    """
    imports: set[str] = set()

    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return imports

    def add_if_project(name: str):
        m = normalize_to_project_module(name, project_prefixes)
        if not m:
            return
        if exclude_self and m == current_module:
            return
        imports.add(m)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add_if_project(alias.name)

        elif isinstance(node, ast.ImportFrom):
            base = resolve_importfrom_base(current_module, node.level, node.module)

            # base 自体
            if base:
                add_if_project(base)

            # from base import y が「base.y（サブモジュール）」の可能性もあるので試す
            for alias in node.names:
                cand = f"{base}.{alias.name}" if base else alias.name
                add_if_project(cand)

    return imports


def build_pyfile_dependency_table(root_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    returns:
      - dependency matrix df (rows: py files, cols: project modules)
      - cycles list df_cycles (pairs)
    """
    root = Path(root_dir).resolve()
    py_files = collect_py_files(root)

    # 列候補: プロジェクト内モジュール（実在する.py/パッケージ）
    project_modules = {
        file_to_module(root, f)
        for f in py_files
        if file_to_module(root, f)
    }
    project_prefixes = all_module_prefixes(project_modules)

    # 行: 相対パスでソート（= フォルダ階層順）
    row_paths = sorted([f.relative_to(root).as_posix() for f in py_files])

    deps_by_row: dict[str, set[str]] = {}
    module_by_row: dict[str, str] = {}

    # 依存抽出
    for f in py_files:
        row = f.relative_to(root).as_posix()
        current_module = file_to_module(root, f)
        module_by_row[row] = current_module

        imps = extract_project_imports(
            f,
            project_prefixes=project_prefixes,
            current_module=current_module,
            exclude_self=True,  # ★① 自分自身を除外
        )
        deps_by_row[row] = imps

    # 表作成
    df = pd.DataFrame("", index=row_paths, columns=sorted(project_modules))
    for row in row_paths:
        for m in deps_by_row.get(row, set()):
            if m in df.columns:
                df.loc[row, m] = "〇"

    # ★③ フォルダ階層順（相対パス順）に並べる（既に row_paths がソート済み）
    df = df.sort_index()

    # ★② 循環参照チェック
    # 「AがBをimportし、BがAをimport」の相互参照（2-cycle）を検出
    # ※より長いサイクル検出も可能ですが、まず実務で多い2-cycleを確実に出す版です
    row_to_module = {row: module_by_row[row] for row in df.index}
    module_to_row = {}
    for row, mod in row_to_module.items():
        if mod:
            module_to_row[mod] = row

    edges = set()
    for row, imps in deps_by_row.items():
        src_mod = module_by_row.get(row, "")
        if not src_mod:
            continue
        for dst_mod in imps:
            if dst_mod in project_modules:
                edges.add((src_mod, dst_mod))

    mutual_pairs = set()
    for a, b in edges:
        if (b, a) in edges and a != b:
            mutual_pairs.add(tuple(sorted((a, b))))

    # cycles表（見やすいようにpyファイルパスも併記）
    cycles_rows = []
    for a, b in sorted(mutual_pairs):
        cycles_rows.append({
            "module_a": a,
            "module_b": b,
            "py_a": module_to_row.get(a, ""),
            "py_b": module_to_row.get(b, ""),
        })
    df_cycles = pd.DataFrame(cycles_rows, columns=["module_a", "module_b", "py_a", "py_b"])

    return df, df_cycles


if __name__ == "__main__":
    root = "beautiful_soup"  # ←対象フォルダに変更

    df, df_cycles = build_pyfile_dependency_table(root)

    print("=== Dependency Matrix ===")
    print(df)

    print("\n=== Mutual (2-way) Cycles ===")
    if df_cycles.empty:
        print("No mutual cycles found.")
    else:
        print(df_cycles)

    df.to_csv("dependency_pyfile.csv", encoding="utf-8-sig")
    df_cycles.to_csv("dependency_cycles_mutual.csv", encoding="utf-8-sig", index=False)
