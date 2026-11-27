"""Sensor único de ACH con atributos siempre visibles y estimación preliminar."""
from collections import deque
from datetime import datetime, timedelta
import math
from typing import Any
from homeassistant.util import dt as dt_util, slugify


from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event


from .const import (
    CONF_CO2_SENSOR,
    CONF_MIN_R2,
    CONF_OCCUPANCY_SENSOR,
    CONF_OPENING_SENSOR,
    CONF_OUTDOOR_CO2_FIXED,
    CONF_OUTDOOR_CO2_SENSOR,
    CONF_ROOM_VOLUME,
    CONF_WINDOW_MINUTES,
    MIN_DELTA_PPM,
    MIN_SAMPLES,
    NOISE_TOLERANCE_PPM,
    MIN_SAMPLE_INTERVAL_SECONDS,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura el sensor ACH a partir de la entrada."""
    config = {**entry.data, **entry.options}
    async_add_entities([Co2AchSensor(hass, entry.entry_id, config)])


class Co2AchSensor(SensorEntity):
    """Sensor que estima las renovaciones por hora (ACH) de una estancia."""

    _attr_has_entity_name = True
    _attr_translation_key = "ach"
    _attr_native_unit_of_measurement = "ACH"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:air-filter"

    def __init__(
        self, hass: HomeAssistant, entry_id: str, config: dict[str, Any]
    ) -> None:
        self.hass = hass
        self._attr_unique_id = f"{entry_id}_ach"
        self._room_name = config[CONF_NAME]
        self.entity_id = f"sensor.ventilacion_{slugify(self._room_name)}_ach"
        self._co2_entity = config[CONF_CO2_SENSOR]
        self._room_volume = config.get(CONF_ROOM_VOLUME)
        self._outdoor_entity = config.get(CONF_OUTDOOR_CO2_SENSOR)
        self._outdoor_fixed = float(config[CONF_OUTDOOR_CO2_FIXED])
        self._window_minutes = int(config[CONF_WINDOW_MINUTES])
        self._min_r2 = float(config[CONF_MIN_R2])
        self._occupancy_entity = config.get(CONF_OCCUPANCY_SENSOR)
        self._opening_entity = config.get(CONF_OPENING_SENSOR)

        # Buffer de tuplas: (datetime, float_ppm)
        self._samples: deque[tuple[datetime, float]] = deque()
        self._ach_value: float | None = None
        self._raw_ach_value: float | None = None
        self._r2_value: float | None = None
        self._status_reason: str = "Esperando lecturas iniciales"

        # Buffer temporal
        self._pending_readings: list[float] = []
        self._last_avg_ppm: float | None = None
        self._last_bucket_count: int = 0
        self._valid_samples_count: int = 0

    @property
    def device_info(self) -> dict[str, Any]:
        """Agrupa el sensor bajo un dispositivo con el nombre de la estancia."""
        return {
            "identifiers": {("co2_ach_estimator", self._attr_unique_id)},
            "name": f"Ventilación {self._room_name}",
            "manufacturer": "CO2 ACH Estimator",
            "model": "Exponential Decay Model",
        }

    @property
    def available(self) -> bool:
        """Disponible siempre que el sensor de CO2 origen esté disponible."""
        co2_state = self.hass.states.get(self._co2_entity)
        return co2_state is not None and co2_state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )

    @property
    def native_value(self) -> float | None:
        """Devuelve el valor de ACH válido o None (estado 'unknown')."""
        return self._ach_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expone R2, estimación preliminar, caudal m³/h y diagnóstico."""
        airflow = None
        if self._ach_value is not None and self._room_volume:
            airflow = round(self._ach_value * float(self._room_volume), 1)

        estimated_airflow = None
        if self._raw_ach_value is not None and self._room_volume:
            estimated_airflow = round(self._raw_ach_value * float(self._room_volume), 1)

        elapsed_minutes = 0.0
        if len(self._samples) >= 2:
            first_ts, _ = self._samples[0]
            last_ts, _ = self._samples[-1]
            elapsed_minutes = round((last_ts - first_ts).total_seconds() / 60.0, 1)

        return {
            "status_detail": self._status_reason,
            "estimated_ach": self._raw_ach_value,
            "r_squared": self._r2_value,
            "airflow_m3h": airflow,
            "estimated_airflow_m3h": estimated_airflow,
            "room_volume_m3": self._room_volume,
            "samples_count": len(self._samples),
            "valid_samples_count": self._valid_samples_count,
            "last_sample_avg_ppm": self._last_avg_ppm,
            "last_sample_readings_count": self._last_bucket_count,            
            "elapsed_minutes": elapsed_minutes,
            "outdoor_co2_used": self._get_outdoor_co2(),
            "window_minutes": self._window_minutes,
        }

    async def async_added_to_hass(self) -> None:
        """Suscribe los eventos de cambio de estado al añadirse."""
        entities_to_track = [self._co2_entity]
        if self._occupancy_entity:
            entities_to_track.append(self._occupancy_entity)
        if self._opening_entity:
            entities_to_track.append(self._opening_entity)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, entities_to_track, self._handle_state_change
            )
        )

        initial_state = self.hass.states.get(self._co2_entity)
        if initial_state:
            self._process_co2_state(initial_state.state)

    @callback
    def _handle_state_change(self, event: Event) -> None:
        """Gestiona actualizaciones de CO2, ocupación o apertura de ventanas."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self.async_write_ha_state()
            return

        if entity_id == self._occupancy_entity:
            if new_state.state == STATE_ON:
                self._reset_buffer("Estancia ocupada")
            return

        if entity_id == self._opening_entity:
            self._reset_buffer("Cambio en apertura de ventana/puerta")
            return

        if entity_id == self._co2_entity:
            self._process_co2_state(new_state.state)

    def _reset_buffer(self, reason: str) -> None:
        """Limpia el histórico acumulado y reinicia valores."""
        self._samples.clear()
        self._pending_readings.clear()
        self._last_avg_ppm = None
        self._last_bucket_count = 0
        self._valid_samples_count = 0            
        self._ach_value = None
        self._raw_ach_value = None
        self._r2_value = None
        self._status_reason = reason
        self.async_write_ha_state()

    def _get_outdoor_co2(self) -> float:
        """Obtiene el CO2 exterior desde el sensor opcional o el valor fijo."""
        if self._outdoor_entity:
            state = self.hass.states.get(self._outdoor_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    return float(state.state)
                except ValueError:
                    pass
        return self._outdoor_fixed

    def _process_co2_state(self, raw_state: str) -> None:
        """Acumula lecturas rápidas y consolida la media cuando pasa el intervalo."""
        try:
            current_ppm = float(raw_state)
        except ValueError:
            return

        if self._occupancy_entity:
            occ_state = self.hass.states.get(self._occupancy_entity)
            if occ_state and occ_state.state == STATE_ON:
                self._reset_buffer("Estancia ocupada")
                return

        now = dt_util.utcnow()

        # 1. Detectar repunte brusco frente al último punto consolidado
        if self._samples:
            _, last_ppm = self._samples[-1]
            if current_ppm > (last_ppm + NOISE_TOLERANCE_PPM):
                self._samples.clear()
                self._pending_readings.clear()

        # 2. Añadir lectura al acumulador
        self._pending_readings.append(current_ppm)

        # 3. Comprobar cuánto tiempo ha pasado desde la última muestra guardada
        if self._samples:
            last_saved_ts, _ = self._samples[-1]
            elapsed_since_last = (now - last_saved_ts).total_seconds()
            if elapsed_since_last < MIN_SAMPLE_INTERVAL_SECONDS:
                return

        # Si es el primer dato o ya pasaron >= MIN_SAMPLE_INTERVAL_SECONDS:
        # Consolidamos la media inmediatamente
        bucket_count = len(self._pending_readings)
        avg_ppm = sum(self._pending_readings) / bucket_count
        self._pending_readings.clear()

        self._last_avg_ppm = round(avg_ppm, 1)
        self._last_bucket_count = bucket_count
        self._samples.append((now, avg_ppm))

        # 4. Purgar muestras fuera de la ventana temporal
        cutoff = now - timedelta(minutes=self._window_minutes)
        while self._samples:
            oldest_ts, _ = next(iter(self._samples))
            if oldest_ts < cutoff:
                self._samples.popleft()
            else:
                break

        self._calculate_regression()
        self.async_write_ha_state()



    def _calculate_regression(self) -> None:
        """Calcula la regresión siempre que haya >=2 puntos y valida criterios."""
        outdoor_ppm = self._get_outdoor_co2()
        min_ppm = outdoor_ppm + MIN_DELTA_PPM



        valid_points = [
            (ts, ppm)
            for ts, ppm in self._samples
            if ppm >= min_ppm
        ]
        
        self._valid_samples_count = len(valid_points)
        
        if self._valid_samples_count < 2:
            self._ach_value = None
            self._raw_ach_value = None
            self._r2_value = None
            min_ppm = round(outdoor_ppm + MIN_DELTA_PPM)
            self._status_reason = (
                f"Muestras válidas insuficientes ({self._valid_samples_count}/{MIN_SAMPLES}, mín. {round(min_ppm)} ppm)"
            )
            return

        t0, _ = valid_points[0]
        t_last, _ = valid_points[-1]
        elapsed_minutes = (t_last - t0).total_seconds() / 60.0
        min_required_minutes = self._window_minutes / 2.0

        xs = [(ts - t0).total_seconds() / 3600.0 for ts, _ in valid_points]
        ys = [math.log(ppm - outdoor_ppm) for _, ppm in valid_points]

        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_x2 = sum(x * x for x in xs)
        sum_y2 = sum(y * y for y in ys)

        denom_x = n * sum_x2 - sum_x ** 2
        denom_y = n * sum_y2 - sum_y ** 2

        if denom_x <= 0 or denom_y <= 0:
            self._ach_value = None
            self._raw_ach_value = None
            self._r2_value = None
            self._status_reason = "Varianza nula en los datos"
            return

        numerator = n * sum_xy - sum_x * sum_y
        slope = numerator / denom_x
        r2 = (numerator ** 2) / (denom_x * denom_y)
        ach = -slope

        self._raw_ach_value = round(ach, 2)
        self._r2_value = round(r2, 4)

        # Validación de criterios para dar el dato como oficial
        if self._valid_samples_count < MIN_SAMPLES:
            self._ach_value = None
            self._status_reason = (
                f"Muestras válidas insuficientes ({self._valid_samples_count}/{MIN_SAMPLES}, mín. {round(min_ppm)} ppm)"
            )
        elif elapsed_minutes < min_required_minutes:
            self._ach_value = None
            self._status_reason = (
            f"Tiempo insuficiente ({elapsed_minutes:.1f}/{min_required_minutes:.1f} min)"
            )
        elif ach <= 0:
            self._ach_value = None
            self._status_reason = "Sin decaimiento neto detectado"
        elif r2 < self._min_r2:
            self._ach_value = None
            self._status_reason = f"R2 insuficiente ({self._r2_value} < {self._min_r2})"
        else:
            self._ach_value = self._raw_ach_value
            self._status_reason = "Cálculo válido"