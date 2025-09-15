#!/bin/bash
# Reinstall AnkiChat Web Interface Tool
# This script clears UV cache, uninstalls, and reinstalls the tool

set -e  # Exit on any error

echo "🔄 Reinstalling AnkiChat Web Interface Tool..."
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

# Step 3: Reinstall from current directory
echo "3️⃣ Installing anki-chat from current directory..."
uv tool install . --force
echo "✅ Tool installed successfully"
echo

# Step 4: Verify installation
echo "4️⃣ Verifying installation..."
echo "Available commands:"
uv tool list | grep anki-chat || echo "⚠️ AnkiChat not found in tool list"
echo

echo "Testing anki-chat-web command:"
anki-chat-web --help | head -3
echo

echo "🎉 Reinstallation complete! You can now run:"
echo "   anki-chat-web        # Start the web interface"
echo "   anki-chat-mcp        # Start the MCP server"