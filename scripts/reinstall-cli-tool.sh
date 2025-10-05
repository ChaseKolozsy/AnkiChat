#!/bin/bash
# Reinstall AnkiChat CLI Tool
# This script clears UV cache, uninstalls, and reinstalls the CLI tool

set -e  # Exit on any error

echo "🔄 Reinstalling AnkiChat CLI Tool..."
echo

# Step 1: Clear UV cache
echo "1️⃣ Clearing UV cache..."
uv cache clean
echo "✅ UV cache cleared"
echo

# Step 2: Uninstall existing tool
echo "2️⃣ Uninstalling existing anki-chat tool..."
uv tool uninstall anki-chat || echo "ℹ️ Tool not installed or already removed"
echo "✅ Uninstalled existing tool"
echo

# Step 3: Reinstall from current directory with CLI extras
echo "3️⃣ Installing anki-chat with CLI extras from current directory..."
uv tool install ".[cli]" --force
echo "✅ Tool installed successfully"
echo

# Step 4: Verify installation
echo "4️⃣ Verifying installation..."
echo "Available commands:"
uv tool list | grep anki-chat || echo "⚠️ AnkiChat not found in tool list"
echo

echo "Testing ankichat-cli command:"
ankichat-cli --help | head -5
echo

echo "🎉 Reinstallation complete! You can now run:"
echo "   ankichat-cli             # Start interactive study session"
echo "   ankichat-cli study       # Start study session"
echo "   ankichat-cli sync        # Sync with AnkiWeb"
echo "   ankichat-cli stats       # Show deck statistics"
echo "   ankichat-cli --help      # Show all commands"
