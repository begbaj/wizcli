#!/bin/bash

# wizcli installation script

# Exit on any error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}==> Starting wizcli installation...${NC}"

# 1. Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed.${NC}"
    exit 1
fi

# 2. Check for venv module
if ! python3 -m venv --help &> /dev/null; then
    echo -e "${YELLOW}The 'venv' module is missing. You might need to install it:${NC}"
    echo "  sudo apt-get install python3-venv"
    exit 1
fi

# 3. Create virtual environment
if [ ! -d "venv" ]; then
    echo -e "${GREEN}==> Creating virtual environment in 'venv/'...${NC}"
    python3 -m venv venv
else
    echo -e "${YELLOW}==> Virtual environment already exists.${NC}"
fi

# 4. Install/Upgrade pip and dependencies
echo -e "${GREEN}==> Installing dependencies...${NC}"
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 5. Create a convenient wrapper script
echo -e "${GREEN}==> Creating 'wizcli' wrapper...${NC}"
cat <<EOF > wizcli
#!/bin/bash
# wizcli wrapper script
SOURCE_DIR="\$( cd "\$( dirname "\${BASH_SOURCE[0]}" )" && pwd )"
"\$SOURCE_DIR/venv/bin/python" "\$SOURCE_DIR/cli.py" "\$@"
EOF

chmod +x wizcli

echo -e "${GREEN}==> Installation successful!${NC}"
echo -e "You can now run wizcli using: ${YELLOW}./wizcli${NC}"
echo ""
echo -e "${YELLOW}Note:${NC} If you encounter errors related to 'pyaudio' or 'aubio', you may need system libraries."
echo -e "On Debian/Ubuntu, try running:"
echo -e "  ${GREEN}sudo apt-get install libportaudio2 portaudio19-dev libaubio-dev${NC}"
echo ""
echo "Try running './wizcli discover' to find your bulbs!"
