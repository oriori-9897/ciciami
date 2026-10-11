"""data/ の資料を読んで、形をそろえる。

⭐ 図の「しまう」の 1 番目の係。ここでは**読むだけ**で、中身の解釈はしない。
   文章（過去の企画書 .docx）→ extract.py へ渡して点と線を抜く
   表（システム台帳 .xlsx） → extract.py を通さず、そのまま database.py へ渡す

📁 置き場所（Google ドライブからダウンロードして置く）
   data/kikaku/*.docx      … 企画書（Word）
   data/システム台帳.xlsx   … システム台帳（Excel）
"""

from pathlib import Path

from docx import Document  # pip install python-docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from openpyxl import load_workbook  # pip install openpyxl

DATA_DIR = Path(__file__).parent / "data"
DAICHOU_FILE = DATA_DIR / "システム台帳.xlsx"

# 🔧 台帳（Excel）の列名 → database.py が期待する列名 の対応表
#    左が Excel の見出し、右が database.py が使う名前。
#    Excel に無い列（別名・稼働の決まり）は、空のまま渡す。
DAICHOU_COLUMNS = {
    "システム名": "システム名",
    "別名": None,  # Excel に無い → 空
    "担当者": "システム担当者",
    "部署": "システム管理部署",
    "稼働の決まり": None,  # Excel に無い → 空
}

# 🔧 別名の対応表（台帳のシステム名 → 企画書での呼び方）
#    台帳 Excel に「別名」列が無いので、ここで補う。複数あるときは「、」でつなぐ。
#    extract.py がこれを LLM に見せ、「CRM」と書かれていても台帳の名前にそろえる。
#    ⚠️ 企画書が増えて、台帳と違う呼び方が出てきたら、ここに足す。
ALIASES = {
    "顧客管理システム": "CRM、顧客情報管理システム",  # 冬のキャンペーン企画書の呼び方
    "勘定系システム": "勘定系",  # 冬のキャンペーン企画書の呼び方
    "投資信託管理システム": "投資信託販売管理システム",  # ⚠️ 要確認：預り資産販売システムの可能性もある
}


def _docx_to_text(path: Path) -> str:
    """Word の本文を、上から順にテキストにする。表も同じ順番で入れる。"""
    doc = Document(path)
    lines = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):  # 段落
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            is_heading = para.style is not None and para.style.name.startswith("Heading")
            lines.append(f"# {text}" if is_heading else text)
        elif child.tag == qn("w:tbl"):  # 表：1 行を「 | 」でつなぐ
            for row in Table(child, doc).rows:
                cells = []
                for cell in row.cells:
                    t = cell.text.strip()
                    if t and t not in cells:  # 結合セルで同じ文字が繰り返されるのを防ぐ
                        cells.append(t)
                if cells:
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


TITLE_SEARCH_LINES = 5  # 題名を探す範囲＝本文の先頭から何行目まで（日付・部署名・題名が入る程度）


def _find_title(body: str, fallback: str) -> str:
    """企画書の題名を探す。先頭の数行のうち、「〜について」を含む最初の行。無ければファイル名。

    ⚠️ 本文の途中にある「〜について」を題名と取り違えないように、探す範囲を先頭だけに限っている。
    """
    for line in body.splitlines()[:TITLE_SEARCH_LINES]:
        line = line.lstrip("# ").strip()
        if "について" in line:
            return line
    return fallback


def load_kikaku() -> list[dict]:
    """過去の企画書（.docx）を全部読む。戻り値は 1 資料 1 辞書のリスト。"""
    shiryou = []
    seen = set()  # 同じ題名の企画書が 2 つあっても 1 つだけ使う
    for path in sorted((DATA_DIR / "kikaku").glob("*.docx")):
        if path.name.startswith("~$"):  # Word が開いている間にできる一時ファイルは飛ばす
            continue
        body = _docx_to_text(path)
        if not body.strip():
            continue
        title = _find_title(body, fallback=path.stem)
        if title in seen:
            continue
        seen.add(title)
        shiryou.append({"title": title, "body": body})
    return shiryou


def load_daichou() -> list[dict]:
    """システム台帳の表（Excel）を読む。戻り値は 1 行 1 辞書のリスト。

    ⭐ 返す列は システム名 / 別名 / 担当者 / 部署 / 稼働の決まり（database.py はこの名前で読む）。
       「誰がどのシステムの担当か」は表にそのまま書いてあるので、LLM に抜かせる必要が無い。
    """
    ws = load_workbook(DAICHOU_FILE, data_only=True).active  # 1 枚目のシート
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]

    def cell(row, excel_name):
        if excel_name is None or excel_name not in header:
            return ""
        value = row[header.index(excel_name)]
        return "" if value is None else str(value).strip()

    daichou = []
    for row in rows:
        record = {new: cell(row, old) for new, old in DAICHOU_COLUMNS.items()}
        if record["システム名"]:  # システム名が空の行（空白行）は飛ばす
            if not record["別名"]:  # Excel に別名が無ければ、上の ALIASES で補う
                record["別名"] = ALIASES.get(record["システム名"], "")
            daichou.append(record)
    return daichou


if __name__ == "__main__":
    # 単体で動かすと、何件読めたかだけ出る。取り込みの確認用。
    print(f"企画書 {len(load_kikaku())} 件 ／ 台帳 {len(load_daichou())} 行")
