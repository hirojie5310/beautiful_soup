import re
import unicodedata


def normalize_name(name: str) -> str:
    """
    名前正規化ルール（表記ゆれ吸収）
    - Unicode正規化（NFKC）
    - 小文字化
    - 空白・記号除去
    """
    if not isinstance(name, str):
        raise TypeError("name must be str")

    # 全角半角・互換文字の正規化
    s = unicodedata.normalize("NFKC", name)

    # 小文字化
    s = s.lower()

    # 空白・記号を除去（英数と日本語だけ残す）
    s = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]", "", s)

    return s
