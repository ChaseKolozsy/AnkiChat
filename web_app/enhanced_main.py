#!/usr/bin/env python3
"""
Enhanced AnkiChat Web Interface with Claude Code SDK Integration
Supports dual study sessions: grammar (main) and vocabulary (secondary with LIFO)
"""

import os
import sys
import asyncio
import json
import logging
import signal
import atexit
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import typer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to the path for imports
project_root = Path(__file__).parents[1]
sys.path.insert(0, str(project_root))

from AnkiClient.src.operations import deck_ops, study_ops, card_ops
from claude_sdk_integration import create_claude_sdk_integration

app = FastAPI(title="Enhanced AnkiChat Web Interface", description="Claude SDK integrated Anki study sessions")

# Global state
current_user = None
current_deck_id = None
study_session = {}
claude_integration = None
anki_client = None  # This would be initialized with actual client


def cleanup_on_exit():
    """Synchronous cleanup function for atexit and signal handlers"""
    global claude_integration
    if claude_integration:
        # Use asyncio to run the async cleanup function
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If event loop is already running, create a new task
                loop.create_task(claude_integration.cleanup())
            else:
                # If no event loop is running, run it
                loop.run_until_complete(claude_integration.cleanup())
        except Exception as e:
            print(f"Error during cleanup: {e}")
            # Try direct synchronous cleanup if async fails
            try:
                if hasattr(claude_integration, 'grammar_session') and claude_integration.grammar_session and claude_integration.grammar_session.session_id:
                    from AnkiClient.src.operations.study_ops import study
                    study(
                        deck_id=claude_integration.grammar_session.deck_id,
                        action="close",
                        username="chase"
                    )
                    print(f"Emergency close of grammar session {claude_integration.grammar_session.session_id}")
            except Exception as cleanup_error:
                print(f"Emergency cleanup also failed: {cleanup_error}")


def signal_handler(signum, frame):
    """Handle termination signals"""
    print(f"\nReceived signal {signum}, cleaning up study sessions...")
    cleanup_on_exit()
    sys.exit(0)


# Register signal handlers and cleanup
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Termination
atexit.register(cleanup_on_exit)  # Normal exit


@app.on_event("startup")
async def startup():
    """Initialize Claude SDK integration on startup"""
    global claude_integration, anki_client

    # TODO: Initialize actual AnkiClient instance
    # anki_client = AnkiClient()

    # For now, we'll simulate the client
    claude_integration = create_claude_sdk_integration(anki_client)

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    global claude_integration
    if claude_integration:
        await claude_integration.cleanup()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Enhanced home page with dual study session support."""
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>Enhanced AnkiChat Web Interface</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: #1f1f1f;
            color: #f0f0f0;
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; }
        .card {
            background: #2d2d2d;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            border: 1px solid #404040;
        }

        /* Dual Session Layout */
        .sessions-container { display: flex; gap: 20px; }
        .session-column { flex: 1; }

        /* Grammar Session (Main) */
        .grammar-session {
            border-left: 4px solid #0084ff;
        }
        .grammar-session h2 { color: #0084ff; }

        /* Vocabulary Session (Secondary) */
        .vocabulary-session {
            border-left: 4px solid #ff6b35;
        }
        .vocabulary-session h2 { color: #ff6b35; }

        /* Session Status Indicators */
        .session-status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 10px;
        }
        .status-active { background: #28a745; color: white; }
        .status-paused { background: #ffc107; color: black; }
        .status-waiting { background: #6c757d; color: white; }

        /* Card Display */
        .card-display {
            background: #1a1a1a;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            border: 1px solid #404040;
        }
        .card-field {
            margin-bottom: 15px;
            padding: 10px;
            background: #262626;
            border-radius: 6px;
            border-left: 3px solid #0084ff;
        }
        .field-label {
            font-weight: bold;
            color: #0084ff;
            margin-bottom: 5px;
            font-size: 14px;
        }
        .field-content {
            color: #f0f0f0;
            line-height: 1.4;
            text-align: left;
        }
        .card-side {
            margin-bottom: 20px;
            padding: 15px;
            background: #1e1e1e;
            border-radius: 8px;
            border: 1px solid #333;
        }
        .card-side h4 {
            margin: 0 0 15px 0;
            color: #ff6b35;
            font-size: 16px;
            border-bottom: 2px solid #333;
            padding-bottom: 8px;
        }

        /* Form Elements */
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: 500; }
        input, select, textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #404040;
            border-radius: 8px;
            background: #1a1a1a;
            color: #ffffff;
            font-size: 16px;
        }
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: #0084ff;
        }

        /* Buttons */
        .btn {
            background: #0084ff;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.2s;
            margin-right: 10px;
            margin-bottom: 5px;
        }
        .btn:hover { background: #0066cc; transform: translateY(-1px); }
        .btn:disabled { background: #404040; cursor: not-allowed; transform: none; }

        .btn-claude { background: #9333ea; }
        .btn-claude:hover { background: #7c3aed; }

        .btn-vocabulary { background: #ff6b35; }
        .btn-vocabulary:hover { background: #e55a2b; }

        /* Answer Buttons */
        .answer-buttons {
            display: flex;
            gap: 10px;
            margin-top: 15px;
            flex-wrap: wrap;
        }
        .btn-answer { flex: 1; min-width: 100px; }
        .btn-again { background: #dc3545; }
        .btn-again:hover { background: #c82333; }
        .btn-hard { background: #fd7e14; }
        .btn-hard:hover { background: #e8610e; }
        .btn-good { background: #28a745; }
        .btn-good:hover { background: #218838; }
        .btn-easy { background: #17a2b8; }
        .btn-easy:hover { background: #138496; }

        .flip-button-container {
            text-align: center;
            margin: 15px 0;
        }
        .btn-flip {
            background: #6f42c1;
            color: white;
            border: none;
            padding: 12px 24px;
            font-size: 16px;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.3s ease;
        }
        .btn-flip:hover {
            background: #5a32a3;
        }

        /* Queue Status */
        .queue-status {
            background: #262626;
            border-radius: 6px;
            padding: 15px;
            margin: 10px 0;
        }
        .queue-item {
            background: #1a1a1a;
            border-radius: 4px;
            padding: 10px;
            margin: 5px 0;
            border-left: 3px solid #ff6b35;
        }

        /* Claude SDK Status */
        .claude-status {
            background: #2d1b69;
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
            border: 1px solid #9333ea;
        }

        /* Loading States */
        .loading { opacity: 0.6; pointer-events: none; }
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #404040;
            border-radius: 50%;
            border-top-color: #0084ff;
            animation: spin 1s ease-in-out infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Hidden elements */
        .hidden { display: none; }

        /* Vocabulary feedback borders */
        .vocabulary-session.feedback-success {
            border: 3px solid #28a745 !important;
            transition: border-color 0.3s ease;
        }
        .vocabulary-session.feedback-error {
            border: 3px solid #dc3545 !important;
            transition: border-color 0.3s ease;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .sessions-container { flex-direction: column; }
            .answer-buttons { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧠 Enhanced AnkiChat Web Interface</h1>
            <p>Dual study sessions with Claude Code SDK integration</p>
        </div>

        <!-- User Setup -->
        <div class="card">
            <h2>Setup</h2>
            <div class="form-group">
                <label for="username">Username:</label>
                <input type="text" id="username" placeholder="Enter your Anki username">
            </div>
            <button class="btn" onclick="loadDecks()">Load Decks</button>
        </div>

        <!-- Deck Selection -->
        <div class="card hidden" id="deck-selection">
            <h2>Select Grammar Deck</h2>
            <div id="deck-list"></div>
            <button class="btn" id="start-study" onclick="startDualSession()" disabled>Start Enhanced Study Session</button>
        </div>

        <!-- Dual Study Sessions -->
        <div class="sessions-container hidden" id="study-interface">
            <!-- Grammar Session (Main) -->
            <div class="session-column">
                <div class="card grammar-session">
                    <h2>📚 Grammar Session <span class="session-status status-active" id="grammar-status">Active</span></h2>

                    <div id="grammar-card-display" class="card-display">
                        <!-- Grammar card content will be displayed here -->
                    </div>

                    <div class="form-group">
                        <label>Define words with Claude SDK:</label>
                        <textarea id="words-to-define" placeholder="Enter words to define (comma-separated)" rows="2"></textarea>
                        <button class="btn btn-claude" onclick="requestDefinitions()">
                            <span class="spinner hidden" id="claude-spinner"></span>
                            Ask Claude for Definitions
                        </button>
                    </div>

                    <div class="flip-button-container">
                        <button class="btn btn-flip" onclick="flipCard()" id="flip-button">🔄 Flip Card</button>
                    </div>

                    <div class="answer-buttons hidden" id="grammar-answers">
                        <button class="btn btn-answer btn-again" onclick="answerCard(1)">1 - Again</button>
                        <button class="btn btn-answer btn-hard" onclick="answerCard(2)">2 - Hard</button>
                        <button class="btn btn-answer btn-good" onclick="answerCard(3)">3 - Good</button>
                        <button class="btn btn-answer btn-easy" onclick="answerCard(4)">4 - Easy</button>
                    </div>

                    <div class="claude-status hidden" id="claude-status">
                        <h4>🤖 Claude SDK Processing</h4>
                        <p>Generating definitions with context...</p>
                        <div>Your answer has been cached. You can:</div>
                        <ul>
                            <li>Study vocabulary cards below while Claude works</li>
                            <li>Submit your cached answer to resume grammar session</li>
                        </ul>
                        <div class="form-group" style="margin-top: 10px;">
                            <label>Cached Answer:</label>
                            <div id="cached-answer-display" style="padding: 10px; background: #404040; border-radius: 6px;">
                                <!-- Cached answer will be shown here -->
                            </div>
                            <button class="btn btn-good" onclick="submitCachedAnswer()" style="margin-top: 10px;">
                                Submit Cached Answer & Resume Grammar
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Vocabulary Session (Secondary) -->
            <div class="session-column">
                <div class="card vocabulary-session">
                    <h2>📖 Vocabulary Queue <span class="session-status status-waiting" id="vocab-status">Detecting Cards</span></h2>

                    <div class="queue-status">
                        <div><strong>Queue Length:</strong> <span id="queue-length">0</span></div>
                        <div><strong>Cached Answers:</strong> <span id="cached-answers">0</span></div>
                        <div><strong>Auto-session Ready:</strong> <span id="auto-ready">No</span></div>
                    </div>

                    <div id="vocabulary-card-display" class="card-display hidden">
                        <!-- Vocabulary card content will be displayed here -->
                    </div>

                    <div class="form-group hidden" id="vocab-define-section">
                        <label>Priority definition request:</label>
                        <textarea id="vocab-words-to-define" placeholder="Enter words from vocabulary card" rows="2"></textarea>
                        <button class="btn btn-claude" onclick="requestVocabularyDefinitions()">
                            Priority Claude Request
                        </button>
                    </div>

                    <div class="answer-buttons hidden" id="vocabulary-answers">
                        <button class="btn btn-answer btn-good" onclick="answerVocabularyCard(3)">✅ Studied</button>
                    </div>

                    <div id="vocabulary-queue" class="queue-status">
                        <h4>📋 New Cards Queue (LIFO)</h4>
                        <div id="queue-items">No new vocabulary cards detected yet...</div>
                    </div>

                    <button class="btn btn-vocabulary" id="submit-vocabulary-session" onclick="submitVocabularySession()" disabled>
                        Submit Vocabulary Session
                    </button>
                </div>
            </div>
        </div>

        <!-- Session Controls -->
        <div class="card hidden" id="session-controls">
            <h2>Session Controls</h2>
            <button class="btn" onclick="pauseSession()">Pause All Sessions</button>
            <button class="btn" onclick="resumeSession()">Resume Sessions</button>
            <button class="btn" onclick="closeAllSessions()">Close All Sessions</button>
        </div>
    </div>

    <script>
        let currentUser = null;
        let selectedDeck = null;
        let grammarSession = { active: false, paused: false, currentCard: null };
        let vocabularySession = { active: false, queue: [], cachedAnswers: {} };
        let pollingInterval = null;
        let claudeProcessing = false;
        let cachedGrammarAnswer = null;  // Store cached answer for later submission

        // Deck loading functions (similar to original)
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

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                let decks = [];

                if (Array.isArray(data)) {
                    decks = data;
                } else if (data.decks && Array.isArray(data.decks)) {
                    decks = data.decks;
                } else if (data.error) {
                    throw new Error(data.error);
                } else {
                    console.warn('Unexpected response format:', data);
                    decks = [];
                }

                displayDecks(decks);
            } catch (error) {
                console.error('Error loading decks:', error);
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
                    <div class="deck-item" onclick="selectDeck(${deck.id}, '${deck.name}')"
                         style="background: #404040; border-radius: 8px; padding: 15px; margin-bottom: 10px; cursor: pointer; transition: all 0.2s;">
                        <strong>${deck.name}</strong>
                        <div style="font-size: 14px; opacity: 0.7; margin-top: 5px;">
                            ID: ${deck.id}
                        </div>
                    </div>
                `).join('');
            }

            deckSelection.classList.remove('hidden');

            // Start vocabulary polling automatically when user loads decks
            startVocabularyPolling();
        }

        function selectDeck(deckId, deckName) {
            document.querySelectorAll('.deck-item').forEach(item => {
                item.style.background = '#404040';
            });
            event.target.closest('.deck-item').style.background = '#0084ff';

            selectedDeck = { id: deckId, name: deckName };
            document.getElementById('start-study').disabled = false;
        }

        // Enhanced Study Session Functions
        async function startDualSession() {
            if (!selectedDeck || !currentUser) {
                alert('Please select a deck and user');
                return;
            }

            try {
                // Start grammar session
                const response = await fetch('/api/start-dual-session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUser,
                        deck_id: selectedDeck.id
                    })
                });

                const result = await response.json();
                if (result.success) {
                    grammarSession.active = true;
                    grammarSession.currentCard = result.current_card;

                    // Show study interface
                    document.getElementById('study-interface').classList.remove('hidden');
                    document.getElementById('session-controls').classList.remove('hidden');
                    document.getElementById('deck-selection').classList.add('hidden');

                    // Display grammar card
                    displayGrammarCard(result.current_card);

                    // Start vocabulary polling
                    startVocabularyPolling();

                    updateSessionStatus('grammar-status', 'Active', 'status-active');
                    updateSessionStatus('vocab-status', 'Polling', 'status-waiting');

                } else {
                    alert('Error starting session: ' + result.error);
                }
            } catch (error) {
                alert('Error starting dual session: ' + error.message);
            }
        }

        function displayGrammarCard(card) {
            const display = document.getElementById('grammar-card-display');
            if (!card) {
                display.innerHTML = '<p>No card data available</p>';
                return;
            }

            let html = '';

            // Handle both the current card data structure (front/back) and legacy fields structure
            // Check for structured front/back data first (e.g., card with front and back keys)
            if (card.front || card.back) {
                if (card.front) {
                    html += '<div class="card-side"><h4>📝 Front</h4>';
                    Object.keys(card.front).forEach(fieldName => {
                        if (card.front[fieldName] && card.front[fieldName].trim()) {
                            html += `
                                <div class="card-field">
                                    <div class="field-label">${fieldName.replace(/_/g, ' ')}</div>
                                    <div class="field-content">${card.front[fieldName]}</div>
                                </div>
                            `;
                        }
                    });
                    html += '</div>';
                }

                if (card.back) {
                    html += '<div class="card-side"><h4>🎯 Back</h4>';
                    Object.keys(card.back).forEach(fieldName => {
                        if (card.back[fieldName] && card.back[fieldName].trim()) {
                            html += `
                                <div class="card-field">
                                    <div class="field-label">${fieldName.replace(/_/g, ' ')}</div>
                                    <div class="field-content">${card.back[fieldName]}</div>
                                </div>
                            `;
                        }
                    });
                    html += '</div>';
                }
            }
            // Check for top-level back/front keys (AnkiAPI flip response format)
            else if (card.back && typeof card.back === 'object') {
                html += '<div class="card-side"><h4>🎯 Back</h4>';
                Object.keys(card.back).forEach(fieldName => {
                    if (card.back[fieldName] && card.back[fieldName].trim()) {
                        html += `
                            <div class="card-field">
                                <div class="field-label">${fieldName.replace(/_/g, ' ')}</div>
                                <div class="field-content">${card.back[fieldName]}</div>
                            </div>
                        `;
                    }
                });
                html += '</div>';
            } else if (card.fields) {
                // Legacy structure: card has fields
                Object.keys(card.fields).forEach(fieldName => {
                    if (card.fields[fieldName] && card.fields[fieldName].trim()) {
                        html += `
                            <div class="card-field">
                                <div class="field-label">${fieldName}</div>
                                <div class="field-content">${card.fields[fieldName]}</div>
                            </div>
                        `;
                    }
                });
            } else if (card && typeof card === 'object') {
                // Direct field iteration (like old main.py) - this is what actually works!
                for (const [field, value] of Object.entries(card)) {
                    // Skip metadata fields and empty values
                    if (field !== 'card_id' && field !== 'id' && field !== 'note_id' &&
                        field !== 'media_files' && field !== 'ease_options' &&
                        value && typeof value === 'string' && value.trim() !== '') {

                        // Clean up field names for display
                        const displayField = field
                            .replace(/_/g, ' ')
                            .replace(/\b\w/g, l => l.toUpperCase());

                        html += `
                            <div class="card-field">
                                <div class="field-label">${displayField}</div>
                                <div class="field-content">${value}</div>
                            </div>
                        `;
                    }
                }
            } else if (typeof card === 'string') {
                // Handle string responses
                html = `<div class="card-field"><div class="field-content">${card}</div></div>`;
            }

            display.innerHTML = html || '<p>No field data available</p>';

            // Reset flip button when new card is displayed
            const flipButton = document.getElementById('flip-button');
            if (flipButton) {
                flipButton.textContent = '🔄 Flip Card';
                flipButton.disabled = false;
            }

            // Hide answer buttons until card is flipped
            const answerButtons = document.getElementById('grammar-answers');
            if (answerButtons) {
                answerButtons.classList.add('hidden');
            }
        }

        async function flipCard() {
            const flipButton = document.getElementById('flip-button');

            if (!grammarSession.active || !grammarSession.currentCard) {
                alert('No active card to flip');
                return;
            }

            try {
                // Disable flip button during request
                flipButton.disabled = true;
                flipButton.textContent = '🔄 Flipping...';

                // Call flip action on the current grammar session
                const response = await fetch('/api/flip-card', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUser
                    })
                });

                const result = await response.json();
                if (result.success) {
                    // Debug: Log the card structure received
                    console.log('DEBUG - Flipped card structure:', result.current_card);
                    console.log('DEBUG - Card type:', typeof result.current_card);
                    console.log('DEBUG - Card keys:', Object.keys(result.current_card || {}));

                    // Update the card display with the flipped card
                    grammarSession.currentCard = result.current_card;
                    displayGrammarCard(result.current_card);

                    // Update flip button text
                    flipButton.textContent = '✅ Flipped';

                    // Show answer buttons after successful flip
                    const answerButtons = document.getElementById('grammar-answers');
                    if (answerButtons) {
                        answerButtons.classList.remove('hidden');
                    }
                } else {
                    alert('Error flipping card: ' + (result.error || 'Unknown error'));
                    flipButton.textContent = '🔄 Flip Card';
                }
            } catch (error) {
                alert('Error flipping card: ' + error.message);
                flipButton.textContent = '🔄 Flip Card';
            } finally {
                // Re-enable flip button
                flipButton.disabled = false;
            }
        }

        function displayVocabularyCard(card) {
            const display = document.getElementById('vocabulary-card-display');
            const defineSection = document.getElementById('vocab-define-section');
            const answerSection = document.getElementById('vocabulary-answers');

            if (!card) {
                display.classList.add('hidden');
                defineSection.classList.add('hidden');
                answerSection.classList.add('hidden');
                return;
            }

            let html = '';

            // Handle full card contents from card_ops (entire card display)
            if (card.fields) {
                // Standard fields structure
                Object.keys(card.fields).forEach(fieldName => {
                    if (card.fields[fieldName] && card.fields[fieldName].trim()) {
                        html += `
                            <div class="card-field">
                                <div class="field-label">${fieldName}</div>
                                <div class="field-content">${card.fields[fieldName]}</div>
                            </div>
                        `;
                    }
                });
            } else if (card && typeof card === 'object') {
                // Direct field iteration (entire card content)
                for (const [field, value] of Object.entries(card)) {
                    // Skip metadata fields and empty values
                    if (field !== 'card_id' && field !== 'id' && field !== 'note_id' &&
                        field !== 'media_files' && field !== 'ease_options' &&
                        value && typeof value === 'string' && value.trim() !== '') {

                        // Clean up field names for display
                        const displayField = field
                            .replace(/_/g, ' ')
                            .replace(/\b\w/g, l => l.toUpperCase());

                        html += `
                            <div class="card-field">
                                <div class="field-label">${displayField}</div>
                                <div class="field-content">${value}</div>
                            </div>
                        `;
                    }
                }
            }

            display.innerHTML = html || '<p>No field data available</p>';
            display.classList.remove('hidden');
            defineSection.classList.remove('hidden');
            answerSection.classList.remove('hidden');

            vocabularySession.currentCard = card;
        }

        async function requestDefinitions() {
            const words = document.getElementById('words-to-define').value.trim();
            if (!words) {
                alert('Please enter words to define');
                return;
            }

            claudeProcessing = true;
            document.getElementById('claude-spinner').classList.remove('hidden');
            updateSessionStatus('grammar-status', 'Paused for Claude', 'status-paused');

            try {
                const response = await fetch('/api/request-definitions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUser,
                        words: words.split(',').map(w => w.trim()),
                        card_context: grammarSession.currentCard
                    })
                });

                const result = await response.json();
                if (result.success) {
                    document.getElementById('claude-status').classList.remove('hidden');
                    grammarSession.paused = true;
                } else {
                    alert('Error requesting definitions: ' + result.error);
                    claudeProcessing = false;
                    document.getElementById('claude-spinner').classList.add('hidden');
                }
            } catch (error) {
                alert('Error requesting definitions: ' + error.message);
                claudeProcessing = false;
                document.getElementById('claude-spinner').classList.add('hidden');
            }
        }

        async function requestVocabularyDefinitions() {
            const words = document.getElementById('vocab-words-to-define').value.trim();
            if (!words || !vocabularySession.currentCard) {
                alert('Please enter words and ensure a vocabulary card is displayed');
                return;
            }

            try {
                const response = await fetch('/api/request-vocabulary-definitions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUser,
                        words: words.split(',').map(w => w.trim()),
                        card_context: vocabularySession.currentCard,
                        priority: true
                    })
                });

                const result = await response.json();
                if (result.success) {
                    alert('Priority vocabulary definition request sent to Claude SDK');
                } else {
                    alert('Error requesting vocabulary definitions: ' + result.error);
                }
            } catch (error) {
                alert('Error requesting vocabulary definitions: ' + error.message);
            }
        }

        async function answerCard(answer) {
            if (!grammarSession.currentCard) {
                alert('No current card to answer');
                return;
            }

            try {
                const response = await fetch('/api/answer-grammar-card', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUser,
                        card_id: grammarSession.currentCard.card_id,
                        answer: answer,
                        claude_processing: claudeProcessing
                    })
                });

                const result = await response.json();
                if (result.success) {
                    if (claudeProcessing) {
                        // Store the cached answer for later submission
                        cachedGrammarAnswer = {
                            card_id: grammarSession.currentCard.card_id,
                            answer: answer,
                            card: grammarSession.currentCard
                        };

                        // Show cached answer in UI
                        const answerText = ['', 'Again', 'Hard', 'Good', 'Easy'][answer] || answer;
                        document.getElementById('cached-answer-display').innerHTML =
                            `Card: ${grammarSession.currentCard.fields?.Word || 'Unknown'}<br>Answer: ${answer} - ${answerText}`;

                        document.getElementById('claude-status').classList.remove('hidden');

                        alert(`Answer ${answer} cached. You can now study vocabulary cards below or submit the cached answer to resume grammar session.`);
                    } else {
                        // Regular answer processing
                        if (result.next_card) {
                            grammarSession.currentCard = result.next_card;
                            displayGrammarCard(result.next_card);
                        }
                    }
                } else {
                    alert('Error answering card: ' + result.error);
                }
            } catch (error) {
                alert('Error answering card: ' + error.message);
            }
        }

        async function submitCachedAnswer() {
            if (!cachedGrammarAnswer) {
                alert('No cached answer to submit');
                return;
            }

            try {
                const response = await fetch('/api/answer-grammar-card', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUser,
                        card_id: cachedGrammarAnswer.card_id,
                        answer: cachedGrammarAnswer.answer,
                        is_cached_answer: true  // Important flag
                    })
                });

                const result = await response.json();
                if (result.success) {
                    alert('Grammar session resumed with cached answer!');

                    // Clear cached answer
                    cachedGrammarAnswer = null;
                    document.getElementById('claude-status').classList.add('hidden');

                    // Update session status
                    updateSessionStatus('grammar-status', 'Active', 'status-active');
                    claudeProcessing = false;

                    // Get next card if available
                    if (result.answer_result && result.answer_result.current_card) {
                        grammarSession.currentCard = result.answer_result.current_card;
                        displayGrammarCard(result.answer_result.current_card);
                    }
                } else {
                    alert('Error submitting cached answer: ' + result.error);
                }
            } catch (error) {
                alert('Error submitting cached answer: ' + error.message);
            }
        }

        async function answerVocabularyCard(answer) {
            if (!vocabularySession.currentCard) {
                alert('No current vocabulary card to answer');
                return;
            }

            const cardId = vocabularySession.currentCard.id || vocabularySession.currentCard.card_id;
            vocabularySession.cachedAnswers[cardId] = answer;

            try {
                const response = await fetch('/api/cache-vocabulary-answer', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUser,
                        card_id: cardId,
                        answer: answer
                    })
                });

                const result = await response.json();
                if (result.success) {
                    showVocabularyFeedback(true); // Show success border
                    updateVocabularyStatus();

                    // Move to next vocabulary card
                    const nextCard = await getNextVocabularyCard();
                    if (nextCard) {
                        displayVocabularyCard(nextCard);
                    } else {
                        document.getElementById('vocabulary-card-display').classList.add('hidden');
                        document.getElementById('vocab-define-section').classList.add('hidden');
                        document.getElementById('vocabulary-answers').classList.add('hidden');
                        // Clear current card so polling can fetch new ones later
                        vocabularySession.currentCard = null;
                    }
                } else {
                    showVocabularyFeedback(false); // Show error border
                }
            } catch (error) {
                showVocabularyFeedback(false); // Show error border
            }
        }

        function startVocabularyPolling() {
            if (pollingInterval) return;

            let lastQueueLength = 0;
            pollingInterval = setInterval(async () => {
                try {
                    const response = await fetch('/api/vocabulary-queue-status', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username: currentUser })
                    });

                    const result = await response.json();
                    if (result.success) {
                        updateVocabularyQueue(result.queue_status);

                        // Show study interface when vocabulary cards are detected
                        if (result.queue_status.queue_length > 0) {
                            document.getElementById('study-interface').classList.remove('hidden');
                        }

                        const vocabDisplayHidden = document.getElementById('vocabulary-card-display').classList.contains('hidden');
                        // If nothing is displayed, show the next card
                        if (result.queue_status.queue_length > 0 && (!vocabularySession.currentCard || vocabDisplayHidden)) {
                            const nextCard = await getNextVocabularyCard();
                            if (nextCard) displayVocabularyCard(nextCard);
                        }

                        // If new cards arrived while a card is displayed, requeue current and show newest (LIFO)
        		const prioritizeNewest = true;
                        if (prioritizeNewest && vocabularySession.currentCard) {
                            const inProgress = result.queue_status.in_progress || 0;
                            if (result.queue_status.queue_length > inProgress && result.queue_status.queue_length > lastQueueLength) {
                                try {
                                    await fetch('/api/requeue-current-vocabulary-card', {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ username: currentUser, card: vocabularySession.currentCard })
                                    });
                                } catch (e) {}
                                const nextCard = await getNextVocabularyCard();
                                if (nextCard) displayVocabularyCard(nextCard);
                            }
                        }
                        lastQueueLength = result.queue_status.queue_length;
                    }
                } catch (error) {
                    console.error('Error polling vocabulary queue:', error);
                }
            }, 3000); // Poll every 3 seconds
        }

        async function getNextVocabularyCard() {
            try {
                const response = await fetch('/api/next-vocabulary-card', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: currentUser })
                });

                const result = await response.json();
                if (result.success && result.card) {
                    return result.card;
                }
            } catch (error) {
                console.error('Error getting next vocabulary card:', error);
            }
            return null;
        }

        function updateVocabularyQueue(queueStatus) {
            document.getElementById('queue-length').textContent = queueStatus.queue_length;
            document.getElementById('cached-answers').textContent = queueStatus.cached_answers;
            document.getElementById('auto-ready').textContent = queueStatus.cached_answers > 0 ? 'Yes' : 'No';

            // Enable submit button if there are cached answers
            document.getElementById('submit-vocabulary-session').disabled = queueStatus.cached_answers === 0;

            updateSessionStatus('vocab-status',
                queueStatus.queue_length > 0 ? 'Cards Available' : 'Polling',
                queueStatus.queue_length > 0 ? 'status-active' : 'status-waiting'
            );
        }

        function updateVocabularyStatus() {
            const cachedCount = Object.keys(vocabularySession.cachedAnswers).length;
            document.getElementById('cached-answers').textContent = cachedCount;
            document.getElementById('auto-ready').textContent = cachedCount > 0 ? 'Yes' : 'No';
            document.getElementById('submit-vocabulary-session').disabled = cachedCount === 0;
        }

        function showVocabularyFeedback(success) {
            const vocabContainer = document.querySelector('.vocabulary-session');
            if (!vocabContainer) return;

            // Remove any existing feedback classes
            vocabContainer.classList.remove('feedback-success', 'feedback-error');

            // Add appropriate feedback class
            const feedbackClass = success ? 'feedback-success' : 'feedback-error';
            vocabContainer.classList.add(feedbackClass);

            // Remove feedback after 2 seconds
            setTimeout(() => {
                vocabContainer.classList.remove(feedbackClass);
            }, 2000);
        }

        async function submitVocabularySession() {
            if (Object.keys(vocabularySession.cachedAnswers).length === 0) {
                alert('No cached vocabulary answers to submit');
                return;
            }

            try {
                const response = await fetch('/api/submit-vocabulary-session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: currentUser })
                });

                const result = await response.json();
                if (result.success) {
                    alert(`Auto-session completed! Successfully processed ${result.processed_count} vocabulary cards.`);

                    // Clear cached answers
                    vocabularySession.cachedAnswers = {};
                    // Clear current card so next poll can show newly created ones
                    vocabularySession.currentCard = null;
                    updateVocabularyStatus();
                } else {
                    alert('Error submitting vocabulary session: ' + result.error);
                }
            } catch (error) {
                alert('Error submitting vocabulary session: ' + error.message);
            }
        }

        function updateSessionStatus(elementId, text, statusClass) {
            const element = document.getElementById(elementId);
            element.textContent = text;
            element.className = 'session-status ' + statusClass;
        }

        async function closeAllSessions() {
            if (pollingInterval) {
                clearInterval(pollingInterval);
                pollingInterval = null;
            }

            try {
                const response = await fetch('/api/close-all-sessions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: currentUser })
                });

                const result = await response.json();
                alert('All sessions closed');

                // Reset UI
                document.getElementById('study-interface').classList.add('hidden');
                document.getElementById('session-controls').classList.add('hidden');
                document.getElementById('deck-selection').classList.remove('hidden');

                // Reset state
                grammarSession = { active: false, paused: false, currentCard: null };
                vocabularySession = { active: false, queue: [], cachedAnswers: {} };
                claudeProcessing = false;

            } catch (error) {
                alert('Error closing sessions: ' + error.message);
            }
        }

        // Cleanup on page unload
        window.addEventListener('beforeunload', async (event) => {
            if (pollingInterval) {
                clearInterval(pollingInterval);
            }

            // Close active study sessions when page is unloaded
            try {
                await fetch('/api/close-all-sessions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: currentUser }),
                    keepalive: true  // Ensure request completes even after page unloads
                });
            } catch (error) {
                console.error('Error closing sessions on page unload:', error);
            }
        });
    </script>
</body>
</html>
""")

# API Endpoints for Enhanced Functionality

@app.post("/api/start-dual-session")
async def start_dual_session(request: Request):
    """Start dual study session (grammar + vocabulary polling)"""
    global claude_integration, current_user, current_deck_id

    try:
        data = await request.json()
        username = data.get("username")
        deck_id = data.get("deck_id")

        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        current_user = username
        current_deck_id = deck_id

        # Start grammar session
        result = await claude_integration.start_grammar_session(deck_id)

        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/flip-card")
async def flip_card(request: Request):
    """Flip the current grammar card to show the back"""
    global claude_integration, current_user

    try:
        data = await request.json()
        username = data.get("username", current_user or "chase")

        if not claude_integration or not claude_integration.grammar_session:
            return JSONResponse({"success": False, "error": "No active grammar session"})

        # Use the study operations to flip the card
        from AnkiClient.src.operations import study_ops

        result, status_code = study_ops.study(
            deck_id=claude_integration.grammar_session.deck_id,
            action="flip",
            username=username
        )

        if status_code == 200:
            # Debug: Print the result structure
            print(f"DEBUG - Flip result structure: {result}")
            print(f"DEBUG - Result type: {type(result)}")
            print(f"DEBUG - Result keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}")

            # Preserve the card_id across flip results (flip payload lacks card_id)
            try:
                existing_id = None
                if isinstance(claude_integration.grammar_session.current_card, dict):
                    existing_id = claude_integration.grammar_session.current_card.get("card_id")
                if isinstance(result, dict) and existing_id and not result.get("card_id"):
                    result["card_id"] = existing_id
            except Exception as _e:
                logger.warning(f"Could not preserve card_id on flip: {_e}")

            # Update the current card in the session
            claude_integration.grammar_session.current_card = result

            return JSONResponse({
                "success": True,
                "current_card": result,
                "message": "Card flipped successfully"
            })
        else:
            return JSONResponse({
                "success": False,
                "error": f"Failed to flip card: {result.get('error', 'Unknown error')}"
            })

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/request-definitions")
async def request_definitions(request: Request):
    """Request word definitions from Claude SDK"""
    global claude_integration, current_user

    try:
        data = await request.json()
        words = data.get("words", [])
        card_context = data.get("card_context", {})

        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        # CRITICAL: Close study session before Claude SDK request
        # This allows Claude SDK to create Anki cards
        try:
            from AnkiClient.src.operations import study_ops

            # Close any active study sessions
            close_result = study_ops.study(
                deck_id=claude_integration.grammar_session.deck_id,
                action="close",
                username=current_user or "chase"
            )

            logger.info("Closed study session before Claude SDK request")

        except Exception as e:
            logger.warning(f"Error closing study session: {e}")

        # Now make the Claude SDK request
        result = await claude_integration.pause_grammar_session_for_definition(words)

        # Add info that session was closed
        if result.get('success'):
            result['study_session_closed_by_web_ui'] = True

        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/request-vocabulary-definitions")
async def request_vocabulary_definitions(request: Request):
    """Request priority vocabulary definitions from Claude SDK"""
    global claude_integration

    try:
        data = await request.json()
        words = data.get("words", [])
        card_context = data.get("card_context", {})
        priority = data.get("priority", True)

        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        # Priority vocabulary definitions would go here
        # This would use the same mechanism but with higher priority
        result = await claude_integration.pause_grammar_session_for_definition(words)

        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/answer-grammar-card")
async def answer_grammar_card(request: Request):
    """Answer grammar card (with caching if Claude is processing)"""
    global claude_integration, current_user

    try:
        data = await request.json()
        card_id = data.get("card_id")
        answer = data.get("answer")
        claude_processing = data.get("claude_processing", False)
        is_cached_answer = data.get("is_cached_answer", False)  # New flag for cached answers

        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        if claude_processing:
            # Cache the answer while Claude SDK is processing
            await claude_integration.cache_user_answer(card_id, answer)
            return JSONResponse({
                "success": True,
                "cached": True,
                "message": "Answer cached. Continue with vocabulary study or submit this cached answer to resume grammar session."
            })
        elif is_cached_answer:
            # This is the submission of a previously cached answer
            # Restart grammar session and auto-answer only if the popped card matches
            try:
                from AnkiClient.src.operations import study_ops

                logger.info("Resuming grammar session; will auto-answer only if current card matches cached")

                # Restart grammar study session to get the current card
                start_result, start_status = study_ops.study(
                    deck_id=claude_integration.grammar_session.deck_id,
                    action="start",
                    username=current_user or "chase"
                )

                if start_status == 200 and start_result.get("card_id"):
                    # Update integration session state
                    claude_integration.grammar_session.current_card = start_result
                    claude_integration.grammar_session.is_paused = False

                    # Attempt auto-answer if the current card matches a cached answer
                    auto = await claude_integration.auto_answer_if_current_matches(start_result)

                    # Determine which card to display now
                    card_to_display = auto.get("next_card") if auto.get("applied") else start_result

                    return JSONResponse({
                        "success": True,
                        "session_restarted": True,
                        "grammar_session_resumed": True,
                        # Keep legacy shape expected by frontend submitCachedAnswer()
                        "answer_result": {"current_card": card_to_display},
                        "auto_answer_applied": auto.get("applied", False),
                        "message": "Grammar session resumed" if not auto.get("applied") else "Grammar session resumed and cached answer auto-applied"
                    })
                else:
                    return JSONResponse({"success": False, "error": "Failed to restart grammar session"})

            except Exception as e:
                logger.error(f"Error restarting grammar session with cached answer: {e}")
                return JSONResponse({"success": False, "error": str(e)})
        else:
            # Regular grammar card answer (session should already be active)
            try:
                from AnkiClient.src.operations import study_ops

                answer_result = study_ops.study(
                    deck_id=claude_integration.grammar_session.deck_id,
                    action=str(answer),
                    username=current_user or "chase"
                )

                # Update current card in integration state
                next_card = answer_result[0]
                if next_card and isinstance(next_card, dict) and next_card.get("card_id"):
                    claude_integration.grammar_session.current_card = next_card

                # Attempt auto-answer if the next card matches any cached answer
                auto = await claude_integration.auto_answer_if_current_matches(next_card)

                # Normalize response so frontend can display a next_card
                response_payload = {
                    "success": True,
                    "answer_result": answer_result[0],
                    "next_card": auto.get("next_card") if auto.get("applied") else next_card,
                    "auto_answer_applied": auto.get("applied", False)
                }

                return JSONResponse(response_payload)

            except Exception as e:
                logger.error(f"Error submitting regular grammar answer: {e}")
                return JSONResponse({"success": False, "error": str(e)})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/cache-vocabulary-answer")
async def cache_vocabulary_answer(request: Request):
    """Cache vocabulary card answer for auto-session"""
    global claude_integration

    try:
        data = await request.json()
        card_id = data.get("card_id")
        answer = data.get("answer")

        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        claude_integration.cache_vocabulary_answer(card_id, answer)

        return JSONResponse({"success": True})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/vocabulary-queue-status")
async def vocabulary_queue_status(request: Request):
    """Get vocabulary queue status"""
    global claude_integration

    try:
        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        status = claude_integration.get_vocabulary_queue_status()

        return JSONResponse({"success": True, "queue_status": status})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/next-vocabulary-card")
async def next_vocabulary_card(request: Request):
    """Get next vocabulary card from LIFO queue"""
    global claude_integration

    try:
        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        card = claude_integration.get_next_vocabulary_card()

        return JSONResponse({"success": True, "card": card})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/requeue-current-vocabulary-card")
async def requeue_current_vocabulary_card(request: Request):
    """Requeue the currently displayed vocabulary card to the top of the LIFO queue."""
    global claude_integration

    try:
        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        data = await request.json()
        card = data.get("card")
        if not isinstance(card, dict):
            return JSONResponse({"success": False, "error": "Invalid card payload"})

        result = claude_integration.requeue_current_vocabulary_card(card)
        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/submit-vocabulary-session")
async def submit_vocabulary_session(request: Request):
    """Submit vocabulary session for auto-processing"""
    global claude_integration

    try:
        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        result = await claude_integration.submit_vocabulary_session()

        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/close-all-sessions")
async def close_all_sessions(request: Request):
    """Close all study sessions"""
    global claude_integration

    try:
        if claude_integration:
            await claude_integration.cleanup()

        return JSONResponse({"success": True, "message": "All sessions closed"})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

# Keep existing API endpoints for compatibility
@app.post("/api/decks")
async def get_decks(request: Request):
    """Get decks for user."""
    try:
        data = await request.json()
        username = data.get("username")

        if not username:
            return JSONResponse({"error": "Username is required"}, status_code=400)

        # Use the deck operations from AnkiClient
        result = deck_ops.get_decks(username=username)

        # Check if result is a tuple (result, status_code) or just result
        if isinstance(result, tuple):
            return JSONResponse(result[0], status_code=result[1])
        else:
            return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# CLI interface
cli = typer.Typer(help="Enhanced AnkiChat Web Interface with Claude SDK Integration")

@cli.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind the server to"),
    port: int = typer.Option(8000, help="Port to bind the server to"),
):
    """Start the enhanced AnkiChat web interface server."""
    print(f"🚀 Starting Enhanced AnkiChat Web Interface on http://{host}:{port}")
    print("🧠 Features: Dual study sessions, Claude SDK integration, LIFO vocabulary queue")
    uvicorn.run(app, host=host, port=port)

def main():
    """Main entry point for the CLI."""
    cli()

if __name__ == "__main__":
    main()
