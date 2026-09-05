import os
import httpx
import asyncio

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv chưa cài, bỏ qua

API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
GEN_MODEL = "gemini-3.5-flash"
EMBED_MODEL = "gemini-embedding-001"

async def test_key():
    if not API_KEY:
        print("❌ Chưa có GEMINI_API_KEY — thêm dòng GEMINI_API_KEY=... vào file .env rồi chạy lại.")
        return

    print("="*50)
    print("1. Đang kiểm tra Chat (Generate Content)...")
    url_gen = f"https://generativelanguage.googleapis.com/v1beta/models/{GEN_MODEL}:generateContent?key={API_KEY}"
    payload_gen = {
        "contents": [{"parts": [{"text": "Xin chào"}]}]
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url_gen, json=payload_gen, timeout=10.0)
        if resp.status_code == 200:
            print("✅ TEST CHAT THÀNH CÔNG!")
        else:
            print(f"❌ TEST CHAT LỖI (HTTP {resp.status_code}): {resp.text}")

    print("\n" + "="*50)
    print(f"2. Đang kiểm tra Embedding ({EMBED_MODEL})...")
    url_embed = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:embedContent?key={API_KEY}"
    payload_embed = {
        "model": f"models/{EMBED_MODEL}",
        "content": {"parts": [{"text": "Xin chào"}]},
        "taskType": "RETRIEVAL_QUERY"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url_embed, json=payload_embed, timeout=10.0)
        if resp.status_code == 200:
            print("✅ TEST EMBEDDING THÀNH CÔNG!")
        else:
            print(f"❌ TEST EMBEDDING LỖI (HTTP {resp.status_code}): {resp.text}")

if __name__ == "__main__":
    asyncio.run(test_key())
