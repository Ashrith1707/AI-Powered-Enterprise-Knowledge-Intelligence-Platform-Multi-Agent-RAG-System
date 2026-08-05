"""Gemini connectivity diagnostic. Run from backend/ after editing .env:

    venv\\Scripts\\python -m scripts.check_gemini

Reports exactly where the key came from, whether it is valid, and whether
chat streaming works — with the precise failure cause if not.
"""
import os
import sys

from app.core.config import BACKEND_DIR, settings
from app.rag.llm_client import classify_llm_error


def main() -> int:
    print(f".env file        : {BACKEND_DIR / '.env'}")
    source = ("environment variable" if os.environ.get("GEMINI_API_KEY") is not None
              else ".env file (or default)")
    print(f"key source       : {source}")
    key = settings.gemini_api_key
    print(f"key present      : {'yes (' + key[:6] + '…)' if key else 'NO'}")
    print(f"chat model       : {settings.gemini_chat_model}")
    print(f"embedding model  : {settings.gemini_embedding_model}")
    print("-" * 50)

    if not key:
        print("RESULT: NOT CONFIGURED — set GEMINI_API_KEY in backend/.env")
        return 1

    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        vec = GoogleGenerativeAIEmbeddings(
            model=settings.gemini_embedding_model, google_api_key=key,
        ).embed_query("connection probe")
        print(f"embeddings       : OK (dimension {len(vec)})")
    except Exception as exc:
        status, detail = classify_llm_error(exc)
        print(f"embeddings       : FAILED ({status})")
        print(f"cause            : {detail}")
        return 1

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model=settings.gemini_chat_model,
                                     google_api_key=key, temperature=0)
        tokens = []
        for piece in llm.stream("Reply with the single word: ready"):
            if piece.content:
                tokens.append(piece.content)
        print(f"chat streaming   : OK ({len(tokens)} stream events, "
              f"reply: {''.join(tokens).strip()!r})")
    except Exception as exc:
        status, detail = classify_llm_error(exc)
        print(f"chat streaming   : FAILED ({status})")
        print(f"cause            : {detail}")
        return 1

    print("-" * 50)
    print("RESULT: GEMINI FULLY OPERATIONAL — restart uvicorn to pick this up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
