# ============================================================
# inventory: アイテム関連（在庫系）

# build_item_list	save["inventory"]を見て、使えるアイテムのリストを返す
# is_item_visible_in_context	ffiii_items.jsonのキーに合わせた表示可否判定
# get_item_quantity	save["inventory"]全カテゴリ横断で残数取得（無ければ0）
# consume_item_from_inventory	save["inventory"]からitem_nameを1消費する
# add_item_to_inventory	save["inventory"]にitem_nameをqty分加算するヘルパー
# ============================================================

from typing import Dict, Any, Tuple, List


# ============================================================
# セーブデータからアイテムリストを作成
# ============================================================


def is_item_usable(item_def: Dict[str, Any], *, in_battle: bool) -> bool:
    """
    アイテム使用可否判定

    ItemType:
      - Combat   : 戦闘中のみ使用可
      - Anywhere : 戦闘中 / 戦闘外どちらでも使用可
      - Field    : 戦闘外専用（※未実装）
    """
    item_type = item_def.get("ItemType")
    if not isinstance(item_type, str):
        return False

    t = item_type.strip().lower()

    if in_battle:
        # 戦闘中は Combat / Anywhere のみ
        return t in ("combat", "anywhere")

    # 戦闘外
    if t == "anywhere":
        return True

    if t == "field":
        # ★ 将来ここを True にする
        return False

    return False


def build_item_list(
    items_by_name: Dict[str, Dict[str, Any]],
    save: dict,
    *,
    in_battle: bool = True,  # ★追加：戦闘中か？
) -> List[Tuple[str, str, int]]:
    """
    save["inventory"] を見て、使えるアイテムのリストを返す。
    戻り値: [(item_name, itype, qty), ...]
    """
    inv = save.get("inventory") or {}
    if not isinstance(inv, dict):
        return []

    # ★戦闘中に表示してよいカテゴリ
    if in_battle:
        allowed_categories = {"Anywhere", "Combat"}
    else:
        allowed_categories = {
            "Anywhere",
            "Field",
            "Key Item",
        }  # 例：フィールドではCombat非表示

    out: List[Tuple[str, str, int]] = []

    for category, items in inv.items():
        if not isinstance(items, dict):
            continue

        itype = str(category)

        # ★カテゴリで弾く
        if itype not in allowed_categories:
            continue

        for name, qty in items.items():
            if qty is None:
                continue
            qty = int(qty)
            if qty <= 0:
                continue
            if name not in items_by_name:
                continue

            out.append((name, itype, qty))

    out.sort(key=lambda x: (x[1], x[0]))
    return out


# 戦闘中に見せていい物だけに絞るヘルパー関数
def is_item_visible_in_context(item_json: Dict[str, Any], in_combat: bool) -> bool:
    """
    ffiii_items.json のキーに合わせた表示可否判定。
    priority: ItemType > Location > Type
    """
    # まず ItemType を最優先で拾う
    raw = (
        item_json.get("ItemType")
        or item_json.get("Location")
        or item_json.get("Type")
        or ""
    )
    it = str(raw).strip().lower()

    if in_combat:
        # 戦闘中は Key / Field は完全非表示
        if it in ("field", "key item", "key"):
            return False
        # 戦闘中は Anywhere / Combat のみ
        return it in ("anywhere", "combat")

    # 戦闘外
    # 現状は Combat を隠す（Field は将来有効化予定）
    return it != "combat"


# ============================================================
# アイテム効果用ヘルパ（回復・蘇生・状態異常回復）
# ============================================================


# アイテム使用ログに「残り個数」を付けるヘルパー
def get_item_quantity(save: dict, item_name: str) -> int:
    """save["inventory"] 全カテゴリ横断で残数取得（無ければ0）"""
    inv = save.get("inventory") or {}
    if not isinstance(inv, dict):
        return 0
    for _, items in inv.items():
        if isinstance(items, dict) and item_name in items:
            return int(items.get(item_name, 0) or 0)
    return 0


# inventory を減らす共通ヘルパ
def consume_item_from_inventory(save: dict, item_name: str) -> bool:
    """
    save["inventory"] から item_name を 1 消費する。
    - 所持していれば True
    - 見つからない / 個数0なら False

    カテゴリ（Anywhere/Combat/Field/Key Item）を横断して探索。
    """
    inv = save.get("inventory")
    if not isinstance(inv, dict):
        return False

    for category, items in inv.items():
        if not isinstance(items, dict):
            continue

        if item_name in items:
            qty = items.get(item_name, 0) or 0
            if qty <= 0:
                return False

            qty -= 1
            if qty == 0:
                # 0になったらキー削除（表示や再構築がラクになる）
                del items[item_name]
            else:
                items[item_name] = qty
            return True

    return False


# インベントリにアイテムを「増やす」ヘルパー（盗賊の"Steal"対応）
def add_item_to_inventory(save: dict, item_name: str, qty: int = 1) -> str:
    """
    save["inventory"] に item_name を qty 分加算するヘルパー。
    すでにどこかのカテゴリに存在すればそこへ加算、
    無ければ "Anywhere" カテゴリを作ってそこに入れる。
    戻り値はアイテムを入れたカテゴリ名。
    """
    if save is None:
        return ""

    inv = save.setdefault("inventory", {})
    if not isinstance(inv, dict):
        return ""

    # 既にどこかのカテゴリにあればそこへ加算
    for category, items in inv.items():
        if not isinstance(items, dict):
            continue
        if item_name in items:
            current = int(items.get(item_name, 0) or 0)
            items[item_name] = current + qty
            return str(category)

    # 見つからなければ "Anywhere" に追加
    category = "Anywhere"
    items = inv.setdefault(category, {})
    if not isinstance(items, dict):
        items = {}
        inv[category] = items

    current = int(items.get(item_name, 0) or 0)
    items[item_name] = current + qty
    return category
