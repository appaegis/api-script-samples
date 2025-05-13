#!/bin/bash

# Step1 install packages
# Check if running on Linux
if [ "$(uname)" = "Linux" ]; then
    # Check if packages are already installed
    if ! command -v python3 &> /dev/null || ! command -v pip3 &> /dev/null; then
        echo "Installing required system packages..."
        sudo apt-get update -y
        sudo apt-get install -y git python3 python3-pip python3-venv
    else
        echo "Required system packages are already installed."
    fi
fi

# Step2 check repository
if [ -d ".git" ]; then
    echo "Running in existing git repository..."
    REPO_DIR=$(pwd)
else
    echo "Setting up repository in ~/mammoth-api/api-script-samples..."
    cd ~
    if [ ! -d "mammoth-api" ]; then
        echo "Creating mammoth-api directory..."
        mkdir -p mammoth-api
    fi
    cd mammoth-api

    if [ -d "api-script-samples" ]; then
        echo "Repository already exists, updating..."
        cd api-script-samples
        git pull
    else
        echo "Cloning repository..."
        git clone https://github.com/appaegis/api-script-samples.git
        cd api-script-samples
    fi
    REPO_DIR=$(pwd)
fi

# Step3 prepare venv
VENV_NAME="apienv"
if [ -d "$VENV_NAME" ]; then
    echo "Virtual environment '$VENV_NAME' already exists. Activating..."
else
    echo "No existing virtual environment found. Creating one..."
    python3 -m venv "$VENV_NAME"
    echo "Created virtual environment '$VENV_NAME'."
fi

# Check if venv is already activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment '$VENV_NAME'..."
    source "$VENV_NAME/bin/activate"
else
    echo "Virtual environment is already activated."
fi

# Step4 install required libraries
if [ -f "requirements.txt" ]; then
    echo "Installing/updating required libraries..."
    python3 -m pip install -r requirements.txt
else
    echo "Error: requirements.txt not found!"
    exit 1
fi

# Finish by venv instructions
echo
echo "Next please run: "
echo "   cd $REPO_DIR"
echo "   source $VENV_NAME/bin/activate"
echo "   python3 block-list-v2.py ..."
