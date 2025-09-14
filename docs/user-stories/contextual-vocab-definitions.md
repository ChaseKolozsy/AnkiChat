# User Story: Contextual Vocab Definitions via Claude Code + Anki

## Summary
- As a learner reviewing a grammar card, I can select unknown words and submit them to an AI agent (Claude Code SDK) to get creative, Hungarian-only definitions that become new Anki vocabulary cards.
- The current study session must be safely paused/closed. The active card is cached immediately. If I haven’t answered yet, I can still select an answer (again/hard/good/easy) after the session is closed; that answer is cached and later auto-submitted when the card reappears.
- The web app polls the Anki API (via MCP-connected Anki Desktop) for newly created cards in the active/default deck and shows them in a separate “Vocab Review” container with controls to: mark as understood, request more definitions, and start an auto study pass.
- Vocab requests follow a LIFO stack so newly requested prerequisite words are handled first.

## Goals
- Provide clear, context-aware vocabulary definitions for words encountered during grammar study.
- Avoid conflicts with Anki by closing the active study session before new notes/cards are created.
- Maintain learner flow: cache the current card and answer, then resume and auto-submit when that card reappears.
- Show newly created vocab cards in a dedicated area with simple actions.
- Process follow-up vocab requests with strict LIFO priority.
- Support an automated study pass that: submits mapped answers and migrates cards to a dedicated “Hungarian Vocab” deck to keep the default deck clean.

## High-Level Flow
1. While studying a grammar card, the learner selects multiple unknown words and clicks “Define with context”.
2. The web app immediately:
   - Closes/pauses the current Anki study session.
   - Caches the active card’s ID in a map: `{ [cardId]: rating }`.
   - If the learner hasn’t answered yet, display a lightweight rating control (again/hard/good/easy) that remains active after session closure; once chosen, persist the rating for the cached card.
   - Captures the full card content/context (entire grammar card: CLE/definition/examples) as text.
3. The app sends a single Claude Code SDK request that:
   - Embeds the full instructions from `.claude/commands/define-with-context.md` in the request (not just a reference), honoring Hungarian-only context and parallel subagents. The selected words are injected as `$ARGUMENTS` (comma-separated), if supported.
   - Provides: selected words (possibly multiple) + the entire source grammar card content as context (no summaries; Hungarian-only where the command requires it).
   - Explicitly instructs the agent to create Anki cards via the MCP Anki API (note type, deck, fields, tags), and to return full creative definitions and card/note IDs.
4. The web app begins polling the Anki API for new cards created in the target deck (default/active).
5. As new vocab cards appear, they are displayed in a “Vocab Review” container showing full content (word, definition, example, IDs).
6. For each vocab card, the learner can:
   - “Understood/Studied”: map that card ID to a ‘good’ (3) rating for the upcoming auto-study pass.
   - “Request additional definitions”: choose words in that card’s content; send the full vocab card content + those words to Claude, embedding the `.claude/commands/define-with-context.md` instructions with the words injected as `$ARGUMENTS`. This request is pushed on top of the LIFO vocab stack.
7. After the learner processes all vocab cards (stack empty or as desired), they click “Start Auto Study”. The app:
   - Starts a study session in the default deck (where cards were created).
   - For each card in the mapped set, flips and submits the mapped rating (default 3 for Understood/Studied).
   - Moves those cards to the “Hungarian Vocab” deck (keeping the default deck clean for the next batch).
8. When the grammar study resumes:
   - If the next shown card matches a cached card ID, the app immediately flips and submits the cached answer without user friction and removes it from the cache, then proceeds to the next queued card.
   - If the newly created vocab card matches the previously visible card, it is auto-answered as above and skipped from the UI (not re-shown).

## Key Behaviors & Rules
- Session safety: Close/terminate the active study session before initiating Anki card creation (to prevent add failures and session corruption).
- Caching: Maintain `{ cardId -> rating }` for both the active grammar card and any cards marked “Understood/Studied”. If the grammar card’s rating wasn’t selected before session closure, accept and persist the rating afterward via a lightweight control.
- LIFO vocab stack: New “request more definitions” actions always push to the top; these are prerequisites and should be shown/processed first.
- Polling: Web app polls the Anki API (via MCP server) for newly created cards in the target deck and updates the UI.
- Auto-answer on resume: When encountering a cached card ID in the resumed session, auto-flip and auto-submit the cached rating immediately.
- Deck hygiene: After auto-study, move vocab cards from the default deck to the “Hungarian Vocab” deck.

## Claude Code SDK Integration
- Command: `.claude/commands/define-with-context.md`.
- Requirements to include in request:
  - Embed the full instruction text from the command file into the request payload (do not rely solely on an external reference). Inject the selected words into the `$ARGUMENTS` placeholder if supported.
  - Multiple words at once; require parallel subagents (single message with multiple tool invocations) per instruction file.
  - Provide the entire source card content as context (grammar card or vocab card) and ensure Hungarian-only context descriptions per the command.
  - Include relevant study instructions (e.g., `StudyTypes/AnkiStudyOfGrammar/instructions.md` Role 2) and Pimsleur Level 1 constraints.
  - Explicit Anki card creation via MCP tool with required fields, note type, deck, tags; return full creative definitions + note/card IDs.
- Results handling:
  - Display complete creative definitions (no summaries), example sentences, and IDs in the UI.

## Acceptance Criteria
- Submitting words closes the current Anki study session and caches the active card ID. If no answer has been given yet, the UI allows selecting again/hard/good/easy after session closure and persists this rating for the cached card.
- The Claude request contains: the selected words, the entire source card content (grammar or vocab), the embedded instructions from `.claude/commands/define-with-context.md` with words supplied as `$ARGUMENTS` where possible, and explicit MCP Anki creation instructions.
- The UI polls and shows new vocab cards in a dedicated container with full definitions and IDs.
- “Understood/Studied” maps that vocab card’s ID to rating 3 in the cache.
- “Request additional definitions” sends the full vocab card content + selected words to Claude, embedding the instruction text, and pushes the request onto the top of the LIFO stack.
- “Start Auto Study” starts a session in the default deck, auto-flips and submits cached ratings for mapped card IDs, and moves those cards to the “Hungarian Vocab” deck.
- When resuming grammar study, any cached card that appears is immediately auto-answered and removed from the cache; if it’s the same card as just shown, it can be skipped from display.

## Open Questions
- Exact deck IDs and note type names in each environment (configurable?).
- Polling interval/backoff and how we detect completion of agent-created cards.
- UX for selecting words in a grammar card and in a vocab card (multi-select, highlighting, etc.).
- Persistence of cached ratings across reloads (local/session storage vs. backend). Ensure late-answer capture survives reloads if possible.
- Error handling: failed card creation, MCP connectivity issues, or conflicts when resuming study sessions.

## Branch Proposal
- Suggested branch name: `feature/ai-context-vocab-stack`
