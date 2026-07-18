"""
One-off script to check if your Gemini API key is still working.
Run manually whenever you suspect rate-limiting or an expired key.
NOT part of the FastAPI app.

Usage:
    python check_gemini_key.py
"""

import os
import sys
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY", "")

if not API_KEY:
    print("❌ No GEMINI_API_KEY found in .env")
    sys.exit(1)

genai.configure(api_key=API_KEY)


def check_generate():
    """Check the main text-generation model."""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            "Reply with just the word: pong",
            generation_config={"max_output_tokens": 5}
        )
        print(f"✅ generate_content OK — response: {response.text.strip()!r}")
        return True
    except Exception as e:
        print(f"❌ generate_content FAILED: {e}")
        return False


def check_embedding():
    """Check the embedding model (used by your RAG pipeline)."""
    try:
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content="test embedding",
            task_type="retrieval_document"
        )
        dim = len(result["embedding"])
        print(f"✅ embed_content OK — embedding dim: {dim}")
        return True
    except Exception as e:
        print(f"❌ embed_content FAILED: {e}")
        return False


if __name__ == "__main__":
    print("Checking Gemini API key...\n")
    gen_ok = check_generate()
    embed_ok = check_embedding()

    print("\n--- Summary ---")
    if gen_ok and embed_ok:
        print("Key is fully working (generation + embeddings).")
    elif gen_ok or embed_ok:
        print("Key partially working — one model type failed. See errors above.")
    else:
        print("Key is NOT working — check quota, billing, or key validity in Google AI Studio.")