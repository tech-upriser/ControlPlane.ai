function injectConfidenceBar() {
  const containers = document.querySelectorAll('.agent-turn, [data-message-author-role="assistant"]'); // Target AI response blocks
  
  containers.forEach(container => {
    if (!container.hasAttribute('data-cp-injected')) {
      const bar = document.createElement('div');
      bar.className = 'cp-confidence-bar';
      
      const text = document.createElement('span');
      text.innerText = 'ControlPlane Confidence: 72%';
      
      const btn = document.createElement('button');
      btn.className = 'cp-deep-dive-btn';
      btn.innerText = 'Deep Dive';
      
      bar.appendChild(text);
      bar.appendChild(btn);
      
      container.insertBefore(bar, container.firstChild);
      container.setAttribute('data-cp-injected', 'true');
    }
  });
}

// Observe DOM for new AI responses
const observer = new MutationObserver((mutations) => {
  injectConfidenceBar();
});
observer.observe(document.body, { childList: true, subtree: true });

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'block') {
    transformToBlocked();
  } else if (message.action === 'streamChunk') {
    // Logic for streaming chunks can go here
  }
});

function transformToBlocked() {
  // Transform relevant paragraph into a blocked box
  const paragraphs = document.querySelectorAll('.cp-hallucination, .cp-high-cost');
  paragraphs.forEach(p => {
    p.className = 'cp-blocked-box';
    p.innerText = 'Blocked by ControlPlane.ai';
  });
}
