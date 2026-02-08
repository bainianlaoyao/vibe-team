# BeeBeeBrain Frontend

## Prerequisites
- Node.js 20+
- npm (project lockfile is `package-lock.json`)

## Environment
- Development: `frontend/.env.development`
- Production: `frontend/.env.production`

Key vars:
- `VITE_API_BASE_URL`
- `VITE_PROJECT_ID`
- Optional: `VITE_API_TOKEN`

## Run
```bash
cd frontend
npm install
npm run dev
```

## Build
```bash
cd frontend
npm run build
npm run preview -- --host 127.0.0.1 --port 4173
```

Build optimizations:
- Rollup manual chunks (`framework`, `icons`)
- CSS code splitting
- ES2020 target

## Browser E2E
```bash
cd frontend
$env:PLAYWRIGHT_BROWSERS_PATH='.playwright'   # PowerShell
npx playwright install chromium
npm run test:e2e
```
