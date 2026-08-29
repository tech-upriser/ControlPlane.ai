/**
 * ControlPlane.ai — Background Service Worker
 * ═════════════════════════════════════════════
 * Workstream 2: Extension / Frontend Developer
 *
 * Responsibilities:
 *  1. Relay evaluation requests from content.js → backend POST /v1/evaluate
 *  2. Relay reword requests from sidepanel.js → backend POST /v1/reword
 *  3. Forward block/action commands between sidepanel.js ↔ content.js
 *  4. Handle side-panel toggle from the Deep Dive button
 *  5. Graceful mock fallback when the backend is unreachable
 */

const API_BASE = 'http://localhost:8000';

// ═══════════════════════════════════════════
// Evaluation State Cache
// Stores the latest evaluation so the side panel
// can retrieve it even when opened after evaluation.
// ═══════════════════════════════════════════
let latestEvaluation = null;

// ═══════════════════════════════════════════
// Extension Lifecycle
// ═══════════════════════════════════════════
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

// ═══════════════════════════════════════════
// Message Router
// ═══════════════════════════════════════════
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab?.id;

  switch (message.action) {
    // ── Content Script → Backend ──
    case 'evaluate':
      handleEvaluate(message, tabId, sendResponse);
      return true; // async

    // ── Side Panel → Backend → Content Script ──
    case 'rewordSegment':
      handleReword(message, tabId, sendResponse);
      return true;

    // ── Side Panel → Content Script ──
    case 'blockSegment':
      handleBlock(message, tabId, sendResponse);
      return true;

    // ── Content Script → Side Panel ──
    case 'openSidePanel':
      handleOpenSidePanel(sender);
      sendResponse({ ok: true });
      break;

    // ── Side Panel requests cached evaluation ──
    case 'getLatestEvaluation':
      sendResponse({ ok: true, data: latestEvaluation });
      break;

    // ── Future: Enterprise escalation ──
    case 'escalateSegment':
      sendResponse({ ok: false, reason: 'Escalation is an enterprise feature (coming soon)' });
      break;
  }
});

// ═══════════════════════════════════════════
// Evaluate Handler
// ═══════════════════════════════════════════
async function handleEvaluate(message, tabId, sendResponse) {
  const { prompt, responseText } = message;
  let evalData;

  try {
    const res = await fetch(`${API_BASE}/v1/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: prompt,
        response_text: responseText,
        platform: 'chatgpt',
      }),
    });
    if (!res.ok) throw new Error(`Backend ${res.status}`);
    evalData = await res.json();
  } catch (err) {
    console.warn('[ControlPlane BG] Backend unreachable — using local mock:', err.message);
    evalData = generateMockEvaluation(prompt, responseText);
  }

  // Cache the evaluation for late-opening side panel
  latestEvaluation = evalData;

  // Broadcast to content script (tab)
  if (tabId) {
    chrome.tabs.sendMessage(tabId, { action: 'evaluationResult', data: evalData })
      .catch((e) => console.warn('[ControlPlane BG] Tab msg error:', e));
  }

  // Broadcast to side panel (extension pages)
  chrome.runtime.sendMessage({ action: 'evaluationResult', data: evalData })
    .catch(() => { /* side panel may not be open */ });

  sendResponse({ ok: true, evaluation_id: evalData.evaluation_id });
}

// ═══════════════════════════════════════════
// Reword Handler
// ═══════════════════════════════════════════
async function handleReword(message, senderTabId, sendResponse) {
  const { segmentIndex, evaluationId, originalText, prompt, reasons } = message;
  const tabId = senderTabId || (await getActiveTabId());

  let rewordData;
  try {
    const res = await fetch(`${API_BASE}/v1/reword`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        original_text: originalText,
        prompt: prompt,
        reasons: reasons || [],
      }),
    });
    if (!res.ok) throw new Error(`Backend ${res.status}`);
    rewordData = await res.json();
  } catch (err) {
    console.warn('[ControlPlane BG] Reword fallback:', err.message);
    rewordData = generateMockReword(originalText);
  }

  // Send corrected text to content script for DOM replacement
  if (tabId) {
    chrome.tabs.sendMessage(tabId, {
      action: 'rewordResult',
      segmentIndex: segmentIndex,
      data: rewordData,
    }).catch((e) => console.warn('[ControlPlane BG] Tab msg error:', e));
  }

  // Notify side panel of completion
  chrome.runtime.sendMessage({
    action: 'rewordComplete',
    segmentIndex: segmentIndex,
    newConfidence: rewordData.new_confidence || 96,
  }).catch(() => {});

  sendResponse({ ok: true });
}

// ═══════════════════════════════════════════
// Block Handler
// ═══════════════════════════════════════════
async function handleBlock(message, senderTabId, sendResponse) {
  const { segmentIndex, evaluationId } = message;
  const tabId = senderTabId || (await getActiveTabId());

  // Forward block command to content script
  if (tabId) {
    chrome.tabs.sendMessage(tabId, {
      action: 'blockSegment',
      segmentIndex: segmentIndex,
      evaluationId: evaluationId,
    }).catch((e) => console.warn('[ControlPlane BG] Tab msg error:', e));
  }

  // Notify side panel
  chrome.runtime.sendMessage({
    action: 'blockComplete',
    segmentIndex: segmentIndex,
  }).catch(() => {});

  sendResponse({ ok: true });
}

// ═══════════════════════════════════════════
// Side Panel Toggle
// ═══════════════════════════════════════════
async function handleOpenSidePanel(sender) {
  try {
    const tabId = sender.tab?.id;
    if (tabId) {
      await chrome.sidePanel.open({ tabId });
    }
  } catch (err) {
    console.warn('[ControlPlane BG] Side panel open failed:', err);
  }
}

// ═══════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════
async function getActiveTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.id;
}

// ═══════════════════════════════════════════
// Mock Data Generators
// Used as fallback when backend is not yet running (WS1 not merged)
// ═══════════════════════════════════════════

function generateMockEvaluation(prompt, responseText) {
  const paragraphs = responseText.split(/\n\n+/).filter((p) => p.trim().length > 15);

  // Deterministic classification pattern matching the demo screenshots
  const classPattern = ['verified', 'verified', 'ambiguous', 'hallucination', 'verified'];
  const segments = paragraphs.map((text, i) => {
    const cls = classPattern[i % classPattern.length];
    const confMap = { verified: 88, ambiguous: 55, hallucination: 22 };
    const badgeMap = {
      verified: 'High Confidence',
      ambiguous: 'High Cost / Rework?',
      hallucination: 'Hallucination Detected',
    };
    const reasonsMap = {
      verified: [],
      ambiguous: ['Medium hallucination risk', 'Contains hedging patterns'],
      hallucination: ['High hallucination risk', 'Speculative claims', 'Low prompt alignment'],
    };
    return {
      text: text.trim(),
      classification: cls,
      confidence: confMap[cls] + Math.floor(Math.random() * 8),
      badge: badgeMap[cls],
      reasons: reasonsMap[cls],
    };
  });

  // Histogram data — bell-curve peaked around 72%
  const distribution = Array.from({ length: 20 }, (_, i) => {
    const center = 14;
    const dist = Math.abs(i - center);
    return Math.max(5, 55 - dist * dist) + Math.floor(Math.random() * 8);
  });

  return {
    evaluation_id: crypto.randomUUID(),
    overall_confidence: 72,
    risk_level: 'medium',
    recommended_action: 'flag',
    dimensions: {
      performance: {
        score: 82,
        label: 'Reliability',
        sub_metrics: {
          accuracy: 33,
          hallucination_risks: 45,
          hallucination_risk_level: 'medium',
          fabrication_signals: [],
          hedging_ratio: 0.15,
          prompt_alignment: 0.72,
        },
      },
      cost: {
        score: 45,
        label: 'Efficiency',
        sub_metrics: {
          token_consumption: 245,
          hallucination_rework_cost: 30,
          loop_detected: false,
          cost_rating: 'moderate',
          estimated_cost_usd: 0.004,
        },
      },
      responsibility: {
        score: 72,
        label: 'Safety & Ethics',
        sub_metrics: {
          hate_speech: 66,
          pii_leaks: 40,
          bias_detection: 59,
          pii_count: 0,
          tone_compliance: 86,
          toxicity_detected: false,
          injection_detected: false,
          content_safe: true,
        },
      },
    },
    segments: segments,
    confidence_distribution: distribution,
  };
}

function generateMockReword(originalText) {
  let corrected = originalText
    .replace(/perfectly/gi, 'effectively')
    .replace(/ensures near-zero/gi, 'aims to minimize')
    .replace(/highly speculative/gi, 'an area of active research')
    .replace(/experimental/gi, 'emerging')
    .replace(/being developed to/gi, 'designed to help');

  // If no substitutions were made, provide a generic corrected version
  if (corrected === originalText) {
    corrected =
      'Current research in this area shows promising results, though real-world implementation varies in effectiveness and scale.';
  }

  return {
    corrected_text: corrected,
    new_confidence: 96,
    new_classification: 'verified',
    new_badge: 'High Confidence',
  };
}
