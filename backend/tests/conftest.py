"""Tests use the default sensors and synthetic data, whatever .env says."""
import json
import os

os.environ["DATA_SOURCE"] = "synthetic"
os.environ["SENSORS"] = json.dumps([
    {"key": "temperature", "label": "Temperature", "unit": "°C"},
    {"key": "ph", "label": "pH", "unit": "pH"},
    {"key": "dissolved_oxygen", "label": "Dissolved oxygen", "unit": "mg/L"},
    {"key": "turbidity", "label": "Turbidity", "unit": "NTU"},
    {"key": "conductivity", "label": "Conductivity", "unit": "µS/cm"},
])
