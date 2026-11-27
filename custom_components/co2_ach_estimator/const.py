"""Constantes para CO2 ACH Estimator."""

DOMAIN = "co2_ach_estimator"

CONF_CO2_SENSOR = "co2_sensor"
CONF_OUTDOOR_CO2_SENSOR = "outdoor_co2_sensor"
CONF_OUTDOOR_CO2_FIXED = "outdoor_co2_fixed"
CONF_WINDOW_MINUTES = "window_minutes"
CONF_MIN_R2 = "min_r2"
CONF_ROOM_VOLUME = "room_volume"
CONF_OCCUPANCY_SENSOR = "occupancy_sensor"
CONF_OPENING_SENSOR = "opening_sensor"

DEFAULT_OUTDOOR_CO2 = 420.0
DEFAULT_WINDOW_MINUTES = 60
DEFAULT_MIN_R2 = 0.95
MIN_SAMPLES = 8
MIN_DELTA_PPM = 100.0
NOISE_TOLERANCE_PPM = 15.0
MIN_SAMPLE_INTERVAL_SECONDS = 20

