# Companion bridge

A thin, additive layer so a LAN client (e.g. a phone) can discover what an
Shirabi server offers and pair to it, without duplicating any LLM logic.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/companion/ping` | session or token | cheap, auth-validated health check |
| GET | `/api/companion/info` | session or token | server identity + capability flags |
| GET | `/api/companion/models` | session or token | the **caller's own** model endpoints |
| GET | `/api/companion/pair` | **admin cookie** | pairing page (a form; never mints) |
| POST | `/api/companion/pair` | **admin cookie** | mint a one-time pairing token (`?format=json` for an in-app screen) |
| GET | `/api/companion/live/status` | session or token | probe local Unity companion runtime/editor targets |
| POST | `/api/companion/live/command` | session or token | forward a live avatar command to the companion runtime |
| POST | `/api/companion/live/speak` | session or token | synthesize custom-voice speech and hand the audio file to Unity |

`/models` scopes to the caller's real owner plus legacy null-owner shared rows
(same rule as `owner_filter`) and never returns API-key material.

## Pairing CSRF posture

Minting happens **only on POST**. The session cookie is `SameSite=Lax`
(`routes/auth_routes.py`), so a browser will not send it on a cross-site POST —
the same protection `POST /api/tokens` relies on. A `GET` would be unsafe (Lax
cookies ride top-level GET navigations), so `GET /pair` only renders a form.
Minting invalidates the auth middleware's token cache, so a freshly minted token
works on the next request without a restart.

The pairing/scoping rules live in small, tested units (`token_owner`,
`owner_can_see`, `mint_pairing_token`, `pairing.*`) — see
`tests/test_companion_readonly.py` and `tests/test_companion_pairing.py`.

## Live local bridge

The live bridge is local-machine only. Shirabi talks to:

- `http://127.0.0.1:9878` for the built Unity companion app runtime bridge.
- `http://127.0.0.1:9877` for Unity Editor control visibility.
- `http://127.0.0.1:9876` for Unity Editor state visibility.

`/live/status` reports all three targets and chooses the runtime app when it is
available. `/live/command` currently sends commands only to the runtime app,
because the editor endpoints expose project/editor automation rather than live
avatar behavior.

`/live/speak` accepts either `{ "text": "hello" }` or an existing
`{ "audioPath": "C:\\path\\speech.wav" }`. Text is synthesized through
Shirabi's TTS path, with a local GPT-SoVITS fallback on `127.0.0.1:9880`, then
Unity receives one `speak_file` command. Unity owns playback, approximate
visemes, and temporary look-at behavior so mouth motion stays tied to the local
audio clock instead of HTTP round trips.
