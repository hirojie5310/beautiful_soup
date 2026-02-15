from typing import List, Tuple, Any, Dict
from pathlib import Path
import shutil

from assets.data.data_loader import save_savedata
from utils.text_normalize import normalize_text_basic


# (name, job_name, blv, alv, bexp, aexp, bjl, ajl, bsp, asp)
DiffRow = Tuple[str, str, int, int, int, int, int, int, int, int]


def diff_party_progress(before_save: dict, after_save: dict) -> List[DiffRow]:
    before_party = before_save.get("party", [])
    after_party = after_save.get("party", [])
    if not isinstance(before_party, list) or not isinstance(after_party, list):
        return []

    before_by_name: Dict[str, Dict[str, Any]] = {}
    for e in before_party:
        if not isinstance(e, dict):
            continue
        n = e.get("name")
        if isinstance(n, str) and n:
            before_by_name[n] = e

    after_by_name: Dict[str, Dict[str, Any]] = {}
    for e in after_party:
        if not isinstance(e, dict):
            continue
        n = e.get("name")
        if isinstance(n, str) and n:
            after_by_name[n] = e

    diffs: List[DiffRow] = []
    for name, b in before_by_name.items():
        a = after_by_name.get(name)
        if a is None:
            continue

        job_name = str(a.get("job"))

        # --- Lv/EXP ---
        blv = int(b.get("level", 1))
        alv = int(a.get("level", 1))
        bexp = int(b.get("exp", 0))
        aexp = int(a.get("exp", 0))

        # --- JobLv/SP ---
        bjl_obj = b.get("job_level", {})
        ajl_obj = a.get("job_level", {})

        bjl = int(bjl_obj.get("level", 1)) if isinstance(bjl_obj, dict) else 1
        ajl = int(ajl_obj.get("level", 1)) if isinstance(ajl_obj, dict) else 1
        bsp = int(bjl_obj.get("skill_point", 0)) if isinstance(bjl_obj, dict) else 0
        asp = int(ajl_obj.get("skill_point", 0)) if isinstance(ajl_obj, dict) else 0

        # どれかが変化していたら差分として採用
        if (blv != alv) or (bexp != aexp) or (bjl != ajl) or (bsp != asp):
            diffs.append((name, job_name, blv, alv, bexp, aexp, bjl, ajl, bsp, asp))

    return diffs


def prompt_save_progress_and_write(
    *,
    before_save: dict,
    after_save: dict,
    save_path: Path,
) -> bool:
    # ギル差分も取得
    before_gil = int(before_save.get("gil", 0))
    after_gil = int(after_save.get("gil", 0))
    gil_diff = after_gil - before_gil

    # CP差分も取得
    before_cp = int(before_save.get("CP", 0))
    after_cp = int(after_save.get("CP", 0))
    cp_diff = after_cp - before_cp

    diffs = diff_party_progress(before_save, after_save)

    if not diffs:
        print("\n[Save] 進捗更新はありません（Lv/EXP/JobLv/SP）。保存は不要です。")
        return False

    print("\n=== Save Preview (Lv/EXP/JobLv/SP changes) ===")
    for name, job, blv, alv, bexp, aexp, bjl, ajl, bsp, asp in diffs:
        lv_str = f"Lv{blv} -> Lv{alv}" if blv != alv else f"Lv{blv}"
        if ajl == 99:
            jl_str = f"{job} JobLv99 (MAX)"
        elif ajl > bjl:
            jl_str = f"{job} JobLv{bjl} -> JobLv{ajl} ↑"
        else:
            jl_str = f"{job} JobLv{bjl}"
        parts = [
            f"- {name}: {lv_str}, EXP {bexp} -> {aexp}",
            f"{jl_str}, SP {bsp} -> {asp}",
        ]
        print(" / ".join(parts))

    # ギル差分も表示
    if gil_diff != 0:
        print("")
        sign = "+" if gil_diff > 0 else ""
        print(f"Gil: {before_gil} -> {after_gil} ({sign}{gil_diff})")

    # CP差分も表示
    if cp_diff != 0:
        sign = "+" if cp_diff > 0 else ""
        print(f"CP: {before_cp} -> {after_cp} ({sign}{cp_diff})")

    ans = normalize_text_basic(
        input("\nこの更新をセーブデータに保存しますか？ [y/N]: ")
    )
    if ans not in ("y", "yes"):
        print("[Save] キャンセルしました。")
        return False

    save_savedata_with_backup(save_path, after_save)
    print(f"[Save] 保存しました: {save_path}")
    return True


def save_savedata_with_backup(path: Path, save: dict) -> None:
    """
    savedata を JSON として保存する。
    互換性のため関数名は維持するが、.bak バックアップは作成しない。
    """
    save_savedata(path, save)


def list_savedata_backups(path: Path) -> List[Path]:
    """
    指定した savedata の日付付き .bak を新しい順で返す
    """
    pattern = path.name + ".*.bak"
    backups = list(path.parent.glob(pattern))
    backups.sort(reverse=True)  # 文字列順＝日付新しい順
    return backups


def restore_latest_backup(path: Path) -> bool:
    backups = list_savedata_backups(path)
    if not backups:
        print("[Restore] バックアップが見つかりません。")
        return False

    latest = backups[0]
    ans = normalize_text_basic(input(f"{latest.name} から復元しますか？ [y/N]: "))
    if ans not in ("y", "yes"):
        print("[Restore] キャンセルしました。")
        return False

    shutil.copy2(latest, path)
    print(f"[Restore] 復元完了: {latest.name} → {path.name}")
    return True


def restore_backup_by_choice(path: Path) -> bool:
    """
    バックアップ一覧から番号選択して復元
    """
    backups = list_savedata_backups(path)
    if not backups:
        print("[Restore] バックアップが存在しません。")
        return False

    print("\n=== 利用可能なバックアップ ===")
    for i, b in enumerate(backups, 1):
        print(f"{i}: {b.name}")

    try:
        choice = int(input("復元する番号を選んでください (0でキャンセル): "))
    except ValueError:
        return False

    if choice <= 0 or choice > len(backups):
        print("[Restore] キャンセルしました。")
        return False

    target = backups[choice - 1]
    import shutil

    shutil.copy2(target, path)
    print(f"[Restore] 復元完了: {target.name} → {path.name}")
    return True


# アイテム差分取得用の小関数
def diff_item_stock(after_save: dict):
    """
    return: [(item_name, gained_count), ...]
    """
    item_stock = after_save.get("item_stock", {})
    return [(item, count) for item, count in item_stock.items() if count != 0]
