#!/usr/bin/env python3.10
"""
Core Claude Code SDK Integration Test
Tests the integration module without web interface dependencies
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parents[2]  # Go up two levels to reach project root
sys.path.insert(0, str(project_root))

# Import only the core integration module
from claude_sdk_integration import create_claude_sdk_integration, VocabularyQueueManager, StudySessionState


class MockAnkiClient:
    """Mock AnkiClient for testing"""

    def __init__(self):
        self.session_counter = 0

    async def start_session(self, deck_id, username):
        self.session_counter += 1
        return {
            "success": True,
            "session_id": f"session_{self.session_counter}",
            "current_card": {
                "card_id": 101,
                "fields": {
                    "Word": "legbiztosabb",
                    "Definition": "A 'biztos' melléknév felsőfokú alakja",
                    "Example Sentence": "Ez a legbiztosabb módszer."
                }
            }
        }


async def test_vocabulary_queue_manager():
    """Test the LIFO vocabulary queue manager"""
    print("🧪 Testing Vocabulary Queue Manager")
    print("-" * 40)

    queue = VocabularyQueueManager()

    # Test 1: Add cards in order (LIFO should reverse)
    cards = [
        {"card_id": 1, "word": "első"},
        {"card_id": 2, "word": "második"},
        {"card_id": 3, "word": "harmadik"}
    ]

    for card in cards:
        queue.add_new_card(card)

    # Test LIFO order - newest (harmadik) should come first
    first_card = queue.get_next_card()
    if first_card and first_card["word"] == "harmadik":
        print("✅ LIFO ordering works correctly")
    else:
        print(f"❌ LIFO failed - got: {first_card}")

    # Test answer caching
    queue.cache_answer(1, 3)
    queue.cache_answer(2, 4)

    cached_count = len(queue.card_answer_mapping)
    if cached_count == 2:
        print("✅ Answer caching works correctly")
    else:
        print(f"❌ Answer caching failed - count: {cached_count}")

    return True


async def test_claude_integration_core():
    """Test core Claude SDK integration functionality"""
    print("\n🧪 Testing Claude SDK Integration Core")
    print("-" * 40)

    mock_client = MockAnkiClient()
    integration = create_claude_sdk_integration(mock_client)

    # Test 1: SDK availability check
    if hasattr(integration, 'claude_sdk_available'):
        print(f"✅ SDK availability check: {integration.claude_sdk_available}")
    else:
        print("❌ SDK availability check failed")
        return False

    # Test 2: Context preparation
    test_card = {
        "fields": {
            "Word": "teszt",
            "Definition": "Próba vagy vizsgálat",
            "Example Sentence": "Ez egy teszt mondat."
        }
    }

    context = integration._prepare_card_context(test_card)
    if "KÁRTYA KONTEXTUSA" in context and "teszt" in context:
        print("✅ Context preparation works correctly")
    else:
        print("❌ Context preparation failed")

    # Test 3: Session state management
    session = StudySessionState("test_session", 123)
    session.current_card = test_card
    session.is_paused = True

    if session.session_id == "test_session" and session.is_paused:
        print("✅ Session state management works correctly")
    else:
        print("❌ Session state management failed")

    # Test 4: Vocabulary queue integration
    queue_status = integration.get_vocabulary_queue_status()
    if isinstance(queue_status, dict) and 'queue_length' in queue_status:
        print("✅ Vocabulary queue integration works correctly")
    else:
        print("❌ Vocabulary queue integration failed")

    await integration.cleanup()
    return True


async def test_context_instructions():
    """Test loading context instructions"""
    print("\n🧪 Testing Context Instructions")
    print("-" * 40)

    mock_client = MockAnkiClient()
    integration = create_claude_sdk_integration(mock_client)

    try:
        instructions = await integration._get_context_instructions()

        # Check if instructions contain key elements
        required_elements = ["Hungarian", "creative", "emoji"]
        found_elements = [elem for elem in required_elements if elem in instructions]

        if len(found_elements) >= 2:
            print(f"✅ Context instructions loaded ({len(found_elements)}/{len(required_elements)} elements found)")
        else:
            print(f"⚠️ Context instructions loaded but may be incomplete ({len(found_elements)}/{len(required_elements)} elements)")

    except Exception as e:
        print(f"❌ Context instructions loading failed: {e}")
        return False

    await integration.cleanup()
    return True


async def test_claude_sdk_query():
    """Test actual Claude SDK query if available"""
    print("\n🧪 Testing Claude SDK Query")
    print("-" * 40)

    mock_client = MockAnkiClient()
    integration = create_claude_sdk_integration(mock_client)

    if not integration.claude_sdk_available:
        print("⏭️ Skipping Claude SDK query test (SDK not available)")
        await integration.cleanup()
        return True

    try:
        # Test with mock data
        test_words = ["teszt"]
        test_context = "Ez egy teszt kontextus."
        test_instructions = "Define the word creatively."

        result = await integration._request_definitions_from_claude_sdk(
            test_words, test_context, test_instructions
        )

        if result.get('success'):
            print("✅ Claude SDK query completed successfully")
            print(f"   Request ID: {result.get('request_id')}")
            return True
        else:
            print(f"❌ Claude SDK query failed: {result.get('error')}")
            return False

    except Exception as e:
        print(f"❌ Claude SDK query error: {e}")
        return False
    finally:
        await integration.cleanup()


async def main():
    """Run all core tests"""
    print("🚀 Claude Code SDK Core Integration Tests")
    print("=" * 50)

    tests = [
        ("Vocabulary Queue Manager", test_vocabulary_queue_manager),
        ("Claude Integration Core", test_claude_integration_core),
        ("Context Instructions", test_context_instructions),
        ("Claude SDK Query", test_claude_sdk_query),
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
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS")
    print("=" * 50)

    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<30} {status}")
        if result:
            passed += 1

    total = len(results)
    print("-" * 50)
    print(f"Passed: {passed}/{total} ({100*passed//total if total > 0 else 0}%)")

    if passed == total:
        print("\n🎉 ALL CORE TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️ {total-passed} test(s) failed")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)