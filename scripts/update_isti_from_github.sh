#!/bin/sh
# Runs nightly on hpc.isti.cnr.it (cron, account raffaele, 04:30 UTC):
# pulls the latest site from GitHub into ~/site-src and copies the public
# files into ~/public_html, which serves https://raffaele.isti.cnr.it/.
# The GitHub workflow refreshes publications at 03:30 UTC, so this picks them up.
# Old files already in public_html are left alone (no --delete).
set -e
SRC="$HOME/site-src"
DEST="$HOME/public_html"
LOG="$HOME/site-update.log"

{
  echo "== $(date -u '+%Y-%m-%d %H:%M UTC')"
  git -C "$SRC" pull --ff-only -q
  git -C "$SRC" log --oneline -1
  cd "$SRC"
  rsync -a --itemize-changes --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
    index.html robots.txt sitemap.xml assets "$DEST/"
} >> "$LOG" 2>&1

# keep the log short
tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
