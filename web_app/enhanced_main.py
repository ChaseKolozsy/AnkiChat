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

        /* Stats Bar Styles */
        .stats-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding: 10px 15px;
            background: #2a2a2a;
            border-radius: 8px;
            border: 1px solid #404040;
            font-size: 14px;
            font-weight: 500;
        }
        .stat-item {
            color: #b8b8b8;
        }
        .stat-value {
            color: #4a9eff;
            font-weight: 600;
        }

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
            <h2>Setup & Login</h2>
            <div class="form-group">
                <label for="profile-name">Profile Name:</label>
                <input type="text" id="profile-name" placeholder="Enter profile name (e.g. chase)" value="chase">
            </div>
            <div class="form-group">
                <label for="username">AnkiWeb Username:</label>
                <input type="text" id="username" placeholder="Enter your AnkiWeb username">
            </div>
            <div class="form-group">
                <label for="password">AnkiWeb Password:</label>
                <input type="password" id="password" placeholder="Enter your AnkiWeb password">
            </div>
            <div class="form-group">
                <label for="endpoint">Endpoint (optional):</label>
                <input type="text" id="endpoint" placeholder="Leave blank for default">
            </div>
            <div style="margin-bottom: 15px;">
                <input type="checkbox" id="upload-checkbox">
                <label for="upload-checkbox">Upload changes to AnkiWeb</label>
            </div>
            <button class="btn" onclick="loginAndLoadDecks()" id="load-decks-btn">Login & Load Decks</button>
            <button class="btn" onclick="syncOnDemand()" id="sync-btn" style="background: #28a745;" disabled>🔄 Sync Now</button>
            <div id="login-status" style="margin-top: 10px; font-size: 14px;"></div>
        </div>

        <!-- Deck Selection -->
        <div class="card hidden" id="deck-selection">
            <h2>Select Study Decks</h2>
            <div style="margin-bottom: 20px;">
                <h3 style="color: #0084ff; margin-bottom: 10px;">📚 Grammar Deck (Main Session)</h3>
                <div id="deck-list"></div>
            </div>
            <div style="margin-bottom: 20px;">
                <h3 style="color: #ff6b35; margin-bottom: 10px;">📖 Vocabulary Deck (For New Cards)</h3>
                <div id="vocab-deck-list"></div>
            </div>
            <button class="btn" id="start-study" onclick="startGrammarSession()" disabled>Start Grammar Session</button>
        </div>

        <!-- Dual Study Sessions -->
        <div class="sessions-container hidden" id="study-interface">
            <!-- Grammar Session (Main) -->
            <div class="session-column">
                <div class="card grammar-session">
                    <h2>📚 Grammar Session <span class="session-status status-active" id="grammar-status">Active</span></h2>

                    <div class="stats-bar">
                        <span class="stat-item">Status: <span class="stat-value" id="session-stats">Ready to start</span></span>
                        <span class="stat-item" id="counts">
                            New: <span class="stat-value" id="count-new">0</span>
                             • Learn: <span class="stat-value" id="count-learn">0</span>
                             • Review: <span class="stat-value" id="count-review">0</span>
                             • Total: <span class="stat-value" id="count-total">0</span>
                        </span>
                        <span class="stat-item" id="card-counter">Cards: <span class="stat-value">0</span></span>
                    </div>

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
                            <div id="vocab-completion-requirement" style="margin: 10px 0; padding: 8px; background: #2d1b69; border-radius: 6px; border: 1px solid #ff6b35;">
                                <strong>📖 Complete vocabulary cards first:</strong> Study all vocabulary cards and submit the auto-session before resuming grammar.
                            </div>
                            <button class="btn btn-good" onclick="submitCachedAnswer()" id="submit-cached-btn" style="margin-top: 10px;" disabled>
                                Submit Cached Answer & Resume Grammar
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Vocabulary Session (Layer-based Custom Study) -->
            <div class="session-column">
                <div class="card vocabulary-session">
                    <h2>📖 Vocabulary Study Session <span class="session-status status-waiting" id="vocab-status">Waiting for custom study session</span></h2>

                    <div class="vocabulary-info">
                        <div><strong>Current Layer:</strong> <span id="current-layer-tag">None</span></div>
                        <div><strong>Cards Remaining:</strong> <span id="vocab-cards-remaining">0</span></div>
                    </div>

                    <div id="vocabulary-card-display" class="card-display hidden">
                        <!-- Vocabulary card content will be displayed here -->
                    </div>

                    <div class="form-group hidden" id="vocab-define-section">
                        <label>Define words (creates nested layer):</label>
                        <textarea id="vocab-words-to-define" placeholder="Enter words from vocabulary card" rows="2"></textarea>
                        <button class="btn btn-claude" onclick="requestVocabularyDefinitions()">
                            Define Words
                        </button>
                    </div>

                    <div class="answer-buttons hidden" id="vocabulary-answers">
                        <button class="btn btn-answer btn-again" onclick="answerVocabularyCard(1)">❌ Again</button>
                        <button class="btn btn-answer btn-hard" onclick="answerVocabularyCard(2)">⚠️ Hard</button>
                        <button class="btn btn-answer btn-good" onclick="answerVocabularyCard(3)">✅ Good</button>
                        <button class="btn btn-answer btn-easy" onclick="answerVocabularyCard(4)">🎯 Easy</button>
                    </div>

                    <div class="vocab-controls hidden" id="vocab-controls">
                        <button class="btn" onclick="checkVocabularySession()">🔄 Check Session</button>
                        <button class="btn btn-vocabulary" onclick="completeVocabularySession()">
                            Complete Session
                        </button>
                    </div>
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
        let selectedGrammarDeck = null;
        let selectedVocabularyDeck = null;
        let grammarSession = { active: false, paused: false, currentCard: null };
        let vocabularySession = {
            active: false,
            currentLayer: null,
            currentCustomDeckId: null,
            currentCard: null,
            availableLayers: []
        };
        let pollingInterval = null;
        let claudeProcessing = false;
        let cachedGrammarAnswer = null;  // Store cached answer for later submission
        let cachedCounts = { new: 0, learning: 0, review: 0, total: 0 };  // Cache counts to avoid collection conflicts

        // Cached credentials for on-demand sync (simple XOR encryption for basic obfuscation)
        let cachedCredentials = null;
        const encryptionKey = "AnkiChatWebSync2024"; // Simple key for XOR

        // Simple XOR encryption/decryption for credential caching
        function simpleEncrypt(text) {
            let result = '';
            for (let i = 0; i < text.length; i++) {
                result += String.fromCharCode(text.charCodeAt(i) ^ encryptionKey.charCodeAt(i % encryptionKey.length));
            }
            return btoa(result); // Base64 encode
        }

        function simpleDecrypt(encrypted) {
            try {
                const decoded = atob(encrypted); // Base64 decode
                let result = '';
                for (let i = 0; i < decoded.length; i++) {
                    result += String.fromCharCode(decoded.charCodeAt(i) ^ encryptionKey.charCodeAt(i % encryptionKey.length));
                }
                return result;
            } catch (e) {
                console.error('Decryption failed:', e);
                return null;
            }
        }

        function cacheCredentials(profileName, username, password, endpoint, upload) {
            cachedCredentials = {
                profileName: profileName,
                username: username,
                password: simpleEncrypt(password), // Encrypt password
                endpoint: endpoint,
                upload: upload
            };
            console.log('Credentials cached for future sync operations');
        }

        function getCachedCredentials() {
            if (!cachedCredentials) return null;
            return {
                profileName: cachedCredentials.profileName,
                username: cachedCredentials.username,
                password: simpleDecrypt(cachedCredentials.password), // Decrypt password
                endpoint: cachedCredentials.endpoint,
                upload: cachedCredentials.upload
            };
        }

        // Login and deck loading functions following db_ops.py protocol
        async function loginAndLoadDecks() {
            const profileName = document.getElementById('profile-name').value.trim();
            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value.trim();
            const endpoint = document.getElementById('endpoint').value.trim();
            const upload = document.getElementById('upload-checkbox').checked;

            if (!profileName || !username || !password) {
                alert('Please enter profile name, username, and password');
                return;
            }

            const loadButton = document.getElementById('load-decks-btn');
            const statusDiv = document.getElementById('login-status');

            // Update UI to show loading
            loadButton.disabled = true;
            loadButton.textContent = 'Logging in...';
            statusDiv.innerHTML = '<span style="color: #0084ff;">🔄 Performing AnkiWeb login and sync...</span>';

            try {
                // Step 1: Login and sync following db_ops.py protocol
                const loginResponse = await fetch('/api/login-and-sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        profile_name: profileName,
                        username: username,
                        password: password,
                        endpoint: endpoint || null,
                        upload: upload
                    })
                });

                const loginResult = await loginResponse.json();

                if (!loginResponse.ok || !loginResult.success) {
                    throw new Error(loginResult.error || loginResult.details || 'Login failed');
                }

                statusDiv.innerHTML = '<span style="color: #28a745;">✅ Login and sync successful!</span>';
                console.log('Login result:', loginResult);

                // Cache credentials for future sync operations
                cacheCredentials(profileName, username, password, endpoint, upload);

                // Enable sync button now that credentials are cached
                document.getElementById('sync-btn').disabled = false;

                // Step 2: Load decks using the profile name
                currentUser = profileName; // Use profile name for deck operations
                await loadDecks();

            } catch (error) {
                console.error('Error during login and sync:', error);
                statusDiv.innerHTML = `<span style="color: #dc3545;">❌ Error: ${error.message}</span>`;
                alert('Login failed: ' + error.message);
            } finally {
                // Reset button state
                loadButton.disabled = false;
                loadButton.textContent = 'Login & Load Decks';
            }
        }

        // Deck loading function (now called after successful login)
        async function loadDecks() {
            if (!currentUser) {
                alert('Please login first');
                return;
            }

            const statusDiv = document.getElementById('login-status');
            statusDiv.innerHTML = '<span style="color: #0084ff;">🔄 Loading decks...</span>';

            try {
                const response = await fetch('/api/decks', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: currentUser })
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

                await displayDecks(decks);
                statusDiv.innerHTML = '<span style="color: #28a745;">✅ Ready to study!</span>';
            } catch (error) {
                console.error('Error loading decks:', error);
                statusDiv.innerHTML = `<span style="color: #dc3545;">❌ Error loading decks: ${error.message}</span>`;
                alert('Error loading decks: ' + error.message);
            }
        }

        // Close study sessions specifically for sync operations
        async function closeStudySessionsForSync() {
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
                console.log('Close sessions result:', result);

                // Reset UI state
                document.getElementById('study-interface').classList.add('hidden');
                document.getElementById('session-controls').classList.add('hidden');
                document.getElementById('deck-selection').classList.remove('hidden');

                // Reset session state
                grammarSession = { active: false, paused: false, currentCard: null };
                vocabularySession = { active: false, queue: [], cachedAnswers: {} };
                claudeProcessing = false;

                return result;
            } catch (error) {
                console.error('Error closing sessions:', error);
                throw error;
            }
        }

        // On-demand sync function using cached credentials
        async function syncOnDemand() {
            const credentials = getCachedCredentials();
            if (!credentials) {
                alert('No cached credentials available. Please login first.');
                return;
            }

            const syncButton = document.getElementById('sync-btn');
            const statusDiv = document.getElementById('login-status');

            // Update UI to show syncing
            syncButton.disabled = true;
            syncButton.textContent = '🔄 Syncing...';

            // Check if there's an active study session and close it first
            if (grammarSession.active) {
                statusDiv.innerHTML = '<span style="color: #ff6b35;">⏸️ Closing active study session before sync...</span>';
                console.log('Active study session detected, closing before sync');

                try {
                    await closeStudySessionsForSync();
                    console.log('Study session closed successfully');
                } catch (sessionError) {
                    console.warn('Error closing study session:', sessionError);
                    // Continue with sync anyway since collection might be accessible
                }
            }

            statusDiv.innerHTML = '<span style="color: #0084ff;">🔄 Performing on-demand sync...</span>';

            try {
                // Use cached credentials for sync
                const syncResponse = await fetch('/api/login-and-sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        profile_name: credentials.profileName,
                        username: credentials.username,
                        password: credentials.password,
                        endpoint: credentials.endpoint || null,
                        upload: credentials.upload
                    })
                });

                const syncResult = await syncResponse.json();

                if (!syncResponse.ok || !syncResult.success) {
                    throw new Error(syncResult.error || syncResult.details || 'Sync failed');
                }

                statusDiv.innerHTML = '<span style="color: #28a745;">✅ Sync completed successfully!</span>';
                console.log('On-demand sync result:', syncResult);

                // Refresh deck list and counts after sync
                await loadDecks();

                // Auto-clear status after 3 seconds
                setTimeout(() => {
                    statusDiv.innerHTML = '<span style="color: #28a745;">✅ Ready to study!</span>';
                }, 3000);

            } catch (error) {
                console.error('Error during on-demand sync:', error);
                statusDiv.innerHTML = `<span style="color: #dc3545;">❌ Sync error: ${error.message}</span>`;
                alert('Sync failed: ' + error.message);
            } finally {
                // Reset button state
                syncButton.disabled = false;
                syncButton.textContent = '🔄 Sync Now';
            }
        }

        async function displayDecks(decks) {
            const deckList = document.getElementById('deck-list');
            const vocabDeckList = document.getElementById('vocab-deck-list');
            const deckSelection = document.getElementById('deck-selection');

            if (!decks || decks.length === 0) {
                deckList.innerHTML = '<p>No decks found for this user.</p>';
                vocabDeckList.innerHTML = '<p>No decks found for this user.</p>';
            } else {
                // Display grammar decks
                deckList.innerHTML = decks.map(deck => `
                    <div class="deck-item" onclick="selectGrammarDeck(${deck.id}, '${deck.name}')"
                         style="background: #404040; border-radius: 8px; padding: 15px; margin-bottom: 10px; cursor: pointer; transition: all 0.2s;">
                        <strong>${deck.name}</strong>
                        <div style="font-size: 14px; opacity: 0.7; margin-top: 5px;">
                            ID: ${deck.id}
                        </div>
                        <div id="counts-${deck.id}" style="font-size: 12px; margin-top: 8px; color: #4a9eff;">
                            Loading counts...
                        </div>
                    </div>
                `).join('');

                // Display vocabulary decks (same list, different selection handler)
                vocabDeckList.innerHTML = decks.map(deck => `
                    <div class="vocab-deck-item" onclick="selectVocabularyDeck(${deck.id}, '${deck.name}')"
                         style="background: #404040; border-radius: 8px; padding: 15px; margin-bottom: 10px; cursor: pointer; transition: all 0.2s;">
                        <strong>${deck.name}</strong>
                        <div style="font-size: 14px; opacity: 0.7; margin-top: 5px;">
                            ID: ${deck.id}
                        </div>
                        <div id="vocab-counts-${deck.id}" style="font-size: 12px; margin-top: 8px; color: #ff6b35;">
                            Loading counts...
                        </div>
                    </div>
                `).join('');

                // Fetch counts for each deck
                fetchDeckCounts(decks);
            }

            deckSelection.classList.remove('hidden');

            // Note: Vocabulary layers are loaded when starting dual session (no auto-polling)
        }

        async function fetchDeckCounts(decks) {
            for (const deck of decks) {
                try {
                    const response = await fetch('/api/study/counts', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ deck_id: deck.id, username: currentUser })
                    });

                    if (response.ok) {
                        const counts = await response.json();

                        // Update grammar deck counts
                        const countsElement = document.getElementById(`counts-${deck.id}`);
                        if (countsElement) {
                            countsElement.innerHTML = `
                                <span style="color: #28a745;">New: ${counts.new}</span> •
                                <span style="color: #ffc107;">Learning: ${counts.learning}</span> •
                                <span style="color: #17a2b8;">Review: ${counts.review}</span> •
                                <span style="color: #6c757d;">Total: ${counts.total}</span>
                            `;
                        }

                        // Update vocabulary deck counts
                        const vocabCountsElement = document.getElementById(`vocab-counts-${deck.id}`);
                        if (vocabCountsElement) {
                            vocabCountsElement.innerHTML = `
                                <span style="color: #28a745;">New: ${counts.new}</span> •
                                <span style="color: #ffc107;">Learning: ${counts.learning}</span> •
                                <span style="color: #17a2b8;">Review: ${counts.review}</span> •
                                <span style="color: #6c757d;">Total: ${counts.total}</span>
                            `;
                        }
                    } else {
                        const countsElement = document.getElementById(`counts-${deck.id}`);
                        if (countsElement) {
                            countsElement.innerHTML = '<span style="color: #dc3545;">Failed to load counts</span>';
                        }

                        const vocabCountsElement = document.getElementById(`vocab-counts-${deck.id}`);
                        if (vocabCountsElement) {
                            vocabCountsElement.innerHTML = '<span style="color: #dc3545;">Failed to load counts</span>';
                        }
                    }
                } catch (error) {
                    const countsElement = document.getElementById(`counts-${deck.id}`);
                    if (countsElement) {
                        countsElement.innerHTML = '<span style="color: #dc3545;">Error loading counts</span>';
                    }

                    const vocabCountsElement = document.getElementById(`vocab-counts-${deck.id}`);
                    if (vocabCountsElement) {
                        vocabCountsElement.innerHTML = '<span style="color: #dc3545;">Error loading counts</span>';
                    }
                }
            }
        }

        function selectGrammarDeck(deckId, deckName) {
            document.querySelectorAll('.deck-item').forEach(item => {
                item.style.background = '#404040';
            });
            event.target.closest('.deck-item').style.background = '#0084ff';

            selectedGrammarDeck = { id: deckId, name: deckName };
            checkBothDecksSelected();
        }

        function selectVocabularyDeck(deckId, deckName) {
            document.querySelectorAll('.vocab-deck-item').forEach(item => {
                item.style.background = '#404040';
            });
            event.target.closest('.vocab-deck-item').style.background = '#ff6b35';

            selectedVocabularyDeck = { id: deckId, name: deckName };
            checkBothDecksSelected();
        }

        function checkBothDecksSelected() {
            const startButton = document.getElementById('start-study');
            if (selectedGrammarDeck && selectedVocabularyDeck) {
                startButton.disabled = false;
                startButton.textContent = `Start Session: ${selectedGrammarDeck.name} → ${selectedVocabularyDeck.name}`;
            } else {
                startButton.disabled = true;
                startButton.textContent = 'Select both decks to start';
            }
        }

        // Enhanced Study Session Functions
        async function startGrammarSession() {
            if (!selectedGrammarDeck || !selectedVocabularyDeck || !currentUser) {
                alert('Please select both a grammar deck and a vocabulary deck');
                return;
            }

            try {
                // First, fetch and cache counts BEFORE starting the session
                console.log('Fetching counts before starting session...');
                const countsFetched = await fetchAndCacheCounts();
                if (!countsFetched) {
                    console.warn('Failed to fetch initial counts, proceeding anyway');
                }

                // Start grammar session (uses existing dual-session endpoint but only starts grammar)
                const response = await fetch('/api/start-dual-session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUser,
                        grammar_deck_id: selectedGrammarDeck.id,
                        vocabulary_deck_id: selectedVocabularyDeck.id
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

                    // Initialize vocabulary session as waiting - no active setup yet
                    document.getElementById('vocab-status').textContent = 'Waiting for vocabulary definitions...';
                    document.getElementById('vocab-status').className = 'session-status status-waiting';
                    document.getElementById('current-layer-tag').textContent = 'None';
                    document.getElementById('vocab-cards-remaining').textContent = '0';
                    document.getElementById('vocab-controls').classList.add('hidden');

                    console.log('Grammar session started. Vocabulary session will start when Claude SDK finishes creating definitions.');

                    // Start polling for vocabulary session creation
                    startVocabularySessionPolling();

                    // Render the cached counts (no fetching during session)
                    renderCachedCounts();

                    updateSessionStatus('grammar-status', 'Active', 'status-active');
                    updateSessionStatus('vocab-status', 'No Active Layer', 'status-waiting');

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

        async function fetchAndCacheCounts() {
            try {
                const deckId = selectedGrammarDeck ? selectedGrammarDeck.id : null;
                if (!deckId) {
                    console.log('No deck selected, skipping counts fetch');
                    return false;
                }
                console.log('Fetching and caching counts for deck:', deckId, 'user:', currentUser);
                const response = await fetch('/api/study/counts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ deck_id: deckId, username: currentUser })
                });
                if (!response.ok) {
                    console.log('Failed to fetch counts:', response.status, response.statusText);
                    return false;
                }
                const data = await response.json();
                console.log('Received counts data:', data);

                // Cache the counts
                cachedCounts = {
                    new: typeof data.new === 'number' ? data.new : 0,
                    learning: typeof data.learning === 'number' ? data.learning : 0,
                    review: typeof data.review === 'number' ? data.review : 0,
                    total: typeof data.total === 'number' ? data.total : 0
                };

                // Update the UI with cached counts
                renderCachedCounts();
                return true;
            } catch (e) {
                console.error('Error fetching counts:', e);
                return false;
            }
        }

        function renderCachedCounts() {
            document.getElementById('count-new').textContent = cachedCounts.new;
            document.getElementById('count-learn').textContent = cachedCounts.learning;
            document.getElementById('count-review').textContent = cachedCounts.review;
            document.getElementById('count-total').textContent = cachedCounts.total;
            console.log('Rendered cached counts:', cachedCounts);
        }

        function updateCachedCountsAfterAnswer(ease) {
            // Decrement the appropriate count based on the card state and answer
            // This is an approximation since we don't know the exact card state transitions
            if (cachedCounts.total > 0) {
                cachedCounts.total--;

                // Simple heuristic: assume we're mostly dealing with new cards initially
                if (cachedCounts.new > 0) {
                    cachedCounts.new--;
                    // Hard answers might move to learning
                    if (ease <= 2 && cachedCounts.learning >= 0) {
                        cachedCounts.learning++;
                    }
                } else if (cachedCounts.learning > 0) {
                    cachedCounts.learning--;
                } else if (cachedCounts.review > 0) {
                    cachedCounts.review--;
                }

                renderCachedCounts();
            }
        }

        // Deprecated function - kept for compatibility but now uses cached counts
        async function fetchAndRenderCounts() {
            // During active study session, just render cached counts
            if (grammarSession.active) {
                console.log('Study session active, using cached counts');
                renderCachedCounts();
                return;
            }

            // If no active session, fetch fresh counts
            await fetchAndCacheCounts();
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

                    // Annotate ease buttons with next interval labels if provided
                    console.log('Card flip data:', result.current_card);
                    console.log('Card type:', typeof result.current_card);
                    console.log('Card keys:', Object.keys(result.current_card || {}));

                    // Check if ease_options is in the main data object
                    let easeOptions = null;
                    if (result.current_card && result.current_card.ease_options) {
                        easeOptions = result.current_card.ease_options;
                    }

                    if (easeOptions) {
                        console.log('Ease options found:', easeOptions);
                        const again = easeOptions['1'] || '';
                        const hard = easeOptions['2'] || '';
                        const good = easeOptions['3'] || '';
                        const easy = easeOptions['4'] || '';
                        console.log('Parsed intervals - Again:', again, 'Hard:', hard, 'Good:', good, 'Easy:', easy);

                        console.log('Finding buttons...');
                        const btnAgain = document.querySelector('.btn-again');
                        const btnHard = document.querySelector('.btn-hard');
                        const btnGood = document.querySelector('.btn-good');
                        const btnEasy = document.querySelector('.btn-easy');

                        console.log('Buttons found:', {
                            btnAgain: !!btnAgain,
                            btnHard: !!btnHard,
                            btnGood: !!btnGood,
                            btnEasy: !!btnEasy
                        });

                        if (btnAgain) {
                            const newText = again ? `1 - Again (${again})` : '1 - Again';
                            btnAgain.textContent = newText;
                            console.log('Updated Again button text to:', newText);
                            console.log('Button actual textContent after update:', btnAgain.textContent);
                        }
                        if (btnHard) {
                            const newText = hard ? `2 - Hard (${hard})` : '2 - Hard';
                            btnHard.textContent = newText;
                            console.log('Updated Hard button text to:', newText);
                            console.log('Button actual textContent after update:', btnHard.textContent);
                        }
                        if (btnGood) {
                            const newText = good ? `3 - Good (${good})` : '3 - Good';
                            btnGood.textContent = newText;
                            console.log('Updated Good button text to:', newText);
                            console.log('Button actual textContent after update:', btnGood.textContent);
                        }
                        if (btnEasy) {
                            const newText = easy ? `4 - Easy (${easy})` : '4 - Easy';
                            btnEasy.textContent = newText;
                            console.log('Updated Easy button text to:', newText);
                            console.log('Button actual textContent after update:', btnEasy.textContent);
                        }
                    } else {
                        console.log('No ease_options found in response data');
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
                // Generate layer tag based on current grammar card
                const currentGrammarCard = grammarSession.currentCard;
                const grammarNoteId = currentGrammarCard?.note_id || currentGrammarCard?.id || Date.now();
                const layerTag = `layer_${grammarNoteId}`;

                // Store layer tag in client-side availableLayers immediately
                if (!vocabularySession.availableLayers) {
                    vocabularySession.availableLayers = [];
                }
                if (!vocabularySession.availableLayers.includes(layerTag)) {
                    vocabularySession.availableLayers.push(layerTag);
                    console.log(`Generated and stored layer tag: ${layerTag}`);
                    console.log(`Available layers now: ${vocabularySession.availableLayers.join(', ')}`);
                }

                const response = await fetch('/api/request-definitions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUser,
                        words: words.split(',').map(w => w.trim()),
                        card_context: grammarSession.currentCard,
                        layer_tag: layerTag  // Pass the generated layer tag to Claude Code
                    })
                });

                const result = await response.json();
                if (result.success) {
                    document.getElementById('claude-status').classList.remove('hidden');
                    grammarSession.paused = true;

                    console.log(`Successfully sent vocabulary definition request with layer tag: ${layerTag}`);
                    console.log('Claude Code will create vocabulary cards with this layer tag');

                    // No need to refresh layers since we already stored the layer tag client-side
                    // The vocabulary session will automatically detect the new layer when polling
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

        // OLD requestVocabularyDefinitions() removed - see new layer-based version below

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
                            // Update cached counts after answering
                            updateCachedCountsAfterAnswer(answer);
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

        // OLD answerVocabularyCard() and showVocabularyFeedback() removed
        // See new layer-based vocabulary functions below

        // ===== VOCABULARY STUDY SESSION FUNCTIONS =====

        async function checkVocabularySession() {
            try {
                // Step 1: Check client-side for layer tags (populated by Claude SDK)
                if (!vocabularySession.availableLayers || vocabularySession.availableLayers.length === 0) {
                    console.log('No layer tags available in client session - waiting for Claude SDK to populate them');
                    document.getElementById('current-layer-tag').textContent = 'None';
                    document.getElementById('vocab-status').textContent = 'Waiting for vocabulary definitions...';
                    document.getElementById('vocab-status').className = 'session-status status-waiting';
                    document.getElementById('vocab-cards-remaining').textContent = '0';
                    document.getElementById('vocab-controls').classList.add('hidden');
                    return;
                }

                // Sort client-side layers by length (longest first) - LIFO ordering
                const sortedAllLayers = vocabularySession.availableLayers.sort((a, b) => b.length - a.length);

                // Initialize completed layers tracking if not exists
                if (!vocabularySession.completedLayers) {
                    vocabularySession.completedLayers = [];
                }

                // Find next layer to study (first uncompleted layer)
                let nextLayerToStudy = null;
                for (const layerTag of sortedAllLayers) {
                    if (!vocabularySession.completedLayers.includes(layerTag)) {
                        nextLayerToStudy = layerTag;
                        break;
                    }
                }

                if (!nextLayerToStudy) {
                    // All layers completed
                    await completeVocabularySession();
                    return;
                }

                console.log(`Next layer to study: ${nextLayerToStudy}`);
                console.log(`Available layers (client-side): ${sortedAllLayers.join(', ')}`);
                console.log(`Completed layers: ${vocabularySession.completedLayers.join(', ')}`);

                // Step 2: Claude SDK should have already created custom study session
                // Check if we need to start studying from the existing custom study session
                const needsNewSession = vocabularySession.currentLayer !== nextLayerToStudy ||
                    !vocabularySession.isActive;

                if (needsNewSession) {
                    console.log(`Starting vocabulary study session for layer: ${nextLayerToStudy}`);

                    // Start studying from the custom study session (Claude SDK already created it)
                    // We don't need to create a new session - just start studying from the existing one
                    vocabularySession.currentLayer = nextLayerToStudy;
                    vocabularySession.isActive = true;

                    // Start studying from the custom study session directly
                    await startVocabularySession();
                } else {
                    console.log(`Already studying layer: ${nextLayerToStudy}`);
                }

                // Update UI with client-side layer information
                document.getElementById('current-layer-tag').textContent = nextLayerToStudy;
                document.getElementById('vocab-status').textContent = `Layer: ${nextLayerToStudy}`;
                document.getElementById('vocab-status').className = 'session-status status-active';
                document.getElementById('vocab-cards-remaining').textContent = vocabularySession.cardsByLayer?.[nextLayerToStudy]?.length || '?';

                // Store layer information (all client-side)
                vocabularySession.currentLayer = nextLayerToStudy;
                vocabularySession.cardsRemaining = vocabularySession.cardsByLayer?.[nextLayerToStudy]?.length || 0;

                // Show vocabulary controls
                document.getElementById('vocab-controls').classList.remove('hidden');

            } catch (error) {
                console.error('Error checking vocabulary session:', error);
            }
        }

        async function startVocabularyStudySession(layerTag) {
            try {
                console.log(`Starting vocabulary study session for layer: ${layerTag}`);

                // Close any existing vocabulary session first
                if (vocabularySession.currentCustomDeckId) {
                    await fetch('/api/close-custom-study-session', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            deck_id: vocabularySession.currentCustomDeckId,
                            username: currentUser
                        })
                    });
                }

                // Create custom study session for the layer
                const createResponse = await fetch('/api/create-custom-study-session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        deck_id: selectedVocabularyDeck.id,
                        username: currentUser,
                        tag: layerTag,
                        card_limit: 100
                    })
                });

                const createResult = await createResponse.json();
                if (createResult.success) {
                    // Start study session for the custom deck
                    const startResponse = await fetch('/api/start-study-session', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            deck_id: createResult.custom_study_deck_id,
                            username: currentUser
                        })
                    });

                    const startResult = await startResponse.json();
                    if (startResult.success) {
                        vocabularySession.currentCustomDeckId = createResult.custom_study_deck_id;
                        vocabularySession.isActive = true;

                        // Get first card via study endpoint (flip to get first card)
                        const flipResponse = await fetch('/api/study', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                deck_id: createResult.custom_study_deck_id,
                                action: 'flip',
                                username: currentUser
                            })
                        });

                        const flipResult = await flipResponse.json();
                        if (flipResult.success !== false && flipResult.front) {
                            vocabularySession.currentCard = flipResult;
                            displayVocabularyCard(flipResult);
                            document.getElementById('vocabulary-card-display').classList.remove('hidden');
                            document.getElementById('vocab-define-section').classList.remove('hidden');
                            document.getElementById('vocabulary-answers').classList.remove('hidden');
                        }

                        console.log(`Successfully started study session for layer: ${layerTag}`);
                    } else {
                        console.error('Failed to start vocabulary study session: ' + startResult.error);
                    }
                } else {
                    console.error('Failed to create custom study session: ' + createResult.error);
                }
            } catch (error) {
                console.error('Error starting vocabulary study session:', error);
            }
        }

        async function startVocabularySessionFromDeck(deckId) {
            try {
                console.log(`Starting vocabulary study session from deck: ${deckId}`);

                // Start study session for the custom deck (behave like grammar session)
                const startResponse = await fetch('/api/study-custom-session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        deck_id: deckId,
                        username: currentUser,
                        action: 'start'
                    })
                });

                const startResult = await startResponse.json();
                if (startResult.success && startResult.card) {
                    vocabularySession.currentCard = startResult.card;
                    vocabularySession.currentCustomDeckId = deckId;
                    vocabularySession.isActive = true;

                    // Display the vocabulary card using same logic as grammar
                    displayVocabularyCard(startResult.card);

                    // Show vocabulary interface
                    document.getElementById('vocabulary-card-display').classList.remove('hidden');
                    document.getElementById('vocab-define-section').classList.remove('hidden');
                    document.getElementById('vocabulary-answers').classList.remove('hidden');

                    console.log('Successfully started vocabulary study session');
                } else {
                    console.error('Failed to start vocabulary study session:', startResult.error || 'Unknown error');
                }
            } catch (error) {
                console.error('Error starting vocabulary study session:', error);
            }
        }

        async function createCustomStudySessionForLayer(layerTag) {
            try {
                console.log(`Creating custom study session for layer: ${layerTag}`);

                // Close any existing custom study session first
                if (vocabularySession.currentCustomDeckId) {
                    await fetch('/api/close-custom-study-session', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            deck_id: vocabularySession.currentCustomDeckId,
                            username: currentUser
                        })
                    });
                }

                // Create custom study session for the layer
                const createResponse = await fetch('/api/create-custom-study-session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        deck_id: selectedVocabularyDeck.id,
                        username: currentUser,
                        tag: layerTag,
                        card_limit: 100
                    })
                });

                const createResult = await createResponse.json();
                if (createResult.success) {
                    console.log(`Custom study session created for layer ${layerTag}, deck ID: ${createResult.custom_study_deck_id}`);

                    // Start studying from the new custom study session
                    await startVocabularySessionFromDeck(createResult.custom_study_deck_id);
                } else {
                    console.error('Failed to create custom study session:', createResult.error);
                }
            } catch (error) {
                console.error('Error creating custom study session for layer:', error);
            }
        }

        async function startVocabularySession() {
            try {
                console.log('Starting vocabulary study session from existing custom study session');

                // Use the study endpoint directly, just like grammar session
                const response = await fetch('/api/study', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        deck_id: vocabularySession.currentCustomDeckId || 'Custom Study Session', // Use the deck ID Claude SDK created
                        action: 'start',
                        username: currentUser
                    })
                });

                const result = await response.json();
                if (result.success && result.card) {
                    vocabularySession.currentCard = result.card;
                    vocabularySession.isActive = true;

                    // Display the vocabulary card using same logic as grammar
                    displayVocabularyCard(result.card);

                    // Show vocabulary interface
                    document.getElementById('vocabulary-card-display').classList.remove('hidden');
                    document.getElementById('vocab-define-section').classList.remove('hidden');
                    document.getElementById('vocabulary-answers').classList.remove('hidden');

                    console.log('Successfully started vocabulary study session');
                } else {
                    console.error('Failed to start vocabulary study session:', result.error || 'Unknown error');
                }
            } catch (error) {
                console.error('Error starting vocabulary study session:', error);
            }
        }

        let vocabularyPollingInterval = null;

        function startVocabularySessionPolling() {
            // Clear any existing polling
            if (vocabularyPollingInterval) {
                clearInterval(vocabularyPollingInterval);
            }

            // Poll every 3 seconds for vocabulary session creation
            vocabularyPollingInterval = setInterval(async () => {
                if (!vocabularySession.isActive) {
                    console.log('Polling for vocabulary session...');
                    await checkVocabularySession();
                } else {
                    // Vocabulary session started, stop polling
                    clearInterval(vocabularyPollingInterval);
                    vocabularyPollingInterval = null;
                    console.log('Vocabulary session detected, stopped polling');
                }
            }, 3000);
        }

        function selectLayer() {
            const layerSelect = document.getElementById('layer-select');
            const startBtn = document.getElementById('start-layer-btn');

            if (layerSelect.value) {
                startBtn.disabled = false;
            } else {
                startBtn.disabled = true;
            }
        }

        async function startLayerStudy() {
            const layerSelect = document.getElementById('layer-select');
            const selectedLayerTag = layerSelect.value;

            if (!selectedLayerTag) {
                alert('Please select a layer to study');
                return;
            }

            try {
                // Close any existing vocabulary session first
                if (vocabularySession.currentCustomDeckId) {
                    await fetch('/api/close-custom-study-session', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            deck_id: vocabularySession.currentCustomDeckId,
                            username: currentUser
                        })
                    });
                }

                // Create custom study session for the selected layer
                const createResponse = await fetch('/api/create-custom-study-session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        deck_id: selectedVocabularyDeck.id,
                        username: currentUser,
                        tag: selectedLayerTag,
                        card_limit: 100
                    })
                });

                const createResult = await createResponse.json();
                if (createResult.success) {
                    vocabularySession.currentLayer = selectedLayerTag;
                    vocabularySession.currentCustomDeckId = createResult.session_deck_id;

                    // Update UI
                    document.getElementById('current-layer-tag').textContent = selectedLayerTag;
                    updateSessionStatus('vocab-status', 'Active', 'status-active');

                    // Hide layer selector, show study interface
                    document.getElementById('layer-selector').classList.add('hidden');

                    // Start studying the custom session
                    await startCustomStudySession();
                } else {
                    alert('Error creating custom study session: ' + createResult.error);
                }
            } catch (error) {
                console.error('Error starting layer study:', error);
                alert('Error starting layer study: ' + error.message);
            }
        }

        async function startCustomStudySession() {
            try {
                const response = await fetch('/api/study', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        deck_id: vocabularySession.currentCustomDeckId,
                        action: 'start',
                        username: currentUser
                    })
                });

                const result = await response.json();
                if (result.success !== false && result.front) {
                    vocabularySession.currentCard = result;
                    displayVocabularyCard(result);
                    vocabularySession.active = true;
                } else if (result.message && result.message.includes('No more cards')) {
                    alert('No cards available in this layer');
                    await completeLayer();
                } else {
                    alert('Error starting custom study session: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error starting custom study session:', error);
                alert('Error starting custom study session: ' + error.message);
            }
        }

        async function answerVocabularyCard(answer) {
            if (!vocabularySession.currentCard) {
                alert('No current vocabulary card to answer');
                return;
            }

            try {
                // Use the study endpoint with the custom deck ID to answer the card
                const response = await fetch('/api/study', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        deck_id: vocabularySession.currentCustomDeckId,
                        action: answer.toString(),
                        username: currentUser
                    })
                });

                const result = await response.json();
                if (result.success !== false && result.front) {
                    // Got next card in current layer
                    vocabularySession.currentCard = result;
                    displayVocabularyCard(result);

                    // Update cards remaining count
                    if (vocabularySession.cardsRemaining > 0) {
                        vocabularySession.cardsRemaining--;
                        document.getElementById('vocab-cards-remaining').textContent = vocabularySession.cardsRemaining;
                    }
                } else if (result.message && result.message.includes('No more cards')) {
                    // Current layer completed - mark as completed and check for next layer
                    console.log(`Layer ${vocabularySession.currentLayer} completed, marking as completed and checking for next layer...`);

                    // Mark current layer as completed
                    if (!vocabularySession.completedLayers) {
                        vocabularySession.completedLayers = [];
                    }
                    if (!vocabularySession.completedLayers.includes(vocabularySession.currentLayer)) {
                        vocabularySession.completedLayers.push(vocabularySession.currentLayer);
                        console.log(`Marked layer ${vocabularySession.currentLayer} as completed`);
                        console.log(`Completed layers now: ${vocabularySession.completedLayers.join(', ')}`);
                    }

                    // Reset current card and check for next layer
                    vocabularySession.currentCard = null;
                    vocabularySession.isActive = false;
                    document.getElementById('vocabulary-card-display').classList.add('hidden');
                    document.getElementById('vocab-define-section').classList.add('hidden');
                    document.getElementById('vocabulary-answers').classList.add('hidden');

                    // Check for next layer automatically
                    await checkVocabularySession();
                } else {
                    alert('Error answering card: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error answering vocabulary card:', error);
                alert('Error answering vocabulary card: ' + error.message);
            }
        }

        async function completeLayer() {
            try {
                // Close the custom study session
                if (vocabularySession.currentCustomDeckId) {
                    await fetch('/api/close-custom-study-session', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            deck_id: vocabularySession.currentCustomDeckId,
                            username: currentUser
                        })
                    });
                }

                // Reset vocabulary session state
                vocabularySession.active = false;
                vocabularySession.currentLayer = null;
                vocabularySession.currentCustomDeckId = null;
                vocabularySession.currentCard = null;

                // Update UI
                document.getElementById('current-layer-tag').textContent = 'None';
                document.getElementById('layer-cards-remaining').textContent = '0';
                updateSessionStatus('vocab-status', 'Completed', 'status-waiting');
                document.getElementById('complete-layer-btn').classList.add('hidden');

                // Refresh layers list
                await refreshLayers();

                // Show layer selector again
                document.getElementById('layer-selector').classList.remove('hidden');

                // Auto-select next layer if available (LIFO = most recent first)
                if (vocabularySession.availableLayers.length > 0) {
                    const layerSelect = document.getElementById('layer-select');
                    layerSelect.value = vocabularySession.availableLayers[0].tag;
                    selectLayer();

                    // Optionally auto-start the next layer
                    if (confirm('Start studying the next layer?')) {
                        await startLayerStudy();
                    }
                } else {
                    alert('All vocabulary layers completed!');
                }
            } catch (error) {
                console.error('Error completing layer:', error);
                alert('Error completing layer: ' + error.message);
            }
        }

        async function requestVocabularyDefinitions() {
            const words = document.getElementById('vocab-words-to-define').value.trim();
            if (!words || !vocabularySession.currentCard) {
                alert('Please enter words and ensure a vocabulary card is displayed');
                return;
            }

            try {
                // Generate nested layer tag based on current vocabulary card and current layer
                const currentVocabCard = vocabularySession.currentCard;
                const vocabNoteId = currentVocabCard?.note_id || currentVocabCard?.id || Date.now();
                const currentLayerTag = vocabularySession.currentLayer;
                const nestedLayerTag = `${currentLayerTag}_${vocabNoteId}`;

                // Store nested layer tag in client-side availableLayers immediately
                if (!vocabularySession.availableLayers) {
                    vocabularySession.availableLayers = [];
                }
                if (!vocabularySession.availableLayers.includes(nestedLayerTag)) {
                    vocabularySession.availableLayers.push(nestedLayerTag);
                    console.log(`Generated and stored nested layer tag: ${nestedLayerTag}`);
                    console.log(`Available layers now: ${vocabularySession.availableLayers.join(', ')}`);
                }

                // Close current custom study session before requesting definitions
                if (vocabularySession.currentCustomDeckId) {
                    await fetch('/api/close-custom-study-session', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            deck_id: vocabularySession.currentCustomDeckId,
                            username: currentUser
                        })
                    });
                    console.log('Closed custom study session before nested definition request');
                }

                const response = await fetch('/api/request-vocabulary-definitions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUser,
                        words: words.split(',').map(w => w.trim()),
                        card_context: vocabularySession.currentCard,
                        priority: true,
                        layer_tag: nestedLayerTag  // Pass the generated nested layer tag to Claude Code
                    })
                });

                const result = await response.json();
                if (result.success) {
                    alert('Nested vocabulary definition request sent to Claude SDK. New nested layer will be created.');
                    console.log(`Successfully sent nested vocabulary definition request with layer tag: ${nestedLayerTag}`);
                    console.log('Claude Code will create nested vocabulary cards with this layer tag');

                    // Reset current card and vocabulary session state
                    vocabularySession.currentCard = null;
                    vocabularySession.isActive = false;
                    document.getElementById('vocabulary-card-display').classList.add('hidden');
                    document.getElementById('vocab-define-section').classList.add('hidden');
                    document.getElementById('vocabulary-answers').classList.add('hidden');

                    // No need to refresh layers since we already stored the nested layer tag client-side
                    // The vocabulary session will automatically detect the new nested layer when polling
                } else {
                    alert('Error requesting vocabulary definitions: ' + result.error);
                }
            } catch (error) {
                console.error('Error requesting vocabulary definitions:', error);
                alert('Error requesting vocabulary definitions: ' + error.message);
            }
        }

        // ===== OLD QUEUE-BASED FUNCTIONS (TO BE REMOVED) =====
        async function submitVocabularySession() {
            console.warn('submitVocabularySession is deprecated - using layer-based system');
            alert('This function is deprecated. Please use the layer-based study system.');
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
        grammar_deck_id = data.get("grammar_deck_id")
        vocabulary_deck_id = data.get("vocabulary_deck_id")

        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        current_user = username
        current_deck_id = grammar_deck_id

        # Set vocabulary deck ID in the integration
        claude_integration.set_vocabulary_deck(vocabulary_deck_id)

        # Start grammar session
        result = await claude_integration.start_grammar_session(grammar_deck_id)

        # Add deck info to result for frontend
        if result.get('success'):
            result['grammar_deck_id'] = grammar_deck_id
            result['vocabulary_deck_id'] = vocabulary_deck_id

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
    """Request vocabulary definitions from Claude SDK using current vocabulary card context"""
    global claude_integration

    try:
        data = await request.json()
        words = data.get("words", [])
        card_context = data.get("card_context", {})
        priority = data.get("priority", True)

        if not claude_integration:
            return JSONResponse({"success": False, "error": "Claude integration not available"})

        # Use the new vocabulary card definition method
        result = await claude_integration.request_vocabulary_card_definitions(
            words=words,
            vocab_card=card_context
        )

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

@app.post("/api/study/counts")
async def get_study_counts_endpoint(request: Request):
    """Get study counts for a specific deck"""
    try:
        data = await request.json()
        username = data.get("username")
        deck_id = data.get("deck_id")

        if not username or deck_id is None:
            return JSONResponse({"error": "username and deck_id are required"}, status_code=400)

        # Call the AnkiApi study counts endpoint directly
        import requests
        response = requests.post("http://localhost:5001/api/study/counts", json={
            "username": username,
            "deck_id": deck_id
        })

        if response.status_code == 200:
            return JSONResponse(response.json())
        else:
            return JSONResponse({"error": f"Failed to get counts: {response.text}"}, status_code=response.status_code)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/login-and-sync")
async def login_and_sync_endpoint(request: Request):
    """Login and sync following db_ops.py protocol"""
    try:
        data = await request.json()
        profile_name = data.get("profile_name")
        username = data.get("username")
        password = data.get("password")
        endpoint = data.get("endpoint")
        upload = data.get("upload", False)

        if not all([profile_name, username, password]):
            return JSONResponse({"error": "profile_name, username, and password are required"}, status_code=400)

        # Follow the same protocol as db_ops.py
        from AnkiClient.src.operations import user_ops, db_ops

        # Sanitize endpoint like in db_ops.py
        endpoint_arg = endpoint or None
        if endpoint_arg and (
            '/api/' in endpoint_arg or
            'localhost:5001' in endpoint_arg or
            '127.0.0.1:5001' in endpoint_arg or
            endpoint_arg.startswith('http://172.17.')
        ):
            endpoint_arg = None

        # Perform login
        login_result = user_ops.sync_user_login(
            profile_name=profile_name,
            username=username,
            password=password,
            endpoint=endpoint_arg,
            upload=upload,
            sync_media=False,
        )

        if not isinstance(login_result, dict):
            return JSONResponse({"error": "Login failed", "details": str(login_result)}, status_code=500)

        if 'error' in login_result:
            return JSONResponse({"error": "Login failed", "details": login_result['error']}, status_code=500)

        # Get hkey and endpoint from login
        hkey = login_result.get('hkey')
        endpoint_from_login = login_result.get('endpoint')

        # If login handled a full sync, skip separate DB sync
        if login_result.get('full_sync'):
            return JSONResponse({
                "success": True,
                "login_result": login_result,
                "full_sync_handled": True,
                "message": "Full sync handled during login"
            })
        else:
            # Proceed with DB sync
            endpoint_for_sync = endpoint_from_login or endpoint_arg
            try:
                sync_result = db_ops.sync_db(profile_name, hkey, endpoint_for_sync, upload=upload)
                return JSONResponse({
                    "success": True,
                    "login_result": login_result,
                    "sync_result": sync_result,
                    "message": "Login and sync completed successfully"
                })
            except Exception as sync_error:
                return JSONResponse({
                    "success": True,  # Login succeeded
                    "login_result": login_result,
                    "sync_error": str(sync_error),
                    "message": "Login succeeded but sync failed"
                })

    except Exception as e:
        logger.error(f"Error in login_and_sync: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

# Health check endpoint for CLI
@app.get("/api/health")
async def health_check():
    """Health check endpoint for CLI to verify server is running"""
    return JSONResponse({
        "status": "ok",
        "version": "1.0.0",
        "service": "ankichat-api"
    })

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

# LIFO Layer System - No active-layers endpoint needed
# Web app directly opens vocab study session for custom study deck when created

@app.post("/api/cards-by-tag-and-state")
async def get_cards_by_tag_and_state_endpoint(request: Dict[str, Any]):
    """Get vocabulary cards by tag and state for LIFO layer processing"""
    try:
        deck_id = request.get('deck_id')
        username = request.get('username')
        tag = request.get('tag')
        tag_prefix = request.get('tag_prefix')  # New parameter for prefix matching
        state = request.get('state', 'new')
        include_fields = request.get('include_fields', True)

        if not deck_id or not username:
            return JSONResponse({"error": "deck_id and username are required"}, status_code=400)

        if not tag and not tag_prefix:
            return JSONResponse({"error": "tag or tag_prefix is required"}, status_code=400)

        inclusions = ['id', 'tags', 'note_id'] if include_fields else ['id']
        all_cards = []

        if tag:
            # Get cards for specific tag
            cards_response = card_ops.get_cards_by_tag_and_state(
                tag=tag,
                state=state,
                username=username,
                inclusions=inclusions
            )
            if cards_response and 'cards' in cards_response:
                all_cards.extend(cards_response['cards'])

        elif tag_prefix:
            # For prefix matching, we need to get cards and then filter by prefix
            # Since get_cards_by_tag_and_state needs exact tag, we'll get all cards by state
            # and then filter for the prefix
            cards_response = card_ops.get_cards_by_state(
                deck_id=deck_id,
                state=state,
                username=username,
                inclusions=inclusions
            )

            if cards_response and 'cards' in cards_response:
                # Filter by tag prefix
                for card in cards_response['cards']:
                    tags = card.get('tags', [])
                    for card_tag in tags:
                        if card_tag.startswith(tag_prefix):
                            all_cards.append(card)
                            break  # Only add card once

        return JSONResponse({
            "success": True,
            "cards": all_cards,
            "count": len(all_cards)
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/create-custom-study-session")
async def create_custom_study_session(request: Dict[str, Any]):
    """Create custom study session for a specific layer"""
    try:
        deck_id = request.get('deck_id')
        username = request.get('username')
        tag = request.get('tag')
        card_limit = request.get('card_limit', 100)

        if not deck_id or not username or not tag:
            return JSONResponse({"error": "deck_id, username, and tag are required"}, status_code=400)

        # Create custom study parameters for the layer
        custom_study_params = {
            "new_limit_delta": card_limit,
            "cram": {
                "kind": "CRAM_KIND_DUE",
                "card_limit": card_limit,
                "tags_to_include": [tag],
                "tags_to_exclude": []
            }
        }

        # Create the custom study session
        result_data, status_code = create_custom_study_session(deck_id=deck_id, username=username, custom_study_params=custom_study_params)

        if status_code == 200:
            result = {'success': True, 'created_deck_id': result_data.get('created_deck_id')}
        else:
            result = {'success': False, 'error': str(result_data)}

        if result.get('success'):
            return JSONResponse({
                "success": True,
                "session_deck_id": result.get('created_deck_id', deck_id),
                "message": f"Created custom study session for layer {tag}"
            })
        else:
            return JSONResponse({"error": result.get('error', 'Failed to create custom study session')}, status_code=500)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/study-custom-session")
async def study_custom_session(request: Dict[str, Any]):
    """Study cards in custom session (start, flip, answer)"""
    try:
        deck_id = request.get('deck_id')
        username = request.get('username')
        action = request.get('action')

        if not deck_id or not username or not action:
            return JSONResponse({"error": "deck_id, username, and action are required"}, status_code=400)

        # Use the existing study endpoint with custom parameters
        if action == 'start':
            # Start studying cards in the custom session
            cards = get_cards_in_deck(deck_id=deck_id, username=username)
            if cards:
                # Get first new card
                for card in cards:
                    if card.get('state') == 'new':
                        return JSONResponse({
                            "success": True,
                            "current_card": card,
                            "message": "Started custom study session"
                        })

            return JSONResponse({
                "success": True,
                "current_card": None,
                "message": "No cards available in this layer"
            })

        elif action.startswith('answer_'):
            # Answer the current card
            answer = int(action.split('_')[1])  # Extract answer number (1-4)
            # This would need to be implemented with proper card tracking
            return JSONResponse({
                "success": True,
                "message": f"Card answered with {answer}"
            })

        elif action == 'next':
            # Get next card (simplified implementation)
            cards = get_cards_in_deck(deck_id=deck_id, username=username)
            return JSONResponse({
                "success": True,
                "current_card": cards[0] if cards else None,
                "message": "Got next card"
            })

        else:
            return JSONResponse({"error": f"Unknown action: {action}"}, status_code=400)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/close-custom-study-session")
async def close_custom_study_session(request: Dict[str, Any]):
    """Close custom study session"""
    try:
        deck_id = request.get('deck_id')
        username = request.get('username')

        if not deck_id or not username:
            return JSONResponse({"error": "deck_id and username are required"}, status_code=400)

        # For now, just return success - the actual session cleanup would need proper implementation
        return JSONResponse({
            "success": True,
            "message": "Custom study session closed"
        })

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
