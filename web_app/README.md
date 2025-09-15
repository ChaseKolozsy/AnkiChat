# AnkiChat Web Interface

A modern web interface for Anki study sessions, available as a global UV tool.

## Features

- 🃏 **Dark Mode Theme**: Clean, modern dark interface designed for extended study sessions
- 👤 **User Selection**: Easy username input to load personal Anki collections
- 📚 **Deck Loading**: Browse and select from all available decks
- 🎯 **Study Sessions**: Interactive study interface with card flipping and rating
- 🌐 **Web-based**: Access from any modern web browser
- 🔧 **Global Tool**: Available system-wide via UV package manager

## Installation

The web interface is included when you install AnkiChat as a UV tool:

```bash
uv tool install . --force
```

## Usage

### Start the Web Interface

From any directory, run:

```bash
anki-chat-web
```

Or specify custom host/port:

```bash
anki-chat-web --host 0.0.0.0 --port 8080
```

Then open your browser to `http://localhost:8000` (or your specified host/port).

### Study Workflow

1. **Enter Username**: Input your Anki username to load your collection
2. **Select Deck**: Choose from your available decks
3. **Start Session**: Begin studying with the interactive interface
4. **Study Cards**:
   - View the front of each card
   - Click "Show Answer" to flip the card
   - Rate your performance (Again, Hard, Good, Easy)
   - Continue until all cards are reviewed

## Architecture

The web interface integrates with AnkiClient operations:

- Uses `deck_ops.py` for deck loading and management
- Uses `study_ops.py` for study session management
- Communicates with the AnkiApi backend (must be running on localhost:5001)
- Built with FastAPI for the backend and vanilla JavaScript for the frontend

## Repository Context

When run from within an AnkiChat repository, the web interface has full access to:

- AnkiClient operations for deck and study management
- AnkiApi endpoints for core Anki functionality
- Local Anki collections and media files
- All study session features and custom study options

## Requirements

- Python 3.10+
- AnkiApi server running on localhost:5001
- Access to Anki collections (typically in `~/.local/share/Anki2/`)

## Development

The web interface is designed for iterative development. The main components are:

- `web_app/main.py`: FastAPI application with embedded HTML/CSS/JS
- Integrated dark theme with modern styling
- RESTful API endpoints for study operations
- Global UV tool integration via pyproject.toml