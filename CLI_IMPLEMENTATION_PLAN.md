# AnkiChat CLI Implementation Plan

## Overview
Create a lightweight command-line interface that communicates with the existing web app as an API backend. The CLI will provide the same functionality as the web interface but with a text-based, paginated display suitable for terminal use.

## CLI Interaction Model

### Primary Mode: Interactive Session (Default)
The CLI operates primarily as an **interactive study session** - similar to using Anki desktop. Users enter a session where they can study cards with simple keyboard commands.

```bash
# Start interactive session (default behavior)
uvx ankichat-cli study              # Auto-select deck
uvx ankichat-cli study --deck 5     # Start specific deck
uvx ankichat-cli                    # Defaults to 'study' command
```

### Secondary Mode: One-Off Commands
Support individual commands for automation and quick operations:

```bash
uvx ankichat-cli sync               # Quick sync with AnkiWeb
uvx ankichat-cli stats              # Show deck statistics
uvx ankichat-cli decks              # List available decks
```

### Why Interactive Session?
- ✅ Natural study flow (like Anki desktop app)
- ✅ Server lifecycle managed automatically (starts/stops with session)
- ✅ One command to start studying
- ✅ Keeps context between cards
- ✅ Perfect for `uv tool install` global CLI pattern

## Architecture

```
┌─────────────────┐         HTTP/JSON          ┌──────────────────┐
│                 │  ────────────────────────>  │                  │
│   CLI Client    │                             │  Web App (API)   │
│  (New Code)     │  <────────────────────────  │  (Existing)      │
│                 │                             │                  │
└─────────────────┘                             └──────────────────┘
                                                         │
                                                         │
                                                         v
                                                ┌──────────────────┐
                                                │  AnkiClient Ops  │
                                                │  Claude SDK      │
                                                │  Anki Backend    │
                                                └──────────────────┘
```

**Key Benefits:**
- No code duplication - all business logic stays in web app
- Web app requires zero or minimal changes
- CLI and web UI can run simultaneously
- Easy to maintain and debug
- Same API for both interfaces

---

## Phase 1: Core CLI Infrastructure

### 1.1 Project Structure
```
AnkiChat/
├── cli/
│   ├── __init__.py
│   ├── client.py          # API client wrapper
│   ├── display.py         # Terminal rendering & pagination
│   ├── session.py         # Study session management
│   └── main.py            # CLI entry point
├── web_app/
│   └── enhanced_main.py   # Existing web app (minimal changes)
└── scripts/
    └── ankichat-cli       # CLI launcher script
```

### 1.2 Dependencies
```toml
# Add to pyproject.toml
[project.scripts]
ankichat-cli = "cli.main:cli"

[project.optional-dependencies]
cli = [
    "requests>=2.31.0",
    "rich>=13.0.0",        # Beautiful terminal output
    "click>=8.1.0",        # CLI argument parsing
    "prompt-toolkit>=3.0"  # Advanced input handling
]
```

**Installation & Usage:**
```bash
# Install globally with uv
uv tool install ankichat[cli]

# Or run without install
uvx ankichat-cli study

# After install, use directly
ankichat-cli study
```

### 1.3 Server Lifecycle Management (`cli/server.py`)

**Auto-start server when CLI launches, auto-stop on exit:**

```python
import subprocess
import time
import requests
import atexit

_server_process = None

def ensure_server_running(host='localhost', port=8000):
    """Start web app server if not running, return server URL"""
    global _server_process

    server_url = f"http://{host}:{port}"

    # Check if already running
    try:
        response = requests.get(f"{server_url}/api/health", timeout=2)
        if response.status_code == 200:
            return server_url
    except:
        pass

    # Start server in background
    _server_process = subprocess.Popen(
        ['python', '-m', 'web_app.enhanced_main', 'serve',
         '--host', host, '--port', str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for server to be ready
    for _ in range(10):
        time.sleep(1)
        try:
            response = requests.get(f"{server_url}/api/health", timeout=1)
            if response.status_code == 200:
                atexit.register(cleanup_server)
                return server_url
        except:
            continue

    raise RuntimeError("Failed to start API server")

def cleanup_server():
    """Cleanup server process on exit"""
    global _server_process
    if _server_process:
        _server_process.terminate()
        _server_process.wait(timeout=5)
```

### 1.4 API Client Class (`cli/client.py`)
Create a simple HTTP client that wraps all API endpoints:

```python
class AnkiChatAPIClient:
    """HTTP client for AnkiChat web app API"""

    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()

    # Authentication
    def login_and_sync(self, profile_name, username, password, endpoint=None, upload=False)

    # Deck operations
    def get_decks(self, username)
    def get_deck_counts(self, deck_id, username)

    # Study session
    def start_dual_session(self, username, deck_id)
    def flip_card(self, username)
    def answer_grammar_card(self, username, card_id, answer, claude_processing=False)
    def close_all_sessions(self, username)

    # Vocabulary operations
    def get_vocabulary_queue_status(self, username)
    def get_next_vocabulary_card(self, username)
    def cache_vocabulary_answer(self, username, card_id, answer)
    def submit_vocabulary_session(self, username)

    # Claude SDK integration
    def request_definitions(self, username, words, card_context)
    def submit_cached_answer(self, username, card_id, answer)
```

---

## Phase 2: Terminal Display & Pagination

### 2.1 Card Display Engine (`cli/display.py`)

**Requirements:**
- Display card fields a few lines at a time
- Support pagination for long content
- Clear, readable formatting
- Handle both front/back display
- Show field names clearly

**Features:**
```python
class CardDisplay:
    """Handles paginated display of card content in terminal"""

    def __init__(self, lines_per_page=10):
        self.lines_per_page = lines_per_page
        self.current_page = 0

    def display_card_front(self, card_data)
    def display_card_back(self, card_data)
    def show_next_page()
    def show_previous_page()
    def reset_pagination()
```

**Example Output:**
```
┌─────────────────────────────────────────────────┐
│ GRAMMAR CARD - Front (Page 1/3)                 │
├─────────────────────────────────────────────────┤
│                                                 │
│ Word: menni                                     │
│                                                 │
│ Sentence: Hova mész?                            │
│                                                 │
│ Grammar_Code: V_INF                             │
│                                                 │
├─────────────────────────────────────────────────┤
│ [Enter] Next page  [f] Flip card  [q] Quit     │
└─────────────────────────────────────────────────┘
```

### 2.2 Pagination Strategy

For each card field:
1. Split content by newlines
2. Group into pages of N lines (configurable, default 10)
3. Track current page index
4. Show page indicator (e.g., "Page 2/5")
5. Allow navigation: Enter (next), b (back), f (flip)

**Handling Long Fields:**
```python
def paginate_field(field_content, lines_per_page=10):
    """Split field content into pages"""
    lines = field_content.split('\n')
    pages = []
    for i in range(0, len(lines), lines_per_page):
        pages.append('\n'.join(lines[i:i+lines_per_page]))
    return pages
```

### 2.3 Rich Terminal UI

Use `rich` library for:
- Color coding (grammar session = blue, vocabulary = orange)
- Tables for deck selection
- Progress bars for study counts
- Panels for card display
- Markdown rendering for card content

```python
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

console = Console()

def display_card(card_data, side="front"):
    """Display card using rich panels"""
    content = format_card_content(card_data, side)
    panel = Panel(content, title=f"Card - {side.upper()}",
                  border_style="blue")
    console.print(panel)
```

---

## Phase 3: Study Session Management

### 3.1 Grammar Study Session (`cli/session.py`)

```python
class GrammarStudySession:
    """Manages grammar study session flow"""

    def __init__(self, api_client, username, deck_id):
        self.api = api_client
        self.username = username
        self.deck_id = deck_id
        self.current_card = None
        self.card_flipped = False
        self.display = CardDisplay()

    async def start(self):
        """Start grammar session"""
        result = self.api.start_dual_session(self.username, self.deck_id)
        self.current_card = result['current_card']
        self.show_card_front()

    def show_card_front(self):
        """Display front of current card with pagination"""
        self.display.reset_pagination()
        self.display.display_card_front(self.current_card)
        self.card_flipped = False

    def flip_card(self):
        """Flip to show back of card"""
        result = self.api.flip_card(self.username)
        self.current_card = result['current_card']
        self.display.display_card_back(self.current_card)
        self.card_flipped = True

    def answer_card(self, answer):
        """Submit answer (1-4) and get next card"""
        result = self.api.answer_grammar_card(
            self.username,
            self.current_card['card_id'],
            answer
        )
        if result.get('next_card'):
            self.current_card = result['next_card']
            self.show_card_front()
```

### 3.2 Vocabulary Study Session

```python
class VocabularyStudySession:
    """Manages vocabulary queue and study"""

    def __init__(self, api_client, username):
        self.api = api_client
        self.username = username
        self.current_card = None
        self.display = CardDisplay()

    def get_queue_status(self):
        """Get current vocabulary queue status"""
        return self.api.get_vocabulary_queue_status(self.username)

    def get_next_card(self):
        """Get next vocabulary card from LIFO queue"""
        result = self.api.get_next_vocabulary_card(self.username)
        if result['card']:
            self.current_card = result['card']
            self.display.display_card_full(self.current_card)
            return True
        return False

    def answer_card(self, answer=3):
        """Cache vocabulary card answer (default: Good)"""
        self.api.cache_vocabulary_answer(
            self.username,
            self.current_card['card_id'],
            answer
        )

    def submit_session(self):
        """Submit all cached vocabulary answers"""
        return self.api.submit_vocabulary_session(self.username)
```

### 3.3 Session State Management

Track:
- Current session type (grammar/vocabulary)
- Current card and flip state
- Pagination position
- Claude processing state
- Cached answers

---

## Phase 4: User Interaction Flow

### 4.1 Main CLI Entry Point (`cli/main.py`)

**Click-based CLI with default interactive session:**

```python
import click
import sys
from rich.console import Console
from cli.server import ensure_server_running
from cli.client import AnkiChatAPIClient
from cli.session import InteractiveStudySession

console = Console()

@click.group(invoke_without_command=True)
@click.pass_context
@click.option('--host', default='localhost', envvar='ANKICHAT_HOST',
              help='API server host')
@click.option('--port', default=8000, type=int, envvar='ANKICHAT_PORT',
              help='API server port')
def cli(ctx, host, port):
    """AnkiChat CLI - Study Anki cards in your terminal

    Run without arguments to start an interactive study session.
    """

    # Store in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj['HOST'] = host
    ctx.obj['PORT'] = port

    # If no subcommand, default to interactive study
    if ctx.invoked_subcommand is None:
        ctx.invoke(study)

@cli.command()
@click.pass_context
@click.option('--deck', type=int, help='Deck ID to study (skip selection)')
def study(ctx, deck):
    """Start interactive study session (default command)"""

    host = ctx.obj['HOST']
    port = ctx.obj['PORT']

    # Ensure server is running
    console.print("🚀 Starting AnkiChat CLI...")
    server_url = ensure_server_running(host, port)
    console.print(f"✅ Connected to API server")

    # Create API client
    api = AnkiChatAPIClient(server_url)

    # Start interactive session
    session = InteractiveStudySession(api, console)
    session.run(deck_id=deck)

@cli.command()
@click.pass_context
def sync(ctx):
    """Sync with AnkiWeb (one-off command)"""
    host = ctx.obj['HOST']
    port = ctx.obj['PORT']

    console.print("🔄 Syncing with AnkiWeb...")
    server_url = ensure_server_running(host, port)
    api = AnkiChatAPIClient(server_url)

    username = click.prompt("Username")
    password = click.prompt("Password", hide_input=True)

    result = api.login_and_sync(username, username, password)
    if result.get('success'):
        console.print("✅ Sync complete!")
    else:
        console.print(f"❌ Sync failed: {result.get('error')}")

@cli.command()
@click.pass_context
def stats(ctx):
    """Show deck statistics"""
    host = ctx.obj['HOST']
    port = ctx.obj['PORT']

    server_url = ensure_server_running(host, port)
    api = AnkiChatAPIClient(server_url)

    username = click.prompt("Username")
    # Show stats for all decks
    # ... implementation ...

@cli.command()
@click.pass_context
def decks(ctx):
    """List available decks"""
    host = ctx.obj['HOST']
    port = ctx.obj['PORT']

    server_url = ensure_server_running(host, port)
    api = AnkiChatAPIClient(server_url)

    username = click.prompt("Username")
    decks = api.get_decks(username)

    # Display decks table
    # ... implementation ...

if __name__ == '__main__':
    cli()
```

### 4.2 Interactive Study Session (`cli/session.py`)

**Main interactive loop with keyboard commands:**

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

class InteractiveStudySession:
    """Handles interactive study session with keybindings"""

    def __init__(self, api_client, console):
        self.api = api_client
        self.console = console
        self.prompt_session = PromptSession()
        self.running = True
        self.username = None
        self.current_card = None
        self.card_flipped = False
        self.current_mode = 'grammar'  # or 'vocabulary'

    def run(self, deck_id=None):
        """Main interactive loop"""

        try:
            # Login
            self.username = self._login()

            # Select deck
            if not deck_id:
                deck_id = self._select_deck()

            # Start study session
            result = self.api.start_dual_session(self.username, deck_id)
            self.current_card = result['current_card']

            # Display initial card
            self._display_card_front()

            # Main study loop
            while self.running:
                action = self._get_user_input()
                self._handle_action(action)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Session interrupted[/yellow]")
        finally:
            self._cleanup()

    def _login(self):
        """Login and sync"""
        self.console.print(Panel("Login to AnkiWeb", style="blue"))

        username = Prompt.ask("Username")
        password = Prompt.ask("Password", password=True)

        self.console.print("🔄 Syncing with AnkiWeb...")
        result = self.api.login_and_sync(username, username, password)

        if not result.get('success'):
            self.console.print(f"[red]Login failed: {result.get('error')}[/red]")
            sys.exit(1)

        self.console.print("✅ Login successful!")
        return username

    def _select_deck(self):
        """Interactive deck selection"""
        # ... deck selection UI ...
        pass

    def _get_user_input(self):
        """Get single character or command from user"""
        return self.prompt_session.prompt('> ').strip().lower()

    def _handle_action(self, action):
        """Handle user action"""
        if action == 'f':
            self._flip_card()
        elif action in ['1', '2', '3', '4']:
            if self.card_flipped:
                self._answer_card(int(action))
            else:
                self.console.print("[yellow]Flip card first (press 'f')[/yellow]")
        elif action == 'd':
            self._define_words()
        elif action == 'v':
            self._switch_to_vocabulary()
        elif action == 'g':
            self._switch_to_grammar()
        elif action == 's':
            self._show_stats()
        elif action == 'q':
            self._quit()
        elif action == '':  # Enter key
            self._next_page()
        elif action == 'b':
            self._previous_page()
        else:
            self._show_help()

    def _flip_card(self):
        """Flip current card"""
        result = self.api.flip_card(self.username)
        self.current_card = result['current_card']
        self.card_flipped = True
        self._display_card_back()

    def _answer_card(self, answer):
        """Submit answer and get next card"""
        result = self.api.answer_grammar_card(
            self.username,
            self.current_card['card_id'],
            answer
        )

        self.console.print(f"✅ Card answered: {['', 'Again', 'Hard', 'Good', 'Easy'][answer]}")

        if result.get('next_card'):
            self.current_card = result['next_card']
            self.card_flipped = False
            self._display_card_front()

    def _quit(self):
        """Quit session"""
        if Confirm.ask("Are you sure you want to quit?"):
            self.running = False

    def _cleanup(self):
        """Cleanup on exit"""
        self.console.print("🔄 Closing session...")
        self.api.close_all_sessions(self.username)
        self.console.print("👋 Goodbye!")
```

### 4.3 Example Session Flow

```bash
$ uvx ankichat-cli study

🚀 Starting AnkiChat CLI...
✅ Connected to API server

┌─────────────────────────────┐
│ Login to AnkiWeb            │
└─────────────────────────────┘

Username: chase
Password: ********
🔄 Syncing with AnkiWeb...
✅ Login successful!

📚 Select a deck:
┌───┬────────────────────┬─────┬──────────┬────────┐
│ # │ Deck Name          │ New │ Learning │ Review │
├───┼────────────────────┼─────┼──────────┼────────┤
│ 1 │ Hungarian Grammar  │ 15  │ 23       │ 42     │
│ 2 │ Vocabulary         │ 5   │ 8        │ 12     │
└───┴────────────────────┴─────┴──────────┴────────┘

Deck #: 1

🎯 Starting study session: Hungarian Grammar
📊 Cards today: 80 (15 new, 23 learning, 42 review)

┌─────────────────────────────────────────────┐
│ CARD - FRONT (Page 1/1)                     │
├─────────────────────────────────────────────┤
│ Word: menni                                 │
│ Sentence: Hova mész?                        │
│ Grammar_Code: V_INF                         │
├─────────────────────────────────────────────┤
│ [f] Flip  [d] Define  [v] Vocab  [q] Quit  │
└─────────────────────────────────────────────┘

> f

┌─────────────────────────────────────────────┐
│ CARD - BACK (Page 1/2)                      │
├─────────────────────────────────────────────┤
│ Word: menni                                 │
│ Translation: to go                          │
│ Explanation: Infinitive form...             │
│                                             │
│ [Enter] Next page                           │
├─────────────────────────────────────────────┤
│ [1] Again  [2] Hard  [3] Good  [4] Easy    │
└─────────────────────────────────────────────┘

> [Enter]

┌─────────────────────────────────────────────┐
│ CARD - BACK (Page 2/2)                      │
├─────────────────────────────────────────────┤
│ Example: Hova akarsz menni?                 │
├─────────────────────────────────────────────┤
│ [1] Again  [2] Hard  [3] Good  [4] Easy    │
└─────────────────────────────────────────────┘

> 3

✅ Card answered: Good
📊 Remaining: 79 cards

[Next card displays...]
```

### 4.4 Keyboard Shortcuts

**During Study Session:**

```
[f]        - Flip card to show back
[1]        - Answer: Again (wrong, repeat soon)
[2]        - Answer: Hard (difficult, repeat with shorter interval)
[3]        - Answer: Good (correct, normal interval)
[4]        - Answer: Easy (too easy, longer interval)
[Enter]    - Next page (when card has multiple pages)
[b]        - Previous page
[d]        - Define words with Claude SDK
[v]        - Switch to vocabulary mode
[g]        - Switch to grammar mode (from vocab)
[s]        - Show session statistics
[h]        - Show help/command list
[q]        - Quit session (with confirmation)
```

**Special Actions:**

```
[d] Define Words Flow:
1. User presses 'd'
2. Prompted: "Enter words to define (comma-separated):"
3. User enters: "menni, hova"
4. Claude SDK processes in background
5. Grammar answer is cached
6. User automatically switches to vocabulary mode
7. After completing vocab cards, can submit cached grammar answer
```

---

## Phase 5: Enhanced Features

### 5.1 Statistics Display

```python
def show_study_stats(api, username, deck_id):
    """Display study statistics"""
    counts = api.get_deck_counts(deck_id, username)

    table = Table(title="Study Statistics")
    table.add_column("Type", style="cyan")
    table.add_column("Count", style="magenta")

    table.add_row("New", str(counts['new']))
    table.add_row("Learning", str(counts['learning']))
    table.add_row("Review", str(counts['review']))
    table.add_row("Total", str(counts['total']))

    console.print(table)
```

### 5.2 Deck Selection UI

```python
def select_deck(decks):
    """Interactive deck selection"""
    table = Table(title="Available Decks")
    table.add_column("#", style="cyan")
    table.add_column("Deck Name", style="green")
    table.add_column("New", style="yellow")
    table.add_column("Learning", style="orange")
    table.add_column("Review", style="blue")

    for i, deck in enumerate(decks, 1):
        table.add_row(
            str(i),
            deck['name'],
            str(deck.get('new', '?')),
            str(deck.get('learning', '?')),
            str(deck.get('review', '?'))
        )

    console.print(table)

    choice = prompt('Select deck number: ')
    return decks[int(choice) - 1]
```

### 5.3 Vocabulary Queue Display

```python
def show_vocabulary_queue(vocab_session):
    """Show current vocabulary queue status"""
    status = vocab_session.get_queue_status()

    panel = Panel(
        f"""
Queue Length: {status['queue_length']}
Cached Answers: {status['cached_answers']}
In Progress: {status['in_progress']}
        """,
        title="Vocabulary Queue",
        border_style="orange"
    )
    console.print(panel)
```

### 5.4 Claude Integration Display

```python
def show_claude_processing():
    """Show that Claude is processing definitions"""
    console.print(Panel(
        "[cyan]Claude is generating vocabulary definitions...[/cyan]\n"
        "You can continue studying vocabulary cards while waiting.\n"
        "Your grammar answer has been cached.",
        title="🤖 Claude SDK Processing",
        border_style="purple"
    ))
```

---

## Phase 6: Web App Enhancements (Optional)

### 6.1 Minimal Changes Needed

The web app already has all necessary API endpoints. Only optional improvements:

**A. Add a health check endpoint:**
```python
@app.get("/api/health")
async def health_check():
    """Health check for CLI to verify server is running"""
    return {"status": "ok", "version": "1.0.0"}
```

**B. Add plain-text card rendering (optional):**
```python
@app.post("/api/card-text")
async def get_card_text(request: Request):
    """Return card content as plain text (no HTML)"""
    data = await request.json()
    # Strip HTML tags, return clean text
    return {"text": clean_text}
```

**C. Add session info endpoint (optional):**
```python
@app.get("/api/session-info")
async def session_info(request: Request):
    """Get current session state for CLI"""
    return {
        "grammar_active": claude_integration.grammar_session.active,
        "vocab_queue_length": len(claude_integration.vocabulary_queue.queue),
        "claude_processing": claude_integration.grammar_session.is_paused
    }
```

### 6.2 Server Configuration

**Recommended: Auto-start server (seamless UX)**

The CLI automatically starts the web app server in the background when launched, and stops it on exit. This is already implemented in `cli/server.py` (see Phase 1).

**Benefits:**
- ✅ One command to start studying: `uvx ankichat-cli study`
- ✅ No manual server management
- ✅ Server automatically cleaned up on exit
- ✅ Works perfectly for `uv tool install` pattern

**Alternative: Manual server (for development)**
```bash
# Terminal 1: Start API server manually
python -m web_app.enhanced_main serve

# Terminal 2: Use CLI
ankichat-cli study
```

This is useful during development to see server logs separately.

---

## Phase 7: Advanced Features

### 7.1 Offline Mode Support

Cache deck data locally for offline study:
```python
import json
from pathlib import Path

class OfflineCache:
    def __init__(self, cache_dir='~/.ankichat/cache'):
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_deck(self, deck_id, deck_data):
        cache_file = self.cache_dir / f"deck_{deck_id}.json"
        with open(cache_file, 'w') as f:
            json.dump(deck_data, f)

    def load_deck(self, deck_id):
        cache_file = self.cache_dir / f"deck_{deck_id}.json"
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                return json.load(f)
        return None
```

### 7.2 Configuration File

`~/.ankichat/config.toml`:
```toml
[server]
host = "localhost"
port = 8000

[display]
lines_per_page = 10
color_scheme = "default"  # or "nord", "dracula", etc.

[study]
auto_flip = false
show_answer_times = true
vocabulary_auto_good = true  # Auto-grade vocab as "Good"

[sync]
auto_sync_on_start = true
auto_sync_on_exit = true
```

### 7.3 Study Session Resumption

Save session state to resume later:
```python
class SessionState:
    def save(self, filepath):
        state = {
            'username': self.username,
            'deck_id': self.deck_id,
            'card_index': self.card_index,
            'timestamp': time.time()
        }
        with open(filepath, 'w') as f:
            json.dump(state, f)

    @classmethod
    def load(cls, filepath):
        with open(filepath, 'r') as f:
            state = json.load(f)
        return cls(**state)
```

### 7.4 Batch Operations

```python
@cli.command()
@click.option('--deck-id', type=int, help='Deck ID to study')
@click.option('--cards', type=int, default=10, help='Number of cards to study')
def quick_study(deck_id, cards):
    """Quick study session for N cards"""
    # Study specified number of cards in batch mode
    pass

@cli.command()
def sync():
    """Sync with AnkiWeb without starting study session"""
    pass

@cli.command()
def stats():
    """Show statistics for all decks"""
    pass
```

---

## Implementation Timeline

### Phase 1: Core Infrastructure
- [ ] Create project structure (`cli/` directory and files)
- [ ] Implement API client class with all endpoint wrappers
- [ ] Basic terminal display with `rich` library
- [ ] Simple card display (no pagination yet)

### Phase 2: Study Sessions
- [ ] Grammar study session flow (start, flip, answer)
- [ ] Card flipping and answering
- [ ] Vocabulary queue integration
- [ ] Basic keyboard shortcuts

### Phase 3: Pagination & Polish
- [ ] Implement pagination for long cards
- [ ] Improve terminal UI with colors/panels
- [ ] Add deck selection interface
- [ ] Statistics display

### Phase 4: Advanced Features
- [ ] Claude SDK integration prompts
- [ ] Vocabulary session flow
- [ ] Configuration file support
- [ ] Error handling and recovery

### Phase 5: Testing & Documentation
- [ ] Test with real Anki decks
- [ ] Handle edge cases
- [ ] Write user documentation
- [ ] Create installation script

---

## Testing Strategy

### Unit Tests
```python
# tests/test_client.py
def test_api_client_login():
    client = AnkiChatAPIClient("http://localhost:8000")
    # Mock response
    result = client.login_and_sync(...)
    assert result['success'] == True

# tests/test_display.py
def test_pagination():
    display = CardDisplay(lines_per_page=5)
    card = {"field": "line1\nline2\nline3\n...\nline20"}
    pages = display.paginate_card(card)
    assert len(pages) == 4  # 20 lines / 5 per page
```

### Integration Tests
```python
# tests/test_session.py
def test_full_study_session():
    # Start API server
    # Create CLI session
    # Simulate user input
    # Verify card progression
    pass
```

### Manual Testing Checklist
- [ ] Login and sync flow
- [ ] Deck selection
- [ ] Card display (short and long cards)
- [ ] Pagination navigation
- [ ] Card flipping
- [ ] Answer grading
- [ ] Vocabulary queue
- [ ] Claude SDK integration
- [ ] Session cleanup on exit

---

## Example Usage

```bash
# Installation
pip install -e ".[cli]"

# Start study session (auto-starts API server)
ankichat-cli study

# Or specify server manually
ankichat-cli study --host localhost --port 8000

# Quick sync
ankichat-cli sync

# Show stats
ankichat-cli stats

# Study specific deck with config
ankichat-cli study --deck 12345 --cards 20
```

---

## File Structure Summary

```
cli/
├── __init__.py              # Package init
├── server.py                # Server lifecycle management (~100 lines)
├── client.py                # AnkiChatAPIClient class (~200 lines)
├── display.py               # CardDisplay, pagination (~300 lines)
├── session.py               # InteractiveStudySession class (~500 lines)
├── main.py                  # CLI entry point, Click commands (~200 lines)
└── config.py                # Configuration management (~100 lines)

tests/
├── test_client.py
├── test_display.py
├── test_session.py
└── test_integration.py
```

**Total estimated code: ~1400 lines** (much less than duplicating web app logic!)

**Entry Point:**
- Installed as `ankichat-cli` command via `pyproject.toml` scripts
- Works with `uv tool install ankichat[cli]`
- Works with `uvx ankichat-cli`

---

## Quick Start Development Guide

### 1. Set Up Project Structure
```bash
cd /home/chase/AnkiChat
mkdir -p cli tests
touch cli/__init__.py cli/server.py cli/client.py cli/display.py cli/session.py cli/main.py
```

### 2. Install Dependencies
```bash
# Add CLI dependencies to pyproject.toml
uv add --optional cli requests rich click prompt-toolkit

# Install in development mode with CLI extras
uv pip install -e ".[cli]"
```

### 3. Test Basic Flow
```bash
# Start the CLI
python -m cli.main study

# Or after installation
ankichat-cli study
```

### 4. Iterate
Start with minimal functionality and iterate:
1. ✅ Server auto-start
2. ✅ API client basic methods
3. ✅ Simple card display (no pagination)
4. ✅ Login flow
5. ✅ Basic study loop (flip, answer)
6. ➡️ Add pagination
7. ➡️ Add vocabulary mode
8. ➡️ Add Claude integration

---

## Summary

**This approach keeps the CLI simple while leveraging all the existing functionality of the web app!**

- **~1400 lines of new code** vs thousands if duplicating logic
- **Interactive session by default** - natural study flow
- **Auto-managed server** - starts/stops automatically
- **Perfect for `uv tool install`** - global CLI pattern
- **Same API backend** - bug fixes benefit both interfaces
