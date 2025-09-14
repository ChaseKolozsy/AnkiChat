#!/bin/bash
# Quick development reinstall script for AnkiChat
# Always includes cache clear for consistent installs

echo "🔄 Quick reinstall with cache clear..."
uv cache clean
uv tool uninstall anki-chat 2>/dev/null || true
uv tool install . --force
echo "✅ Done! Updated with latest changes."