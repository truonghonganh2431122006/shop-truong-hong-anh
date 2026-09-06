import os, httpx
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

k = os.getenv("GEMINI_API_KEY", "")
r = httpx.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={k}")
for m in r.json().get("models", []):
    name = m["name"]
    methods = m.get("supportedGenerationMethods", [])
    if "generateContent" in methods and "flash" in name.lower():
        print(name)
