import os
import re
import sys

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

sys.path.append(os.path.abspath("../scraper"))
from amazon_api import search_products

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

SYSTEM_PROMPT = """You are Kart, a friendly AI product advisor. Your job is to help users find the best product to buy on Amazon or Walmart.

Have a natural conversation to understand what the user needs. Before searching, you MUST have answers to ALL of these:
1. The SPECIFIC product - including brand/type if relevant (e.g. if they say "gaming console", ask which brand: PlayStation, Xbox, Nintendo? If they say "dishwasher", ask machine or pods?)
2. Their budget (always required - ask if not given)
3. Any key features or preferences (ask once, optional)

IMPORTANT - do NOT search until you have all the answers to YOUR OWN questions. If you asked "PlayStation, Xbox, or Nintendo?" - wait for their reply before triggering [SEARCH].

Search query rules:
- Use ALL the info collected: brand, type, features, budget
- Make queries specific enough to return the exact product category (e.g. include "machine", "appliance", "console", brand name)
- When budget is high (e.g. $500+), phrase the query to attract premium results - use words like "best", "premium", or the brand name directly
- Bad: [SEARCH: gaming console] - too generic, returns cheap retro consoles
- Good: [SEARCH: PlayStation 5 console under $1500]
- Good: [SEARCH: best dishwasher machine appliance under $700]
- Good: [SEARCH: premium 4K OLED TV 65 inch under $2000]

When ready, include this EXACTLY on its own line:
[SEARCH: <specific query>]

After receiving search results:
- Pick the best match and recommend it naturally - name, price, rating, why it fits
- NEVER say "let me try again" or "please provide new search results" - you only get one search, make it count
- If results are imperfect, recommend the closest match and explain why it's still a good option"""


def get_response(history):
    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
        temperature=0.7,
        max_tokens=1024,
    )
    return completion.choices[0].message.content


def extract_search_query(text):
    match = re.search(r"\[SEARCH:\s*(.+?)\]", text)
    return match.group(1).strip() if match else None


def format_results(products):
    if not products:
        return "No products found."
    lines = []
    for i, product in enumerate(products[:5], 1):
        lines.append(
            f"{i}. {product['name']} | Rating: {product['rating']} | Price: {product['price']}"
        )
    return "\n".join(lines)


def chatbot():
    if not GROQ_API_KEY:
        print("GROQ_API_KEY is missing. Add it to your .env file and try again.")
        return

    history = []

    print("\nKart - AI Product Advisor (Groq + LLaMA 3)\n")
    print("Type 'exit' to quit.\n")
    print("Kart: Hey, I am Kart, your personal product advisor.")
    print("      What are you looking to buy today?\n")

    while True:
        user_input = input("You: ").strip()

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit", "bye"]:
            print("\nKart: Glad I could help! Happy shopping!\n")
            break

        history.append({"role": "user", "content": user_input})

        response = get_response(history)
        search_query = extract_search_query(response)
        display = re.sub(r"\[SEARCH:.*?\]", "", response).strip()

        if search_query:
            if display:
                print(f"\nKart: {display}\n")
            print("Searching Amazon...\n")

            products = search_products(search_query)

            if products:
                results_text = format_results(products)
                history.append({"role": "assistant", "content": display or "Let me search for that."})
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"[Search results for '{search_query}':\n{results_text}]"
                            "\n\nPlease give me your recommendation."
                        ),
                    }
                )
                final = get_response(history)
                final = re.sub(r"\[SEARCH:.*?\]", "", final).strip()
                history.append({"role": "assistant", "content": final})
                print(f"Kart: {final}\n")
            else:
                history.append({"role": "assistant", "content": display})
                print(f"Kart: {display}\n")
                print("Kart: Hmm, I couldn't find results for that. Could you try rephrasing?\n")
        else:
            history.append({"role": "assistant", "content": response})
            print(f"\nKart: {response}\n")

        if len(history) > 20:
            history = history[-20:]


if __name__ == "__main__":
    chatbot()
