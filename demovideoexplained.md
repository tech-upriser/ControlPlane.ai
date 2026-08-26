# In-Depth Summary of AIC_Demo Video

This document provides a detailed breakdown of the events and features demonstrated in the `AIC_Demo Video.mp4`. The video showcases the installation and functionality of the **ControlPlane.ai** Chrome extension, specifically its real-time analysis and moderation of AI-generated responses in ChatGPT.

## 1. Extension Installation (00:00 - 00:09)
* The video begins with the user opening Google Chrome and searching for "google chrome extensions".
* The user navigates to the Chrome Web Store and searches for "ControlPlane.ai".
* The user selects the ControlPlane.ai extension and clicks "Add to Chrome" to install it.

## 2. Interacting with ChatGPT (00:10 - 00:13)
* The user opens ChatGPT and submits the following prompt: *"What are the key factors driving the adoption of AI in supply chain management?"*
* As ChatGPT generates the response, the ControlPlane.ai extension actively monitors the output.

## 3. Real-Time Text Analysis and Highlighting (00:14 - 00:22)
* Once the response is generated, ControlPlane.ai overlays its analysis directly onto the chat interface. Different sections of the text are highlighted based on the extension's evaluation:
    * **Green Highlight:** Labeled "High Confidence", indicating reliable information.
    * **Orange Highlight:** Labeled "High Cost / Rework?", suggesting potential inefficiencies or questionable claims.
    * **Red Highlight:** Labeled "Hallucination Detected", warning the user of fabricated or inaccurate information.
* A floating indicator displays an overall "ControlPlane Confidence" score (initially 72%) and provides a "Deep Dive" button for more information.

## 4. Deep Dive Metrics and Insights (00:23 - 00:29)
* The user clicks the "Deep Dive" button, which opens a comprehensive side panel detailing the analysis metrics.
* The panel categorizes the evaluation into three main dimensions:
    * **Performance (Reliability):** Tracks Accuracy and Hallucination Risks.
    * **Cost (Efficiency):** Monitors resource and operational efficiency.
    * **Responsibility (Safety & Ethics):** Evaluates Hate Speech, Toxicity, Bias Detection, and Control Deviation.
* The user hovers over the "Bias Detection" metric, revealing specific warnings related to Gender Bias and Political Neutrality.

## 5. Actionable Feedback: Reward and Block (00:30 - 00:48)
* The Deep Dive panel provides actions at the bottom: "Block", "Reward", and "Escalate".
* **Rewarding:** The user clicks the "Reward" button on a selected response. This action provides positive reinforcement, and the overall confidence score visibly increases (e.g., to 96%).
* **Blocking:** In another instance where text is flagged with high hallucination risk, the user clicks the "Block" button. This action actively censors the output, replacing the flagged paragraph with a red "Blocked" indicator, preventing the user from utilizing the problematic text.

## Conclusion
The video effectively demonstrates how ControlPlane.ai acts as a protective and analytical layer over LLM interactions, offering real-time visibility into AI reliability, highlighting hallucinations, surfacing ethical biases, and allowing users to actively moderate and reinforce AI behavior.
