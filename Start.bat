@echo off
pushd %~dp0
set NODE_ENV=production
echo Installing server dependencies...
cd server
call pnpm install --frozen-lockfile
cd ..
echo Installing client dependencies...
cd client
call pnpm install --frozen-lockfile
echo Building client...
call pnpm build
cd ..
echo Starting PenDrift...
node server/server.js
pause
popd
