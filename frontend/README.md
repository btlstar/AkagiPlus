# AkagiPlus frontend

The React / TypeScript frontend is the application UI configured in
`../tauri.conf.json`. It uses Vite, Tailwind CSS, shadcn/ui, Zustand,
react-grid-layout and Tauri 2 APIs.

## Build and run

From this directory, run `npm ci` once, `npm run dev` for the development
server, or `npm run build` to type-check and build `dist/`. Run the desktop
application through the repository-root `start.bat`. `npm run lint` and
`npm test` check the affected frontend code.

## Source layout

- `src/routes`: Overview, Match, Cosmetics, Bots, History, Review, Logs and Settings.
- `src/components` and `src/tiles`: shared controls and dashboard widgets.
- `src/stores` and `src/hooks/useTauriBridge.ts`: state and event subscriptions.
- `src/types.ts`: frontend types; backend definitions are under `../src/schema`.
- `src/lib/tauri.ts` and `../src/ipc`: commands and event integration.
- `src/i18n/resources`: English, Japanese, Simplified and Traditional Chinese strings.
- `src/announcements`: bundled release announcements and their translations.

Game launch and local cosmetics are shared between Overview, Match and
Settings. Product names are RiichiCityStyle, ZhangxinPlus and AmatsukiStyle;
RiichiCityUnlock remains a separate optional external program.

Mahjong images are managed by `src/components/Mahgen.tsx` and
`src/lib/mahgenRegistry.ts`; see [tile sizing](mahgen.md).
