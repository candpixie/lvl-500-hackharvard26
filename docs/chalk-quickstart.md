# Quick start: connect the API to the Chalk ask service

For whoever runs the API (`uv run uvicorn api.main:app --reload --port 8000`). Five minutes. Background and details: `docs/chalk-ask-service.md`.

## 1. Get Chalk access
The ask service is locked: a request with no Chalk token gets HTTP 401. Ask Sarah to invite you to the Chalk team (dashboard, Settings, Users and roles), accept the invite, then:
```sh
curl -s -L https://api.chalk.ai/install.sh | sh
export PATH="$HOME/.chalk/bin:$PATH"
chalk login          # approve the link in a browser signed in to the account you were invited with
chalk token get --expires-in 24h
```
The last command prints your token. Tokens expire (24 hours here), so repeat it when the service starts answering 401. A token acts as you, so do not paste it in chat, commit it, or put it in anything starting with `VITE_`.

## 2. Add three lines to the gitignored `.env` on the API machine
```
CHALK_ASK_URL=https://spcwce09a241-orbit-ask.mdwje5.svls.customers.gcp.chalk.ai/ask
CHALK_TOKEN=<the token from step 1>
CHALK_ENV_ID=spcwce09a241
```
`spcwce09a241` is the environment id, not a secret. See `.env.example`.

## 3. Restart and check
Restart uvicorn, then:
```sh
curl -s http://127.0.0.1:8000/health
```
You want `"chalk": true` and `"reasoner": "chalk"` once a question has gone through. Then ask something:
```sh
curl -s -X POST http://127.0.0.1:8000/ask -H 'Content-Type: application/json' \
  -d '{"question":"Where should I put 1,000 four-meter satellites?"}'
```
Expect `focus.altitude_km` of 525, and the globe at `http://127.0.0.1:5173` should fly there.

To test the Chalk service directly, without the API:
```sh
curl -s -X POST "$CHALK_ASK_URL" -H "Authorization: Bearer $CHALK_TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"What is the closest near miss this week?"}'
```

## If something is off
| You see | Meaning | Fix |
|---|---|---|
| `"chalk": false`, no `chalk_error` | `CHALK_ASK_URL` empty, or the API was not restarted | check `.env`, restart uvicorn |
| `chalk_error: "auth"` or HTTP 401 | no token, or it expired | run `chalk token get --expires-in 24h` again and update `CHALK_TOKEN` |
| `chalk_error: "not_found"` | wrong URL (it must end in `/ask`) | copy the URL above exactly |
| `chalk_error: "unreachable"` or `"http_5xx"` | the Chalk service is down or restarting | check `GET .../health` with the token; tell Sarah. Grok falls back to the local tools automatically |
| answers say `"reasoner": "local"` | Chalk returned an error for that question, so the local tools answered | expected for questions outside what the service handles (for example "what is the weather") |

## What it answers
Where to put N satellites, what happens at an altitude, why an altitude is crowded, how crowded an altitude is, and the closest near miss (optionally around an altitude). Anything else returns an error on purpose, so Grok uses its local tools.

## Demo day
Get a fresh token right before the demo, or right after it expires, and run the health check. If Chalk is down the demo still works on the local fallback, but the answers then say they came from the local reasoner. Do not present those as running on Chalk.
