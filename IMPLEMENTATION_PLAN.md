# ControlPlane Frontend–Backend Bridge & Actionable UI

## Problem Summary

The ControlPlane.ai browser extension is currently **detached from the backend engine**. The content script injects hardcoded `72%` confidence bars, duplicates them on every DOM mutation, and has no real data flow from the backend analysis pipeline. The side panel renders static mock data. Action buttons (`Block`, `Reword`, `Escalate`) are non-functional placeholders. DOM selectors are hardcoded for a single ChatGPT layout.

### Current Architecture Gaps Identified

| Component | Current State | Target State |
|---|---|---|
| [content.js](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/content.js) | Hardcoded `72%`, duplicated bars, ChatGPT-only selectors | Dynamic scores from backend, single bar per response, multi-platform |
| [background.js](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/background.js) | Sends prompt to backend, broadcasts raw chunks | Full orchestrator: captures prompt + response, sends to `/v1/evaluate`, manages state |
| [sidepanel.html](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/sidepanel.html) / [sidepanel.js](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/sidepanel.js) | Static hardcoded metrics, button sends message but content.js ignores it | Dynamic telemetry binding, histogram, collapsible dimensions, hover popovers |
| [content.css](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/content.css) | Basic box-shadow styles, no gradient bar, no badge system | Gradient confidence meter, semantic paragraph badges, blocked banner |
| Backend API | No `/v1/evaluate` endpoint for the extension to call post-hoc | New endpoint that accepts `{prompt, response}` and returns structured analysis JSON |
| [manifest.json](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/manifest.json) | Only ChatGPT host permissions | Claude, Gemini host permissions added |

---

## User Review Required

> [!IMPORTANT]
> **Backend API Design**: The current backend only has `/v1/chat/completions` (a proxy endpoint). For the extension to evaluate *third-party* AI responses observed in the DOM (ChatGPT, Claude, Gemini), we need a new **`POST /v1/evaluate`** endpoint that accepts `{prompt, response_text}` and returns the full structured analysis. This is the foundational bridge.

> [!IMPORTANT]
> **Reword Flow**: The `Reword` action in the screenshots shows the flagged text being *replaced* with a corrected version. This requires a new **`POST /v1/reword`** endpoint that accepts `{original_text, prompt, reasons}` and returns `{corrected_text}`. Since the backend uses a mock LLM, we'll generate a heuristic "cleaned" version (removing hedging phrases, fake citations, etc.) rather than calling a real LLM.

> [!WARNING]
> **Multi-platform DOM Selectors**: The screenshots all show ChatGPT. Adding Claude (`claude.ai`) and Gemini (`gemini.google.com`) support requires platform-specific DOM selector configs. These can be tested only on those live sites. The architecture will be built to support them, but initial testing will focus on ChatGPT.

---

## Open Questions

1. **Backend URL Configuration**: Should the extension connect to `localhost:8000` (dev) or should we add a settings page for configurable API URL? The screenshots show a "Settings" tab in the side panel — should we implement that now?

2. **"Traces" and "Models" Tabs**: Screenshots 3–6 show tabs for `Overview | Traces | Models | Policy | Settings` in the side panel. Should we stub all of these, or focus only on the `Overview` tab (which contains the confidence + dimensions + actions)?

3. **Escalation Webhook**: The `Escalate` button is specified as disabled/future. Should clicking it show a tooltip ("Coming soon — enterprise feature"), or just remain visually disabled?

---

## Proposed Changes — 3 Parallel Workstreams

The implementation is divided into **3 independent workstreams** that can be developed simultaneously by 3 different team members, then merged. Each workstream has clear interface contracts defined below.

---

### 🔴 WORKSTREAM 1: Backend API Bridge (Member A — Backend Developer)

**Goal**: Create the new API endpoints that the extension will call, and expose the structured analysis JSON that the frontend needs.

#### Interface Contract (Output)

The extension will call these endpoints. Member A must implement them and publish the response schemas for Members B and C to consume.

---

#### [NEW] `app/api/evaluate_routes.py`

New FastAPI router with two endpoints:

**`POST /v1/evaluate`** — Main analysis endpoint
```
Request:
{
  "prompt": "What are the key factors driving AI adoption...",
  "response_text": "The adoption of AI in supply chain management...",
  "session_id": "optional-session-id",
  "platform": "chatgpt"  // "claude", "gemini"
}

Response:
{
  "evaluation_id": "uuid",
  "overall_confidence": 72,  // 0-100 (100 - overall_risk from RiskEngine)
  "risk_level": "medium",
  "recommended_action": "flag",
  "dimensions": {
    "performance": {
      "score": 82,
      "label": "Reliability",
      "sub_metrics": {
        "accuracy": 33,
        "hallucination_risks": 45,
        "hallucination_risk_level": "medium",
        "fabrication_signals": ["fake_url: https://example.com/study"],
        "hedging_ratio": 0.15,
        "prompt_alignment": 0.72
      }
    },
    "cost": {
      "score": 45,
      "label": "Efficiency",
      "sub_metrics": {
        "token_consumption": 245,
        "hallucination_rework_cost": 30,
        "loop_detected": false,
        "cost_rating": "moderate",
        "estimated_cost_usd": 0.004
      }
    },
    "responsibility": {
      "score": 72,
      "label": "Safety & Ethics",
      "sub_metrics": {
        "hate_speech": 66,
        "pii_leaks": 40,
        "bias_detection": 59,
        "pii_count": 0,
        "tone_compliance": 86,
        "toxicity_detected": false,
        "injection_detected": false,
        "content_safe": true
      }
    }
  },
  "segments": [
    {
      "text": "The adoption of AI in supply chain management is driven by several key factors. First, AI enables demand forecasting with greater accuracy by analyzing vast amounts of historical and real-time data.",
      "classification": "verified",
      "confidence": 91,
      "badge": "High Confidence",
      "reasons": []
    },
    {
      "text": "Second, It helps optimize inventory levels and reduce operational costs across the supply chain by identifying inefficiencies and automating routine tasks.",
      "classification": "ambiguous",
      "confidence": 58,
      "badge": "High Cost / Rework?",
      "reasons": ["Medium hallucination risk", "Contains hedging patterns"]
    },
    {
      "text": "Additionally, some experimental AI models are being developed to perfectly synchronize global logistics with an efficiency that ensures near-zero disruptions, which is considered highly speculative.",
      "classification": "hallucination",
      "confidence": 22,
      "badge": "Hallucination Detected",
      "reasons": ["High hallucination risk", "Fabricated claims", "Low prompt alignment"]
    },
    {
      "text": "Finally, AI improves supplier collaboration and enhances decision-making speed through automation and intelligent insights.",
      "classification": "verified",
      "confidence": 88,
      "badge": "High Confidence",
      "reasons": []
    }
  ],
  "confidence_distribution": [5, 8, 12, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 72, 68, 55, 40, 30]
}
```

**`POST /v1/reword`** — Re-generation/correction endpoint
```
Request:
{
  "original_text": "some experimental AI models are being developed...",
  "prompt": "What are the key factors driving AI adoption...",
  "reasons": ["High hallucination risk", "Fabricated claims"],
  "session_id": "optional"
}

Response:
{
  "corrected_text": "Current AI research is focused on improving logistics coordination, though real-world deployment remains in early stages with varying degrees of success.",
  "new_confidence": 96,
  "new_classification": "verified",
  "new_badge": "High Confidence"
}
```

#### [MODIFY] [main.py](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/app/main.py)
- Register the new `evaluate_routes` router

#### [NEW] `app/core/segment_analyzer.py`
- New module that takes the full response text and splits it into semantic segments (by paragraph/sentence boundaries)
- Runs each segment through the existing checkers (`hallucination_checker`, `content_safety`, `pii_scanner`, `context_health`)
- Classifies each segment as `verified` / `ambiguous` / `hallucination` with per-segment confidence scores
- Generates the `confidence_distribution` histogram data (20 buckets representing the confidence distribution)

#### [NEW] `app/core/reword_engine.py`
- Heuristic reword engine that:
  - Strips hedging phrases from the text
  - Removes fabricated citations/URLs
  - Softens absolute claims to hedged, factual language
  - Returns cleaned text with a boosted confidence score

---

### 🟢 WORKSTREAM 2: Content Script & DOM Bridge (Member B — Extension/Frontend Developer)

**Goal**: Rewrite the content script to be platform-adaptive, capture prompts/responses from the DOM, communicate with the backend via the background worker, and render inline visual annotations.

#### Dependencies
- Consumes the `/v1/evaluate` response schema (defined by Workstream 1)
- Communicates with the side panel via Chrome messages (interface defined below)

---

#### [NEW] `extension/platforms/platform_adapter.js`
Decoupled DOM selection layer. Exports a platform-specific adapter:

```javascript
// Each adapter implements:
{
  name: "chatgpt",
  matchUrl: (url) => url.includes("chatgpt.com"),
  selectors: {
    responseContainers: '[data-message-author-role="assistant"]',
    promptContainers: '[data-message-author-role="user"]',
    responseText: '.markdown.prose',
    streamingIndicator: '.result-streaming',
    messageWrapper: 'article[data-testid^="conversation-turn"]'
  },
  extractPromptText: (container) => { /* ... */ },
  extractResponseText: (container) => { /* ... */ },
  getInsertionPoint: (container) => { /* returns element to insert bar before */ },
  isStreaming: () => { /* check if response is still streaming */ }
}
```

Adapters for: **ChatGPT**, **Claude** (`claude.ai`), **Gemini** (`gemini.google.com`) — with Claude and Gemini being initial stubs with documented selector patterns.

#### [MODIFY] [content.js](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/content.js) → Full rewrite

**New responsibilities:**
1. **Platform Detection**: On load, detect which platform from URL and load the correct adapter
2. **Response Observer**: Use `MutationObserver` with platform-specific selectors to detect when a new AI response appears and when streaming finishes
3. **Prompt Capture**: When a response appears, traverse backward in the DOM to find the corresponding user prompt
4. **Backend Request**: Send `{prompt, response_text}` to background.js which relays to `/v1/evaluate`
5. **Header Bar Rendering**: Inject a single, non-duplicated confidence bar above the response with:
   - `ControlPlane Confidence: XX%` text
   - Multi-color gradient progress meter (green → yellow → orange → red)
   - `Deep Dive ↗` button that sends a Chrome message to open/toggle the side panel
6. **Inline Semantic Highlighting**: Parse the `segments[]` array from the backend response and wrap matching paragraphs in the DOM with classification-specific styles:
   - **`verified`**: Subtle green left-border + `High Confidence` badge (right-aligned)
   - **`ambiguous`**: Orange dashed underline + `High Cost / Rework?` badge
   - **`hallucination`**: Red dashed border + `Hallucination Detected` badge
7. **Action Handlers**: Listen for messages from the side panel:
   - `reword`: Replace the flagged paragraph text in the DOM, transition highlight green → update confidence
   - `block`: Replace flagged paragraph with red banner `⚠️ Content blocked due to policy/hallucination risk`
8. **Deduplication Guard**: Track injected responses via `data-cp-eval-id` attribute to prevent double injection

#### [MODIFY] [content.css](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/content.css) → Full rewrite

Match the screenshots exactly:
- **Header bar**: Dark semi-transparent background (`rgba(30,30,30,0.9)`), rounded, with gradient meter (green-yellow-orange-red segments)
- **`Deep Dive ↗` button**: Right-aligned, with bar chart icon (`↗` with small bars), white text on dark
- **Verified segments**: Subtle green left-border, semi-transparent green bg
- **Ambiguous segments**: Orange dashed underline, orange badge
- **Hallucination segments**: Red dashed border, red background tint, `Hallucination Detected` tag
- **Blocked banner**: Full-width red dashed border box with ⚠️ icon and bold warning text
- **Badges**: Pill-shaped, right-aligned below each paragraph, color-coded

#### [MODIFY] [background.js](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/background.js) → Significant rewrite

**New responsibilities:**
1. **API Relay**: Receive `{action: 'evaluate', prompt, response_text}` from content.js → call `POST /v1/evaluate` → return structured JSON
2. **Reword Relay**: Receive `{action: 'reword', ...}` → call `POST /v1/reword` → return corrected text
3. **Side Panel Toggle**: Handle `{action: 'openSidePanel'}` messages from the Deep Dive button → use `chrome.sidePanel.open()`
4. **State Bridge**: Forward evaluation results to both content.js and sidepanel.js
5. **Error Handling**: Graceful fallback if backend is unreachable (show "Backend offline" in confidence bar)

#### [MODIFY] [manifest.json](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/manifest.json)

- Add host permissions for `*://*.claude.ai/*`, `*://*.gemini.google.com/*`
- Add `"side_panel"` configuration pointing to `sidepanel.html`
- Add content script matches for Claude and Gemini
- Import the new `platforms/platform_adapter.js` in `content_scripts.js` array

---

### 🔵 WORKSTREAM 3: Deep Dive Side Panel & Actions UI (Member C — UI/UX Developer)

**Goal**: Rebuild the side panel to match the screenshots exactly — dynamic telemetry, collapsible dimensions, hover popovers, histogram, and wired action buttons.

#### Dependencies
- Consumes the evaluation JSON schema (defined by Workstream 1)
- Sends action messages to content.js via background.js (interface defined below)

---

#### [MODIFY] [sidepanel.html](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/sidepanel.html) → Full rewrite

Match the screenshots precisely. Structure:

```
┌────────────────────────────────────────────┐
│ 🛡️ ControlPlane  v1.2.0    Maximize  ✕    │
├────────────────────────────────────────────┤
│ Overview | Traces | Models | Policy | Sett │
├────────────────────────────────────────────┤
│ Overall Confidence ⓘ    How is this calc? │
│                                            │
│  72%        ▐▐▐▌▐▐▐▐▐▐▐▐▐▐ 72%           │
│  Confidence  ▐▐▐▌▐▐▐▐▐▐▐▐▐▐              │
│              0%          100%              │
├────────────────────────────────────────────┤
│ Dimensions ⓘ                              │
│                                            │
│ ✅ Performance (Reliability)  ●●●  82%  ▸ │
│ 💰 Cost (Efficiency)         ●●   45%  ▸ │
│ 🛡️ Responsibility            ●●●  72%  ▸ │
│   └ Responsibility (Safety & Ethics)    ▸ │
│     ┌─────────────────────────────────┐   │
│     │ · Hate Speech    ████████  66%  │   │
│     │ · PII Leaks      ██████    40%  │   │
│     │ · Hate Speech    ████████  60%  │   │
│     │ · PII Leaks      █████████ 90%  │   │
│     │ · Bias Detection ██████████ 59% │   │
│     │ · Tone Compliance████████  86%  │   │
│     └─────────────────────────────────┘   │
├────────────────────────────────────────────┤
│ Checks ⓘ                    All passes ⓘ │
├────────────────────────────────────────────┤
│ Actions                                    │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│ │ 🚫 Block │ │ ✏️ Reword│ │ ⚡Escalate│   │
│ └──────────┘ └──────────┘ └──────────┘   │
├────────────────────────────────────────────┤
│ ControlPlane v1.5.0   Beta   Report Issue │
└────────────────────────────────────────────┘
```

Key UI elements:
- **Tab bar**: `Overview | Traces | Models | Policy | Settings` — only Overview is functional; others show "Coming Soon" placeholder
- **Confidence histogram**: Bar chart visualization (20 bars) with highlighted peak bar, green-to-red gradient
- **Dimension sections**: Collapsible accordion with chevron toggle
- **Sub-metrics**: Horizontal bar indicators with percentage labels, color-coded (green/yellow/orange/red)
- **Bias Detection popover**: On hover, show tooltip with Gender Bias, Racial Bias, Political Neutrality sub-scores and contextual recommendations
- **"Blocked" state**: When Block is clicked, the Overall Confidence header transitions to show "Blocked" in red with updated percentage
- **Footer**: Version number, Beta badge, Report Issue link

#### [MODIFY] [sidepanel.css](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/sidepanel.css) → Full rewrite

Dark theme matching screenshots:
- Background: `#121212` body, `#1a1a1a` sections
- Tab bar: Dark with subtle borders, active tab has bottom highlight
- Histogram bars: Green-to-yellow gradient, peak bar highlighted
- Dimension headers: Icon + label + circular progress indicator + score + chevron
- Sub-metric bars: Rounded, color stops at green(>80)/yellow(60-80)/orange(40-60)/red(<40)
- Action buttons: Red (Block), green (Reword), orange/gray (Escalate — disabled)
- Smooth transitions and micro-animations throughout
- Popover/tooltip: Dark card with arrow, appears on hover

#### [MODIFY] [sidepanel.js](file:///c:/Users/katri/OneDrive/Desktop/CurrProjects/ControlPlane.ai/extension/sidepanel.js) → Full rewrite

**New responsibilities:**
1. **Data Binding**: Listen for `{action: 'evaluationResult', data: {...}}` messages from background.js
2. **Dynamic Rendering**: On receiving evaluation data:
   - Update overall confidence percentage and histogram
   - Populate dimension scores with animated progress bars
   - Render sub-metrics in collapsible sections
   - Update segment list highlighting
3. **Accordion Toggle**: Each dimension section expands/collapses on click, showing sub-metrics
4. **Hover Popovers**: Bias Detection row shows popover with:
   - Gender Bias: Low/Medium/High
   - Racial Bias: Low/Medium/High  
   - Political Neutrality: Fair (Warning)
   - "Patterns neutralize biases"
   - "Inference is provided token flo studies."
   - "View Audit/More" link
5. **Action Button Handlers**:
   - **Block**: Sends `{action: 'blockSegment', segmentIndex}` to background → relayed to content.js → updates sidebar badge to "Blocked" + red styling on overall confidence
   - **Reword**: Sends `{action: 'rewordSegment', segmentIndex}` to background → calls `/v1/reword` → relayed to content.js for DOM replacement → updates sidebar confidence to ~96% with green styling
   - **Escalate**: Disabled button with tooltip "Enterprise feature — coming soon"
6. **Histogram Renderer**: Canvas or div-based bar chart with 20 bars, green-to-red gradient, peak highlighted with the confidence percentage label above it
7. **Tab Navigation**: Only Overview tab is active; other tabs show placeholder content
8. **State Management**: Local state object that tracks current evaluation, blocked segments, reworded segments

---

## Interface Contracts Between Workstreams

### Chrome Message Protocol

All communication between content.js ↔ background.js ↔ sidepanel.js uses `chrome.runtime.sendMessage` / `chrome.tabs.sendMessage` with this message protocol:

```javascript
// Content.js → Background.js
{ action: 'evaluate', prompt: string, responseText: string, tabId: number }
{ action: 'openSidePanel' }

// Background.js → Content.js
{ action: 'evaluationResult', data: EvaluationResponse }
{ action: 'rewordResult', segmentIndex: number, data: RewordResponse }

// Background.js → Sidepanel.js
{ action: 'evaluationResult', data: EvaluationResponse }
{ action: 'rewordComplete', segmentIndex: number, newConfidence: number }
{ action: 'blockComplete', segmentIndex: number }

// Sidepanel.js → Background.js
{ action: 'blockSegment', segmentIndex: number, evaluationId: string }
{ action: 'rewordSegment', segmentIndex: number, evaluationId: string, originalText: string, prompt: string, reasons: string[] }
{ action: 'escalateSegment', segmentIndex: number }  // future
```

### File Ownership Matrix

| File | Workstream | Owner |
|---|---|---|
| `app/api/evaluate_routes.py` | 🔴 WS1 | Member A |
| `app/core/segment_analyzer.py` | 🔴 WS1 | Member A |
| `app/core/reword_engine.py` | 🔴 WS1 | Member A |
| `app/main.py` (router registration) | 🔴 WS1 | Member A |
| `extension/platforms/platform_adapter.js` | 🟢 WS2 | Member B |
| `extension/content.js` | 🟢 WS2 | Member B |
| `extension/content.css` | 🟢 WS2 | Member B |
| `extension/background.js` | 🟢 WS2 | Member B |
| `extension/manifest.json` | 🟢 WS2 | Member B |
| `extension/sidepanel.html` | 🔵 WS3 | Member C |
| `extension/sidepanel.css` | 🔵 WS3 | Member C |
| `extension/sidepanel.js` | 🔵 WS3 | Member C |

---

## Merge Strategy

1. **WS1 (Backend)** merges first — it has no frontend dependencies
2. **WS2 (Content Script)** and **WS3 (Side Panel)** can merge in parallel after WS1, since they communicate through messages and don't touch the same files
3. **Integration testing** after merge: Load extension on ChatGPT, submit a prompt, verify end-to-end flow

---

## Verification Plan

### Automated Tests

```bash
# WS1: Backend endpoint tests
pytest tests/test_evaluate_endpoint.py -v
pytest tests/test_reword_endpoint.py -v
pytest tests/test_segment_analyzer.py -v

# Backend server smoke test
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl -X POST http://localhost:8000/v1/evaluate -H "Content-Type: application/json" -d '{"prompt": "test", "response_text": "test response"}'
```

### Manual Verification

1. **Flow A (Inline Highlighting)**:
   - Load extension in Chrome → navigate to `chatgpt.com`
   - Submit a prompt → wait for AI response to complete
   - Verify: single confidence bar appears above response (not duplicated)
   - Verify: paragraphs are highlighted with correct classification badges
   - Verify: gradient meter reflects the actual confidence score

2. **Flow B (Deep Dive Panel)**:
   - Click `Deep Dive ↗` → verify side panel opens
   - Verify: Overall Confidence matches the header bar
   - Verify: Histogram renders with correct distribution
   - Click dimension headers → verify accordion expand/collapse
   - Hover over Bias Detection → verify popover appears

3. **Flow C (Actions)**:
   - Click `Reword` → verify flagged paragraph text is replaced in DOM
   - Verify: highlight transitions from red → green
   - Verify: confidence score updates to ~96%
   - Click `Block` → verify paragraph is replaced with red warning banner
   - Verify: sidebar shows "Blocked" state
   - Verify: `Escalate` button is visually disabled

4. **Cross-platform Stub**:
   - Navigate to `claude.ai` → verify extension loads without errors (even if selectors need tuning)
   - Check console for platform detection log message
