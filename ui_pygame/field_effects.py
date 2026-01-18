# field_effects.py
# メニューの「まほう」「アイテム」の処理に利用する純粋に“状態を書き換える”層
from combat.constants import STATUS_ENUM_BY_KEY, Status

FIELD_ITEM_TYPES = ("Anywhere", "Field")


# フィールドで使える所持品一覧
def iter_field_inventory(save_dict: dict) -> list[tuple[str, str, int]]:
    inv = (save_dict or {}).get("inventory", {})
    out: list[tuple[str, str, int]] = []
    for itype in FIELD_ITEM_TYPES:
        bucket = inv.get(itype, {})
        if isinstance(bucket, dict):
            for name, cnt in bucket.items():
                c = int(cnt or 0)
                if c > 0:
                    out.append((str(name), itype, c))
    out.sort(key=lambda t: t[0])
    return out


# 所持数を1減らす
def dec_inventory_item(save_dict: dict, item_type: str, item_name: str) -> bool:
    inv = (save_dict or {}).get("inventory", {})
    bucket = inv.get(item_type, {})
    if not isinstance(bucket, dict):
        return False
    cur = int(bucket.get(item_name, 0) or 0)
    if cur <= 0:
        return False
    nxt = cur - 1
    if nxt <= 0:
        bucket.pop(item_name, None)
    else:
        bucket[item_name] = nxt
    return True


# get_battle_state(actor)（PartyMemberRuntime / BattleActorState の解決）
def get_battle_state(actor):
    st = getattr(actor, "state", None)
    if (
        st is not None
        and hasattr(st, "mp_pool")
        and hasattr(st, "statuses")
        and hasattr(st, "hp")
    ):
        return st
    bt = getattr(actor, "battle", None)
    if (
        bt is not None
        and hasattr(bt, "mp_pool")
        and hasattr(bt, "statuses")
        and hasattr(bt, "hp")
    ):
        return bt
    if (
        hasattr(actor, "mp_pool")
        and hasattr(actor, "statuses")
        and hasattr(actor, "hp")
    ):
        return actor
    return None


# set_hp(actor, new_hp)（BattleActorState.hp を更新）
def set_hp(actor, new_hp: int) -> bool:
    st = get_battle_state(actor)
    if st is None:
        return False

    old = int(st.hp)
    max_hp = int(st.max_hp or old)
    new_hp = max(0, min(int(new_hp), max_hp))
    if new_hp == old:
        return False

    st.hp = new_hp
    return True


# clear_status(actor, Status or key)（BattleActorState.statuses から消す）
def clear_status(actor, key: str, save_dict=None) -> bool:
    changed = False
    key_l = str(key).strip().lower()

    # (A) 戦闘ロジックの本体：BattleActorState.statuses を消す
    st = get_battle_state(actor)
    if st is not None:
        enum = STATUS_ENUM_BY_KEY.get(key_l)
        if enum is not None:
            before = set(st.statuses)
            st.remove(enum)  # BattleActorState.remove() を使える
            if st.statuses != before:
                changed = True

            # petrify系の追加処理
            if enum in (Status.PARTIAL_PETRIFY, Status.PETRIFY):
                if hasattr(st, "partial_petrify_gauge"):
                    st.partial_petrify_gauge = 0.0

    # (B) 互換のため dict(status_effects) も消す（残してOK）
    se = (
        get_status_effects_dict(actor, save_dict) if isinstance(save_dict, dict) else {}
    )
    if key in se:
        se.pop(key, None)
        changed = True
    if key_l in se:
        se.pop(key_l, None)
        changed = True

    return changed


def get_status_effects_dict(actor, save_dict) -> dict:
    # ここはあなたの設計に合わせて：
    # - battle.statuses (set[Status]) しかないなら、それを savedata形式(dict)に変換する必要がある
    # - 既に actor に status_effects(dict) があるならそれを使う
    se = getattr(actor, "status_effects", None)
    nm = getattr(actor, "name", None)
    if isinstance(se, dict):
        return se
    # 無ければ save_dict 側を直接いじる方式にする（簡易）
    if isinstance(save_dict, dict):
        for sp in save_dict.get("party", []):
            if sp.get("name") == nm:
                d = sp.get("status_effects")
                if isinstance(d, dict):
                    return d
                sp["status_effects"] = {}
                return sp["status_effects"]
    return {}


# sync_party_member_to_save(save_dict, actor)（hp/status/mp の保存反映）
def sync_hp_status_to_save(actor, save_dict):
    if not isinstance(save_dict, dict):
        return
    st = get_battle_state(actor)
    if st is None:
        return
    for sp in save_dict.get("party", []):
        if sp.get("name") == getattr(actor, "name", None):
            sp["hp"] = int(st.hp)
            return


def sync_mp_to_save(actor, save_dict, toast=None):
    if not isinstance(save_dict, dict):
        return
    st = get_battle_state(actor)
    if st is None:
        return
    for sp in save_dict.get("party", []):
        if sp.get("name") == getattr(actor, "name", None):
            mp_pool = st.mp_pool
            sp["mp"] = {f"L{i}MP": int(mp_pool.get(i, 0)) for i in range(1, 9)}
            return
    if toast:
        toast("WARN: cannot sync MP to save (name mismatch?)")


def sync_equipment_to_save(a, save_dict):
    if save_dict is None:
        return
    for sp in save_dict.get("party", []):
        if sp.get("name") != a.name:
            continue
        eq = a.equipment
        sp["equipment"] = {
            "main_hand": getattr(eq, "main_hand", None) if eq else None,
            "off_hand": getattr(eq, "off_hand", None) if eq else None,
            "head": getattr(eq, "head", None) if eq else None,
            "body": getattr(eq, "body", None) if eq else None,
            "arms": getattr(eq, "arms", None) if eq else None,
        }
        return
