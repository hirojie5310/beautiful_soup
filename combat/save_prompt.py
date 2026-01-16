from typing import List, Tuple, Any, Sequence, Dict
from pathlib import Path
import json
import shutil
import pygame
from datetime import datetime

from combat.data_loader import save_savedata


# (name, blv, alv, bexp, aexp, bjl, ajl, bsp, asp)
DiffRow = Tuple[str, int, int, int, int, int, int, int, int]


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
            diffs.append((name, blv, alv, bexp, aexp, bjl, ajl, bsp, asp))

    return diffs


def prompt_save_progress_and_write(
    *,
    before_save: dict,
    after_save: dict,
    save_path: Path,
) -> bool:
    diffs = diff_party_progress(before_save, after_save)

    if not diffs:
        print("\n[Save] 進捗更新はありません（Lv/EXP/JobLv/SP）。保存は不要です。")
        return False

    print("\n=== Save Preview (Lv/EXP/JobLv/SP changes) ===")
    for name, blv, alv, bexp, aexp, bjl, ajl, bsp, asp in diffs:
        lv_str = f"Lv{blv} -> Lv{alv}" if blv != alv else f"Lv{blv}"
        jl_str = f"JobLv{bjl} -> JobLv{ajl}" if bjl != ajl else f"JobLv{bjl}"

        parts = [
            f"- {name}: {lv_str}, EXP {bexp} -> {aexp}",
            f"{jl_str}, SP {bsp} -> {asp}",
        ]
        print(" / ".join(parts))

    ans = input("\nこの更新をセーブデータに保存しますか？ [y/N]: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[Save] キャンセルしました。")
        return False

    save_savedata_with_backup(save_path, after_save)
    print(f"[Save] 保存しました: {save_path}")
    print(f"[Save] バックアップ: {save_path}.bak")
    return True


def save_savedata_with_backup(path: Path, save: dict) -> None:
    """
    savedata を JSON として保存する。
    既存ファイルがあれば .bak を作成してから上書きする。
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # ① バックアップ作成
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_name(f"{path.name}.{ts}.bak")
        shutil.copy2(path, backup_path)

    # ② 新しい savedata を書き込み
    with path.open("w", encoding="utf-8") as f:
        json.dump(save, f, ensure_ascii=False, indent=2)


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
    ans = input(f"{latest.name} から復元しますか？ [y/N]: ").strip().lower()
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


def prompt_save_progress_and_write_pygame(
    *,
    screen: pygame.Surface,
    font: pygame.font.Font,
    before_save: dict,
    after_save: dict,
    save_path: Path,
    save_func,
    caption: str = "Save updated progress?",
) -> bool:
    diffs = diff_party_progress(before_save, after_save)

    if not diffs:
        _toast_pygame(screen, font, "[Save] No progress changes.", ms=900)
        return False

    lines = ["=== Save Preview (Lv/EXP/JobLv/SP changes) ==="]
    for name, blv, alv, bexp, aexp, bjl, ajl, bsp, asp in diffs:
        lv_str = f"Lv{blv} -> Lv{alv}" if blv != alv else f"Lv{blv}"
        jl_str = f"JobLv{bjl} -> JobLv{ajl}" if bjl != ajl else f"JobLv{bjl}"
        lines.append(f"- {name}: {lv_str}, EXP {bexp} -> {aexp}")
        lines.append(f"    {jl_str}, SP {bsp} -> {asp}")

    lines.append("")
    lines.append("Y: Save   N(or ESC): Cancel")

    ok = _prompt_lines_yes_no(screen, font, caption, lines)
    if not ok:
        _toast_pygame(screen, font, "[Save] Cancelled.", ms=700)
        return False

    save_func(save_path, after_save)
    _toast_pygame(screen, font, f"[Save] Saved: {save_path.name}", ms=900)
    return True


def _prompt_lines_yes_no(
    screen: pygame.Surface,
    font: pygame.font.Font,
    title: str,
    lines: Sequence[str],
) -> bool:
    """
    lines を表示して、Y/N（ESCもN扱い）で返す。
    """
    w, h = screen.get_size()
    clock = pygame.time.Clock()

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYUP:
                if ev.key == pygame.K_y:
                    return True
                if ev.key in (pygame.K_n, pygame.K_ESCAPE):
                    return False

        # 背景
        screen.fill((0, 0, 0))

        # タイトル
        y = 40
        _draw_center_text(screen, font, title, y)
        y += 50

        # 本文（左寄せで見やすく）
        margin_x = 40
        line_h = font.get_linesize() + 6
        for line in lines:
            surf = font.render(line, True, (255, 255, 255))
            screen.blit(surf, (margin_x, y))
            y += line_h
            if y > h - 30:
                break  # 画面に収まらない分は切る（必要ならスクロール拡張）

        pygame.display.flip()
        clock.tick(60)


def _draw_center_text(
    screen: pygame.Surface, font: pygame.font.Font, text: str, y: int
) -> None:
    surf = font.render(text, True, (255, 255, 255))
    rect = surf.get_rect(center=(screen.get_width() // 2, y))
    screen.blit(surf, rect)


def _toast_pygame(
    screen: pygame.Surface, font: pygame.font.Font, message: str, ms: int = 800
) -> None:
    """
    短い通知を一定時間表示（操作不要）
    """
    clock = pygame.time.Clock()
    start = pygame.time.get_ticks()

    while pygame.time.get_ticks() - start < ms:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return

        screen.fill((0, 0, 0))
        _draw_center_text(screen, font, message, screen.get_height() // 2)
        pygame.display.flip()
        clock.tick(60)
