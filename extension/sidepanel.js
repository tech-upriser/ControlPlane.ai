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
    confidenceSublabel: document.getElementById('confidence-sublabel'),
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

    // Reset UI to empty state waiting for evaluation
    updateConfidence('--%', 'normal');
    renderHistogram([]);
    renderDimensions({
        performance: { score: 0 },
        cost: { score: 0 },
        responsibility: { score: 0 }
    });

    // Request cached evaluation from background.js
    // This handles the case where the side panel opens AFTER evaluation completed
    if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({ action: 'getLatestEvaluation' }, (response) => {
            if (chrome.runtime.lastError) return;
            if (response && response.ok && response.data) {
                renderEvaluation(response.data);
            }
        });
    }
});

// ===== TAB NAVIGATION =====
function initTabs() {
    const tabs = document.querySelectorAll('.tab');
    const overviewContent = document.getElementById('tab-content-overview');
    const placeholderContent = document.getElementById('tab-content-placeholder');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            if (tab.dataset.tab === 'overview') {
                overviewContent.classList.add('active');
                placeholderContent.classList.remove('active');
            } else {
                overviewContent.classList.remove('active');
                placeholderContent.classList.add('active');
            }
        });
    });
}

// ===== ACCORDION =====
function initAccordions() {
    document.querySelectorAll('.dimension-header').forEach(header => {
        header.addEventListener('click', () => {
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

// ===== ACTION BUTTONS =====
function initActions() {
    els.btnBlock.addEventListener('click', handleBlock);
    els.btnReword.addEventListener('click', handleReword);
    els.btnEscalate.addEventListener('click', () => {
        // Disabled — show tooltip only
    });
}

function handleBlock() {
    if (!state.evaluation) return;

    // Find first hallucination or ambiguous segment to block
    const segments = state.evaluation.segments || [];
    let targetIndex = segments.findIndex(
        (s, i) => !state.blockedSegments.has(i) && (s.classification === 'hallucination' || s.classification === 'ambiguous')
    );
    if (targetIndex === -1) return;

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

    // Determine if there are actionable segments
    const hasIssues = (data.segments || []).some(s => s.classification === 'hallucination' || s.classification === 'ambiguous');

    // Update button states
    els.btnBlock.classList.remove('active-action');
    els.btnReword.classList.remove('active-action');
    
    if (!hasIssues) {
        els.btnBlock.style.opacity = '0.5';
        els.btnBlock.style.cursor = 'not-allowed';
        els.btnReword.style.opacity = '0.5';
        els.btnReword.style.cursor = 'not-allowed';
    } else {
        els.btnBlock.style.opacity = '1';
        els.btnBlock.style.cursor = 'pointer';
        els.btnReword.style.opacity = '1';
        els.btnReword.style.cursor = 'pointer';
    }

    // Confidence
    updateConfidence(data.overall_confidence + '%', 'normal');

    // Histogram
    renderHistogram(data.confidence_distribution || []);

    // Dimensions
    renderDimensions(data.dimensions || {});
}

function updateConfidence(display, mode) {
    const el = els.confidenceValue;
    const sub = els.confidenceSublabel;

    el.classList.remove('blocked');
    sub.classList.remove('blocked');

    if (mode === 'blocked') {
        el.textContent = display;
        el.classList.add('blocked');
        sub.textContent = 'Blocked';
        sub.classList.add('blocked');
    } else {
        el.textContent = display;
        el.style.color = '#4CAF50';
        sub.textContent = mode === 'reworded' ? 'Confidence' : 'Overall';
        sub.classList.remove('blocked');
    }
}

// ===== HISTOGRAM =====
function renderHistogram(distribution) {
    const container = els.histogram;
    container.innerHTML = '';

    if (!distribution || distribution.length === 0) {
        // Generate default distribution
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
    scoreEl.style.color = getScoreColor(score);

    // Update ring indicator
    const ring = dim.querySelector('.ring-fill');
    const circumference = 2 * Math.PI * 15.5; // r=15.5
    const dashArray = (score / 100) * circumference;
    ring.style.strokeDasharray = `${dashArray} ${circumference}`;
    ring.style.stroke = getScoreColor(score);

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

function getScoreColor(score) {
    if (score >= 80) return '#4CAF50';
    if (score >= 60) return '#FFD700';
    if (score >= 40) return '#FF9800';
    return '#D32F2F';
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
                break;

            case 'blockComplete':
                state.blockedSegments.add(msg.segmentIndex);
                state.status = 'blocked';
                updateConfidence('Blocked', 'blocked');
                break;
        }
    });
}

// ===== DEMO DATA (default when no backend) =====
function getDemoData() {
    return {
        evaluation_id: 'demo-001',
        overall_confidence: 72,
        risk_level: 'medium',
        recommended_action: 'flag',
        dimensions: {
            performance: {
                score: 60,
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
        segments: [
            {
                text: 'The adoption of AI in supply chain management is driven by several key factors.',
                classification: 'verified',
                confidence: 91,
                badge: 'High Confidence',
                reasons: [],
            },
            {
                text: 'Second, It helps optimize inventory levels and reduce operational costs across the supply chain.',
                classification: 'ambiguous',
                confidence: 58,
                badge: 'High Cost / Rework?',
                reasons: ['Medium hallucination risk', 'Contains hedging patterns'],
            },
            {
                text: 'Additionally, some experimental AI models are being developed to perfectly synchronize global logistics.',
                classification: 'hallucination',
                confidence: 22,
                badge: 'Hallucination Detected',
                reasons: ['High hallucination risk', 'Fabricated claims'],
            },
            {
                text: 'Finally, AI improves supplier collaboration and enhances decision-making speed.',
                classification: 'verified',
                confidence: 88,
                badge: 'High Confidence',
                reasons: [],
            },
        ],
        confidence_distribution: [5, 8, 12, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 72, 68, 55, 40, 30],
    };
}
