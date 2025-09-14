#!/usr/bin/env python3
"""
AnkiChat Web Interface - A global UV tool for web-based Anki study sessions.
"""

import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import typer

# Add the project root to the path for imports
project_root = Path(__file__).parents[1]
sys.path.insert(0, str(project_root))

from AnkiClient.src.operations import deck_ops, study_ops, card_ops

app = FastAPI(title="AnkiChat Web Interface", description="Web interface for Anki study sessions")

# Setup static files and templates
static_path = Path(__file__).parent / "static"
templates_path = Path(__file__).parent / "templates"

if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")

if templates_path.exists():
    templates = Jinja2Templates(directory=templates_path)

# Global state
current_user = None
current_deck_id = None
study_session = {}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - user selection and deck loading."""
    if not templates_path.exists():
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>AnkiChat Web Interface</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body { font-family: 'Segoe UI', sans-serif; background: #1a1a1a; color: #ffffff; min-height: 100vh; }
                .container { max-width: 800px; margin: 0 auto; padding: 20px; }
                .header { text-align: center; margin-bottom: 40px; }
                .card { background: #2d2d2d; border-radius: 12px; padding: 30px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
                .form-group { margin-bottom: 20px; }
                label { display: block; margin-bottom: 8px; font-weight: 500; }
                input, select { width: 100%; padding: 12px; border: 2px solid #404040; border-radius: 8px; background: #1a1a1a; color: #ffffff; font-size: 16px; }
                input:focus, select:focus { outline: none; border-color: #0084ff; }
                .btn { background: #0084ff; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; transition: all 0.2s; }
                .btn:hover { background: #0066cc; transform: translateY(-1px); }
                .btn:disabled { background: #404040; cursor: not-allowed; transform: none; }
                #deck-list { margin-top: 20px; }
                .deck-item { background: #404040; border-radius: 8px; padding: 15px; margin-bottom: 10px; cursor: pointer; transition: all 0.2s; }
                .deck-item:hover { background: #505050; transform: translateX(5px); }
                .deck-item.selected { background: #0084ff; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🃏 AnkiChat Web Interface</h1>
                    <p>Study your Anki decks with a modern web interface</p>
                </div>

                <div class="card">
                    <h2>Select User</h2>
                    <div class="form-group">
                        <label for="username">Username:</label>
                        <input type="text" id="username" placeholder="Enter your Anki username">
                    </div>
                    <button class="btn" onclick="loadDecks()">Load Decks</button>
                </div>

                <div class="card" id="deck-selection" style="display: none;">
                    <h2>Select Deck</h2>
                    <div id="deck-list"></div>
                    <button class="btn" id="start-study" onclick="startStudy()" disabled>Start Study Session</button>
                </div>
            </div>

            <script>
                let selectedDeck = null;
                let currentUser = null;

                async function loadDecks() {
                    const username = document.getElementById('username').value.trim();
                    if (!username) {
                        alert('Please enter a username');
                        return;
                    }

                    currentUser = username;

                    try {
                        const response = await fetch('/api/decks', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ username })
                        });

                        const decks = await response.json();
                        displayDecks(decks);
                    } catch (error) {
                        alert('Error loading decks: ' + error.message);
                    }
                }

                function displayDecks(decks) {
                    const deckList = document.getElementById('deck-list');
                    const deckSelection = document.getElementById('deck-selection');

                    if (!decks || decks.length === 0) {
                        deckList.innerHTML = '<p>No decks found for this user.</p>';
                    } else {
                        deckList.innerHTML = decks.map(deck => `
                            <div class="deck-item" onclick="selectDeck(${deck.id}, '${deck.name}')">
                                <strong>${deck.name}</strong>
                                <div style="font-size: 14px; opacity: 0.7; margin-top: 5px;">
                                    ID: ${deck.id}
                                </div>
                            </div>
                        `).join('');
                    }

                    deckSelection.style.display = 'block';
                }

                function selectDeck(deckId, deckName) {
                    // Remove previous selection
                    document.querySelectorAll('.deck-item').forEach(item => {
                        item.classList.remove('selected');
                    });

                    // Add selection to clicked item
                    event.target.closest('.deck-item').classList.add('selected');

                    selectedDeck = { id: deckId, name: deckName };
                    document.getElementById('start-study').disabled = false;
                }

                function startStudy() {
                    if (!selectedDeck || !currentUser) {
                        alert('Please select a deck and user');
                        return;
                    }

                    window.location.href = `/study?user=${encodeURIComponent(currentUser)}&deck_id=${selectedDeck.id}&deck_name=${encodeURIComponent(selectedDeck.name)}`;
                }
            </script>
        </body>
        </html>
        """)

    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/decks")
async def get_decks(request: Request):
    """Get decks for a specific user."""
    try:
        data = await request.json()
        username = data.get("username")

        if not username:
            raise HTTPException(status_code=400, detail="Username is required")

        decks_response = deck_ops.get_decks(username)

        # Debug: log what we actually received
        print(f"DEBUG: deck_ops.get_decks returned: {type(decks_response)} -> {decks_response}")

        # Handle different response formats
        if isinstance(decks_response, list):
            print(f"DEBUG: Returning list of {len(decks_response)} decks")
            return decks_response
        elif isinstance(decks_response, dict):
            print(f"DEBUG: Got dict with keys: {list(decks_response.keys())}")
            # Check if it's an error response or wrapped data
            if 'error' in decks_response:
                raise HTTPException(status_code=500, detail=decks_response['error'])
            # If it's a dict with a 'decks' key or similar, extract it
            if 'decks' in decks_response:
                print(f"DEBUG: Extracting 'decks' key")
                return decks_response['decks']
            # If it looks like a single deck object, wrap in array
            if 'id' in decks_response and 'name' in decks_response:
                print(f"DEBUG: Wrapping single deck in array")
                return [decks_response]
            # Otherwise return the dict as-is and let frontend handle it
            print(f"DEBUG: Returning dict as-is")
            return decks_response
        else:
            # Fallback: return empty array
            print(f"DEBUG: Returning empty array for unknown type: {type(decks_response)}")
            return []

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/study", response_class=HTMLResponse)
async def study_interface(request: Request, user: str, deck_id: int, deck_name: str):
    """Study interface page."""
    global current_user, current_deck_id
    current_user = user
    current_deck_id = deck_id

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Study: {deck_name} - AnkiChat</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Segoe UI', sans-serif; background: #1a1a1a; color: #ffffff; min-height: 100vh; display: flex; flex-direction: column; }}
            .header {{ background: #2d2d2d; padding: 20px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.3); }}
            .container {{ flex: 1; max-width: 800px; margin: 0 auto; padding: 20px; display: flex; flex-direction: column; }}
            .card {{ background: #2d2d2d; border-radius: 12px; padding: 30px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); flex: 1; }}
            .card-content {{ font-size: 24px; line-height: 1.6; text-align: center; min-height: 200px; display: flex; align-items: center; justify-content: center; }}
            .controls {{ display: flex; justify-content: center; gap: 10px; margin-top: 30px; }}
            .btn {{ background: #0084ff; color: white; border: none; padding: 15px 25px; border-radius: 8px; cursor: pointer; font-size: 16px; transition: all 0.2s; }}
            .btn:hover {{ background: #0066cc; transform: translateY(-1px); }}
            .btn:disabled {{ background: #404040; cursor: not-allowed; transform: none; }}
            .btn.secondary {{ background: #404040; }}
            .btn.secondary:hover {{ background: #505050; }}
            .ease-buttons {{ display: none; gap: 10px; }}
            .ease-btn {{ background: #666; padding: 10px 15px; border-radius: 6px; cursor: pointer; transition: all 0.2s; }}
            .ease-btn:hover {{ background: #777; }}
            .ease-btn.again {{ background: #dc3545; }}
            .ease-btn.hard {{ background: #fd7e14; }}
            .ease-btn.good {{ background: #28a745; }}
            .ease-btn.easy {{ background: #007bff; }}
            .stats {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; font-size: 14px; opacity: 0.7; }}
            .back-link {{ position: absolute; top: 20px; left: 20px; color: #0084ff; text-decoration: none; }}
            .back-link:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="header">
            <a href="/" class="back-link">← Back to Decks</a>
            <h1>📚 Studying: {deck_name}</h1>
            <p>User: {user}</p>
        </div>

        <div class="container">
            <div class="stats">
                <span id="session-stats">Click "Start Session" to begin</span>
                <span id="card-counter"></span>
            </div>

            <div class="card">
                <div class="card-content" id="card-content">
                    <p>Ready to start studying?</p>
                </div>

                <div class="controls">
                    <button class="btn" id="start-btn" onclick="startSession()">Start Session</button>
                    <button class="btn secondary" id="flip-btn" onclick="flipCard()" style="display: none;">Show Answer</button>
                    <button class="btn secondary" id="close-btn" onclick="closeSession()" style="display: none;">End Session</button>
                </div>

                <div class="controls ease-buttons" id="ease-buttons">
                    <button class="ease-btn again" onclick="answerCard(1)">Again</button>
                    <button class="ease-btn hard" onclick="answerCard(2)">Hard</button>
                    <button class="ease-btn good" onclick="answerCard(3)">Good</button>
                    <button class="ease-btn easy" onclick="answerCard(4)">Easy</button>
                </div>
            </div>
        </div>

        <script>
            let sessionActive = false;
            let cardFlipped = false;
            let cardCount = 0;

            const deckId = {deck_id};
            const username = "{user}";

            async function startSession() {{
                try {{
                    const data = await makeStudyRequest('/api/study/start', {{
                        deck_id: deckId, username, action: 'start'
                    }});

                    if (data.message && data.message.includes('No more cards')) {{
                        document.getElementById('card-content').innerHTML = '<p>🎉 No more cards to review! Well done!</p>';
                        return;
                    }}

                    sessionActive = true;
                    cardFlipped = false;
                    cardCount++;

                    displayCard(data.front || data);

                    document.getElementById('start-btn').style.display = 'none';
                    document.getElementById('flip-btn').style.display = 'inline-block';
                    document.getElementById('close-btn').style.display = 'inline-block';
                    document.getElementById('session-stats').textContent = 'Session active - Front side shown';
                    document.getElementById('card-counter').textContent = `Card #${{cardCount}}`;

                }} catch (error) {{
                    alert('Error starting session: ' + error.message);
                }}
            }}

            async function flipCard() {{
                if (!sessionActive) return;

                try {{
                    const data = await makeStudyRequest('/api/study/flip', {{
                        deck_id: deckId, username, action: 'flip'
                    }});
                    cardFlipped = true;

                    displayCard(data.back || data);

                    document.getElementById('flip-btn').style.display = 'none';
                    document.getElementById('ease-buttons').style.display = 'flex';
                    document.getElementById('session-stats').textContent = 'Back side shown - Choose difficulty';

                }} catch (error) {{
                    alert('Error flipping card: ' + error.message);
                }}
            }}

            async function answerCard(ease) {{
                if (!sessionActive || !cardFlipped) return;

                try {{
                    const data = await makeStudyRequest('/api/study/answer', {{
                        deck_id: deckId, username, action: ease.toString()
                    }});

                    if (data.message && data.message.includes('No more cards')) {{
                        document.getElementById('card-content').innerHTML = '<p>🎉 No more cards to review! Session complete!</p>';
                        document.getElementById('ease-buttons').style.display = 'none';
                        document.getElementById('close-btn').style.display = 'inline-block';
                        document.getElementById('session-stats').textContent = 'Session complete!';
                        return;
                    }}

                    cardFlipped = false;
                    cardCount++;

                    displayCard(data.front || data);

                    document.getElementById('flip-btn').style.display = 'inline-block';
                    document.getElementById('ease-buttons').style.display = 'none';
                    document.getElementById('session-stats').textContent = 'Next card - Front side shown';
                    document.getElementById('card-counter').textContent = `Card #${{cardCount}}`;

                }} catch (error) {{
                    alert('Error answering card: ' + error.message);
                }}
            }}

            async function closeSession(silent = false) {{
                if (!sessionActive && !silent) return;

                try {{
                    await fetch('/api/study/close', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ deck_id: deckId, username, action: 'close' }})
                    }});

                    sessionActive = false;

                    if (!silent) {{
                        window.location.href = '/';
                    }}

                }} catch (error) {{
                    if (!silent) {{
                        console.error('Error closing session:', error);
                        // Still redirect even if close fails
                        window.location.href = '/';
                    }}
                }}
            }}

            // Cleanup when page is being unloaded
            window.addEventListener('beforeunload', function(e) {{
                if (sessionActive) {{
                    closeSession(true);
                    // Note: synchronous request in beforeunload is limited, but we try
                    navigator.sendBeacon('/api/study/close', JSON.stringify({{
                        deck_id: deckId, username, action: 'close'
                    }}));
                }}
            }});

            // Cleanup when page becomes hidden (mobile/tab switching)
            document.addEventListener('visibilitychange', function() {{
                if (document.hidden && sessionActive) {{
                    closeSession(true);
                }}
            }});

            // Cleanup on navigation away from study page
            window.addEventListener('pagehide', function(e) {{
                if (sessionActive) {{
                    closeSession(true);
                }}
            }});

            // Handle server disconnection gracefully
            async function makeStudyRequest(endpoint, data) {{
                try {{
                    const response = await fetch(endpoint, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(data)
                    }});

                    if (!response.ok) {{
                        if (response.status >= 500) {{
                            throw new Error('Server connection lost. Study session ended.');
                        }}
                        throw new Error(`Server error: ${{response.status}}`);
                    }}

                    return await response.json();
                }} catch (error) {{
                    if (error.name === 'TypeError' && error.message.includes('fetch')) {{
                        // Network error - server probably stopped
                        sessionActive = false;
                        throw new Error('Server connection lost. Please restart the AnkiAPI server.');
                    }}
                    throw error;
                }}
            }}

            function displayCard(cardData) {{
                const content = document.getElementById('card-content');

                if (typeof cardData === 'string') {{
                    content.innerHTML = cardData;
                    return;
                }}

                if (cardData && typeof cardData === 'object') {{
                    let html = '';
                    for (const [field, value] of Object.entries(cardData)) {{
                        if (field !== 'card_id' && field !== 'media_files' && field !== 'ease_options') {{
                            html += `<div><strong>${{field}}:</strong> ${{value}}</div>`;
                        }}
                    }}
                    content.innerHTML = html || '<p>No content to display</p>';
                }} else {{
                    content.innerHTML = '<p>Loading...</p>';
                }}
            }}
        </script>
    </body>
    </html>
    """)

@app.post("/api/study/start")
async def study_start(request: Request):
    """Start a study session."""
    try:
        data = await request.json()
        result, status_code = study_ops.study(
            deck_id=data["deck_id"],
            action="start",
            username=data["username"]
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/study/flip")
async def study_flip(request: Request):
    """Flip the current card."""
    try:
        data = await request.json()
        result, status_code = study_ops.study(
            deck_id=data["deck_id"],
            action="flip",
            username=data["username"]
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/study/answer")
async def study_answer(request: Request):
    """Answer the current card."""
    try:
        data = await request.json()
        result, status_code = study_ops.study(
            deck_id=data["deck_id"],
            action=data["action"],
            username=data["username"]
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/study/close")
async def study_close(request: Request):
    """Close the study session."""
    try:
        # Handle both JSON and raw text (from beacon)
        content_type = request.headers.get('content-type', '')

        if content_type.startswith('application/json'):
            data = await request.json()
        else:
            # Handle beacon request or other formats
            body = await request.body()
            try:
                import json
                data = json.loads(body.decode('utf-8'))
            except:
                # Fallback for malformed requests
                return {"message": "Session closed (fallback)"}

        result, status_code = study_ops.study(
            deck_id=data["deck_id"],
            action="close",
            username=data["username"]
        )
        return result
    except Exception as e:
        # Don't raise error for close requests - just log and return success
        print(f"Warning: Error closing study session: {e}")
        return {"message": "Session closed"}

def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Run the web interface server."""
    print(f"🚀 Starting AnkiChat Web Interface on http://{host}:{port}")
    print("🃏 Access your Anki study sessions through the web interface")
    uvicorn.run(app, host=host, port=port)

# CLI interface using typer
cli = typer.Typer(help="AnkiChat Web Interface - Global UV tool for Anki study sessions")

@cli.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind the server to"),
    port: int = typer.Option(8000, help="Port to bind the server to"),
):
    """Start the AnkiChat web interface server."""
    run_server(host, port)

def main():
    """Main entry point for the CLI."""
    cli()

if __name__ == "__main__":
    main()