"""Flujo de configuración en interfaz gráfica para CO2 ACH Estimator."""
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CO2_SENSOR,
    CONF_MIN_R2,
    CONF_OCCUPANCY_SENSOR,
    CONF_OPENING_SENSOR,
    CONF_OUTDOOR_CO2_FIXED,
    CONF_OUTDOOR_CO2_SENSOR,
    CONF_ROOM_VOLUME,
    CONF_WINDOW_MINUTES,
    DEFAULT_MIN_R2,
    DEFAULT_OUTDOOR_CO2,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
)


def _get_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Genera el esquema del formulario con selectores nativos."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, "Salón")
            ): selector.TextSelector(),
            vol.Required(
                CONF_CO2_SENSOR, default=defaults.get(CONF_CO2_SENSOR)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(
                CONF_ROOM_VOLUME,
                description={"suggested_value": defaults.get(CONF_ROOM_VOLUME)},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=1000, step=0.5, unit_of_measurement="m³", mode="box"
                )
            ),
            vol.Optional(
                CONF_OUTDOOR_CO2_SENSOR,
                description={"suggested_value": defaults.get(CONF_OUTDOOR_CO2_SENSOR)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_OUTDOOR_CO2_FIXED,
                default=defaults.get(CONF_OUTDOOR_CO2_FIXED, DEFAULT_OUTDOOR_CO2),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=350, max=600, step=1, unit_of_measurement="ppm", mode="box"
                )
            ),
            vol.Required(
                CONF_WINDOW_MINUTES,
                default=defaults.get(CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=15, max=240, step=5, unit_of_measurement="min", mode="box"
                )
            ),
            vol.Required(
                CONF_MIN_R2,
                default=defaults.get(CONF_MIN_R2, DEFAULT_MIN_R2),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.80, max=0.999, step=0.01, mode="box"
                )
            ),
            vol.Optional(
                CONF_OCCUPANCY_SENSOR,
                description={"suggested_value": defaults.get(CONF_OCCUPANCY_SENSOR)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Optional(
                CONF_OPENING_SENSOR,
                description={"suggested_value": defaults.get(CONF_OPENING_SENSOR)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
        }
    )


class Co2AchConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gestiona la creación inicial de la entidad."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Paso inicial de configuración."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME], data=user_input
            )

        return self.async_show_form(step_id="user", data_schema=_get_schema())

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Permite editar la configuración sin borrar el sensor."""
        return Co2AchOptionsFlowHandler()


class Co2AchOptionsFlowHandler(config_entries.OptionsFlow):
    """Gestiona la edición de parámetros posteriores."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Muestra el formulario de edición."""
        current_data = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init", data_schema=_get_schema(current_data)
        )
