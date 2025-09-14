#!/usr/bin/env python3.10
"""
Test Claude SDK Subagent Functionality
Tests if Claude SDK uses parallel subagents for multiple word definitions
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

async def test_parallel_subagents():
    """Test that Claude SDK uses parallel subagents for multiple words"""
    print("🧪 Testing Parallel Subagent Functionality")
    print("=" * 50)

    mock_client = MockAnkiClient()
    integration = create_claude_sdk_integration(mock_client)

    if not integration.claude_sdk_available:
        print("⏭️ Skipping test - Claude SDK not available")
        return False

    try:
        # Test with multiple words that should trigger subagents
        test_card_context = {
            "fields": {
                "Word": "legbiztosabb",
                "Definition": "A 'biztos' melléknév felsőfokú alakja, ami a legnagyobb biztonságot vagy legmagasabb fokú bizonyosságot jelenti. Ez a fokozat segít megérteni a választ.",
                "Example Sentence": "Ez a legbiztosabb módszer a siker eléréséhez, teljes kontrollt biztosít.",
                "Grammar Code": "ADJ-SUPERLATIVE"
            }
        }

        # Prepare context
        context = integration._prepare_card_context(test_card_context)
        instructions = await integration._get_context_instructions()

        # Add specific instruction about parallel subagents
        subagent_instructions = """

**CRITICAL: PARALLEL SUBAGENT USAGE REQUIRED**

When defining multiple words, you MUST:
1. Use the Task tool to launch creative-definer agents IN PARALLEL (single message with multiple Task tool calls)
2. Launch one agent per word in the SAME message
3. Each agent should receive the full context and create one card per word
4. DO NOT process words sequentially - use parallel Task tool invocations

Example: If defining 3 words, send ONE message with THREE Task tool calls together.
"""

        full_instructions = instructions + subagent_instructions

        print("Testing with multiple words to trigger subagent usage...")
        print("Context being sent:")
        print(context[:200] + "...")

        # Test with multiple words that appear in the definition
        test_words = ["fokozat", "választ", "teljes"]  # Words from the card context

        print(f"\n🎯 Testing multiple word definitions: {test_words}")
        print("This should trigger parallel creative-definer subagents...")

        result = await integration._request_definitions_from_claude_sdk(
            test_words, context, full_instructions
        )

        if result.get('success'):
            print("✅ Claude SDK request completed")
            print(f"Request ID: {result.get('request_id')}")

            response = result.get('response', '')

            # Check for subagent usage indicators
            subagent_indicators = [
                'Task',
                'creative-definer',
                'agent',
                'parallel',
                'launch'
            ]

            found_indicators = [indicator for indicator in subagent_indicators if indicator in response]

            if found_indicators:
                print(f"✅ Subagent usage detected: {found_indicators}")
            else:
                print("⚠️ No clear subagent usage detected in response")

            # Check for multiple card creation calls
            card_creation_count = response.count('mcp__anki-api__create_card')
            if card_creation_count >= len(test_words):
                print(f"✅ Multiple card creation calls detected: {card_creation_count}")
            else:
                print(f"⚠️ Expected {len(test_words)} card creations, found {card_creation_count}")

            # Print a sample of the response to analyze
            print(f"\nResponse sample (first 1000 chars):")
            print("-" * 50)
            print(response[:1000])
            if len(response) > 1000:
                print("...(truncated)")

            return True
        else:
            print(f"❌ Claude SDK request failed: {result.get('error')}")
            return False

    except Exception as e:
        print(f"❌ Test error: {e}")
        return False
    finally:
        await integration.cleanup()

async def test_single_word_vs_multiple():
    """Compare single word vs multiple word processing"""
    print("\n🔄 Testing Single Word vs Multiple Word Processing")
    print("=" * 50)

    mock_client = MockAnkiClient()
    integration = create_claude_sdk_integration(mock_client)

    if not integration.claude_sdk_available:
        print("⏭️ Skipping comparison test - Claude SDK not available")
        return False

    try:
        test_card_context = {
            "fields": {
                "Word": "példa",
                "Definition": "Minta vagy szemléltető eset valaminek a bemutatására",
                "Example Sentence": "Ez egy jó példa a helyes használatra."
            }
        }

        context = integration._prepare_card_context(test_card_context)
        instructions = await integration._get_context_instructions()

        # Test 1: Single word
        print("📝 Testing with single word...")
        single_result = await integration._request_definitions_from_claude_sdk(
            ["példa"], context, instructions
        )

        single_response = single_result.get('response', '') if single_result.get('success') else ''
        single_has_task = 'Task' in single_response
        single_card_count = single_response.count('mcp__anki-api__create_card')

        print(f"Single word - Task usage: {single_has_task}, Card creations: {single_card_count}")

        # Test 2: Multiple words
        print("\n📝 Testing with multiple words...")
        multiple_result = await integration._request_definitions_from_claude_sdk(
            ["példa", "minta", "eset"], context, instructions
        )

        multiple_response = multiple_result.get('response', '') if multiple_result.get('success') else ''
        multiple_has_task = 'Task' in multiple_response
        multiple_card_count = multiple_response.count('mcp__anki-api__create_card')

        print(f"Multiple words - Task usage: {multiple_has_task}, Card creations: {multiple_card_count}")

        # Analysis
        print(f"\n🔍 Analysis:")
        print(f"Single word should use direct processing: {'✅' if not single_has_task else '⚠️'}")
        print(f"Multiple words should use Task agents: {'✅' if multiple_has_task else '❌'}")

        return True

    except Exception as e:
        print(f"❌ Comparison test error: {e}")
        return False
    finally:
        await integration.cleanup()

async def main():
    """Run subagent functionality tests"""
    print("🚀 Claude SDK Subagent Functionality Tests")
    print("=" * 60)

    tests = [
        ("Parallel Subagents", test_parallel_subagents),
        ("Single vs Multiple Comparison", test_single_word_vs_multiple),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test error: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 SUBAGENT TEST RESULTS")
    print("=" * 60)

    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<35} {status}")
        if result:
            passed += 1

    total = len(results)
    print("-" * 60)
    print(f"Passed: {passed}/{total} ({100*passed//total if total > 0 else 0}%)")

    if passed == total:
        print("\n🎉 SUBAGENT FUNCTIONALITY VERIFIED!")
        return 0
    else:
        print(f"\n⚠️ {total-passed} test(s) failed - subagent usage may need investigation")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Subagent tests interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)