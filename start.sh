#!/usr/bin/env bash
cd "$(dirname "$0")"

if ! command -v pnpm &> /dev/null; then
    echo -e "\033[0;31mpnpm not found. Install it with: npm install -g pnpm\033[0m"
    exit 1
fi

export NODE_ENV=production
echo "Installing server dependencies..."
(cd server && pnpm install --frozen-lockfile)
echo "Installing client dependencies and building..."
(cd client && pnpm install --frozen-lockfile && pnpm build)
echo "Starting PenDrift..."
node server/server.js
