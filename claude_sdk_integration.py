#!/usr/bin/env python3.10
"""
Claude Code SDK Integration Module
Handles Claude Code SDK interactions for AnkiChat with context-aware word definitions
"""

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import deque
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CachedCard:
    """Represents a cached card with user response"""
    card_id: int
    user_answer: int  # 1, 2, 3, 4
    card_data: Dict[str, Any]
    timestamp: float


@dataclass
class StudySessionState:
    """Manages study session state"""
    session_id: str
    deck_id: int
    current_card: Optional[Dict[str, Any]] = None
    is_paused: bool = False
    cached_cards: List[CachedCard] = None

    def __post_init__(self):
        if self.cached_cards is None:
            self.cached_cards = []


class VocabularyQueueManager:
    """Manages LIFO vocabulary queue for default deck"""

    def __init__(self):
        self.queue = deque()  # LIFO queue for new vocabulary cards
        self.card_answer_mapping: Dict[int, int] = {}  # card_id -> answer
        self.processed_cards: List[Dict[str, Any]] = []
        self.seen_card_ids: set[int] = set()  # Track seen IDs to avoid treating existing cards as new
        self.in_progress_ids: set[int] = set()  # Cards currently shown but not yet answered

    def add_new_card(self, card_data: Dict[str, Any]):
        """Add new card to front of queue (LIFO)"""
        cid = self._extract_card_id(card_data)
        if cid is None:
            return
        cid = int(cid)
        # Avoid duplicates or replacing an in-progress card
        if cid in self.in_progress_ids:
            return
        if any((self._extract_card_id(c) == cid) for c in self.queue):
            return
        self.queue.appendleft(card_data)
        logger.info(f"Added new vocabulary card {cid} to front of queue")

    def get_next_card(self) -> Optional[Dict[str, Any]]:
        """Get next card from front of queue"""
        if self.queue:
            card = self.queue.popleft()
            cid = self._extract_card_id(card)
            if cid is not None:
                self.in_progress_ids.add(int(cid))
            return card
        return None

    def cache_answer(self, card_id: int, answer: int):
        """Cache user answer for auto-session"""
        self.card_answer_mapping[card_id] = answer
        logger.info(f"Cached answer {answer} for card {card_id}")
        # Mark in-progress card as completed when user answers
        try:
            self.in_progress_ids.discard(int(card_id))
        except Exception:
            pass

    def get_cached_answer(self, card_id: int) -> Optional[int]:
        """Get cached answer for card"""
        return self.card_answer_mapping.get(card_id)

    @staticmethod
    def _extract_card_id(card: Dict[str, Any]) -> Optional[int]:
        return card.get('id') or card.get('card_id')

    def record_initial_cards(self, cards: List[Dict[str, Any]]):
        """Seed seen_card_ids with existing cards so they aren't treated as new."""
        for c in cards:
            cid = self._extract_card_id(c) if isinstance(c, dict) else None
            if cid is not None:
                self.seen_card_ids.add(int(cid))
        logger.info(f"Seeded {len(self.seen_card_ids)} existing vocabulary cards as seen")

    def requeue_in_progress(self, card: Dict[str, Any]) -> bool:
        """Move an in-progress card back to the top of the queue (LIFO)."""
        cid = self._extract_card_id(card)
        if cid is None:
            return False
        cid = int(cid)
        if cid in self.in_progress_ids:
            self.in_progress_ids.remove(cid)
            # Mark it as seen and put back at the BOTTOM so newest stays on top
            if not any((self._extract_card_id(c) == cid) for c in self.queue):
                self.queue.append(card)
            return True
        return False


class ClaudeSDKIntegration:
    """Main Claude Code SDK integration class"""

    def __init__(self, anki_client, target_language: str = "Hungarian", banned_language: str = "English"):
        self.anki_client = anki_client
        self.target_language = target_language
        self.banned_language = banned_language
        # Map language to appropriate vocabulary tag
        self.vocabulary_tag = self._get_vocabulary_tag(target_language)
        self.grammar_session = StudySessionState("", 0)
        self.vocabulary_queue = VocabularyQueueManager()
        self.polling_active = False
        self.claude_sdk_available = False
        # Deck to monitor for new vocabulary cards (default Anki deck id: 1)
        self.vocab_deck_id: int = 1
        # Poller initialization guard: first pass seeds without enqueuing
        self.vocab_initialized: bool = False
        # Track current vocabulary card for nested layer generation
        self.current_vocabulary_card: Optional[Dict[str, Any]] = None
        # Track last created vocabulary session for frontend retrieval
        self.last_vocabulary_session: Optional[Dict[str, Any]] = None
        # Track current layer tag for polling (set by definition requests)
        self.current_layer_tag: Optional[str] = None
        # Track expected word count for current layer
        self.words_in_current_layer: int = 0
        # Track initial card count before Claude SDK creates new cards
        self.initial_card_count: int = 0
        # Track cards processed in current layer
        self.cards_processed_in_current_layer: int = 0
        self._check_sdk_availability()

    def _get_vocabulary_tag(self, language: str) -> str:
        """Get the vocabulary tag for a given language"""
        # Language-specific vocabulary tags (meaning "what is this")
        language_tags = {
            "Hungarian": "mit-jelent",
            "Cebuano": "unsa-kini",
            "Spanish": "que-es",
            "French": "qu-est-ce",
            "German": "was-ist",
            "Japanese": "nan-desu",
            "Korean": "mwo-eyo",
            "Mandarin": "shi-shenme",
        }
        return language_tags.get(language, "vocabulary-definition")

    def set_vocabulary_deck(self, deck_id: int):
        """Optionally override the vocabulary deck ID to monitor."""
        try:
            self.vocab_deck_id = int(deck_id)
            logger.info(f"Vocabulary deck set to {self.vocab_deck_id}")
        except Exception as e:
            logger.warning(f"Invalid vocabulary deck id {deck_id}: {e}")

    def _check_sdk_availability(self):
        """Check if Claude Code SDK is available"""
        try:
            import claude_code_sdk
            self.claude_sdk_available = True
            logger.info("Claude Code SDK is available")
        except ImportError:
            logger.warning("Claude Code SDK not available")
            self.claude_sdk_available = False

    async def _get_context_instructions(self) -> str:
        """Load full define-with-context instructions and augment with explicit parallel/subagent + card template rules"""
        try:
            # Use current working directory to find .claude/commands relative to where anki-chat-web was run
            cwd = os.getcwd()
            commands_path = os.path.join(cwd, '.claude', 'commands', 'define-with-context.md')
            with open(commands_path, 'r') as f:
                content = f.read()

            # Append explicit directives we require for this integration
            instructions = content + f"""

ADDITIONAL SYSTEM DIRECTIVES (ENFORCED):

CRITICAL INSTRUCTIONS FOR WORD DEFINITION:

1. **CONTEXT SOURCE IDENTIFICATION**:
   - The word appeared in the provided card context
   - Use ONLY {self.target_language} in context descriptions
   - NO {self.banned_language} summaries or explanations

2. **DEFINITION REQUIREMENTS**:
   - **CRITICAL: DEFINE THE LEMMA/STEM, NOT CONJUGATIONS**
     - Always define the base form/root/stem of the word (the lemma)
     - Do NOT define conjugated forms, inflections, or derived forms
     - Example: If asked to define "mentek", define "menni" (the infinitive lemma)
     - Example: If asked to define "szép", define "szép" (the base adjective)
     - Example: If asked to define "házak", define "ház" (the singular noun)
     - Example: If asked to define "olvastam", define "olvasni" (the infinitive)
   - Use ONLY {self.target_language} words from basic A1 Vocabulary
   - Use creative definitions with emojis, symbols, mathematical notation
   - Create multiple definitions/approaches
   - AVOID {self.banned_language} loan words
   - Mix strategies - not 100% emojis

3. **MANDATORY ANKI CARD CREATION**:
   After creating each definition, you MUST create an Anki card using this EXACT format:

   **DECK SELECTION**:
   - If VOCABULARY_DECK_ID is provided in the prompt, use that deck_id
   - Otherwise, use deck_id: 1 as default

   Call mcp__anki-api__create_card with:
   - username: "chase"
   - note_type: "{self.target_language} Vocabulary Note"
   - deck_id: [USE_VOCABULARY_DECK_ID_FROM_PROMPT_OR_1]
   - fields: {{
       "Word": "[THE_LEMMA_BASE_FORM_ONLY]",
       "Definition": "[YOUR_CREATIVE_DEFINITION_WITH_HTML_BR_TAGS]",
       "Grammar Code": "[IF_APPLICABLE_FROM_CONTEXT]",
       "Example Sentence": "[CREATE_EXAMPLE_USING_THE_LEMMA_BASE_FORM]"
   }}
   - tags: ["vocabulary", "{self.vocabulary_tag}", "from-context", "[USE_LAYER_TAG_FROM_PROMPT_IF_PROVIDED]"]

4. **CARD TEMPLATE REQUIREMENTS**:
   - Word field: Only the {self.target_language} word (no {self.banned_language} ever)
   - Definition field: Your creative explanation with HTML <br> tags for line breaks
   - Grammar Code: Include if the word has grammatical significance from context
   - Example Sentence: Create ONE example sentence using the word
   - NEVER query for note types or deck information - use the provided template

5. **IMPORTANT**:
   - Create ONE card per word
   - Follow Role 2 creative definition principles from the instructions
   - Use the provided deck_id and note_type exactly as specified
   - Do not attempt to discover or query for card templates

6. **PARALLEL SUBAGENTS REQUIRED**:
   - Spawn a dedicated subagent for EACH word to define the word in parallel.
   - Each subagent must produce a rich, multi-approach {self.target_language} definition (3–5 variants), mixing emojis, symbols, and minimal math where appropriate.
   - Subagents must independently call mcp__anki-api__create_card for their word when ready.
   - Do not serialize; run subagents concurrently so all words are processed quickly.
"""
            return instructions
        except FileNotFoundError:
            logger.warning("define-with-context.md not found, using default instructions")
            return f"Define the word creatively using only {self.target_language}, with emojis and symbols."

    async def start_grammar_session(self, deck_id: int) -> Dict[str, Any]:
        """Start main grammar study session"""
        try:
            # Start study session using AnkiClient
            from AnkiClient.src.operations.study_ops import study

            session_result, status_code = study(
                deck_id=deck_id,
                action="start",
                username="chase"
            )

            if status_code == 200 and session_result.get('card_id'):
                self.grammar_session = StudySessionState(
                    session_id=f"session_{deck_id}_{int(time.time())}",
                    deck_id=deck_id,
                    current_card=session_result
                )

                # Reset vocabulary queue state before polling
                try:
                    self.vocabulary_queue.queue.clear()
                    self.vocabulary_queue.card_answer_mapping.clear()
                    self.vocabulary_queue.seen_card_ids.clear()
                    self.vocabulary_queue.in_progress_ids.clear()
                    self.vocab_initialized = False
                except Exception:
                    pass

                # Seed seen IDs synchronously to exclude all existing cards in default deck (1)
                # But DON'T start polling automatically - only poll when user requests definitions
                try:
                    from AnkiClient.src.operations.deck_ops import get_cards_in_deck
                    existing_cards = get_cards_in_deck(deck_id=self.vocab_deck_id, username="chase")
                    if isinstance(existing_cards, list):
                        self.vocabulary_queue.record_initial_cards(existing_cards)
                        logger.info(
                            f"Seeded {len(self.vocabulary_queue.seen_card_ids)} existing cards (polling will start when definitions are requested)"
                        )
                except Exception as e:
                    logger.warning(f"Synchronous vocabulary seeding failed: {e}")

                # NOTE: Polling is NOT started automatically anymore to avoid collection lock conflicts
                # Polling will be started only when the user requests word definitions

                return {
                    'success': True,
                    'session_id': self.grammar_session.session_id,
                    'current_card': self.grammar_session.current_card
                }
            else:
                return {'success': False, 'error': 'Failed to start study session'}

        except Exception as e:
            logger.error(f"Error starting grammar session: {e}")
            return {'success': False, 'error': str(e)}

    async def _start_vocabulary_polling(self):
        """Start polling for new vocabulary cards in default deck"""
        if self.polling_active:
            return

        self.polling_active = True
        asyncio.create_task(self._poll_vocabulary_cards())

    async def _poll_vocabulary_cards(self):
        """Poll for new vocabulary cards using tag-based filtering"""
        logger.info("Starting tag-based vocabulary card polling...")
        # Don't reset words_in_current_layer - it should be set by the definition request
        # self.current_layer_tag = None
        # self.words_in_current_layer = 0
        self.cards_processed_in_current_layer = 0

        while self.polling_active:
            try:
                # Check if polling was stopped (important for breaking out after session creation)
                if not self.polling_active:
                    logger.info("Polling stopped, exiting poll loop")
                    break

                # DO NOT modify self.current_layer_tag here - it's set by the definition request
                # and should be preserved throughout the polling cycle. The polling should use
                # whatever layer tag was set by request_vocabulary_card_definitions or
                # pause_grammar_session_for_definition.

                # If no current_layer_tag is set, use a fallback (shouldn't happen normally)
                if not self.current_layer_tag:
                    logger.warning("No current_layer_tag set, using fallback from grammar session")
                    if self.grammar_session.current_card:
                        base_note_id = self.grammar_session.current_card.get('note_id')
                        if not base_note_id:
                            card_id = self.grammar_session.current_card.get('card_id')
                            if card_id:
                                try:
                                    from AnkiClient.src.operations.card_ops import get_card_contents
                                    full_card = get_card_contents(card_id=card_id, username="chase")
                                    base_note_id = full_card.get('note_id', 'unknown')
                                    logger.info(f"Polling: Fetched note_id {base_note_id} from card_id {card_id}")
                                except Exception as e:
                                    logger.error(f"Polling: Failed to fetch note_id for card_id {card_id}: {e}")
                                    base_note_id = 'unknown'
                            else:
                                base_note_id = 'unknown'
                        self.current_layer_tag = f"layer_{base_note_id}"
                    else:
                        self.current_layer_tag = "layer_unknown"

                # Poll for cards with the current layer tag that are in 'new' state
                try:
                    from AnkiClient.src.operations.card_ops import get_cards_by_tag_and_state

                    logger.info(f"Polling for tag='{self.current_layer_tag}', state='new', username='chase'")
                    tagged_cards = get_cards_by_tag_and_state(
                        tag=self.current_layer_tag,
                        state="new",
                        username="chase",
                        inclusions=None  # Get all fields
                    )

                    logger.info(f"get_cards_by_tag_and_state returned: {type(tagged_cards)} - {tagged_cards}")
                    logger.info(f"Response details: length={len(tagged_cards) if hasattr(tagged_cards, '__len__') else 'N/A'}")

                    if isinstance(tagged_cards, list) and tagged_cards:
                        found_count = len(tagged_cards)
                        logger.info(f"Found {found_count} cards with tag '{self.current_layer_tag}'")

                        # Check if we have all expected cards for this layer
                        expected_word_count = self.words_in_current_layer

                        # Calculate the total expected cards (initial + new from Claude SDK)
                        total_expected = getattr(self, 'initial_card_count', 0) + expected_word_count

                        # Handle different scenarios for found vs expected cards
                        if expected_word_count == 0:
                            logger.warning(f"Expected word count is 0, waiting for definition request to set proper count")
                        elif found_count >= total_expected:
                            logger.info(f"===== POLLING DETECTED ALL CARDS READY =====")
                            logger.info(f"Expected total cards reached ({found_count}/{total_expected}). Creating custom study session...")
                            logger.info(f"(Initial: {getattr(self, 'initial_card_count', 0)} + New: {expected_word_count} = Total: {total_expected})")
                            logger.info(f"Current layer tag: {self.current_layer_tag}")
                            logger.info(f"About to call _attempt_custom_session_creation()...")
                            await self._attempt_custom_session_creation()
                            logger.info(f"Returned from _attempt_custom_session_creation()")
                            logger.info(f"===== POLLING COMPLETE =====")
                            # IMPORTANT: Stop polling immediately after creating session to avoid collection lock conflicts
                            # The polling loop will exit naturally on next iteration check
                            break
                        else:
                            remaining_cards = total_expected - found_count
                            logger.info(f"Waiting for more cards ({found_count}/{total_expected}). Need {remaining_cards} more cards from Claude SDK.")

                except ImportError as e:
                    # Fallback to old polling method if tag-based function not available
                    logger.warning(f"Tag-based polling not available, falling back to deck polling: {e}")
                    await self._fallback_poll_vocabulary_cards()
                    return

                # Check if current layer is complete
                await self._check_layer_completion()

                # Wait before next poll (3 seconds)
                await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"Error in tag-based vocabulary polling: {e}")
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception details: {str(e)}")
                logger.error(f"Current layer tag: {self.current_layer_tag}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(5)  # Wait longer on error

    async def _fallback_poll_vocabulary_cards(self):
        """Fallback polling method for when tag-based filtering is not available"""
        logger.info("Using fallback vocabulary card polling...")
        last_card_count = 0

        # On first run, seed seen_card_ids with current deck contents
        try:
            from AnkiClient.src.operations.deck_ops import get_cards_in_deck
            existing_cards = get_cards_in_deck(deck_id=self.vocab_deck_id, username="chase")
            if isinstance(existing_cards, list):
                self.vocabulary_queue.record_initial_cards(existing_cards)
                last_card_count = len(existing_cards)
        except Exception as e:
            logger.warning(f"Initial vocabulary seeding failed: {e}")

        while self.polling_active:
            try:
                # Get current cards in vocabulary deck
                from AnkiClient.src.operations.deck_ops import get_cards_in_deck

                deck_cards = get_cards_in_deck(
                    deck_id=self.vocab_deck_id,
                    username="chase"
                )

                if isinstance(deck_cards, list):
                    # On first loop after start, seed only; do not enqueue
                    if not self.vocab_initialized:
                        self.vocabulary_queue.record_initial_cards(deck_cards)
                        self.vocab_initialized = True
                    else:
                        # Identify truly new cards by unseen IDs
                        new_count = 0
                        for card in deck_cards:
                            cid = self.vocabulary_queue._extract_card_id(card) if isinstance(card, dict) else None
                            if cid is None:
                                continue
                            cid = int(cid)
                            if cid not in self.vocabulary_queue.seen_card_ids:
                                self.vocabulary_queue.seen_card_ids.add(cid)
                                self.vocabulary_queue.add_new_card(card)
                                new_count += 1

                        if new_count > 0:
                            logger.info(f"Detected {new_count} new vocabulary cards by ID (fallback method)")

                # Wait before next poll (5 seconds)
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Error in fallback vocabulary polling: {e}")
                await asyncio.sleep(10)

    async def _check_layer_completion(self):
        """Check if the current layer's vocabulary cards have been processed"""
        if self.current_layer_tag and self.words_in_current_layer > 0:
            # Count cards processed in current layer
            processed_in_layer = sum(1 for card_id in self.vocabulary_queue.card_answer_mapping.keys()
                                   if self._card_has_layer_tag(card_id, self.current_layer_tag))

            # Check if all expected cards for this layer have been processed
            if processed_in_layer >= self.words_in_current_layer:
                logger.info(f"Layer {self.current_layer_tag} complete: {processed_in_layer}/{self.words_in_current_layer} cards processed")

                # Get actual card count from the vocabulary deck with this layer tag to verify completion
                try:
                    from AnkiClient.src.operations.card_ops import get_cards_by_tag_and_state

                    actual_cards_in_layer = get_cards_by_tag_and_state(
                        tag=self.current_layer_tag,
                        state="new",  # Check remaining unprocessed cards
                        username="chase",
                        inclusions=['id']  # Only get IDs for counting
                    )

                    if isinstance(actual_cards_in_layer, list):
                        remaining_cards = len(actual_cards_in_layer)
                        total_expected = self.words_in_current_layer

                        # Layer is truly complete when no cards remain or all expected cards have been processed
                        if remaining_cards == 0 or processed_in_layer >= total_expected:
                            logger.info(f"Layer {self.current_layer_tag} fully verified complete: {processed_in_layer}/{total_expected} processed, {remaining_cards} remaining")

                            # Reset for next layer
                            self.current_layer_tag = None
                            self.words_in_current_layer = 0
                            self.cards_processed_in_current_layer = 0
                        else:
                            logger.info(f"Layer {self.current_layer_tag} progress: {processed_in_layer}/{total_expected} processed, {remaining_cards} still in deck")

                except ImportError:
                    # Fallback: assume completion based on processed count
                    logger.info(f"Layer {self.current_layer_tag} complete (fallback): {processed_in_layer}/{self.words_in_current_layer} cards processed")
                    self.current_layer_tag = None
                    self.words_in_current_layer = 0
                    self.cards_processed_in_current_layer = 0

    def is_current_layer_complete(self) -> bool:
        """Check if the current layer is complete based on word count comparison"""
        if not self.current_layer_tag or self.words_in_current_layer == 0:
            return True  # No active layer, considered complete

        processed_in_layer = sum(1 for card_id in self.vocabulary_queue.card_answer_mapping.keys()
                               if self._card_has_layer_tag(card_id, self.current_layer_tag))

        return processed_in_layer >= self.words_in_current_layer

    def _card_has_layer_tag(self, card_id: int, layer_tag: str) -> bool:
        """Check if a card has a specific layer tag (placeholder for future implementation)"""
        # This would require access to card tag information
        # For now, we'll use a simplified approach
        return True  # Simplified - in real implementation would check actual tags

    async def pause_grammar_session_for_definition(self, words: List[str], layer_tag: str = None) -> Dict[str, Any]:
        """Pause grammar session and request word definitions from Claude SDK"""
        if not self.claude_sdk_available:
            return {'success': False, 'error': 'Claude Code SDK not available'}

        try:
            # Mark session as paused (study session already closed by web UI)
            self.grammar_session.is_paused = True

            # Get current card context
            current_card = self.grammar_session.current_card
            if not current_card:
                return {'success': False, 'error': 'No current card available for context'}

            # Generate layer tag from current card if not provided
            if not layer_tag:
                # Get note_id from card - if not present, fetch it using card_id
                base_note_id = current_card.get('note_id')
                if not base_note_id:
                    card_id = current_card.get('card_id')
                    if card_id:
                        try:
                            from AnkiClient.src.operations.card_ops import get_card_contents
                            full_card = get_card_contents(card_id=card_id, username="chase")
                            base_note_id = full_card.get('note_id', 'unknown')
                            logger.info(f"Fetched note_id {base_note_id} from card_id {card_id}")
                        except Exception as e:
                            logger.error(f"Failed to fetch note_id for card_id {card_id}: {e}")
                            base_note_id = 'unknown'
                    else:
                        base_note_id = 'unknown'
                layer_tag = f"layer_{base_note_id}"

            # Track word count for this layer
            if not hasattr(self, 'layer_word_counts'):
                self.layer_word_counts = {}
            self.layer_word_counts[layer_tag] = len(words)
            self.words_in_current_layer = len(words)

            # Set current_layer_tag so polling uses the correct tag
            self.current_layer_tag = layer_tag

            # Get initial card count for this layer tag before Claude SDK starts
            try:
                from AnkiClient.src.operations.card_ops import get_cards_by_tag_and_state
                initial_cards = get_cards_by_tag_and_state(
                    tag=layer_tag,
                    state="new",
                    username="chase",
                    inclusions=['id']  # Only get IDs for counting
                )
                if isinstance(initial_cards, list):
                    self.initial_card_count = len(initial_cards)
                    logger.info(f"Starting new layer {layer_tag} with {len(words)} words, initial cards present: {self.initial_card_count}")
                else:
                    self.initial_card_count = 0
                    logger.info(f"Starting new layer {layer_tag} with {len(words)} words, no initial cards found")
            except Exception as e:
                self.initial_card_count = 0
                logger.warning(f"Failed to get initial card count for layer {layer_tag}: {e}")

            # START POLLING NOW - only when user requests word definitions
            await self._start_vocabulary_polling()

            # Prepare context from current card
            card_context = self._prepare_card_context(current_card)

            # Get context instructions
            instructions = await self._get_context_instructions()
            instructions += "\n\n**IMPORTANT**: The study session has been closed by the web UI to allow card creation. You can now create Anki cards without restrictions."

            # Send to Claude Code SDK with layer tag and vocabulary deck ID
            definition_result = await self._request_definitions_from_claude_sdk(
                words, card_context, instructions, layer_tag, self.vocab_deck_id
            )

            return {
                'success': True,
                'definition_request_id': definition_result.get('request_id'),
                'session_paused': True,
                'layer_tag': definition_result.get('layer_tag'),
                'vocab_deck_id': definition_result.get('vocab_deck_id'),
                'word_count': len(words)
            }

        except Exception as e:
            logger.error(f"Error pausing session for definitions: {e}")
            return {'success': False, 'error': str(e)}

    async def request_vocabulary_card_definitions(self, words: List[str], vocab_card: Dict[str, Any]) -> Dict[str, Any]:
        """Request word definitions from a vocabulary card context with nested layer tags"""
        if not self.claude_sdk_available:
            return {'success': False, 'error': 'Claude Code SDK not available'}

        try:
            # Get the current vocabulary card context
            if not vocab_card:
                return {'success': False, 'error': 'No vocabulary card available for context'}

            # Generate nested layer tag based on current grammar layer + vocab card note_id
            base_layer_tag = self.current_layer_tag or "layer_unknown"

            # Get note_id from vocab card - if not present, fetch it using card_id
            vocab_note_id = vocab_card.get('note_id')
            if not vocab_note_id:
                card_id = vocab_card.get('card_id') or vocab_card.get('id')
                if card_id:
                    try:
                        from AnkiClient.src.operations.card_ops import get_card_contents
                        full_card = get_card_contents(card_id=card_id, username="chase")
                        vocab_note_id = full_card.get('note_id', 'unknown')
                        logger.info(f"Nested vocab: Fetched note_id {vocab_note_id} from card_id {card_id}")
                    except Exception as e:
                        logger.error(f"Nested vocab: Failed to fetch note_id for card_id {card_id}: {e}")
                        vocab_note_id = 'unknown'
                else:
                    vocab_note_id = 'unknown'

            nested_layer_tag = f"{base_layer_tag}_{vocab_note_id}"

            logger.info(f"Starting nested layer {nested_layer_tag} from vocabulary card with {len(words)} words")

            # Track word count for the nested layer
            if not hasattr(self, 'layer_word_counts'):
                self.layer_word_counts = {}
            self.layer_word_counts[nested_layer_tag] = len(words)

            # Update current layer to nested layer
            prev_layer_tag = self.current_layer_tag
            self.current_layer_tag = nested_layer_tag
            self.words_in_current_layer = len(words)

            # Get initial card count for this nested layer tag before Claude SDK starts
            try:
                from AnkiClient.src.operations.card_ops import get_cards_by_tag_and_state
                initial_cards = get_cards_by_tag_and_state(
                    tag=nested_layer_tag,
                    state="new",
                    username="chase",
                    inclusions=['id']  # Only get IDs for counting
                )
                if isinstance(initial_cards, list):
                    self.initial_card_count = len(initial_cards)
                    logger.info(f"Starting nested layer {nested_layer_tag} with {len(words)} words, initial cards present: {self.initial_card_count}")
                else:
                    self.initial_card_count = 0
                    logger.info(f"Starting nested layer {nested_layer_tag} with {len(words)} words, no initial cards found")
            except Exception as e:
                self.initial_card_count = 0
                logger.warning(f"Failed to get initial card count for nested layer {nested_layer_tag}: {e}")

            # RESTART POLLING for the nested layer - stop any existing poll and start fresh
            # This ensures we're polling for the correct nested layer tag
            if self.polling_active:
                logger.info(f"Stopping existing polling for layer {prev_layer_tag}")
                self.polling_active = False
                # Give it a moment to stop
                await asyncio.sleep(0.5)

            logger.info(f"Starting polling for nested layer {nested_layer_tag}")
            await self._start_vocabulary_polling()

            # Prepare context from vocabulary card
            vocab_context = self._prepare_card_context(vocab_card)

            # Get context instructions with vocabulary-specific additions
            instructions = await self._get_context_instructions()
            instructions += "\n\n**IMPORTANT**: This is a nested definition request from a vocabulary card."

            # Send to Claude Code SDK with nested layer tag
            definition_result = await self._request_definitions_from_claude_sdk(
                words, vocab_context, instructions, nested_layer_tag, self.vocab_deck_id
            )

            return {
                'success': True,
                'definition_request_id': definition_result.get('request_id'),
                'layer_tag': definition_result.get('layer_tag'),
                'vocab_deck_id': definition_result.get('vocab_deck_id'),
                'word_count': len(words),
                'nested_layer': True,
                'previous_layer': prev_layer_tag
            }

        except Exception as e:
            logger.error(f"Error requesting vocabulary card definitions: {e}")
            return {'success': False, 'error': str(e)}

    def _prepare_card_context(self, card_data: Dict[str, Any]) -> str:
        """Prepare rich card context for Claude SDK from either front/back or fields structures"""
        context_lines: List[str] = ["KÁRTYA KONTEXTUSA (Card Context):"]

        try:
            if isinstance(card_data, dict):
                # Newer API: separate front/back dicts
                if 'front' in card_data or 'back' in card_data:
                    if card_data.get('front'):
                        context_lines.append("FRONT:")
                        for k, v in card_data['front'].items():
                            if isinstance(v, str) and v.strip():
                                context_lines.append(f"- {k}: {v}")
                    if card_data.get('back'):
                        context_lines.append("BACK:")
                        for k, v in card_data['back'].items():
                            if isinstance(v, str) and v.strip():
                                context_lines.append(f"- {k}: {v}")
                # Legacy: fields dict
                elif 'fields' in card_data:
                    fields = card_data.get('fields', {})
                    for k, v in fields.items():
                        if isinstance(v, str) and v.strip():
                            context_lines.append(f"- {k}: {v}")
                else:
                    # Fallback: dump key/value pairs
                    for k, v in card_data.items():
                        if isinstance(v, str) and v.strip():
                            context_lines.append(f"- {k}: {v}")
        except Exception as e:
            logger.warning(f"Context preparation fallback due to error: {e}")

        return "\n".join(context_lines)

    async def _request_definitions_from_claude_sdk(self, words: List[str], context: str, instructions: str, layer_tag: str = None, vocab_deck_id: int = None) -> Dict[str, Any]:
        """Send definition request to Claude Code SDK"""
        try:
            from claude_code_sdk import query, ClaudeCodeOptions

            # Generate layer tag if not provided - starts with current grammar card's note_id
            if not layer_tag:
                if self.grammar_session.current_card:
                    # Get note_id from card - if not present, fetch it using card_id
                    base_note_id = self.grammar_session.current_card.get('note_id')
                    if not base_note_id:
                        card_id = self.grammar_session.current_card.get('card_id')
                        if card_id:
                            try:
                                from AnkiClient.src.operations.card_ops import get_card_contents
                                full_card = get_card_contents(card_id=card_id, username="chase")
                                base_note_id = full_card.get('note_id', 'unknown')
                                logger.info(f"SDK request: Fetched note_id {base_note_id} from card_id {card_id}")
                            except Exception as e:
                                logger.error(f"SDK request: Failed to fetch note_id for card_id {card_id}: {e}")
                                base_note_id = 'unknown'
                        else:
                            base_note_id = 'unknown'
                    layer_tag = f"layer_{base_note_id}"
                else:
                    layer_tag = "layer_unknown"

            # Prepare the prompt with layer tag and deck information
            deck_info = f"\nVOCABULARY_DECK_ID: {vocab_deck_id}" if vocab_deck_id else ""
            layer_info = f"\nLAYER_TAG: {layer_tag}"

            prompt = f"""
{instructions}

{deck_info}
{layer_info}

KONTEXTUS AHOL EZEK A SZAVAK MEGJELENTEK:
{context}

Kérlek, definiáld ezeket a szavakat kreatívan és hozz létre Anki kártyákat mindegyikhez:
{', '.join(words)}

Használd a define-with-context parancs pontos utasításait és hozz létre minden szóhoz Anki kártyát a mcp__anki-api__create_card függvénnyel.

FUTÁSSTRATÉGIA:
- Minden szóhoz INDÍTSD EL egy külön szubügynököt (subagent) párhuzamosan.
- A szubügynökök NE várjanak egymásra; dolgozzanak egyszerre.
- Minden szubügynök 3–5 különböző, gazdag magyar definíciós megközelítést készítsen, majd hozzon létre 1 kártyát a legjobb szintézis alapján.

FONTOS TAG INFORMÁCIÓ:
- Hozzá kell adni a megadott LAYER_TAG-et minden létrehozott kártyához címként (tag)
- Ha VOCABULARY_DECK_ID meg van adva, abban a pakliban (deck) kell létrehozni a kártyákat
- A layer tag segít nyomon követni, melyik szinten/traversálban jöttek létre a kártyák
"""

            options = ClaudeCodeOptions(
                system_prompt=f"You are a {self.target_language} vocabulary definition expert following the define-with-context command patterns.",
                max_turns=3
            )

            # Send query to Claude SDK
            response_parts = []
            async for message in query(prompt=prompt, options=options):
                response_parts.append(str(message))
                logger.info(f"Claude SDK Response: {message}")

            return {
                'success': True,
                'request_id': f"def_{int(time.time())}",
                'response': "".join(response_parts),
                'layer_tag': layer_tag,
                'vocab_deck_id': vocab_deck_id
            }

        except Exception as e:
            logger.error(f"Error requesting definitions from Claude SDK: {e}")
            return {'success': False, 'error': str(e)}

    async def cache_user_answer(self, card_id: int, answer: int):
        """Cache user answer while waiting for Claude SDK"""
        cached_card = CachedCard(
            card_id=card_id,
            user_answer=answer,
            card_data=self.grammar_session.current_card,
            timestamp=time.time()
        )

        self.grammar_session.cached_cards.append(cached_card)
        logger.info(f"Cached answer {answer} for card {card_id}")

    def _pop_cached_answer_for(self, card_id: int) -> Optional[CachedCard]:
        """Find and remove a cached answer for the given card_id if present."""
        if not self.grammar_session.cached_cards:
            return None
        for idx, cached in enumerate(self.grammar_session.cached_cards):
            if cached.card_id == card_id:
                return self.grammar_session.cached_cards.pop(idx)
        return None

    async def auto_answer_if_current_matches(self, current_card_result: Dict[str, Any]) -> Dict[str, Any]:
        """If the provided current card matches a cached answer, auto-answer it and return the next card.

        Returns a dict with keys:
        - applied (bool): whether an auto-answer was applied
        - next_card (dict|None): the next card result if applied, else None
        """
        try:
            # Determine card_id from result shape
            card_id = current_card_result.get('card_id')
            if not card_id:
                return {"applied": False, "next_card": None}

            cached = self._pop_cached_answer_for(card_id)
            if not cached:
                return {"applied": False, "next_card": None}

            # Apply the cached answer to the current card
            from AnkiClient.src.operations.study_ops import study
            result, _ = study(
                deck_id=self.grammar_session.deck_id,
                action=str(cached.user_answer),
                username="chase"
            )

            # Update current card in session to the newly served card
            if result.get('card_id'):
                self.grammar_session.current_card = result

            logger.info(
                f"Auto-answered matching card {card_id} with answer {cached.user_answer}; advanced to next."
            )
            return {"applied": True, "next_card": result}

        except Exception as e:
            logger.error(f"Error during auto-answer flow: {e}")
            return {"applied": False, "next_card": None}

    async def _close_active_study_session(self):
        """Close active study session to allow card creation"""
        try:
            if self.grammar_session.session_id:
                from AnkiClient.src.operations.study_ops import study

                study(
                    deck_id=self.grammar_session.deck_id,
                    action="close",
                    username="chase"
                )

                logger.info(f"Closed study session {self.grammar_session.session_id} for card creation")

        except Exception as e:
            logger.error(f"Error closing study session: {e}")

    async def _restart_study_session(self) -> Dict[str, Any]:
        """Restart study session after card creation"""
        try:
            from AnkiClient.src.operations.study_ops import study

            result, status_code = study(
                deck_id=self.grammar_session.deck_id,
                action="start",
                username="chase"
            )

            if status_code == 200 and result.get('card_id'):
                self.grammar_session.session_id = f"session_{self.grammar_session.deck_id}_{int(time.time())}"
                self.grammar_session.current_card = result
                logger.info(f"Restarted study session {self.grammar_session.session_id}")

            return result

        except Exception as e:
            logger.error(f"Error restarting study session: {e}")
            return {'success': False, 'error': str(e)}

    async def resume_grammar_session(self) -> Dict[str, Any]:
        """Resume grammar session with auto-answer for cached cards"""
        try:
            # Restart the study session first
            restart_result = await self._restart_study_session()
            if not restart_result.get('card_id'):
                return {'success': False, 'error': 'Failed to restart study session'}

            self.grammar_session.is_paused = False

            # Process cached cards with auto-answers
            for cached_card in self.grammar_session.cached_cards:
                await self._auto_answer_card(cached_card)

            # Clear cached cards
            self.grammar_session.cached_cards.clear()

            # Continue with next card
            return await self._get_next_grammar_card()

        except Exception as e:
            logger.error(f"Error resuming grammar session: {e}")
            return {'success': False, 'error': str(e)}

    async def _auto_answer_card(self, cached_card: CachedCard):
        """Automatically answer a previously cached card"""
        try:
            from AnkiClient.src.operations.study_ops import study

            result, _ = study(
                deck_id=self.grammar_session.deck_id,
                action=str(cached_card.user_answer),
                username="chase"
            )

            logger.info(f"Auto-answered card {cached_card.card_id} with answer {cached_card.user_answer}")
            return result

        except Exception as e:
            logger.error(f"Error auto-answering card {cached_card.card_id}: {e}")

    async def _get_next_grammar_card(self) -> Dict[str, Any]:
        """Get next card in grammar session"""
        try:
            from AnkiClient.src.operations.study_ops import study

            result, _ = study(
                deck_id=self.grammar_session.deck_id,
                action="flip",
                username="chase"
            )

            if result.get('card_id'):
                self.grammar_session.current_card = result

            return result

        except Exception as e:
            logger.error(f"Error getting next grammar card: {e}")
            return {'success': False, 'error': str(e)}

    def get_vocabulary_queue_status(self) -> Dict[str, Any]:
        """Get current vocabulary queue status"""
        queue_length = len(self.vocabulary_queue.queue) + len(self.vocabulary_queue.in_progress_ids)
        logger.debug(f"Vocabulary queue status: queue_length={queue_length}, queue contents: {[card.get('card_id', card.get('id', 'unknown')) for card in self.vocabulary_queue.queue]}")
        return {
            'queue_length': queue_length,
            'cached_answers': len(self.vocabulary_queue.card_answer_mapping),
            'processed_cards': len(self.vocabulary_queue.processed_cards),
            'in_progress': len(self.vocabulary_queue.in_progress_ids)
        }

    def get_next_vocabulary_card(self) -> Optional[Dict[str, Any]]:
        """Get next vocabulary card from LIFO queue with full contents"""
        card = self.vocabulary_queue.get_next_card()
        if not card:
            self.current_vocabulary_card = None
            # Stop polling when no more cards are available - prevents unnecessary API calls
            if self.polling_active:
                logger.info("Stopping polling: no more vocabulary cards in queue")
                self.polling_active = False
            return None

        # Track the current vocabulary card for nested layer generation
        self.current_vocabulary_card = card

        # Get full card contents using card_ops
        try:
            from AnkiClient.src.operations.card_ops import get_card_contents

            card_id = card.get('id') or card.get('card_id')
            if card_id:
                full_card_data = get_card_contents(card_id=card_id, username="chase")
                logger.info(f"Retrieved full contents for vocabulary card {card_id}")
                # Update the current vocabulary card with full data
                self.current_vocabulary_card = full_card_data
                return full_card_data
            else:
                logger.warning("No card ID found, returning original card data")
                return card

        except Exception as e:
            logger.error(f"Error getting vocabulary card contents: {e}")
            return card

    def cache_vocabulary_answer(self, card_id: int, answer: int):
        """Cache vocabulary card answer"""
        self.vocabulary_queue.cache_answer(card_id, answer)

    def requeue_current_vocabulary_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        """Requeue the currently displayed vocabulary card to the top of the LIFO queue."""
        ok = self.vocabulary_queue.requeue_in_progress(card)
        return {"success": ok}

    async def submit_vocabulary_session(self) -> Dict[str, Any]:
        """Submit vocabulary session and start auto-answer session"""
        try:
            if not self.vocabulary_queue.card_answer_mapping:
                return {'success': False, 'error': 'No cached answers to process'}

            # Capture count before processing clears the mapping
            cards_to_process = len(self.vocabulary_queue.card_answer_mapping)

            # Start auto-session for default deck
            auto_session_result = await self._start_auto_vocabulary_session()

            return {
                'success': True,
                'auto_session_started': True,
                'cards_to_process': cards_to_process,
                'processed_count': auto_session_result.get('processed_count', cards_to_process),
                'session_result': auto_session_result
            }

        except Exception as e:
            logger.error(f"Error submitting vocabulary session: {e}")
            return {'success': False, 'error': str(e)}

    async def _start_auto_vocabulary_session(self) -> Dict[str, Any]:
        """Start LIFO layer-by-layer vocabulary study sessions with custom study sessions"""
        try:
            from AnkiClient.src.operations.study_ops import study
            from AnkiClient.src.operations.card_ops import get_cards_by_tag_and_state

            if not self.vocabulary_queue.card_answer_mapping:
                return {'success': False, 'error': 'No cached answers to process'}

            # Group cards by layer tag for LIFO processing
            layer_groups = self._group_cards_by_layer()

            session_id = f"vocab_session_{int(time.time())}"
            total_processed = 0

            # Process layers in LIFO order (most recent first)
            for layer_tag in sorted(layer_groups.keys(), reverse=True):
                logger.info(f"Processing layer: {layer_tag} ({len(layer_groups[layer_tag])} cards)")

                # Create custom study session for this layer
                custom_session_result = await self._create_custom_study_session(layer_tag)

                if not custom_session_result.get('success'):
                    logger.error(f"Failed to create custom study session for layer {layer_tag}")
                    continue

                # Process cards in this layer
                layer_processed = await self._process_layer_cards(layer_groups[layer_tag], layer_tag)
                total_processed += layer_processed

                # Close the custom study session
                await self._close_custom_study_session()

            # Clear processed answers
            self.vocabulary_queue.card_answer_mapping.clear()

            return {
                'success': True,
                'session_id': session_id,
                'processed_count': total_processed,
                'layers_processed': len(layer_groups)
            }

        except Exception as e:
            logger.error(f"Error in LIFO vocabulary session: {e}")
            return {'success': False, 'error': str(e)}

    def _group_cards_by_layer(self) -> Dict[str, List[int]]:
        """Group cached vocabulary cards by their layer tags"""
        layer_groups = {}

        for card_id, answer in self.vocabulary_queue.card_answer_mapping.items():
            # For now, use a simple grouping based on current layer
            # In a full implementation, this would extract actual tags from cards
            if self.current_layer_tag:
                layer_tag = self.current_layer_tag
            else:
                layer_tag = "layer_unknown"

            if layer_tag not in layer_groups:
                layer_groups[layer_tag] = []
            layer_groups[layer_tag].append(card_id)

        return layer_groups

    async def _attempt_custom_session_creation(self):
        """Attempt to create a custom study session and handle retry logic"""
        logger.info(f"===== _attempt_custom_session_creation CALLED =====")
        logger.info(f"Current layer tag: {self.current_layer_tag}")
        logger.info(f"About to call _create_custom_study_session({self.current_layer_tag})...")

        custom_session_result = await self._create_custom_study_session(self.current_layer_tag)

        logger.info(f"_create_custom_study_session returned: {custom_session_result}")

        if custom_session_result.get('success'):
            logger.info(f"===== SESSION CREATION SUCCESS =====")
            logger.info(f"Successfully created and started custom study session for layer {self.current_layer_tag}")
            logger.info(f"Custom deck ID: {custom_session_result.get('custom_deck_id')}")
            logger.info(f"Session ID: {custom_session_result.get('session_id')}")
            logger.info(f"First card: {custom_session_result.get('first_card')}")
            logger.info(f"Stored in self.last_vocabulary_session: {self.last_vocabulary_session}")
            # Stop polling since we've created and started the session
            self.polling_active = False
            logger.info(f"Set polling_active to False")
        else:
            logger.error(f"===== SESSION CREATION FAILED =====")
            logger.error(f"Failed to create custom study session: {custom_session_result.get('error')}")
            # If collection not open, wait and try again
            if "CollectionNotOpen" in str(custom_session_result.get('error', '')):
                logger.info("Collection not open, will retry in next poll cycle")

    async def _create_custom_study_session(self, layer_tag: str) -> Dict[str, Any]:
        """Create a custom study session for cards with a specific layer tag and start studying it"""
        logger.info(f"===== _create_custom_study_session CALLED =====")
        logger.info(f"Layer tag: {layer_tag}")
        try:
            from AnkiClient.src.operations.study_ops import create_custom_study_session, study

            # Parameters for creating custom study session with filtered cards
            custom_study_params = {
                "new_limit_delta": 0,
                "cram": {
                    "kind": "CRAM_KIND_NEW",
                    "card_limit": 100,  # Process all cards in the layer
                    "tags_to_include": [layer_tag],
                    "tags_to_exclude": []
                }
            }

            logger.info(f"Creating custom study session for layer {layer_tag} with params: {custom_study_params}")
            logger.info(f"Vocab deck ID: {self.vocab_deck_id}")

            # Create the custom study session
            response_data, status_code = create_custom_study_session(
                username="chase",
                deck_id=self.vocab_deck_id,
                custom_study_params=custom_study_params
            )

            if status_code != 200:
                logger.error(f"Failed to create custom study session: {response_data}")
                return {'success': False, 'error': str(response_data)}

            # Extract the created deck ID
            created_deck_id = response_data.get('created_deck_id')

            if not created_deck_id:
                logger.error("No deck ID returned for custom study session")
                return {'success': False, 'error': 'No deck ID returned'}

            logger.info(f"Custom study session created with deck ID: {created_deck_id}")

            # Start a study session with the new custom deck
            study_result, study_status = study(
                deck_id=created_deck_id,
                action="start",
                username="chase"
            )

            if study_status == 200 and study_result.get('card_id'):
                logger.info(f"===== STUDY SESSION STARTED SUCCESSFULLY =====")
                logger.info(f"Successfully started study session for custom deck {created_deck_id}")
                logger.info(f"Study result: {study_result}")

                # Fetch note_id if not present in study_result
                card_id = study_result.get('card_id')
                note_id = study_result.get('note_id')
                logger.info(f"Fetching note_id: card_id={card_id}, note_id={note_id}")
                if not note_id and card_id:
                    try:
                        from AnkiClient.src.operations.card_ops import get_card_contents
                        full_card = get_card_contents(card_id=card_id, username="chase")
                        note_id = full_card.get('note_id')
                        logger.info(f"Fetched note_id {note_id} for vocabulary card {card_id}")
                    except Exception as e:
                        logger.warning(f"Failed to fetch note_id for card {card_id}: {e}")
                        note_id = None

                # Add note_id to first_card
                first_card_with_note_id = {**study_result}
                if note_id:
                    first_card_with_note_id['note_id'] = note_id

                logger.info(f"Building session_info dict...")
                session_info = {
                    'success': True,
                    'custom_deck_id': created_deck_id,
                    'session_id': f"custom_session_{created_deck_id}_{int(time.time())}",
                    'first_card': first_card_with_note_id,
                    'layer_tag': layer_tag
                }
                logger.info(f"Session info built: {session_info}")
                logger.info(f"===== STORING SESSION INFO IN self.last_vocabulary_session =====")
                # Store session info for frontend retrieval
                self.last_vocabulary_session = session_info
                logger.info(f"STORED! Verifying: self.last_vocabulary_session = {self.last_vocabulary_session}")
                # Update current_layer_tag to the session's layer so nested definitions work correctly
                self.current_layer_tag = layer_tag
                logger.info(f"Updated current_layer_tag to: {layer_tag}")
                logger.info(f"===== SESSION INFO STORAGE COMPLETE =====")
                return session_info
            else:
                logger.error(f"Failed to start study session for custom deck: {study_result}")
                return {'success': False, 'error': f"Failed to start study session: {study_result}"}

        except Exception as e:
            logger.error(f"Error creating custom study session for layer {layer_tag}: {e}")
            return {'success': False, 'error': str(e)}

    async def _process_layer_cards(self, card_ids: List[int], layer_tag: str) -> int:
        """Process all cards in a layer using their cached answers"""
        try:
            from AnkiClient.src.operations.study_ops import study

            processed_count = 0

            for card_id in card_ids:
                try:
                    answer = self.vocabulary_queue.card_answer_mapping.get(card_id)
                    if answer is None:
                        continue

                    # Submit the cached answer
                    result, status_code = study(
                        deck_id=self.vocab_deck_id,
                        action=str(answer),
                        username="chase"
                    )

                    if status_code == 200 and not result.get('error'):
                        processed_count += 1
                        logger.info(f"Processed vocabulary card {card_id} in layer {layer_tag} with answer {answer}")
                    else:
                        logger.warning(f"Failed to process card {card_id}: {result.get('error', 'Unknown error')}")

                except Exception as e:
                    logger.error(f"Error processing card {card_id} in layer {layer_tag}: {e}")

            return processed_count

        except Exception as e:
            logger.error(f"Error processing layer {layer_tag}: {e}")
            return 0

    async def _close_custom_study_session(self):
        """Close the current custom study session"""
        try:
            from AnkiClient.src.operations.study_ops import study

            # Close any active study session
            study(
                deck_id=self.vocab_deck_id,
                action="close",
                username="chase"
            )

            logger.info("Closed custom study session")

        except Exception as e:
            logger.error(f"Error closing custom study session: {e}")

    async def cleanup(self):
        """Clean up resources and close active study sessions"""
        self.polling_active = False

        # Close active grammar study session if one exists
        if hasattr(self, 'grammar_session') and self.grammar_session and self.grammar_session.session_id:
            try:
                from AnkiClient.src.operations.study_ops import study
                study(
                    deck_id=self.grammar_session.deck_id,
                    action="close",
                    username="chase"
                )
                logger.info(f"Closed active grammar study session {self.grammar_session.session_id}")
            except Exception as e:
                logger.error(f"Error closing grammar study session: {e}")

        # Reset session state
        if hasattr(self, 'grammar_session'):
            self.grammar_session = StudySessionState("", 0)

        logger.info("Claude SDK Integration cleanup completed")


# Factory function to create integration instance
def create_claude_sdk_integration(anki_client, target_language: str = "Hungarian", banned_language: str = "English"):
    """Create and return Claude SDK integration instance"""
    return ClaudeSDKIntegration(anki_client, target_language, banned_language)
