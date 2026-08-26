document.addEventListener('DOMContentLoaded', () => {
    // Listen for messages from the background script to update UI
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.action === 'updateMetrics') {
            const data = message.data;
            if (data.overallConfidence) {
                document.querySelector('.confidence-value').textContent = data.overallConfidence + '%';
                document.querySelector('.overview .progress').style.width = data.overallConfidence + '%';
            }
            // Add other metrics as needed
        }
    });

    // Helper to send message to the active tab
    function sendActionToTab(action) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs[0]) {
                chrome.tabs.sendMessage(tabs[0].id, { action: action }, (response) => {
                    console.log(`${action} action sent to tab.`);
                });
            }
        });
    }

    // Button event listeners
    document.getElementById('btn-block').addEventListener('click', () => {
        sendActionToTab('blockParagraph');
    });

    document.getElementById('btn-reward').addEventListener('click', () => {
        sendActionToTab('rewardParagraph');
    });

    document.getElementById('btn-escalate').addEventListener('click', () => {
        sendActionToTab('escalateParagraph');
    });
});
