# Deploying the AEGIS dashboard (get a public link, no local running)

You do **not** have to run `streamlit run ...` every time. Deploy once, get a URL, open it from
any browser/phone. I cannot click "deploy" for you (it needs YOUR GitHub + host login), but the repo
is now deploy-ready — follow one of these.

## The one blocker (now fixed)
The root `requirements.txt` is the **dev** file: it lists `MetaTrader5` (Windows-only — fails on Linux),
`torch`, `ray`, `transformers`… a cloud build would choke on it. So use **`requirements-dashboard.txt`**
(minimal, Linux-safe) for deployment instead.

---

## Option A — Streamlit Community Cloud  (free, easiest, recommended)
1. Go to https://share.streamlit.io  → sign in with GitHub → authorize access to the **private**
   `praveen330/NexaQuant` repo.
2. **New app** →
   - Repository: `praveen330/NexaQuant`
   - Branch: `main`
   - Main file path: `india/aegis_dashboard.py`
3. Advanced settings → **Python dependencies file**: set to `requirements-dashboard.txt`
   (if no such field appears, rename `requirements-dashboard.txt` to `requirements.txt` ON A
   DEPLOY BRANCH so the dev file isn't disturbed — ask me and I'll make that branch).
4. Deploy. You get `https://<something>.streamlit.app`.
5. **Privacy:** in app settings you can keep it **private** (only invited Google/emails can view) or
   make it public. Keep it private if you don't want your picks visible.

Notes: free tier **sleeps** after inactivity and wakes (~30s) on the next visit; ~1 GB RAM (fine here).
The app reads the **committed** workbook + CSVs, so the data is whatever was last pushed.

## Option B — Hugging Face Spaces  (free, full control of deps)
Create a Space (SDK = Streamlit), `app_file = india/aegis_dashboard.py`, put the contents of
`requirements-dashboard.txt` as the Space's `requirements.txt`. Push code + `data/` + `reports/`.
URL: `https://huggingface.co/spaces/<you>/aegis`.

## Option C — Always-on (Render / Railway / a small VPS)
For an always-on app (no sleep) or a custom domain, a $5–7/mo VPS or Render web service running
`streamlit run india/aegis_dashboard.py --server.port $PORT --server.address 0.0.0.0`. More setup,
more control. A `Dockerfile` can be added on request.

---

## Keeping the live link fresh
The deployed app shows the **last pushed** `reports/AEGIS_*.xlsx` + CSVs. To update it:
`python india/recommendation_generator.py && python india/recommendation_db.py` then commit+push —
the cloud app auto-redeploys. (The "daily-refresh scheduler" sprint would automate this.)

## Secrets
The dashboard needs **no** secrets — it does not use Angel/MT5 or any broker. Do **not** put
`.env.angel`/MT5 creds into the host's secrets; nothing in the dashboard reads them.
