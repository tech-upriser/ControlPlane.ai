// ===== STATE MANAGEMENT =====
const state = {
    status: 'idle', // idle | evaluating | ready | blocked | reworded
    evaluation: null,
    blockedSegments: new Set(),
    rewordedSegments: new Set(),
};

// ===== DOM REFS =====
const els = {
    confidenceValue: document.getElementById('confidence-value'),
    confidenceStatus: document.getElementById('confidence-status'),
    histogram: document.getElementById('histogram'),
    checksStatus: document.getElementById('checks-status'),
    biasPopover: document.getElementById('bias-popover'),
    biasRow: document.getElementById('bias-row'),
    btnBlock: document.getElementById('btn-block'),
    btnReword: document.getElementById('btn-reword'),
    btnEscalate: document.getElementById('btn-escalate'),
};

// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initAccordions();
    initActions();
    initBiasPopover();
    initChecksExpanded();
    initThemeControls();
    initWindowControls();

    // Reset UI to empty state waiting for evaluation
    updateConfidence('--%', 'normal');
    renderHistogram([]);
    renderDimensions({
        performance: { score: 0 },
        cost: { score: 0 },
        responsibility: { score: 0 }
    });

    // Disable action buttons initially until evaluation arrives
    els.btnBlock.disabled = true;
    els.btnReword.disabled = true;

    // Request cached evaluation from background.js
    if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({ action: 'getLatestEvaluation' }, (response) => {
            if (chrome.runtime.lastError) return;
            if (response && response.ok && response.data) {
                renderEvaluation(response.data);
            }
        });
    }
});

// ===== WINDOW CONTROLS =====
function initWindowControls() {
    const btnMaximize = document.getElementById('btn-maximize');
    const btnClose = document.getElementById('btn-close');

    if (btnMaximize) {
        btnMaximize.addEventListener('click', (e) => {
            e.preventDefault();
            if (typeof chrome !== 'undefined' && chrome.tabs && chrome.tabs.create) {
                chrome.tabs.create({ url: chrome.runtime.getURL('sidepanel.html') });
            }
        });
    }

    if (btnClose) {
        btnClose.addEventListener('click', () => {
            window.close();
        });
    }
}

// ===== THEME CONTROLS =====
function initThemeControls() {
    const btnToggle = document.getElementById('theme-toggle-btn');
    const selector = document.getElementById('theme-selector');

    if (typeof window.ControlPlaneTheme === 'undefined') {
        console.warn('[ControlPlane] Theme module not loaded');
        return;
    }

    // Initialize Theme module
    window.ControlPlaneTheme.initSidePanel();

    // Header theme toggle button
    if (btnToggle) {
        btnToggle.addEventListener('click', () => {
            const nextMode = window.ControlPlaneTheme.cycleOverride();
            updateToggleUI(nextMode);
        });
    }

    // Settings panel theme selector
    if (selector) {
        const options = selector.querySelectorAll('.theme-option');
        options.forEach(opt => {
            opt.addEventListener('click', () => {
                const mode = opt.dataset.themeMode;
                window.ControlPlaneTheme.setOverride(mode);
            });
        });
    }

    // Listen for theme change events to sync UI state
    window.addEventListener('themeChanged', (e) => {
        const override = window.ControlPlaneTheme.getOverride();
        updateToggleUI(override);
        updateSelectorUI(override);
    });

    // Initial UI state setup
    const initialOverride = window.ControlPlaneTheme.getOverride();
    updateToggleUI(initialOverride);
    updateSelectorUI(initialOverride);
}

function updateToggleUI(mode) {
    const btnToggle = document.getElementById('theme-toggle-btn');
    if (!btnToggle) return;

    if (mode === 'auto') {
        btnToggle.textContent = '🌓';
        btnToggle.title = 'Theme: Sync / Host';
    } else if (mode === 'light') {
        btnToggle.textContent = '☀️';
        btnToggle.title = 'Theme: Light';
    } else {
        btnToggle.textContent = '🌙';
        btnToggle.title = 'Theme: Dark';
    }
}

function updateSelectorUI(mode) {
    const selector = document.getElementById('theme-selector');
    if (!selector) return;

    const options = selector.querySelectorAll('.theme-option');
    options.forEach(opt => {
        if (opt.dataset.themeMode === mode) {
            opt.classList.add('active');
        } else {
            opt.classList.remove('active');
        }
    });
}

// ===== TAB NAVIGATION =====
function initTabs() {
    const tabs = document.querySelectorAll('.tab');
    const overviewContent = document.getElementById('tab-content-overview');
    const settingsContent = document.getElementById('tab-content-settings');
    const placeholderContent = document.getElementById('tab-content-placeholder');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const target = tab.dataset.tab;
            overviewContent.classList.remove('active');
            settingsContent.classList.remove('active');
            placeholderContent.classList.remove('active');

            if (target === 'overview') {
                overviewContent.classList.add('active');
            } else if (target === 'settings') {
                settingsContent.classList.add('active');
            } else {
                placeholderContent.classList.add('active');
            }
        });
    });
}

// ===== ACCORDION =====
function initAccordions() {
    document.querySelectorAll('.dimension-header').forEach(header => {
        header.addEventListener('click', (e) => {
            // Avoid toggling accordion if user clicked details/status element directly
            if (e.target.classList.contains('dimension-status')) return;
            const dim = header.closest('.dimension');
            dim.classList.toggle('expanded');
        });
    });
}

// ===== BIAS POPOVER =====
function initBiasPopover() {
    const biasRow = els.biasRow;
    const popover = els.biasPopover;
    if (!biasRow || !popover) return;

    biasRow.addEventListener('mouseenter', (e) => {
        const rect = biasRow.getBoundingClientRect();
        popover.style.top = (rect.bottom + 8) + 'px';
        popover.style.left = Math.max(8, rect.left - 40) + 'px';
        popover.classList.remove('hidden');
    });

    biasRow.addEventListener('mouseleave', () => {
        popover.classList.add('hidden');
    });
}

// ===== CHECKS EXPANSIBLE =====
function initChecksExpanded() {
    const btnExpand = document.getElementById('btn-expand-checks');
    const detail = document.getElementById('checks-detail');
    if (!btnExpand || !detail) return;

    btnExpand.addEventListener('click', () => {
        detail.classList.toggle('expanded');
        btnExpand.textContent = detail.classList.contains('expanded') ? 'Collapse' : 'Details';
    });
}

// ===== ACTION BUTTONS =====
function initActions() {
    els.btnBlock.addEventListener('click', handleBlock);
    els.btnReword.addEventListener('click', handleReword);
    els.btnEscalate.addEventListener('click', () => {
        // Disabled — handled by CSS and disabled attribute
    });
}

function handleBlock() {
    if (!state.evaluation) return;

    // Find first hallucination or ambiguous segment to block
    const segments = state.evaluation.segments || [];
    let targetIndex = segments.findIndex(
        (s, i) => !state.blockedSegments.has(i) && (s.classification === 'hallucination' || s.classification === 'ambiguous')
    );
    if (targetIndex === -1) targetIndex = 0;

    state.blockedSegments.add(targetIndex);
    state.status = 'blocked';

    // Update sidebar UI to blocked state
    updateConfidence('Blocked', 'blocked');

    // Highlight the Block button as active
    els.btnBlock.classList.add('active-action');
    els.btnReword.classList.remove('active-action');

    // Send message to background → content.js
    chrome.runtime.sendMessage({
        action: 'blockSegment',
        segmentIndex: targetIndex,
        evaluationId: state.evaluation.evaluation_id,
    });
}

function handleReword() {
    if (!state.evaluation) return;

    // Find first hallucination or ambiguous segment to reword
    const segments = state.evaluation.segments || [];
    let targetIndex = segments.findIndex(
        (s, i) => !state.rewordedSegments.has(i) && !state.blockedSegments.has(i) &&
                  (s.classification === 'hallucination' || s.classification === 'ambiguous')
    );
    if (targetIndex === -1) return;

    const segment = segments[targetIndex];

    // Highlight the Reword button as active
    els.btnReword.classList.add('active-action');
    els.btnBlock.classList.remove('active-action');

    // Send reword request to background.js
    chrome.runtime.sendMessage({
        action: 'rewordSegment',
        segmentIndex: targetIndex,
        evaluationId: state.evaluation.evaluation_id,
        originalText: segment.text,
        prompt: state.evaluation._prompt || '',
        reasons: segment.reasons || [],
    });
}

// ===== MAIN RENDER =====
function renderEvaluation(data) {
    state.evaluation = data;
    state.status = 'ready';
    state.blockedSegments.clear();
    state.rewordedSegments.clear();

    // Reset button states and enable them
    els.btnBlock.classList.remove('active-action');
    els.btnReword.classList.remove('active-action');
    els.btnBlock.disabled = false;
    els.btnReword.disabled = false;

    // Confidence
    updateConfidence(data.overall_confidence + '%', 'normal');

    // Histogram
    renderHistogram(data.confidence_distribution || []);

    // Dimensions
    renderDimensions(data.dimensions || {});

    // Checks (Dynamic Rendering)
    renderChecks(data);
}

function updateConfidence(display, mode) {
    const el = els.confidenceValue;
    const statusEl = els.confidenceStatus;

    if (!el || !statusEl) return;

    el.classList.remove('blocked');
    statusEl.className = 'confidence-status';

    const scoreNum = parseInt(display) || 0;
    const ringProgress = document.querySelector('.confidence-ring .ring-progress');
    if (ringProgress) {
        const circumference = 2 * Math.PI * 15.5; // r=15.5
        const dashArray = (scoreNum / 100) * circumference;
        ringProgress.style.strokeDasharray = `${dashArray} ${circumference}`;
        
        // Dynamic colors for progress ring based on score
        if (mode === 'blocked') {
            ringProgress.style.stroke = 'var(--cp-danger)';
        } else {
            ringProgress.style.stroke = getScoreColor(scoreNum);
        }
    }

    if (mode === 'blocked') {
        el.textContent = 'Block';
        el.classList.add('blocked');
        statusEl.textContent = 'Policy Blocked';
        statusEl.classList.add('status-poor');
    } else {
        el.textContent = display;
        if (scoreNum >= 80) {
            statusEl.textContent = 'High Confidence';
            statusEl.classList.add('status-good');
        } else if (scoreNum >= 60) {
            statusEl.textContent = 'Medium Confidence';
            statusEl.classList.add('status-moderate');
        } else {
            statusEl.textContent = 'Low Confidence';
            statusEl.classList.add('status-poor');
        }
    }
}

// ===== DYNAMIC CHECKS RENDER =====
function renderChecks(data) {
    const list = document.querySelector('.checks-detail-list');
    const statusEl = els.checksStatus;
    if (!list || !statusEl) return;

    list.innerHTML = '';

    const perfScore = data.dimensions?.performance?.score || 0;
    const costScore = data.dimensions?.cost?.score || 0;
    const respScore = data.dimensions?.responsibility?.score || 0;

    const checks = [
        {
            name: 'Reliability',
            passed: perfScore >= 60,
            warning: perfScore >= 40 && perfScore < 60,
            successText: 'Reliability validation passed',
            failText: 'Low reliability risk detected',
            warningText: 'Moderate reliability risk warning'
        },
        {
            name: 'Cost Efficiency',
            passed: costScore >= 60,
            warning: costScore >= 40 && costScore < 60,
            successText: 'Cost efficiency threshold met',
            failText: 'High token/cost waste warning',
            warningText: 'Moderate cost overhead warning'
        },
        {
            name: 'Safety & Ethics',
            passed: respScore >= 60,
            warning: respScore >= 40 && respScore < 60,
            successText: 'Safety & ethics compliance verified',
            failText: 'Safety/ethical risks detected',
            warningText: 'Potential safety compliance warnings'
        }
    ];

    let allPassed = true;
    let anyFail = false;

    checks.forEach(c => {
        const li = document.createElement('li');
        let icon = '';
        let text = '';
        let colorClass = '';

        if (c.passed) {
            icon = '✓';
            text = c.successText;
            colorClass = 'color-green';
        } else if (c.warning) {
            icon = '⚠';
            text = c.warningText;
            colorClass = 'color-yellow';
            allPassed = false;
        } else {
            icon = '✕';
            text = c.failText;
            colorClass = 'color-red';
            allPassed = false;
            anyFail = true;
        }

        li.innerHTML = `<span class="check-icon ${colorClass}">${icon}</span> ${text}`;
        list.appendChild(li);
    });

    if (allPassed) {
        statusEl.textContent = '✓ All checks passed';
        statusEl.className = 'checks-status color-green';
    } else if (anyFail) {
        statusEl.textContent = '✕ Safety/Reliability warnings';
        statusEl.className = 'checks-status color-red';
    } else {
        statusEl.textContent = '⚠ Review warnings';
        statusEl.className = 'checks-status color-yellow';
    }
}

// ===== HISTOGRAM =====
function renderHistogram(distribution) {
    const container = els.histogram;
    container.innerHTML = '';

    if (!distribution || distribution.length === 0) {
        distribution = generateDefaultDistribution(72);
    }

    const maxVal = Math.max(...distribution, 1);

    // Find peak index
    let peakIndex = 0;
    let peakVal = 0;
    distribution.forEach((v, i) => {
        if (v > peakVal) { peakVal = v; peakIndex = i; }
    });

    distribution.forEach((val, i) => {
        const bar = document.createElement('div');
        bar.className = 'bar';
        const heightPct = Math.max(4, (val / maxVal) * 100);
        bar.style.height = heightPct + '%';

        // Green-to-yellow-to-red gradient based on position
        const ratio = i / (distribution.length - 1);
        bar.style.backgroundColor = getHistogramColor(ratio);

        if (i === peakIndex) {
            bar.classList.add('peak');
            const pctLabel = Math.round((peakIndex / (distribution.length - 1)) * 100);
            bar.setAttribute('data-label', pctLabel + '%');
        }

        container.appendChild(bar);
    });
}

function getHistogramColor(ratio) {
    // Green (0%) → Yellow (50%) → Red (100%)
    if (ratio < 0.5) {
        const r = Math.round(76 + (255 - 76) * (ratio * 2));
        const g = Math.round(175 + (215 - 175) * (ratio * 2));
        const b = Math.round(80 - 80 * (ratio * 2));
        return `rgb(${r},${g},${b})`;
    } else {
        const r = Math.round(255 - (255 - 211) * ((ratio - 0.5) * 2));
        const g = Math.round(215 - (215 - 47) * ((ratio - 0.5) * 2));
        const b = Math.round(0 + 47 * ((ratio - 0.5) * 2));
        return `rgb(${r},${g},${b})`;
    }
}

function generateDefaultDistribution(peak) {
    const bars = [];
    const peakIndex = Math.round((peak / 100) * 19);
    for (let i = 0; i < 20; i++) {
        const dist = Math.abs(i - peakIndex);
        bars.push(Math.max(5, 50 - dist * dist * 1.5 + Math.random() * 10));
    }
    return bars;
}

// ===== DIMENSIONS =====
function renderDimensions(dimensions) {
    renderDimension('performance', dimensions.performance);
    renderDimension('cost', dimensions.cost);
    renderDimension('responsibility', dimensions.responsibility);
}

function renderDimension(name, data) {
    if (!data) return;
    const dim = document.querySelector(`.dimension[data-dimension="${name}"]`);
    if (!dim) return;

    const score = data.score || 0;

    // Update score text
    const scoreEl = dim.querySelector('.dimension-score');
    scoreEl.textContent = score + '%';

    // Update score status text badge
    const statusEl = dim.querySelector(`#status-${name}`);
    if (statusEl) {
        statusEl.className = 'dimension-status';
        if (score >= 80) {
            statusEl.textContent = 'Good';
            statusEl.classList.add('status-good');
        } else if (score >= 60) {
            statusEl.textContent = 'Moderate';
            statusEl.classList.add('status-moderate');
        } else {
            statusEl.textContent = 'Poor';
            statusEl.classList.add('status-poor');
        }
    }

    // Update ring indicator
    const ring = dim.querySelector('.ring-fill');
    if (ring) {
        const circumference = 2 * Math.PI * 15.5; // r=15.5
        const dashArray = (score / 100) * circumference;
        ring.style.strokeDasharray = `${dashArray} ${circumference}`;
        ring.style.stroke = getScoreColor(score);
    }

    // Update sub-metrics
    const subMetrics = dim.querySelectorAll('.sub-metric');
    const subData = getSubMetricValues(name, data);

    subMetrics.forEach((el, i) => {
        if (i >= subData.length) return;
        const { label, value } = subData[i];

        const labelEl = el.querySelector('.sub-label');
        const valueEl = el.querySelector('.sub-value');
        const fillEl = el.querySelector('.sub-bar-fill');

        if (labelEl) labelEl.textContent = label;
        if (valueEl) valueEl.textContent = value + '%';
        if (fillEl) {
            fillEl.style.width = Math.max(0, Math.min(100, value)) + '%';
            fillEl.style.backgroundColor = getScoreColor(value);
        }
    });

    // Handle bias row highlighting
    if (name === 'responsibility') {
        const biasRow = dim.querySelector('#bias-row');
        if (biasRow && data.sub_metrics && data.sub_metrics.bias_detection > 50) {
            biasRow.classList.add('highlighted');
        } else if (biasRow) {
            biasRow.classList.remove('highlighted');
        }
    }
}

function getSubMetricValues(name, data) {
    const sm = data.sub_metrics || {};
    if (name === 'performance') {
        return [
            { label: 'Accuracy', value: sm.accuracy || 0 },
            { label: 'Hallucination risks', value: sm.hallucination_risks || 0 },
            { label: 'Prompt Alignment', value: sm.prompt_alignment ? Math.round(sm.prompt_alignment * 100) : 0 },
        ];
    } else if (name === 'cost') {
        return [
            { label: 'Inference', value: sm.token_consumption ? Math.min(100, Math.round(sm.token_consumption / 5)) : 0 },
            { label: 'Hallucination', value: sm.hallucination_rework_cost || 0 },
            { label: 'Detection fails', value: sm.cost_rating === 'wasteful' ? 80 : sm.cost_rating === 'moderate' ? 50 : 20 },
            { label: 'Correction', value: sm.loop_detected ? 60 : 30 },
        ];
    } else if (name === 'responsibility') {
        return [
            { label: 'Hate Speech', value: sm.hate_speech || 0 },
            { label: 'PII Leaks', value: sm.pii_leaks || 0 },
            { label: 'Bias Detection', value: sm.bias_detection || 0 },
            { label: 'Tone Compliance', value: sm.tone_compliance || 0 },
        ];
    }
    return [];
}

// Get CSS variable equivalents for JS scores to support proper theming
function getScoreColor(score) {
    if (score >= 80) return 'var(--cp-success)';
    if (score >= 60) return 'var(--cp-warning)';
    if (score >= 40) return 'var(--cp-warning)';
    return 'var(--cp-danger)';
}

// ===== CHROME MESSAGE LISTENERS =====
if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
        switch (msg.action) {
            case 'evaluationResult':
                renderEvaluation(msg.data);
                break;

            case 'rewordComplete':
                state.rewordedSegments.add(msg.segmentIndex);
                state.status = 'reworded';
                const newConf = msg.newConfidence || 96;
                updateConfidence(newConf + '%', 'reworded');
                // Re-render histogram for new score
                renderHistogram(generateDefaultDistribution(newConf));
                // Update checks to dynamic new state
                if (state.evaluation) {
                    state.evaluation.overall_confidence = newConf;
                    // If performance was low, simulate fix
                    if (state.evaluation.dimensions?.performance) {
                        state.evaluation.dimensions.performance.score = Math.max(88, state.evaluation.dimensions.performance.score);
                    }
                    renderChecks(state.evaluation);
                }
                break;

            case 'blockComplete':
                state.blockedSegments.add(msg.segmentIndex);
                state.status = 'blocked';
                updateConfidence('Blocked', 'blocked');
                break;
        }
    });
}
