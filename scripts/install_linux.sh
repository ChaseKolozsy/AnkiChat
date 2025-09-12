#!/bin/bash

# Make sure core dependencies are installed
sudo apt-get update && sudo apt-get install -y build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev curl libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

# Install Docker if not present
if ! command -v docker &>/dev/null; then
  echo "Docker not found. Installing..."
  sudo apt-get update
  sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce
else
  echo "Docker already installed."
fi

# Install uv if not present
echo "Checking for uv..."
if ! command -v uv &>/dev/null; then
  echo "uv not found. Installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
else
  echo "uv already installed."
fi

# Install pyenv if not present
if ! command -v pyenv &>/dev/null; then
  curl https://pyenv.run | bash
  echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
  echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
  echo 'eval "$(pyenv init -)"' >> ~/.bashrc
  source ~/.bashrc
fi

# Install Node.js 18+ and npm if not present or if version is too old
echo "Checking Node.js version..."
if command -v node &>/dev/null; then
  NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
  if [ "$NODE_VERSION" -lt 18 ]; then
    echo "Node.js version is less than 18. Installing Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
  else
    echo "Node.js version $NODE_VERSION is already installed."
  fi
else
  echo "Node.js not found. Installing Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

# Install Claude Code globally via npm
echo "Installing Claude Code..."
npm install -g @anthropic-ai/claude-code

# Build Docker image and run container
OS_SELECT="linux"
BUILD_ARGS=""
while getopts ":s:m:p:i:c:h" opt; do
  case ${opt} in
    s) OS_SELECT=${OPTARG} ;;
    m) BUILD_ARGS+=" -m \"${OPTARG}\"" ;;
    p) BUILD_ARGS+=" -p ${OPTARG}" ;;
    i) BUILD_ARGS+=" -i ${OPTARG}" ;;
    c) BUILD_ARGS+=" -c ${OPTARG}" ;;
    h) echo "Usage: $0 [-s linux|mac|windows] [-m host_anki2_dir] [-p host_port] [-i image] [-c container]"; exit 0 ;;
    :) echo "Option -${OPTARG} requires an argument" >&2; exit 1 ;;
    \?) echo "Invalid option: -${OPTARG}" >&2; exit 1 ;;
  esac
done

echo "Building Docker image with OS selection: ${OS_SELECT}"
cd AnkiAPI/docker && eval ./build.sh -s "${OS_SELECT}" ${BUILD_ARGS}

# Clear uv cache before installation
echo "Clearing uv cache..."
uv cache clean

# Install AnkiChat globally as a uv tool
echo "Installing AnkiChat globally as a uv tool..."
uv tool install . --force

# Verify installation
echo "Verifying AnkiChat installation..."
which anki-chat-mcp
uv tool list | grep anki-chat

# Configure Claude Code with AnkiChat MCP server
echo "Configuring Claude Code with AnkiChat MCP server..."
# Get the absolute path of the project directory
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MCP_CONFIG_PATH="$PROJECT_DIR/mcp_config_global.json"

if [ -f "$MCP_CONFIG_PATH" ]; then
  echo "Adding AnkiChat MCP server to Claude Code..."
  # Add the MCP server at project level using the latest method
  cd "$PROJECT_DIR"
  claude mcp add anki-chat --scope project -- anki-chat-mcp
  echo "MCP server configured successfully."
else
  echo "Warning: mcp_config_global.json not found at $MCP_CONFIG_PATH"
fi

echo "Installation complete!"
echo "You can now use 'claude' command to access Claude Code with AnkiChat MCP integration."
