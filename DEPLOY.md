# Deploying the Dashboard

GitHub Pages cannot run this app because it is a Python FastAPI server and it must keep the Massive API key private.

Use this setup instead:

1. Push this folder to a GitHub repository.
2. Create a Render web service from that GitHub repo.
3. Set the Render start command:

```text
uvicorn app.app:app --host 0.0.0.0 --port $PORT
```

4. Add these Render environment variables:

```text
MASSIVE_API_KEY=your_massive_key
PRIVATE_DASHBOARD_TOKEN=choose_a_private_random_token
PUSHOVER_APP_TOKEN=optional
PUSHOVER_USER_KEY=optional
```

5. Share the public Render URL.

The public dashboard does not show the private portfolio file. The private route is available only when `PRIVATE_DASHBOARD_TOKEN` is set and used as:

```text
/private?token=your_private_token
```
