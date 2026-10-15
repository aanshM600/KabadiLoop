# KabadiLoop: waste finds its next life

Reuse first, repair next, recycle last, and hazardous items only to specialist handling. Photograph an object, confirm what it is, then sell it, give it away, scrap it, or send it to specialist handling. Every step is tracked in a digital twin.

**Team:** <team name> · **College:** DSU · **Hackathon:** <name, date>
**Live demo:** <GitHub Pages link>

## What works
- Scan a photo or use the camera, then confirm or correct the guess.
- Follow-up questions: condition, cleanliness, battery/chemicals/electronics.
- Sell as scrap, sell on the reuse board, give away, or hand to a specialist.
- Hazardous items are blocked from reuse and recycling batches.
- Digital twin: valid state transitions only, timestamped event history, saved in the browser.
- Dashboard: counts, estimated value, material-flow diagram, wallet.

## Honest limits
- **Money, buyers, destinations and the reuse board are simulated.** Scrap values are estimates from sample weights and sample rates.
- **Scanner:** optional Teachable Machine model, then Claude vision, then a basic colour scanner. Claude vision only works when the page is opened through claude.ai. Accuracy has not been measured.
- No real partnerships, no Loop AI chat yet, environmental savings not shown.

## Run
Open `index.html` in a browser, or use GitHub Pages. No build step.

## Backend prototype (`backend/`, `tests/`)
Original Python lifecycle, routing, matching, batching and impact logic (standard library only).
Run tests: `python3 tests/test_core.py`. `app.py` (FastAPI) is untested.

## Original work vs external
- Original: routing rules, lifecycle engine, matching, batching, destination ranking, UI.
- External: TensorFlow.js and Teachable Machine library (optional model), Claude vision (via claude.ai), Google Fonts.
