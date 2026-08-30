# ControlPlane.ai

The ControlPlane.ai project is an Enterprise AI Guardrail Middleware. It acts as a real-time responsible AI checker layer that evaluates AI responses and flags or blocks bias, hallucination risks, or privacy leaks before they reach the user. Operating via a Chrome Extension (middleware) that intercepts ChatGPT/Claude/Gemini traffic in real-time, it pairs with a FastAPI backend acting as the policy engine and risk evaluator. It features a two-tier hybrid engine: Tier 1 heuristics (PII scanning, Content Safety, Injection detection) for fast validation, and Tier 2 Gemini "LLM-as-a-Judge" for semantic hallucination checking. It also includes a Reword Engine for dynamically improving low-confidence paragraphs.

## Table of contents

- Requirements
- Recommended modules
- Installation
- Configuration
- Troubleshooting
- FAQ
- Maintainers

## Requirements

This project requires the following:
- Python 3.9+
- Google Chrome (to install the middleware extension)
- A valid Gemini API Key for the Tier 2 Judge

## Recommended modules

This project requires no modules outside of the Python ecosystem and Chrome extensions APIs.

## Installation

### Backend Setup
1. Clone the repository to your local machine.
2. Ensure you have Python installed.
3. Install the required Python packages using pip:
   `pip install -r requirements.txt`

### Extension Setup
1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Enable "Developer mode" using the toggle in the top right corner.
3. Click "Load unpacked" and select the `extension/` folder from this repository.

## Configuration

1. Create a `.env` file in the root of the project directory.
2. Add your Gemini API Key to the `.env` file:
   `GEMINI_API_KEY=your_gemini_api_key_here`
   `GEMINI_MODEL=gemini-3.6-flash`
3. Review and customize the policy profiles located in the `config/profiles/` directory (e.g., `default.yaml`, `customer_support.yaml`, `internal_analyst.yaml`) to adjust latency budgets, strictness, and actions per use case.
4. Start the FastAPI backend server:
   `python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

## Troubleshooting

- **Backend Offline Error in Extension**: Ensure that the FastAPI backend is running on `http://localhost:8000`. If it is running and the error persists, try hard refreshing the page (`Cmd + Shift + R`) or reloading the extension in `chrome://extensions/`.
- **Gemini Judge Fails / No Reword Action**: Verify that your `.env` file contains a valid `GEMINI_API_KEY` and the `google-genai` package is installed (`pip install -r requirements.txt`).

## FAQ

**Q: How does the system avoid blocking legitimate AI responses?**
**A:** ControlPlane.ai uses a Segment Analyzer that highlights specific problematic paragraphs inline (Green/Yellow/Red) rather than blocking the entire response, minimizing alert fatigue.

**Q: How is latency managed?**
**A:** The system utilizes a Two-Tier Architecture. Tier 1 (heuristics) runs extremely fast to block catastrophic failures, while Tier 2 (Gemini Judge) handles complex checks.

## Maintainers

- tech-upriser
