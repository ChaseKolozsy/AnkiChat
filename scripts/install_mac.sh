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

# Run the build script
echo "Building Docker image..."
cd AnkiAPI/docker && ./build.sh 


uv venv
source .venv/bin/activate

# Install project dependencies
uv pip install .

which python
which uv

