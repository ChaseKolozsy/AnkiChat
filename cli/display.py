"""
Card display and pagination for terminal output

Handles rendering card content in a readable, paginated format.
"""

import logging
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)


class CardDisplay:
    """Handles paginated display of card content in terminal"""

    def __init__(self, console: Console, lines_per_page: int = 10):
        """
        Initialize card display

        Args:
            console: Rich console instance
            lines_per_page: Number of lines to show per page
        """
        self.console = console
        self.lines_per_page = lines_per_page
        self.current_page = 0
        self.pages: List[str] = []
        self.total_pages = 0

    def display_card_front(self, card_data: Dict[str, Any]):
        """Display front of card"""
        self._render_card(card_data, side="FRONT", color="blue")

    def display_card_back(self, card_data: Dict[str, Any]):
        """Display back of card"""
        self._render_card(card_data, side="BACK", color="green")

    def display_card_full(self, card_data: Dict[str, Any]):
        """Display full card content (for vocabulary cards)"""
        self._render_card(card_data, side="VOCABULARY", color="orange1")

    def _render_card(self, card_data: Dict[str, Any], side: str, color: str):
        """Render card content with pagination"""
        if not card_data:
            self.console.print("[yellow]No card data available[/yellow]")
            return

        # Extract card fields
        content = self._extract_card_content(card_data)

        if not content:
            self.console.print("[yellow]No content to display[/yellow]")
            return

        # Paginate content
        self.pages = self._paginate_content(content)
        self.total_pages = len(self.pages)
        self.current_page = 0

        # Display first page
        self._show_current_page(side, color)

    def _extract_card_content(self, card_data: Dict[str, Any]) -> str:
        """Extract displayable content from card data"""
        lines = []

        # Handle different card data structures
        if isinstance(card_data, dict):
            # Check for front/back structure
            if 'front' in card_data or 'back' in card_data:
                if card_data.get('front'):
                    lines.append("[bold cyan]FRONT:[/bold cyan]")
                    lines.extend(self._format_fields(card_data['front']))
                if card_data.get('back'):
                    lines.append("\n[bold green]BACK:[/bold green]")
                    lines.extend(self._format_fields(card_data['back']))
            # Check for fields structure
            elif 'fields' in card_data:
                lines.extend(self._format_fields(card_data['fields']))
            # Direct field iteration
            else:
                for key, value in card_data.items():
                    if self._is_displayable_field(key, value):
                        field_name = self._format_field_name(key)
                        cleaned_value = self._clean_html_content(str(value))
                        lines.append(f"[bold]{field_name}:[/bold] {cleaned_value}")

        return "\n".join(lines) if lines else "No content available"

    def _format_fields(self, fields: Dict[str, Any]) -> List[str]:
        """Format dictionary of fields into display lines"""
        lines = []
        for key, value in fields.items():
            if self._is_displayable_field(key, value):
                field_name = self._format_field_name(key)
                # Convert HTML <br> tags to newlines and clean up the content
                cleaned_value = self._clean_html_content(str(value))
                lines.append(f"[bold]{field_name}:[/bold] {cleaned_value}")
        return lines

    def _clean_html_content(self, content: str) -> str:
        """Clean HTML content by converting <br> tags to newlines and removing other HTML"""
        if not content:
            return content

        # Convert <br> and <br/> to actual newlines
        import re
        content = re.sub(r'<br\s*/?>', '\n', content)

        # Remove other HTML tags (keep the content)
        content = re.sub(r'<[^>]+>', '', content)

        # Clean up extra whitespace
        content = re.sub(r'\n\s*\n', '\n\n', content)  # Multiple newlines to double newline
        content = content.strip()

        return content

    def _is_displayable_field(self, key: str, value: Any) -> bool:
        """Check if field should be displayed"""
        # Skip metadata fields
        skip_fields = {'card_id', 'id', 'note_id', 'media_files', 'ease_options'}
        if key in skip_fields:
            return False

        # Skip empty values
        if not value or (isinstance(value, str) and not value.strip()):
            return False

        return True

    def _format_field_name(self, field_name: str) -> str:
        """Format field name for display"""
        return field_name.replace('_', ' ').title()

    def _paginate_content(self, content: str) -> List[str]:
        """Split content into pages"""
        lines = content.split('\n')

        if len(lines) <= self.lines_per_page:
            return [content]

        pages = []
        for i in range(0, len(lines), self.lines_per_page):
            page_lines = lines[i:i + self.lines_per_page]
            pages.append('\n'.join(page_lines))

        return pages

    def _show_current_page(self, side: str, color: str):
        """Show current page of card"""
        if not self.pages:
            return

        page_content = self.pages[self.current_page]
        page_indicator = f"Page {self.current_page + 1}/{self.total_pages}" if self.total_pages > 1 else ""

        title = f"CARD - {side}"
        if page_indicator:
            title += f" ({page_indicator})"

        panel = Panel(
            page_content,
            title=title,
            border_style=color,
            padding=(1, 2)
        )

        self.console.print(panel)

        # Show navigation hint if multiple pages
        if self.total_pages > 1 and self.current_page < self.total_pages - 1:
            self.console.print("[dim]Press [Enter] for more...[/dim]")

    def next_page(self) -> bool:
        """
        Show next page

        Returns:
            True if there was a next page, False otherwise
        """
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            return True
        return False

    def previous_page(self) -> bool:
        """
        Show previous page

        Returns:
            True if there was a previous page, False otherwise
        """
        if self.current_page > 0:
            self.current_page -= 1
            return True
        return False

    def reset_pagination(self):
        """Reset pagination to first page"""
        self.current_page = 0
        self.pages = []
        self.total_pages = 0

    def has_more_pages(self) -> bool:
        """Check if there are more pages to display"""
        return self.current_page < self.total_pages - 1


def display_deck_table(console: Console, decks: List[Dict[str, Any]]):
    """Display deck selection table"""
    table = Table(title="📚 Available Decks", show_header=True, header_style="bold cyan")

    table.add_column("#", style="cyan", width=4)
    table.add_column("Deck Name", style="green")
    table.add_column("New", style="yellow", justify="right")
    table.add_column("Learning", style="orange1", justify="right")
    table.add_column("Review", style="blue", justify="right")
    table.add_column("Total", style="magenta", justify="right")

    for i, deck in enumerate(decks, 1):
        # Try to get counts from deck data
        new = str(deck.get('new', '?'))
        learning = str(deck.get('learning', '?'))
        review = str(deck.get('review', '?'))
        total = str(deck.get('total', '?'))

        table.add_row(
            str(i),
            deck.get('name', 'Unknown'),
            new,
            learning,
            review,
            total
        )

    console.print(table)


def display_stats(console: Console, counts: Dict[str, int]):
    """Display study statistics"""
    table = Table(title="📊 Study Statistics", show_header=True, header_style="bold cyan")

    table.add_column("Type", style="cyan")
    table.add_column("Count", style="magenta", justify="right")

    table.add_row("New", str(counts.get('new', 0)))
    table.add_row("Learning", str(counts.get('learning', 0)))
    table.add_row("Review", str(counts.get('review', 0)))
    table.add_row("Total", str(counts.get('total', 0)))

    console.print(table)


def display_vocabulary_queue(console: Console, status: Dict[str, Any]):
    """Display vocabulary queue status"""
    content = f"""
Queue Length: {status.get('queue_length', 0)}
Cached Answers: {status.get('cached_answers', 0)}
In Progress: {status.get('in_progress', 0)}
    """.strip()

    panel = Panel(
        content,
        title="📖 Vocabulary Queue",
        border_style="orange1",
        padding=(1, 2)
    )

    console.print(panel)


def show_help(console: Console):
    """Display help with keyboard shortcuts"""
    help_text = """
[bold cyan]Keyboard Shortcuts:[/bold cyan]

[bold]Study Commands:[/bold]
  [yellow]f[/yellow]        - Flip card to show back
  [yellow]1[/yellow]        - Answer: Again (wrong, repeat soon)
  [yellow]2[/yellow]        - Answer: Hard (difficult, shorter interval)
  [yellow]3[/yellow]        - Answer: Good (correct, normal interval)
  [yellow]4[/yellow]        - Answer: Easy (too easy, longer interval)

[bold]Navigation:[/bold]
  [yellow]Enter[/yellow]    - Next page (when card has multiple pages)
  [yellow]b[/yellow]        - Previous page

[bold]Session Commands:[/bold]
  [yellow]d[/yellow]        - Define words with Claude SDK
  [yellow]v[/yellow]        - Switch to vocabulary mode
  [yellow]g[/yellow]        - Switch to grammar mode
  [yellow]s[/yellow]        - Show session statistics
  [yellow]h[/yellow]        - Show this help
  [yellow]q[/yellow]        - Quit session

[dim]Tip: You must flip the card before you can answer it![/dim]
    """.strip()

    panel = Panel(
        help_text,
        title="Help",
        border_style="cyan",
        padding=(1, 2)
    )

    console.print(panel)
