"""ドラフトに似た企画を探し、そこから線をたどる。

⭐ 図の「探す」のまん中の係。やることは 3 段。LLM は呼ばない。
   ① 探す     … ドラフトと文章が似ている過去企画を出す（並べる計算は ranking_v2.py に任せる）
   ② たどる   … その企画から出ている線を追い、法令・システム・その担当者まで引き出す
   ③ まとめる … たどった道を、画面の表の形（1 システム 1 行、1 法令 1 行）にそろえる
⭐⭐ ②があるので、**ドラフトに一度も書かれていない語**が出てくる。
   ドラフトに「景品表示法」と書いていなくても、似た企画がその法令につながっていれば拾える。
"""

import database
import ranking_v2


def nita_kikaku(draft: str, kikaku: list[dict], n: int = 3) -> list[dict]:
    """ドラフトに似た過去企画を、似ている順に n 件返す。本文（原文）も一緒に返す。

    ⚠️ ranking_v2.py には足切りがある（似ている度合いが 0.01 以下は出さない）。
       似た企画が 1 つも無いドラフトでは、n 件より少なく返ることがある。
    """
    return ranking_v2.narabu(draft, kikaku, n)


def tadoru(titles: list[str]) -> list[dict]:
    """企画から線をたどる。企画 → 法令／システム → （システムなら）担当者。

    戻り値は 1 本の道が 1 行。例:
      {"kikaku": "…口座開設…", "kankei": "使う", "saki": "勘定系システム",
       "shurui": "システム", "tantou": "佐藤"}
    """
    michi = []
    for title in titles:
        for sen in database.sen_from(title):
            tantou = ""
            if sen["shurui"] == "システム":
                # 線を**逆向き**に読む。システム ← 担当する ← 誰？
                tantou = "・".join(database.sen_to(sen["saki"], "担当する"))
            michi.append(
                {
                    "kikaku": title,
                    "kankei": sen["kankei"],
                    "saki": sen["saki"],
                    "shurui": sen["shurui"],
                    "tantou": tantou,
                }
            )
    return michi


def kaite_aru(name: str, draft: str, betsumei: str = "") -> bool:
    """その点の名前が、ドラフトにすでに書かれているか。

    ⚠️ 「勘定系システム」は、ドラフトに「勘定系」とだけ書かれていても「書いてある」と見なす。
       台帳の別名（CRM など）で書かれていても同じ。
    """
    mijikai = name.removesuffix("システム")
    if name in draft or (len(mijikai) >= 2 and mijikai in draft):
        return True
    return bool(betsumei) and betsumei in draft


def matomeru(draft: str, michi: list[dict]) -> dict:
    """たどった道を、表の形にそろえる。同じシステム・同じ法令は 1 行にまとめ、出どころの企画を並べる。

    戻り値 … {"system": [...], "hourei": [...]}。どちらも、多くの類似企画から着いた順。
    ⭐ システムの行には、台帳の表から 担当者・部署・稼働の決まり を足す。
       台帳に載っていないシステム（企画書にだけ出てくる）は、担当者が空のまま出る。＝聞く相手が分からない所。
    """
    gyou = {}  # 行き先の名前 → 行
    for m in michi:
        if m["saki"] not in gyou:
            d = database.daichou_of(m["saki"]) if m["shurui"] == "システム" else {}
            gyou[m["saki"]] = {
                "name": m["saki"],
                "shurui": m["shurui"],
                "tantou": m["tantou"],
                "busho": d.get("busho", ""),
                "kimari": d.get("kimari", ""),
                "kikaku": [],
                "kaite_aru": kaite_aru(m["saki"], draft, d.get("betsumei", "")),
            }
        gyou[m["saki"]]["kikaku"].append(m["kikaku"])

    narabi = sorted(gyou.values(), key=lambda g: -len(g["kikaku"]))  # 同じ件数なら、たどった順のまま
    return {
        "system": [g for g in narabi if g["shurui"] == "システム"],
        "hourei": [g for g in narabi if g["shurui"] == "法令"],
    }


def sagasu(draft: str, n: int = 3) -> dict:
    """ドラフトを受け取って、見つけた物をまとめて返す。app.py が画面に出し、zu.py が絵にする。"""
    nita = nita_kikaku(draft, database.all_kikaku(), n)
    michi = tadoru([k["title"] for k in nita])
    return {"nita": nita, "michi": michi, **matomeru(draft, michi)}


if __name__ == "__main__":
    # 単体で動かすと、サンプルのドラフトで探した結果が出る（API は呼ばない）。
    from loader import DATA_DIR

    kekka = sagasu((DATA_DIR / "draft_sample.md").read_text(encoding="utf-8"))
    for k in kekka["nita"]:
        print(f"{k['score']:.2f}  {k['title']}")
    for g in kekka["system"] + kekka["hourei"]:
        print(f"  {g['shurui']} {g['name']}  担当: {g['tantou'] or '-'}  ← {len(g['kikaku'])} 件")
