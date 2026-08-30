# ControlPlane.ai

The ControlPlane.ai project is an **Enterprise AI Guardrail Middleware**. It acts as a real-time responsible AI checker layer that evaluates AI responses and flags or blocks bias, hallucination risks, or privacy leaks before they reach the user. 

Operating via a Chrome Extension (middleware) that intercepts ChatGPT, Claude, and Gemini traffic in real-time, it pairs with a FastAPI backend acting as the policy engine and risk evaluator. It features a **Two-Tier Hybrid Engine**: Tier 1 heuristics (PII scanning, Content Safety, Injection detection) for lightning-fast validation, and Tier 2 Gemini "LLM-as-a-Judge" for deep semantic hallucination checking. It also includes an intelligent **Reword Engine** for dynamically rewriting and improving low-confidence paragraphs on the fly.

## Table of contents

- Features & Architecture
- Requirements
- Installation
- Configuration
- Troubleshooting
- FAQ
- Future Enhancements
- Maintainers

## Features & Architecture

- **Two-Tier Engine**: Solves the latency vs. accuracy tradeoff. Fast regex/heuristics handle PII and safety in milliseconds, while a secondary LLM audits semantic claims asynchronously.
- **Dynamic Policy Engine**: Configurable YAML profiles (`default`, `customer_support`, `internal_analyst`) allow different use cases to have custom latency budgets, strictness thresholds, and action policies.
- **Granular Segment Analyzer**: Rather than blocking an entire chat, ControlPlane analyzes and highlights specific paragraphs inline (Green = Verified, Yellow = Ambiguous, Red = Hallucination), significantly reducing alert fatigue.
- **Telemetry & Deep Dive**: A comprehensive UI sidepanel providing visibility into Performance, Cost (Efficiency), and Responsibility metrics.

## Requirements

This project requires the following:
- **Python 3.9+** (For the FastAPI backend)
- **Google Chrome** (To install and run the middleware extension)
- **A valid Gemini API Key** (For the Tier 2 Semantic Judge and Reword engine)

## Installation

### Backend Setup
1. Clone the repository to your local machine:
   `git clone https://github.com/tech-upriser/ControlPlane.ai.git`
2. Navigate into the project directory:
   `cd ControlPlane.ai`
3. Install the required Python packages using pip:
   `pip install -r requirements.txt`

### Extension Setup
1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Enable **"Developer mode"** using the toggle in the top right corner.
3. Click **"Load unpacked"** and select the `extension/` folder located inside the cloned repository.

## Configuration

1. Create a `.env` file in the root of the project directory.
2. Add your Gemini API Key to the `.env` file:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-3.6-flash
   ```
3. **Customize Policies**: Review the policy profiles located in the `config/profiles/` directory. You can adjust values like `max_latency_budget_ms` and `hallucination_strictness` based on your mock use cases.
4. Start the FastAPI backend server:
   `python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

## Troubleshooting

- **Backend Offline Error in Extension**: Ensure that the FastAPI backend is running on `http://localhost:8000`. If it is running and the error persists, try hard refreshing the web page (`Ctrl + Shift + R` / `Ctrl + F5` on Windows/Linux, or `Cmd + Shift + R` on Mac) or reloading the extension in `chrome://extensions/`.
- **Segment Element Not Found**: Ensure you have loaded the latest extension code. The extension uses Word Overlap Intersection to map backend analysis to frontend DOM paragraphs resiliently.
- **Gemini Judge Fails / No Reword Action**: Verify that your `.env` file contains a valid `GEMINI_API_KEY` and the `google-genai` package is successfully installed (`pip install -r requirements.txt`).

## FAQ

**Q: How does the system avoid blocking legitimate AI responses?**
**A:** ControlPlane.ai utilizes precise DOM injection to highlight only the specific paragraphs that violate policies, rather than dropping the entire HTTP response. 

**Q: How is latency managed for real-time customer chatbots?**
**A:** The system utilizes a Two-Tier Architecture. Tier 1 (heuristics) runs extremely fast to block catastrophic failures immediately, while Tier 2 (Gemini Judge) handles complex checks.

**Q: Does it actually know if a fact is false?**
**A:** Currently, the system uses an LLM-as-a-Judge pattern relying on the model's pre-trained knowledge. (See Future Enhancements for RAG grounding).

## Future Enhancements
- **RAG Grounding**: Connecting the Gemini Judge to a Vector Database containing internal company policies so it verifies claims against reliable ground truth.
- **Feedback Loops**: Expanding the UI to allow users to report "False Positives" to continuously tune the system's precision and recall.

## Maintainers

- tech-upriser
