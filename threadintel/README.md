# ThreadIntel Engine

This folder contains all research and delivery tools that power the ThreadIntel service.
Each file handles one specific job. Run them independently or chain them together.

## Tools

| File | What It Does | Run |
|------|-------------|-----|
| `email_brief.py` | Generates a full intelligence brief and creates a Gmail draft | `python threadintel/email_brief.py` |
| `research.py` | *(coming)* Raw research pipeline — mines Reddit + news, returns structured JSON | — |
| `pdf_report.py` | *(coming)* Builds a PDF report from research JSON | — |
| `pptx_report.py` | *(coming)* Builds a PowerPoint deck from research JSON | — |
| `deliver.py` | *(coming)* Sends a completed report to a subscriber via email | — |

## Workflow

```
Customer submits topic
        ↓
  research.py         ← mines Reddit, forums, news → structured JSON
        ↓
  email_brief.py      ← builds Gmail draft from JSON
  pdf_report.py       ← builds PDF from JSON
  pptx_report.py      ← builds PPTX from JSON
        ↓
  deliver.py          ← emails report to subscriber
```

## Environment
All tools read from the root `.env` file. Required keys:
- `GROQ_API_KEY` — for AI content generation (free at console.groq.com)
- Google OAuth credentials in `credentials.json` + `token.json` — for Gmail
