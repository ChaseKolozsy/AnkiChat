#!/bin/bash

# Install the current package
echo "Installing package..."
uv pip install .

# Navigate to the AnkiAPI/docker directory and run build.sh
echo "Building Docker image..."
cd AnkiAPI/docker && ./build.sh 