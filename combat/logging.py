# ============================================================
# logging: ログ出力

# log_damage	ダメージログ文字列を共通フォーマットで組み立ててlogsに追加
# relation_comment	属性相性とヒット属性から表示用コメント文字列を生成
# ============================================================

from typing import Literal

from combat.enums import ElementRelation


# ============================================================
# ログ生成の共通化（ダメージ/属性コメント）
# ============================================================


def log_damage(
    logs: list[str],
    prefix: str,
    target_name: str,
    damage: int,
    old_hp: int,
    new_hp: int,
    perspective: Literal["attacker", "target", "neutral"] = "attacker",
    hp_style: Literal["remain", "arrow", "arrow_with_max"] = "remain",
    max_hp: int | None = None,
    suffix: str = "",
    shout: bool = False,
) -> None:
    """
    ダメージログを組み立てて logs に追加するユーティリティ（位置引数対応版）
    """

    # 本文（誰がどれだけ喰らったか）
    if perspective == "attacker":
        main = f"{target_name}に{damage}のダメージ"
    elif perspective == "target":
        main = f"{target_name}は{damage}のダメージを受けた"
    else:  # "neutral"
        main = f"{target_name}は{damage}のダメージ"

    main += "！" if shout else "。"

    # HP 部分
    if hp_style == "remain":
        hp_part = f"（{target_name} 残りHP: {new_hp}）"
    elif hp_style == "arrow":
        hp_part = f"（{old_hp}→{new_hp}）"
    elif hp_style == "arrow_with_max" and max_hp is not None:
        hp_part = f"（{old_hp}→{new_hp}/{max_hp}）"
    else:
        hp_part = ""

    logs.append(f"{prefix}{main}{hp_part}{suffix}")


# 属性相性コメント
def relation_comment(
    relation: ElementRelation,
    hit_elems: list[str] | None = None,
    *,
    perspective: str = "attacker",  # "attacker" / "target"
) -> str:
    """
    属性相性とヒット属性名から、表示用コメントを返す。

    perspective:
      - "attacker": 攻撃側視点（例: 弱点をついた！）
      - "target"  : 被弾側視点   (例: 弱点を突かれた！)
    """
    if perspective == "target":
        if relation == "weak":
            msg = "弱点を突かれた！"
        elif relation == "resist":
            msg = "耐性で軽減した！"
        elif relation == "absorb":
            msg = "属性を吸収した！"
        elif relation == "null":
            msg = "無効化した！"
        else:
            msg = ""
    else:  # 攻撃側視点（これまで使っていた方）
        if relation == "weak":
            msg = "弱点をついた！"
        elif relation == "resist":
            msg = "耐性がある…"
        elif relation == "absorb":
            msg = "吸収されてしまった！"
        elif relation == "null":
            msg = "無効化された！"
        else:
            msg = ""

    suffix = ""
    if relation != "normal" and hit_elems:
        suffix = "（" + "/".join(e.title() for e in hit_elems) + "）"

    return msg + suffix
