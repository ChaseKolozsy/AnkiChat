# Web App Layer-Based Vocabulary Refactor Plan

## Overview
Convert web app from queue-based vocabulary system to layer-based custom study sessions (matching CLI implementation).

## Status
- ✅ HTML UI updated to show layers instead of queue
- ✅ Session state variables updated
- ✅ Backend API endpoints already exist
- ⏳ JavaScript functions need replacement
- ⏳ Old queue endpoints need removal

## Changes Made So Far

### 1. HTML/UI Changes (DONE)
**File**: `/home/chase/AnkiChat/web_app/enhanced_main.py`

**Old UI** (lines 471-505):
- Queue length counter
- Cached answers counter
- Single "Studied" button
- "Submit Vocabulary Session" button

**New UI** (lines 471-514):
- Layer selector dropdown
- Active layer count
- Current layer tag display
- Cards remaining counter
- Full answer buttons (1-4: Again/Hard/Good/Easy)
- "Start Layer Study" button
- "Complete Layer & Next" button
- "Define Words" section (creates nested layers)

### 2. JavaScript State Variables (DONE)
**Old**:
```javascript
let vocabularySession = { active: false, queue: [], cachedAnswers: {} };
```

**New**:
```javascript
let vocabularySession = {
    active: false,
    currentLayer: null,
    currentCustomDeckId: null,
    currentCard: null,
    availableLayers: []
};
```

## Required JavaScript Functions (TO DO)

### Functions to ADD:

####  1. `refreshLayers()`
```javascript
async function refreshLayers() {
    // Fetch active layers from /api/active-layers
    // Update vocabularySession.availableLayers
    // Populate layer-select dropdown
    // Update active-layer-count display
}
```

#### 2. `selectLayer()`
```javascript
function selectLayer() {
    // Get selected layer from dropdown
    // Enable/disable "Start Layer Study" button
}
```

#### 3. `startLayerStudy()`
```javascript
async function startLayerStudy() {
    // Get selected layer tag
    // Close any existing vocabulary session
    // Call /api/create-custom-study-session with layer tag
    // Store custom deck ID in vocabularySession.currentCustomDeckId
    // Call startCustomStudySession()
}
```

#### 4. `startCustomStudySession()`
```javascript
async function startCustomStudySession() {
    // Call /api/study-custom-session with action='start'
    // Get first card
    // Display vocabulary card
    // Show answer buttons
    // Update layer status
}
```

#### 5. `answerVocabularyCard(answer)` - REPLACE existing
```javascript
async function answerVocabularyCard(answer) {
    // Use /api/study endpoint with custom deck ID
    // Answer card with ease rating (1-4)
    // Get next card
    // If no more cards, call completeLayer()
}
```

#### 6. `completeLayer()`
```javascript
async function completeLayer() {
    // Close custom study session
    // Remove completed layer from availableLayers
    // Refresh layers list
    // If more layers exist, auto-select next (LIFO = most recent first)
    // Reset vocabulary session state
}
```

#### 7. `requestVocabularyDefinitions()` - UPDATE existing
```javascript
async function requestVocabularyDefinitions() {
    // Keep existing code BUT:
    // After definitions are requested:
    // 1. Close current custom study session
    // 2. Wait for new nested layer to be created
    // 3. Call refreshLayers()
    // 4. Auto-select the new nested layer
    // 5. Auto-start studying the nested layer
}
```

### Functions to REMOVE:

1. `startVocabularyPolling()` - lines 1571-1647
2. `updateVocabularyQueue()` - search and find
3. `getNextVocabularyCard()` - search and find
4. `submitVocabularySession()` - line 1785
5. All queue status update functions
6. All cache-related vocabulary functions

## Backend API Endpoints

### Endpoints Already Implemented (READY TO USE):

#### 1. `/api/active-layers` (line 2360)
```python
POST /api/active-layers
Body: {
    "deck_id": int,
    "username": str
}
Returns: {
    "success": true,
    "layers": [
        {"tag": "layer_12345", "created_at": "..."},
        ...
    ]
}
```

#### 2. `/api/create-custom-study-session` (line 2436)
```python
POST /api/create-custom-study-session
Body: {
    "deck_id": int,
    "username": str,
    "tag": str,  # layer tag
    "card_limit": int  # optional, default 100
}
Returns: {
    "success": true,
    "session_deck_id": int,
    "message": "Created custom study session for layer {tag}"
}
```

#### 3. `/api/study-custom-session` (line 2479)
```python
POST /api/study-custom-session
Body: {
    "deck_id": int,  # custom session deck ID
    "username": str,
    "action": str  # 'start', 'answer_1', 'answer_2', 'answer_3', 'answer_4', 'next'
}
Returns: {
    "success": true,
    "current_card": {...},
    "message": "..."
}
```

**NOTE**: This endpoint needs improvement to properly use the Anki study API instead of just listing cards.

#### 4. `/api/close-custom-study-session` (line 2534)
```python
POST /api/close-custom-study-session
Body: {
    "deck_id": int,  # custom session deck ID
    "username": str
}
Returns: {
    "success": true,
    "message": "Custom study session closed"
}
```

### Endpoints to REMOVE:

1. `/api/cache-vocabulary-answer` - line 2119
2. `/api/vocabulary-queue-status` - line 2139
3. `/api/next-vocabulary-card` - line 2155
4. `/api/requeue-current-vocabulary-card` - line 2171
5. `/api/submit-vocabulary-session` - line 2191

## Backend Improvements Needed

### 1. Improve `/api/study-custom-session`
Current implementation (line 2479) is simplified - it just lists cards. It needs to:
- Use `AnkiClient.src.operations.study_ops.study()` properly
- Maintain study session state
- Handle flip/answer actions correctly
- Track current card properly

**Suggested approach**: Look at how `/api/study` (grammar) works and replicate for custom sessions.

### 2. Improve `/api/request-vocabulary-definitions`
Current implementation (line 1994) needs to:
- Close active custom vocabulary session before requesting definitions
- Wait for nested layer creation
- Return nested layer tag in response

**Add to response**:
```python
{
    "success": true,
    "nested_layer_tag": "layer_12345_67890",
    "previous_layer_tag": "layer_12345"
}
```

## Workflow Comparison

### OLD: Queue-Based Workflow
1. User defines words from grammar card
2. Claude creates vocabulary cards with layer tags
3. **Polling detects new cards**
4. **Cards added to LIFO queue**
5. **User studies from queue (cached answers)**
6. **User submits vocabulary session (auto-answers all cached)**

### NEW: Layer-Based Workflow (like CLI)
1. User defines words from grammar card
2. Claude creates vocabulary cards with layer tags
3. **User clicks "Refresh Layers"**
4. **User selects layer from dropdown**
5. **User clicks "Start Layer Study"**
6. **System creates custom study session for that layer**
7. **User studies cards with immediate answer submission (1-4)**
8. **When layer complete, user clicks "Complete Layer & Next"**
9. **System shows next available layer (LIFO order)**

### Nested Vocabulary Workflow
1. User is studying vocabulary layer A
2. User defines new words from vocabulary card
3. **System closes current custom session**
4. Claude creates nested layer B (tag: `layer_A_noteId`)
5. **System refreshes layers**
6. **New nested layer B appears at top of list (LIFO)**
7. **System auto-selects and auto-starts layer B**
8. User studies nested layer B
9. When done, layer A reappears for continuation

## Testing Checklist

- [ ] Layer selection UI works
- [ ] Custom study session creation works
- [ ] Card display shows vocabulary cards
- [ ] Answer buttons (1-4) work correctly
- [ ] Next card navigation works
- [ ] Layer completion works
- [ ] Nested layer creation works
- [ ] Nested layer auto-selection works
- [ ] LIFO order is maintained (most recent first)
- [ ] Old queue functionality is removed
- [ ] No collection lock conflicts occur

## Migration Notes

1. **Backup created**: `/home/chase/AnkiChat/web_app/enhanced_main.py.queue_backup`
2. **Current state**: Partial - HTML updated, JavaScript needs completion
3. **Risk**: Large refactor - test thoroughly before deploying
4. **Alternative**: Consider creating a new `enhanced_main_v2.py` and switching when ready

## Next Steps

1. Complete JavaScript function implementations
2. Test with actual Anki collection
3. Improve backend custom study session handling
4. Remove old queue-based code
5. Update documentation
6. Deploy and test nested vocabulary workflow

## Related Files

- Web app: `/home/chase/AnkiChat/web_app/enhanced_main.py`
- CLI reference: `/home/chase/AnkiChat/cli/session.py` (lines 426-680)
- Backend integration: `/home/chase/AnkiChat/claude_sdk_integration.py`
- Study operations: `/home/chase/AnkiChat/AnkiClient/src/operations/study_ops.py`
