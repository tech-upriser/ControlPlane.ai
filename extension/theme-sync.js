/**
 * ControlPlane.ai — Theme Synchronization Engine
 * ═══════════════════════════════════════════════
 * Detects the host website's active theme (ChatGPT, Gemini, Claude)
 * and synchronizes ControlPlane's UI to match.
 *
 * Used by both sidepanel.js (side panel context) and content.js (host page context).
 *
 * Features:
 *  - Auto-detects host theme from DOM classes/attributes
 *  - MutationObserver for instant sync on host theme toggle
 *  - Manual override (light / dark / auto) persisted to chrome.storage.local
 *  - Broadcasts 'themeChanged' message for cross-context sync
 *  - Falls back to prefers-color-scheme if host detection fails
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'cp_theme_override';

  // ═══════════════════════════════════════════
  // Host Theme Detection Strategies
  // ═══════════════════════════════════════════

  /**
   * ChatGPT: Uses <html class="dark"> or <html class="light">
   * Also checks data-theme and color-scheme attributes.
   */
  function detectChatGPTTheme() {
    const html = document.documentElement;
    if (html.classList.contains('dark')) return 'dark';
    if (html.classList.contains('light')) return 'light';
    if (html.dataset.theme === 'dark') return 'dark';
    if (html.dataset.theme === 'light') return 'light';
    // ChatGPT also uses style attribute with color-scheme
    const cs = html.style.colorScheme || getComputedStyle(html).colorScheme;
    if (cs === 'dark') return 'dark';
    if (cs === 'light') return 'light';
    return null;
  }

  /**
   * Gemini: Uses <html data-dark-theme>, <body class="dark-theme">,
   * or <html data-theme="dark">. Also checks body background luminance.
   */
  function detectGeminiTheme() {
    const html = document.documentElement;
    const body = document.body;
    if (html.hasAttribute('data-dark-theme')) return 'dark';
    if (html.dataset.theme === 'dark') return 'dark';
    if (html.dataset.theme === 'light') return 'light';
    if (body) {
      if (body.classList.contains('dark-theme') || body.classList.contains('dark')) return 'dark';
      if (body.classList.contains('light-theme') || body.classList.contains('light')) return 'light';
      // Check body data attributes
      if (body.dataset.theme === 'dark') return 'dark';
      if (body.dataset.theme === 'light') return 'light';
    }
    // Check color-scheme meta tag
    const meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) {
      const val = meta.content.trim().toLowerCase();
      if (val === 'dark') return 'dark';
      if (val === 'light') return 'light';
    }
    return null;
  }

  /**
   * Claude: Uses <html data-theme="dark"> or body classes.
   */
  function detectClaudeTheme() {
    const html = document.documentElement;
    if (html.dataset.theme === 'dark') return 'dark';
    if (html.dataset.theme === 'light') return 'light';
    if (html.classList.contains('dark')) return 'dark';
    if (html.classList.contains('light')) return 'light';
    return null;
  }

  /**
   * Generic fallback: Checks common theme indicators on any page.
   */
  function detectGenericTheme() {
    const html = document.documentElement;
    const body = document.body;

    // data-theme on html or body
    for (const el of [html, body]) {
      if (!el) continue;
      const dt = el.dataset.theme || el.getAttribute('data-color-scheme');
      if (dt === 'dark') return 'dark';
      if (dt === 'light') return 'light';
    }

    // Class-based
    for (const el of [html, body]) {
      if (!el) continue;
      if (el.classList.contains('dark') || el.classList.contains('dark-mode') || el.classList.contains('dark-theme')) return 'dark';
      if (el.classList.contains('light') || el.classList.contains('light-mode') || el.classList.contains('light-theme')) return 'light';
    }

    // color-scheme property
    const cs = getComputedStyle(html).colorScheme;
    if (cs && cs !== 'normal') {
      if (cs.includes('dark') && !cs.includes('light')) return 'dark';
      if (cs.includes('light') && !cs.includes('dark')) return 'light';
    }

    return null;
  }

  /**
   * System preference fallback via prefers-color-scheme.
   */
  function getSystemTheme() {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  // ═══════════════════════════════════════════
  // Detect host theme using platform-specific logic
  // ═══════════════════════════════════════════

  function detectHostTheme() {
    const url = window.location.href;

    let detected = null;

    if (url.includes('chatgpt.com')) {
      detected = detectChatGPTTheme();
    } else if (url.includes('gemini.google.com')) {
      detected = detectGeminiTheme();
    } else if (url.includes('claude.ai')) {
      detected = detectClaudeTheme();
    }

    if (!detected) {
      detected = detectGenericTheme();
    }

    if (!detected) {
      detected = getSystemTheme();
    }

    return detected;
  }

  // ═══════════════════════════════════════════
  // Apply theme to a document
  // ═══════════════════════════════════════════

  // ═══════════════════════════════════════════
  // Apply theme to a document
  // ═══════════════════════════════════════════

  function applyTheme(theme, targetDoc) {
    const doc = targetDoc || document;
    const root = doc.documentElement;
    
    // Check if we are running in the context of the host webpage (content script)
    const isContentScript = typeof chrome !== 'undefined' && 
                            chrome.runtime && 
                            chrome.runtime.getURL &&
                            !window.location.href.startsWith('chrome-extension://');

    if (isContentScript) {
      root.setAttribute('data-cp-theme', theme);
      if (chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({ cp_host_theme: theme }).catch(() => {});
      }
    } else {
      root.setAttribute('data-theme', theme);
    }
  }

  // ═══════════════════════════════════════════
  // Storage helpers
  // ═══════════════════════════════════════════

  function getStoredOverride(callback) {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get([STORAGE_KEY], (result) => {
        callback(result[STORAGE_KEY] || 'auto');
      });
    } else {
      // Fallback for non-extension contexts
      try {
        callback(localStorage.getItem(STORAGE_KEY) || 'auto');
      } catch (e) {
        callback('auto');
      }
    }
  }

  function setStoredOverride(value) {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.set({ [STORAGE_KEY]: value });
    } else {
      try {
        localStorage.setItem(STORAGE_KEY, value);
      } catch (e) { /* ignore */ }
    }
  }

  // ═══════════════════════════════════════════
  // Resolve effective theme
  // ═══════════════════════════════════════════

  function resolveTheme(override) {
    if (override === 'light' || override === 'dark') {
      return override;
    }
    // 'auto' — detect from host
    return detectHostTheme();
  }

  // ═══════════════════════════════════════════
  // MutationObserver — watch host page for theme changes
  // ═══════════════════════════════════════════

  let _observer = null;
  let _currentOverride = 'auto';
  let _lastApplied = null;

  function startObserving(targetDoc) {
    if (_observer) return;

    const html = document.documentElement;
    const body = document.body;

    const check = () => {
      if (_currentOverride !== 'auto') return; // Manual override active
      const detected = detectHostTheme();
      if (detected !== _lastApplied) {
        _lastApplied = detected;
        applyTheme(detected, targetDoc);
        broadcastThemeChange(detected);
      }
    };

    _observer = new MutationObserver(check);

    // Observe <html> for class and attribute changes
    _observer.observe(html, {
      attributes: true,
      attributeFilter: ['class', 'data-theme', 'data-dark-theme', 'data-color-scheme', 'style'],
    });

    // Observe <body> if it exists
    if (body) {
      _observer.observe(body, {
        attributes: true,
        attributeFilter: ['class', 'data-theme', 'data-dark-theme', 'data-color-scheme'],
      });
    }

    // Also listen for system preference changes
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', check);
    }
  }

  function stopObserving() {
    if (_observer) {
      _observer.disconnect();
      _observer = null;
    }
  }

  // ═══════════════════════════════════════════
  // Broadcast theme change via Chrome messaging
  // ═══════════════════════════════════════════

  function broadcastThemeChange(theme) {
    if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
      chrome.runtime.sendMessage({ action: 'themeChanged', theme: theme }).catch(() => {});
    }
  }

  // ═══════════════════════════════════════════
  // Public API
  // ═══════════════════════════════════════════

  const ControlPlaneTheme = {
    /**
     * Initialize theme for the side panel.
     * The side panel doesn't have direct access to the host page DOM,
     * so it listens for themeChanged messages and stored override.
     */
    initSidePanel() {
      getStoredOverride((override) => {
        _currentOverride = override;
        if (override === 'auto') {
          // Side panel can't see host DOM. Fetch latest host theme from storage.
          if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
            chrome.storage.local.get(['cp_host_theme'], (res) => {
              const theme = res.cp_host_theme || getSystemTheme();
              applyTheme(theme);
              _lastApplied = theme;
              window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
            });
          } else {
            const theme = getSystemTheme();
            applyTheme(theme);
            _lastApplied = theme;
            window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
          }
        } else {
          applyTheme(override);
          _lastApplied = override;
          window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: override } }));
        }
      });

      // Listen for theme changes from content script
      if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
        chrome.runtime.onMessage.addListener((msg) => {
          if (msg.action === 'themeChanged' && _currentOverride === 'auto') {
            applyTheme(msg.theme);
            _lastApplied = msg.theme;
            window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: msg.theme } }));
          }
        });
      }
    },

    /**
     * Initialize theme for the content script (runs on host page).
     * Detects host theme and starts observing for changes.
     */
    initContentScript() {
      getStoredOverride((override) => {
        _currentOverride = override;
        const theme = resolveTheme(override);
        _lastApplied = theme;
        applyTheme(theme);
        broadcastThemeChange(theme);
      });

      // Start observing for host theme changes
      startObserving();
    },

    /**
     * Set manual theme override.
     * @param {'auto' | 'light' | 'dark'} mode
     */
    setOverride(mode) {
      _currentOverride = mode;
      setStoredOverride(mode);
      if (mode === 'auto') {
        if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
          chrome.storage.local.get(['cp_host_theme'], (res) => {
            const theme = res.cp_host_theme || getSystemTheme();
            _lastApplied = theme;
            applyTheme(theme);
            broadcastThemeChange(theme);
            window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
          });
        } else {
          const theme = getSystemTheme();
          _lastApplied = theme;
          applyTheme(theme);
          broadcastThemeChange(theme);
          window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
        }
      } else {
        _lastApplied = mode;
        applyTheme(mode);
        broadcastThemeChange(mode);
        window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: mode } }));
      }
    },

    /**
     * Get the current override setting.
     * @returns {'auto' | 'light' | 'dark'}
     */
    getOverride() {
      return _currentOverride;
    },

    /**
     * Get the currently applied theme.
     * @returns {'light' | 'dark'}
     */
    getCurrentTheme() {
      return _lastApplied || getSystemTheme();
    },

    /**
     * Cycle through override modes: auto → light → dark → auto
     * @returns {string} The new override mode
     */
    cycleOverride() {
      const cycle = { auto: 'light', light: 'dark', dark: 'auto' };
      const next = cycle[_currentOverride] || 'auto';
      this.setOverride(next);
      return next;
    },

    // Expose for external use
    detectHostTheme,
    getSystemTheme,
  };

  // Listen for storage changes to sync override settings instantly across contexts
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.onChanged) {
    chrome.storage.onChanged.addListener((changes, areaName) => {
      if (areaName === 'local' && changes[STORAGE_KEY]) {
        const newOverride = changes[STORAGE_KEY].newValue || 'auto';
        _currentOverride = newOverride;
        const theme = resolveTheme(newOverride);
        _lastApplied = theme;
        applyTheme(theme);
        
        // Notify side panel JS components via custom event
        if (typeof window !== 'undefined' && window.location.href.startsWith('chrome-extension://')) {
          window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
        }
      }
    });
  }

  // Expose globally
  window.ControlPlaneTheme = ControlPlaneTheme;
})();
