import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENAI_API_KEY")
)

response = client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[
        {"role": "user", "content": "Say hello"}
    ],
    extra_headers={
        "HTTP-Referer": "https://cerca-app.com",
        "X-Title": "CERCA Disaster System",
    }
)

print(response.choices[0].message.content)