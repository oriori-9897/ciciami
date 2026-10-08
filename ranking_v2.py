"""TF-IDF で、ドラフトと文章が似ている順に資料を並べる。

⭐ 図の「並べさせる」の係。graph.py がここを呼ぶ。このアプリに要る分だけを書いた版。
   やることは 3 つ。資料を数字の並び（ベクトル）にする → ドラフトも同じ物差しで数字にする → 向きの近さを測る。
⭐⭐ 日本語は単語の間に空白が無いので、単語ではなく「2〜3 文字のまとまり」で数える（analyzer="char_wb"）。
   単語区切りのままだと、1 文がまるごと 1 語になり、どの資料とも一致しなくなる。
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ASHIKIRI = 0.01  # 似ている度合いがこれ以下の資料は出さない（ほぼ無関係なので）


def narabu(draft: str, shiryou: list[dict], n: int = 3) -> list[dict]:
    """ドラフトに似ている資料を、似ている順に n 件返す。

    shiryou … {"title", "body"} のリスト
    戻り値  … {"title", "body", "score"} のリスト。score は 0〜1 で、大きいほど似ている。
    """
    if not shiryou or not draft.strip():
        return []

    vectorizer = TfidfVectorizer(
        analyzer="char_wb",   # 文字のまとまりで数える（空白をまたがない）
        ngram_range=(2, 3),   # 2〜3 文字のまとまり
        max_features=5000,    # よく出る 5000 種類までに絞る
        max_df=0.95,          # ほぼ全部の資料に出るまとまりは、区別に役立たないので捨てる
        sublinear_tf=True,    # 同じまとまりが何度も出ても、点が伸びすぎないようにする
    )
    # ⭐ 題名は 3 回くり返して、本文より重く数える。題名はその資料の中身をいちばん短く表しているため。
    gyouretsu = vectorizer.fit_transform([" ".join([s["title"]] * 3 + [s["body"]]) for s in shiryou])
    # ⚠️ ドラフトは fit せず transform だけ。資料で作った物差し（どのまとまりが何列目か）をそのまま使う。
    nite_iru = cosine_similarity(vectorizer.transform([draft]), gyouretsu)[0]

    kekka = [
        {"title": s["title"], "body": s["body"], "score": round(float(score), 3)}
        for s, score in zip(shiryou, nite_iru)
        if score > ASHIKIRI
    ]
    kekka.sort(key=lambda k: k["score"], reverse=True)
    return kekka[:n]


if __name__ == "__main__":
    # 単体で動かすと、サンプルのドラフトに似ている企画書が上から出る（API は呼ばない）。
    from loader import DATA_DIR, load_kikaku

    for k in narabu((DATA_DIR / "draft_sample.md").read_text(encoding="utf-8"), load_kikaku(), n=5):
        print(f"{k['score']:.3f}  {k['title']}")
