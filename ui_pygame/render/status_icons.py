# ui_pygame/render/status_icons.py

from combat.constants import STATUS_ICON_KEY_BY_ENUM, STATUS_ENUM_BY_KEY


def draw_status_icons(screen, actor, icon_cache, x, y, spacing=2):
    statuses = getattr(actor.state, "statuses", set()) or set()

    xx = x
    for st in statuses:
        key = STATUS_ICON_KEY_BY_ENUM.get(st)
        if not key:
            continue

        icon = icon_cache.get(key)
        screen.blit(icon, (xx, y))
        xx += icon.get_width() + spacing


def draw_status_immune_icons(
    screen,
    status_immunities,
    icon_cache,
    x,
    y,
    spacing=2,
):
    xx = x

    for st in status_immunities:
        # --- 正規化（ここが超重要） ---
        if isinstance(st, str):
            key = st.strip().lower()
            st_enum = STATUS_ENUM_BY_KEY.get(key)
        else:
            st_enum = st

        if not st_enum:
            continue

        icon_key = STATUS_ICON_KEY_BY_ENUM.get(st_enum)
        if not icon_key:
            continue

        icon = icon_cache.get(icon_key)
        if not icon:
            continue

        screen.blit(icon, (xx, y))
        xx += icon.get_width() + spacing
