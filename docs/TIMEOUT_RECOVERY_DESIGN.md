# Timeout and Recovery System Design

## Problem Statement

The AnkiChat CLI and Web App experienced pernicious bugs where:

1. **Vocabulary card polling hangs indefinitely** when Claude SDK creates cards slowly or fails
2. **Grammar session recovery hangs** when switching back from vocabulary mode
3. **No user control** - users couldn't retry or recover from hung states
4. **Screen sleep/suspension** could cause polling to hang permanently

These issues occurred because the polling loops had no timeout mechanism and no way to detect whether cards were actually created.

## Solution Overview

Implemented a comprehensive timeout and retry system with three key components:

### 1. Polling Manager (`cli/polling_manager.py`)

A robust polling infrastructure that provides:

- **Configurable timeouts** (default: 60 seconds)
- **Baseline card tracking** - records existing cards before polling
- **New card detection** - compares current deck state to baseline
- **Manual retry capability** - allows users to retry after timeout (up to 3 attempts)
- **Progress tracking** - shows elapsed time, poll count, and remaining time

#### Key Classes:

**`PollConfig`**: Configuration for polling behavior
- `timeout_seconds`: Total polling timeout (default: 60s)
- `poll_interval_seconds`: Time between checks (default: 2s)
- `max_retries`: Maximum manual retry attempts (default: 3)

**`PollState`**: Tracks polling session state
- Start time, poll count, retry count
- Timeout and completion flags
- Baseline card IDs and detected new IDs

**`PollingManager`**: Main polling orchestration
- `record_baseline()`: Capture current deck state
- `check_for_new_cards()`: Compare current state to baseline
- `should_continue_polling()`: Check timeout and completion
- `retry()`: Reset state for manual retry attempt
- `can_retry()`: Validate retry availability

**`VocabularyCardDetector`**: Card detection utility
- `get_current_cards()`: Fetch current deck snapshot
- `detect_new_cards()`: Find cards not in baseline
- Works independently of polling loop for manual checks

### 2. CLI Session Updates (`cli/session.py`)

#### Vocabulary Card Detection with Timeout

**`_poll_for_new_vocabulary_cards()`**:
- Initializes polling manager with 60-second timeout
- Records baseline card IDs from vocabulary deck
- Polls every 2 seconds for new cards
- Returns `'found'`, `'timeout'`, or `'error'`
- Shows real-time progress: "Checking... 12.5s / 6 checks (timeout in 47.5s)"

**`_retry_vocabulary_poll()`**:
- Allows up to 3 manual retry attempts
- Validates retry eligibility
- Re-polls with fresh timeout window
- Returns true if cards found

**Updated `_define_vocabulary_words()`**:
- Uses polling manager instead of fixed 2-second sleep
- Shows timeout message with retry instructions
- Supports 'r' command to retry after timeout
- Displays polling status during wait

#### Vocabulary Mode Retry Command

Added 'r' command handler in `_handle_vocabulary_action()`:
- Triggers manual retry of vocabulary card detection
- Loads new cards from queue if found
- Provides feedback on retry success/failure
- Updated help text to include retry instructions

#### Grammar Session Recovery with Timeout

**`_recover_grammar_session()`**:
- Uses SIGALRM signal for 30-second timeout
- Attempts to close existing sessions
- Starts fresh grammar session
- Returns `'success'`, `'timeout'`, or `'error'`
- Gracefully handles timeout with user feedback

**Updated `_switch_to_grammar()`**:
- Calls recovery with timeout protection
- Shows clear timeout messages
- Suggests 'retry-grammar' command on timeout

**Grammar Mode Retry Command**:
- Added 'retry-grammar' command in `_handle_action()`
- Manually retriggers session recovery
- Provides feedback on recovery outcome

### 3. Web App Timeout Handling (`web_app/enhanced_main.py`)

#### JavaScript Polling with Timeout

**Updated `startVocabularyPolling()`**:
- Tracks poll start time and elapsed time
- 60-second timeout for card detection
- Automatically stops polling and shows timeout message
- Creates dynamic "Retry Poll" button on timeout
- Resets timeout when cards are successfully found

**`showRetryPollButton()`**:
- Dynamically creates or shows retry button
- Positioned near vocabulary status display
- Clear visual indication of timeout state

**`retryVocabularyPolling()`**:
- Clears old polling interval
- Resets timeout tracking
- Restarts polling with fresh timeout window
- Updates UI status during retry

## Usage Examples

### CLI - Vocabulary Card Timeout

```
User defines words in vocabulary mode:
> d
Enter words: szó, ház

🤖 Requesting definitions...
[Polling starts]
Checking... 15.2s / 7 checks (timeout in 44.8s)
...
⏱️ Timeout after 60.0s

⏱️  Polling timed out waiting for new vocabulary cards.
The cards may still be created in the background.
Press 'r' to retry checking for new cards.

[User presses 'r']
> r
🔄 Retrying vocabulary card detection... (Retry 1/3 available)
Baseline: 245 cards in vocabulary deck
Checking... 3.1s / 1 checks (timeout in 56.9s)
✅ Detected 2 new card(s)!
✅ New vocabulary card ready (top of stack)!
```

### CLI - Grammar Session Recovery Timeout

```
User switches back to grammar mode after device sleep:
> g

📚 Grammar Mode

Closing existing sessions...
✓ Closed existing sessions
Starting fresh grammar session for deck: Hungarian Grammar (ID: 2)
[Hangs...]

⏱️  Session recovery timed out.
The session may be in an inconsistent state.
Type 'retry-grammar' to try again.

[User types retry command]
> retry-grammar
🔄 Retrying grammar session recovery...
Closing existing sessions...
✓ Closed existing sessions
Starting fresh grammar session...
[Shows card]
✅ Grammar session recovered successfully
```

### Web App - Polling Timeout

```
Web interface polling for vocabulary cards:

[After 60 seconds with no cards]
Vocabulary Status: ⏱️ Polling timed out. Click "Retry Poll" to check again.
[Retry Poll] button appears

[User clicks "Retry Poll"]
Vocabulary Status: 🔄 Retrying poll...
[Polling restarts with fresh 60-second timeout]
```

## Architecture Benefits

### 1. **Robustness**
- No infinite hangs - all operations timeout
- Graceful degradation when services are slow
- Clear error states and recovery paths

### 2. **User Control**
- Manual retry capability after timeout
- Multiple retry attempts allowed (configurable)
- Clear feedback on timeout and retry status

### 3. **Card Existence Checking**
- Baseline comparison ensures accuracy
- Detects cards created during timeout
- Avoids false negatives from slow creation

### 4. **Session Recovery**
- Grammar mode can recover from hung states
- Fresh session start on recovery
- Signal-based timeout for API calls

### 5. **Testability**
- Polling logic isolated in dedicated module
- Configurable timeout and retry parameters
- State tracking for debugging

## Configuration

### CLI Polling Configuration

```python
# Default configuration
poll_config = PollConfig(
    timeout_seconds=60,      # Total timeout
    poll_interval_seconds=2.0,  # Check every 2 seconds
    max_retries=3            # Allow 3 manual retries
)

# Can be customized per use case
quick_poll = PollConfig(timeout_seconds=30, poll_interval_seconds=1.0)
patient_poll = PollConfig(timeout_seconds=120, poll_interval_seconds=5.0)
```

### Web App Polling Configuration

```javascript
// In startVocabularyPolling()
let pollTimeout = 60000; // 60 seconds (configurable)
let pollInterval = 3000; // 3 seconds between checks
```

### Grammar Session Recovery

```python
# In _recover_grammar_session()
timeout_seconds = 30  # Can be adjusted as parameter
```

## Future Enhancements

1. **Adaptive Timeout**: Adjust timeout based on historical card creation times
2. **Exponential Backoff**: Increase poll interval if no cards detected
3. **Background Polling**: Continue polling in background after timeout
4. **Persistent State**: Save polling state across CLI restarts
5. **Metrics Tracking**: Log timeout frequency for analysis
6. **User Notifications**: Desktop notifications when cards are ready

## Files Modified

### Created:
- `cli/polling_manager.py` - Polling infrastructure

### Modified:
- `cli/session.py` - CLI session with timeout handling
- `web_app/enhanced_main.py` - Web app polling with timeout

## Testing Recommendations

1. **Timeout Testing**: Simulate slow card creation (> 60s)
2. **Retry Testing**: Verify retry logic after timeout
3. **Baseline Testing**: Ensure existing cards aren't treated as new
4. **Session Recovery**: Test grammar mode recovery after various hang states
5. **Device Sleep**: Test behavior when device suspends during polling
6. **Edge Cases**: Empty decks, API failures, network issues

## Summary

This implementation solves the hanging issues by:
1. **Adding timeouts** to all polling operations (60s default)
2. **Enabling manual retries** when timeouts occur (up to 3 attempts)
3. **Using card existence checking** via baseline comparison
4. **Providing session recovery** for grammar mode with timeout protection

The system is robust, user-friendly, and provides clear feedback throughout the polling and recovery process.
