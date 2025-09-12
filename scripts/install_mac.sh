#!/bin/bash

# Install Xcode command line tools if not present
xcode-select --install > /dev/null 2>&1

# Install Homebrew if not present
if ! command -v brew &>/dev/null; then
  echo "Homebrew not found. Installing..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
else
  echo "Homebrew already installed."
fi

# Install Docker if not present
if ! command -v docker &>/dev/null; then
  echo "Docker not found. Installing..."
  brew install docker
else
  echo "Docker already installed."
fi

# Install uv if not present
echo "Checking for uv..."
if ! command -v uv &>/dev/null; then
  echo "uv not found. Installing..."
  brew install uv
else
  echo "uv already installed."
fi

# Install pyenv if not present
if ! command -v pyenv &>/dev/null; then
  brew update
  brew install pyenv
  echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
  echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
  echo 'eval "$(pyenv init -)"' >> ~/.zshrc
  source ~/.zshrc
fi

# Run the build script with OS selection support
OS_SELECT="mac"
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
echo "Verifying installation..."
which anki-chat-mcp
uv tool list | grep anki-chat
