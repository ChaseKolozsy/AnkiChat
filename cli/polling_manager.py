"""
Polling manager with timeout and retry capabilities

Handles vocabulary card detection with configurable timeouts and manual retries.
"""

import time
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PollConfig:
    """Configuration for polling behavior"""
    timeout_seconds: int = 60  # Total polling timeout
    poll_interval_seconds: float = 2.0  # Time between polls
    max_retries: int = 3  # Max manual retry attempts


@dataclass
class PollState:
    """Tracks the state of a polling operation"""
    start_time: float = field(default_factory=time.time)
    last_check_time: float = field(default_factory=time.time)
    poll_count: int = 0
    retry_count: int = 0
    timed_out: bool = False
    completed: bool = False
    error: Optional[str] = None
    baseline_card_ids: set = field(default_factory=set)
    detected_new_ids: set = field(default_factory=set)


class PollingManager:
    """
    Manages polling operations with timeout and retry capability

    This ensures:
    - Polls don't run forever if cards aren't created
    - User can manually retry after timeout
    - Fresh baseline comparison on each retry
    """

    def __init__(self, config: Optional[PollConfig] = None):
        self.config = config or PollConfig()
        self.state = PollState()

    def reset(self):
        """Reset poll state for a new polling session"""
        self.state = PollState()
        logger.info("Polling state reset")

    def record_baseline(self, card_ids: set):
        """
        Record baseline card IDs before starting to poll

        Args:
            card_ids: Set of card IDs currently in the deck
        """
        self.state.baseline_card_ids = set(card_ids)
        logger.info(f"Recorded baseline: {len(card_ids)} cards")

    def check_for_new_cards(self, current_card_ids: set) -> List[int]:
        """
        Check if new cards have appeared since baseline

        Args:
            current_card_ids: Current set of card IDs in deck

        Returns:
            List of new card IDs that weren't in baseline
        """
        new_ids = current_card_ids - self.state.baseline_card_ids

        if new_ids:
            self.state.detected_new_ids.update(new_ids)
            logger.info(f"Detected {len(new_ids)} new card(s): {new_ids}")

        return sorted(list(new_ids))

    def should_continue_polling(self) -> tuple[bool, str]:
        """
        Determine if polling should continue

        Returns:
            (should_continue, reason)
        """
        if self.state.completed:
            return False, "Polling completed"

        if self.state.timed_out:
            return False, "Polling timed out"

        elapsed = time.time() - self.state.start_time
        if elapsed >= self.config.timeout_seconds:
            self.state.timed_out = True
            return False, f"Timeout after {elapsed:.1f}s"

        return True, f"Continue polling ({elapsed:.1f}s elapsed)"

    def wait_poll_interval(self):
        """Wait for the configured poll interval"""
        time.sleep(self.config.poll_interval_seconds)
        self.state.last_check_time = time.time()
        self.state.poll_count += 1

    def mark_completed(self):
        """Mark polling as successfully completed"""
        self.state.completed = True
        elapsed = time.time() - self.state.start_time
        logger.info(f"Polling completed after {elapsed:.1f}s, {self.state.poll_count} checks")

    def can_retry(self) -> tuple[bool, str]:
        """
        Check if manual retry is allowed

        Returns:
            (can_retry, reason)
        """
        if self.state.retry_count >= self.config.max_retries:
            return False, f"Max retries ({self.config.max_retries}) reached"

        if not self.state.timed_out:
            return False, "Polling hasn't timed out yet"

        return True, f"Retry {self.state.retry_count + 1}/{self.config.max_retries} available"

    def retry(self):
        """Start a new retry attempt"""
        self.state.retry_count += 1
        self.state.start_time = time.time()
        self.state.last_check_time = time.time()
        self.state.poll_count = 0
        self.state.timed_out = False
        self.state.error = None
        logger.info(f"Starting retry {self.state.retry_count}/{self.config.max_retries}")

    def get_status_summary(self) -> Dict[str, Any]:
        """Get current polling status for display"""
        elapsed = time.time() - self.state.start_time
        remaining = max(0, self.config.timeout_seconds - elapsed)

        return {
            'elapsed_seconds': round(elapsed, 1),
            'remaining_seconds': round(remaining, 1),
            'poll_count': self.state.poll_count,
            'retry_count': self.state.retry_count,
            'timed_out': self.state.timed_out,
            'completed': self.state.completed,
            'baseline_cards': len(self.state.baseline_card_ids),
            'new_cards_detected': len(self.state.detected_new_ids),
            'can_retry': self.can_retry()[0]
        }


class VocabularyCardDetector:
    """
    Detects new vocabulary cards by comparing deck snapshots

    Works independently of polling loop - can be used for manual checks
    """

    def __init__(self, get_cards_fn: Callable[[int, str], List[Dict[str, Any]]]):
        """
        Args:
            get_cards_fn: Function to fetch cards from deck (deck_id, username) -> cards
        """
        self.get_cards_fn = get_cards_fn

    @staticmethod
    def extract_card_ids(cards: List[Dict[str, Any]]) -> set:
        """Extract card IDs from card list"""
        ids = set()
        for card in cards:
            if isinstance(card, dict):
                card_id = card.get('id') or card.get('card_id')
                if card_id is not None:
                    try:
                        ids.add(int(card_id))
                    except (ValueError, TypeError):
                        pass
        return ids

    def get_current_cards(self, deck_id: int, username: str) -> tuple[List[Dict], set]:
        """
        Fetch current cards from deck

        Returns:
            (cards_list, card_ids_set)
        """
        cards = self.get_cards_fn(deck_id, username)
        if not isinstance(cards, list):
            return [], set()

        card_ids = self.extract_card_ids(cards)
        return cards, card_ids

    def detect_new_cards(
        self,
        deck_id: int,
        username: str,
        baseline_ids: set
    ) -> List[Dict[str, Any]]:
        """
        Detect new cards by comparing current state to baseline

        Args:
            deck_id: Deck to check
            username: User
            baseline_ids: Set of card IDs from before (baseline)

        Returns:
            List of new cards that weren't in baseline
        """
        cards, current_ids = self.get_current_cards(deck_id, username)
        new_ids = current_ids - baseline_ids

        if not new_ids:
            return []

        # Return full card objects for new IDs
        new_cards = []
        for card in cards:
            if isinstance(card, dict):
                card_id = card.get('id') or card.get('card_id')
                if card_id and int(card_id) in new_ids:
                    new_cards.append(card)

        return new_cards
