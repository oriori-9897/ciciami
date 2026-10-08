"""Claude の API を呼ぶ共通の入口。

⭐ 図の右上の「LLM」の係。extract.py（点と線を抜く）がここを通って API を呼ぶ。
   モデル名やキーの読み方を 1 か所にまとめるためのファイル。
⚠️ キーはこのファイルに書かない。同じフォルダの .env に
       ANTHROPIC_API_KEY=sk-ant-...
   と書く（.env は .gitignore で履歴から外してある）。
"""

import os
import ssl
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")  # .env の中身を環境変数に入れる

MODEL = "claude-opus-5-5"

# モデルが安全上の理由で答えを断ったとき、API の側で別のモデルに回してもらう設定。
# 企画書の文章で断られることはまず無いが、断られたら黙って空が返るのを防ぐ。
BETAS = ["server-side-fallback-2026-07-01"]
FALLBACKS = "default"


def _client() -> anthropic.Anthropic:
    # 引数なしで作ると、環境変数 ANTHROPIC_API_KEY を自分で読みにいく。
    # ⚠️ キーが無いと、呼んだ先で分かりにくい TypeError になる。ここで先に止めて言葉にする。
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("API キーが見つかりません。app_v2 フォルダに .env を作り、ANTHROPIC_API_KEY=... を書いてください。")
    # ⚠️ verify に証明書の設定を自分で渡す。このパソコンには pip-system-certs が入っていて、
    #    SDK の既定の設定とぶつかり、つなぐ途中で無限にくり返して「つながりません」になる。
    #    自分で渡せば SDK は既定の設定を作らないので、ぶつからない。
    http_client = anthropic.DefaultHttpxClient(verify=ssl.create_default_context())
    return anthropic.Anthropic(http_client=http_client)


def yobu_json(system: str, user: str, schema: dict) -> str:
    """決まった形（schema）の JSON で答えてもらう。戻り値は JSON の文字列。

    ⭐ output_config の format に schema を渡すと、答えが必ずその形の JSON になる。
       「JSON で返して」とお願いするだけだと、前後に説明文が付いて json.loads が落ちる。
    """
    response = _client().beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=BETAS,
        fallbacks=FALLBACKS,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("モデルがこの文章の処理を断りました。")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("答えが長すぎて途中で切れました。")
    return next(block.text for block in response.content if block.type == "text")
