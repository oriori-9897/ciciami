"""探した結果を、丸と矢印の絵にする。

⭐ graph.sagasu() の結果を、Graphviz の DOT という書き方の文字列にする係。
   画面では st.graphviz_chart に渡すだけで絵になる（追加のインストールは要らない）。
   左から右へ  ドラフト → 似た企画 → 法令・システム → 担当者  の 4 段に並ぶ。
⭐⭐ 濃い色は「ドラフトに名前が出てこなかった点」。線をたどったから見つかった物がどれかを見せる。
   色の決め方は表と同じ（graph.matomeru の kaite_aru）なので、表と絵で食い違わない。
"""

DRAFT = "ドラフト"

# 色は 1 か所にまとめる。塗り / 文字。
IRO = {
    "draft": ("#0B3C6F", "white"),
    "kikaku": ("#DCE9F7", "black"),
    "atarashii": ("#C2410C", "white"),  # ドラフトに書かれていなかった（たどって見つかった）
    "kizon": ("#EEEEEE", "#555555"),    # ドラフトにすでに書かれていた
}
KATACHI = {"法令": "box", "システム": "cylinder", "担当者": "ellipse"}
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

    # 3 段目（法令・システム）と 4 段目（担当者）。表の 1 行が 1 つの点になる。
    kaita = set()
    for g in kekka["system"] + kekka["hourei"]:
        iro = "kizon" if g["kaite_aru"] else "atarashii"
        lines.append(_ten(g["name"], iro, KATACHI[g["shurui"]]))
        for tantou in filter(None, g["tantou"].split("・")):
            if tantou not in kaita:
                kaita.add(tantou)
                # 担当者はドラフトに書かれていないのが普通なので、いつも濃い色。
                lines.append(_ten(tantou, "atarashii", KATACHI["担当者"]))
            # ⚠️ 本当の線の向きは 担当者 → システム。担当者を右の段に置きたいので、
            #    システム → 担当者 の順に書き、dir=back で矢じりだけを逆（システム側）に付ける。
            lines.append(f'{_q(g["name"])} -> {_q(tantou)} [dir=back, label="担当する"];')

    # 2 段目 → 3 段目の線。
    for m in kekka["michi"]:
        lines.append(f'{_q(m["kikaku"])} -> {_q(m["saki"])} [label="{m["kankei"]}"];')

    lines.append("}")
    return "\n".join(lines)


if __name__ == "__main__":
    # 単体で動かすと、サンプルのドラフトの DOT が出る（API は呼ばない）。
    import graph
    from loader import DATA_DIR

    print(dot(graph.sagasu((DATA_DIR / "draft_sample.md").read_text(encoding="utf-8"))))
