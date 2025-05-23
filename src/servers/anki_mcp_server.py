import sys
import os
from pathlib import Path
from typing import Optional

# Add the project root to the path to allow importing AnkiClient
project_root = Path(__file__).parents[2]  # Go up two directories from current file
sys.path.append(str(project_root))

from AnkiClient.src.operations import card_ops, deck_ops, note_ops, user_ops, study_ops, import_ops, export_ops, db_ops
from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("Anki Operations")

BASE_URL = 'http://localhost:5001/api'
MODE = "simple_study"

#
# Modal Operations
#
@mcp.tool()
def change_mode(mode: str):
    """
    This changes the mode to either "simple_study", "curate", "curate_and_assess"
    """
    global MODE
    MODE = mode

#
# Card Operations
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
    return card_ops.create_card(
        username=username,
        note_type=note_type,
        deck_id=deck_id,
        fields=fields,
        tags=tags
    )

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
def get_card_by_id(note_id: int, username: str) -> dict:
    """
    Retrieve a card using its associated note ID.
    - note_id (int): The note's unique ID.
    - username (str): The user who owns the card.
    Returns: dict with card info for the given note.
    Use this to find a card when you know the note but not the card ID.
    """
    return card_ops.get_card_by_id(note_id=note_id, username=username)

@mcp.tool()
def get_cards_by_note_id(note_id: int, username: str, inclusions: list = None) -> dict:
    """
    Retrieve a card using its associated note ID.
    - note_id (int): The note's unique ID.
    - username (str): The user who owns the card.
    - inclusions (list, optional): List of field names to include in the fields dict.
    Returns: dict with card info for the given note.
    """
    return card_ops.get_cards_by_note_id(note_id=note_id, username=username, inclusions=inclusions)

@mcp.tool()
def get_cards_by_tag(tag: str, username: str, inclusions: list = None) -> dict:
    """
    Get all cards for a user that have a specific tag.
    - tag (str): The tag to filter by.
    - username (str): The user whose cards to search.
    - inclusions (list, optional): List of field names to include in the fields dict.
    Returns: dict/list of cards with the tag.
    Use this to find or batch-process cards by topic or label.
    """
    return card_ops.get_cards_by_tag(tag=tag, username=username, inclusions=inclusions)

@mcp.tool()
def get_cards_by_state(deck_id: int, state: str, username: str, include_fields: bool = False, inclusions: list = None) -> dict:
    """
    Get all cards in a deck for a user filtered by their learning state.
    - deck_id (int): The deck to search.
    - username (str): The user who owns the cards.
    - include_fields (bool, optional): Whether to include the fields of the cards. Defaults to False.
    - inclusions (list, optional): List of field names to include in the fields dict.
    - state (str): Card state ('new', 'learning', 'review', etc.).
        'new'
        'learning'
        'due'
        'suspended'
        'manually_buried'
        'sibling_buried'
        'day_learn_relearn'
        'preview'
    Returns: dict/list of cards in the specified state.
    Use this to select cards for study or review sessions.
    """
    if include_fields:
        return card_ops.get_cards_by_state(deck_id=deck_id, state=state, username=username, inclusions=inclusions)
    else:
        return card_ops.get_cards_by_state_without_fields(deck_id=deck_id, state=state, username=username)

@mcp.tool()
def get_cards_by_tag_and_state(tag: str, state: str, username: str, include_fields: bool = False, inclusions: list = None) -> dict:
    """
    Get all cards for a user that have a specific tag and are in a specific state.
    refer to get_cards_by_state for the state values.
    include_fields is a boolean that defaults to False.
    inclusions (list, optional): List of field names to include in the fields dict.
    """
    if include_fields:
        return card_ops.get_cards_by_tag_and_state(tag=tag, state=state, username=username, inclusions=inclusions)
    else:
        return card_ops.get_cards_by_tag_and_state_without_fields(tag=tag, state=state, username=username)

@mcp.tool()
def suspend_card(card_id: int, username: str) -> dict:
    """
    Suspend a card for a user, making it temporarily unavailable for study.
    - card_id (int): The card to suspend.
    - username (str): The user who owns the card.
    Returns: dict with success or error info.
    Use this to pause cards that should not appear in study sessions.
    """
    return card_ops.suspend_card(card_id=card_id, username=username)

@mcp.tool()
def reset_card(card_id: int) -> dict:
    """
    Reset a card's scheduling and progress, making it as if it was never studied.
    - card_id (int): The card to reset.
    Returns: dict with reset status.
    Use this to restart learning for a card.
    """
    return card_ops.reset_card(card_id=card_id)

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

@mcp.tool()
def get_cards_by_ease_(username: str, deck_id: int, min_reviews: int = 3, min_factor: int = 2000, max_factor: int = 2750, min_ratio: float = 0.2, max_ratio: float = 1.0, include_suspended: bool = False, include_fields: bool = True, inclusions: list = None) -> dict:
    '''
    Get difficult cards based on criteria like reviews, ease factor, and review-to-interval ratio.
    - username (str): The user who owns the cards.
    - deck_id (int): The deck to search.
    - min_reviews (int): Minimum number of reviews.
    - min_factor (int): Minimum ease factor (in permille). 2300, 2500, 2100, 2700, etc
    - max_factor (int): Maximum ease factor (in permille). 2300, 2500, 2100, 2700, etc
    - min_ratio (float): Minimum reviews-to-interval ratio.
    - include_suspended (bool): Whether to include suspended cards.
    - include_fields (bool): Whether to include card fields.
    - inclusions (list, optional): List of field names to include in the fields dict.
    Returns: List of difficult cards.
    '''
    return card_ops.get_cards_by_ease_(username=username, deck_id=deck_id, min_reviews=min_reviews, min_factor=min_factor, max_factor=max_factor, min_ratio=min_ratio, max_ratio=max_ratio, include_suspended=include_suspended, include_fields=include_fields, inclusions=inclusions)

@mcp.tool()
def get_cards_by_learning_metrics(username: str, deck_id: int, min_reviews: Optional[int] = None, max_reviews: Optional[int] = None, min_interval: Optional[int] = None, max_interval: Optional[int] = None, min_factor: Optional[int] = None, max_factor: Optional[int] = None, min_lapses: Optional[int] = None, max_lapses: Optional[int] = None, min_ratio: Optional[float] = None, max_ratio: Optional[float] = None, include_suspended: bool = False, include_new: bool = False, include_fields: bool = True, limit: int = 100, inclusions: list = None) -> dict:
    '''
    Get cards filtered by various learning metrics.
    - username (str): The user who owns the cards.
    - deck_id (int): The deck to search.
    - min_reviews, max_reviews, etc.: Filters for specific metrics.
    - include_suspended, include_new: Whether to include those card types.
    - include_fields: Whether to include card fields.
    - limit: Maximum number of cards to return.
    - inclusions (list, optional): List of field names to include in the fields dict.
    Returns: List of filtered cards.
    '''
    return card_ops.get_cards_by_learning_metrics(username=username, deck_id=deck_id, min_reviews=min_reviews, max_reviews=max_reviews, min_interval=min_interval, max_interval=max_interval, min_factor=min_factor, max_factor=max_factor, min_lapses=min_lapses, max_lapses=max_lapses, min_ratio=min_ratio, max_ratio=max_ratio, include_suspended=include_suspended, include_new=include_new, include_fields=include_fields, limit=limit, inclusions=inclusions)

#
# Deck Operations
#

@mcp.tool()
def create_deck(deck_name: str, username: str) -> dict:
    """
    Create a new deck for a user.
    - deck_name (str): The name of the new deck.
    - username (str): The user who will own the deck.
    Returns: dict with the new deck's ID and info.
    Use this to organize cards into new collections.
    """
    return deck_ops.create_deck(deck_name, username)

@mcp.tool()
def get_decks(username: str) -> dict:
    """
    Retrieve all decks belonging to a user.
    - username (str): The user whose decks to list.
    Returns: dict/list of all decks for the user.
    Use this to show available decks or for deck selection.
    """
    return deck_ops.get_decks(username)

@mcp.tool()
def get_deck(deck_id: int, username: str) -> dict:
    """
    Get detailed information about a specific deck.
    - deck_id (int): The deck's unique ID.
    - username (str): The user who owns the deck.
    Returns: dict with deck details and metadata.
    Use this to display or manage a single deck.
    """
    return deck_ops.get_deck(deck_id, username)

@mcp.tool()
def get_cards_in_deck(deck_id: int, username: str) -> dict:
    """
    List all cards in a specific deck for a user.
    - deck_id (int): The deck to list cards from.
    - username (str): The user who owns the deck.
    Returns: dict/list of cards in the deck.
    Use this to enumerate or process all cards in a deck.
    """
    return deck_ops.get_cards_in_deck(deck_id, username)

@mcp.tool()
def rename_deck(deck_id: int, new_name: str, username: str) -> dict:
    """
    Rename an existing deck for a user.
    - deck_id (int): The deck to rename.
    - new_name (str): The new name for the deck.
    - username (str): The user who owns the deck.
    Returns: dict with rename status.
    Use this to update deck organization or fix typos.
    """
    return deck_ops.rename_deck(deck_id, new_name, username)

@mcp.tool()
def delete_deck(deck_id: int, username: str) -> dict:
    """
    Permanently delete a deck and all its cards for a user.
    - deck_id (int): The deck to delete.
    - username (str): The user who owns the deck.
    Returns: dict with deletion status.
    Use this to remove obsolete or empty decks.
    """
    return deck_ops.delete_deck(deck_id, username)

#
# Note Operations
#
@mcp.tool()
def get_notetypes(username: str) -> dict:
    """
    Get all note types for a user.
    - username (str): The user who owns the note types.
    Returns: dict with note types.
    """
    return note_ops.get_notetypes(username)

@mcp.tool()
def create_notetype_with_fields(username: str, name: str, fields: list, base_notetype_id: int, qfmt: str = None, afmt: str = None) -> dict:
    """
    Create a new note type (notetype) with custom fields for a user.

    Args:
        username (str): The user who owns the note types.
        name (str): The name of the new note type.
        fields (list of str): List of field names (e.g., ["Front", "Back"]).
        base_notetype_id (int): The ID of the base notetype to copy templates from (required).
        qfmt (str, optional): The question format for the first template. If not provided, defaults to '{{<first_field>}}'.
        afmt (str, optional): The answer format for the first template. If not provided, defaults to '{{FrontSide}}<hr id=answer>{{<second_field>}}'.

    Example:
        create_notetype_with_fields(
            username="User 1",
            name="My Notetype",
            fields=["Front", "Back"],
            base_notetype_id=123456789,
            qfmt="{{Front}}",
            afmt="{{FrontSide}}<hr id=answer>{{Back}}"
        )
    """
    return note_ops.create_notetype_with_fields(username, name, fields, base_notetype_id, qfmt, afmt)


@mcp.tool()
def get_notetype_id_by_card_id(card_id: int, username: str) -> dict:
    """
    Get the notetype ID for a card for a user.

    Args:
        card_id (int): The card's ID.
        username (str): The user who owns the card.
    Returns:
        dict: {"notetype_id": <id>} or error info.
    """
    return note_ops.get_notetype_id_by_card_id(card_id, username)

@mcp.tool()
def get_notetype_templates(notetype_id: int, username: str) -> dict:
    """
    Get the templates for a notetype for a user.
    """
    return note_ops.get_notetype_templates(notetype_id, username)

@mcp.tool()
def add_template_to_notetype(notetype_id: int, template_name: str, qfmt: str, afmt: str, username: str) -> dict:
    """
    Add a card template to a notetype for a user.

    Args:
        notetype_id (int): The notetype's ID.
        template_name (str): The name of the new template.
        qfmt (str): The question format (HTML or Anki template syntax).
        afmt (str): The answer format (HTML or Anki template syntax).
        username (str): The user who owns the notetype.
    Example:
        add_template_to_notetype(
            notetype_id=123456789,
            template_name="Reverse",
            qfmt="{{Back}}",
            afmt="{{FrontSide}}<hr id=answer>{{Front}}",
            username="User 1"
        )
    """
    return note_ops.add_template_to_notetype(notetype_id, template_name, qfmt, afmt, username)

@mcp.tool()
def get_notetype_css(notetype_id: int, username: str) -> dict:
    """
    Get the CSS for a notetype for a user.

    Args:
        notetype_id (int): The notetype's ID.
        username (str): The user who owns the notetype.
    Returns:
        dict: {"css": <css_string>} or error info.
    """
    return note_ops.get_notetype_css(notetype_id, username)

@mcp.tool()
def update_notetype_css(notetype_id: int, new_css: str, username: str) -> dict:
    """
    Update the CSS for a notetype for a user.

    Args:
        notetype_id (int): The notetype's ID.
        new_css (str): The new CSS string.
        username (str): The user who owns the notetype.
    Example:
        update_notetype_css(
            notetype_id=123456789,
            new_css=".card { font-family: Arial; }",
            username="User 1"
        )
    """
    return note_ops.update_notetype_css(notetype_id, new_css, username)


@mcp.tool()
def get_notetype_fields(notetype_id: int, username: str) -> dict:
    """
    Get the fields for a notetype for a user.

    Args:
        notetype_id (int): The notetype's ID.
        username (str): The user who owns the notetype.
    Returns:
        dict: {"fields": [<field_dicts>]} or error info.
    """
    return note_ops.get_notetype_fields(notetype_id, username)

@mcp.tool()
def add_field_to_notetype(notetype_id: int, field_name: str, username: str) -> dict:
    """
    Add a field to a notetype for a user.

    Args:
        notetype_id (int): The notetype's ID.
        field_name (str): The name of the new field.
        username (str): The user who owns the notetype.
    Example:
        add_field_to_notetype(
            notetype_id=123456789,
            field_name="Extra Info",
            username="User 1"
        )
    """
    return note_ops.add_field_to_notetype(notetype_id, field_name, username)

@mcp.tool()
def remove_field_from_notetype(notetype_id: int, field_name: str, username: str) -> dict:
    """
    Remove a field from a notetype for a user.

    Args:
        notetype_id (int): The notetype's ID.
        field_name (str): The name of the field to remove.
        username (str): The user who owns the notetype.
    Example:
        remove_field_from_notetype(
            notetype_id=123456789,
            field_name="Extra Info",
            username="User 1"
        )
    """
    return note_ops.remove_field_from_notetype(notetype_id, field_name, username)

@mcp.tool()
def update_note_contents(note_id: int, fields: dict, username: str, tags: list = None) -> dict:
    """
    Update the contents of a note by modifying its fields.
    
    Args:
        note_id (int): The ID of the note to update
        fields (dict): Dictionary mapping field names to their new values
        username (str): The user who owns the note
        
    Returns:
        dict: Response from the note update operation
        
    Example:
        update_note_contents(
            note_id=12345,
            fields={"Front": "Updated question", "Back": "Updated answer"},
            username="user1",
            tags=["tag1", "tag2"]
        )
    """
    return note_ops.update_note_fields(
        note_id=note_id,
        username=username,
        fields=fields,
        tags=tags
    )

@mcp.tool()
def get_sort_field(notetype_id: int, username: str) -> dict:
    """
    Get the sort field for a notetype for a user.

    Args:
        notetype_id (int): The notetype's ID.
        username (str): The user who owns the notetype.
    Returns:
        dict: {"sort_field": <field_name>} or error info.
    """
    return note_ops.get_sort_field(notetype_id, username)

@mcp.tool()
def set_sort_field(notetype_id: int, field_name: str, username: str) -> dict:
    """
    Set the sort field for a notetype for a user.

    Args:
        notetype_id (int): The notetype's ID.
        field_name (str): The name of the field to use for sorting.
        username (str): The user who owns the notetype.
    Example:
        set_sort_field(
            notetype_id=123456789,
            field_name="Front",
            username="User 1"
        )
    """
    return note_ops.set_sort_field(notetype_id, field_name, username)

@mcp.tool()
def reorder_fields(notetype_id: int, new_order: dict, username: str) -> dict:
    """
    Reorder the fields for a notetype for a user.

    Args:
        notetype_id (int): The notetype's ID.
        new_order (dict): Mapping of field names to new ordinal positions (0-based). Example: {"Front": 1, "Back": 0}
        username (str): The user who owns the notetype.
    Example:
        reorder_fields(
            notetype_id=123456789,
            new_order={"Front": 1, "Back": 0},
            username="User 1"
        )
    """
    return note_ops.reorder_fields(notetype_id, new_order, username)

@mcp.tool()
def get_note(note_id: int, username: str) -> dict:
    """
    Retrieve a specific note by its ID for a user.
    - note_id (int): The note's unique ID.
    - username (str): The user who owns the note.
    Returns: dict with note fields, tags, and associated card info.
    Use this to view or edit note content.
    """
    return note_ops.get_note(note_id=note_id, username=username)

@mcp.tool()
def update_note(note_id: int, username: str, fields: dict = None, tags: list = None) -> dict:
    """
    Update the fields and/or tags of an existing note for a user.
    - note_id (int): The note to update.
    - username (str): The user who owns the note.
    - fields (dict, optional): New field values.
    - tags (list, optional): New tags.
    Returns: dict with update status.
    Use this to modify note content or organization.
    """
    return note_ops.update_note(
        note_id=note_id,
        username=username,
        fields=fields,
        tags=tags
    )

@mcp.tool()
def delete_note(note_id: int, username: str) -> dict:
    """
    Permanently delete a note and all its associated cards for a user.
    - note_id (int): The note to delete.
    - username (str): The user who owns the note.
    Returns: dict with deletion status.
    Use this to remove unwanted notes and their cards.
    """
    return note_ops.delete_note(note_id=note_id, username=username)

#
# User Operations
#

@mcp.tool()
def create_user(username: str) -> dict:
    """
    Create a new user profile in the Anki system.
    - username (str): The unique username for the new user.
    Returns: dict with user info or error details.
    Use this to initialize a new user's collection.
    """
    return user_ops.create_user(username)

@mcp.tool()
def get_user(username: str) -> dict:
    """
    Retrieve information about a user.
    - username (str): The username to look up.
    Returns: dict with user details and stats.
    Use this to check user existence or get user metadata.
    """
    return user_ops.get_user(username)

@mcp.tool()
def delete_user(username: str) -> dict:
    """
    Permanently delete a user and all their data.
    - username (str): The user to delete.
    Returns: dict with deletion status.
    Use this to remove test or obsolete users.
    """
    return user_ops.delete_user(username)

def sync_user_login(profile_name: str, upload: bool = False) -> dict:
    """
    Synchronize a user's login credentials and collection with the Anki server.
    - profile_name (str): The user's profile name., i.e. 'User 1', 'chase', 'admin', etc.
    - upload (bool, optional): Whether to upload the user's collection to the server, default is False.
    Returns: dict with sync status and details.
    Use this to synchronize a user's login credentials and collection with the Anki server.
    """
    import dotenv
    dotenv.load_dotenv()
    username = os.getenv('ANKI_USERNAME')
    password = os.getenv('ANKI_PASSWORD')
    endpoint = os.getenv('ANKI_ENDPOINT')
    return user_ops.sync_user_login(profile_name=profile_name, username=username, password=password, endpoint=endpoint, upload=upload)

#
# DB Operations
#

@mcp.tool()
def sync_db(profile_name: str, sync_media: bool = False, upload: bool = False) -> dict:
    """
    Synchronize a user's collection with the Anki server.
    - profile_name (str): The user's profile name., i.e. 'User 1', 'chase', 'admin', etc.
    - sync_media (bool, optional): Whether to sync media.
    - upload (bool, optional): Whether to upload the user's collection to the server.
    Returns: dict with sync status and details.
    Use this to synchronize a user's collection with the Anki server.
    """
    import dotenv
    import json
    dotenv.load_dotenv()
    hkey = os.getenv('ANKI_HKEY')
    endpoint = os.getenv('ANKI_ENDPOINT')
    response = db_ops.sync_db(profile_name, hkey, endpoint, sync_media, upload)
    response['hkey'] = hkey
    response['endpoint'] = endpoint
    return response

#
# Study Operations
#
@mcp.tool()
def study(*, deck_id: int, action: str, username: str, base_url: str = BASE_URL) -> tuple[dict, int]:
    """
    Start a new study session for a user on a specific deck.
    - deck_id (int): The deck to study.
    - action (str): The action to perform (e.g., 'start', 'flip', '3', 'close').
    - '1', '2', '3', '4' are the rating actions, telling anki to take the action of pressing 1, 2, 3, or 4.
    - an action can be either to start a new session, flip the current card, answer the current card with an ease rating, or close the current session.
    - username (str): The user studying the deck.
    Returns: dict with session info and selected cards.
    Use this to begin a focused review or learning session.
    You need to be prepared to comply with either 'curation_instructions' or 'assessment_intructions'
    that will tell you to follow a specific Protocol supplied to you earlier in your chat with the user.
    If the instructions have not been supplied to you, then prompt the user to provide them.
    """
    response_data, response_status_code = study_ops.study(deck_id=deck_id, action=action, username=username)
    if 'close' in action or action in 'close' or action.startswith('close') or action.endswith('close'):
        sync_message = sync_db(profile_name=username, sync_media=False, upload=False)
        response_data['sync_message'] = sync_message
    if MODE == "simple_study":
        return response_data, response_status_code
    elif MODE.startswith("curate"):
        response_data['curation_instructions'] = "Apply the `Curation Protocol` supplied in the `Anki Instructions`"
        return response_data, response_status_code
    elif MODE == "curate_and_assess":
        response_data["assessment_instructions"] = "Apply the `Assessment Protocol` supplied in the `Anki Instructions`"
        return response_data, response_status_code
    return response_data, response_status_code

@mcp.tool()
def flip_and_submit(deck_id: int, action: str, username: str) -> dict:
    """
    - deck_id (int): The deck to study.
    - action (str): SHOULD ONLY EVER BE ONE OF '1, '2', '3', or '4', tells anki to press 1, 2, 3, or 4
    - username (str): The user studying the deck.
    Returns: dict with session info and selected cards.
    This should be called whenever a study session request has curation or assessment instructions.
    this takes a number for its feedback, 1, 2, 3, or 4 and automatically flips the card first,
    and THEN submits the feedback. It saves you from calling `study` twice.

    You need to be prepared to comply with either 'curation_instructions' or 'assessment_intructions'
    that will tell you to follow a specific Protocol supplied to you earlier in your chat with the user.
    If the instructions have not been supplied to you, then prompt the user to provide them.
    """
    flip_response = study(deck_id=deck_id, action="flip", username=username)
    submit_response = study(deck_id=deck_id, action=action, username=username)
    return submit_response

@mcp.tool()
def create_custom_study_session(username: str, deck_id: int, custom_study_params: dict, leave_open: bool = False) -> dict:
    """
    Create a custom study session for a user on a specific deck.
    - username (str): The user who owns the deck.
    - deck_id (int): The deck to study.
    - custom_study_params (dict): The custom study parameters.
    - leave_open (bool, optional): Whether to leave the study session open after completion.
    i.e.:
    custom_study_params = {
        "new_limit_delta": 0,
        "cram": {
            "kind": "CRAM_KIND_DUE",
            "card_limit": count,
            "tags_to_include": [],
            "tags_to_exclude": []
        }
    }
    """
    response, status_code =  study_ops.create_custom_study_session(username=username, deck_id=deck_id, custom_study_params=custom_study_params)
    if not leave_open:
        created_deck_id = response['created_deck_id']
        _ = study(deck_id=created_deck_id, action="close", username=username)
    return response

@mcp.tool()
def supply_feedback_for_cards(username: str, deck_id: int, feedback: dict[int, str]) -> dict:
    """
    Supply feedback for a list of cards.
    - username (str): The user who owns the deck.
    - deck_id (int): The deck to supply feedback for.
    - feedback (dict[int, str]): A dictionary of the card id and the feedback to supply.
    - the card id that you put in the dictionary is supposed to be an integer, not a string.
    - you are supposed to supply the number, not the word.
    for the feedback you are to supply a string version of '1', '2', '3', or '4'
    where 1 is again, 2 is hard, 3 is good, and 4 is easy.
    """
    def get_ease(card_id: int) -> str:
        try:
            return str(feedback[card_id])
        except:
            return str(feedback[str(card_id)])
    try:
        count = len(feedback)
        response, _ = study(deck_id=deck_id, action="start", username=username)
        if 'card_id' in response:
            card_id = response['card_id']
            ease = get_ease(card_id)
            response, _ = flip_and_submit(deck_id=deck_id, action=ease, username=username)
            for _ in range(count - 1):
                if 'card_id' in response:
                    card_id = response['card_id']
                    ease = get_ease(card_id)
                    response, _ = flip_and_submit(deck_id=deck_id, action=ease, username=username)
        response, _ = study(deck_id=deck_id, action="close", username=username)
        return response
    except Exception as e:
        return {"status": "error", "message": str(e)}

#
# Import/Export Operations
#

@mcp.tool()
def upload_anki_package(username: str, file_path: str) -> dict:
    """
    Import an Anki .apkg package file into a user's collection.
    - username (str): The user to import for.
    - file_path (str): Path to the .apkg file.
    Returns: dict with import status and details.
    Use this to bulk import decks and cards from Anki.
    """
    return import_ops.upload_anki_package(username, file_path)

@mcp.tool()
def upload_csv_file(username: str, file_path: str, deck_name: str, notetype: str, delimiter: str) -> dict:
    """
    Import cards from a CSV file into a user's deck and note type.
    - username (str): The user to import for.
    - file_path (str): Path to the CSV file.
    - deck_name (str): Name of the target deck.
    - notetype (str): Name of the note type/template.
    - delimiter (str): Delimiter used in the CSV (e.g., 'TAB', ',').
    Returns: dict with import status and details.
    Use this to add many cards at once from spreadsheets or exports.
    """
    return import_ops.upload_csv_file(username, file_path, deck_name, notetype, delimiter)

@mcp.tool()
def export_deck(deck_id: int, username: str, include_scheduling: bool = True) -> dict:
    """
    Export a deck as an Anki .apkg package file for backup or sharing.
    - deck_id (int): The deck to export.
    - username (str): The user who owns the deck.
    - include_scheduling (bool, optional): Whether to include scheduling data (default: True).
    Returns: dict with export file path or status.
    Use this to back up or share decks with others.
    """
    return export_ops.export_deck(deck_id=deck_id, username=username, include_scheduling=include_scheduling)

#
# High-level information resources
#

@mcp.resource("anki://help")
def anki_help() -> str:
    """Provide help information about available Anki operations"""
    return """
    # Anki Operations API

    This server exposes Anki operations through the Model Context Protocol.

    ## Available Operation Categories:

    1. Card Operations - Create, modify, and manage individual cards
    2. Deck Operations - Create and manage decks
    3. Note Operations - Work with note templates and content
    4. User Operations - Manage Anki users
    5. Study Operations - Study cards and track progress
    6. Import/Export - Import from and export to Anki packages and CSV files

    Use the tools to execute operations on the Anki system.
    """

@mcp.resource("anki://card-ops-help")
def card_ops_help() -> str:
    """Provide information about available card operations"""
    return """
    # Card Operations

    Operations for working with individual Anki cards:

    - create_card: Create a new card
    - get_card_contents: Get card contents
    - get_card_by_id: Get a card by ID
    - get_cards_by_tag: Get cards with a specific tag
    - get_cards_by_state: Get cards by state (new, learning, review)
    - suspend_card: Suspend a card
    - reset_card: Reset a card's progress
    - delete_card: Delete a card
    """

@mcp.resource("anki://deck-ops-help")
def deck_ops_help() -> str:
    """Provide information about available deck operations"""
    return """
    # Deck Operations

    Operations for working with Anki decks:

    - create_deck: Create a new deck
    - get_decks: Get all decks
    - get_deck: Get a specific deck
    - get_cards_in_deck: Get all cards in a deck
    - rename_deck: Rename a deck
    - delete_deck: Delete a deck
    """

@mcp.prompt()
def create_basic_card_prompt() -> str:
    """Prompt template for creating a basic Anki card"""
    return """
    Create a basic Anki card for the user. You'll need to:

    1. Ask the user for the front (question) and back (answer) of the card
    2. Ask which deck they want to add it to
    3. Ask for any tags they want to attach to the card

    Then use the create_card tool to create the card with the provided information.

    Remember to validate the inputs and provide helpful feedback if any information is missing.
    """

@mcp.prompt()
def study_session_prompt() -> str:
    """Prompt template for helping users study cards"""
    return """
    Help the user study their Anki cards by:

    1. Asking which deck they want to study
    2. Asking how many cards they want to study
    3. Using the start_study_session tool to begin a study session
    4. For each card:
       - Show the question
       - When the user is ready, show the answer
       - Ask the user to rate their answer (Again, Hard, Good, Easy)
       - Use the answer_card tool to record their answer

    Provide encouragement and track their progress through the session.
    """

# Run the server
if __name__ == "__main__":
    print("Attempting to start MCP server...", file=sys.stderr) # Print to stderr
    try:
        mcp.run(transport="stdio")
        # If mcp.run exits normally, this line will be reached.
        print("MCP server exited normally.", file=sys.stderr) # Print to stderr
    except Exception as e:
        # Catch and print any Python exceptions during mcp.run
        print(f"MCP server crashed with exception: {e}", file=sys.stderr) # Print to stderr
        import traceback
        traceback.print_exc(file=sys.stderr)
    finally:
        # This will run whether mcp.run exits normally or crashes
        print("MCP server process finished.", file=sys.stderr) # Print to stderr
