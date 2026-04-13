# scripts/build_wasm_bundle.py
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "web_wasm" / "python_bundle.zip"
DEFAULT_INCLUDE_DIRS = (
    "combat",
    "assets/data",
    "schemas",
    "system",
    "utils",
)

DEFAULT_INCLUDE_FILES = ("requirements.txt",)

ALLOWED_SUFFIXES = {".py", ".json", ".csv", ".txt"}


def iter_bundle_sources(
    root: Path = REPO_ROOT,
    *,
    include_dirs: tuple[str, ...] = DEFAULT_INCLUDE_DIRS,
    include_files: tuple[str, ...] = DEFAULT_INCLUDE_FILES,
) -> list[Path]:
    files: list[Path] = []
    for rel_dir in include_dirs:
        base_dir = root / rel_dir
        for path in sorted(base_dir.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            if path.suffix not in ALLOWED_SUFFIXES:
                continue
            files.append(path)

    for rel_file in include_files:
        path = root / rel_file
        if path.is_file():
            files.append(path)

    return files


def build_wasm_bundle(
    output_path: Path = DEFAULT_OUTPUT,
    *,
    root: Path = REPO_ROOT,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as zip_file:
        for path in iter_bundle_sources(root):
            zip_file.write(path, path.relative_to(root).as_posix())
    return output_path


def main() -> None:
    output_path = build_wasm_bundle()
    print(f"Wrote Wasm bundle: {output_path}")


if __name__ == "__main__":
    main()
