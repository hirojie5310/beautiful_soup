# utils.text_normalize.py
# 正規化処理の共通化

import unicodedata
from typing import Any


def normalize_text_basic(value: Any) -> str:
    """
    Basic string normalization used across modules.
    - to str
    - trim
    - lowercase
    """
    return str(value).strip().lower()


def normalize_text_nfkc(value: Any) -> str:
    """
    NFKC-based string normalization.
    - Unicode NFKC
    - trim
    - lowercase
    """
    s = unicodedata.normalize("NFKC", str(value))
    return s.strip().lower()


def normalize_whitespace(value: str) -> str:
    """
    Normalize whitespace runs and full-width spaces.
    """
    s = value.replace("\u3000", " ")
    return " ".join(s.split())
