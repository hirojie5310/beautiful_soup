# ============================================================
# models: Job / Character / Enemy などデータクラス

# SideTurnResult: 片側（キャラ側or敵側）のターン処理の結果（終了理由・逃走可否・敵被弾情報など）をまとめる結果クラス
# BattleActorState: 戦闘中のアクター（キャラ/敵）の変動ステータス（HP・状態異常・MP・部分石化ゲージ・リフレク・一時フラグなど）を保持するクラス
# JobLevelStats: ジョブごとのレベル別ステータス（Str/Agi/Vit/Int/MndとMPテーブル）を1レベル分だけ保持する行クラス
# Job: ジョブ名・取得条件と、レベル別ステータス/武器防具/魔法定義など原データを束ねるジョブ定義クラス
# BaseCharacter: 装備を含まないキャラクターの基礎ステータス（レベル・職Lv・能力値・前列/後列）を表すクラス
# EquipmentSet: キャラクターが装備している武器/防具（main_hand/off_hand/head/body/arms）の名前セットを表すクラス
# FinalCharacterStats: 装備・ジョブ補正を反映したキャラクターの最終戦闘ステータス（攻撃力・防御・魔防・属性耐性・武器属性など）を表すクラス
# FinalEnemyStats: 敵JSONから整形された敵側の最終戦闘ステータス（攻撃・防御・魔防・疑似Agilityなど）を表すクラス
# SpellInfo: 魔法の威力・命中率・種別（黒/白/召喚など）・属性リストをまとめたシンプルな魔法定義クラス
# EnemyCasterStats: 敵が魔法攻撃を行うときの魔力・倍率・命中率など「敵キャスター」としてのパラメータを表すクラス
# EnemyAttackResult: 敵の1回の攻撃結果（ダメージ値・攻撃種別・属性相性・クリティカル・付与状態異常など）を保持するクラス
# OneTurnResult: シミュレーション1ターン分の結果（両者のBattleActorState・ログ・敵攻撃結果・逃走フラグ・終了理由）をまとめるクラス
# PartyMember: パーティ側1メンバーの名前・最終ステータス(FinalCharacterStats)・戦闘状態(BattleActorState)を束ねるクラス
# EnemyUnit: 敵ユニット1体分の名前・FinalEnemyStats・BattleActorState・元monsters.json行(raw_json)をまとめるクラス
# PartyMemberRuntime: ランタイム（別モジュール側）で使うパーティメンバー情報（名前・ジョブ・ステータス・状態）を保持するためのラッパークラス
# EnemyRuntime: ランタイムで使う敵ユニット情報（名前・ステータス・状態・元JSON）を保持するためのラッパークラス
# PlannedAction: そのターンに予定している行動（物理/魔法/アイテム/防御などの種別とコマンド名・魔法名・アイテム名・ターゲット情報）を表すクラス
# PartyMagicInfo: パーティのジョブ名、使用できる魔法リスト等を表すクラス
# AttackResult: 攻撃結果（キャラ攻撃・敵攻撃 共通で使える）
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Optional,
    Literal,
    Dict,
    Tuple,
    Any,
    List,
    Set,
    FrozenSet,
    Sequence,
    Collection,
    TypeAlias,
    TypedDict,
)

from combat.enums import Status, ElementRelation, BattleEndReason, MagicType, BattleKind


# UI/戦闘共通のターゲット概念
TargetSide: TypeAlias = Literal["enemy", "ally", "self"]
# 「魔法メニューに並ぶ1行」という意味を持つデータ
MagicCandidate: TypeAlias = tuple[str, MagicType, int]  # (name, type, level)
# (name, lv, cost)
SpellTuple = Tuple[str, int, int]  # (name, lv, cost) 例


# 戦闘イベントの型定義
class DamageEvent(TypedDict):
    type: Literal["damage"]
    enemy_index: int
    value: int


class StatusEvent(TypedDict):
    type: Literal["status"]
    enemy_index: int
    names: list[str]


BattleEvent = DamageEvent | StatusEvent


# 逃走や敵撃破などの情報を返すための簡単な結果クラス
@dataclass
class SideTurnResult:
    end_reason: Literal[
        "continue",
        "enemy_defeated",
        "char_defeated",
        "escaped",
        "enemy_escaped",
        "forced_end",
    ]
    escaped: bool = False
    # 将来のためのフック（例：このターン物理で殴ったか？など）
    enemy_was_physically_hit: bool = False
    enemy_attack_result: Optional[EnemyAttackResult] = None  # 敵ターン用


@dataclass
class BattleActorState:
    hp: int
    statuses: Set[Status] = field(default_factory=set)
    max_hp: Optional[int] = None

    mp_pool: Dict[int, int] = field(default_factory=lambda: {i: 0 for i in range(1, 9)})
    max_mp_pool: Dict[int, int] = field(
        default_factory=lambda: {i: 0 for i in range(1, 9)}
    )

    partial_petrify_gauge: float = 0.0

    # ★ Reflect 用
    reflect_charges: int = 0

    # ★ Dragoon のジャンプ中フラグ
    is_jumping: bool = False
    jump_target_index: Optional[int] = None

    # ★ このターンだけ有効な一時フラグ（防御・Boost中など）
    temp_flags: Dict[str, bool] = field(default_factory=dict)

    # ★ Black Belt / Monk の Boost 溜め回数
    boost_count: int = 0

    # ★ Bard の Cheer 回数
    cheer_count: int = 0  # ★ 追加

    def has(self, status: Status) -> bool:
        return status in self.statuses

    def add(self, status: Status) -> None:
        self.statuses.add(status)

    def remove(self, status: Status) -> None:
        self.statuses.discard(status)


@dataclass
class JobLevelStats:
    level: int
    strength: int
    agility: int
    vitality: int
    intelligence: int
    mind: int
    mp: Dict[str, int] = field(default_factory=dict)


@dataclass
class Job:
    name: str
    slug: str
    earned: str
    stats_by_level: Dict[int, JobLevelStats]
    raw: Dict[
        str, Any
    ]  # Weapons / Armors / Spells なども後で使いたければここに残しておく


@dataclass
class BaseCharacter:
    """キャラクターの基礎ステータス（装備を加味しない）"""

    level: int
    total_exp: int
    job_level: int
    job_skill_point: int  # ★追加（0..99）
    max_hp: int
    strength: int
    agility: int
    vitality: int
    intelligence: int
    mind: int
    row: str = "front"  # "front" or "back"


@dataclass
class EquipmentSet:
    """キャラクターの装備構成（名前は JSON の name と一致させる）"""

    main_hand: Optional[str] = None
    off_hand: Optional[str] = None
    head: Optional[str] = None
    body: Optional[str] = None
    arms: Optional[str] = None


@dataclass
class FinalCharacterStats:
    """ダメージ計算に使うキャラクター最終ステータス"""

    level: int
    job_level: int
    max_hp: int
    strength: int
    agility: int
    vitality: int
    intelligence: int
    mind: int
    row: str

    # 物理攻撃（手ごと）
    main_power: int
    main_accuracy: int
    main_atk_multiplier: int
    main_two: bool
    main_long: bool
    off_power: int
    off_accuracy: int
    off_atk_multiplier: int
    off_two: bool
    off_long: bool

    # 防御系
    defense: int
    defense_multiplier: int
    evasion_percent: int
    magic_defense: int
    magic_def_multiplier: int
    magic_resistance: int
    shield_count: int

    # 追加：防具による属性耐性（ElementalResist の集約）
    elemental_resists: FrozenSet[str] = field(default_factory=frozenset)
    elemental_nulls: FrozenSet[str] = field(default_factory=frozenset)
    elemental_weaks: FrozenSet[str] = field(default_factory=frozenset)
    elemental_absorbs: FrozenSet[str] = field(default_factory=frozenset)

    # 追加：防具によるステータス異常耐性
    status_immunities: FrozenSet[str] = field(default_factory=frozenset)  # ★追加

    # ★追加：武器の属性（手ごと）
    main_weapon_elements: List[str] = field(default_factory=list)
    off_weapon_elements: List[str] = field(default_factory=list)


@dataclass
class FinalEnemyStats:
    """ダメージ計算に使う敵最終ステータス（JSON からそのまま整形）"""

    name: str
    hp: int
    level: int
    job_level: int

    # 物理攻撃
    attack_power: int
    attack_multiplier: int
    accuracy_percent: int

    # 物理防御
    defense: int
    defense_multiplier: int
    evasion_percent: int

    # 魔法防御
    magic_defense: int
    magic_def_multiplier: int
    magic_resistance_percent: int

    # 行動順決定用の「擬似 Agility」
    agility: int


# 魔法用構造体
@dataclass
class SpellInfo:
    power: int  # BasePower
    accuracy_percent: int
    magic_type: str  # "black", "white" など
    elements: List[str]


@dataclass
class EnemyCasterStats:
    """敵が魔法攻撃を行う際のパラメータ"""

    magic_power_base: int
    magic_multiplier: int
    magic_accuracy_percent: int


# 攻撃結果を返す用の dataclass
@dataclass
class EnemyAttackResult:
    damage: int
    attack_type: Literal["normal", "special", "mixed"]  # mixed = 期待値モード
    attack_name: Optional[str] = None  # special のとき Spell 名など
    is_crit: bool = False
    # ★追加
    net_hits: Optional[float] = None

    # 属性相性など
    element_relation: ElementRelation = "normal"
    hit_elements: List[str] = field(default_factory=list)

    # 状態異常
    inflicted_status: Optional[str] = None
    status_success_prob: float = 0.0

    # ★追加：この攻撃が「Reflectable: Yes」の Spell に由来するか？
    is_reflectable_spell: bool = False


# 1ターンの攻防ループ結果用クラス
@dataclass
class OneTurnResult:
    # 変更後:
    char_state: BattleActorState
    enemy_state: BattleActorState
    logs: List[str]
    enemy_attack_result: Optional[EnemyAttackResult]
    escaped: bool = False  # ★追加
    end_reason: BattleEndReason = "continue"  # ★追加


# Party ---------------------
# PartyMember / EnemyUnit の型
@dataclass
class PartyMember:
    name: str
    stats: FinalCharacterStats
    state: BattleActorState
    # 必要ならセーブデータ1行そのものも持っておける
    # entry: dict | None = None


@dataclass
class EnemyUnit:
    name: str
    stats: FinalEnemyStats
    state: BattleActorState
    raw_json: Dict[str, Any]  # monsters[enemy_name] の dict


# ランタイム用の構造体
@dataclass
class PartyMemberRuntime:
    name: str
    job: "Job"
    base: "BaseCharacter"  # ★追加
    stats: "FinalCharacterStats"
    state: "BattleActorState"
    portrait_key: Optional[str] = None  # ★追加（例: "runeth", "refia"）

    equipment_logs: List[str] = field(default_factory=list)
    equipment: Optional["EquipmentSet"] = None

    @property
    def hp(self) -> int:
        return self.state.hp

    @property
    def max_hp(self) -> int:
        return self.state.max_hp if self.state.max_hp is not None else self.state.hp

    @property
    def mp_pool(self) -> Dict[int, int]:
        return self.state.mp_pool

    @property
    def max_mp_pool(self) -> Dict[int, int]:
        return self.state.max_mp_pool

    @property
    def mp(self) -> int:
        return sum(self.state.mp_pool.values())

    @property
    def max_mp(self) -> int:
        return sum(self.state.max_mp_pool.values())

    # 「battle」という名前で参照したいなら field ではなく property にする
    @property
    def battle(self) -> "BattleActorState":
        return self.state


@dataclass
class EnemyRuntime:
    name: str
    stats: FinalEnemyStats
    state: BattleActorState
    json: Dict[str, Any]  # ← raw_json ではなく json にそろえる

    sprite_id: Optional[str] = None

    is_boss: bool = False

    @property
    def hp(self) -> int:
        return self.state.hp

    @property
    def max_hp(self) -> int:
        return self.state.max_hp if self.state.max_hp is not None else self.state.hp


@dataclass
class PlannedAction:
    kind: BattleKind
    command: Optional[str] = (
        None  # "Fight", "Defend", "Steal" などジョブコマンドの文字列
    )
    spell_name: Optional[str] = None
    item_name: Optional[str] = None

    # ★ 追加：ターゲット情報
    target_side: Literal["enemy", "ally", "self"] = "enemy"
    target_index: Optional[int] = None  # enemy/ally リストのインデックス

    # ★追加：範囲（全体）指定。主に魔法（One/All, All）で使う
    target_all: bool = False


@dataclass
class PartyMagicInfo:
    job_name: str
    cast_code: Optional[str]
    allowed_names: Optional[Collection[str]]
    magic_list: Sequence[MagicCandidate]  # ← 3要素タプルに合わせる


# 攻撃結果（キャラ攻撃・敵攻撃 共通で使える）
@dataclass
class AttackResult:
    damage: int
    hit_count: int
    is_critical: bool = False


@dataclass(frozen=True)
class PartyEntryBuildResult:
    base: BaseCharacter
    eq: EquipmentSet
    state: BattleActorState
    eq_logs: List[str]
    job_name: str
    job: Job
