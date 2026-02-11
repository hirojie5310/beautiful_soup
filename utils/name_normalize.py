# utils.name_normalize.py


import re

from utils.text_normalize import normalize_text_nfkc


def normalize_name(name: str) -> str:
    """
    Name lookup normalizer.
    - Unicode normalization (NFKC)
    - lowercase
    - remove punctuation/symbols
    """
    if not isinstance(name, str):
        raise TypeError("name must be str")

    s = normalize_text_nfkc(name)
    s = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]", "", s)
    return s
