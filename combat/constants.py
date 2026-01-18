# ============================================================
# constants: 世界のルールそのもの ゲーム仕様・ロジック定数
# 属性相性、コマンド種別、状態異常種別 ❌ 基本変更しない

# JOB_CAST_CODE: 「そのジョブが実際に詠唱できる魔法」に絞り込むためのキー
# OFFENSIVE_WHITE: 白魔法の中でも「攻撃魔法」として扱う魔法名の集合（HolyやAero系など）で、白魔ダメージ計算対象の判定に使われる
# OFFENSIVE_WHITE_ELEMENTS: 白魔法を名前ではなく「属性」で攻撃判定するための属性集合（holy/air）で、SpellInfoにnameが無い場合の代替判定に使われる
# COMMAND_TO_KIND: 戦闘コマンド文字列（Fight,Magic,Item,Runなど）をBattleKindに正規化変換するための対応表
# _ELEMENT_SYNONYMS: 属性名の同義語（例:fire=flameなど）を正規化・展開するための対応辞書で、属性相性計算の統一処理に使用される
# STATUS_NAME_MAP: AoE状態異常専用関数用
# MASTER_SPELLS_BY_NAME（宣言だけ置く（中身の代入は data_loader 側））: spells.jsonから読み込んだ魔法定義を「魔法名→魔法JSON」の辞書として全体共有するためのグローバルキャッシュ
# ============================================================

from typing import Dict, Any

from combat.enums import Status
from combat.enums import BattleKind


# CastBy を併用したい場合の job → code
JOB_CAST_CODE = {
    "Red Mage": "RM",
    "White Mage": "WM",
    "Black Mage": "BM",
    "Evoker": "Ev",
    "Devout": "De",
    "Magus": "Ma",
    "Summoner": "Su",
    "Sage": "Sa",
}

# 白魔で「攻撃扱い」する名前と属性
OFFENSIVE_WHITE = {"holy", "aero", "aeroga"}  # 必要なら追加
OFFENSIVE_WHITE_ELEMENTS = {"holy", "air"}

# フィールド使用対象魔法（小文字で統一）
FIELD_MAGIC_WHITELIST = {
    "warp",
    "teleport",
    # 回復
    "cure",
    "cura",
    "curaga",
    "curaja",
    # 蘇生
    "raise",
    "arise",
    # 状態回復
    "poisona",
    "blindna",
    "stona",
    "esuna",
    # 状態付与（フィールド用）
    "mini",
    "toad",
    # 情報系
    "sight",
}

# フィールドで「対象を選ぶ」必要がある魔法
FIELD_MAGIC_TARGET_REQUIRED = {
    "cure",
    "cura",
    "curaga",
    "curaja",
    "raise",
    "arise",
    "poisona",
    "blindna",
    "stona",
    "mini",
    "toad",
    # esuna は作品によって「単体/全体」が揺れるので、必要なら入れてください
    "esuna",
}

# 状態名
STATUS_ENUM_BY_KEY = {
    "poison": Status.POISON,
    "blind": Status.BLIND,
    "mini": Status.MINI,
    "silence": Status.SILENCE,
    "toad": Status.TOAD,
    "confusion": Status.CONFUSION,
    "sleep": Status.SLEEP,
    "paralysis": Status.PARALYZE,
    "petrification": Status.PETRIFY,
    "partial petrification": Status.PARTIAL_PETRIFY,  # あなたのEnum名に合わせて
    "ko": Status.KO,
}

# 「対象が必要なアイテム」ホワイトリスト
FIELD_ITEM_TARGET_REQUIRED = {
    # 回復
    "potion",
    "hi potion",
    "elixir",
    # 状態回復
    "antidote",  # Poisona :contentReference[oaicite:4]{index=4}
    "echo herbs",  # 沈黙回復（データに存在）:contentReference[oaicite:5]{index=5}
    "mallet",  # Mini
    "maiden's kiss",  # Toad
    "gold needle",  # 石化/部分石化回復
    "eye drops",  # Blind
    # 蘇生
    "phoenix down",
}


COMMAND_TO_KIND: Dict[str, BattleKind] = {
    # 物理
    "Fight": "physical",
    "Attack": "physical",
    "Sing": "physical",  # ★ 追加：Bard の Sing は Fight と同じ物理攻撃
    # 魔法
    "Magic": "magic",
    # アイテム
    "Item": "item",
    # 防御
    "Defend": "defend",
    # ジャンプ
    "Jump": "jump",
    # 逃走（表記揺れを全部吸収）
    "Run": "run",
    "Flee": "run",
    "Run(Flee)": "run",
    "Run (Flee)": "run",
}

_ELEMENT_SYNONYMS = {
    "air": {"air", "wind"},
    "wind": {"air", "wind"},
    "thunder": {"thunder", "lightning"},
    "lightning": {"thunder", "lightning"},
}

# AoE状態異常専用関数用
STATUS_NAME_MAP = {
    "paralysis": Status.PARALYZE,
    # 必要なら追加
    # "confusion": Status.CONFUSION,
    # "toad": Status.TOAD,
    # ...
}

# spells.json の name → spell 定義を保持するためのグローバル
MASTER_SPELLS_BY_NAME: Dict[str, Dict[str, Any]] = {}

# 状態異常の短縮名
STATUS_ABBR = {
    "Poison": "POI",
    "Blind": "BLD",
    "Mini": "MIN",
    "Silence": "SIL",
    "Toad": "TOA",
    "Petrification": "STN",
    "KO": "KO",
    "Confusion": "CON",
    "Sleep": "SLP",
    "Paralysis": "PAR",
    "Partial Petrification": "PST",
}
