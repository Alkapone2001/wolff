# summarization.py

import os
from dotenv import load_dotenv
from openai import OpenAI

# Load OPENAI_API_KEY from .env
load_dotenv()

# Initialize OpenAI client
client = OpenAI()

def summarize_messages(messages: list[dict]) -> str:
    """
    Given a list of messages (each a dict with 'role' and 'content'),
    build a single conversation string, call the LLM to summarize it,
    and return the summary text.
    """
    # Build a plain-text conversation history
    conversation = ""
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        conversation += f"{role}: {content}\n"

    # Construct a summarization prompt (system + user)
    # Feel free to tweak the system message to match your accounting context
    system_message = "You are an accounting assistant. Concisely summarize the following conversation so it can be used as context in the future."
    user_message = conversation

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # or whichever model you prefer
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
    )

    # Extract the summary from the LLM’s reply
    summary = response.choices[0].message.content
    return summary
