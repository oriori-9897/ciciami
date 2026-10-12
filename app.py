"""🦁 獅子編み検索 ver2 — 企画のドラフトから、似た過去企画と、次に相談する相手を引き出す。

起動:  streamlit run app.py
準備:  同じフォルダに .env を作り、ANTHROPIC_API_KEY=... を書く（.env.example を写す）
       キーが要るのは「資料を読み込む」のときだけ。探すときは API を呼ばない。

⭐ 流れは 2 本。
   しまう … 資料を読む → 点と線を抜く → DB にしまう（横の「資料を読み込む」。shimau.py）
   探す   … ドラフトを受け取る → 似た企画を探して線をたどる → 表で返す（まん中。graph.py）
⭐⭐ 返すのは 2 つ。①過去の類似企画（原文）と、②企画 ― システム― 担当者のつながり。
   ②は表が主役で、絵は補助（折りたたみ）。次の行動は「各担当者と調整」なので、相手が一覧で読める形にする。
"""

import os

from io import BytesIO

import anthropic
import pandas as pd
import streamlit as st

import database
import graph
import jouken        # 追加：共通の選択肢
import ranking_v2    # 追加：条件を使ったランキング
import shimau
import zu
from loader import DATA_DIR

st.set_page_config(page_title="獅子編み検索 ver2", page_icon="🦁", layout="wide")

MARU = "①②③④⑤"          # 類似企画の番号。表の「使っていた類似企画」の列で、この番号を使う
ATARASHII = "🟠 なし"  # ドラフトに書かれていなかった（＝線をたどったから見つかった）

WEB_LIMIT = 3
EXPORT_LIMIT = 20

RESULT_COLUMNS = [
    "企画書タイトル",
    "投資信託",
    "定期預金",
    "保険",
    "開始月",
    "ターゲット層",
    "システム",
    "担当者",
    "連絡先",
]

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

def make_result_table(kekka: dict) -> pd.DataFrame:
    """企画の順位を保ったまま、指定の9列の表を作る。"""
    rows = []

    for item in kekka["nita"]:
        title = item["title"]

        # この企画につながるシステムだけを取り出す。
        systems = [
            system
            for system in kekka["system"]
            if title in system["kikaku"]
        ]

        # 各列の同じ行が、同じシステムに対応する。
        system_names = []
        person_names = []
        contacts = []

        for system in systems:
            system_names.append(system["name"])
            person_names.append(
                system.get("tantou") or "未登録"
            )
            contacts.append(
                str(system.get("renraku") or "未登録")
            )

        yokin = item.get("yokin")
        if yokin == "定期預金":
            yokin_display = "あり"
        else:
            yokin_display = yokin or "不明"

        rows.append({
            "企画書タイトル": title,
            "投資信託": item.get("toushin") or "不明",
            "定期預金": yokin_display,
            "保険": item.get("hoken") or "不明",
            "開始月": (
                jouken.tsuki_moji(item["tsuki"])
                if item.get("tsuki") else "不明"
            ),
            "ターゲット層": item.get("target") or "不明",
            "システム": (
                "\n".join(system_names) if systems else "該当なし"
            ),
            "担当者": (
                "\n".join(person_names) if systems else "該当なし"
            ),
            "連絡先": (
                "\n".join(contacts) if systems else "該当なし"
            ),
        })

    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def make_result_excel(
    result_df: pd.DataFrame,
    search_info: dict,
) -> bytes:
    """指定の9列をExcelファイルに出力する。"""
    from openpyxl.styles import Alignment, Font, PatternFill

    condition_df = pd.DataFrame([
        {
            "項目": "検索方法",
            "値": search_info["mode"],
        },
        {
            "項目": "検索キーワード",
            "値": search_info.get("keyword", ""),
        },
        {
            "項目": "検索条件",
            "値": jouken.moji(search_info["joken"]),
        },
        {
            "項目": "出力件数",
            "値": len(result_df),
        },
        {
            "項目": "並び順",
            "値": "検索スコアの高い順",
        },
        {
            "項目": "連絡先",
            "値": "システム台帳の代表連絡先",
        },
    ])

    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        result_df.to_excel(
            writer,
            sheet_name="検索結果",
            index=False,
        )
        condition_df.to_excel(
            writer,
            sheet_name="検索条件",
            index=False,
        )

        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "A2"

            for cell in sheet[1]:
                cell.font = Font(
                    color="FFFFFF",
                    bold=True,
                )
                cell.fill = PatternFill(
                    fill_type="solid",
                    fgColor="203864",
                )

            for row in sheet.iter_rows(min_row=2):
                for cell in row:
                    # 連絡先などを文字列として保存する。
                    # 「=」で始まる文字も数式にしない。
                    if isinstance(cell.value, str):
                        cell.data_type = "s"

                    cell.alignment = Alignment(
                        vertical="top",
                        wrap_text=True,
                    )

        sheet = writer.book["検索結果"]
        sheet.auto_filter.ref = sheet.dimensions

        widths = {
            "A": 45,  # 企画書タイトル
            "B": 16,  # 投資信託
            "C": 14,  # 定期預金
            "D": 16,  # 保険
            "E": 12,  # 開始月
            "F": 18,  # ターゲット層
            "G": 35,  # システム
            "H": 25,  # 担当者
            "I": 28,  # 連絡先
        }

        for column, width in widths.items():
            sheet.column_dimensions[column].width = width

        for row in sheet.iter_rows(min_row=2):
            line_count = max(
                str(cell.value or "").count("\n") + 1
                for cell in row
            )
            sheet.row_dimensions[row[0].row].height = min(
                409,
                max(45, line_count * 20),
            )

        condition_sheet = writer.book["検索条件"]
        condition_sheet.column_dimensions["A"].width = 20
        condition_sheet.column_dimensions["B"].width = 90

        for row_number in range(
            2, condition_sheet.max_row + 1
        ):
            condition_sheet.row_dimensions[row_number].height = 45

    return buffer.getvalue()

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

        for key in (
            "kekka",
            "search_info",
            "result_table",
            "result_excel",
        ):
            st.session_state.pop(key, None)

        st.rerun()

    st.divider()
    st.caption(
        f"画面：上位{WEB_LIMIT}企画 ／ "
        f"Excel：上位{EXPORT_LIMIT}企画"
    )
    with st.expander("システム台帳（表）を見る"):
        st.dataframe(
            pd.DataFrame(database.all_daichou()).rename(
                columns={"system": "システム名", "betsumei": "別名", "tantou": "担当者", "busho": "部署", "kimari": "稼働の決まり"}
            ),
            hide_index=True,
        )


# ---------------------------------------------------------------- 探す
st.title("🦁 獅子編み検索 ver2")
st.caption(
    "ドラフト・キーワード・検索条件から過去企画を探し、"
    "関連するシステム・担当者を表示します。"
)

# ---------------------------------------------------------- ドラフト
st.subheader("企画ドラフト（任意）")

if st.button("サンプルのドラフトを入れる"):
    st.session_state["draft"] = (
        DATA_DIR / "draft_sample.md"
    ).read_text(encoding="utf-8")

file = st.file_uploader(
    "ドラフトのファイル（.md / .txt、任意）",
    type=["md", "txt"],
)

if file and st.session_state.get("file_name") != file.name:
    st.session_state["file_name"] = file.name
    st.session_state["draft"] = file.getvalue().decode("utf-8-sig")

draft = st.text_area(
    "企画ドラフトを貼り付ける（任意）",
    key="draft",
    height=220,
)

# ---------------------------------------------------------- キーワード
st.subheader("キーワード（任意）")

keyword = st.text_input(
    "検索キーワード",
    placeholder="例：NISA 若年層 キャンペーン",
    key="search_keyword",
)

st.caption("複数のキーワードは、空白・読点・カンマで区切れます。")

# ---------------------------------------------------------- プルダウン
st.subheader("検索条件（任意）")
st.markdown("**商品種別**")

col1, col2, col3 = st.columns(3)

with col1:
    toushin = st.selectbox(
        "投資信託",
        options=[""] + jouken.TOUSHIN,
        format_func=lambda value: value or "指定なし",
        key="condition_toushin",
    )

with col2:
    yokin = st.selectbox(
        "定期預金",
        options=[""] + jouken.YOKIN,
        format_func=lambda value: (
            "指定なし" if value == ""
            else "あり" if value == "定期預金"
            else value
        ),
        key="condition_yokin",
    )

with col3:
    hoken = st.selectbox(
        "保険",
        options=[""] + jouken.HOKEN,
        format_func=lambda value: value or "指定なし",
        key="condition_hoken",
    )

col4, col5 = st.columns(2)

with col4:
    tsuki = st.selectbox(
        "販売開始月",
        options=[0] + jouken.TSUKI,
        format_func=lambda value: (
            jouken.tsuki_moji(value) if value else "指定なし"
        ),
        key="condition_tsuki",
    )

with col5: #ターゲット層のタグ付けをjoukenから引用
    target = st.selectbox(
        "ターゲット層",
        options=[""] + [
            value for value in jouken.TARGET if value != "なし"
        ],
        format_func=lambda value: value or "指定なし",
        key="condition_target",
    )

joken = {
    "toushin": toushin,
    "yokin": yokin,
    "hoken": hoken,
    "tsuki": tsuki,
    "target": target,
}

st.caption(
    "「指定なし」は条件を使わない設定です。"
    "商品の「なし」は、その商品を扱わないという条件です。"
)

# ---------------------------------------------------------- 検索方法
has_draft = bool(draft.strip())
has_keyword = bool(ranking_v2.keyword_wakeru(keyword))
has_conditions = any(joken.values())

# ドラフトとキーワードの両方がある場合は、
# どちらを文章比較に使うか明示的に選ぶ。
search_mode = None

if has_draft and has_keyword:
    search_mode = st.radio(
        "検索に使う入力",
        options=["キーワード", "企画ドラフト"],
        horizontal=True,
        key="search_mode",
    )
    st.caption("プルダウンの条件は、どちらの検索にも反映します。")
elif has_keyword:
    search_mode = "キーワード"
elif has_draft:
    search_mode = "企画ドラフト"
elif has_conditions:
    search_mode = "条件のみ"

can_search = has_draft or has_keyword or has_conditions

# ---------------------------------------------------------- 検索実行
# ---------------------------------------------------------- 検索実行
if st.button("探す", type="primary", disabled=not can_search):
    # 前回の結果を消し、今回の検索結果だけを保存する。
    for key in (
        "kekka",
        "search_info",
        "result_table",
        "result_excel",
    ):
        st.session_state.pop(key, None)

    shiryou = database.all_kikaku()

    if not shiryou:
        st.warning(
            "検索対象の過去企画がDBにありません。"
            "過去企画の登録が必要です。"
        )
    else:
        with st.spinner("検索しています…"):
            # Excel用に、まず上位20企画を検索する。
            if search_mode == "キーワード":
                export_results = ranking_v2.narabu_keyword(
                    keyword,
                    shiryou,
                    EXPORT_LIMIT,
                    joken,
                )
                search_text = keyword

            elif search_mode == "企画ドラフト":
                export_results = ranking_v2.narabu(
                    draft,
                    shiryou,
                    EXPORT_LIMIT,
                    joken,
                )
                search_text = draft

            else:
                export_results = ranking_v2.narabu(
                    "",
                    shiryou,
                    EXPORT_LIMIT,
                    joken,
                )
                search_text = ""

            search_info = {
                "mode": search_mode,
                "keyword": (
                    keyword
                    if search_mode == "キーワード"
                    else ""
                ),
                "joken": joken.copy(),
            }

            # 上位20企画についてシステム・担当者・連絡先を取得。
            export_kekka = graph.tadotte_matomeru(
                export_results,
                search_text,
            )

            result_table = make_result_table(export_kekka)

            # 図と原文表示には上位3企画を使う。
            web_results = export_results[:WEB_LIMIT]
            web_kekka = graph.tadotte_matomeru(
                web_results,
                search_text,
            )

            st.session_state["kekka"] = web_kekka
            st.session_state["search_info"] = search_info
            st.session_state["result_table"] = result_table

            if not result_table.empty:
                st.session_state["result_excel"] = (
                    make_result_excel(
                        result_table,
                        search_info,
                    )
                )


# ---------------------------------------------------------- 結果表示
if "kekka" in st.session_state:
    kekka = st.session_state["kekka"]
    search_info = st.session_state["search_info"]
    result_table = st.session_state["result_table"]

    st.caption(
        f"検索方法：{search_info['mode']} ／ "
        f"検索時の条件：{jouken.moji(search_info['joken'])}"
    )

    if search_info.get("keyword"):
        st.caption(
            f"検索時のキーワード：{search_info['keyword']}"
        )

    if result_table.empty:
        st.info(
            "過去企画が見つかりませんでした。"
            "キーワード・ドラフト・検索条件を変更してください。"
        )
        st.stop()

    st.subheader("検索結果")

    web_table = result_table.head(WEB_LIMIT)

    st.caption(
        f"関連性の高い順に上位{len(web_table)}企画を表示しています。"
        "連絡先はシステム台帳の代表連絡先です。"
    )

    # 改行と複数システムの対応を読みやすく表示する。
    st.table(web_table)

    st.download_button(
        label=(
            "検索結果をExcelでダウンロード"
            f"（{len(result_table)}企画）"
        ),
        data=st.session_state["result_excel"],
        file_name="検索結果_上位20企画.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        key="download_result_excel",
    )

    st.caption(
        "Excelも同じ関連性の順で、最大20企画を出力します。"
        "システム・担当者・連絡先の各セルは、"
        "同じ行が同じシステムに対応します。"
    )

    # 原文は必要な場合に開けるようにする。
    st.subheader("企画書の原文")

    for rank, item in enumerate(kekka["nita"], start=1):
        with st.expander(
            f"{rank}. {item['title']}"
        ):
            st.markdown(item["body"])

    # 上位3企画に関するつながりを表示する。
    with st.expander("つながりを図で見る"):
        st.caption(
            "画面に表示した上位3企画の"
            "システム・担当者とのつながりです。"
        )
        st.graphviz_chart(
            zu.dot(kekka),
            use_container_width=True,
        )
