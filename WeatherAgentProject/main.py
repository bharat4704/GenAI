# Weather agent using Groq LLM
from dotenv import load_dotenv
from groq import Groq
import requests
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
    return "Something went wrong"

# --------------------------------------------------
# Main function
# --------------------------------------------------
def main():
    while True:
        user_query = input("> ")

        # If user asks about weather, detect it and call the tool
        if "weather" in user_query.lower():
            # crude extraction of city
            city = user_query.split("in")[-1].strip() if "in" in user_query.lower() else "Mumbai"
            weather_info = get_weather(city)
            print(f"🛠️ Weather tool output: {weather_info}")
            continue

        # Otherwise, send query to Groq LLM
        response = client.chat.completions.create(
            model="llama3-70b-8192",   # Groq LLM model
            messages=[
                {"role": "user", "content": user_query}
            ],
            temperature=0
        )

        print(f"🤖: {response.choices[0].message.content}")

# --------------------------------------------------
if __name__ == "__main__":
    main()
