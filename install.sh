# prepare environment and install this example on Ubuntu

# Step1 install packages
sudo apt-get update -y
sudo apt-get install -y git python3 python3-pip python3-venv

# Step2 download this repo into ~/mammoth-api/api-script-samples
cd ~
mkdir -p mammoth-api
cd mammoth-api
if [ -d "api-script-samples" ]; then
    cd api-script-samples
else
    git clone https://github.com/appaegis/api-script-samples.git
    cd api-script-samples
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
echo "Activating virtual environment '$VENV_NAME'..."
source "$VENV_NAME/bin/activate"

# Step4 install required libraries
python3 -m pip install -r requirements.txt

# Finish by venv instructions
echo
echo "Next please run: "
echo "   cd ~/mammoth-api/api-script-samples"
echo "   source $VENV_NAME/bin/activate"
echo "   python3 block-list-v2.py ..."
