# CO2 ACH Estimator for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/cjgarciao/co2_ach_estimator.svg)](https://github.com/cjgarciao/co2_ach_estimator/releases)
[![Validate with HACS](https://github.com/cjgarciao/co2_ach_estimator/actions/workflows/hacs.yml/badge.svg)](https://github.com/cjgarciao/co2_ach_estimator/actions/workflows/hacs.yml)
[![Validate with hassfest](https://github.com/cjgarciao/co2_ach_estimator/actions/workflows/hassfest.yml/badge.svg)](https://github.com/cjgarciao/co2_ach_estimator/actions/workflows/hassfest.yml)

A Home Assistant custom integration that estimates **Air Changes per Hour (ACH)** and **ventilation airflow ($$\text{m}^3/\text{h}$$)** in a room using the exponential decay of indoor $$\text{CO}_2$$ levels when the space is unoccupied.

> **Note:** This integration was designed and developed with the assistance of AI.


---

## How It Works

When a room is empty, indoor $\text{CO}_2$ concentration decays exponentially toward the outdoor baseline concentration ($C_{\text{ext}}$):

$$C(t) = C_{\text{ext}} + (C_0 - C_{\text{ext}}) \cdot e^{-\text{ACH} \cdot t}$$

By applying a natural logarithm to the excess $\text{CO}_2$, the integration performs a real-time linear regression over a rolling time window:

$$\ln(C(t) - C_{\text{ext}}) = \ln(C_0 - C_{\text{ext}}) - \text{ACH} \cdot t$$

### Smart Filtering & Noise Reduction
* **Interval Averaging (Bucketing):** High-frequency sensors (e.g., 1 reading/second) are automatically averaged over 20-second intervals to eliminate NDIR sensor noise and keep memory usage minimal.
* **Automatic Reset on Occupancy:** Immediately clears the buffer if $\text{CO}_2$ rises above noise tolerance (`+15 ppm`), if an optional occupancy sensor turns `on`, or when a window/door sensor changes state.
* **Quality Thresholds:** Only publishes an official ACH state when enough valid samples (`>= 100 ppm` above outdoor baseline), minimum decay duration (half of the configured window), and minimum correlation ($R^2$) are met. Preliminary calculations remain visible in the entity attributes at all times.

---

## Installation

### Option 1: HACS (Recommended)
1. Open **HACS** in your Home Assistant instance.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add `https://github.com/cjgarciao/co2_ach_estimator` with category **Integration**.
4. Search for **CO2 ACH Estimator** and click **Download**.
5. Restart Home Assistant.

### Option 2: Manual Installation
1. Download the latest release.
2. Copy the `custom_components/co2_ach_estimator` folder into your Home Assistant `/config/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. Go to **Settings > Devices & Services**.
2. Click **+ Add Integration** and search for **CO2 ACH Estimator**.
3. Configure each room with:
   * **Room name:** Name of the space (creates `sensor.ventilacion_<room>_ach`).
   * **Indoor CO2 sensor:** Your room's $\text{CO}_2$ sensor (`ppm`).
   * **Room volume (optional):** Volume in $\text{m}^3$ to calculate airflow in $\text{m}^3/\text{h}$.
   * **Outdoor CO2 sensor (optional):** Reference outdoor $\text{CO}_2$ sensor.
   * **Default outdoor CO2:** Fallback baseline in `ppm` (default: `420 ppm`).
   * **Analysis window:** Rolling time window in minutes (default: `60 min`).
   * **Minimum $R^2$:** Minimum goodness-of-fit required to validate the reading (default: `0.95`).
   * **Occupancy / Opening binary sensors (optional):** Automatically reset the calculation buffer when triggered.

---

## Entity & Attributes

Each configured room creates a single sensor (`ACH`) whose state is `unknown` until valid decay conditions are met, while diagnostic attributes update continuously:

| Attribute | Description |
| :--- | :--- |
| `status_detail` | Current calculation status or reason why the state is `unknown`. |
| `estimated_ach` | Preliminary unvalidated ACH value from the current regression. |
| `r_squared` | Coefficient of determination ($R^2$) of the logarithmic fit. |
| `airflow_m3h` | Validated ventilation airflow in $\text{m}^3/\text{h}$ (requires room volume). |
| `estimated_airflow_m3h` | Preliminary airflow in $\text{m}^3/\text{h}$. |
| `samples_count` | Total averaged points stored in the rolling buffer. |
| `valid_samples_count` | Points above the minimum threshold (`outdoor + 100 ppm`). |
| `elapsed_minutes` | Time span between the first and last valid sample. |

---

## Lovelace Dashboard Examples

### 1. Standard Entities Card (Native)
Displays the validated ACH value alongside its most important attributes without requiring any custom frontend cards:

```yaml
type: entities
title: Living Room Ventilation
entities:
  - entity: sensor.ventilacion_salon_ach
    name: Air Changes per Hour
  - type: attribute
    entity: sensor.ventilacion_salon_ach
    attribute: airflow_m3h
    name: Airflow
    suffix: m³/h
  - type: attribute
    entity: sensor.ventilacion_salon_ach
    attribute: r_squared
    name: Fit Quality (R²)
  - type: attribute
    entity: sensor.ventilacion_salon_ach
    attribute: status_detail
    name: Status
```

### 2. Diagnostic Markdown Card (Native)
Shows both the validated measurement and the live preliminary regression values while samples are accumulating:

```yaml
type: markdown
title: Ventilation Diagnostics
content: >
  {% set entity = 'sensor.ventilacion_salon_ach' %}
  {% set state = states(entity) %}
  {% set est_ach = state_attr(entity, 'estimated_ach') %}
  {% set r2 = state_attr(entity, 'r_squared') %}
  {% set airflow = state_attr(entity, 'airflow_m3h') %}
  {% set valid = state_attr(entity, 'valid_samples_count') %}
  {% set total = state_attr(entity, 'samples_count') %}
  {% set mins = state_attr(entity, 'elapsed_minutes') %}

  **Official ACH:** {{ state if state != 'unknown' else 'Calculating...' }} {{ 'ACH' if state != 'unknown' else '' }}
  {% if airflow is not none %}
  **Airflow:** {{ airflow }} m³/h
  {% endif %}

  ---
  * **Preliminary ACH:** {{ est_ach if est_ach is not none else 'N/A' }} ACH
  * **Correlation (R²):** {{ r2 if r2 is not none else 'N/A' }}
  * **Valid / Total Samples:** {{ valid }} / {{ total }} ({{ mins }} min)
  * **Status:** {{ state_attr(entity, 'status_detail') }}
```
