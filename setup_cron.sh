#!/bin/bash
# Sets up a daily 8:00 AM cron job for the Genie Code PM Morning Brief.
# Run once: bash setup_cron.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(which python3)"
LOG="$SCRIPT_DIR/logs/cron.log"

CRON_LINE="0 8 * * * $PYTHON $SCRIPT_DIR/main.py >> $LOG 2>&1"

# Check if already registered
if crontab -l 2>/dev/null | grep -qF "$SCRIPT_DIR/main.py"; then
  echo "✓ Cron job already registered."
else
  (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
  echo "✓ Cron job added: runs daily at 8:00 AM."
fi

echo ""
echo "Verify with:  crontab -l"
echo "Remove with:  crontab -e  (delete the Genie Code line)"
echo "Manual run:   python3 $SCRIPT_DIR/main.py"
echo "Dry run:      python3 $SCRIPT_DIR/main.py --dry-run"
