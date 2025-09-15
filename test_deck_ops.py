#!/usr/bin/env python3

import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import requests
from AnkiClient.src.operations import deck_ops

def test_get_decks():
    username = "chase"  # Use a known username

    print(f"Testing deck_ops.get_decks('{username}')")
    print("-" * 50)

    # First test the raw API call
    BASE_URL = "http://localhost:5001/api/decks"
    print(f"Testing raw API call to: {BASE_URL}")
    try:
        response = requests.get(BASE_URL, json={"username": username})
        print(f"HTTP Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Raw Response: {response.text}")
        print("-" * 30)
    except Exception as e:
        print(f"Raw API Error: {e}")
        print("-" * 30)

    # Then test the operation wrapper
    try:
        result = deck_ops.get_decks(username)

        print(f"Type: {type(result)}")
        print(f"Content: {result}")
        print(f"Length (if applicable): {len(result) if hasattr(result, '__len__') else 'N/A'}")

        if isinstance(result, dict):
            print(f"Keys: {list(result.keys())}")

        return result

    except Exception as e:
        print(f"deck_ops Error: {e}")
        return None

if __name__ == "__main__":
    test_get_decks()