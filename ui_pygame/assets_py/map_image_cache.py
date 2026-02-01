import pygame

from pathlib import Path


# グループ名 → 画像ファイル名の変換
def group_name_to_image_key(name: str) -> str:
    return name.lower().replace("'", "").replace(" ", "_")


# マッププレビュー画像の読み込み（キャッシュ付き）
def load_map_preview(
    group_name: str,
    cache: dict[str, pygame.Surface | None],
) -> pygame.Surface | None:
    key = group_name_to_image_key(group_name)

    if key in cache:
        return cache[key]

    base = Path("assets/images/maps")
    for ext in (".png", ".jpg", ".jpeg", ".PNG", ".JPG"):
        path = base / f"{key}{ext}"
        if path.exists():
            img = pygame.image.load(path).convert_alpha()
            cache[key] = img
            return img

    cache[key] = None
    return None
