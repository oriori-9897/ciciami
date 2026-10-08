"""資料を DB にしまう。loader → extract → database を順に呼ぶ、図の下の段の流れそのもの。

⭐ 画面の「資料を読み込む」ボタンと、コマンド（python shimau.py）の両方がここを呼ぶ。
⭐⭐ 順番に意味がある。台帳（表）を先に入れ、企画書（文章）をあとで抜く。
   台帳のシステム名が先に DB にあるので、LLM は企画書の「CRM」を台帳の「顧客管理システム」にそろえられる。
"""

import database
import extract
import loader


def shimau(shinchoku=None) -> None:
    """資料を読んで、表はそのまま、文章は点と線にして DB にしまう。

    shinchoku … 進み具合を受け取る関数（何件目, 全部で何件, 題名）。画面の進み具合の棒に使う。
    """
    kikaku = loader.load_kikaku()
    database.save_daichou(loader.load_daichou())  # 表は抜かずに、そのまま渡す
    database.save_kikaku(kikaku)

    for i, k in enumerate(kikaku):
        if shinchoku:
            shinchoku(i, len(kikaku), k["title"])
        # ⭐ 1 件ごとに「いま DB にある点」を取り直して渡す。前の企画書で作った法令の名前に、次の企画書をそろえるため。
        kekka = extract.nuku(k, database.all_ten())
        database.save_ten_sen(kekka["ten"], kekka["sen"])
    database.kakidasu()


if __name__ == "__main__":
    # 単体で動かすと、DB を空にしてから全部しまい直す（企画書の件数ぶん API を呼ぶ）。
    database.reset()
    shimau(lambda i, n, title: print(f"{i + 1}/{n} {title}"))
    print(database.kazu())
