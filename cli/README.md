# AnkiChat CLI

Command-line interface for studying Anki cards in your terminal.

## Features

- 🎯 **Interactive study sessions** - Natural keyboard-driven workflow
- 📄 **Paginated card display** - Long cards displayed in readable chunks
- 🤖 **Claude SDK integration** - Define words and auto-create vocabulary cards
- 📊 **Dual session support** - Grammar and vocabulary study modes
- 🔄 **Auto-managed server** - Starts and stops automatically
- 🎨 **Beautiful terminal UI** - Powered by Rich library

## Installation

### With uv (recommended)

```bash
# Install globally
uv tool install ankichat[cli]

# Or run without installing
uvx ankichat-cli study
```

### With pip

```bash
# Install in development mode
pip install -e ".[cli]"

# Use the CLI
ankichat-cli study
```

## Usage

### Interactive Study Session (Default)

```bash
# Start interactive study (auto-selects deck)
ankichat-cli study

# Or run without subcommand
ankichat-cli

# Start specific deck (skip selection)
ankichat-cli study --deck 5
```

### Other Commands

```bash
# Sync with AnkiWeb
ankichat-cli sync

# Show deck statistics
ankichat-cli stats

# List available decks
ankichat-cli decks

# Show version
ankichat-cli version

# Show help
ankichat-cli --help
```

## Keyboard Shortcuts

During study session:

### Study Commands
- `f` - Flip card to show back
- `1` - Answer: Again (wrong, repeat soon)
- `2` - Answer: Hard (difficult, shorter interval)
- `3` - Answer: Good (correct, normal interval)
- `4` - Answer: Easy (too easy, longer interval)

### Navigation
- `Enter` - Next page (when card has multiple pages)
- `b` - Previous page

### Session Commands
- `d` - Define words with Claude SDK
- `v` - Switch to vocabulary mode
- `g` - Switch to grammar mode
- `s` - Show session statistics
- `h` - Show help
- `q` - Quit session

## Example Session

```bash
$ ankichat-cli study

🚀 Starting AnkiChat CLI...
✅ Connected to API server at http://localhost:8000

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

┌─────────────────────────────────────────────┐
│ CARD - FRONT (Page 1/1)                     │
├─────────────────────────────────────────────┤
│ Word: menni                                 │
│ Sentence: Hova mész?                        │
├─────────────────────────────────────────────┤
│ [f] Flip  [d] Define  [h] Help  [q] Quit   │
└─────────────────────────────────────────────┘

> f

┌─────────────────────────────────────────────┐
│ CARD - BACK (Page 1/1)                      │
├─────────────────────────────────────────────┤
│ Word: menni                                 │
│ Translation: to go                          │
│ Explanation: Infinitive form of the verb... │
├─────────────────────────────────────────────┤
│ 1 Again  2 Hard  3 Good  4 Easy            │
└─────────────────────────────────────────────┘

> 3

✅ Card answered: Good

[Next card displays...]
```

## Configuration

### Environment Variables

- `ANKICHAT_HOST` - API server host (default: `localhost`)
- `ANKICHAT_PORT` - API server port (default: `8000`)

Example:

```bash
export ANKICHAT_HOST=localhost
export ANKICHAT_PORT=8000
ankichat-cli study
```

### Command Line Options

```bash
# Use custom server
ankichat-cli --host localhost --port 8000 study

# Enable verbose logging
ankichat-cli --verbose study
```

## How It Works

The CLI acts as a thin client that communicates with the web app API:

1. **Auto-starts API server** - CLI automatically starts `web_app.enhanced_main` in the background
2. **Makes HTTP requests** - All operations go through `/api/*` endpoints
3. **Displays in terminal** - Responses are rendered with Rich library
4. **Auto-stops on exit** - Server is cleaned up when CLI exits

This architecture means:
- ✅ No code duplication
- ✅ Bug fixes benefit both web and CLI
- ✅ Can use both interfaces simultaneously
- ✅ Simple implementation (~1400 lines total)

## Troubleshooting

### Server won't start

```bash
# Check if web app can start manually
python -m web_app.enhanced_main serve

# Check for port conflicts
lsof -i :8000
```

### Connection refused

```bash
# Verify server is running
curl http://localhost:8000/api/health

# Try different port
ankichat-cli --port 8001 study
```

### Import errors

```bash
# Install CLI dependencies
pip install -e ".[cli]"

# Or with uv
uv pip install -e ".[cli]"
```

## Development

### Project Structure

```
cli/
├── __init__.py       # Package init
├── server.py         # Server lifecycle management
├── client.py         # API client wrapper
├── display.py        # Card display and pagination
├── session.py        # Interactive study session
└── main.py           # CLI entry point (Click)
```

### Running Tests

```bash
# Run CLI tests
pytest tests/cli/

# Test specific functionality
python -m cli.main study --verbose
```

### Adding New Commands

1. Add command function to `cli/main.py`:

```python
@cli.command()
@click.pass_context
def mycommand(ctx):
    """My new command"""
    # Implementation
```

2. Add API method to `cli/client.py` if needed
3. Update this README

## License

Same as AnkiChat project.
