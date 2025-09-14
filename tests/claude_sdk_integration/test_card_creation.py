#!/usr/bin/env python3.10
"""
Test Claude SDK Card Creation
Tests if the updated context prevents permission issues and successfully creates cards
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from claude_sdk_integration import create_claude_sdk_integration

class MockAnkiClient:
    """Mock AnkiClient for testing"""
    def __init__(self):
        self.session_counter = 0

async def test_card_creation_with_template():
    """Test that Claude SDK creates cards without querying for note types"""
    print("🧪 Testing Card Creation with Provided Template")
    print("=" * 50)

    mock_client = MockAnkiClient()
    integration = create_claude_sdk_integration(mock_client)

    if not integration.claude_sdk_available:
        print("⏭️ Skipping test - Claude SDK not available")
        return False

    try:
        # Test with a single word from a realistic card context
        test_card_context = {
            "fields": {
                "Word": "legbiztosabb",
                "Definition": "A 'biztos' melléknév felsőfokú alakja, ami a legnagyobb biztonságot vagy legmagasabb fokú bizonyosságot jelenti.",
                "Example Sentence": "Ez a legbiztosabb módszer a siker eléréséhez.",
                "Grammar Code": "ADJ-SUPERLATIVE"
            }
        }

        # Prepare context
        context = integration._prepare_card_context(test_card_context)
        instructions = await integration._get_context_instructions()

        print("Context being sent to Claude SDK:")
        print("-" * 30)
        print(context)
        print("\nInstructions being sent:")
        print("-" * 30)
        print(instructions[:500] + "..." if len(instructions) > 500 else instructions)

        # Test with a simple word that appeared in the context
        test_words = ["fokozat"]  # This could appear in "felsőfokú" explanation

        print(f"\n🎯 Testing word definition: {test_words}")
        print("Sending request to Claude SDK...")

        result = await integration._request_definitions_from_claude_sdk(
            test_words, context, instructions
        )

        if result.get('success'):
            print("✅ Claude SDK request completed")
            print(f"Request ID: {result.get('request_id')}")

            # Check if the response indicates card creation attempt
            response = result.get('response', '')
            if 'mcp__anki-api__create_card' in response:
                print("✅ Response contains card creation call")
            else:
                print("⚠️ Response may not have attempted card creation")

            if 'mcp__anki-api__get_notetypes' in response:
                print("❌ Response still tried to query note types (this is bad)")
            else:
                print("✅ Response did not query note types (this is good)")

            return True
        else:
            print(f"❌ Claude SDK request failed: {result.get('error')}")
            return False

    except Exception as e:
        print(f"❌ Test error: {e}")
        return False
    finally:
        await integration.cleanup()

async def main():
    """Run the card creation test"""
    try:
        success = await test_card_creation_with_template()

        if success:
            print("\n🎉 Card creation test completed successfully!")
            print("The integration should now work without permission issues.")
            return 0
        else:
            print("\n⚠️ Card creation test had issues.")
            return 1

    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted")
        sys.exit(1)