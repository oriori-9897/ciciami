"""企画書・台帳の表・点と線を SQLite にしまう。

⭐ 図の「しまう」の 3 番目の係と、まん中の「DB」。表は 4 つ。
   kikaku  … 過去の企画書の本文（似た企画を探すのに使う。原文もここから出す）
   daichou … システム台帳の表（CSV をそのまま。1 行が 1 システム）
   ten     … 点。登場する物の名前（企画・法令・システム・担当者）
   sen     … 線。点どうしの関係（moto --kankei--> saki）
⭐⭐ どの表にも UNIQUE を付け、INSERT OR IGNORE で書く。
   「資料を読み込む」を 2 回押しても、同じ行が 2 つにならない（＝重ならないように書く）。
"""

import csv
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "shishiami.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS kikaku (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,
    body  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daichou (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    system   TEXT NOT NULL UNIQUE,   -- システム名
    betsumei TEXT,                   -- 別名（例: CRM）
    tantou   TEXT,                   -- 担当者
    busho    TEXT,                   -- 部署
    kimari   TEXT                    -- 稼働の決まり
);
CREATE TABLE IF NOT EXISTS ten (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL UNIQUE,   -- 例: 景品表示法
    shurui TEXT NOT NULL           -- 企画 / 法令 / システム / 担当者
);
CREATE TABLE IF NOT EXISTS sen (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    moto   TEXT NOT NULL,   -- 線の出どころ（ten.name）
    kankei TEXT NOT NULL,   -- 関わる / 使う / 担当する
    saki   TEXT NOT NULL,   -- 線の行き先（ten.name）
    UNIQUE (moto, kankei, saki)
);
"""


TABLES = ("kikaku", "daichou", "ten", "sen")


def connect() -> sqlite3.Connection:
    """接続を開いて、表が無ければ作る。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 行を row["title"] のように列名で読めるようにする
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------- 書く
def save_kikaku(kikaku: list[dict]) -> None:
    with connect() as conn:  # with を抜けるときに commit される
        conn.executemany(
            "INSERT OR IGNORE INTO kikaku (title, body) VALUES (?, ?)",
            [(k["title"], k["body"]) for k in kikaku],
        )


def save_daichou(rows: list[dict]) -> None:
    """台帳の表を書く。あわせて、表から読める点と線（担当者 --担当する--> システム）も書く。

    ⭐ CSV の日本語の列名を、表の列に当てはめる。
    ⭐⭐ 担当者とシステムの線は、表の 1 行がそのまま 1 本の線になる。LLM は通さない。
    """
    with connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO daichou (system, betsumei, tantou, busho, kimari) VALUES (?, ?, ?, ?, ?)",
            [(r["システム名"], r["別名"], r["担当者"], r["部署"], r["稼働の決まり"]) for r in rows],
        )
    ten = [{"name": r["システム名"], "shurui": "システム"} for r in rows]
    ten += [{"name": r["担当者"], "shurui": "担当者"} for r in rows if r["担当者"]]
    sen = [{"moto": r["担当者"], "kankei": "担当する", "saki": r["システム名"]} for r in rows if r["担当者"]]
    save_ten_sen(ten, sen)


def save_ten_sen(ten: list[dict], sen: list[dict]) -> None:
    """点と線を書く。すでにある点・線は飛ばす。"""
    with connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO ten (name, shurui) VALUES (?, ?)",
            [(t["name"], t["shurui"]) for t in ten],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO sen (moto, kankei, saki) VALUES (?, ?, ?)",
            [(s["moto"], s["kankei"], s["saki"]) for s in sen],
        )


def reset() -> None:
    """4 つの表を空にする。読み込みをやり直すとき用。"""
    with connect() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")


# ---------------------------------------------------------------- 読む
def _rows(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def all_kikaku() -> list[dict]:
    return _rows("SELECT title, body FROM kikaku ORDER BY id")


def all_daichou() -> list[dict]:
    return _rows("SELECT system, betsumei, tantou, busho, kimari FROM daichou ORDER BY id")


def daichou_of(system: str) -> dict:
    """そのシステムの台帳の行。台帳に載っていなければ空の辞書。"""
    rows = _rows("SELECT system, betsumei, tantou, busho, kimari FROM daichou WHERE system = ?", (system,))
    return rows[0] if rows else {}


def all_ten() -> list[dict]:
    """点を全部。システムには台帳の別名も付ける（extract.py が名前をそろえるのに使う）。"""
    return _rows(
        """
        SELECT ten.name, ten.shurui, daichou.betsumei
        FROM ten LEFT JOIN daichou ON daichou.system = ten.name
        ORDER BY ten.shurui, ten.name
        """
    )


def all_sen() -> list[dict]:
    return _rows("SELECT moto, kankei, saki FROM sen ORDER BY id")


def sen_from(moto: str) -> list[dict]:
    """その点から**出ている**線。行き先の種類も一緒に返す。"""
    return _rows(
        """
        SELECT sen.kankei, sen.saki, ten.shurui
        FROM sen JOIN ten ON ten.name = sen.saki
        WHERE sen.moto = ?
        ORDER BY ten.shurui, sen.saki
        """,
        (moto,),
    )


def sen_to(saki: str, kankei: str) -> list[str]:
    """その点に**入ってくる**線の出どころ。例: システム ← 担当する ← 誰？"""
    rows = _rows("SELECT moto FROM sen WHERE saki = ? AND kankei = ? ORDER BY moto", (saki, kankei))
    return [r["moto"] for r in rows]


def kazu() -> dict:
    """各表の件数。画面の横に出す。"""
    with connect() as conn:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }


def kakidasu() -> Path:
    """点と線を CSV に書き出す。DB のファイルはそのままでは開けないので、Excel で見るため。

    ⚠️ encoding は utf-8-sig。ただの utf-8 だと、Excel で開いたときに日本語が文字化けする。
    """
    out = Path(__file__).parent / "export"
    out.mkdir(exist_ok=True)
    for name, header, rows in (
        ("ten.csv", ["点", "種類"], [(t["name"], t["shurui"]) for t in all_ten()]),
        ("sen.csv", ["出どころ", "関係", "行き先"], [(s["moto"], s["kankei"], s["saki"]) for s in all_sen()]),
    ):
        with open(out / name, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
    return out


if __name__ == "__main__":
    # 単体で動かすと、件数を出して、点と線を export/ に書き出す。
    print(kazu(), "→", kakidasu())
