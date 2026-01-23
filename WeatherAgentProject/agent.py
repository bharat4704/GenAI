
from dotenv import load_dotenv
from groq import Groq
import requests
from pydantic import BaseModel
from typing import Optional
import json
import os

# --------------------------------------------------
# Load environment variables from .env
# --------------------------------------------------
load_dotenv()

# --------------------------------------------------
# Initialize Groq client
# --------------------------------------------------
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# --------------------------------------------------
# Tool: Get Weather
# --------------------------------------------------
def get_weather(city: str) -> str:
    url = f"https://wttr.in/{city.lower()}?format=%C+%t"
    response = requests.get(url)

    if response.status_code == 200:
        return f"The weather in {city} is {response.text}"

    return "Unable to fetch weather information."

# --------------------------------------------------
# Available tools
# --------------------------------------------------
available_tools = {
    "get_weather": get_weather
}

# --------------------------------------------------
# System Prompt
# --------------------------------------------------
SYSTEM_PROMPT = """
You are an AI agent.

You MUST respond strictly in JSON.
You work in steps: PLAN, TOOL, OUTPUT.

JSON format:
{
  "step": "PLAN | TOOL | OUTPUT",
  "content": "string",
  "tool": "string",
  "input": "string"
}

Rules:
- Only one step at a time
- Call TOOL only if required
- Do not add extra text outside JSON
"""

# --------------------------------------------------
# Output Schema
# --------------------------------------------------
class AgentResponse(BaseModel):
    step: str
    content: Optional[str] = None
    tool: Optional[str] = None
    input: Optional[str] = None

# --------------------------------------------------
# Message history
# --------------------------------------------------
messages = [
    {"role": "system", "content": SYSTEM_PROMPT}
]

# --------------------------------------------------
# Main loop
# --------------------------------------------------
while True:
    user_input = input("👉🏻 ")
    messages.append({"role": "user", "content": user_input})

    while True:
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=messages,
            temperature=0
        )

        raw_output = response.choices[0].message.content
        messages.append({"role": "assistant", "content": raw_output})

        parsed = AgentResponse.parse_raw(raw_output)

        # PLAN step
        if parsed.step == "PLAN":
            print("🧠", parsed.content)
            continue

        # TOOL step
        if parsed.step == "TOOL":
            tool_name = parsed.tool
            tool_input = parsed.input

            print(f"🛠️ Calling {tool_name}({tool_input})")

            tool_result = available_tools[tool_name](tool_input)

            messages.append({
                "role": "developer",
                "content": json.dumps({
                    "step": "OBSERVE",
                    "tool": tool_name,
                    "input": tool_input,
                    "output": tool_result
                })
            })
            continue

        # OUTPUT step
        if parsed.step == "OUTPUT":
            print("🤖", parsed.content)
            break
