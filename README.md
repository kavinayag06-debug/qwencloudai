# QwenCloud AI - Website Redesign Agent

An AI-powered automation agent that discovers small brick-and-mortar businesses with weak websites, generates HTML landing page redesigns, and manages outreach emails with human-in-the-loop approval.

## Features

- **Discovery Pipeline** — Finds local businesses with poor web presence using Exa, Google Maps, and web directory search
- **Website Analysis** — Evaluates modernity, responsiveness, CTAs, trust signals, mobile-friendliness
- **Design Reference Analysis** — Scans your past design screenshots to extract style signals
- **HTML Generation** — Creates complete, responsive landing pages tailored to each business
- **Screenshot Rendering** — Uses Playwright to capture desktop/tablet/mobile screenshots of generated HTML
- **Email Drafting** — Generates professional outreach emails with approval gating
- **Confidence Scoring** — Transparent scoring with routing rules (high/medium/low)
- **Dashboard** — Lean web UI for reviewing leads, previewing designs, and approving sends
- **Provider Abstraction** — Switch between OpenAI, Qwen, OpenRouter, or mock by changing `.env` only

## Quick Start (Windows)

### 1. Clone and setup

```bash
git clone <your-repo-url>
cd qwencloudai

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### 2. Configure environment

```bash
copy .env.example .env
# Edit .env with your API keys (or leave as mock for testing)
```

### 3. Add design references (optional)

Place your past design screenshots (PNG, JPG, WebP) in:
```
data/design_screenshots/
```

### 4. Run the application

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open: http://127.0.0.1:8000

### 5. Run tests

```bash
pytest
```

## Project Structure

```
qwencloudai/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings from .env
│   ├── api/
│   │   └── routes.py        # REST API endpoints
│   ├── core/
│   │   ├── llm_provider.py  # Provider abstraction (OpenAI/Qwen/Mock)
│   │   ├── models.py        # Pydantic data models
│   │   ├── scoring.py       # Confidence scoring logic
│   │   └── prompts.py       # Provider-agnostic prompt templates
│   ├── connectors/
│   │   ├── base.py          # Connector interface
│   │   ├── mock_connector.py
│   │   ├── exa_connector.py
│   │   ├── google_maps_connector.py
│   │   └── web_directory_connector.py
│   ├── services/
│   │   ├── design_analyzer.py     # Style reference analysis
│   │   ├── discovery_service.py   # Discovery orchestration
│   │   ├── site_analyzer.py       # Website evaluation
│   │   ├── html_generator.py      # Landing page generation
│   │   ├── screenshot_renderer.py # Playwright screenshots
│   │   ├── zip_packager.py        # Zip packaging
│   │   └── email_service.py       # Email drafting & sending
│   ├── agents/
│   │   └── pipeline.py      # Full pipeline orchestration
│   ├── storage/
│   │   └── database.py      # SQLite persistence
│   ├── templates/            # Jinja2 HTML templates
│   ├── static/               # CSS/JS assets
│   └── ui/
│       └── dashboard.py      # Server-rendered dashboard routes
├── tests/
│   ├── test_provider.py
│   ├── test_scoring.py
│   ├── test_discovery.py
│   ├── test_html_generation.py
│   ├── test_approval.py
│   ├── test_file_handling.py
│   ├── test_confidence_recompute.py
│   ├── test_design_analyzer.py
│   └── test_email_service.py
├── data/
│   ├── design_screenshots/   # Your past design references
│   ├── output/               # Generated HTML/screenshots/zips
│   ├── cache/                # Cached API responses
│   └── knowledge/            # Knowledge base files
├── .env.example
├── requirements.txt
├── pytest.ini
└── README.md
```

## Provider Configuration

Switch providers by editing `.env` only. No code changes needed.

### OpenAI
```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
```

### Qwen (DashScope)
```env
LLM_PROVIDER=qwen
LLM_MODEL=qwen-max
LLM_API_KEY=sk-...
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### OpenRouter
```env
LLM_PROVIDER=openrouter
LLM_MODEL=anthropic/claude-3.5-sonnet
LLM_API_KEY=sk-or-...
LLM_BASE_URL=https://openrouter.ai/api/v1
```

### Mock (Testing)
```env
LLM_PROVIDER=mock
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/discovery/run` | Run business discovery |
| POST | `/api/pipeline/run` | Run full pipeline |
| GET | `/api/leads` | List all leads |
| GET | `/api/leads/{id}` | Lead detail |
| POST | `/api/leads/{id}/generate` | Generate redesign |
| POST | `/api/leads/{id}/screenshots` | Render screenshots |
| POST | `/api/leads/{id}/email` | Create email draft |
| POST | `/api/leads/{id}/approve` | Approve & send |
| POST | `/api/leads/{id}/reject` | Reject email |
| GET | `/api/leads/{id}/download` | Download zip |
| GET | `/api/logs` | View all logs |

## Dashboard

The web dashboard at http://127.0.0.1:8000 provides:

- Lead list with confidence scores and status
- Detail pages with website analysis, style reference, screenshots
- HTML preview and zip download
- Email draft review with approve/reject controls
- Activity logs

## Confidence Scoring

Scores are computed from weighted components:

| Component | Weight | Description |
|-----------|--------|-------------|
| Website Weakness | 25% | How badly the site needs redesign |
| Style Fit | 15% | Match to our design references |
| Industry Match | 15% | Industry suitability |
| Opportunity Clarity | 20% | How clear the problems are |
| HTML Quality | 15% | Quality of generated redesign |
| Outreach Confidence | 10% | Confidence in email copy |

Routing rules:
- **High (≥75)**: Eligible for one-click approval
- **Medium (50-74)**: Requires manual review
- **Low (<50)**: Draft only, do not send

## Extending

- Add new discovery connectors in `app/connectors/`
- Add new LLM providers by extending `BaseLLMProvider`
- Customize prompts in `app/core/prompts.py`
- Modify scoring weights in `app/core/scoring.py`
- Add new dashboard pages in `app/ui/` and `app/templates/`

## License

Private - All rights reserved.
