#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  THE ARCHITECT — Setup Script
#  Sovereign Development & Autonomy Platform
#  Threadpower Labs / P.A.T.R.I.C.I.A. Stack
# ═══════════════════════════════════════════════════════════
#
#  Run this on The Forge to deploy The Architect:
#    chmod +x setup.sh && ./setup.sh
#
# ═══════════════════════════════════════════════════════════

set -e

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  THE ARCHITECT — Setup"
echo "  Sovereign Development & Autonomy Platform"
echo "  Threadpower Labs"
echo "═══════════════════════════════════════════════════════"
echo ""

# Step 1: Create /forge/architect if it doesn't exist
INSTALL_DIR="/forge/architect"
echo "[1/6] Creating installation directory..."
sudo mkdir -p "$INSTALL_DIR"
sudo chown -R $USER:$USER "$INSTALL_DIR"

# Step 2: Copy project files
echo "[2/6] Copying project files..."
# If running from the downloaded directory:
if [ -f "main.py" ]; then
    cp -r . "$INSTALL_DIR/"
else
    echo "  Run this script from the architect project directory"
    exit 1
fi

cd "$INSTALL_DIR"

# Step 3: Create .env from template
echo "[3/6] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from template"
    echo "  IMPORTANT: Edit .env with your API keys before starting"
    echo "    nano $INSTALL_DIR/.env"
else
    echo "  .env already exists, keeping current config"
fi

# Step 4: Create Docker network if needed
echo "[4/6] Checking Docker network..."
if ! docker network inspect forge-network >/dev/null 2>&1; then
    docker network create forge-network
    echo "  Created forge-network"
else
    echo "  forge-network already exists"
fi

# Step 5: Install Python dependencies (for CLI usage outside Docker)
echo "[5/6] Installing Python dependencies..."
pip install --break-system-packages -q fastapi pydantic pydantic-settings \
    redis httpx pyyaml typer rich uvicorn 2>/dev/null || \
pip install -q fastapi pydantic pydantic-settings \
    redis httpx pyyaml typer rich uvicorn

# Step 6: Create tasks directory
echo "[6/6] Creating task directories..."
mkdir -p "$INSTALL_DIR/tasks"
mkdir -p "$INSTALL_DIR/modules"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SETUP COMPLETE"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Edit your API keys:"
echo "     nano $INSTALL_DIR/.env"
echo ""
echo "  2. Start The Architect (choose one):"
echo ""
echo "     Direct (for development):"
echo "       cd $INSTALL_DIR"
echo "       uvicorn architect.main:app --reload --port 8000"
echo ""
echo "     Docker (for production):"
echo "       cd $INSTALL_DIR"
echo "       docker compose up -d"
echo ""
echo "  3. Verify it's running:"
echo "       curl http://localhost:8000/health"
echo ""
echo "  4. Submit your first task:"
echo "       curl -X POST http://localhost:8000/tasks \\"
echo "         -H 'Content-Type: application/json' \\"
echo "         -d '{\"name\": \"Hello Architect\","
echo "              \"description\": \"Test task\","
echo "              \"type\": \"config\"}'"
echo ""
echo "  5. Or use the CLI:"
echo "       cd $INSTALL_DIR"
echo "       python -m architect.cli health"
echo "       python -m architect.cli budget"
echo "       python -m architect.cli guardrails"
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  The Forge is now building The Architect."
echo "  Let's make it sing."
echo "═══════════════════════════════════════════════════════"
echo ""
