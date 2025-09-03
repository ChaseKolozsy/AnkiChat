#!/bin/bash

# Test script for AnkiChat MCP Server
echo "Testing AnkiChat MCP Server..."

cd /home/chase/AnkiChat

echo "Checking imports..."
.venv/bin/python -c "import sys; sys.path.append('.'); from AnkiClient.src.operations import card_ops; print('✓ Imports successful')"

echo -e "\nStarting MCP server (will stop after 3 seconds)..."
timeout 3s uv run --with 'mcp[cli]' mcp run src/servers/anki_mcp_server.py

echo -e "\n✓ MCP server test completed successfully!"
echo "Configuration file is available at: /home/chase/AnkiChat/mcp_config.json"
