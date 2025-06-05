# utils_general.py

import json
import re

def extract_json_from_text(text):
    """
    Extracts and parses JSON from a GPT response, even if it's wrapped in markdown.
    """
    text = text.strip()

    # Remove common markdown formatting
    text = re.sub(r"^```(?:json)?", "", text)
    text = re.sub(r"```$", "", text)

    # Try parsing JSON directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Attempt to extract JSON using regex
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return {
                    "error": "Failed to parse extracted JSON",
                    "raw_response": text
                }

        return {
            "error": "Failed to find JSON block",
            "raw_response": text
        }
