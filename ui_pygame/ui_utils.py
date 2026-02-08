# スクロール計算ヘルパー


def calc_view_range(cursor: int, total: int, visible: int) -> tuple[int, int]:
    """
    表示開始 index と終了 index を返す
    """
    if total <= visible:
        return 0, total

    half = visible // 2
    start = max(0, cursor - half)
    end = start + visible

    if end > total:
        end = total
        start = end - visible

    return start, end
