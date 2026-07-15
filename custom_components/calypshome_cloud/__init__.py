import copy
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CalypsHomeAPI, CalypsHomeObject
from .const import DOMAIN, CONF_LOGIN, CONF_PASSWORD, PLATFORMS, UPDATE_INTERVAL

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configure Calyps'HOME à partir d'une entrée config"""

    login = entry.data[CONF_LOGIN]
    password = entry.data[CONF_PASSWORD]

    api = CalypsHomeAPI(login, password)
    
    async def _async_update_data():
        # Récupérer les données des objets
        try:
            return await hass.async_add_executor_job(api.get_objects)
        except Exception as err:
            raise UpdateFailed(f"Impossible de mettre à jour les données Calyps'HOME: {err}") from err

    coordinator = DataUpdateCoordinator(hass, LOGGER, name=f"{DOMAIN}_{entry.entry_id}", update_method=_async_update_data, update_interval=timedelta(minutes=UPDATE_INTERVAL))

    async def on_ws_update(ws_update=None) -> None:
        """Callback appelé lorsqu'une mise à jour est reçue via le websocket"""
        # Vérifie que la mise à jour contient les informations nécessaires
        if not ws_update or not (real_name := ws_update.get("real_name")) or (level_value := ws_update.get("value")) is None or not coordinator.data:
            return

        updated = False
        next_objects = []

        # Parcourt les objets existants pour trouver celui correspondant à la mise à jour
        for obj in coordinator.data:
            if obj.real_name == real_name:
                obj: CalypsHomeObject = copy.copy(obj)
                statuses = list(obj.statuses)

                # Met à jour le statut "level" si présent, sinon l'ajoute
                if status := next((s for s in statuses if isinstance(s, dict) and s.get("name") == "level"), None):
                    status = dict(status)
                    status["value"] = level_value
                    statuses = [status if s.get("name") == "level" else s for s in statuses]
                else:
                    statuses = statuses + [{"name": "level", "value": level_value}]

                obj.statuses = statuses
                updated = True

            next_objects.append(obj)

        if updated:
            coordinator.async_set_updated_data(next_objects)

    api.on_update = on_ws_update

    try:
        # Authentifier auprès du cloud
        await hass.async_add_executor_job(api.login)
        # Récupérer les données initiales
        await coordinator.async_config_entry_first_refresh()
        if coordinator.data is None:
            raise ConfigEntryNotReady("Impossible de récupérer les objets de Calyps'HOME")
    except Exception as err:
        LOGGER.error("Erreur lors de la configuration de Calyps'HOME: %s", err)
        return False

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    # Démarrer l'écouteur websocket pour les mises à jour en temps réel
    await api.start_websocket()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge une entrée config"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry_data = hass.data[DOMAIN].get(entry.entry_id)
        if entry_data:
            api = entry_data.get("api")
            if api:
                api.stop_websocket()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok