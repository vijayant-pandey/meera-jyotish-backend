# Meera Jyotish – Backend

FastAPI service behind the Meera Astrology site. It computes kundali charts, dashas, panchang
and almanac data, handles user accounts and saved reports, and serves the CMS that the admin
panel edits.

The React frontend lives in [meera-jyotish-frontend](https://github.com/vijayant-pandey/meera-jyotish-frontend).

## Tech stack

- **Python 3.13**, FastAPI, Uvicorn
- **SQLAlchemy** with PostgreSQL (Neon in production) or SQLite locally
- **PyJHora** and **pysweph** (Swiss Ephemeris) for the astrology calculations
- **OpenStreetMap / Nominatim** for place search, with optional Google Places and Time Zone APIs
- **Cloudinary** for CMS image uploads (optional; falls back to local disk)

## Getting started

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
Copy-Item .env.example .env      # then fill in the values you need
uvicorn app.main:app --reload
```

The API runs at http://localhost:8000, with interactive docs at http://localhost:8000/docs.
Tables are created on startup, so an empty database works out of the box.

Optional one-off setup:

```powershell
python -m app.seed_content    # fill the CMS tables with the default site content (safe to rerun)
python -m app.create_admin --username admin --name "Site Admin"   # prompts for the password
```

Admin accounts can only be created with this script, never through the API. To create one in
production, run it locally with `DATABASE_URL` pointing at the Neon database.

## Configuration

All settings are read from environment variables or `.env`. See [.env.example](.env.example) for
the full list with comments.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL URL. Leave unset to use SQLite at `data/kundali.db`. |
| `FRONTEND_ORIGIN` | Frontend URL allowed by CORS (default `http://localhost:5173`). |
| `SESSION_SECURE_COOKIE` | Set to `true` in production so session cookies are HTTPS-only. |
| `CLOUDINARY_URL` | Stores admin image uploads on Cloudinary; otherwise they go to `media/`. |
| `NOMINATIM_USER_AGENT` | Contact string required by the OpenStreetMap usage policy. |
| `GOOGLE_PLACES_API_KEY`, `GOOGLE_TIMEZONE_API_KEY` | Optional; enables Google place lookup. |
| `SWISS_EPHE_PATH` | Folder of `.se1` ephemeris files (defaults to `ephe/`). |
| `RATE_LIMIT_MAX_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS` | Per-IP rate limit (default 80 per 60 s). |

The Swiss Ephemeris files in `ephe/` are committed on purpose: without them the calculations
silently fall back to the less precise Moshier model.

## Project layout

```
app/
  main.py          App setup: CORS, rate limiting, routers, startup tasks
  config.py        Settings loaded from the environment
  models.py        SQLAlchemy models
  routers/         API endpoints, one file per area
  services/        Astrology, panchang, almanac, geolocation and storage logic
  create_admin.py  CLI to create an admin user
  seed_content.py  CLI to seed CMS content
ephe/              Swiss Ephemeris data files
tests/             pytest suite
render.yaml        Render deployment blueprint
```

## API overview

| Prefix | What it covers |
|---|---|
| `/health` | Health check used by Render |
| `/api/auth` | Register, log in, log out, current user |
| `/api/kundali/generate`, `/api/reports` | Generate kundalis; saved reports, divisional charts and dasha |
| `/api/panchang` | Daily panchang |
| `/api/almanac` | Choghadiya, hora, rahu kaal, eclipses, seasons, lunar days, planet positions and events, doshas |
| `/api/match` | Ashtakoota match making |
| `/api/places` | Place autocomplete and resolution (coordinates and time zone) |
| `/api/content` | Public CMS content, newsletter sign-ups and feedback |
| `/api/admin` | Admin login and CMS editing, including image uploads |

Full request and response schemas are at `/docs` while the server is running.

## Tests

```powershell
pytest
```

## Deployment

The backend runs on **Render** using [render.yaml](render.yaml), and the database is on **Neon**.

- Render deploys automatically on every push to the `production` branch.
- Secrets (`DATABASE_URL`, `FRONTEND_ORIGIN`, `CLOUDINARY_URL`, API keys) are set in the Render
  dashboard and are never committed.
- Live URL: https://meera-jyotish-backend.onrender.com (health check at `/health`). The free plan
  sleeps when idle, so the first request after a while can take up to a minute.

The frontend on Vercel forwards `/api`, `/media` and `/health` to this service, so the browser
only ever talks to one domain.

## Branches

| Branch | Purpose |
|---|---|
| `production` | What is live on Render. Only updated through pull requests. |
| `development` | Integration branch; feature work is merged here first. |
| `task/MA-XXXX-...` | One branch per task, merged into `development` by pull request. |
