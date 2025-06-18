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
    # 1. Build a plain-text conversation history
    conversation = ""
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        conversation += f"{role}: {content}\n"

    # 2. Create a system/user prompt for summarization
    system_message = (
        "You are an accounting assistant. Summarize the following conversation "
        "as concisely as possible, preserving important details for future context."
    )
    user_message = conversation

    # 3. Call the model
    response = client.chat.completions.create(
        model="gpt-4o-mini",  # adjust if you prefer a different model
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
    )

    # 4. Extract and return the summary
    summary_text = response.choices[0].message.content
    return summary_text
