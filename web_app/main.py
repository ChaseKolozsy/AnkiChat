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
from web_app.claude_sdk_integration import define_with_context_async, build_source_context_from_payload
import asyncio
import time
from typing import Dict, List, Any, Tuple, Set

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

# In-memory wiring for new vocab flow
cached_answers: Dict[str, Dict[int, int]] = {}
seen_cards_in_deck: Dict[Tuple[str, int], Set[int]] = {}
vocab_stack: Dict[str, List[Dict[str, Any]]] = {}
vocab_answers: Dict[str, Dict[int, int]] = {}  # username -> {card_id: rating}

# Default deck where vocab cards are created (from define-with-context.md).
# Adjust if your environment differs.
VOCAB_DECK_ID = 1756509006667
VOCAB_TARGET_DECK_NAME = "Hungarian Vocab"

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
            .card {{ background: #2a2a2a; border-radius: 12px; padding: 30px; margin-bottom: 20px; box-shadow: 0 6px 20px rgba(0,0,0,0.4); flex: 1; border: 1px solid #404040; }}
            .card-content {{
                font-size: 18px;
                line-height: 1.8;
                text-align: left;
                min-height: 300px;
                padding: 25px;
                background: #1f1f1f;
                border-radius: 8px;
                border: 1px solid #333;
                color: #f0f0f0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}
            .field-item {{
                margin-bottom: 20px;
                padding: 15px;
                background: #2a2a2a;
                border-radius: 6px;
                border-left: 4px solid #0084ff;
            }}
            .field-label {{
                font-weight: 600;
                color: #4a9eff;
                font-size: 14px;
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .field-value {{
                color: #e8e8e8;
                font-size: 16px;
                line-height: 1.6;
            }}
            .controls {{ display: flex; justify-content: center; gap: 15px; margin-top: 30px; flex-wrap: wrap; }}
            .btn {{
                background: #0084ff;
                color: white;
                border: none;
                padding: 16px 28px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 16px;
                font-weight: 500;
                transition: all 0.2s;
                border: 2px solid transparent;
                min-width: 130px;
            }}
            .btn:hover {{ background: #0066cc; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,132,255,0.3); }}
            .btn:disabled {{ background: #404040; cursor: not-allowed; transform: none; box-shadow: none; }}
            .btn.secondary {{ background: #505050; border: 2px solid #666; }}
            .btn.secondary:hover {{ background: #606060; border-color: #777; }}
            .ease-buttons {{ display: none; gap: 12px; justify-content: center; }}
            .ease-btn {{
                background: #666;
                padding: 14px 20px;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.2s;
                border: none;
                color: white;
                font-weight: 500;
                font-size: 15px;
                min-width: 90px;
            }}
            .ease-btn:hover {{ transform: translateY(-1px); box-shadow: 0 4px 8px rgba(0,0,0,0.3); }}
            .ease-btn.again {{ background: #dc3545; }}
            .ease-btn.again:hover {{ background: #c82333; box-shadow: 0 4px 8px rgba(220,53,69,0.3); }}
            .ease-btn.hard {{ background: #fd7e14; }}
            .ease-btn.hard:hover {{ background: #e96b00; box-shadow: 0 4px 8px rgba(253,126,20,0.3); }}
            .ease-btn.good {{ background: #28a745; }}
            .ease-btn.good:hover {{ background: #218838; box-shadow: 0 4px 8px rgba(40,167,69,0.3); }}
            .ease-btn.easy {{ background: #007bff; }}
            .ease-btn.easy:hover {{ background: #0056b3; box-shadow: 0 4px 8px rgba(0,123,255,0.3); }}
            .stats {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 25px;
                padding: 15px 20px;
                background: #2a2a2a;
                border-radius: 8px;
                border: 1px solid #404040;
                font-size: 15px;
                font-weight: 500;
            }}
            .stat-item {{
                color: #b8b8b8;
            }}
            .stat-value {{
                color: #4a9eff;
                font-weight: 600;
            }}
            .back-link {{ position: absolute; top: 20px; left: 20px; color: #0084ff; text-decoration: none; }}
            .back-link:hover {{ text-decoration: underline; }}
            /* Vocab flow */
            .tools {{ margin-top: 16px; display: flex; gap: 10px; flex-wrap: wrap; }}
            .tools .input {{ flex: 1; min-width: 260px; }}
            .tools input {{ width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #444; background: #1a1a1a; color: #eee; }}
            .subtle {{ color: #a0a0a0; font-size: 13px; }}
            .panel {{ background: #232323; border: 1px solid #3a3a3a; border-radius: 10px; padding: 16px; margin-top: 16px; }}
            .panel h3 {{ margin-bottom: 10px; }}
            .vocab-card {{ background: #2a2a2a; border: 1px solid #444; padding: 12px; border-radius: 8px; margin-bottom: 10px; }}
            .vocab-actions {{ display: flex; gap: 8px; margin-top: 8px; }}
            .hidden {{ display: none; }}
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
                <span class="stat-item">Status: <span class="stat-value" id="session-stats">Ready to start</span></span>
                <span class="stat-item" id="card-counter">Cards: <span class="stat-value">0</span></span>
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

                <div class="panel">
                    <h3>Vocab Tools</h3>
                    <div class="tools">
                        <div class="input">
                            <input id="unknown-words" placeholder="Enter unknown words, comma-separated" />
                            <div class="subtle">Will use the current card content as context.</div>
                        </div>
                        <button class="btn secondary" id="define-words-btn" onclick="defineWithContext()">Define with context</button>
                    </div>
                    <div id="late-answer" class="tools hidden">
                        <div class="subtle">Session closed for safety. Choose answer for cached card:</div>
                        <div class="ease-buttons" style="display:flex;">
                            <button class="ease-btn again" onclick="cacheAnswer(1)">Again</button>
                            <button class="ease-btn hard" onclick="cacheAnswer(2)">Hard</button>
                            <button class="ease-btn good" onclick="cacheAnswer(3)">Good</button>
                            <button class="ease-btn easy" onclick="cacheAnswer(4)">Easy</button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card" id="vocab-review" style="display:none;">
                <h2>Vocab Review</h2>
                <div id="vocab-list"></div>
                <div class="controls" style="justify-content:flex-start;">
                    <button class="btn" onclick="startAutoStudy()">Submit Answers</button>
                </div>
            </div>
        </div>

        <script>
            let sessionActive = false;
            let cardFlipped = false;
            let cardCount = 0;
            let currentCardId = null;

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
                    currentCardId = data.card_id || null;
                    cardCount++;

                    // Try auto-submitting if this card was cached
                    const maybeFront = await autoSubmitCachedIfNeeded(data);
                    displayCard(maybeFront || (data.front || data));

                    document.getElementById('start-btn').style.display = 'none';
                    document.getElementById('flip-btn').style.display = 'inline-block';
                    document.getElementById('close-btn').style.display = 'inline-block';
                    document.getElementById('session-stats').textContent = 'Front side shown';
                    document.getElementById('card-counter').innerHTML = `Cards: <span class="stat-value">${{cardCount}}</span>`;

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
                    document.getElementById('session-stats').textContent = 'Choose difficulty';

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
                    currentCardId = data.card_id || currentCardId;

                    displayCard(data.front || data);

                    document.getElementById('flip-btn').style.display = 'inline-block';
                    document.getElementById('ease-buttons').style.display = 'none';
                    document.getElementById('session-stats').textContent = 'Front side shown';
                    document.getElementById('card-counter').innerHTML = `Cards: <span class="stat-value">${{cardCount}}</span>`;

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
                    content.innerHTML = `<div class="field-item"><div class="field-value">${{cardData}}</div></div>`;
                    return;
                }}

                if (cardData && typeof cardData === 'object') {{
                    let html = '';
                    for (const [field, value] of Object.entries(cardData)) {{
                        if (field !== 'card_id' && field !== 'media_files' && field !== 'ease_options' && value && value.trim() !== '') {{
                            // Clean up field names for display
                            const displayField = field
                                .replace(/_/g, ' ')
                                .replace(/\b\w/g, l => l.toUpperCase());

                            html += `
                                <div class="field-item">
                                    <div class="field-label">${{displayField}}</div>
                                    <div class="field-value">${{value}}</div>
                                </div>
                            `;
                        }}
                    }}
                    content.innerHTML = html || '<div class="field-item"><div class="field-value">No content to display</div></div>';
                }} else {{
                    content.innerHTML = '<div class="field-item"><div class="field-value">Loading...</div></div>';
                }}
            }}

            // Auto-skip cached card by flipping + answering automatically
            async function autoSubmitCachedIfNeeded(initialData) {{
                try {{
                    let frontData = initialData.front || initialData;
                    let guard = 20;
                    while (guard-- > 0 && currentCardId) {{
                        const res = await fetch(`/api/session/pop-cached-answer?username=${{encodeURIComponent(username)}}&card_id=${{encodeURIComponent(currentCardId)}}`);
                        if (!res.ok) break;
                        const payload = await res.json();
                        const rating = payload.rating;
                        if (!rating) break;

                        await makeStudyRequest('/api/study/flip', {{ deck_id: deckId, username, action: 'flip' }});
                        const ans = await makeStudyRequest('/api/study/answer', {{ deck_id: deckId, username, action: rating.toString() }});
                        if (ans.message && ans.message.includes('No more cards')) {{
                            document.getElementById('card-content').innerHTML = '<p>🎉 No more cards to review! Session complete!</p>';
                            document.getElementById('ease-buttons').style.display = 'none';
                            document.getElementById('close-btn').style.display = 'inline-block';
                            document.getElementById('session-stats').textContent = 'Session complete!';
                            return null;
                        }}
                        cardCount++;
                        frontData = ans.front || ans;
                        currentCardId = ans.card_id || currentCardId;
                    }}
                    return frontData;
                }} catch (e) {{ console.warn('autoSubmitCachedIfNeeded error', e); return null; }}
            }}

            // --- Vocab flow wiring ---
            async function defineWithContext() {{
                const input = document.getElementById('unknown-words').value.trim();
                if (!input) {{ alert('Enter one or more words.'); return; }}
                const words = input.split(',').map(w => w.trim()).filter(Boolean);
                if (words.length === 0) {{ alert('No valid words.'); return; }}

                await closeSession(true);
                const late = document.getElementById('late-answer');
                if (late) late.classList.remove('hidden');

                const sourceHtml = document.getElementById('card-content').innerHTML;
                try {{
                    await makeStudyRequest('/api/vocab/define', {{ username, deck_id: deckId, words, source_card: {{ html: sourceHtml }} }});
                    const review = document.getElementById('vocab-review');
                    if (review) review.style.display = 'block';
                    setTimeout(pollForNewCards, 500); // first quick poll
                    window.__vocabPollTimer = setInterval(pollForNewCards, 3000);
                }} catch (e) {{ alert('Error submitting words: ' + e.message); }}
            }}

            async function pollForNewCards() {{
                try {{
                    const res = await fetch(`/api/vocab/poll-new?username=${{encodeURIComponent(username)}}&deck_id=${{encodeURIComponent(deckId)}}`);
                    if (!res.ok) return;
                    const items = await res.json();
                    if (Array.isArray(items) && items.length) {{
                        const list = document.getElementById('vocab-list');
                        for (const item of items) {{
                            const div = document.createElement('div');
                            div.className = 'vocab-card';
                            const word = (item.fields && (item.fields.Word || item.fields.word || '')) || '';
                            const definition = (item.fields && (item.fields.Definition || item.fields.definition || '')) || '';
                            const example = (item.fields && (item.fields['Example Sentence'] || item.fields.example || '')) || '';
                            div.innerHTML = `
                                <div><strong>${{word}}</strong></div>
                                <div>${{definition}}</div>
                                <div class="subtle">${{example}}</div>
                                <div class="vocab-actions">
                                    <button class="btn" onclick="markUnderstood(${{item.card_id}})">Understood/Studied</button>
                                    <button class="btn secondary" onclick="requestMore(${{item.card_id}})">Request additional definitions</button>
                                </div>
                            `;
                            list.prepend(div);
                        }}
                    }}
                }} catch (e) {{ console.warn('Polling error', e); }}
            }}

            async function cacheAnswer(ease) {{
                try {{
                    await makeStudyRequest('/api/session/cache-answer', {{ username, rating: ease, card_id: currentCardId }});
                    const late = document.getElementById('late-answer');
                    if (late) late.classList.add('hidden');
                    // Immediately resume the grammar study session and auto-submit cached answer(s)
                    await startSession();
                }} catch (e) {{ alert('Error caching answer: ' + e.message); }}
            }}

            async function markUnderstood(cardId) {{
                try {{ await makeStudyRequest('/api/vocab/mark-understood', {{ username, card_id: cardId }}); }} catch (e) {{}}
            }}

            async function requestMore(cardId) {{
                const wordsInput = prompt('Words to define (comma-separated):');
                if (!wordsInput) return;
                const words = wordsInput.split(',').map(w => w.trim()).filter(Boolean);
                try {{
                    const res = await fetch(`/api/vocab/card-contents?username=${{encodeURIComponent(username)}}&card_id=${{encodeURIComponent(cardId)}}`);
                    const source = await res.json();
                    await makeStudyRequest('/api/vocab/request-more', {{ username, words, source_card: source }});
                }} catch (e) {{ console.warn(e); }}
            }}

            async function startAutoStudy() {{
                try {{
                    const res = await makeStudyRequest('/api/vocab/auto-study', {{ username, deck_id: deckId }});
                    alert(res.message || 'Auto study started');
                }} catch (e) {{ alert('Error starting auto study: ' + e.message); }}
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

@app.post("/api/session/cache-answer")
async def api_cache_answer(request: Request):
    data = await request.json()
    username = data.get("username")
    rating = int(data.get("rating")) if str(data.get("rating")).isdigit() else None
    card_id = data.get("card_id")
    if not username or rating is None:
        raise HTTPException(status_code=400, detail="username and rating required")
    if card_id is not None:
        try:
            card_id = int(card_id)
        except Exception:
            card_id = None
    # Store rating; if no card_id, keep under a special key
    if card_id is None:
        cached_answers.setdefault(username, {})[-1] = rating
    else:
        cached_answers.setdefault(username, {})[card_id] = rating
    return {"ok": True}

@app.get("/api/session/pop-cached-answer")
async def api_pop_cached_answer(username: str, card_id: int):
    try:
        rating = None
        card_id = int(card_id)
        by_user = cached_answers.get(username, {})
        if card_id in by_user:
            rating = by_user.pop(card_id)
            if not by_user:
                cached_answers.pop(username, None)
        return {"rating": rating}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/vocab/define")
async def api_vocab_define(request: Request):
    data = await request.json()
    username = data.get("username")
    deck_id = int(data.get("deck_id"))
    words = data.get("words") or []
    source_card = data.get("source_card") or {}
    vocab_stack.setdefault(username, []).append({
        "type": "define",
        "words": words,
        "source_card": source_card,
        "deck_id": deck_id,
    })
    # Seed seen set to avoid returning entire deck as new
    key = (username, deck_id)
    if key not in seen_cards_in_deck:
        seen_cards_in_deck[key] = set()
        try:
            existing = deck_ops.get_cards_in_deck(deck_id, username)
            if isinstance(existing, list):
                for c in existing:
                    cid = c.get('id') or c.get('card_id')
                    if cid is not None:
                        seen_cards_in_deck[key].add(int(cid))
        except Exception as e:
            print(f"Warn: seeding seen set failed: {e}")
    # Kick off Claude task in background
    src_ctx = build_source_context_from_payload(source_card)
    asyncio.create_task(define_with_context_async(words=words, source_context=src_ctx, username=username))
    return {"ok": True, "queued": len(words), "started": True}

@app.get("/api/vocab/poll-new")
async def api_vocab_poll_new(request: Request, username: str, deck_id: int):
    # Always poll the vocab deck where cards are created
    deck_id = VOCAB_DECK_ID
    key = (username, int(deck_id))
    seen = seen_cards_in_deck.setdefault(key, set())
    try:
        cards = deck_ops.get_cards_in_deck(int(deck_id), username)
        new_items: List[Dict[str, Any]] = []
        if isinstance(cards, list):
            for c in cards:
                cid = c.get('id') or c.get('card_id')
                if cid is None:
                    continue
                cid = int(cid)
                if cid not in seen:
                    detail = card_ops.get_card_contents(card_id=cid, username=username)
                    new_items.append({
                        "card_id": cid,
                        "fields": detail.get('fields', {}),
                        "note_id": detail.get('note_id')
                    })
                    seen.add(cid)
        return new_items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/vocab/card-contents")
async def api_vocab_card_contents(username: str, card_id: int):
    try:
        return card_ops.get_card_contents(card_id=int(card_id), username=username)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/vocab/mark-understood")
async def api_vocab_mark_understood(request: Request):
    data = await request.json()
    username = data.get("username")
    card_id = data.get("card_id")
    if not username or card_id is None:
        raise HTTPException(status_code=400, detail="username and card_id required")
    vocab_answers.setdefault(username, {})[int(card_id)] = 3
    return {"ok": True}

@app.post("/api/vocab/request-more")
async def api_vocab_request_more(request: Request):
    data = await request.json()
    username = data.get("username")
    words = data.get("words") or []
    source_card = data.get("source_card") or {}
    vocab_stack.setdefault(username, []).append({
        "type": "request-more",
        "words": words,
        "source_card": source_card,
    })
    # Background Claude call with LIFO priority
    src_ctx = build_source_context_from_payload(source_card)
    asyncio.create_task(define_with_context_async(words=words, source_context=src_ctx, username=username))
    return {"ok": True, "queued": len(words), "started": True}

@app.post("/api/vocab/auto-study")
async def api_vocab_auto_study(request: Request):
    data = await request.json()
    username = data.get("username")
    # Use the vocab deck where cards were created
    deck_id = VOCAB_DECK_ID

    answers = vocab_answers.get(username, {})
    if not answers:
        return {"ok": False, "message": "No vocab answers cached."}

    processed: List[int] = []
    try:
        # Start session
        _, _ = study_ops.study(deck_id=deck_id, action="start", username=username)

        # Best-effort loop to flip and submit mapped ratings when encountered
        max_steps = max(50, len(answers) * 10)
        for _i in range(max_steps):
            try:
                flip_res, _ = study_ops.study(deck_id=deck_id, action="flip", username=username)
            except Exception:
                break

            # Try to extract current card id from response
            current_id = None
            if isinstance(flip_res, dict):
                current_id = flip_res.get("card_id")
                if current_id is None and isinstance(flip_res.get("card"), dict):
                    current_id = flip_res["card"].get("card_id")
                # Some payloads use nested fields; attempt a fallback
                if current_id is None and isinstance(flip_res.get("fields"), dict):
                    current_id = flip_res.get("fields", {}).get("card_id")

            if current_id is not None and int(current_id) in answers and int(current_id) not in processed:
                # Submit mapped rating
                rating = answers[int(current_id)]
                study_ops.study(deck_id=deck_id, action=str(rating), username=username)
                processed.append(int(current_id))
                if len(processed) == len(answers):
                    break
            else:
                # Advance without mapping
                study_ops.study(deck_id=deck_id, action="1", username=username)

        # Close session
        try:
            study_ops.study(deck_id=deck_id, action="close", username=username)
        except Exception:
            pass

        # Move processed cards to target vocab deck
        moved = []
        if processed:
            move_res = card_ops.move_cards(card_ids=processed, target_deck_name=VOCAB_TARGET_DECK_NAME, username=username)
            moved = processed

        # Clear processed from cache
        for cid in processed:
            answers.pop(cid, None)
        if not answers:
            vocab_answers.pop(username, None)

        return {
            "ok": True,
            "processed": processed,
            "moved": moved,
            "remaining": list(answers.keys()),
            "message": f"Auto-studied {len(processed)} cards and moved to '{VOCAB_TARGET_DECK_NAME}'."
        }
    except Exception as e:
        return {"ok": False, "message": f"Auto-study failed: {e}"}

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
