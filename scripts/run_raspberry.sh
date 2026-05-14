#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-xcb}
python3 main.py --fullscreen --update-interval-ms 150 --max-plot-points 3000
