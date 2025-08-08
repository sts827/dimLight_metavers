#!/bin/bash

set -Eeuo pipefail

# Simple task runner to organize scripts without changing their current paths
# Usage: ./scripts/manage.sh <command> [args]
# Run ./scripts/manage.sh help for the list.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$PROJECT_DIR/scripts"

print_help() {
  cat <<'EOF'
Smart Switch Dimming - Task Runner

Usage:
  ./scripts/manage.sh <command> [args]

Core:
  status                       Show app and kiosk status
  web:start [--dev|--prod|--daemon]  Start web server
  web:stop                     Stop web server
  kiosk:start [--browser chromium|midori]  Start kiosk mode
  kiosk:stop                   Stop kiosk mode

Setup:
  setup:auto                   Run auto setup
  setup:zero2w                 Run Zero2W setup
  setup:install-auto           Install auto setup as service

SSH:
  ssh:fix                      Apply immediate SSH fixes
  ssh:optimize                 Optimize SSH for Zero2W

Diagnostics / Logs:
  logs:env                     Capture environment snapshot
  logs:migration               View migration logs

Misc:
  help                         Show this help
EOF
}

cmd=${1:-help}
shift || true

case "$cmd" in
  help|-h|--help)
    print_help ;;

  status)
    bash "$SCRIPTS_DIR/status.sh" ;;  

  web:start)
    bash "$SCRIPTS_DIR/start.sh" "$@" ;;

  web:stop)
    bash "$SCRIPTS_DIR/stop.sh" ;;

  kiosk:start)
    bash "$SCRIPTS_DIR/simple_kiosk.sh" "$@" ;;

  kiosk:stop)
    bash "$SCRIPTS_DIR/stop_kiosk.sh" ;;

  setup:auto)
    bash "$SCRIPTS_DIR/auto_setup.sh" "$@" ;;

  setup:zero2w)
    bash "$SCRIPTS_DIR/setup_zero2w.sh" "$@" ;;

  setup:install-auto)
    bash "$SCRIPTS_DIR/install_auto_setup.sh" "$@" ;;

  ssh:fix)
    bash "$SCRIPTS_DIR/fix_ssh_immediately.sh" ;;

  ssh:optimize)
    bash "$SCRIPTS_DIR/optimize_ssh_zero2w.sh" ;;

  logs:env)
    bash "$SCRIPTS_DIR/environment_logger.sh" ;;

  logs:migration)
    bash "$SCRIPTS_DIR/view_migration_logs.sh" ;;

  *)
    echo "Unknown command: $cmd" >&2
    echo "Run: ./scripts/manage.sh help" >&2
    exit 1 ;;

esac
