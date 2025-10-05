"""
API Client for AnkiChat web app

Wraps all HTTP endpoints for easy access from CLI.
"""

import logging
from typing import Dict, List, Any, Optional

import requests

logger = logging.getLogger(__name__)


class AnkiChatAPIClient:
    """HTTP client for AnkiChat web app API"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize API client

        Args:
            base_url: Base URL of the API server
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def _post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request to API"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.post(url, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return {'error': str(e), 'success': False}

    def _get(self, endpoint: str) -> Dict[str, Any]:
        """Make GET request to API"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return {'error': str(e), 'success': False}

    # Authentication
    def login_and_sync(
        self,
        profile_name: str,
        username: str,
        password: str,
        endpoint: Optional[str] = None,
        upload: bool = False
    ) -> Dict[str, Any]:
        """Login and sync with AnkiWeb"""
        return self._post('/api/login-and-sync', {
            'profile_name': profile_name,
            'username': username,
            'password': password,
            'endpoint': endpoint,
            'upload': upload
        })

    def sync(self, username: str, password: str) -> Dict[str, Any]:
        """Quick sync with AnkiWeb"""
        return self.login_and_sync(username, username, password, upload=True)

    # Deck operations
    def get_decks(self, username: str) -> List[Dict[str, Any]]:
        """Get all decks for user"""
        result = self._post('/api/decks', {'username': username})
        if isinstance(result, list):
            return result
        return result.get('decks', [])

    def get_deck_counts(self, deck_id: int, username: str) -> Dict[str, Any]:
        """Get study counts for a specific deck"""
        return self._post('/api/study/counts', {
            'deck_id': deck_id,
            'username': username
        })

    # Study session
    def start_dual_session(self, username: str, deck_id: int) -> Dict[str, Any]:
        """Start dual study session (grammar + vocabulary)"""
        return self._post('/api/start-dual-session', {
            'username': username,
            'deck_id': deck_id
        })

    def flip_card(self, username: str) -> Dict[str, Any]:
        """Flip the current card to show the back"""
        return self._post('/api/flip-card', {'username': username})

    def answer_grammar_card(
        self,
        username: str,
        card_id: int,
        answer: int,
        claude_processing: bool = False,
        is_cached_answer: bool = False
    ) -> Dict[str, Any]:
        """Answer grammar card (1-4 for Again/Hard/Good/Easy)"""
        return self._post('/api/answer-grammar-card', {
            'username': username,
            'card_id': card_id,
            'answer': answer,
            'claude_processing': claude_processing,
            'is_cached_answer': is_cached_answer
        })

    def close_all_sessions(self, username: str) -> Dict[str, Any]:
        """Close all active study sessions"""
        return self._post('/api/close-all-sessions', {'username': username})

    # Vocabulary operations
    def get_vocabulary_queue_status(self, username: str) -> Dict[str, Any]:
        """Get vocabulary queue status"""
        return self._post('/api/vocabulary-queue-status', {'username': username})

    def get_next_vocabulary_card(self, username: str) -> Dict[str, Any]:
        """Get next vocabulary card from LIFO queue"""
        return self._post('/api/next-vocabulary-card', {'username': username})

    def cache_vocabulary_answer(
        self,
        username: str,
        card_id: int,
        answer: int
    ) -> Dict[str, Any]:
        """Cache vocabulary card answer for auto-session"""
        return self._post('/api/cache-vocabulary-answer', {
            'username': username,
            'card_id': card_id,
            'answer': answer
        })

    def submit_vocabulary_session(self, username: str) -> Dict[str, Any]:
        """Submit vocabulary session for auto-processing"""
        return self._post('/api/submit-vocabulary-session', {'username': username})

    def requeue_vocabulary_card(self, username: str, card: Dict[str, Any]) -> Dict[str, Any]:
        """Requeue current vocabulary card to top of LIFO queue"""
        return self._post('/api/requeue-current-vocabulary-card', {
            'username': username,
            'card': card
        })

    # Claude SDK integration
    def request_definitions(
        self,
        username: str,
        words: List[str],
        card_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Request word definitions from Claude SDK"""
        return self._post('/api/request-definitions', {
            'username': username,
            'words': words,
            'card_context': card_context
        })

    def submit_cached_answer(
        self,
        username: str,
        card_id: int,
        answer: int
    ) -> Dict[str, Any]:
        """Submit cached grammar answer after Claude processing"""
        return self.answer_grammar_card(
            username=username,
            card_id=card_id,
            answer=answer,
            is_cached_answer=True
        )

    # Health check
    def health_check(self) -> Dict[str, Any]:
        """Check if server is healthy"""
        return self._get('/api/health')
