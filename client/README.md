# Dental Clinic Assistant Frontend

React + Vite dashboard for the Dental Clinic Assistant backend.

## Backend Contract Used By UI

The UI is wired to these FastAPI endpoints:

- `GET /health`
- `GET /api/metrics`
- `GET /api/appointments`
- `POST /api/appointments`
- `POST /api/chat`

Database-backed fields displayed in the UI come from PostgreSQL tables defined in `db_server/schema.sql`.

## Local Development

1. Install dependencies:

```bash
npm install
```

2. Set backend URL (optional). By default, the client uses `http://localhost:8000`:

```bash
# .env
VITE_API_URL=http://localhost:8000
```

3. Start the development server:

```bash
npm run dev
```

4. Build for production:

```bash
npm run build
```

## Notes

- Appointment times are rendered from PostgreSQL time values.
- Call timestamps are rendered from backend datetime values.
- Booking errors include alternative available slots when provided by backend.
