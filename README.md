# Water Quality Monitoring Dashboard

Web dashboard for one water quality station. It reads sensor data from MySQL every 5 minutes and shows:

- **Forecast:** the next 3 h (36 steps) from the last 24 h (288 lags) of all sensors, using LightGBM.
- **Lag influence:** how lag features drive each forecast, using LightGBM's built-in TreeSHAP (`pred_contrib`).
- **Anomalies:** s-IDK with a 5 h window (60 steps) and psi = 2, scored over the last 3 days.

## Run

Needs Python 3.12+ and Node.js 20+.

```powershell
copy .env.example .env        # then fill in the settings

cd frontend
npm install
npm run build

cd ..\backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. If no models exist, the first start trains them in the background.

For frontend work, run `npm run dev` in `frontend/`; it proxies `/api` to port 8000.

Tests: `cd backend; pip install -r requirements-dev.txt; python -m pytest tests`. They use synthetic data and never touch MySQL.

## Deploy

The dashboard runs as two [CapRover](https://caprover.com) apps, each from its own Dockerfile: `water-quality-api` (FastAPI, port 8000) and `water-quality` (nginx serving the built frontend). GitHub Actions deploys both on every push to `main` (`.github/workflows/deploy.yml`). The frontend reaches the API through `VITE_API_URL`, which is set in that workflow and built into the frontend.

Deployment stays off until it is connected once:

1. In CapRover, create `water-quality-api` with **Has Persistent Data** ticked, and `water-quality` without it. Persistent data cannot be changed later.
2. On `water-quality-api`, set the container HTTP port to 8000 and add a persistent directory with path in app `/app/data`. Keep it at one instance: the scheduler runs inside its process.
3. On `water-quality-api`, add the environment variables from `.env.example`, plus `CORS_ORIGINS=https://water-quality.s1.inference-analytics.my`.
4. Enable HTTPS on both apps, then copy each app's token from its Deployment tab.
5. In the GitHub repository settings, add the secrets `CAPROVER_SERVER`, `BACKEND_APP_NAME`, `BACKEND_APP_TOKEN`, `FRONTEND_APP_NAME` and `FRONTEND_APP_TOKEN`.
6. Add the repository variable `DEPLOY_ENABLED=true`, then run the workflow or push to `main`.

Models and `app.db` live in the volume at `/app/data`, so they survive redeploys. On first start the API trains its models in the background.

Anyone with the URL can read the dashboard. Only people holding a token from `APPROVER_TOKENS` can mark episodes reviewed.

## Configuration

Everything site-specific is in `.env`; see `.env.example`.

- `DATA_SOURCE`: `mysql`, or `synthetic` for generated test data, which the dashboard labels clearly.
- `SENSORS`: JSON list of `key` (column name), `label` and `unit`.
- `DB_TIMEZONE`: the timezone of the stored timestamps, which is not always the server's.

`python scripts/inspect_db.py` lists the tables, and `python scripts/inspect_db.py <table> <time_column>` reports columns, cadence and gaps. `python scripts/train_now.py` retrains on demand and prints forecast skill. Models otherwise retrain nightly at `RETRAIN_HOUR`.

The app only reads MySQL. Its own state (forecast log, episodes) is in `backend/data/app.db`.

## How it works

**Cleaning.** Readings go on a 5-minute grid. A reading far from its neighbours for a single sample is set aside as a glitch, and is listed on the Anomalies tab. Gaps up to 30 min are interpolated, so chart lines stay continuous, and those points are marked as estimated in the data tables. Longer gaps stay empty: LightGBM handles them natively, and charts shade them as "No data" rather than drawing a line across an outage.

**Forecast.** Direct strategy: one model per sensor per horizon, so 36 × sensors models. Each model predicts the change from the recent level (the median of the last 3 readings), because trees cannot predict outside the range they trained on. Every forecast is backtested against persistence on data held out from training.

**Validation.** The Forecast tab plots past forecasts against the readings later measured at those times, with the error at each point, for any look-ahead. Backtest points come from data held out of training (`validation.npz` in each model folder). Live points are stored forecasts whose target time has passed, kept for 14 days, and they replace backtest points where the two overlap.

**Lag influence.** For any forecast, recent level + typical change + contributions = forecast, in the sensor's units. Lags are grouped into 1-hour buckets by default because neighbouring lags are nearly identical and share credit arbitrarily. Contributions describe the model, not physical cause.

**Anomalies.** Each sensor's last 864 points are z-scored and scored with `IDK_square_sliding` (t = 500). A window is flagged when its similarity is below median − 3 × 1.4826 × MAD of the population, the rule from the reference repo. An episode stays open until reviewed, because a lasting change becomes the new normal for the score after about 1.5 days. Readings that do not change for a whole window are flagged separately, since s-IDK cannot see a sensor stuck at a normal value.

## Credits

`backend/third_party/idk/` is copied unchanged from [sufficiency-gated-maintenance-agent](https://github.com/alpermana14/sufficiency-gated-maintenance-agent) (MIT, licence included there).
