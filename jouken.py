"""探す条件（商品・販売開始月・ターゲット）の「選択肢の一覧」を 1 か所にまとめる。

⭐ 何をするファイルか
   選択肢（投資信託の軸なら NISA／積み立て／投資信託／なし のような決まった値の一覧）を置く。
   database.py（列）・extract.py（LLM に選ばせる enum）・ranking_v2.py（一致の判定）・app.py（画面のプルダウン）
   が、全部ここを読む。中身はほぼ定数で、関数は表示用の小さいものが 2 つだけ。
   🔰 メニューの「選べる物の一覧」を 1 枚の紙に書いて、厨房も注文票もレジもその紙を見るようにしたもの。

⭐ このファイルがやらないこと
   「合っているか」の判定（商品はいくつ一致？ 月は何か月ずれ？）は書かない。それは ranking_v2.py の仕事。
   このファイルは「どんな値があるか」だけを知っていて、点の計算も比較もしない。

⭐ 無いとどうなるか
   - ファイルごと無い … 各ファイルの先頭の `import jouken` で ModuleNotFoundError。app.py は画面が出る前に止まる。
   - ファイルを作らず 4 か所に同じ一覧を書く … 動くが、改名したときに 1 か所直し忘れると
     「積立」と「積み立て」のように文字が食い違い、一致が永久に数えられなくなる。エラーは出ない。
     ここに 1 か所あれば、直すのは 1 行で 4 か所が同時に変わる。

⭐⭐ 商品は 3 つの軸の組み合わせ（4 × 2 × 3 = 24 通り）。「なし」も 1 つの値として数える。
   ドラフト〈NISA・定期預金・なし〉と企画〈NISA・定期預金・なし〉は 3 つ一致（保険を扱わない企画どうしも似ていると見なす）。
⚠️ "なし" は選択肢の 1 つ（扱わない、という値）。""（空文字）と 0 は「まだ決めていない・分からない」。
   この 2 つは別物で、判定側は "" と 0 を一致に数えないこと。

⭐ 「条件の辞書」の形（アプリの中を流れる joken）
   joken = {"toushin": "NISA", "yokin": "定期預金", "hoken": "なし", "tsuki": 4, "target": "若年層"}
   作る … app.py のプルダウン（「？」を "" に直して渡す）
   受ける … graph → ranking_v2.narabu(draft, shiryou, n, joken) → bonus()（joken[k] == shiryou[k] と文字列で比べる）
   だからドラフト側と企画書側（DB の列）が同じ文字を使っている必要があり、その保証がこのファイル。

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

 ranking_v2.py … 26 行目の `from jouken import shouhin_icchi_suu, target_onaji, tsuki_zure` は動かない
               （この 3 関数はここに無い。判定はランキング側の仕事）。`import jouken` に変えて、
               ranking_v2.py の中に次の 3 つを書く。bonus() はそのまま使える。
                 def shouhin_icchi_suu(joken, kikaku) -> int:
                     return sum(1 for k in jouken.SHOUHIN if joken.get(k) and joken[k] == kikaku.get(k))
                 def tsuki_zure(joken, kikaku) -> int | None:      # 12 月と 1 月の差は 1。どちらかが 0 なら None
                     a, b = joken.get("tsuki", 0), kikaku.get("tsuki", 0)
                     if not a or not b:
                         return None
                     sa = abs(int(a) - int(b))
                     return min(sa, 12 - sa)
                 def target_onaji(joken, kikaku) -> bool:
                     return bool(joken.get("target")) and joken["target"] == kikaku.get("target")

 app.py      … プルダウンの選択肢に TOUSHIN / YOKIN / HOKEN / TARGET / TSUKI を使う。
               月は数のまま持ち、表示だけ tsuki_moji() を通す（format_func）。選ばれていない軸は "" と 0 にする。
               条件を 1 行で見せるときは moji(joken)。
"""

TOUSHIN = ["NISA", "積み立て", "投資信託", "なし"]   # 投資信託の軸。extract の enum・app のプルダウン
YOKIN = ["定期預金", "なし"]                         # 預金の軸
HOKEN = ["一時払い", "平準払い", "なし"]              # 保険の軸（払い方）
TARGET = ["若年層", "現役層", "高齢層", "なし"]       # ターゲット
TSUKI = list(range(1, 13))                           # 販売開始月。0 は「分からない」で、一覧には入れない

SHOUHIN = ("toushin", "yokin", "hoken")              # 商品の 3 軸のキー名。判定側はこれを回して一致を数える。4 軸にするならここに足す
SHOUHIN_NAMAE = {"toushin": "投資信託", "yokin": "預金", "hoken": "払い"}  # キー名 → 画面の見出し

KARA = {"toushin": "", "yokin": "", "hoken": "", "tsuki": 0, "target": ""}  # 条件が無いときの形。DB の列名もこのキーに合わせる


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
    ⭐ 中身を数のままにしておくのが肝。判定側は abs(a - b) で月の差を出すので、
       「4月」という文字が渡ると計算できない。表示のときだけこの関数を通す。
    🔰 数字の 4 を「4月」と書き直すだけの係。
    """
    return f"{tsuki}月" if tsuki else "？"


if __name__ == "__main__":
    # 単体で動かすと、選択肢の一覧と、条件を 1 行にした見本が出る。
    print("投資信託:", TOUSHIN)
    print("預金:", YOKIN)
    print("保険:", HOKEN)
    print("ターゲット:", TARGET)
    print("販売開始月:", [tsuki_moji(t) for t in TSUKI])
    print()
    print(moji({"toushin": "NISA", "yokin": "定期預金", "hoken": "なし", "tsuki": 4, "target": "若年層"}))
    print(moji(KARA))
