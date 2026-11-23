# Deploying FinRAG Agent

Prerequisites: the index is built and committed (`data/index/` and `data/processed/chunks.jsonl`,
under 50 MB), and you have an LLM API key. Never commit `.env`.

## Option 0: free live demo from your own PC (no hosting account)

Docker Spaces on Hugging Face may be paid-only for new accounts, and free hosts such as Render
have too little memory (512 MB) for the two models. A Cloudflare quick tunnel needs no account:

```bash
winget install --id Cloudflare.cloudflared         # once (Windows)
uvicorn app.main:app --port 7860                    # terminal 1
cloudflared tunnel --url http://localhost:7860      # terminal 2: prints a public https://....trycloudflare.com link
```

The link works while both commands run. Set `DAILY_LIMIT` low (for example 40) in `.env` so a shared
link cannot use up your free LLM quota.

## Option 1: Hugging Face Spaces (Docker, if your account allows it)

1. Create a Space at https://huggingface.co/new-space. SDK: **Docker**, hardware: **CPU basic**.
2. The top of `README.md` already contains the Space front matter (`sdk: docker`, `app_port: 7860`).
3. Add the Space as a git remote and push:
   ```bash
   git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
   git push space main
   ```
   (HF asks for a write token as the password. Create one in your HF settings.)
4. In the Space: **Settings -> Variables and secrets**. Add as **secrets**: `LLM_API_KEY`
   (and `LOGFIRE_TOKEN` if you use it). Add as **variables**: `LLM_MODEL`, `DAILY_LIMIT`,
   `RATE_LIMIT`, `WEAK_SCORE_THRESHOLD`, `GITHUB_URL`.
5. The Space builds the Dockerfile (several minutes: it downloads both models) and then serves
   on port 7860. Check `https://<space>.hf.space/health`.
6. Set a spending limit on your LLM provider account. `DAILY_LIMIT` caps questions per day, but
   it resets whenever the container restarts.

## Option 2: Render

1. Push the repo to GitHub.
2. Render dashboard -> **New -> Web Service** -> connect the repo, **Runtime: Docker**.
3. Environment variables: the same as above (`LLM_API_KEY` etc.). Render sets `PORT` itself, but
   the Dockerfile listens on 7860, so set the service's port to 7860 in the settings.
4. Health check path: `/health`.
5. Free instances sleep when idle, so the first request after a pause is slow.

## Run locally with Docker

```bash
cp .env.example .env      # then fill in LLM_MODEL and LLM_API_KEY
docker compose up --build
# open http://localhost:7860
```
