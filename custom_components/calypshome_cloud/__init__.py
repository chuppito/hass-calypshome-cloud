from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CalypsHomeAPI
from .const import DOMAIN, CONF_LOGIN, CONF_PASSWORD, LOGGER, PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configurer Calyps'HOME à partir d'une entrée config"""

    login = entry.data[CONF_LOGIN]
    password = entry.data[CONF_PASSWORD]

    api = CalypsHomeAPI(login, password)
    
    async def _async_update_data():
        # Récupérer les données des objets
        try:
            return await hass.async_add_executor_job(api.get_objects)
        except Exception as err:
            raise UpdateFailed(f"Impossible de mettre à jour les données Calyps'HOME: {err}") from err

    coordinator = DataUpdateCoordinator(hass, LOGGER, name=f"{DOMAIN}_{entry.entry_id}", update_method=_async_update_data, update_interval=timedelta(seconds=15))

    # Configurer le callback websocket pour mettre à jour uniquement le volet concerné.
    async def on_ws_update(ws_update=None):
        # Récupération des données du mise à jour du websocket
        if not ws_update:
            return

        real_name = ws_update.get("real_name")
        level_value = ws_update.get("value")
        if not real_name or level_value is None:
            return

        # Récupère les objets actuels du coordinateur
        objects = coordinator.data
        if not objects:
            return

        updated = False
        next_objects = []

        # Parcourt les objets pour trouver celui correspondant au real_name et mettre à jour son niveau
        for obj in objects:
            if obj.get("realName") != real_name:
                next_objects.append(obj)
                continue

            new_obj = dict(obj)
            statuses = list(new_obj.get("statuses", []))
            level_found = False

            for status in statuses:
                if isinstance(status, dict) and status.get("name") == "level":
                    status["value"] = level_value
                    level_found = True
                    updated = True
                    break

            if not level_found:
                statuses.append({"name": "level", "value": level_value})
                updated = True

            new_obj["statuses"] = statuses
            next_objects.append(new_obj)

        # Si une mise à jour a été effectuée, met à jour les données du coordinateur
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
        raise ConfigEntryNotReady from err

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