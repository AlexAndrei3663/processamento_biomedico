#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Instalação Python concluída."
echo "Para executar:"
echo "  source .venv/bin/activate"
echo "  python main.py --fullscreen --update-interval-ms 150 --max-plot-points 3000"
echo ""
echo "Se houver erro de permissão na serial, adicione o usuário ao grupo dialout:"
echo "  sudo usermod -a -G dialout $USER"
echo "Depois reinicie a sessão do usuário."
