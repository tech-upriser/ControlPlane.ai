/**
 * ControlPlane.ai — Content Script
 * ═══════════════════════════════════
 * Workstream 2: Content Script & DOM Bridge
 *
 * Responsibilities:
 *  1. Detect AI platform and initialize the appropriate adapter
 *  2. Observe DOM for new AI responses via MutationObserver
 *  3. Capture prompt / response pairs once streaming finishes (debounce)
 *  4. Send evaluation requests to background.js → backend /v1/evaluate
 *  5. Render the single, non-duplicated confidence header bar with gradient meter
 *  6. Apply inline semantic highlights to response paragraphs
 *  7. Handle Block / Reword action messages from the side panel
 *  8. Guard against duplicate injection via data-cp-eval-id
 */
(function () {
  'use strict';

  // ═══════════════════════════════════════════
  // Configuration
  // ═══════════════════════════════════════════
  const CONFIG = {
    DEBOUNCE_MS: 2000,            // Wait for streaming to settle before evaluating
    MIN_RESPONSE_LENGTH: 30,      // Minimum chars to trigger evaluation
    ATTR_EVAL_ID: 'data-cp-eval-id',
    ATTR_PENDING: 'data-cp-pending',
    ATTR_SEGMENT: 'data-cp-segment-idx',
  };

  // ═══════════════════════════════════════════
  // Internal State
  // ═══════════════════════════════════════════
  const state = {
    platform: null,                     // Active platform adapter
    evaluations: new Map(),             // evalId → { data, container, segmentEls[], prompt }
    debounceTimers: new Map(),          // container → timeoutId
    currentEvalId: null,                // Most recent evaluation for action routing
    _pendingContainer: null,            // Container awaiting evaluation result
    _pendingPrompt: '',                 // Prompt for the pending container
  };

  // ═══════════════════════════════════════════
  // Initialization
  // ═══════════════════════════════════════════
  function init() {
    if (window.ControlPlaneTheme) {
      window.ControlPlaneTheme.initContentScript();
    }
    if (!window.ControlPlanePlatform) {
      console.error('[ControlPlane] Platform adapter not loaded — aborting');
      return;
    }
    state.platform = window.ControlPlanePlatform.detectPlatform();
    if (!state.platform) {
      console.warn('[ControlPlane] Unsupported platform:', window.location.href);
      return;
    }
    window.ControlPlanePlatform.current = state.platform;

    setupObserver();
    setupMessageListener();

    // Initial scan for any pre-existing responses (page already loaded)
    setTimeout(scanForResponses, 1200);

    console.log(`[ControlPlane] Content script initialized for ${state.platform.name}`);
  }

  // ═══════════════════════════════════════════
  // DOM Observation
  // ═══════════════════════════════════════════
  function setupObserver() {
    const observer = new MutationObserver(() => {
      scanForResponses();
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  /**
   * Scans the page for AI response containers. For each new, unprocessed
   * container, starts (or resets) a debounce timer. When the timer fires
   * without further mutations the response is considered "settled" and
   * gets sent for evaluation.
   */
  function scanForResponses() {
    if (!state.platform) return;

    let containers;
    try {
      containers = document.querySelectorAll(state.platform.selectors.responseContainers);
    } catch (e) {
      return; // Selector may be invalid on this page variant
    }

    containers.forEach((container) => {
      // Already evaluated — skip
      if (container.hasAttribute(CONFIG.ATTR_EVAL_ID)) return;

      // Still streaming — reset debounce so we try again later
      if (state.platform.isStreaming && state.platform.isStreaming()) {
        resetDebounce(container);
        return;
      }

      // Start / reset debounce for this container
      resetDebounce(container);
    });
  }

  function resetDebounce(container) {
    if (state.debounceTimers.has(container)) {
      clearTimeout(state.debounceTimers.get(container));
    }

    const timerId = setTimeout(() => {
      state.debounceTimers.delete(container);
      // Final guard: not yet evaluated, not pending, not streaming
      if (container.hasAttribute(CONFIG.ATTR_EVAL_ID)) return;
      if (container.hasAttribute(CONFIG.ATTR_PENDING)) return;
      if (state.platform.isStreaming && state.platform.isStreaming()) return;
      processResponse(container);
    }, CONFIG.DEBOUNCE_MS);

    state.debounceTimers.set(container, timerId);
  }

  // ═══════════════════════════════════════════
  // Response Processing
  // ═══════════════════════════════════════════
  function processResponse(container) {
    const responseText = state.platform.extractResponseText(container);
    if (!responseText || responseText.length < CONFIG.MIN_RESPONSE_LENGTH) return;

    const prompt = state.platform.extractPromptText(container);

    // Mark as pending to prevent double-processing
    container.setAttribute(CONFIG.ATTR_PENDING, 'true');
    state._pendingContainer = container;
    state._pendingPrompt = prompt;

    // Request evaluation from background service worker
    try {
      chrome.runtime.sendMessage(
        {
          action: 'evaluate',
          prompt: prompt,
          responseText: responseText,
        },
        (response) => {
          if (chrome.runtime.lastError) {
            console.warn('[ControlPlane] Background error:', chrome.runtime.lastError.message);
            container.removeAttribute(CONFIG.ATTR_PENDING);
            renderOfflineBar(container);
          }
          // Actual result arrives via the 'evaluationResult' message handler
        }
      );
    } catch (err) {
      console.error('[ControlPlane] Messaging failed:', err);
      container.removeAttribute(CONFIG.ATTR_PENDING);
      renderOfflineBar(container);
    }
  }

  // ═══════════════════════════════════════════
  // Chrome Message Listener
  // ═══════════════════════════════════════════
  function setupMessageListener() {
    chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
      switch (message.action) {
        case 'evaluationResult':
          handleEvaluationResult(message.data);
          sendResponse({ received: true });
          break;

        case 'rewordResult':
          handleRewordResult(message.segmentIndex, message.data);
          sendResponse({ received: true });
          break;

        case 'blockSegment':
          handleBlockSegment(message.evaluationId, message.segmentIndex);
          sendResponse({ received: true });
          break;
      }
      return true; // Keep channel open for async responses
    });
  }

  // ═══════════════════════════════════════════
  // Evaluation Result → Render UI
  // ═══════════════════════════════════════════
  function handleEvaluationResult(data) {
    const container = state._pendingContainer || findPendingContainer();
    if (!container) {
      console.warn('[ControlPlane] No pending container for evaluation result');
      return;
    }

    const evalId = data.evaluation_id;
    container.removeAttribute(CONFIG.ATTR_PENDING);
    container.setAttribute(CONFIG.ATTR_EVAL_ID, evalId);

    // Store evaluation state for later action handling
    const evalState = {
      data: data,
      container: container,
      segmentEls: [],
      prompt: state._pendingPrompt || '',
    };
    state.evaluations.set(evalId, evalState);
    state.currentEvalId = evalId;

    // Clear pending references
    state._pendingContainer = null;
    state._pendingPrompt = '';

    // Render the confidence header bar
    renderConfidenceBar(container, data);

    // Apply inline paragraph highlights
    renderInlineHighlights(container, data, evalState);
  }

  function findPendingContainer() {
    return document.querySelector(`[${CONFIG.ATTR_PENDING}="true"]`);
  }

  // ═══════════════════════════════════════════
  // Render: Confidence Header Bar
  // ═══════════════════════════════════════════
  function renderConfidenceBar(container, data) {
    // Remove any existing bar in this container to prevent duplicates
    const existing = container.querySelector('.cp-header-bar');
    if (existing) existing.remove();

    const confidence = data.overall_confidence || 0;

    const bar = document.createElement('div');
    bar.className = 'cp-header-bar';
    bar.setAttribute('data-cp-injected', 'true');

    bar.innerHTML = `
      <div class="cp-header-left">
        <div class="cp-header-title">
          <span class="cp-header-label">ControlPlane Confidence:</span>
          <span class="cp-header-score">${confidence}%</span>
        </div>
        <div class="cp-gradient-bar">
          <div class="cp-gradient-fill" style="width: 0%"></div>
        </div>
      </div>
      <button class="cp-deep-dive-btn" title="Open Deep Dive analytics panel">
        <span class="cp-bar-icon">📊</span>
        <span>Deep Dive</span>
        <span class="cp-arrow">↗</span>
      </button>
    `;

    // Insert at the top of the container
    const insertionPoint = state.platform.getInsertionPoint(container);
    if (insertionPoint) {
      container.insertBefore(bar, insertionPoint);
    } else {
      container.prepend(bar);
    }

    // Animate the gradient fill in the next frame
    requestAnimationFrame(() => {
      const fill = bar.querySelector('.cp-gradient-fill');
      if (fill) fill.style.width = confidence + '%';
    });

    // Deep Dive button → open side panel
    const deepDiveBtn = bar.querySelector('.cp-deep-dive-btn');
    deepDiveBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      try {
        chrome.runtime.sendMessage({ action: 'openSidePanel' });
      } catch (err) {
        console.warn('[ControlPlane] Could not open side panel:', err);
      }
    });
  }

  function renderOfflineBar(container) {
    const existing = container.querySelector('.cp-header-bar');
    if (existing) existing.remove();

    const bar = document.createElement('div');
    bar.className = 'cp-header-bar cp-offline';
    bar.setAttribute('data-cp-injected', 'true');

    bar.innerHTML = `
      <div class="cp-header-left">
        <div class="cp-header-title">
          <span class="cp-header-label">ControlPlane: Backend Offline</span>
        </div>
        <div class="cp-gradient-bar">
          <div class="cp-gradient-fill" style="width: 0%; opacity: 0.3"></div>
        </div>
      </div>
      <button class="cp-deep-dive-btn" disabled title="Backend is not reachable">
        <span class="cp-bar-icon">⚠️</span>
        <span>Offline</span>
      </button>
    `;

    const insertionPoint = state.platform.getInsertionPoint(container);
    if (insertionPoint) {
      container.insertBefore(bar, insertionPoint);
    } else {
      container.prepend(bar);
    }
  }

  // ═══════════════════════════════════════════
  // Render: Inline Semantic Highlights
  // ═══════════════════════════════════════════
  function renderInlineHighlights(container, data, evalState) {
    if (!data.segments || data.segments.length === 0) return;

    const paragraphs = state.platform.getTextParagraphs(container);
    if (paragraphs.length === 0) return;

    const matches = matchSegmentsToParagraphs(data.segments, paragraphs);

    matches.forEach(({ segment, element, index }) => {
      let effectiveClassification = segment.classification;

      // Apply classification class
      const classMap = {
        verified: 'cp-segment-verified',
        ambiguous: 'cp-segment-ambiguous',
        hallucination: 'cp-segment-hallucination',
      };

      const className = classMap[effectiveClassification];
      if (className) {
        element.classList.add('cp-segment-wrapper', className);
      }

      // Track segment index for action routing
      element.setAttribute(CONFIG.ATTR_SEGMENT, String(index));

      // Append badge — use the effective classification's badge
      const badgeMap = {
        verified: 'High Confidence',
        ambiguous: 'High Cost / Rework?',
        hallucination: 'Hallucination Detected',
      };
      const badgeText = badgeMap[effectiveClassification] || segment.badge;
      if (badgeText) {
        const badge = createBadge(badgeText, effectiveClassification);
        element.appendChild(badge);
      }

      // Store reference for action handlers
      evalState.segmentEls[index] = element;

      if (effectiveClassification === 'blocked') {
        handleBlockSegment(evalState.data.evaluation_id, index);
      }
    });
  }

  /**
   * Match backend segments to DOM paragraphs.
   * Strategy 1: direct index mapping when counts align.
   * Strategy 2: text-similarity fallback for mismatched counts.
   */
  function matchSegmentsToParagraphs(segments, paragraphs) {
    const matches = [];

    // Strategy 1: counts match — assume 1:1 ordering
    if (segments.length === paragraphs.length) {
      segments.forEach((segment, i) => {
        matches.push({ segment, element: paragraphs[i], index: i });
      });
      return matches;
    }

    // Strategy 2: text overlap matching
    const used = new Set();

    segments.forEach((segment, segIdx) => {
      const segText = normalizeText(segment.text);
      let bestEl = null;
      let bestScore = 0;
      let bestIdx = -1;

      paragraphs.forEach((para, pIdx) => {
        if (used.has(pIdx)) return;
        const paraText = normalizeText(para.innerText);
        const score = textOverlap(segText, paraText);
        if (score > bestScore && score > 0.3) {
          bestScore = score;
          bestEl = para;
          bestIdx = pIdx;
        }
      });

      if (bestEl) {
        used.add(bestIdx);
        matches.push({ segment, element: bestEl, index: segIdx });
      }
    });

    return matches;
  }

  function createBadge(text, classification) {
    const badge = document.createElement('span');
    badge.className = `cp-badge cp-badge-${classification}`;
    badge.textContent = text;
    return badge;
  }

  // ═══════════════════════════════════════════
  // Action Handler: Block
  // ═══════════════════════════════════════════
  function handleBlockSegment(evaluationId, segmentIndex) {
    const evalId = evaluationId || state.currentEvalId;
    const evalState = state.evaluations.get(evalId);
    if (!evalState) {
      console.warn('[ControlPlane] No evaluation found for block action');
      return;
    }

    const segmentEl = evalState.segmentEls[segmentIndex];
    if (!segmentEl) {
      console.warn('[ControlPlane] Segment element not found at index', segmentIndex);
      return;
    }

    // Replace the paragraph with a blocked banner
    const banner = document.createElement('div');
    banner.className = 'cp-blocked-banner';
    banner.innerHTML = `
      <span class="cp-blocked-icon">⚠️</span>
      <span class="cp-blocked-text">Content blocked due to policy/hallucination risk</span>
      <span class="cp-blocked-status">Blocked</span>
    `;

    // Clear existing segment styling and content
    segmentEl.className = 'cp-segment-wrapper';
    segmentEl.innerHTML = '';
    segmentEl.appendChild(banner);

    // Update the header bar to reflect blocked state
    const headerBar = evalState.container.querySelector('.cp-header-bar');
    if (headerBar) {
      headerBar.classList.add('cp-blocked-state');
      headerBar.classList.remove('cp-updated');
      const scoreEl = headerBar.querySelector('.cp-header-score');
      if (scoreEl) scoreEl.textContent = 'Blocked';
    }

    // Update internal segment state
    if (evalState.data.segments[segmentIndex]) {
      evalState.data.segments[segmentIndex].classification = 'blocked';
    }
  }

  // ═══════════════════════════════════════════
  // Action Handler: Reword
  // ═══════════════════════════════════════════
  function handleRewordResult(segmentIndex, data) {
    const evalState = state.evaluations.get(state.currentEvalId);
    if (!evalState) {
      console.warn('[ControlPlane] No evaluation found for reword action');
      return;
    }

    const segmentEl = evalState.segmentEls[segmentIndex];
    if (!segmentEl) {
      console.warn('[ControlPlane] Segment element not found at index', segmentIndex);
      return;
    }

    // Remove old classification styling
    segmentEl.classList.remove('cp-segment-hallucination', 'cp-segment-ambiguous');

    // Remove old badge
    const oldBadge = segmentEl.querySelector('.cp-badge');
    if (oldBadge) oldBadge.remove();

    // Replace paragraph text with corrected version
    // Preserve the element but replace text content
    const correctedText = data.corrected_text || data.correctedText || '';
    const childEls = Array.from(segmentEl.children).filter(
      (ch) => !ch.classList.contains('cp-badge')
    );

    if (childEls.length > 0) {
      // If paragraph has child elements (e.g., <strong>, <em>), replace innerText
      childEls.forEach((ch) => (ch.textContent = ''));
      if (childEls[0]) childEls[0].textContent = correctedText;
    } else {
      // Plain text node
      segmentEl.childNodes.forEach((node) => {
        if (node.nodeType === Node.TEXT_NODE) node.textContent = '';
      });
      segmentEl.insertBefore(document.createTextNode(correctedText), segmentEl.firstChild);
    }

    // Apply verified styling with glow animation
    segmentEl.classList.add('cp-segment-verified', 'cp-segment-reworded');

    // Add new badge
    const newBadge = createBadge(data.new_badge || 'High Confidence', 'verified');
    segmentEl.appendChild(newBadge);

    // Update the confidence bar
    const newConfidence = data.new_confidence || 96;
    updateConfidenceBar(evalState.container, newConfidence);

    // Update internal segment state
    if (evalState.data.segments[segmentIndex]) {
      evalState.data.segments[segmentIndex].classification = 'verified';
      evalState.data.segments[segmentIndex].confidence = newConfidence;
      evalState.data.segments[segmentIndex].badge = 'High Confidence';
    }
    evalState.data.overall_confidence = newConfidence;
  }

  function updateConfidenceBar(container, newConfidence) {
    const headerBar = container.querySelector('.cp-header-bar');
    if (!headerBar) return;

    headerBar.classList.add('cp-updated');
    headerBar.classList.remove('cp-blocked-state');

    const scoreEl = headerBar.querySelector('.cp-header-score');
    if (scoreEl) scoreEl.textContent = newConfidence + '%';

    const fill = headerBar.querySelector('.cp-gradient-fill');
    if (fill) fill.style.width = newConfidence + '%';
  }

  // ═══════════════════════════════════════════
  // Utilities
  // ═══════════════════════════════════════════
  function normalizeText(text) {
    return (text || '').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function textOverlap(a, b) {
    if (!a || !b) return 0;
    // Full containment
    if (a.includes(b) || b.includes(a)) return 1.0;
    // Prefix comparison (first 80 characters)
    const len = Math.min(80, a.length, b.length);
    const prefA = a.substring(0, len);
    const prefB = b.substring(0, len);
    let matches = 0;
    for (let i = 0; i < len; i++) {
      if (prefA[i] === prefB[i]) matches++;
    }
    return matches / len;
  }

  // ═══════════════════════════════════════════
  // Bootstrap
  // ═══════════════════════════════════════════
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
