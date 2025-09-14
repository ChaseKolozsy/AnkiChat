# Claude Code SDK Integration Tests

This directory contains comprehensive tests for the Claude Code SDK integration with AnkiChat.

## Test Files

### Core Integration Tests

**`test_claude_sdk_core.py`** - Main integration test suite
- ✅ Vocabulary Queue Manager (LIFO ordering)
- ✅ Claude Integration Core (session management)
- ✅ Context Instructions (define-with-context patterns)
- ✅ Claude SDK Query (full integration)

**`test_claude_sdk.py`** - Basic Claude SDK connection test
- Tests SDK availability and basic query functionality
- Verifies API key configuration and connection

### Feature-Specific Tests

**`test_card_creation.py`** - Card creation without permission issues
- Tests card template integration
- Verifies study session closure before card creation
- Validates proper deck and note type usage

**`test_subagent_functionality.py`** - Parallel subagent testing
- Tests creative-definer subagent usage for multiple words
- Verifies parallel processing vs sequential processing
- Validates subagent Task tool usage

**`test_enhanced_integration.py`** - Complete workflow testing (requires web dependencies)
- Full dual-session workflow simulation
- Web interface compatibility testing
- End-to-end integration validation

## Test Requirements

### Environment Setup
```bash
# Create and activate Python 3.10+ virtual environment
uv venv --python 3.10 .venv_claude_sdk
source .venv_claude_sdk/bin/activate

# Install dependencies
uv pip install claude-code-sdk fastapi uvicorn typer requests
```

### Environment Variables
- `ANTHROPIC_API_KEY` - Required for Claude SDK integration
- Must be authenticated with Anthropic Pro account

## Running Tests

### Quick Core Test
```bash
source .venv_claude_sdk/bin/activate
python tests/claude_sdk_integration/test_claude_sdk_core.py
```

### Full Test Suite
```bash
# Run each test individually
python tests/claude_sdk_integration/test_claude_sdk.py
python tests/claude_sdk_integration/test_card_creation.py
python tests/claude_sdk_integration/test_subagent_functionality.py
```

### Test Dependencies
- AnkiAPI server running (for MCP tools)
- Claude Code SDK available in environment
- Proper Anki deck structure (Hungarian Vocabulary Note template)

## Test Results

All tests should pass with the following expected outcomes:

- **Core Integration**: 4/4 tests passing (100%)
- **Card Creation**: Cards successfully created in deck 1756509006667
- **Subagent Usage**: Parallel creative-definer agents for multiple words
- **Session Management**: Proper study session lifecycle handling

## Integration Architecture

The tests verify the complete Claude Code SDK integration:

1. **Dual Study Sessions** - Grammar (main) + Vocabulary (LIFO secondary)
2. **Context-Aware Definitions** - Using active card context
3. **Parallel Subagents** - Multiple word definitions via Task agents
4. **Session Management** - Close before Claude, restart after answers
5. **Answer Caching** - Seamless user experience during processing

## Troubleshooting

### Common Issues

**Permission Errors**: Ensure Claude Code SDK has access to MCP tools
**Card Creation Failures**: Verify deck 1756509006667 exists and note type is available
**SDK Not Available**: Check Python 3.10+ and claude-code-sdk installation
**Context Loading Errors**: Verify `.claude/commands/define-with-context.md` exists

### Debug Mode
Set logging level for detailed output:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```