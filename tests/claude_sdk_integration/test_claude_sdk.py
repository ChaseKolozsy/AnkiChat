#!/usr/bin/env python3.10
"""
Test script for Claude Code SDK integration
This script demonstrates basic usage of the Claude Code SDK
"""

import asyncio
import os
import sys

def check_requirements():
    """Check if required dependencies and environment are set up"""
    print("Checking Claude Code SDK requirements...")

    # Check Python version
    if sys.version_info < (3, 10):
        print(f"❌ Python 3.10+ required, found {sys.version_info.major}.{sys.version_info.minor}")
        return False
    print(f"✅ Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    # Check for ANTHROPIC_API_KEY
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ ANTHROPIC_API_KEY environment variable not set")
        print("   Please set it with: export ANTHROPIC_API_KEY='your-api-key'")
        return False
    print("✅ ANTHROPIC_API_KEY is set")

    # Try importing the SDK
    try:
        import claude_code_sdk
        print("✅ claude-code-sdk is installed")
        return True
    except ImportError as e:
        print(f"❌ claude-code-sdk not installed: {e}")
        print("   Install with: pip install claude-code-sdk")
        return False

async def basic_query_test():
    """Test basic query functionality"""
    print("\n🧪 Testing basic query...")

    try:
        from claude_code_sdk import query

        prompt = "What is 2 + 2? Please respond with just the number."
        print(f"Sending query: {prompt}")

        response_parts = []
        async for message in query(prompt=prompt):
            print(f"📝 Response: {message}")
            response_parts.append(str(message))

        full_response = "".join(response_parts)
        print(f"🎯 Complete response: {full_response}")
        return True

    except Exception as e:
        print(f"❌ Basic query test failed: {e}")
        return False

async def advanced_options_test():
    """Test query with options"""
    print("\n🧪 Testing query with options...")

    try:
        from claude_code_sdk import query, ClaudeCodeOptions

        options = ClaudeCodeOptions(
            system_prompt="You are a helpful coding assistant.",
            max_turns=1
        )

        prompt = "List the files in the current directory and briefly describe what you see."
        print(f"Sending query with options: {prompt}")

        response_parts = []
        async for message in query(prompt=prompt, options=options):
            print(f"📝 Response: {message}")
            response_parts.append(str(message))

        full_response = "".join(response_parts)
        print(f"🎯 Complete response: {full_response}")
        return True

    except Exception as e:
        print(f"❌ Advanced options test failed: {e}")
        return False

async def main():
    """Main test function"""
    print("🚀 Claude Code SDK Test Script")
    print("=" * 50)

    # Check requirements first
    if not check_requirements():
        print("\n❌ Requirements check failed. Please fix the issues above.")
        sys.exit(1)

    print("\n✅ All requirements satisfied!")

    # Run tests
    tests_passed = 0
    total_tests = 2

    if await basic_query_test():
        tests_passed += 1

    if await advanced_options_test():
        tests_passed += 1

    # Summary
    print("\n" + "=" * 50)
    print(f"🎯 Test Results: {tests_passed}/{total_tests} passed")

    if tests_passed == total_tests:
        print("✅ All tests passed! Claude Code SDK is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Check the errors above.")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)