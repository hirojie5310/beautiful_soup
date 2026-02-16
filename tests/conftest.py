# tests/conftest.py
# pytest 起動時にリポジトリルートを sys.path へ自動追加
# Windows PowerShell でも pytest -q tests/test_battle_lifecycle_dto.py を
# そのまま実行可能です（PYTHONPATH=. のPOSIX書式エラー回避）
from __future__ import annotations

import sys
from pathlib import Path


# pytest 実行環境（PowerShell含む）で `combat` を安定して import できるように
# リポジトリルートを先頭に追加する。
REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)
