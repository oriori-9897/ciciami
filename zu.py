"""探した結果を、丸と矢印の絵にする。

⭐ graph.sagasu() の結果を、Graphviz の DOT という書き方の文字列にする係。
   画面では st.graphviz_chart に渡すだけで絵になる（追加のインストールは要らない）。
   左から右へ  ドラフト → 似た企画 → システム → 担当者 → 電話番号  の 5 段に並ぶ。
⭐⭐ 濃い色は「ドラフトに名前が出てこなかった点」。線をたどったから見つかった物がどれかを見せる。
   色の決め方は表と同じ（graph.matomeru の kaite_aru）なので、表と絵で食い違わない。
   電話番号は担当者の付属情報なので薄い色にして、視線が担当者で止まるようにする。
⭐ 電話番号は、graph.matomeru がシステムの行に載せる renraku（台帳の「代表連絡先」。1 システムに 1 つ）から読む。
   担当者ごとの番号ではなく、そのシステムの代表番号を、そのシステムの担当者の右に付ける。
   renraku が空（台帳に無い）なら、電話番号の点は描かない。同じ番号を持つ担当者が何人いても、点は 1 つに合流する。
⚠️ 法令は描かない（点の種類から外した）。kekka に hourei が残っていても読まない。
"""

DRAFT = "ドラフト"

# 色は 1 か所にまとめる。塗り / 文字。
IRO = {
    "draft": ("#0B3C6F", "white"),
    "kikaku": ("#DCE9F7", "black"),
    "atarashii": ("#C2410C", "white"),  # ドラフトに書かれていなかった（たどって見つかった）
    "kizon": ("#EEEEEE", "#555555"),    # ドラフトにすでに書かれていた
}
KATACHI = {"システム": "cylinder", "担当者": "ellipse", "電話番号": "note"}  # note は右上の折れた紙の形
KAIGYOU = chr(92) + "n"  # DOT の中の改行の印（\ と n の 2 文字）


def _q(text: str) -> str:
    """DOT の中で名前を " で囲むための下ごしらえ。"""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ten(name: str, iro: str, katachi: str) -> str:
    """点を 1 つ書く。"""
    nuri, moji = IRO[iro]
    # 長い企画名は、空白の所で 2 行に折る。DOT の改行は「\ と n の 2 文字」で書く。
    label = _q(name).replace(" ", KAIGYOU)
    return f'{_q(name)} [label={label}, shape={katachi}, fillcolor="{nuri}", fontcolor="{moji}"];'


def dot(kekka: dict) -> str:
    """graph.sagasu() の結果を DOT の文字列にする。"""
    lines = [
        "digraph {",
        'rankdir=LR; bgcolor="white"; nodesep=0.25; ranksep=0.9;',
        # ⚠️ 日本語は幅が狭く見積もられ枠からはみ出すので、左右の余白（margin）を広めに取る
        'node [style="filled,rounded", shape=box, fontname="Meiryo", fontsize=11, color="#888888", margin="0.35,0.1"];',
        'edge [fontname="Meiryo", fontsize=9, color="#666666", fontcolor="#444444"];',
        _ten(DRAFT, "draft", "box"),
    ]

    # 1 段目 → 2 段目: ドラフトと、似ている企画。点線は「線をたどった」のではなく「文章が似ている」の意味。
    for k in kekka["nita"]:
        lines.append(_ten(k["title"], "kikaku", "box"))
        lines.append(f'{_q(DRAFT)} -> {_q(k["title"])} [style=dashed, label="似ている {k["score"]:.2f}"];')

    # 3 段目（システム）・4 段目（担当者）・5 段目（電話番号）。表の 1 行が 1 つのシステムの点になる。
    kaita = set()  # 書いた担当者と電話番号の名前。同じ人が 2 つのシステムを担当していても、点は 1 つ。
    for g in kekka["system"]:
        iro = "kizon" if g["kaite_aru"] else "atarashii"
        lines.append(_ten(g["name"], iro, KATACHI["システム"]))
        bangou = str(g.get("renraku") or "")  # そのシステムの代表連絡先。台帳に無ければ ""
        for tantou in filter(None, g["tantou"].split("・")):
            if tantou not in kaita:
                kaita.add(tantou)
                # 担当者はドラフトに書かれていないのが普通なので、いつも濃い色。
                lines.append(_ten(tantou, "atarashii", KATACHI["担当者"]))
            # ⚠️ 本当の線の向きは 担当者 → システム。担当者を右の段に置きたいので、
            #    システム → 担当者 の順に書き、dir=back で矢じりだけを逆（システム側）に付ける。
            lines.append(f'{_q(g["name"])} -> {_q(tantou)} [dir=back, label="担当する"];')

            # 5 段目: 電話番号。番号が無ければ描かない（空の点を増やさない）。
            if not bangou:
                continue
            if bangou not in kaita:
                kaita.add(bangou)
                # 同じ代表連絡先を持つ担当者が 2 人いれば、点は 1 つに合流する（＝その部署の番号）。
                lines.append(_ten(bangou, "kizon", KATACHI["電話番号"]))
            # 線の向きは本当に 担当者 → 電話番号 なので、dir=back は要らない。
            lines.append(f'{_q(tantou)} -> {_q(bangou)} [label="電話"];')

    # 2 段目 → 3 段目の線。⚠️ システムへの線だけ。graph.py が法令の道を返している間も、法令の点が勝手に生えないように。
    for m in kekka["michi"]:
        if m["shurui"] == "システム":
            lines.append(f'{_q(m["kikaku"])} -> {_q(m["saki"])} [label="{m["kankei"]}"];')

    lines.append("}")
    return "\n".join(lines)


if __name__ == "__main__":
    # 単体で動かすと、サンプルのドラフトの DOT が出る（API は呼ばない）。
    import graph
    from loader import DATA_DIR

    print(dot(graph.sagasu((DATA_DIR / "draft_sample.md").read_text(encoding="utf-8"))))
