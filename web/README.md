# web

Next.js + Tailwind CSS frontend — chat UI, confidence gauge, and
listing/neighborhood cards with source citations. See A-01.

## Design

A cartography/compass concept, grounded directly in the product name
rather than a generic chatbot look: deep ink-navy surfaces, brass and
verdigris accents (a navigator's instrument case, not a SaaS palette),
Fraunces for the wordmark, Work Sans for the conversation, Space Mono
for prices/coordinates/citations. The confidence score — required to
always be visible, not left to the agent's prose — is drawn as a
compass needle swinging from south (no bearing) to true north
(confident) rather than a generic progress bar.

## Run it

```
npm install
cp .env.local.example .env.local   # point at your running api/ (Phase 4)
npm run dev
```

Open http://localhost:3000. Requires `api/`'s FastAPI server running
(`uvicorn main:app --port 8080` — see `../api/README.md`) with Postgres
seeded (Phases 0–1) for there to be anything to search.

## How it talks to the backend

`lib/streamChat.ts` hand-parses the SSE wire format from a plain
`fetch()` response stream — `EventSource` only supports GET requests,
and `/chat` needs a POST body, so this is the standard pattern for
POST-based SSE. Each turn yields four kinds of events (see
`lib/types.ts`, mirroring `api/main.py` exactly):

1. `{"thread_id": "..."}` — once, at the start
2. `{"status": "..."}` — zero or more, as the agent moves through steps
   ("Reading your message...", "Searching listings...", etc.) — see
   `components/StatusLog.tsx`
3. `{"token": "..."}` — as the agent's reply streams in
4. `{"done": true, "confidence_score": ..., "recommendations": [...]}` — once, at the end

The confidence score and listing cards only render once the `done`
event arrives — they're structured data from the graph's final state,
not something parsed out of the streamed prose.

## Structure

```
app/
├── layout.tsx        → fonts, metadata
├── page.tsx           → chat state machine, streaming, layout
└── globals.css        → design tokens (Tailwind v4 @theme)
components/
├── CompassGauge.tsx    → the confidence indicator (signature element)
├── ChatMessage.tsx      → message bubble + inline gauge + listing cards
├── StatusLog.tsx         → live "what's happening" log while the agent works
├── ListingCard.tsx       → property record card with source citations
└── ChatInput.tsx          → input bar
lib/
├── types.ts            → shared types, mirrors the backend's SSE/data shapes
└── streamChat.ts         → the SSE client
```

## Testing notes

`npm run build`, `npx tsc --noEmit`, and `npx eslint .` all pass
cleanly. The one thing not verified in the environment this was built
in: an actual live fetch of the Google Fonts used in `layout.tsx` —
that domain wasn't reachable from that sandbox, so the build was
re-run with system fonts substituted to confirm everything *other*
than the font fetch was correct (it was), then the real
`next/font/google` imports were restored for this delivered version.
That fetch will work normally wherever you actually run this.
