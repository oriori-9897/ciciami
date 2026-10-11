"""企画書の文章から、点と線と、企画の属性（商品・販売開始月・ターゲット）を抜く。

⭐ 図の「しまう」の 2 番目の係。LLM を呼ぶのは、アプリの中でここだけ。
   点 … 登場する物の名前（システム）
   線 … 企画と点の関係（「この企画はこのシステムを使う」）
   属性 … 商品（投資信託・預金・払いの 3 軸）・販売開始月・ターゲット。
          企画書の概要の表（対象商品・ターゲット層・実施期間）にある語を、jouken.py の選択肢のどれかにそろえて返させる。
          ranking_v2.py のボーナス点は、この属性とドラフトの条件を jouken.py で見比べて決まる。
⭐⭐ 抜くのは LLM、形を決めるのはこちら。点の種類・線の種類・属性の値を SCHEMA で縛るので、
   LLM が勝手に「部署」や「協力する」や「中高年層」を作ることはない。点や線を増やしたいときは下の 2 行を直す。
   属性の選択肢を増やしたいときは jouken.py を直す（ここは jouken.py を読んでいるだけ）。
⭐ 点と線と属性は、同じ 1 回の LLM 呼び出しで抜く。文章は 1 回しか送らないので、属性を足しても API 代と時間は変わらない。
⭐⭐ 点と線の種類の全体（グラフにあるもの）と、ここで抜く分
   点 … 企画 ／ システム ／ 担当者 ／ 電話番号      → LLM が抜くのは「システム」だけ。
   線 … 使う ／ 担当する ／ 電話                    → LLM が抜くのは「使う」（企画 → システム）だけ。
   「企画」の点は題名からこちらで足す。「担当者」「電話番号」の点と「担当する」「電話」の線は、
   台帳の表（システム担当者・代表連絡先の列）から database.py がそのまま作る。文章から抜く必要が無い。
⚠️ 法令は抜かない（点の種類から外した）。戻したいときは TEN_SHURUI に "法令"、SEN_SHURUI に "関わる" を足し、SYSTEM の説明にも 2 行戻す。
⚠️ 属性の読み替えの決め（企画書側）
   - 書いていない商品は「なし」（扱わない）。""（不明）にはしない。企画書は扱う商品を書く文書なので、書いていない＝扱わない。
   - 投資信託の軸は具体的な方が勝つ。NISA ＞ 積み立て ＞ 投資信託。
   - 販売開始月は実施期間の開始日の月。終了月は使わない。年は捨てる。「冬」「下期」のように月が無ければ 0（推測しない）。
"""

import json

import jouken
import llm

TEN_SHURUI = ["システム"]      # LLM に選ばせる点の種類。「企画」はこちらで足し、「担当者」「電話番号」は台帳から来る
SEN_SHURUI = ["使う"]          # LLM に選ばせる線の種類。企画→システム。「担当する」「電話」は台帳から来る

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
        # 企画の属性。値は jouken.py の選択肢に縛る（キー名は jouken.KARA と同じ）。
        "zokusei": {
            "type": "object",
            "properties": {
                "toushin": {"type": "string", "enum": jouken.TOUSHIN},
                "yokin": {"type": "string", "enum": jouken.YOKIN},
                "hoken": {"type": "string", "enum": jouken.HOKEN},
                # ⚠️ integer に minimum / maximum を付けると API が 400 を返す。範囲は nuku() の中で 0〜12 に丸める。
                "tsuki": {"type": "integer"},   # 0 = 書いていない
                "target": {"type": "string", "enum": jouken.TARGET},
            },
            "required": ["toushin", "yokin", "hoken", "tsuki", "target"],
            "additionalProperties": False,
        },
    },
    "required": ["ten", "sen", "zokusei"],
    "additionalProperties": False,
}

SYSTEM = """社内の過去の企画書から、ナレッジグラフの点と線と、企画の属性を抜き出します。
抜いた点と線は、別の企画を立てる人が「似た企画で使ったシステム」をたどり、
システムの担当者に相談しに行くために使います。企画書に書いてあることだけを抜き、書いていない関係は作りません。
属性は、別の企画を立てる人が「商品・時期・ターゲットが同じ過去の企画」を探すために使います。

点の種類
- システム: 社内システムの名前（例: 勘定系システム）。法令・部署・担当者は点にしない

線の種類（向きを守る）
- 使う: 企画 → システム

名前のそろえ方
- 「すでにある点」と同じ物を指しているなら、新しい名前を作らず、その名前をそのまま使う。
  略称や言い換え（「勘定系」と「勘定系システム」）、「別名」に書かれた呼び方は、同じ物として扱う。
- 線の moto には渡された企画名を、saki には ten に入れた名前を、そのまま使う。

企画の属性（zokusei）。値は決まった選択肢から選ぶ。主に「キャンペーン概要」の表（対象商品・ターゲット層・実施期間）を読む。
企画書に書いていない商品は「なし」（その商品は扱わない、という意味）。
- toushin: 投資信託の軸。NISA（NISA 口座・つみたて投資枠・成長投資枠など）／ 積み立て（投資信託の積立・毎月の買付）／ 投資信託（一括の投信）／ なし
  複数に当てはまるときは、具体的な方を選ぶ: NISA ＞ 積み立て ＞ 投資信託。
- yokin:   預金の軸。定期預金（円定期・外貨定期・積立定期も含む）／ なし。普通口座の開設だけなら「なし」
- hoken:   保険の軸。一時払い ／ 平準払い ／ なし。保険の払い方が書いてあるときだけ選ぶ
- tsuki:   販売開始月。実施期間の開始日の月を 1〜12 で答える（「2026年11月1日～2027年1月29日」なら 11）。
  終了月は使わない。年は捨てる。「告知開始」と「販売開始」が別にあれば販売開始の方。
  月が書いていなければ 0。「冬」「下期」「ボーナス時期」のような言葉から月を推測しない。
- target:  ターゲット。若年層（10〜20代・学生・新社会人）／ 現役層（30〜50代・給与所得者）／ 高齢層（60代以上・シニア・退職者）／ なし（全年代・年代の記述なし）
  年齢の幅が 2 つにまたがるときは、中心の年代で選ぶ。"""


def nuku(kikaku: dict, kizon: list[dict]) -> dict:
    """1 つの企画書から点と線と属性を抜く。

    kikaku … {"title", "body"}
    kizon  … すでに DB にある点 {"name", "shurui", "betsumei"}。
             ⭐ これを LLM に見せることで、名前のゆれをそろえる。台帳のシステム名が先に入っているので、
                企画書が「CRM」と書いていても、台帳の「顧客管理システム」にそろう。
                そろわないと別の点になり、企画 → システム → 担当者 の線がつながらない。
    戻り値 … {"ten": [...], "sen": [...], "zokusei": {...}}
             zokusei は {"toushin", "yokin", "hoken", "tsuki", "target"}（jouken.KARA と同じキー）。
             shimau.py がこれを企画書の行に足して database.save_kikaku に渡す。
    """
    kizon = [t for t in kizon if t["shurui"] in TEN_SHURUI]  # 企画・担当者・電話番号の点は、名前そろえに要らない（システムだけ見せる）
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

    # 属性。月だけは 1〜12 の外（LLM が -1 や 13 を返したとき）を 0（書いていない）に丸める。
    zokusei = data["zokusei"]
    zokusei["tsuki"] = int(zokusei["tsuki"]) if 1 <= int(zokusei["tsuki"]) <= 12 else 0
    return {"ten": ten, "sen": sen, "zokusei": zokusei}


if __name__ == "__main__":
    # 単体で動かすと、1 件目の企画書から抜いた点と線と属性が出る（API を 1 回呼ぶ）。
    from loader import load_kikaku

    kekka = nuku(load_kikaku()[0], [])
    for t in kekka["ten"]:
        print("点", t["shurui"], t["name"])
    for s in kekka["sen"]:
        print("線", s["moto"], f"--{s['kankei']}-->", s["saki"])
    print("属性", jouken.moji(kekka["zokusei"]))
