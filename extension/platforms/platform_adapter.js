/**
 * ControlPlane.ai — Platform Adapter Layer
 * ═══════════════════════════════════════════
 * Provides decoupled DOM selectors and text extraction logic for each
 * supported AI chat platform. The content script uses this abstraction
 * to operate without hardcoding any platform-specific selectors.
 *
 * Supported platforms:
 *   ✅ ChatGPT  (chatgpt.com)     — fully implemented
 *   🔧 Claude   (claude.ai)       — stub with documented selectors
 *   🔧 Gemini   (gemini.google.com) — stub with documented selectors
 *
 * Each adapter implements the PlatformAdapter interface:
 *   name              — platform identifier string
 *   matchUrl(url)     — returns true if URL belongs to this platform
 *   selectors         — CSS selector strings for key DOM elements
 *   extractResponseText(container)  — extracts AI response as plain text
 *   extractPromptText(container)    — finds the preceding user prompt
 *   getInsertionPoint(container)    — returns the element to insert the confidence bar before
 *   isStreaming()                   — checks if the AI is still generating
 *   getTextParagraphs(container)    — returns paragraph-level elements for inline highlighting
 */
(function () {
  'use strict';

  // ───────────────────────────────────────────────
  // ChatGPT Adapter (chatgpt.com)
  // ───────────────────────────────────────────────
  const chatgptAdapter = {
    name: 'chatgpt',

    matchUrl(url) {
      return url.includes('chatgpt.com');
    },

    selectors: {
      responseContainers: '[data-message-author-role="assistant"]',
      promptContainers: '[data-message-author-role="user"]',
      responseText: '.markdown',
      streamingIndicator: '.result-streaming',
      conversationTurn: 'article[data-testid^="conversation-turn"]',
      messageWrapper: '.group\\/conversation-turn',
    },

    extractResponseText(container) {
      const textEl = container.querySelector(this.selectors.responseText);
      if (textEl) return textEl.innerText.trim();
      return container.innerText.trim();
    },

    extractPromptText(responseContainer) {
      // Strategy 1: Navigate via conversation turn siblings
      const turn =
        responseContainer.closest(this.selectors.conversationTurn) ||
        responseContainer.closest(this.selectors.messageWrapper);
      if (turn) {
        let prev = turn.previousElementSibling;
        while (prev) {
          const userMsg = prev.querySelector(this.selectors.promptContainers);
          if (userMsg) return userMsg.innerText.trim();
          prev = prev.previousElementSibling;
        }
      }

      // Strategy 2: Index-based matching (user[i] → assistant[i])
      const allUser = document.querySelectorAll(this.selectors.promptContainers);
      const allAssistant = document.querySelectorAll(this.selectors.responseContainers);
      const respIndex = Array.from(allAssistant).indexOf(responseContainer);
      if (respIndex >= 0 && respIndex < allUser.length) {
        return allUser[respIndex]?.innerText?.trim() || '';
      }

      // Fallback: most recent user message
      if (allUser.length > 0) {
        return allUser[allUser.length - 1].innerText.trim();
      }
      return '';
    },

    getInsertionPoint(container) {
      return container.firstChild;
    },

    isStreaming() {
      return !!document.querySelector(this.selectors.streamingIndicator);
    },

    getTextParagraphs(container) {
      const textEl = container.querySelector(this.selectors.responseText);
      const root = textEl || container;
      // Collect block-level text elements with meaningful content
      return Array.from(
        root.querySelectorAll('p, li, pre, blockquote, h1, h2, h3, h4, h5, h6')
      ).filter((el) => {
        // Exclude our own injected elements
        if (el.closest('.cp-header-bar') || el.closest('.cp-badge')) return false;
        return el.innerText.trim().length > 15;
      });
    },
  };

  // ───────────────────────────────────────────────
  // Claude Adapter (claude.ai) — Stub
  // DOM structure may change; selectors are best-effort
  // ───────────────────────────────────────────────
  const claudeAdapter = {
    name: 'claude',

    matchUrl(url) {
      return url.includes('claude.ai');
    },

    selectors: {
      responseContainers: '[data-is-streaming], .font-claude-message, [data-testid="assistant-message"]',
      promptContainers: '.font-user-message, [data-testid="user-message"]',
      responseText: '.font-claude-message .grid-cols-1, .prose',
      streamingIndicator: '[data-is-streaming="true"]',
      conversationTurn: '[data-testid^="chat-message"]',
      messageWrapper: '.group',
    },

    extractResponseText(container) {
      const textEl = container.querySelector(this.selectors.responseText);
      if (textEl) return textEl.innerText.trim();
      return container.innerText.trim();
    },

    extractPromptText(_responseContainer) {
      const allUser = document.querySelectorAll(this.selectors.promptContainers);
      if (allUser.length > 0) {
        return allUser[allUser.length - 1].innerText.trim();
      }
      return '';
    },

    getInsertionPoint(container) {
      return container.firstChild;
    },

    isStreaming() {
      return !!document.querySelector(this.selectors.streamingIndicator);
    },

    getTextParagraphs(container) {
      const root = container.querySelector(this.selectors.responseText) || container;
      return Array.from(root.querySelectorAll('p, li, pre, blockquote')).filter(
        (el) => !el.closest('.cp-header-bar') && el.innerText.trim().length > 15
      );
    },
  };

  // ───────────────────────────────────────────────
  // Gemini Adapter (gemini.google.com) — Stub
  // DOM structure may change; selectors are best-effort
  // ───────────────────────────────────────────────
  const geminiAdapter = {
    name: 'gemini',

    matchUrl(url) {
      return url.includes('gemini.google.com');
    },

    selectors: {
      responseContainers: 'model-response message-content, .model-response-text, [data-content-type="model"]',
      promptContainers: 'user-query .query-text, .user-message-text, [data-content-type="user"]',
      responseText: '.markdown, .response-content',
      streamingIndicator: '.loading-indicator, .response-streaming',
      conversationTurn: '.conversation-turn',
      messageWrapper: '.chat-turn',
    },

    extractResponseText(container) {
      const textEl = container.querySelector(this.selectors.responseText);
      if (textEl) return textEl.innerText.trim();
      return container.innerText.trim();
    },

    extractPromptText(_responseContainer) {
      const allUser = document.querySelectorAll(this.selectors.promptContainers);
      if (allUser.length > 0) {
        return allUser[allUser.length - 1].innerText.trim();
      }
      return '';
    },

    getInsertionPoint(container) {
      return container.firstChild;
    },

    isStreaming() {
      return !!document.querySelector(this.selectors.streamingIndicator);
    },

    getTextParagraphs(container) {
      const root = container.querySelector(this.selectors.responseText) || container;
      return Array.from(root.querySelectorAll('p, li, pre, blockquote')).filter(
        (el) => !el.closest('.cp-header-bar') && el.innerText.trim().length > 15
      );
    },
  };

  // ───────────────────────────────────────────────
  // Platform Registry & Detection
  // ───────────────────────────────────────────────
  const adapters = [chatgptAdapter, claudeAdapter, geminiAdapter];

  function detectPlatform() {
    const url = window.location.href;
    for (const adapter of adapters) {
      if (adapter.matchUrl(url)) {
        console.log(`[ControlPlane] Platform detected: ${adapter.name}`);
        return adapter;
      }
    }
    console.warn('[ControlPlane] No supported platform detected for:', url);
    return null;
  }

  // Expose globally for content.js (MV3 content scripts share execution context)
  window.ControlPlanePlatform = {
    adapters,
    detectPlatform,
    current: null,
  };
})();
