"""企画書の文章から、点と線を抜く。

⭐ 図の「しまう」の 2 番目の係。LLM を呼ぶのは、アプリの中でここだけ。
   点 … 登場する物の名前（法令・システム）
   線 … 企画と点の関係（「この企画はこの法令に関わる」「この企画はこのシステムを使う」）
⭐⭐ 抜くのは LLM、形を決めるのはこちら。点の種類と線の種類を SCHEMA で縛るので、
   LLM が勝手に「部署」や「協力する」を作ることはない。増やしたいときは下の 2 行を直す。
⚠️ 担当者はここでは抜かない。担当者とシステムの線は、台帳の表から database.py がそのまま作る。
"""

import json

import llm

TEN_SHURUI = ["法令", "システム"]      # 「企画」はこちらで足すので、LLM には選ばせない
SEN_SHURUI = ["関わる", "使う"]        # 企画→法令 ／ 企画→システム

SCHEMA = {
    "type": "object",
    "properties": {
        "ten": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "shurui": {"type": "string", "enum": TEN_SHURUI},
                },
                "required": ["name", "shurui"],
                "additionalProperties": False,
            },
        },
        "sen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "moto": {"type": "string"},
                    "kankei": {"type": "string", "enum": SEN_SHURUI},
                    "saki": {"type": "string"},
                },
                "required": ["moto", "kankei", "saki"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["ten", "sen"],
    "additionalProperties": False,
}

SYSTEM = """社内の過去の企画書から、ナレッジグラフの点と線を抜き出します。
抜いた点と線は、別の企画を立てる人が「似た企画で関わった法令・使ったシステム」をたどり、
システムの担当者に相談しに行くために使います。企画書に書いてあることだけを抜き、書いていない関係は作りません。

点の種類
- 法令: 法律の名前（例: 景品表示法）
- システム: 社内システムの名前（例: 勘定系システム）

線の種類（向きを守る）
- 関わる: 企画 → 法令
- 使う: 企画 → システム

名前のそろえ方
- 「すでにある点」と同じ物を指しているなら、新しい名前を作らず、その名前をそのまま使う。
  略称や言い換え（「勘定系」と「勘定系システム」）、「別名」に書かれた呼び方は、同じ物として扱う。
- 線の moto には渡された企画名を、saki には ten に入れた名前を、そのまま使う。"""


def nuku(kikaku: dict, kizon: list[dict]) -> dict:
    """1 つの企画書から点と線を抜く。

    kikaku … {"title", "body"}
    kizon  … すでに DB にある点 {"name", "shurui", "betsumei"}。
             ⭐ これを LLM に見せることで、名前のゆれをそろえる。台帳のシステム名が先に入っているので、
                企画書が「CRM」と書いていても、台帳の「顧客管理システム」にそろう。
                そろわないと別の点になり、企画 → システム → 担当者 の線がつながらない。
    戻り値 … {"ten": [...], "sen": [...]}
    """
    kizon = [t for t in kizon if t["shurui"] in TEN_SHURUI]  # 企画・担当者の点は、名前そろえに要らない
    kizon_text ="\n".join(
        f"- {t['name']}（{t['shurui']}" + (f"、別名: {t['betsumei']}" if t.get("betsumei") else "") + "）"
        for t in kizon
    ) or "（まだ無い）"
    user = (
        f"企画名: {kikaku['title']}\n\n"
        f"すでにある点:\n{kizon_text}\n\n"
        f"企画書:\n{kikaku['body']}"
    )
    data = json.loads(llm.yobu_json(SYSTEM, user, SCHEMA))

    # 企画そのものも点にする。名前は LLM に任せず、題名をそのまま使う。
    ten = [{"name": kikaku["title"], "shurui": "企画"}] + data["ten"]

    # ⚠️ 出どころがこの企画で、行き先が「知っている点」の線だけ残す。
    #    片方が宙に浮いた線は、たどった先で行き止まりになる。
    shitteiru = {t["name"] for t in ten} | {t["name"] for t in kizon}
    sen = [s for s in data["sen"] if s["moto"] == kikaku["title"] and s["saki"] in shitteiru]
    return {"ten": ten, "sen": sen}


if __name__ == "__main__":
    # 単体で動かすと、1 件目の企画書から抜いた点と線が出る（API を 1 回呼ぶ）。
    from loader import load_kikaku

    kekka = nuku(load_kikaku()[0], [])
    for t in kekka["ten"]:
        print("点", t["shurui"], t["name"])
    for s in kekka["sen"]:
        print("線", s["moto"], f"--{s['kankei']}-->", s["saki"])
