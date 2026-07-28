import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

print("Models available to your API key:\n")
for model in client.models.list():
    # only show models that support text generation (generateContent)
    if "generateContent" in model.supported_actions:
        print(f"- {model.name}")