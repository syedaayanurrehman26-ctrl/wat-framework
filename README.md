# WAT Newsletter Framework

A free, automated newsletter generator that researches any topic, builds a visually rich HTML email, and drops it straight into your Gmail as a ready-to-send draft — in under 30 seconds.

**Built on the WAT architecture:** Workflows → Agents → Tools. AI handles reasoning, Python handles execution.

---

## What It Does

1. You type a topic (e.g. `youtube`, `tesla earnings`, `2026 world cup`)
2. It fetches the brand's real colors from their official website
3. Groq AI researches and writes the full newsletter content
4. A styled HTML email is created and saved as a Gmail draft
5. Chrome opens with the draft pre-loaded — you add recipients and hit Send

---

## What the Newsletter Includes

- **AT A GLANCE** — 3 scannable bullets at the top
- **Executive Summary** — 3 paragraphs of context
- **By The Numbers** — hero stat + 9 stat cards
- **Timeline** — 10 key events with dates
- **Data Table** — topic-specific comparison
- **Bar Charts** — visual metric comparison
- **Outlook & Analysis** — short term, key risk, watch for
- **CTA Button** — in the footer

Colors are extracted live from the brand's official website on every run.

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/wat-newsletter-framework.git
cd wat-newsletter-framework
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Get a free Groq API key

- Go to [console.groq.com](https://console.groq.com)
- Sign up free → API Keys → Create API Key
- Copy the key (starts with `gsk_`)

### 4. Set up Google Gmail API

- Go to [console.cloud.google.com](https://console.cloud.google.com)
- Create a new project → Enable the **Gmail API**
- Go to Credentials → Create OAuth 2.0 Client ID → Desktop app
- Download the JSON → rename it to `credentials.json`
- Place it in the project root

### 5. Add your API key

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_key_here
```

---

## Run

```bash
python tools/newsletter.py
```

- Type your topic when prompted
- First run opens a Google login window — sign in once, never again
- Gmail opens in Chrome with your newsletter ready to send

---

## File Structure

```
tools/newsletter.py          — main script (run this)
workflows/                   — SOP documentation
newsletter_config.md         — visual preferences and rules
CLAUDE.md                    — WAT framework architecture
requirements.txt             — Python dependencies
.env                         — your API keys (gitignored)
credentials.json             — Google OAuth (gitignored)
```

---

## Tech Stack

| Component | Tool | Cost |
|-----------|------|------|
| AI content generation | Groq API (Llama 3.3 70B) | Free |
| Gmail integration | Gmail API (OAuth) | Free |
| Brand color extraction | Live website scraping | Free |
| Everything else | Python | Free |

**Total cost: $0**

---

## Architecture

This project uses the **WAT Framework** (Workflows, Agents, Tools):

- **Workflows** — markdown SOPs in `workflows/` that define what to do
- **Agents** — the AI layer that coordinates execution
- **Tools** — Python scripts that do the actual work deterministically

The separation keeps AI focused on reasoning and Python focused on reliable execution.

---

## Built By

Syed Aayan Rehman — built with [Claude Code](https://claude.ai/code)
