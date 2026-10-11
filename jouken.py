"""探す条件（商品・販売開始月・ターゲット）の「選択肢の一覧」と「合っているかの判定」を 1 か所にまとめる。

⭐ 何をするファイルか
   1. 選択肢（投資信託の軸なら NISA／積み立て／投資信託／なし のような決まった値の一覧）を置く。
      database.py（列）・extract.py（LLM に選ばせる enum）・app.py（画面のプルダウン）が、ここを読む。
   2. ドラフトの条件と企画書が「合っているか」を事実で答える関数を 3 つ置く。ranking_v2.py がここを呼ぶ。
        shouhin_icchi_suu(joken, kikaku) … 商品 3 軸のうち、いくつ一致したか（0〜3）
        tsuki_zure(joken, kikaku)        … 販売開始月が何か月ずれているか（0〜6）。どちらかに月が無ければ None
        target_onaji(joken, kikaku)      … ターゲットが同じか（True / False）
   🔰 メニューの「選べる物の一覧」を 1 枚の紙に書いて、厨房も注文票もレジもその紙を見るようにしたもの。
      「注文と料理が合っているか」を確かめるのもこの紙の係で、合っていたら何点かを決めるのはレジ（ranking_v2.py）。

⭐⭐ ranking_v2.py との役割分担
   このファイル   … 判定（事実を答える）  商品はいくつ一致？ ／ 月は何か月ずれ？ ／ ターゲットは同じ？
   ranking_v2.py  … 点数付け              その事実を何点にするか（TEN_〜）
   だから ranking_v2.py は「商品の列名」や「選択肢の名前」を知らない。それはこのファイルだけが知っている。
   列名を変えても、選択肢を足しても、ranking_v2.py は直さなくてよい。

⭐ 無いとどうなるか
   - ファイルごと無い … 各ファイルの先頭の `import jouken` で ModuleNotFoundError。app.py は画面が出る前に止まる。
   - ファイルを作らず 4 か所に同じ一覧を書く … 動くが、改名したときに 1 か所直し忘れると
     「積立」と「積み立て」のように文字が食い違い、一致が永久に数えられなくなる。エラーは出ない。
     ここに 1 か所あれば、直すのは 1 行で 4 か所が同時に変わる。

⭐⭐ 商品は 3 つの軸の組み合わせ（4 × 2 × 3 = 24 通り）。「なし」も 1 つの値として数える。
   ドラフト〈NISA・定期預金・なし〉と企画〈NISA・定期預金・なし〉は 3 つ一致（保険を扱わない企画どうしも似ていると見なす）。
⚠️ "なし" は選択肢の 1 つ（扱わない、という値）。""（空文字）と 0 は「まだ決めていない・分からない」。
   この 2 つは別物で、下の判定関数は "" と 0 を一致に数えない。

⭐ 「条件の辞書」の形（アプリの中を流れる joken）
   joken = {"toushin": "NISA", "yokin": "定期預金", "hoken": "なし", "tsuki": 4, "target": "若年層"}
   作る … app.py のプルダウン（「？」を "" に直して渡す）
   受ける … graph → ranking_v2.narabu(draft, shiryou, n, joken) → bonus() → ここの判定 3 関数
   企画書（kikaku）側は database.all_kikaku() の 1 件で、同じキー名の列を持つ。
   ドラフト側と企画書側が同じ文字を使っている必要があり、その保証がこのファイル。

════════════════════════════════════════════════════════════════════
 他のファイルを直す人への手引き（このファイルは足すだけ。残りは各担当で）
════════════════════════════════════════════════════════════════════
 database.py … kikaku テーブルに 5 列を足す。列名は KARA のキーと同じにする。
                 toushin TEXT, yokin TEXT, hoken TEXT, tsuki INTEGER, target TEXT
               ⚠️ 列を足したら shishiami.db を消して読み込み直す（既存の行には列が無い）。

 extract.py  … LLM に企画書から選ばせる JSON スキーマで、enum にここの一覧を使う。
                 "toushin": {"type": "string", "enum": jouken.TOUSHIN}
                 "yokin":   {"type": "string", "enum": jouken.YOKIN}
                 "hoken":   {"type": "string", "enum": jouken.HOKEN}
                 "tsuki":   {"type": "integer", "minimum": 0, "maximum": 12}   # 0 = 分からない
                 "target":  {"type": "string", "enum": jouken.TARGET}

 ranking_v2.py … 直さなくてよい。`from jouken import shouhin_icchi_suu, target_onaji, tsuki_zure` がそのまま動く。

 app.py      … プルダウンの選択肢に TOUSHIN / YOKIN / HOKEN / TARGET / TSUKI を使う。
               月は数のまま持ち、表示だけ tsuki_moji() を通す（format_func）。選ばれていない軸は "" と 0 にする。
               条件を 1 行で見せるときは moji(joken)。
"""

# ════════════════════════════════════════════════════════════════════
#  選択肢の一覧
# ════════════════════════════════════════════════════════════════════

TOUSHIN = ["NISA", "積み立て", "投資信託", "なし"]   # 投資信託の軸。extract の enum・app のプルダウン
YOKIN = ["定期預金", "なし"]                         # 預金の軸
HOKEN = ["一時払い", "平準払い", "なし"]              # 保険の軸（払い方）
TARGET = ["若年層", "現役層", "高齢層", "なし"]       # ターゲット
TSUKI = list(range(1, 13))                           # 販売開始月。0 は「分からない」で、一覧には入れない

SHOUHIN = ("toushin", "yokin", "hoken")              # 商品の 3 軸のキー名。shouhin_icchi_suu はこれを回して一致を数える。4 軸にするならここに足す
SHOUHIN_NAMAE = {"toushin": "投資信託", "yokin": "預金", "hoken": "払い"}  # キー名 → 画面の見出し

KARA = {"toushin": "", "yokin": "", "hoken": "", "tsuki": 0, "target": ""}  # 条件が無いときの形。DB の列名もこのキーに合わせる


# ════════════════════════════════════════════════════════════════════
#  判定（事実を答える。何点かは ranking_v2.py が決める）
# ════════════════════════════════════════════════════════════════════

def shouhin_icchi_suu(joken: dict, kikaku: dict) -> int:
    """商品 3 軸（投資信託・預金・払い）のうち、いくつ一致したかを返す（0〜3）。

    引数   joken  … 条件の辞書。kikaku … 企画書 1 件（同じキー名の列を持つ）
    戻り値 一致した軸の数。ranking_v2.bonus() は 3 なら満点、2 なら半分、1 以下は 0 点にする
    ⚠️ 条件側が ""（選んでいない）の軸は、企画書側が何でも一致に数えない。"なし" どうしは一致に数える。
    🔰 注文票と料理を 3 項目ずつ見比べて、合っていた数を指で数える。
    """
    return sum(1 for k in SHOUHIN if joken.get(k) and joken[k] == kikaku.get(k))


def tsuki_zure(joken: dict, kikaku: dict) -> int | None:
    """販売開始月が何か月ずれているかを返す（0〜6）。どちらかに月が無い（0）なら None。

    引数   joken・kikaku … shouhin_icchi_suu と同じ。"tsuki" は 0〜12 の整数
    戻り値 0 … 同じ月、1 … 1 か月ずれ、… 、None … 比べられない（ranking_v2 は None に点を足さない）
    ⭐ 12 月と 1 月の差は 1（年をまたぐ）。abs だけだと 11 になるので、12 から引いた方と小さい方を取る。
    ⚠️ 「4月」という文字が渡ると int() で落ちる。月は数のまま持つこと（表示だけ tsuki_moji）。
    🔰 カレンダーを丸く並べて、2 つの月の近い方の間隔を数える。
    """
    a, b = joken.get("tsuki", 0), kikaku.get("tsuki", 0)
    if not a or not b:
        return None
    sa = abs(int(a) - int(b))
    return min(sa, 12 - sa)


def target_onaji(joken: dict, kikaku: dict) -> bool:
    """ターゲットが同じなら True。条件側が ""（選んでいない）なら False。

    引数   joken・kikaku … shouhin_icchi_suu と同じ
    🔰 「若年層向け」と書いた注文票と、料理の札を見比べる。
    """
    return bool(joken.get("target")) and joken["target"] == kikaku.get("target")


# ════════════════════════════════════════════════════════════════════
#  表示用
# ════════════════════════════════════════════════════════════════════

def moji(jouken: dict) -> str:
    """条件の辞書を、人が読める 1 行にする。

    引数   jouken … 条件の辞書（上の joken の形）。5 つそろっていなくてもよい（.get で読む）
    戻り値 例: 投資信託=NISA ／ 預金=定期預金 ／ 払い=なし ／ 販売開始月=4月 ／ ターゲット=若年層
           値が "" や 0 の軸は「？」になる
    使う所 app.py（表の上の「条件: …」）、各ファイルの __main__
    🔰 注文票を、読み上げ用の 1 行の日本語にする。
    """
    bubun = [f"{SHOUHIN_NAMAE[k]}={jouken.get(k) or '？'}" for k in SHOUHIN]
    bubun.append(f"販売開始月={tsuki_moji(jouken.get('tsuki', 0))}")
    bubun.append(f"ターゲット={jouken.get('target') or '？'}")
    return " ／ ".join(bubun)


def tsuki_moji(tsuki: int) -> str:
    """月の数を「4月」の文字にする。0 は「？」。

    引数   tsuki … 0〜12 の整数
    戻り値 "4月" / "？"
    使う所 app.py のプルダウン（format_func。中身は数のまま、表示だけ文字にする）、表、moji() の中
    ⭐ 中身を数のままにしておくのが肝。tsuki_zure() は abs(a - b) で月の差を出すので、
       「4月」という文字が渡ると計算できない。表示のときだけこの関数を通す。
    🔰 数字の 4 を「4月」と書き直すだけの係。
    """
    return f"{tsuki}月" if tsuki else "？"


if __name__ == "__main__":
    # 単体で動かすと、選択肢の一覧と、判定 3 関数の見本が出る。
    print("投資信託:", TOUSHIN)
    print("預金:", YOKIN)
    print("保険:", HOKEN)
    print("ターゲット:", TARGET)
    print("販売開始月:", [tsuki_moji(t) for t in TSUKI])
    print()
    joken = {"toushin": "NISA", "yokin": "定期預金", "hoken": "なし", "tsuki": 12, "target": "若年層"}
    kikaku = {"toushin": "NISA", "yokin": "定期預金", "hoken": "一時払い", "tsuki": 1, "target": "若年層"}
    print("条件  :", moji(joken))
    print("企画書:", moji(kikaku))
    print("商品の一致数:", shouhin_icchi_suu(joken, kikaku), "／ 月のずれ:", tsuki_zure(joken, kikaku), "／ ターゲット同じ:", target_onaji(joken, kikaku))
    print("空の条件と比べると:", shouhin_icchi_suu(KARA, kikaku), tsuki_zure(KARA, kikaku), target_onaji(KARA, kikaku))
