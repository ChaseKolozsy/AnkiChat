#!/usr/bin/env python3.10
"""
Claude Code SDK Integration Module
Handles Claude Code SDK interactions for AnkiChat with context-aware word definitions
"""

import asyncio
import json
import logging
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
            # Mark it as seen and put back on top if not already queued
            if not any((self._extract_card_id(c) == cid) for c in self.queue):
                self.queue.appendleft(card)
            return True
        return False


class ClaudeSDKIntegration:
    """Main Claude Code SDK integration class"""

    def __init__(self, anki_client):
        self.anki_client = anki_client
        self.grammar_session = StudySessionState("", 0)
        self.vocabulary_queue = VocabularyQueueManager()
        self.polling_active = False
        self.claude_sdk_available = False
        # Deck to monitor for new vocabulary cards (default Anki deck id: 1)
        self.vocab_deck_id: int = 1
        # Poller initialization guard: first pass seeds without enqueuing
        self.vocab_initialized: bool = False
        self._check_sdk_availability()

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
        """Load context instructions from define-with-context command with card template"""
        try:
            with open('/home/chase/AnkiChat/.claude/commands/define-with-context.md', 'r') as f:
                content = f.read()

            # Extract the relevant instruction sections and add card template
            instructions = """
CRITICAL INSTRUCTIONS FOR WORD DEFINITION:

1. **CONTEXT SOURCE IDENTIFICATION**:
   - The word appeared in the provided card context
   - Use ONLY Hungarian in context descriptions
   - NO English summaries or explanations

2. **DEFINITION REQUIREMENTS**:
   - Use ONLY Hungarian words from Pimsleur Level 1 vocabulary
   - Use creative definitions with emojis, symbols, mathematical notation
   - Create multiple definitions/approaches
   - AVOID English loan words (komputer→számítógép, hotel→szálloda)
   - Mix strategies - not 100% emojis

3. **MANDATORY ANKI CARD CREATION**:
   After creating each definition, you MUST create an Anki card using this EXACT format:

   **DO NOT QUERY FOR NOTE TYPES OR DECKS** - Use these provided values:

   Call mcp__anki-api__create_card with:
   - username: "chase"
   - note_type: "Hungarian Vocabulary Note"
   - deck_id: 1756509006667
   - fields: {
       "Word": "[THE_HUNGARIAN_WORD_ONLY]",
       "Definition": "[YOUR_CREATIVE_DEFINITION_WITH_HTML_BR_TAGS]",
       "Grammar Code": "[IF_APPLICABLE_FROM_CONTEXT]",
       "Example Sentence": "[CREATE_EXAMPLE_USING_THE_WORD]"
   }
   - tags: ["vocabulary", "mit-jelent", "from-context"]

4. **CARD TEMPLATE REQUIREMENTS**:
   - Word field: Only the Hungarian word (no English ever)
   - Definition field: Your creative explanation with HTML <br> tags for line breaks
   - Grammar Code: Include if the word has grammatical significance from context
   - Example Sentence: Create ONE example sentence using the word
   - NEVER query for note types or deck information - use the provided template

5. **IMPORTANT**:
   - Create ONE card per word
   - Follow Role 2 creative definition principles from the instructions
   - Use the provided deck_id and note_type exactly as specified
   - Do not attempt to discover or query for card templates
"""
            return instructions
        except FileNotFoundError:
            logger.warning("define-with-context.md not found, using default instructions")
            return "Define the word creatively using only Hungarian, with emojis and symbols."

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
                try:
                    from AnkiClient.src.operations.deck_ops import get_cards_in_deck
                    existing_cards = get_cards_in_deck(deck_id=self.vocab_deck_id, username="chase")
                    if isinstance(existing_cards, list):
                        self.vocabulary_queue.record_initial_cards(existing_cards)
                        logger.info(
                            f"Seeded {len(self.vocabulary_queue.seen_card_ids)} existing cards before starting poll"
                        )
                except Exception as e:
                    logger.warning(f"Synchronous vocabulary seeding failed: {e}")

                # Start vocabulary polling against configured vocab deck
                await self._start_vocabulary_polling()

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
        """Poll for new cards in default deck (ID: 1)"""
        logger.info("Starting vocabulary card polling...")
        last_card_count = 0

        # On first run, seed seen_card_ids with current deck contents so we don't treat them as new
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
                # Get current cards in default deck
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
                            logger.info(f"Detected {new_count} new vocabulary cards by ID")

                # Wait before next poll (5 seconds)
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Error polling vocabulary cards: {e}")
                await asyncio.sleep(10)  # Wait longer on error

    async def pause_grammar_session_for_definition(self, words: List[str]) -> Dict[str, Any]:
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

            # Prepare context from current card
            card_context = self._prepare_card_context(current_card)

            # Get context instructions
            instructions = await self._get_context_instructions()
            instructions += "\n\n**IMPORTANT**: The study session has been closed by the web UI to allow card creation. You can now create Anki cards without restrictions."

            # Send to Claude Code SDK
            definition_result = await self._request_definitions_from_claude_sdk(
                words, card_context, instructions
            )

            return {
                'success': True,
                'definition_request_id': definition_result.get('request_id'),
                'session_paused': True
            }

        except Exception as e:
            logger.error(f"Error pausing session for definitions: {e}")
            return {'success': False, 'error': str(e)}

    def _prepare_card_context(self, card_data: Dict[str, Any]) -> str:
        """Prepare card context for Claude SDK"""
        fields = card_data.get('fields', {})

        context = "KÁRTYA KONTEXTUSA (Card Context):\n"
        context += f"Szó: {fields.get('Word', 'N/A')}\n"
        context += f"Definíció: {fields.get('Definition', 'N/A')}\n"

        if fields.get('Example Sentence'):
            context += f"Példamondat: {fields.get('Example Sentence')}\n"

        if fields.get('Grammar Code'):
            context += f"Nyelvtani kód: {fields.get('Grammar Code')}\n"

        return context

    async def _request_definitions_from_claude_sdk(self, words: List[str], context: str, instructions: str) -> Dict[str, Any]:
        """Send definition request to Claude Code SDK"""
        try:
            from claude_code_sdk import query, ClaudeCodeOptions

            # Prepare the prompt
            prompt = f"""
{instructions}

KONTEXTUS AHOL EZEK A SZAVAK MEGJELENTEK:
{context}

Kérlek, definiáld ezeket a szavakat kreatívan és hozz létre Anki kártyákat mindegyikhez:
{', '.join(words)}

Használd a define-with-context parancs pontos utasításait és hozz létre minden szóhoz Anki kártyát a mcp__anki-api__create_card függvénnyel.
"""

            options = ClaudeCodeOptions(
                system_prompt="You are a Hungarian vocabulary definition expert following the define-with-context command patterns.",
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
                'response': "".join(response_parts)
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
            return None

        # Get full card contents using card_ops
        try:
            from AnkiClient.src.operations.card_ops import get_card_contents

            card_id = card.get('id') or card.get('card_id')
            if card_id:
                full_card_data = get_card_contents(card_id=card_id, username="chase")
                logger.info(f"Retrieved full contents for vocabulary card {card_id}")
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
        """Start automatic vocabulary session with cached answers"""
        try:
            from AnkiClient.src.operations.study_ops import study

            # Start session for default deck (ID: 1)
            session_result, status_code = study(
                deck_id=self.vocab_deck_id,
                action="start",
                username="chase"
            )

            if status_code != 200 or not session_result.get('card_id'):
                return {'success': False, 'error': 'Failed to start auto session'}

            session_id = f"vocab_session_{int(time.time())}"
            processed_count = 0

            # Process each cached answer
            for card_id, answer in self.vocabulary_queue.card_answer_mapping.items():
                try:
                    result, _ = study(
                        deck_id=self.vocab_deck_id,
                        action=str(answer),
                        username="chase"
                    )

                    if not result.get('error'):
                        processed_count += 1
                        logger.info(f"Auto-processed vocabulary card {card_id} with answer {answer}")

                except Exception as e:
                    logger.error(f"Error processing card {card_id}: {e}")

            # Clear processed answers
            self.vocabulary_queue.card_answer_mapping.clear()

            return {
                'success': True,
                'session_id': session_id,
                'processed_count': processed_count
            }

        except Exception as e:
            logger.error(f"Error in auto vocabulary session: {e}")
            return {'success': False, 'error': str(e)}

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
def create_claude_sdk_integration(anki_client):
    """Create and return Claude SDK integration instance"""
    return ClaudeSDKIntegration(anki_client)
