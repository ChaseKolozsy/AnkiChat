import sys
import os
from pathlib import Path

# Add the project root to the path to allow importing AnkiClient
project_root = Path(__file__).parents[2]  # Go up two directories from current file
sys.path.append(str(project_root))

from AnkiClient.src.operations import card_ops
from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("Basic Card Operations")

#
# Basic Card Operations
#

@mcp.tool()
def create_card(username: str, note_type: str, deck_id: int, fields: dict, tags: list = None) -> dict:
    """
    Create a new Anki card for a user in a specific deck and note type.
    - username (str): The user who owns the card.
    - note_type (str): The name of the note type/template (e.g., 'Basic').
    - deck_id (int): The ID of the deck to add the card to.
    - fields (dict): A dictionary mapping field names to their values (e.g., {"Front": "Q", "Back": "A"}).
    - tags (list, optional): List of tags to attach to the card.
    Returns: dict with card and note IDs, or error info.
    Use this to add new study material for a user.
    """
    result = card_ops.create_card(
        username=username,
        note_type=note_type,
        deck_id=deck_id,
        fields=fields,
        tags=tags
    )
    card_contents = get_card_contents(result["card_ids"][0], username)
    return {
        "result": result,
        "card_contents": card_contents
    }

@mcp.tool()
def get_card_contents(card_id: int, username: str) -> dict:
    """
    Retrieve the full contents of a specific card, including all field values and metadata.
    - card_id (int): The unique card ID.
    - username (str): The user who owns the card.
    Returns: dict with card fields, tags, and scheduling info.
    Use this to display or review a card's details.
    """
    return card_ops.get_card_contents(card_id=card_id, username=username)

@mcp.tool()
def delete_card(card_id: int, username: str) -> dict:
    """
    Permanently delete a card for a user.
    - card_id (int): The card to delete.
    - username (str): The user who owns the card.
    Returns: dict with deletion status.
    Use this to remove unwanted or duplicate cards.
    """
    return card_ops.delete_card(card_id=card_id, username=username)

#
# Help resource
#

@mcp.resource("basic-card://help")
def basic_card_help() -> str:
    """Provide help information about available basic card operations"""
    return """
    # Basic Card Operations API

    This server exposes basic Anki card operations through the Model Context Protocol.

    ## Available Operations:

    1. create_card - Create a new Anki card
    2. get_card_contents - Retrieve card contents and metadata
    3. delete_card - Permanently delete a card

    Use these tools to perform basic card management operations.
    """

# Run the server
if __name__ == "__main__":
    print("Attempting to start Basic Card MCP server...", file=sys.stderr)
    try:
        mcp.run(transport="stdio")
        print("Basic Card MCP server exited normally.", file=sys.stderr)
    except Exception as e:
        print(f"Basic Card MCP server crashed with exception: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
    finally:
        print("Basic Card MCP server process finished.", file=sys.stderr) 