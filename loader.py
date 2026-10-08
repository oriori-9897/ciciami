"""data/ の資料を読んで、形をそろえる。

⭐ 図の「しまう」の 1 番目の係。ここでは**読むだけ**で、中身の解釈はしない。
   文章（過去の企画書）    → extract.py へ渡して点と線を抜く
   表（システム台帳の CSV）→ extract.py を通さず、そのまま database.py へ渡す
"""

import csv
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def load_kikaku() -> list[dict]:
    """過去の企画書（.md）を全部読む。戻り値は 1 資料 1 辞書のリスト。"""
    shiryou = []
    for path in sorted((DATA_DIR / "kikaku").glob("*.md")):
        body = path.read_text(encoding="utf-8")
        # 1 行目の「# 題名」を資料の名前にする。無ければファイル名。
        first = body.splitlines()[0] if body.strip() else ""
        title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
        shiryou.append({"title": title, "body": body})
    return shiryou


def load_daichou() -> list[dict]:
    """システム台帳の表（CSV）を読む。戻り値は 1 行 1 辞書のリスト。

    ⭐ 列は システム名 / 別名 / 担当者 / 部署 / 稼働の決まり。1 行が 1 システム。
       「誰がどのシステムの担当か」は表にそのまま書いてあるので、LLM に抜かせる必要が無い。
    ⚠️ encoding は utf-8-sig。Excel で保存した CSV は先頭に見えない印（BOM）が付き、
       utf-8 で読むと 1 列目の名前が「﻿システム名」になって列が見つからなくなる。
    """
    with open(DATA_DIR / "daichou.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    # 単体で動かすと、何件読めたかだけ出る。取り込みの確認用。
    print(f"企画書 {len(load_kikaku())} 件 ／ 台帳 {len(load_daichou())} 行")
