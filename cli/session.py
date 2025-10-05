"""
Interactive study session management

Handles the main study loop with keyboard commands.
"""

import sys
import logging
from typing import Dict, Any, Optional
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
        self.current_card: Optional[Dict[str, Any]] = None
        self.card_flipped = False
        self.current_mode = 'grammar'  # 'grammar' or 'vocabulary'
        self.claude_processing = False
        self.cached_grammar_answer: Optional[Dict[str, Any]] = None

    def run(self, deck_id: Optional[int] = None):
        """
        Main interactive loop

        Args:
            deck_id: Optional deck ID to skip selection
        """
        try:
            # Login
            self.profile_name = self._login()

            # Select deck
            if deck_id is None:
                deck_id = self._select_deck()

            self.deck_id = deck_id

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

    def _select_deck(self) -> int:
        """Interactive deck selection"""
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

        # Prompt for selection
        while True:
            try:
                choice = Prompt.ask("\nSelect deck number")
                deck_num = int(choice)
                if 1 <= deck_num <= len(decks):
                    selected_deck = decks[deck_num - 1]
                    self.deck_name = selected_deck['name']
                    return selected_deck['id']
                else:
                    self.console.print(f"[yellow]Please enter a number between 1 and {len(decks)}[/yellow]")
            except ValueError:
                self.console.print("[yellow]Please enter a valid number[/yellow]")

    def _start_session(self):
        """Start the study session"""
        self.console.print(f"\n🎯 Starting study session: [bold]{self.deck_name}[/bold]\n")

        result = self.api.start_dual_session(self.profile_name, self.deck_id)

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
            # Answer was cached
            self.console.print(Panel(
                "[cyan]Answer cached while Claude generates vocabulary cards.[/cyan]\n"
                "You can study vocabulary cards now or wait.",
                title="Answer Cached",
                border_style="purple"
            ))
            return

        # Get next card
        next_card = result.get('next_card')
        if next_card:
            self.current_card = next_card
            self._display_card_front()
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
                "Your next answer will be cached.\n"
                "Switch to vocabulary mode ([v]) to study the new cards.",
                title="Claude SDK Processing",
                border_style="purple"
            ))
        else:
            error_msg = result.get('error', 'Unknown error')
            self.console.print(f"[red]Failed to request definitions: {error_msg}[/red]")

    def _switch_to_vocabulary(self):
        """Switch to vocabulary study mode"""
        if self.current_mode == 'vocabulary':
            self.console.print("[yellow]Already in vocabulary mode[/yellow]")
            return

        self.current_mode = 'vocabulary'
        self.console.print("\n📖 [bold]Vocabulary Mode[/bold]\n")

        # Show queue status
        status_result = self.api.get_vocabulary_queue_status(self.profile_name)
        if status_result.get('success'):
            status = status_result.get('queue_status', {})
            display_vocabulary_queue(self.console, status)

            if status.get('queue_length', 0) > 0:
                self._study_vocabulary()
            else:
                self.console.print("[yellow]No vocabulary cards in queue[/yellow]")
                self.console.print("[dim]Press 'g' to return to grammar mode[/dim]")
        else:
            self.console.print("[red]Failed to get vocabulary queue status[/red]")

    def _study_vocabulary(self):
        """Study vocabulary cards"""
        self.current_mode = 'vocabulary'
        vocabulary_card = None

        while True:
            # Get next card
            result = self.api.get_next_vocabulary_card(self.profile_name)

            if not result.get('success') or not result.get('card'):
                self.console.print("[green]No more vocabulary cards![/green]")

                # Check if there are cached answers to submit
                status_result = self.api.get_vocabulary_queue_status(self.profile_name)
                if status_result.get('success'):
                    status = status_result.get('queue_status', {})
                    if status.get('cached_answers', 0) > 0:
                        if Confirm.ask("Submit vocabulary session?"):
                            self._submit_vocabulary_session()
                break

            vocabulary_card = result['card']
            self.current_card = vocabulary_card  # Store for navigation

            # Display the vocabulary card with pagination
            self.display.reset_pagination()
            self.display.display_card_full(vocabulary_card)

            # Show vocabulary navigation options
            self._show_vocabulary_actions()

            # Handle user input
            action = self._get_user_input()
            action_result = self._handle_vocabulary_action(action, vocabulary_card)

            # If action was pagination, continue studying same card
            if action_result == 'continue_pagination':
                continue  # Stay on current card for more pagination
            elif action_result == 'exit_mode':
                break  # Exit vocabulary mode
            # If action was 'studied', move to next card (continue loop)

    def _show_vocabulary_actions(self):
        """Show available actions for vocabulary cards"""
        pagination_hint = ""
        if self.display.total_pages > 1:
            pagination_hint = "  [n/p] Next/Prev page"
        self.console.print(f"[dim][Enter] Studied{pagination_hint}  [d] Define  [g] Grammar  [h] Help  [q] Quit[/dim]\n")

    def _handle_vocabulary_action(self, action: str, card: Dict[str, Any]):
        """Handle user action in vocabulary mode"""
        if action in ['', 'n']:
            # Navigate to next page (Enter or n key)
            if self.display.next_page():
                self.display.display_card_full(card)
                self._show_vocabulary_actions()
                return 'continue_pagination'  # Stay on this card for more pagination
            else:
                # At end of card, mark as studied
                card_id = card.get('card_id') or card.get('id')
                self.api.cache_vocabulary_answer(self.profile_name, card_id, 3)
                self.console.print("✅ [green]Marked as studied[/green]\n")
                # Show updated queue status
                self._show_vocabulary_queue_status()
                return 'studied'  # Move to next card
        elif action == '3':
            # Explicit mark as studied
            card_id = card.get('card_id') or card.get('id')
            self.api.cache_vocabulary_answer(self.profile_name, card_id, 3)
            self.console.print("✅ [green]Marked as studied[/green]\n")
            # Show updated queue status
            self._show_vocabulary_queue_status()
            return 'studied'  # Move to next card
        elif action in ['b', 'p']:
            # Navigate to previous page
            if self.display.previous_page():
                self.display.display_card_full(card)
                self._show_vocabulary_actions()
                return 'continue_pagination'  # Stay on this card for more pagination
            else:
                self.console.print("[dim]Already on the first page[/dim]")
                return 'continue_pagination'  # Stay on this card
        elif action == 'd':
            self._define_vocabulary_words(card)
            return 'continue_pagination'  # Stay on this card (new card might appear)
        elif action == 'g':
            self._switch_to_grammar()
            return 'exit_mode'  # Exit vocabulary mode
        elif action in ['h', '?']:
            self._show_vocabulary_help()
            return 'continue_pagination'  # Stay on this card
        elif action == 'q':
            if Confirm.ask("Are you sure you want to quit?", default=False):
                self.running = False
            return 'continue_pagination'  # Stay on this card unless quitting
        else:
            self.console.print(f"[yellow]Unknown command. Press Enter to mark as studied, 'h' for help[/yellow]")
            return 'continue_pagination'  # Stay on this card

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
        """Switch back to grammar study mode"""
        if self.current_mode == 'grammar':
            self.console.print("[yellow]Already in grammar mode[/yellow]")
            return

        self.current_mode = 'grammar'
        self.console.print("\n📚 [bold]Grammar Mode[/bold]\n")

        if self.current_card:
            if self.card_flipped:
                self._display_card_back()
            else:
                self._display_card_front()

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
            return

        self.console.print(f"🤖 Requesting definitions for vocabulary words: {', '.join(words)}...")

        result = self.api.request_definitions(
            username=self.profile_name,
            words=words,
            card_context=card
        )

        if result.get('success'):
            self.console.print(Panel(
                "[cyan]Claude is generating vocabulary definitions...[/cyan]\n"
                "New cards will be added to the vocabulary queue.",
                title="Claude SDK Processing",
                border_style="purple"
            ))

            # Set claude_processing flag (for grammar mode behavior)
            self.claude_processing = True

            # Wait a moment for processing, then check queue status
            import time
            time.sleep(2)  # Give it a moment to process

            # Check and display updated queue status
            self._show_vocabulary_queue_status()

            # For LIFO stack behavior, get the most recently added card
            new_card_result = self.api.get_next_vocabulary_card(self.profile_name)
            if new_card_result.get('success') and new_card_result.get('card'):
                # Display the newly created card immediately (top of stack)
                new_card = new_card_result['card']
                self.current_card = new_card
                self.display.reset_pagination()
                self.display.display_card_full(new_card)
                self._show_vocabulary_actions()
                self.console.print("[green]✅ New vocabulary card ready (top of stack)![/green]")
            else:
                self.console.print("[yellow]No new vocabulary card available yet[/yellow]")
                # Show current card again
                self._show_vocabulary_actions()

        else:
            error_msg = result.get('error', 'Unknown error')
            self.console.print(f"[red]Failed to request definitions: {error_msg}[/red]")

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
[bold cyan]Vocabulary Mode Help:[/bold cyan]

[bold]Study Commands:[/bold]
  [yellow]Enter[/yellow]    - Next page, or mark as studied at end
  [yellow]3[/yellow]        - Explicitly mark as studied

[bold]Navigation:[/bold]
  [yellow]Enter/n[/yellow]  - Next page (when card has multiple pages)
  [yellow]b/p[/yellow]      - Previous page

[bold]Learning Commands:[/bold]
  [yellow]d[/yellow]        - Define words from this card with Claude SDK
  [yellow]g[/yellow]        - Switch back to grammar mode
  [yellow]h/?[/yellow]      - Show this help
  [yellow]q[/yellow]        - Quit session

[bold]Tips:[/bold]
• Use 'n' to navigate through long vocabulary cards page by page
• Press Enter when done reading to mark as studied
• Define unfamiliar words for better learning
• New cards are added to TOP of stack (LIFO) - newest first
• Switch between grammar and vocabulary modes as needed
• All studied cards are cached for batch submission
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
            self.console.print("\n🔄 Closing session...")
            try:
                self.api.close_all_sessions(self.profile_name)
                self.console.print("✅ Session closed")
            except Exception as e:
                logger.error(f"Error closing session: {e}")

        self.console.print("👋 [bold]Goodbye![/bold]\n")
