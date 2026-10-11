
"""TF-IDF（文章 または キーワードの近さ）＋ 条件ボーナス（商品・販売開始月・ターゲット）で、似ている順に企画書を並べる。
 
⭐ 図の「並べさせる」の係。外から呼ぶ関数は 2 つ。引数も戻り値も同じ形なので、呼ぶ関数を変えるだけで探し方が切り替わる。
     narabu(draft, shiryou, n, joken)            … 文書 ＋ ボーナス      企画ドラフトの文章に近い順
     narabu_keyword(keyword, shiryou, n, joken)  … キーワード ＋ ボーナス  検索ワードをよく含む順
 
⭐⭐ 中の部品
     monosashi()       … 資料から TF-IDF の物差しを作る（下の 2 つが共通で使う）
     bun_no_ten()      … 文章の点。ドラフト全体と資料の近さ。計算は v2 と同じ
     keyword_no_ten()  … キーワードの点。キーワード 1 語ずつ資料との近さを出して、平均する
     bonus()           … ボーナス点。「合っているか」は jouken.py に聞き、「何点か」はここで決める
     tashite_narabu()  … 点 ＋ ボーナスを足して、足切りして、並べて返す（narabu と narabu_keyword が共通で使う）
 
⭐⭐ jouken.py との役割分担
     jouken.py     … 判定（事実を答える）  商品はいくつ一致？ ／ 月は何か月ずれ？ ／ ターゲットは同じ？
     このファイル  … 点数付け              その事実を何点にするか（下の TEN_〜）
   だから、このファイルは「商品の列名」や「選択肢の名前」を知らない。それは jouken.py だけが知っている。
"""

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from jouken import shouhin_icchi_suu, target_onaji, tsuki_zure #jouken.py次第で引数は変わる

ASHIKIRI = 0.01  # 似ている度合いがこれ以下の資料は出さない（ほぼ無関係なので）

# ── ボーナス点（ここだけ直せば配点を変えられる） ──────────────
TEN_SHOUHIN_3 = 1.0    # 商品 3 つの組み合わせが完全一致
TEN_SHOUHIN_2 = 0.5    # 商品 3 つのうち 2 つが一致
TEN_TSUKI_ICCHI = 0.8  # 販売開始月が同じ
TEN_TSUKI_ZURE1 = 0.7  # 販売開始月が 1 か月ずれ
TEN_TARGET = 0.5       # ターゲットが同じ
 

# ════════════════════════════════════════════════════════════════════
#  TF-IDF の点（文章の点 と キーワードの点）
# ════════════════════════════════════════════════════════════════════
 
def monosashi(shiryou: list[dict]):
    """資料から TF-IDF の物差しを作り、（物差し, 資料を数字にした表）を返す。
 
    ⭐ 文章の点とキーワードの点は、同じ物差しで測る。だから設定はここ 1 か所だけに書く。
    ⭐⭐ 日本語は単語の間に空白が無いので、単語ではなく「2〜3 文字のまとまり」で数える（analyzer="char_wb"）。
    """
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",   # 文字のまとまりで数える（空白をまたがない）
        ngram_range=(2, 3),   # 2〜3 文字のまとまり
        max_features=5000,    # よく出る 5000 種類までに絞る
        max_df=0.95,          # ほぼ全部の資料に出るまとまりは、区別に役立たないので捨てる
        sublinear_tf=True,    # 同じまとまりが何度も出ても、点が伸びすぎないようにする
    )
    # ⭐ 題名は 3 回くり返して、本文より重く数える。題名はその資料の中身をいちばん短く表しているため。
    gyouretsu = vectorizer.fit_transform([" ".join([s["title"]] * 3 + [s["body"]]) for s in shiryou])
    return vectorizer, gyouretsu
 
 
def bun_no_ten(draft: str, shiryou: list[dict]) -> list[float]:
    """文章の点。ドラフト全体と各資料の文章の近さを、資料と同じ順番で返す（0〜1。大きいほど似ている）。"""
    if not draft.strip():
        return [0.0] * len(shiryou)  # ドラフトが空なら比べる文章が無いので、全部 0 点
 
    vectorizer, gyouretsu = monosashi(shiryou)
    # ⚠️ ドラフトは fit せず transform だけ。資料で作った物差し（どのまとまりが何列目か）をそのまま使う。
    nite_iru = cosine_similarity(vectorizer.transform([draft]), gyouretsu)[0]
    return [float(x) for x in nite_iru]
 
 
def keyword_wakeru(keyword: str) -> list[str]:
    """検索ワードを 1 語ずつに分ける。区切りは空白（全角も可）と「、」「,」。同じ語は 1 つにまとめる。
 
    例: "投資信託　若年層、キャンペーン" → ["投資信託", "若年層", "キャンペーン"]
    """
    go = [k for k in re.split(r"[\s、,，]+", keyword) if k]
    return list(dict.fromkeys(go))  # 順番はそのままで、重複だけ取る
 
 
def keyword_no_ten(keyword: str, shiryou: list[dict]) -> list[float]:
    """キーワードの点。各資料がキーワードをどれだけ含むかを、資料と同じ順番で返す（0〜1。大きいほどよく含む）。
 
    ⭐ キーワードを 1 語ずつ資料と比べて点を出し、その平均を取る。
       まとめて 1 つの文として比べると長い語ばかりが効くので、1 語ずつにして、どの語も同じ重さで数える。
    ⚠️ 物差しが「2〜3 文字のまとまり」なので、1 文字だけのキーワード（例:「株」）には点が付かない。
    ⚠️ 短いキーワードと長い資料を比べるので、点は文章の点より小さく出やすい（ボーナスの方が強く効く）。
    """
    go = keyword_wakeru(keyword)
    if not go:
        return [0.0] * len(shiryou)  # キーワードが空なら、全部 0 点
 
    vectorizer, gyouretsu = monosashi(shiryou)
    hyou = cosine_similarity(vectorizer.transform(go), gyouretsu)  # 行＝キーワード 1 語、列＝資料 1 件
    return [float(x) for x in hyou.mean(axis=0)]                   # 資料ごとに、キーワードの点を平均する
 
 
# ════════════════════════════════════════════════════════════════════
#  ボーナス点（判定は jouken.py、点数付けはここ）
# ════════════════════════════════════════════════════════════════════
 
def bonus(joken: dict | None, kikaku: dict) -> tuple[float, list[str]]:
    """ボーナス点。条件(joken)と企画書(kikaku)が合っている分の点と、その理由を返す。
 
    ⭐ 「合っているか」は jouken.py の関数に聞く。ここでは、その答えを点に変えるだけ。
    """
    ten = 0.0
    riyuu = []
    if not joken:
        return ten, riyuu  # 条件が渡されていなければ、ボーナスは無し
 
    # 商品：3 軸のうち、いくつ一致したか
    kazu = shouhin_icchi_suu(joken, kikaku)
    if kazu == 3:
        ten += TEN_SHOUHIN_3
        riyuu.append(f"商品が3つとも一致 +{TEN_SHOUHIN_3}")
    elif kazu == 2:
        ten += TEN_SHOUHIN_2
        riyuu.append(f"商品が2つ一致 +{TEN_SHOUHIN_2}")
 
    # 販売開始月：何か月ずれているか（None は「どちらかに月が無い」。そのときは点を足さない）
    zure = tsuki_zure(joken, kikaku)
    if zure == 0:
        ten += TEN_TSUKI_ICCHI
        riyuu.append(f"販売開始月が一致 +{TEN_TSUKI_ICCHI}")
    elif zure == 1:
        ten += TEN_TSUKI_ZURE1
        riyuu.append(f"販売開始月が1か月ずれ +{TEN_TSUKI_ZURE1}")
 
    # ターゲット
    if target_onaji(joken, kikaku):
        ten += TEN_TARGET
        riyuu.append(f"ターゲットが一致 +{TEN_TARGET}")
 
    return ten, riyuu
 
 
# ════════════════════════════════════════════════════════════════════
#  足して、並べて、返す
# ════════════════════════════════════════════════════════════════════
 
def tashite_narabu(ten: list[float], shiryou: list[dict], n: int | None, joken: dict | None) -> list[dict]:
    """TF-IDF の点(ten)にボーナスを足し、足切りして、点の高い順に n 件返す。narabu と narabu_keyword の共通部分。"""
    kekka = []
    for s, bun in zip(shiryou, ten):
        kasan, riyuu = bonus(joken, s)
        goukei = bun + kasan
        # ⭐ 足切りは「合計点」で見る。文章やキーワードが合っていなくても、商品や月が合っていれば残す。
        if goukei > ASHIKIRI:
            kekka.append({
                **s,  # 資料の中身はそのまま持ち回る（商品・月・ターゲットも画面に出せるように）
                "score": round(goukei, 3),
                "bun_score": round(bun, 3),
                "bonus": round(kasan, 3),
                "riyuu": riyuu,
            })
    kekka.sort(key=lambda k: k["score"], reverse=True)
    return kekka if n is None else kekka[:n]
 
 
def narabu(draft: str, shiryou: list[dict], n: int | None = 20, joken: dict | None = None) -> list[dict]:
    """【文書 ＋ ボーナス】ドラフトの文章に似ている資料を、似ている順に n 件返す。
 
    draft   … 企画ドラフトの文章。空でもよい（そのときはボーナスだけで並べる）。
    shiryou … 企画書のリスト。1 件は {"title", "body", ＋商品・月・ターゲットの列} の dict。
    joken   … 画面のプルダウンで選んだ条件（dict）。渡さなければボーナスは 0 点で、v2 と同じ並びになる。
    n       … 返す件数。None なら全部返す（スプレッドシートに出すとき用）。
    戻り値  … 資料の中身に、次の 4 つを足したリスト。
              score     … 合計点（bun_score + bonus）。大きいほど似ている。⚠️ 0〜1 ではない（今の配点で最大 3.3）
              bun_score … TF-IDF の点（0〜1）。ここでは文章の点。v2 の score と同じもの
              bonus     … ボーナス点
              riyuu     … 点を足した理由（画面に「なぜ上に来たか」を出せる）
    """
    if not shiryou:
        return []
    return tashite_narabu(bun_no_ten(draft, shiryou), shiryou, n, joken)
 
 
def narabu_keyword(keyword: str, shiryou: list[dict], n: int | None = 20, joken: dict | None = None) -> list[dict]:
    """【キーワード ＋ ボーナス】検索ワードをよく含む資料を、点の高い順に n 件返す。
 
    keyword … 検索ワード。空白か「、」で区切って何語でも入れられる。空でもよい（そのときはボーナスだけで並べる）。
    shiryou・joken・n・戻り値 … narabu と同じ。bun_score には、文章の点の代わりにキーワードの点が入る。
    """
    if not shiryou:
        return []
    return tashite_narabu(keyword_no_ten(keyword, shiryou), shiryou, n, joken)
 




if __name__ == "__main__":
    # 単体で動かすと、サンプルのドラフトに似ている企画書が上から出る（API は呼ばない）。
    from loader import DATA_DIR, load_kikaku

    for k in narabu((DATA_DIR / "draft_sample.md").read_text(encoding="utf-8"), load_kikaku(), n=5):
        print(f"{k['score']:.3f}  {k['title']}")
