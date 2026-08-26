chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'sendPrompt') {
    handlePromptStream(message.prompt, sender.tab.id);
  }
});

async function handlePromptStream(prompt, tabId) {
  try {
    const response = await fetch('http://localhost:8000/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: "gpt-4",
        messages: [{ role: "user", content: prompt }],
        stream: true
      })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n').filter(line => line.trim() !== '');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.substring(6);
          if (dataStr === '[DONE]') break;
          
          try {
            const data = JSON.parse(dataStr);
            
            // Broadcast to content.js
            chrome.tabs.sendMessage(tabId, {
              action: 'streamChunk',
              chunk: data
            });

            // Broadcast to side panel
            chrome.runtime.sendMessage({
              action: 'streamMetadata',
              metadata: data.metadata || {}
            });
          } catch (e) {
            console.error("Error parsing chunk", e);
          }
        }
      }
    }
  } catch (error) {
    console.error("Fetch error:", error);
  }
}
