import os
from dotenv import load_dotenv
from google import genai

load_dotenv(dotenv_path="../.env")

api_key = os.environ.get("GOOGLE_API_KEY")
print(f"Key starts with: {api_key[:5] if api_key else 'None'}")

client = genai.Client(api_key=api_key)
print("Available embedding models:")
for m in client.models.list():
    if 'embed' in m.supported_actions:
        print(m.name)
