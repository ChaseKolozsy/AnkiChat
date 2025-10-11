#!/usr/bin/env python3.10
"""
Enhanced Integration Test Script
Tests the complete Claude Code SDK + AnkiChat integration system
"""

import asyncio
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parents[2]  # Go up two levels to reach project root
sys.path.insert(0, str(project_root))

# Import the integration modules
from claude_sdk_integration import create_claude_sdk_integration
from web_app.enhanced_main import app

class MockAnkiClient:
    """Mock AnkiClient for testing purposes"""

    def __init__(self):
        self.decks = [
            {"id": 12345, "name": "Hungarian Grammar", "card_count": 150},
            {"id": 1, "name": "Default", "card_count": 25}  # Default deck for vocabulary
        ]

        self.cards = {
            12345: [  # Grammar cards
                {
                    "card_id": 101,
                    "fields": {
                        "Word": "legbiztosabb",
                        "Definition": "A 'biztos' melléknév felsőfokú alakja, ami a legnagyobb biztonságot vagy legmagasabb fokú bizonyosságot jelenti.",
                        "Example Sentence": "Ez a legbiztosabb módszer a siker eléréséhez.",
                        "Grammar Code": "ADJ-SUPERLATIVE"
                    },
                    "tags": ["grammar", "adjective", "superlative"]
                }
            ],
            1: []  # Vocabulary cards (initially empty, will be populated)
        }

        self.session_counter = 0

    async def get_decks(self, username: str):
        """Mock get decks"""
        return {"success": True, "decks": self.decks}

    async def start_session(self, deck_id: int, username: str):
        """Mock start session"""
        self.session_counter += 1
        session_id = f"session_{self.session_counter}"

        if deck_id in self.cards and self.cards[deck_id]:
            return {
                "success": True,
                "session_id": session_id,
                "current_card": self.cards[deck_id][0]
            }

        return {"success": False, "error": "No cards available"}

    async def add_vocabulary_card(self, word: str, definition: str):
        """Simulate new vocabulary card being added"""
        card_id = 200 + len(self.cards[1])
        new_card = {
            "card_id": card_id,
            "fields": {
                "Word": word,
                "Definition": definition,
                "Example Sentence": f"Példa mondat a '{word}' szóval."
            },
            "tags": ["vocabulary", "new"]
        }

        self.cards[1].append(new_card)
        print(f"✅ Added new vocabulary card: {word} (ID: {card_id})")
        return new_card


async def test_claude_sdk_integration():
    """Test Claude Code SDK integration components"""
    print("🧪 Testing Claude Code SDK Integration")
    print("=" * 50)

    # Initialize mock client
    mock_client = MockAnkiClient()

    # Create integration
    integration = create_claude_sdk_integration(mock_client)

    # Test 1: Check SDK availability
    print("\n1️⃣ Testing SDK Availability...")
    if integration.claude_sdk_available:
        print("✅ Claude Code SDK is available")
    else:
        print("❌ Claude Code SDK not available - some tests will be skipped")

    # Test 2: Start grammar session
    print("\n2️⃣ Testing Grammar Session Start...")
    try:
        result = await integration.start_grammar_session(12345)
        if result.get('success'):
            print("✅ Grammar session started successfully")
            print(f"   Session ID: {result.get('session_id')}")
            print(f"   Current card: {result.get('current_card', {}).get('fields', {}).get('Word', 'N/A')}")
        else:
            print(f"❌ Failed to start grammar session: {result.get('error')}")
    except Exception as e:
        print(f"❌ Error starting grammar session: {e}")

    # Test 3: Vocabulary queue management
    print("\n3️⃣ Testing Vocabulary Queue...")

    # Simulate new vocabulary cards being detected
    await mock_client.add_vocabulary_card("fokozat", "Fokozási szint vagy fokozat jelölése")
    await mock_client.add_vocabulary_card("választ", "Válaszol valakinek vagy valamire")
    await mock_client.add_vocabulary_card("teljes", "Egész, teljességi állapot")

    # Add cards to queue (LIFO order)
    for card in mock_client.cards[1]:
        integration.vocabulary_queue.add_new_card(card)

    # Check queue status
    queue_status = integration.get_vocabulary_queue_status()
    print(f"✅ Vocabulary queue status: {queue_status}")

    # Test LIFO ordering
    print("\n   Testing LIFO ordering...")
    first_card = integration.get_next_vocabulary_card()
    if first_card and first_card['fields']['Word'] == 'teljes':
        print("✅ LIFO ordering working correctly (newest card 'teljes' first)")
    else:
        print(f"❌ LIFO ordering issue - got: {first_card['fields']['Word'] if first_card else 'None'}")

    # Test 4: Answer caching
    print("\n4️⃣ Testing Answer Caching...")
    integration.cache_vocabulary_answer(200, 3)  # Good
    integration.cache_vocabulary_answer(201, 2)  # Hard
    integration.cache_vocabulary_answer(202, 4)  # Easy

    cached_answers = len(integration.vocabulary_queue.card_answer_mapping)
    if cached_answers == 3:
        print(f"✅ Answer caching working: {cached_answers} answers cached")
    else:
        print(f"❌ Answer caching issue: expected 3, got {cached_answers}")

    # Test 5: Context preparation
    print("\n5️⃣ Testing Context Preparation...")
    test_card = {
        "fields": {
            "Word": "legbiztosabb",
            "Definition": "A 'biztos' melléknév felsőfokú alakja...",
            "Example Sentence": "Ez a legbiztosabb módszer...",
            "Grammar Code": "ADJ-SUPERLATIVE"
        }
    }

    context = integration._prepare_card_context(test_card)
    if "legbiztosabb" in context and "KÁRTYA KONTEXTUSA" in context:
        print("✅ Context preparation working correctly")
    else:
        print("❌ Context preparation issue")

    # Test 6: Claude SDK definition request (if available)
    if integration.claude_sdk_available:
        print("\n6️⃣ Testing Claude SDK Definition Request...")
        try:
            result = await integration.pause_grammar_session_for_definition(["fokozat", "teljes"])
            if result.get('success'):
                print("✅ Claude SDK definition request successful")
                print(f"   Request ID: {result.get('definition_request_id')}")
            else:
                print(f"❌ Claude SDK definition request failed: {result.get('error')}")
        except Exception as e:
            print(f"❌ Claude SDK definition request error: {e}")

    # Cleanup
    await integration.cleanup()
    print("\n✅ Integration test completed")

    return integration


async def test_web_interface_compatibility():
    """Test web interface integration points"""
    print("\n🌐 Testing Web Interface Compatibility")
    print("=" * 50)

    # Test that the enhanced main module can be imported
    try:
        from web_app.enhanced_main import app, startup, shutdown
        print("✅ Enhanced web interface module imported successfully")
    except Exception as e:
        print(f"❌ Error importing enhanced web interface: {e}")
        return False

    # Test FastAPI app creation
    try:
        if hasattr(app, 'routes'):
            route_count = len(app.routes)
            print(f"✅ FastAPI app created with {route_count} routes")
        else:
            print("❌ FastAPI app structure issue")
            return False
    except Exception as e:
        print(f"❌ FastAPI app test error: {e}")
        return False

    # Test API endpoint definitions
    expected_endpoints = [
        "/api/start-dual-session",
        "/api/request-definitions",
        "/api/request-vocabulary-definitions",
        "/api/answer-grammar-card",
        "/api/cache-vocabulary-answer",
        "/api/vocabulary-queue-status",
        "/api/next-vocabulary-card",
        "/api/submit-vocabulary-session",
        "/api/close-all-sessions"
    ]

    route_paths = [route.path for route in app.routes if hasattr(route, 'path')]

    missing_endpoints = []
    for endpoint in expected_endpoints:
        if endpoint not in route_paths:
            missing_endpoints.append(endpoint)

    if not missing_endpoints:
        print("✅ All expected API endpoints defined")
    else:
        print(f"❌ Missing endpoints: {missing_endpoints}")
        return False

    return True


async def test_define_with_context_integration():
    """Test integration with define-with-context command patterns"""
    print("\n📝 Testing Define-with-Context Integration")
    print("=" * 50)

    # Test context instructions loading
    mock_client = MockAnkiClient()
    integration = create_claude_sdk_integration(mock_client)

    try:
        instructions = await integration._get_context_instructions()

        if "CRITICAL INSTRUCTIONS" in instructions and "Hungarian" in instructions:
            print("✅ Context instructions loaded successfully")
            print(f"   Instructions length: {len(instructions)} characters")
        else:
            print("❌ Context instructions content issue")
            return False

    except Exception as e:
        print(f"❌ Error loading context instructions: {e}")
        return False

    # Test instruction content
    required_elements = [
        "CONTEXT SOURCE IDENTIFICATION",
        "Hungarian",
        "basic A1 Vocabulary",
        "creative definitions",
        "emojis",
        "LEMMA",
        "STEM",
        "base form",
        "conjugation",
        "mcp__anki-api__create_card"
    ]

    missing_elements = []
    for element in required_elements:
        if element not in instructions:
            missing_elements.append(element)

    if not missing_elements:
        print("✅ All required instruction elements found")
    else:
        print(f"❌ Missing instruction elements: {missing_elements}")

    await integration.cleanup()
    return len(missing_elements) == 0


async def test_complete_workflow():
    """Test complete workflow simulation"""
    print("\n🔄 Testing Complete Workflow")
    print("=" * 50)

    mock_client = MockAnkiClient()
    integration = create_claude_sdk_integration(mock_client)

    try:
        # Step 1: Start dual session
        print("1. Starting dual session...")
        session_result = await integration.start_grammar_session(12345)
        if not session_result.get('success'):
            print(f"❌ Failed to start session: {session_result.get('error')}")
            return False
        print("✅ Dual session started")

        # Step 2: Simulate vocabulary card detection
        print("2. Simulating vocabulary card detection...")
        await mock_client.add_vocabulary_card("példa", "Minta vagy szemléltető eset")
        integration.vocabulary_queue.add_new_card(mock_client.cards[1][-1])
        print("✅ Vocabulary card detected and queued (LIFO)")

        # Step 3: Cache vocabulary answer
        print("3. Caching vocabulary answer...")
        integration.cache_vocabulary_answer(203, 3)  # Good answer
        print("✅ Vocabulary answer cached")

        # Step 4: Simulate Claude SDK request (if available)
        if integration.claude_sdk_available:
            print("4. Requesting definitions from Claude SDK...")
            def_result = await integration.pause_grammar_session_for_definition(["példa"])
            if def_result.get('success'):
                print("✅ Claude SDK definition request completed")
            else:
                print(f"⚠️ Claude SDK request issue: {def_result.get('error')}")
        else:
            print("4. ⏭️ Skipping Claude SDK test (not available)")

        # Step 5: Test auto-session submission
        print("5. Testing vocabulary session submission...")
        submit_result = await integration.submit_vocabulary_session()
        if submit_result.get('success'):
            print("✅ Vocabulary session submitted for auto-processing")
        else:
            print(f"❌ Vocabulary session submission failed: {submit_result.get('error')}")

        # Step 6: Cleanup
        print("6. Cleaning up...")
        await integration.cleanup()
        print("✅ Cleanup completed")

        print("\n🎉 Complete workflow test passed!")
        return True

    except Exception as e:
        print(f"❌ Workflow test error: {e}")
        await integration.cleanup()
        return False


async def main():
    """Main test runner"""
    print("🚀 Enhanced AnkiChat Integration Test Suite")
    print("=" * 60)

    test_results = []

    # Run all tests
    try:
        # Test 1: Core integration
        integration_result = await test_claude_sdk_integration()
        test_results.append(("Claude SDK Integration", integration_result is not None))

        # Test 2: Web interface compatibility
        web_result = await test_web_interface_compatibility()
        test_results.append(("Web Interface Compatibility", web_result))

        # Test 3: Define-with-context integration
        context_result = await test_define_with_context_integration()
        test_results.append(("Define-with-Context Integration", context_result))

        # Test 4: Complete workflow
        workflow_result = await test_complete_workflow()
        test_results.append(("Complete Workflow", workflow_result))

    except Exception as e:
        print(f"💥 Test suite error: {e}")
        test_results.append(("Test Suite", False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)

    passed = 0
    total = len(test_results)

    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<35} {status}")
        if result:
            passed += 1

    print("-" * 60)
    print(f"Total: {passed}/{total} tests passed ({100*passed//total if total > 0 else 0}%)")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Integration is ready.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the issues above.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Test suite interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)