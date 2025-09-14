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

    def add_new_card(self, card_data: Dict[str, Any]):
        """Add new card to front of queue (LIFO)"""
        self.queue.appendleft(card_data)
        logger.info(f"Added new vocabulary card {card_data.get('card_id', 'unknown')} to front of queue")

    def get_next_card(self) -> Optional[Dict[str, Any]]:
        """Get next card from front of queue"""
        if self.queue:
            return self.queue.popleft()
        return None

    def cache_answer(self, card_id: int, answer: int):
        """Cache user answer for auto-session"""
        self.card_answer_mapping[card_id] = answer
        logger.info(f"Cached answer {answer} for card {card_id}")

    def get_cached_answer(self, card_id: int) -> Optional[int]:
        """Get cached answer for card"""
        return self.card_answer_mapping.get(card_id)


class ClaudeSDKIntegration:
    """Main Claude Code SDK integration class"""

    def __init__(self, anki_client):
        self.anki_client = anki_client
        self.grammar_session = StudySessionState("", 0)
        self.vocabulary_queue = VocabularyQueueManager()
        self.polling_active = False
        self.claude_sdk_available = False
        self._check_sdk_availability()

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
            from AnkiClient.src.operations.study_ops import start_study_session

            session_result = await start_study_session(
                self.anki_client,
                deck_id=deck_id,
                username="chase"
            )

            if session_result.get('success'):
                self.grammar_session = StudySessionState(
                    session_id=session_result.get('session_id', ''),
                    deck_id=deck_id,
                    current_card=session_result.get('current_card')
                )

                # Start vocabulary polling
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

        while self.polling_active:
            try:
                # Get current cards in default deck
                from AnkiClient.src.operations.deck_ops import get_deck_cards

                deck_cards = await get_deck_cards(
                    self.anki_client,
                    deck_id=1,  # Default deck
                    username="chase"
                )

                if deck_cards.get('success'):
                    current_count = len(deck_cards.get('cards', []))

                    # Check for new cards
                    if current_count > last_card_count:
                        new_cards = deck_cards['cards'][last_card_count:]
                        for card in new_cards:
                            self.vocabulary_queue.add_new_card(card)

                        logger.info(f"Detected {len(new_cards)} new vocabulary cards")
                        last_card_count = current_count

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

    async def _close_active_study_session(self):
        """Close active study session to allow card creation"""
        try:
            if self.grammar_session.session_id:
                from AnkiClient.src.operations.study_ops import close_study_session

                await close_study_session(
                    self.anki_client,
                    session_id=self.grammar_session.session_id,
                    username="chase"
                )

                logger.info(f"Closed study session {self.grammar_session.session_id} for card creation")

        except Exception as e:
            logger.error(f"Error closing study session: {e}")

    async def _restart_study_session(self) -> Dict[str, Any]:
        """Restart study session after card creation"""
        try:
            from AnkiClient.src.operations.study_ops import start_study_session

            result = await start_study_session(
                self.anki_client,
                deck_id=self.grammar_session.deck_id,
                username="chase"
            )

            if result.get('success'):
                self.grammar_session.session_id = result.get('session_id', '')
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
            if not restart_result.get('success'):
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
            from AnkiClient.src.operations.study_ops import submit_card_answer

            result = await submit_card_answer(
                self.anki_client,
                session_id=self.grammar_session.session_id,
                card_id=cached_card.card_id,
                answer=cached_card.user_answer,
                username="chase"
            )

            logger.info(f"Auto-answered card {cached_card.card_id} with answer {cached_card.user_answer}")
            return result

        except Exception as e:
            logger.error(f"Error auto-answering card {cached_card.card_id}: {e}")

    async def _get_next_grammar_card(self) -> Dict[str, Any]:
        """Get next card in grammar session"""
        try:
            from AnkiClient.src.operations.study_ops import get_next_card

            result = await get_next_card(
                self.anki_client,
                session_id=self.grammar_session.session_id,
                username="chase"
            )

            if result.get('success'):
                self.grammar_session.current_card = result.get('card')

            return result

        except Exception as e:
            logger.error(f"Error getting next grammar card: {e}")
            return {'success': False, 'error': str(e)}

    def get_vocabulary_queue_status(self) -> Dict[str, Any]:
        """Get current vocabulary queue status"""
        return {
            'queue_length': len(self.vocabulary_queue.queue),
            'cached_answers': len(self.vocabulary_queue.card_answer_mapping),
            'processed_cards': len(self.vocabulary_queue.processed_cards)
        }

    def get_next_vocabulary_card(self) -> Optional[Dict[str, Any]]:
        """Get next vocabulary card from LIFO queue"""
        return self.vocabulary_queue.get_next_card()

    def cache_vocabulary_answer(self, card_id: int, answer: int):
        """Cache vocabulary card answer"""
        self.vocabulary_queue.cache_answer(card_id, answer)

    async def submit_vocabulary_session(self) -> Dict[str, Any]:
        """Submit vocabulary session and start auto-answer session"""
        try:
            if not self.vocabulary_queue.card_answer_mapping:
                return {'success': False, 'error': 'No cached answers to process'}

            # Start auto-session for default deck
            auto_session_result = await self._start_auto_vocabulary_session()

            return {
                'success': True,
                'auto_session_started': True,
                'cards_to_process': len(self.vocabulary_queue.card_answer_mapping),
                'session_result': auto_session_result
            }

        except Exception as e:
            logger.error(f"Error submitting vocabulary session: {e}")
            return {'success': False, 'error': str(e)}

    async def _start_auto_vocabulary_session(self) -> Dict[str, Any]:
        """Start automatic vocabulary session with cached answers"""
        try:
            from AnkiClient.src.operations.study_ops import start_study_session, submit_card_answer

            # Start session for default deck (ID: 1)
            session_result = await start_study_session(
                self.anki_client,
                deck_id=1,
                username="chase"
            )

            if not session_result.get('success'):
                return {'success': False, 'error': 'Failed to start auto session'}

            session_id = session_result.get('session_id')
            processed_count = 0

            # Process each cached answer
            for card_id, answer in self.vocabulary_queue.card_answer_mapping.items():
                try:
                    result = await submit_card_answer(
                        self.anki_client,
                        session_id=session_id,
                        card_id=card_id,
                        answer=answer,
                        username="chase"
                    )

                    if result.get('success'):
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
        """Clean up resources"""
        self.polling_active = False
        logger.info("Claude SDK Integration cleanup completed")


# Factory function to create integration instance
def create_claude_sdk_integration(anki_client):
    """Create and return Claude SDK integration instance"""
    return ClaudeSDKIntegration(anki_client)