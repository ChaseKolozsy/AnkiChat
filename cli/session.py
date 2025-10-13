"""
Interactive study session management

Handles the main study loop with keyboard commands.
"""

import sys
import logging
from typing import Dict, Any, Optional, List
from prompt_toolkit import PromptSession
from prompt_toolkit.shortcuts import prompt
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from cli.client import AnkiChatAPIClient
from cli.display import (
    CardDisplay,
    display_deck_table,
    display_stats,
    display_vocabulary_queue,
    show_help
)
from cli.polling_manager import PollingManager, PollConfig, VocabularyCardDetector

logger = logging.getLogger(__name__)


class InteractiveStudySession:
    """Handles interactive study session with keybindings"""

    def __init__(self, api_client: AnkiChatAPIClient, console: Console):
        """
        Initialize interactive session

        Args:
            api_client: API client instance
            console: Rich console instance
        """
        self.api = api_client
        self.console = console
        self.prompt_session = PromptSession()
        self.display = CardDisplay(console)

        # Session state
        self.running = True
        self.profile_name: Optional[str] = None
        self.username: Optional[str] = None  # AnkiWeb username
        self.deck_id: Optional[int] = None
        self.deck_name: Optional[str] = None
        self.grammar_deck_id: Optional[int] = None
        self.grammar_deck_name: Optional[str] = None
        self.vocabulary_deck_id: Optional[int] = None
        self.vocabulary_deck_name: Optional[str] = None
        self.current_card: Optional[Dict[str, Any]] = None
        self.card_flipped = False
        self.current_mode = 'grammar'  # 'grammar' or 'vocabulary'
        self.claude_processing = False
        self.cached_grammar_answer: Optional[Dict[str, Any]] = None

        # LIFO layer system state
        self.active_layers: List[str] = []  # Stack of layer tags (LIFO)
        self.current_layer: Optional[str] = None
        self.current_custom_session_deck_id: Optional[int] = None
        self.layer_study_stack: List[str] = []  # Layers to study in LIFO order

        # Polling manager for vocabulary card detection (kept for compatibility)
        self.vocab_poll_manager: Optional[PollingManager] = None

    def run(self, deck_id: Optional[int] = None):
        """
        Main interactive loop

        Args:
            deck_id: Optional deck ID to skip selection (for backward compatibility)
        """
        try:
            # Login
            self.profile_name = self._login()

            # Select decks (both grammar and vocabulary)
            if deck_id is None:
                self._select_decks()
            else:
                # Backward compatibility: use provided deck as grammar deck and prompt for vocabulary deck
                self.grammar_deck_id = deck_id
                decks = self.api.get_decks(self.profile_name)
                for deck in decks:
                    if deck['id'] == deck_id:
                        self.grammar_deck_name = deck['name']
                        break
                self._select_vocabulary_deck()

            # Start study session
            self._start_session()

            # Main study loop
            while self.running:
                try:
                    action = self._get_user_input()
                    self._handle_action(action)
                except KeyboardInterrupt:
                    self.console.print("\n[yellow]Use 'q' to quit[/yellow]")
                except Exception as e:
                    logger.error(f"Error in study loop: {e}")
                    self.console.print(f"[red]Error: {e}[/red]")

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Session interrupted[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Fatal error: {e}[/red]")
            logger.error(f"Fatal error in session: {e}", exc_info=True)
        finally:
            self._cleanup()

    def _login(self) -> str:
        """Login and sync with AnkiWeb"""
        self.console.print(Panel("Login to AnkiWeb", style="blue"))

        profile_name = Prompt.ask("Profile name", default="chase")
        username = Prompt.ask("Username")
        password = Prompt.ask("Password", password=True)

        self.console.print("🔄 Syncing with AnkiWeb...")
        result = self.api.login_and_sync(profile_name, username, password)

        if not result.get('success'):
            error_msg = result.get('error', 'Unknown error')
            self.console.print(f"[red]Login failed: {error_msg}[/red]")
            sys.exit(1)

        # Store both profile_name and username for later use
        self.profile_name = profile_name
        self.username = username

        self.console.print("✅ Login successful!\n")
        return profile_name  # Return profile_name for deck operations

    def _select_decks(self):
        """Interactive selection of both grammar and vocabulary decks"""
        self.console.print("📚 Loading decks...\n")

        decks = self.api.get_decks(self.profile_name)

        if not decks:
            self.console.print("[red]No decks found![/red]")
            sys.exit(1)

        # Fetch counts for each deck
        for deck in decks:
            counts = self.api.get_deck_counts(deck['id'], self.profile_name)
            deck.update(counts)

        # Display deck table
        display_deck_table(self.console, decks)

        # Select grammar deck
        self.console.print("[bold blue]Select Grammar Deck:[/bold blue]")
        while True:
            try:
                choice = Prompt.ask("Enter grammar deck number")
                deck_num = int(choice)
                if 1 <= deck_num <= len(decks):
                    selected_deck = decks[deck_num - 1]
                    self.grammar_deck_id = selected_deck['id']
                    self.grammar_deck_name = selected_deck['name']
                    self.deck_id = selected_deck['id']  # For backward compatibility
                    self.deck_name = selected_deck['name']
                    break
                else:
                    self.console.print(f"[yellow]Please enter a number between 1 and {len(decks)}[/yellow]")
            except ValueError:
                self.console.print("[yellow]Please enter a valid number[/yellow]")

        # Select vocabulary deck
        self._select_vocabulary_deck(decks)

    def _select_vocabulary_deck(self, decks: Optional[List[Dict]] = None):
        """Select vocabulary deck (can be same or different from grammar deck)"""
        if decks is None:
            decks = self.api.get_decks(self.profile_name)
            # Fetch counts for each deck
            for deck in decks:
                counts = self.api.get_deck_counts(deck['id'], self.profile_name)
                deck.update(counts)

        self.console.print("[bold green]Select Vocabulary Deck:[/bold green]")
        self.console.print("[dim](This is where new vocabulary cards will be created)[/dim]")

        while True:
            try:
                choice = Prompt.ask("Enter vocabulary deck number", default=str(self.grammar_deck_id))
                deck_num = int(choice)
                if 1 <= deck_num <= len(decks):
                    selected_deck = decks[deck_num - 1]
                    self.vocabulary_deck_id = selected_deck['id']
                    self.vocabulary_deck_name = selected_deck['name']
                    break
                else:
                    self.console.print(f"[yellow]Please enter a number between 1 and {len(decks)}[/yellow]")
            except ValueError:
                self.console.print("[yellow]Please enter a valid number[/yellow]")

        # Show selection summary
        self.console.print(f"\n✅ [bold]Deck Selection:[/bold]")
        self.console.print(f"   Grammar: [blue]{self.grammar_deck_name}[/blue] (ID: {self.grammar_deck_id})")
        self.console.print(f"   Vocabulary: [green]{self.vocabulary_deck_name}[/green] (ID: {self.vocabulary_deck_id})")
        if self.grammar_deck_id == self.vocabulary_deck_id:
            self.console.print("[dim]   (Using same deck for both grammar and vocabulary)[/dim]")
        self.console.print()

    def _start_session(self):
        """Start the study session"""
        self.console.print(f"\n🎯 Starting dual study session...")
        self.console.print(f"   Grammar: [blue]{self.grammar_deck_name}[/blue]")
        self.console.print(f"   Vocabulary: [green]{self.vocabulary_deck_name}[/green]\n")

        result = self.api.start_dual_session(
            self.profile_name,
            self.grammar_deck_id,
            self.vocabulary_deck_id
        )

        if not result.get('success'):
            error_msg = result.get('error', 'Unknown error')
            self.console.print(f"[red]Failed to start session: {error_msg}[/red]")
            sys.exit(1)

        self.current_card = result.get('current_card')

        if not self.current_card:
            self.console.print("[yellow]No cards available to study[/yellow]")
            sys.exit(0)

        # Display first card
        self._display_card_front()

    def _get_user_input(self) -> str:
        """Get user input (single character or command)"""
        try:
            return self.prompt_session.prompt('> ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 'q'

    def _handle_action(self, action: str):
        """Handle user action"""
        if action == 'f':
            self._flip_card()
        elif action in ['1', '2', '3', '4']:
            if self.card_flipped:
                self._answer_card(int(action))
            else:
                self.console.print("[yellow]⚠️  Flip card first (press 'f')[/yellow]")
        elif action in ['', 'n']:
            # Enter or 'n' key - show next page
            if self.display.next_page():
                self._redisplay_current_card()
            else:
                self.console.print("[dim]Already on the last page[/dim]")
        elif action in ['b', 'p']:
            # 'b' or 'p' key - show previous page
            if self.display.previous_page():
                self._redisplay_current_card()
        elif action == 'd':
            self._define_words()
        elif action == 'v':
            self._switch_to_vocabulary()
        elif action == 'g':
            self._switch_to_grammar()
        elif action == 'retry-grammar':
            # Manual retry for grammar session recovery
            self.console.print("[cyan]🔄 Retrying grammar session recovery...[/cyan]")
            recovery_result = self._recover_grammar_session()
            if recovery_result == 'success':
                self.console.print(f"[green]✅ Grammar session recovered successfully[/green]")
            elif recovery_result == 'timeout':
                self.console.print(f"[yellow]⏱️  Recovery timed out again[/yellow]")
            else:
                self.console.print(f"[red]❌ Recovery failed[/red]")
        elif action == 's':
            self._show_stats()
        elif action == 'h' or action == '?':
            show_help(self.console)
        elif action == 'q':
            self._quit()
        elif action == '':
            # Just Enter with no more pages - show help hint
            self.console.print("[dim]Type 'h' for help, 'f' to flip, '1-4' to answer[/dim]")
        else:
            self.console.print(f"[yellow]Unknown command: '{action}'. Press 'h' for help[/yellow]")

    def _display_card_front(self):
        """Display front of current card"""
        self.display.reset_pagination()
        self.display.display_card_front(self.current_card)
        self.card_flipped = False
        self._show_card_actions()

    def _display_card_back(self):
        """Display back of current card"""
        self.display.reset_pagination()
        self.display.display_card_back(self.current_card)
        self.card_flipped = True
        self._show_answer_options()

    def _redisplay_current_card(self):
        """Redisplay current page of current card"""
        if self.card_flipped:
            self.display._render_card(self.current_card, side="BACK", color="green", force_refresh=False)
        else:
            self.display._render_card(self.current_card, side="FRONT", color="blue", force_refresh=False)

    def _show_card_actions(self):
        """Show available actions for unflipped card"""
        pagination_hint = ""
        if self.display.total_pages > 1:
            pagination_hint = "  [n/p] Next/Prev page"
        self.console.print(f"[dim][f] Flip  [d] Define  [v] Vocab  [s] Stats{pagination_hint}  [h] Help  [q] Quit[/dim]\n")

    def _show_answer_options(self):
        """Show answer options for flipped card"""
        pagination_hint = ""
        if self.display.total_pages > 1:
            pagination_hint = "  [n/p] Next/Prev page"
        self.console.print(
            "[dim]"
            "[red]1[/red] Again  "
            "[yellow]2[/yellow] Hard  "
            "[green]3[/green] Good  "
            "[cyan]4[/cyan] Easy  "
            "[white]|[/white]  "
            f"[dim]h[/dim] Help{pagination_hint}"
            "[/dim]\n"
        )

    def _flip_card(self):
        """Flip current card to show back"""
        if self.card_flipped:
            self.console.print("[yellow]Card is already flipped[/yellow]")
            return

        result = self.api.flip_card(self.profile_name)

        if not result.get('success'):
            error_msg = result.get('error', 'Unknown error')
            self.console.print(f"[red]Failed to flip card: {error_msg}[/red]")
            return

        self.current_card = result.get('current_card', self.current_card)
        self._display_card_back()

    def _answer_card(self, answer: int):
        """Submit answer and get next card"""
        result = self.api.answer_grammar_card(
            username=self.profile_name,
            card_id=self.current_card.get('card_id', 0),
            answer=answer,
            claude_processing=self.claude_processing
        )

        if not result.get('success'):
            error_msg = result.get('error', 'Unknown error')
            self.console.print(f"[red]Failed to answer card: {error_msg}[/red]")
            return

        # Show feedback
        answer_labels = ['', 'Again', 'Hard', 'Good', 'Easy']
        self.console.print(f"✅ Card answered: [bold]{answer_labels[answer]}[/bold]\n")

        if self.claude_processing:
            # Show message that vocabulary cards are being created
            self.console.print(Panel(
                "[cyan]Vocabulary cards are being created in custom study sessions.[/cyan]\n"
                "You can study vocabulary cards now or continue.",
                title="Vocabulary Creation",
                border_style="purple"
            ))
            # Don't return - continue to get next card like web app

        # Get next card
        next_card = result.get('next_card')
        if next_card:
            self.current_card = next_card
            self._display_card_front()

            if self.claude_processing:
                self.console.print("[dim]💡 Press 'v' to study vocabulary cards when ready[/dim]")
                # Note: Auto-answer logic removed as we no longer use caching system
        else:
            self.console.print("[green]🎉 No more cards to study![/green]")
            self.running = False

    def _define_words(self):
        """Request word definitions from Claude SDK"""
        words_str = Prompt.ask("Enter words to define (comma-separated)")
        words = [w.strip() for w in words_str.split(',') if w.strip()]

        if not words:
            self.console.print("[yellow]No words entered[/yellow]")
            return

        self.console.print(f"🤖 Requesting definitions for: {', '.join(words)}...")

        result = self.api.request_definitions(
            username=self.profile_name,
            words=words,
            card_context=self.current_card
        )

        if result.get('success'):
            self.claude_processing = True
            self.console.print(Panel(
                "[cyan]Claude is generating vocabulary definitions...[/cyan]\n"
                "New cards will be added to custom study sessions with layer tags.\n"
                "Switch to vocabulary mode ([v]) to study the new cards.",
                title="Claude SDK Processing",
                border_style="purple"
            ))

            # Refresh layers after new cards are created
            self._load_active_layers()
        else:
            error_msg = result.get('error', 'Unknown error')
            self.console.print(f"[red]Failed to request definitions: {error_msg}[/red]")

    def _switch_to_vocabulary(self):
        """Switch to vocabulary study mode using LIFO layer system"""
        if self.current_mode == 'vocabulary':
            self.console.print("[yellow]Already in vocabulary mode[/yellow]")
            return

        self.current_mode = 'vocabulary'
        self.console.print("\n📖 [bold]Vocabulary Mode (LIFO Layers)[/bold]\n")

        # Load active layers in LIFO order
        self._load_active_layers()

        if self.layer_study_stack:
            self.console.print(f"[green]Found {len(self.layer_study_stack)} active layers[/green]")
            self._study_vocabulary_lifo()
        else:
            self.console.print("[yellow]No vocabulary layers available[/yellow]")
            self.console.print("[dim]Define words from grammar cards to create layers[/dim]")
            self.console.print("[dim]Press 'g' to return to grammar mode[/dim]")

    def _load_active_layers(self):
        """Load active vocabulary layers in LIFO order"""
        try:
            result = self.api.get_active_layers(self.vocabulary_deck_id, self.profile_name)
            if result.get('success'):
                layers = result.get('layers', [])
                # Sort layers by timestamp (most recent first) for LIFO
                layers.sort(key=lambda x: x.get('created_at', ''), reverse=True)
                self.layer_study_stack = [layer['tag'] for layer in layers]
                self.console.print(f"[dim]Loaded layers (LIFO order): {', '.join(self.layer_study_stack[:3])}{'...' if len(self.layer_study_stack) > 3 else ''}[/dim]")
            else:
                self.layer_study_stack = []
                self.console.print(f"[dim]No active layers found: {result.get('error', 'Unknown error')}[/dim]")
        except Exception as e:
            logger.error(f"Error loading active layers: {e}")
            self.layer_study_stack = []
            self.console.print(f"[red]Error loading layers: {e}[/red]")

    def _study_vocabulary_lifo(self):
        """Study vocabulary cards using LIFO layer system"""
        if not self.layer_study_stack:
            self.console.print("[yellow]No more layers to study[/yellow]")
            return

        # Get the most recent layer (top of stack)
        current_layer = self.layer_study_stack[0]
        self.current_layer = current_layer

        self.console.print(f"\n🎯 [bold]Studying Layer:[/bold] [cyan]{current_layer}[/cyan]")
        self.console.print(f"[dim]Layers remaining: {len(self.layer_study_stack) - 1}[/dim]\n")

        # Create custom study session for this layer
        session_result = self.api.create_custom_study_session(
            self.vocabulary_deck_id,
            self.profile_name,
            current_layer,
            card_limit=100
        )

        if not session_result.get('success'):
            self.console.print(f"[red]Failed to create study session: {session_result.get('error')}[/red]")
            return

        self.current_custom_session_deck_id = session_result.get('session_deck_id', self.vocabulary_deck_id)

        # Start studying the custom session
        self._study_custom_session()

    def _study_custom_session(self):
        """Study cards in the current custom session"""
        # Start the session
        start_result = self.api.study_custom_session(
            self.current_custom_session_deck_id,
            self.profile_name,
            'start'
        )

        if not start_result.get('success'):
            self.console.print(f"[red]Failed to start custom session: {start_result.get('error')}[/red]")
            return

        current_card = start_result.get('current_card')
        if not current_card:
            self.console.print("[green]No cards in this layer![/green]")
            self._complete_current_layer()
            return

        # Study loop for this layer
        while current_card and self.current_mode == 'vocabulary':
            self.current_card = current_card

            # Display the card
            self.display.reset_pagination()
            self.display.display_card_full(current_card, force_refresh=True)
            self._show_custom_session_actions()

            # Get user input
            try:
                action = self._get_user_input()
                result = self._handle_custom_session_action(action, current_card)

                if result == 'next_card':
                    # Get next card
                    next_result = self.api.study_custom_session(
                        self.current_custom_session_deck_id,
                        self.profile_name,
                        'next'
                    )

                    if next_result.get('success') and next_result.get('current_card'):
                        current_card = next_result['current_card']
                    else:
                        # No more cards in this layer
                        self.console.print("[green]✅ Layer completed![/green]")
                        self._complete_current_layer()
                        break
                elif result == 'exit_mode':
                    break

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use 'q' to quit[/yellow]")
            except Exception as e:
                logger.error(f"Error in custom session: {e}")
                self.console.print(f"[red]Error: {e}[/red]")

    def _complete_current_layer(self):
        """Complete current layer and move to next one"""
        # Close the custom session
        self.api.close_custom_study_session(
            self.current_custom_session_deck_id,
            self.profile_name
        )

        # Remove current layer from stack (LIFO - pop from top)
        if self.layer_study_stack and self.layer_study_stack[0] == self.current_layer:
            self.layer_study_stack.pop(0)

        # Reset session state
        self.current_custom_session_deck_id = None
        self.current_layer = None
        self.current_card = None

        # Continue with next layer if available
        if self.layer_study_stack:
            self.console.print(f"\n[cyan]📚 Moving to next layer...[/cyan]")
            self._study_vocabulary_lifo()
        else:
            self.console.print("\n[green]🎉 All vocabulary layers completed![/green]")
            self.console.print("[dim]Press 'g' to return to grammar mode[/dim]")

    def _show_custom_session_actions(self):
        """Show available actions for custom vocabulary session"""
        pagination_hint = ""
        if self.display.total_pages > 1:
            pagination_hint = "  [n/p] Next/Prev page"
        self.console.print(f"[dim][1-4] Answer{pagination_hint}  [d] Define  [g] Grammar  [h] Help  [q] Quit[/dim]\n")

    def _handle_custom_session_action(self, action: str, card: Dict[str, Any]) -> str:
        """Handle user action in custom vocabulary session"""
        if action in ['1', '2', '3', '4']:
            # Answer the card
            answer_result = self.api.study_custom_session(
                self.current_custom_session_deck_id,
                self.profile_name,
                f'answer_{action}'
            )

            if answer_result.get('success'):
                answer_labels = ['', 'Again', 'Hard', 'Good', 'Easy']
                self.console.print(f"✅ Card answered: [bold]{answer_labels[int(action)]}[/bold]")
                return 'next_card'
            else:
                self.console.print(f"[red]Failed to answer card: {answer_result.get('error')}[/red]")
                return None

        elif action in ['', 'n']:
            # Next page
            if self.display.next_page():
                self.display.display_card_full(card, force_refresh=False)
                self._show_custom_session_actions()
            return None
        elif action in ['b', 'p']:
            # Previous page
            if self.display.previous_page():
                self.display.display_card_full(card, force_refresh=False)
                self._show_custom_session_actions()
            return None
        elif action == 'd':
            # Define words (creates nested layer)
            define_result = self._define_vocabulary_words_in_session(card)
            return define_result
        elif action == 'g':
            self._switch_to_grammar()
            return 'exit_mode'
        elif action in ['h', '?']:
            self._show_vocabulary_help()
            return None
        elif action == 'q':
            if Confirm.ask("Are you sure you want to quit?", default=False):
                self.running = False
            return None
        else:
            self.console.print(f"[yellow]Unknown command. Press 'h' for help[/yellow]")
            return None

    def _define_vocabulary_words_in_session(self, card: Dict[str, Any]) -> str:
        """Define words from vocabulary card, creating nested layer"""
        words_str = Prompt.ask("Enter words to define (comma-separated)")
        words = [w.strip() for w in words_str.split(',') if w.strip()]

        if not words:
            self.console.print("[yellow]No words entered[/yellow]")
            return None

        self.console.print(f"🤖 Requesting definitions for vocabulary words: {', '.join(words)}...")

        # IMPORTANT: Close current custom study session before creating new cards
        # This prevents collection lock conflicts during nested definition creation
        if self.current_custom_session_deck_id:
            self.console.print("[dim]Closing current vocabulary session to allow card creation...[/dim]")
            close_result = self.api.close_custom_study_session(
                self.current_custom_session_deck_id,
                self.profile_name
            )
            if not close_result.get('success'):
                logger.warning(f"Failed to close custom session: {close_result.get('error')}")

        # Use vocabulary card context for nested layer generation
        result = self.api.request_definitions(
            username=self.profile_name,
            words=words,
            card_context=card
        )

        if result.get('success'):
            self.console.print(Panel(
                "[cyan]Claude is generating nested vocabulary definitions...[/cyan]\n"
                "New cards will be added to a nested layer (LIFO priority).\n"
                "[dim]Polling will timeout after 60 seconds if cards aren't created.[/dim]",
                title="Nested Layer Creation",
                border_style="purple"
            ))

            # Poll for new cards
            poll_result = self._poll_for_new_vocabulary_cards()

            if poll_result == 'found':
                self.console.print("[green]✅ New nested layer created![/green]")
                # Reload layers to get the new nested layer on top
                self._load_active_layers()
                if self.layer_study_stack:
                    self.console.print("[cyan]🔄 Restarting with new nested layer (LIFO priority)[/cyan]")
                    # Restart studying with the new layer on top
                    self._complete_current_layer()  # This will start the new layer
                    return 'restart_layer'
                else:
                    self.console.print("[yellow]No layers found after creation[/yellow]")
                    return None
            else:
                self.console.print("[yellow]No new cards detected[/yellow]")
                return None
        else:
            error_msg = result.get('error', 'Unknown error')
            self.console.print(f"[red]Failed to request definitions: {error_msg}[/red]")
            return None

    def _study_vocabulary(self):
        """[DEPRECATED] Study vocabulary cards - use _study_vocabulary_lifo instead"""
        self.console.print("[yellow]Note: Using legacy vocabulary study mode. New LIFO layer system recommended.[/yellow]")
        self.console.print("[dim]Switching to LIFO layer system...[/dim]")
        self._switch_to_vocabulary()
        return

    def _show_vocabulary_actions(self):
        """Show available actions for vocabulary cards"""
        pagination_hint = ""
        if self.display.total_pages > 1:
            pagination_hint = "  [n/p] Next/Prev page"
        self.console.print(f"[dim][Enter] Studied{pagination_hint}  [d] Define  [r] Retry  [g] Grammar  [h] Help  [q] Quit[/dim]\n")

    def _handle_vocabulary_action(self, action: str, card: Dict[str, Any]):
        """Handle user action in vocabulary mode"""
        if action == 'r':
            # Retry polling for vocabulary cards after timeout
            if self._retry_vocabulary_poll():
                # New cards found - reload from queue
                new_card_result = self.api.get_next_vocabulary_card(self.profile_name)
                if new_card_result.get('success') and new_card_result.get('card'):
                    new_card = new_card_result['card']
                    self.current_card = new_card
                    self.display.reset_pagination()
                    self.display.display_card_full(new_card)
                    self._show_vocabulary_actions()
                    self.console.print("[green]✅ New vocabulary card loaded after retry![/green]")
                    return 'new_card'
                else:
                    self.console.print("[yellow]No cards in queue after retry[/yellow]")
            else:
                self.console.print("[yellow]Retry did not find new cards[/yellow]")
            return None  # Stay on current card
        elif action in ['', 'n']:
            # Enter or 'n' key - show next page
            if self.display.next_page():
                self.display.display_card_full(card, force_refresh=False)
                self._show_vocabulary_actions()
                self._last_page_reached = False  # Reset since we're not on last page anymore
                return None  # Stay on current card
            else:
                # At last page - if we haven't indicated this before, show hint
                if not hasattr(self, '_last_page_reached') or not self._last_page_reached:
                    self._last_page_reached = True
                    self.console.print("[dim]📄 Last page reached. Press Enter again to mark as studied, or 'd' to define words.[/dim]")
                    self._show_vocabulary_actions()
                    return None  # Stay on current card
                else:
                    # Already on last page and user confirmed - mark as studied
                    card_id = card.get('card_id') or card.get('id')
                    self.api.cache_vocabulary_answer(self.profile_name, card_id, 3)
                    self.console.print("✅ [green]Marked as studied[/green]\n")
                    # Show updated queue status
                    self._show_vocabulary_queue_status()
                    self._last_page_reached = False  # Reset for next card
                    return 'studied'  # Get next card
        elif action == '3':
            # Explicit mark as studied
            card_id = card.get('card_id') or card.get('id')
            self.api.cache_vocabulary_answer(self.profile_name, card_id, 3)
            self.console.print("✅ [green]Marked as studied[/green]\n")
            # Show updated queue status
            self._show_vocabulary_queue_status()
            self._last_page_reached = False  # Reset for next card
            return 'studied'  # Get next card
        elif action in ['b', 'p']:
            # 'b' or 'p' key - show previous page
            if self.display.previous_page():
                self.display.display_card_full(card, force_refresh=False)
                self._show_vocabulary_actions()
                self._last_page_reached = False  # Reset since we went back
            else:
                self.console.print("[dim]Already on the first page[/dim]")
            return None  # Stay on current card
        elif action == 'd':
            define_result = self._define_vocabulary_words(card)
            if define_result == 'new_card_ready':
                # We've switched to a new card, update the study loop
                self._last_page_reached = False  # Reset for new card
                return 'new_card'  # Signal study loop to update vocabulary_card
            else:
                self._last_page_reached = True  # User is still on same card after defining
                return None  # Stay on current card
        elif action == 'g':
            self._switch_to_grammar()
            return 'exit_mode'  # Exit vocabulary mode
        elif action in ['h', '?']:
            self._show_vocabulary_help()
            return None  # Stay on current card
        elif action == 'q':
            if Confirm.ask("Are you sure you want to quit?", default=False):
                self.running = False
            return None  # Stay on current card
        else:
            self.console.print(f"[yellow]Unknown command. Press Enter to mark as studied, 'h' for help[/yellow]")
            return None  # Stay on current card

    def _submit_vocabulary_session(self):
        """Submit cached vocabulary answers"""
        self.console.print("📤 Submitting vocabulary session...")

        result = self.api.submit_vocabulary_session(self.profile_name)

        if result.get('success'):
            count = result.get('processed_count', 0)
            self.console.print(f"[green]✅ Processed {count} vocabulary cards![/green]\n")
        else:
            error_msg = result.get('error', 'Unknown error')
            self.console.print(f"[red]Failed to submit session: {error_msg}[/red]")

    def _switch_to_grammar(self):
        """Switch back to grammar study mode with timeout handling"""
        if self.current_mode == 'grammar':
            self.console.print("[yellow]Already in grammar mode[/yellow]")
            return

        self.current_mode = 'grammar'
        self.console.print("\n📚 [bold]Grammar Mode[/bold]\n")

        # Attempt to recover or start fresh grammar session with timeout
        recovery_result = self._recover_grammar_session()

        if recovery_result == 'timeout':
            self.console.print(Panel(
                "[yellow]⏱️  Session recovery timed out.[/yellow]\n"
                "The session may be in an inconsistent state.\n"
                "[cyan]Type 'retry-grammar' to try again.[/cyan]",
                title="Recovery Timeout",
                border_style="yellow"
            ))
        elif recovery_result == 'success':
            self.console.print(f"[green]✅ Grammar session ready[/green]")
        else:
            self.console.print(f"[red]❌ Could not start grammar session[/red]")

    def _recover_grammar_session(self, timeout_seconds: int = 30) -> str:
        """
        Attempt to recover or start fresh grammar session with timeout

        Args:
            timeout_seconds: Max time to wait for session recovery

        Returns:
            'success', 'timeout', or 'error'
        """
        import signal

        class TimeoutError(Exception):
            pass

        def timeout_handler(signum, frame):
            raise TimeoutError("Session recovery timed out")

        # Set timeout for session recovery
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)

        try:
            # Close any existing sessions first
            self.console.print("[dim]Closing existing sessions...[/dim]")
            close_result = self.api.close_all_sessions(self.profile_name)
            if close_result.get('success'):
                self.console.print("[dim]✓ Closed existing sessions[/dim]")
            else:
                self.console.print(f"[dim]Note: {close_result.get('error', 'Could not close sessions')}[/dim]")

            # Complete state reset except for essential info (profile, username, deck)
            self.current_card = None
            self.card_flipped = False
            self.claude_processing = False
            self.cached_grammar_answer = None

            # Start completely fresh grammar session
            if self.deck_id:
                self.console.print(f"[dim]Starting fresh grammar session for deck: {self.deck_name} (ID: {self.deck_id})[/dim]")
                result = self.api.start_dual_session(
                    self.profile_name,
                    self.grammar_deck_id,
                    self.vocabulary_deck_id
                )

                if result.get('success') and result.get('current_card'):
                    self.current_card = result['current_card']
                    self.card_flipped = False

                    # Display the fresh grammar card
                    self._display_card_front()
                    remaining = result.get('remaining', 'unknown')
                    self.console.print(f"[dim]Cards remaining in session: {remaining}[/dim]")

                    # Cancel alarm
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
                    return 'success'
                else:
                    error_msg = result.get('error', 'Unknown error')
                    self.console.print(f"[red]Failed to start grammar session: {error_msg}[/red]")
                    self.current_card = None
                    self.card_flipped = False

                    # Cancel alarm
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
                    return 'error'
            else:
                self.console.print("[red]No deck selected - cannot start grammar session[/red]")
                self.current_card = None
                self.card_flipped = False

                # Cancel alarm
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
                return 'error'

        except TimeoutError:
            # Timeout occurred
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
            logger.warning("Grammar session recovery timed out")
            return 'timeout'

        except Exception as e:
            # Other error
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
            logger.error(f"Error during grammar session recovery: {e}")
            self.console.print(f"[red]Recovery error: {e}[/red]")
            return 'error'

    def _show_stats(self):
        """Show current session statistics"""
        counts = self.api.get_deck_counts(self.deck_id, self.profile_name)
        if counts:
            display_stats(self.console, counts)
        else:
            self.console.print("[yellow]Failed to load statistics[/yellow]")

    def _define_vocabulary_words(self, card: Dict[str, Any]):
        """Request word definitions from Claude SDK for vocabulary cards"""
        # Prompt user for words to define
        words_str = Prompt.ask("Enter words to define (comma-separated)")
        words = [w.strip() for w in words_str.split(',') if w.strip()]

        if not words:
            self.console.print("[yellow]No words entered[/yellow]")
            return None

        self.console.print(f"🤖 Requesting definitions for vocabulary words: {', '.join(words)}...")

        result = self.api.request_definitions(
            username=self.profile_name,
            words=words,
            card_context=card
        )

        if result.get('success'):
            self.console.print(Panel(
                "[cyan]Claude is generating vocabulary definitions...[/cyan]\n"
                "New cards will be added to custom study sessions with layer tags.\n"
                "[dim]Polling will timeout after 60 seconds if cards aren't created.[/dim]",
                title="Claude SDK Processing",
                border_style="purple"
            ))

            # Set claude_processing flag (for grammar mode behavior)
            self.claude_processing = True

            # Use polling manager to wait for new cards with timeout
            poll_result = self._poll_for_new_vocabulary_cards()

            if poll_result == 'timeout':
                self.console.print(Panel(
                    "[yellow]⏱️  Polling timed out waiting for new vocabulary cards.[/yellow]\n"
                    "The cards may still be created in the background.\n"
                    "[cyan]Press 'r' to retry checking for new cards.[/cyan]",
                    title="Timeout",
                    border_style="yellow"
                ))
                # Stay on current card
                self._show_vocabulary_actions()
                return None
            elif poll_result == 'found':
                # For LIFO stack behavior, requeue current card then get the newly added card
                if card:
                    requeue_result = self.api.requeue_vocabulary_card(self.profile_name, card)
                    if not requeue_result.get('success'):
                        logger.warning(f"Failed to requeue current card: {requeue_result.get('error')}")

                new_card_result = self.api.get_next_vocabulary_card(self.profile_name)
                if new_card_result.get('success') and new_card_result.get('card'):
                    # Display the newly created card immediately (top of stack)
                    new_card = new_card_result['card']
                    self.current_card = new_card
                    self.display.reset_pagination()
                    self.display.display_card_full(new_card)
                    self._show_vocabulary_actions()
                    self.console.print("[green]✅ New vocabulary card ready (top of stack)![/green]")
                    return 'new_card_ready'  # Signal that we've switched to a new card
                else:
                    self.console.print("[yellow]No new vocabulary card available in queue[/yellow]")
                    self._show_vocabulary_actions()
                    return None
            else:
                # Error or other issue
                self.console.print("[yellow]Could not detect new cards[/yellow]")
                self._show_vocabulary_actions()
                return None

        else:
            error_msg = result.get('error', 'Unknown error')
            self.console.print(f"[red]Failed to request definitions: {error_msg}[/red]")
            return None

    def _poll_for_new_vocabulary_cards(self) -> str:
        """
        Poll for new vocabulary cards with timeout

        Returns:
            'found' if cards detected, 'timeout' if timed out, 'error' on error
        """
        # Initialize polling manager
        if self.vocab_poll_manager is None:
            self.vocab_poll_manager = PollingManager(PollConfig(timeout_seconds=60, poll_interval_seconds=2.0))
        else:
            self.vocab_poll_manager.reset()

        # Get baseline card IDs from vocabulary deck (deck ID 1)
        try:
            from AnkiClient.src.operations.deck_ops import get_cards_in_deck

            def get_cards_fn(deck_id: int, username: str):
                return get_cards_in_deck(deck_id=deck_id, username=username)

            detector = VocabularyCardDetector(get_cards_fn)
            _, baseline_ids = detector.get_current_cards(self.vocabulary_deck_id, self.profile_name)
            self.vocab_poll_manager.record_baseline(baseline_ids)

            self.console.print(f"[dim]Baseline: {len(baseline_ids)} cards in vocabulary deck[/dim]")

        except Exception as e:
            logger.error(f"Failed to get baseline cards: {e}")
            self.console.print(f"[red]Error getting baseline: {e}[/red]")
            return 'error'

        # Poll for new cards
        while True:
            should_continue, reason = self.vocab_poll_manager.should_continue_polling()

            if not should_continue:
                if self.vocab_poll_manager.state.timed_out:
                    self.console.print(f"[yellow]⏱️  {reason}[/yellow]")
                    return 'timeout'
                else:
                    logger.warning(f"Polling stopped: {reason}")
                    return 'error'

            # Check for new cards
            try:
                _, current_ids = detector.get_current_cards(self.vocabulary_deck_id, self.profile_name)
                new_ids = self.vocab_poll_manager.check_for_new_cards(current_ids)

                if new_ids:
                    self.console.print(f"[green]✅ Detected {len(new_ids)} new card(s)![/green]")
                    self.vocab_poll_manager.mark_completed()
                    return 'found'

                # Show progress
                status = self.vocab_poll_manager.get_status_summary()
                self.console.print(
                    f"[dim]Checking... {status['elapsed_seconds']}s / {status['poll_count']} checks "
                    f"(timeout in {status['remaining_seconds']}s)[/dim]",
                    end='\r'
                )

            except Exception as e:
                logger.error(f"Error during polling: {e}")
                self.console.print(f"\n[red]Polling error: {e}[/red]")
                return 'error'

            # Wait before next check
            self.vocab_poll_manager.wait_poll_interval()

    def _retry_vocabulary_poll(self) -> bool:
        """
        Retry polling for vocabulary cards after timeout

        Returns:
            True if new cards found, False otherwise
        """
        if self.vocab_poll_manager is None:
            self.console.print("[yellow]No active polling session to retry[/yellow]")
            return False

        can_retry, reason = self.vocab_poll_manager.can_retry()
        if not can_retry:
            self.console.print(f"[yellow]Cannot retry: {reason}[/yellow]")
            return False

        self.console.print(f"[cyan]🔄 Retrying vocabulary card detection... ({reason})[/cyan]")
        self.vocab_poll_manager.retry()

        # Re-poll
        result = self._poll_for_new_vocabulary_cards()
        return result == 'found'

    def _show_vocabulary_queue_status(self):
        """Display current vocabulary queue status"""
        status_result = self.api.get_vocabulary_queue_status(self.profile_name)
        if status_result.get('success'):
            status = status_result.get('queue_status', {})
            queue_length = status.get('queue_length', 0)
            cached_answers = status.get('cached_answers', 0)

            if queue_length > 0 or cached_answers > 0:
                status_text = f"📚 Vocabulary Stack (LIFO): {queue_length} cards"
                if cached_answers > 0:
                    status_text += f" | {cached_answers} cached answers"

                self.console.print(Panel(
                    status_text,
                    title="Stack Status",
                    border_style="cyan"
                ))

    def _show_vocabulary_help(self):
        """Display help specific to vocabulary mode"""
        help_text = """
[bold cyan]Vocabulary Mode Help (LIFO Layers):[/bold cyan]

[bold]Study Commands:[/bold]
  [yellow]1-4[/yellow]       - Answer card (Again/Hard/Good/Easy)
  [yellow]d[/yellow]        - Define words (creates nested layer)

[bold]Navigation:[/bold]
  [yellow]Enter/n[/yellow]  - Next page (when card has multiple pages)
  [yellow]b/p[/yellow]      - Previous page

[bold]Mode Commands:[/bold]
  [yellow]g[/yellow]        - Switch back to grammar mode
  [yellow]h/?[/yellow]      - Show this help
  [yellow]q[/yellow]        - Quit session

[bold]LIFO Layer System:[/bold]
• Vocabulary cards are organized in layers with tags (e.g., layer_123)
• New words from grammar cards create new layers
• Layers are studied in LIFO order (most recent first)
• Defining words from vocabulary cards creates nested layers
• Nested layers get immediate priority (LIFO behavior)

[bold]Tips:[/bold]
• Navigate long vocabulary cards page by page
• Define unfamiliar words to create nested learning paths
• New layers automatically get priority over existing ones
• Each layer is a custom study session with 1-4 answer options
• Switch between grammar and vocabulary modes as needed
        """.strip()

        panel = Panel(
            help_text,
            title="Vocabulary Mode Help",
            border_style="orange1",
            padding=(1, 2)
        )

        self.console.print(panel)
        self.console.print()  # Add spacing after help

    def _quit(self):
        """Quit the session"""
        if Confirm.ask("Are you sure you want to quit?", default=False):
            self.running = False

    def _cleanup(self):
        """Cleanup on exit"""
        if self.profile_name:
            self.console.print("\n🔄 Closing sessions...")
            try:
                # Close any active custom vocabulary session
                if self.current_custom_session_deck_id and self.current_mode == 'vocabulary':
                    self.api.close_custom_study_session(
                        self.current_custom_session_deck_id,
                        self.profile_name
                    )
                    self.console.print("[dim]✓ Closed custom vocabulary session[/dim]")

                # Close main study sessions
                self.api.close_all_sessions(self.profile_name)
                self.console.print("✅ All sessions closed")
            except Exception as e:
                logger.error(f"Error closing sessions: {e}")

        self.console.print("👋 [bold]Goodbye![/bold]\n")
