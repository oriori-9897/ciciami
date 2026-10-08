"""🦁 獅子編み検索 ver2 — 企画のドラフトから、似た過去企画と、次に相談する相手を引き出す。

起動:  streamlit run app.py
準備:  同じフォルダに .env を作り、ANTHROPIC_API_KEY=... を書く（.env.example を写す）
       キーが要るのは「資料を読み込む」のときだけ。探すときは API を呼ばない。

⭐ 流れは 2 本。
   しまう … 資料を読む → 点と線を抜く → DB にしまう（横の「資料を読み込む」。shimau.py）
   探す   … ドラフトを受け取る → 似た企画を探して線をたどる → 表で返す（まん中。graph.py）
⭐⭐ 返すのは 2 つ。①過去の類似企画（原文）と、②企画 ― システム（法令）― 担当者のつながり。
   ②は表が主役で、絵は補助（折りたたみ）。次の行動は「各担当者と調整」なので、相手が一覧で読める形にする。
"""

import os

import anthropic
import pandas as pd
import streamlit as st

import database
import graph
import shimau
import zu
from loader import DATA_DIR

st.set_page_config(page_title="獅子編み検索 ver2", page_icon="🦁", layout="wide")

MARU = "①②③④⑤"          # 類似企画の番号。表の「使っていた類似企画」の列で、この番号を使う
ATARASHII = "🟠 なし"  # ドラフトに書かれていなかった（＝線をたどったから見つかった）


def api_error(e: Exception) -> str:
    """API の失敗を、次に何をすればよいかが分かる言葉にする。"""
    if isinstance(e, anthropic.AuthenticationError):
        return "API キーが通りませんでした。.env の ANTHROPIC_API_KEY を確かめてください。"
    if isinstance(e, anthropic.RateLimitError):
        return "呼びすぎで止められました。少し待ってからもう一度押してください。"
    if isinstance(e, anthropic.APIConnectionError):
        return "API につながりませんでした。ネットワークを確かめてください。"
    if isinstance(e, anthropic.APIStatusError):
        return f"API がエラーを返しました（{e.status_code}）: {e.message}"
    # キーが見つからない・モデルが断った、など。llm.py が言葉にして投げてくる。
    return str(e)


# ---------------------------------------------------------------- 合言葉
# ⚠️ URL で公開すると、URL を知っている人は誰でもボタンを押せて、その分の API 料金がかかる。
#    環境変数（公開先では Secrets）に APP_AIKOTOBA を入れておくと、合言葉を知る人だけが使える。
#    入れていなければ何も聞かない（手元で動かすときはこちら）。
AIKOTOBA = os.environ.get("APP_AIKOTOBA", "")
if AIKOTOBA and st.text_input("合言葉", type="password") != AIKOTOBA:
    st.info("合言葉を入れると使えます。")
    st.stop()


# ---------------------------------------------------------------- しまう
with st.sidebar:
    st.header("資料を DB にしまう")
    kazu = database.kazu()
    st.caption(
        f"企画書 {kazu['kikaku']} 件 ／ 台帳 {kazu['daichou']} 行 ／ "
        f"点 {kazu['ten']} 個 ／ 線 {kazu['sen']} 本"
    )
    if st.button("資料を読み込む", type="primary", help="企画書の件数ぶん、Claude API を呼びます"):
        bar = st.progress(0.0, text="点と線を抜いています…")
        try:
            shimau.shimau(lambda i, n, title: bar.progress(i / n, text=f"点と線を抜いています… {title}"))
            st.rerun()  # 件数の表示を新しくする
        except (anthropic.AnthropicError, RuntimeError) as e:
            bar.empty()
            st.error(api_error(e))
    if st.button("DB を空にする"):
        database.reset()
        st.session_state.pop("kekka", None)
        st.rerun()

    st.divider()
    kensuu = st.slider("出す類似企画の件数", 1, len(MARU), 3)
    with st.expander("システム台帳（表）を見る"):
        st.dataframe(
            pd.DataFrame(database.all_daichou()).rename(
                columns={"system": "システム名", "betsumei": "別名", "tantou": "担当者", "busho": "部署", "kimari": "稼働の決まり"}
            ),
            hide_index=True,
        )


# ---------------------------------------------------------------- 探す
st.title("🦁 獅子編み検索 ver2")
st.caption("企画のドラフトを渡すと、似た過去企画（原文）と、そこからつながるシステム・法令・担当者を返します。")

if st.button("サンプルのドラフトを入れる"):
    # ⚠️ text_area の中身は key（draft）で session_state に置かれている。ここを書き換えると欄に入る。
    st.session_state["draft"] = (DATA_DIR / "draft_sample.md").read_text(encoding="utf-8")
file = st.file_uploader("ドラフトのファイル（.md / .txt）", type=["md", "txt"])
if file and st.session_state.get("file_name") != file.name:
    st.session_state["file_name"] = file.name  # 同じファイルで、手で直した欄を上書きし直さないための印
    st.session_state["draft"] = file.read().decode("utf-8")
draft = st.text_area("または、ここに貼る", key="draft", height=220)

if st.button("探す", type="primary", disabled=not draft.strip()):
    if kazu["kikaku"] == 0:
        st.warning("DB が空です。先に横の「資料を読み込む」を押してください。")
    else:
        # ⚠️ 結果は session_state に置く。Streamlit はボタンを押すたびに上から全部走り直すので、
        #    ふつうの変数に置くと、次に何かを触った瞬間に結果が消える。
        st.session_state["kekka"] = graph.sagasu(draft, kensuu)

if "kekka" in st.session_state:
    kekka = st.session_state["kekka"]
    if not kekka["nita"]:
        st.info("似ている過去企画が見つかりませんでした。ドラフトの文章を足してみてください。")
        st.stop()
    bangou = {k["title"]: MARU[i] for i, k in enumerate(kekka["nita"])}

    def kikaku_no(titles: list[str]) -> str:
        """企画名のリストを、①の番号に置きかえる。例: ①②"""
        return " ".join(bangou[t] for t in titles)

    # ---------------------------------------------------------- ① 類似企画
    st.subheader("① 過去の類似企画")
    st.caption("ドラフトと文章が似ている順。開くと原文が読めます。")
    for k in kekka["nita"]:
        with st.expander(f"{bangou[k['title']]} {k['title']}　（似ている度合い {k['score']:.2f}）"):
            st.markdown(k["body"])

    # ---------------------------------------------------------- ② つながり（表）
    st.subheader("② つながり — 次に相談する相手")
    zenbu = kekka["system"] + kekka["hourei"]
    hito = {t for g in kekka["system"] for t in g["tantou"].split("・") if t}
    st.caption(
        f"類似企画からたどって、システム {len(kekka['system'])} 件（担当者 {len(hito)} 人）と"
        f"法令 {len(kekka['hourei'])} 件が見つかりました。"
        f"このうち {sum(not g['kaite_aru'] for g in zenbu)} 件は、ドラフトに書かれていなかったものです（🟠）。"
    )

    st.markdown("**システムと担当者**　多くの類似企画が使っていた順")
    if kekka["system"]:
        st.table(
            pd.DataFrame(
                [
                    {
                        "システム": g["name"],
                        "担当者": g["tantou"] or "（台帳に無い）",
                        "部署": g["busho"],
                        "稼働の決まり（台帳より）": g["kimari"],
                        "使っていた類似企画": kikaku_no(g["kikaku"]),
                        "ドラフトに記載": "あり" if g["kaite_aru"] else ATARASHII,
                    }
                    for g in kekka["system"]
                ]
            ).set_index("システム")
        )
    else:
        st.write("類似企画からつながるシステムはありませんでした。")

    st.markdown("**確かめる法令**　多くの類似企画が関わっていた順")
    if kekka["hourei"]:
        st.table(
            pd.DataFrame(
                [
                    {
                        "法令": g["name"],
                        "関わっていた類似企画": kikaku_no(g["kikaku"]),
                        "ドラフトに記載": "あり" if g["kaite_aru"] else ATARASHII,
                    }
                    for g in kekka["hourei"]
                ]
            ).set_index("法令")
        )
    else:
        st.write("類似企画からつながる法令はありませんでした。")

    # ---------------------------------------------------------- 絵（補助）
    with st.expander("つながりを絵で見る"):
        st.caption(
            "上の表と同じ中身を、丸と矢印にしたものです。"
            "🟧 濃い色 = ドラフトに書かれていなかった点（たどって見つかった）／"
            "⬜ 薄い色 = ドラフトにすでに書かれていた点。"
            "形は 四角 = 法令、円筒 = システム、だ円 = 担当者。"
        )
        st.graphviz_chart(zu.dot(kekka), use_container_width=True)
