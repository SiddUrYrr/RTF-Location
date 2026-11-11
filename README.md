# RTF-Location

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Leaflet](https://img.shields.io/badge/Maps-Leaflet.js-199900.svg?style=flat&logo=leaflet)](https://leafletjs.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](#license)

**RTF-Location** is a privacy-focused family location-sharing and safety web app. Trusted circles can see each other on a live map, review recent routes, share medical notes, and raise a one-click SOS that reaches the whole circle — plus emergency contacts by SMS when Twilio is configured.

Built with FastAPI, SQLAlchemy, vanilla JavaScript, and Leaflet/OpenStreetMap. No frontend build step, no Firebase dependency.

---

## Features

### Live location sharing
- Real-time family map with avatar markers, battery level, accuracy circle, and distance from you.
- GPS tracking via the browser Geolocation API, with single updates and batched sync.
- Family feed refreshes roughly every 8 seconds while the tab is visible.
- Pause sharing instantly with a master switch.

### Privacy controls
- **Exact mode** for precise coordinates.
- **Blurred mode** shifts your location by a stable, secret-derived 180–300 m offset.
- The offset is per user, so markers do not jump on every GPS update and averaging readings cannot recover the exact point.
- You always see your own exact route. Active SOS temporarily overrides blur for your circle.
- Configurable retention deletes old raw location history automatically.

### Emergency SOS
- One-click SOS button with no confirmation dialog.
- Visual distress state for circle members and an in-app emergency notification.
- Optional SMS escalation to up to 10 emergency contacts, including a live map link.
- One-click “safe” resolution that notifies the circle.
- Medical profile fields (blood group, notes, home address) kept with your account for emergency reference.

### Family circles and friends
- Create circles with auto-generated 8-character invite codes.
- Join by code; circle admins can remove members.
- Send, accept, reject, and remove friend requests by username or email.

### Route history
- Replay the last 4, 12, 24, or 48 hours.
- Polyline visualization with start (A) and latest (B) markers.
- Blurred users get a shifted trail; owners get the exact trail.

### Account and UI
- Email/username login with bcrypt-hashed passwords and JWT sessions.
- Avatar uploads through Cloudinary when configured, with a base64 fallback.
- In-app notification bell with unread count and clear actions.
- Responsive glassmorphism UI with dark/light themes and mobile bottom-sheet gestures.

---

## Tech stack

| Layer | Technologies |
| :--- | :--- |
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy 2, Pydantic 2, Uvicorn, python-jose, bcrypt |
| **Database** | SQLite by default; PostgreSQL supported through `DATABASE_URL` |
| **Frontend** | Vanilla JavaScript, HTML5, CSS3, Bootstrap 5, Bootstrap Icons |
| **Maps** | Leaflet.js, OpenStreetMap/Google tile layer, HTML5 Geolocation API |
| **Optional services** | Cloudinary (avatars), Twilio (SOS SMS) |

---

## Quick start

### 1. Create a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Generate a signing key and put it in `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Minimal `.env`:

```dotenv
SECRET_KEY=your-long-random-secret
ACCESS_TOKEN_EXPIRE_MINUTES=10080
DATABASE_URL=sqlite:///./rtf_location.db
LOCATION_RETENTION_DAYS=90
```

### 4. Run the app

```bash
python -m uvicorn backend.main:app --reload
```

Open **http://localhost:8000**.

> Geolocation requires a secure context. `localhost` works; other hosts need HTTPS.

---

## Configuration

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `SECRET_KEY` | — | **Required.** Signs JWTs and derives blur offsets. Changing it invalidates sessions and reshuffles blur. |
| `ALGORITHM` | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | Session lifetime in minutes (7 days). |
| `DATABASE_URL` | `sqlite:///./rtf_location.db` | SQLAlchemy connection string. `postgres://` URLs are normalized automatically. |
| `CORS_ORIGINS` | empty | Comma-separated allowed origins. Only needed when the frontend is hosted on another origin. |
| `LOCATION_RETENTION_DAYS` | `90` | Delete raw location rows older than this at startup. `0` disables pruning. |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | empty | Enable Cloudinary avatar uploads. |
| `CLOUDINARY_URL` | empty | Alternative single-variable Cloudinary configuration. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | empty | Enable SOS SMS to emergency contacts. All three must be set. |

`.env` is gitignored. Never commit real credentials.

If `SECRET_KEY` is missing, the app generates an ephemeral key and logs a warning; every restart logs users out. Set it explicitly.

---

## Pages

| Page | URL | What it does |
| :--- | :--- | :--- |
| Live map | `/` or `/map` | Map, family feed, route history, notifications, SOS |
| Login | `/login` | Email/username + password sign-in |
| Sign up | `/signup` | Create an account |
| Profile hub | `/profile` | Personal details, medical info, emergency contacts, circles, privacy, password |

Health probe: `GET /health` returns `{"status":"ok","database":"ok"}` or HTTP 503.

---

## API overview

All endpoints below require `Authorization: Bearer <token>` unless noted. Request and response bodies are JSON.

### Authentication — `/api/auth`
| Method | Path | Notes |
| :--- | :--- | :--- |
| `POST` | `/signup` | Public. Creates a user and returns a token. |
| `POST` | `/login` | Public. Returns a token. |
| `GET` | `/me` | Current user profile. |
| `PUT` | `/profile` | Update name, phone, bio, address, medical fields, avatar. |
| `POST` | `/upload-avatar` | Multipart avatar upload. |
| `GET` | `/cloudinary-status` | CDN configuration check. |
| `POST` | `/change-password` | Rotates the token; the old token stops working. |

### Friends — `/api/friends`
| Method | Path | Notes |
| :--- | :--- | :--- |
| `GET` | `/` | List confirmed friends. |
| `POST` | `/request` | Send a request by username or email. |
| `GET` | `/requests` | Pending incoming requests. |
| `POST` | `/requests/{id}/respond?action=accept\|reject` | Respond to a request. |
| `DELETE` | `/{friend_user_id}` | Remove a friend. |

### Circles — `/api/groups`
| Method | Path | Notes |
| :--- | :--- | :--- |
| `POST` | `/create` | Create a circle. |
| `POST` | `/join` | Join by invite code. |
| `GET` | `/` | List your circles. |
| `DELETE` | `/{group_id}/leave` | Leave a circle. |
| `DELETE` | `/{group_id}/delete` | Delete a circle (admin only). |
| `GET` | `/{group_id}/members` | List members and roles. |
| `DELETE` | `/{group_id}/members/{user_id}` | Remove a member (admin only). |

### Locations — `/api/locations`
| Method | Path | Notes |
| :--- | :--- | :--- |
| `POST` | `/update` | Send one location reading. |
| `POST` | `/batch-sync` | Send up to 500 readings. |
| `POST` | `/toggle-sharing` | Set sharing and `exact`/`blurred` mode. |
| `GET` | `/live-feed` | Latest locations for friends and circle members. |
| `GET` | `/history/{user_id}?hours=24` | Route history for 1–168 hours. |

### Emergency — `/api/emergency`
| Method | Path | Notes |
| :--- | :--- | :--- |
| `GET` | `/contacts` | List emergency contacts. |
| `POST` | `/contacts` | Add a contact (max 10). |
| `DELETE` | `/contacts/{id}` | Remove a contact. |
| `POST` | `/sos/trigger` | Activate SOS, notify circles, queue SMS. |
| `POST` | `/sos/resolve` | Mark yourself safe. |

### Notifications — `/api/notifications`
| Method | Path | Notes |
| :--- | :--- | :--- |
| `GET` | `/` | Latest 30 notifications. |
| `POST` / `DELETE` | `/clear` | Clear all notifications. |
| `DELETE` | `/{id}` | Delete one notification. |

---

## Project structure

```text
RTF-Location/
├── backend/
│   ├── routers/
│   │   ├── auth_router.py       # Signup, login, profile, passwords, avatars
│   │   ├── friends_router.py    # Friend requests and connections
│   │   ├── groups_router.py     # Circles, invite codes, membership
│   │   ├── location_router.py   # GPS updates, live feed, history, blur
│   │   ├── notify_router.py     # In-app notifications
│   │   └── sos_router.py        # Emergency contacts and SOS lifecycle
│   ├── auth.py                  # JWT, password hashing, token revocation
│   ├── cloudinary_service.py    # Optional avatar CDN helper
│   ├── database.py              # Engine, sessions, SQLite pragmas
│   ├── main.py                  # App entry point, retention, headers, pages
│   ├── models.py                # SQLAlchemy models
│   ├── ratelimit.py             # Sliding-window abuse limits
│   ├── schemas.py               # Pydantic schemas and validation
│   ├── sms_service.py           # Optional Twilio SOS SMS escalation
│   └── timeutils.py             # Naive UTC helper
├── frontend/
│   ├── css/styles.css           # Design system and responsive layout
│   ├── js/
│   │   ├── app.js               # App controller, feed, circles, notifications
│   │   ├── location.js          # GPS tracker and SOS dispatcher
│   │   ├── map.js               # Leaflet map, markers, route polylines
│   │   └── utils.js             # HTML escaping and safe URL helpers
│   ├── index.html               # Live map
│   ├── login.html
│   ├── signup.html
│   └── profile.html
├── .env.example                 # Safe environment template
├── Procfile                     # Generic process definition
├── render.yaml                  # Render blueprint
├── requirements.txt
└── README.md
```

---

## Security and privacy

- **Passwords:** bcrypt hashing; no plaintext storage.
- **Sessions:** signed JWTs with expiry. Every token carries a password fingerprint; changing the password revokes all older tokens.
- **Input validation:** strict Pydantic rules for usernames, names, phone numbers, coordinates, invite codes, avatar URLs, and password length.
- **XSS defense:** server-side validation plus context-aware escaping (`esc`, `escAttr`, `safeUrl`) for every user-controlled value rendered into HTML, attributes, and map popups.
- **Rate limiting:** sliding-window limits on login, signup, friend requests, circle joins, password changes, and SOS.
- **Privacy blur:** HMAC-SHA256-derived offset using the server secret and user ID; the true coordinate is never sent to other users in blurred mode.
- **Headers and CORS:** `nosniff`, `SAMEORIGIN`, `no-referrer`, a restrictive permissions policy, and CORS disabled unless explicitly configured.
- **Data retention:** old raw locations are pruned at startup according to `LOCATION_RETENTION_DAYS`.
- **Secrets:** `.env` is ignored; there is no hardcoded production JWT secret.

### Current limitations

- SOS SMS requires Twilio credentials. Without them, in-app alerts still work and the API reports `sms_configured: false`.
- There is no email verification or self-service password reset flow yet.
- Rate limits are in memory. For multiple workers or instances, move counters to Redis.
- The live feed polls; there is no WebSocket/SSE channel.
- SQLite is intended for local use. Use PostgreSQL for production.

---

## Deploying

### Render blueprint

1. Push the repository to GitHub.
2. In Render, choose **New → Blueprint** and select the repository.
3. Render reads [`render.yaml`](render.yaml), generates `SECRET_KEY`, and builds with `pip install -r requirements.txt`.
4. Set `DATABASE_URL` to a managed PostgreSQL instance. Render’s free filesystem is ephemeral, so a local SQLite file is lost on redeploy.
5. Optionally add Cloudinary and Twilio variables.

### Manual web service

| Setting | Value |
| :--- | :--- |
| Runtime | Python 3.11+ |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |

Environment variables mirror the table above. The included `Procfile` provides the same start command for platforms that use it.

### Production checklist

- Set a strong, stable `SECRET_KEY`.
- Use PostgreSQL with backups instead of SQLite.
- Set `CORS_ORIGINS` only if the frontend is on another origin.
- Serve over HTTPS so browser geolocation is available.
- Configure Twilio if SMS escalation is required.
- Keep `LOCATION_RETENTION_DAYS` aligned with your privacy policy.

---

## Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| Users are logged out after restart | `SECRET_KEY` is missing or changed. Set a stable value in `.env`. |
| Map loads but no location | Allow browser location permission; use `localhost` or HTTPS. |
| SOS sends no texts | Set all three `TWILIO_*` variables; check server logs for Twilio errors. |
| Avatars fall back to initials | Configure Cloudinary credentials; check `/api/auth/cloudinary-status`. |
| `database is locked` on SQLite | Stop duplicate server processes and avoid running multiple writers. |
| CORS errors from another origin | Set `CORS_ORIGINS` to the exact frontend origin. |

---

## License

MIT. Use and adapt it for personal or commercial projects.
