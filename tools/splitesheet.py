from pathlib import Path
from PIL import Image

# ========= 設定 =========
SRC_PATH = r"C:\Users\hirot\iCloudDrive\iCloud~AsheKube~Carnets\beautiful_soup\tools\Font_Icons(2).png"  # 入力ファイル
OUT_DIR = Path("icons")  # 出力フォルダ

SPRITE_W = 8
SPRITE_H = 8
GAP_X = 0
GAP_Y = 0

# 左上の余白がある場合はここを調整（ないなら0のままでOK）
MARGIN_X = 0
MARGIN_Y = 0

# 1行目18枚、2行目16枚（合計34）
ROW_COUNTS = [16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16]

# 出力ファイル名を 001.png ～ 034.png にする（必要なら "1.png" 形式にも変更可）
ZERO_PAD = 3
# ========================


def crop_one(img: Image.Image, col: int, row: int) -> Image.Image:
    x = MARGIN_X + col * (SPRITE_W + GAP_X)
    y = MARGIN_Y + row * (SPRITE_H + GAP_Y)
    return img.crop((x, y, x + SPRITE_W, y + SPRITE_H))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sheet = Image.open(SRC_PATH).convert("RGBA")

    idx = 1
    for row, ncols in enumerate(ROW_COUNTS):
        for col in range(ncols):
            sprite = crop_one(sheet, col, row)

            # 透過だけの画像（完全に透明）をスキップしたい場合は下を有効化
            # if sprite.getbbox() is None:
            #     print(f"skip empty: {idx}")
            #     idx += 1
            #     continue

            name = f"l48_48_{idx:0{ZERO_PAD}d}.png"
            sprite.save(OUT_DIR / name)
            idx += 1

    print(f"done: {idx-1} sprites -> {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
