import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, LIGHT_LUX

from .api import CalypsHomeAPI, CalypsHomeObject
from .const import DOMAIN

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Configure les sondes Calyps'HOME à partir d'une entrée config

    Args:
        hass: Instance de Home Assistant
        entry: Entrée de configuration
        async_add_entities: Callback pour ajouter des entités à Home Assistant
    """
    entry_data = hass.data[DOMAIN][entry.entry_id]
    api = entry_data["api"]
    coordinator = entry_data["coordinator"]
    objects = coordinator.data

    if objects is None:
        LOGGER.error("Impossible de récupérer les objets de Calyps'HOME")
        return

    sonde_objects = [obj for obj in objects if isinstance(obj, CalypsHomeObject) and obj.class_name == "Sonde"]

    entities: list[SensorEntity] = []
    for obj in sonde_objects:
        statuses_names = {item.get("name") for item in (obj.statuses or []) if isinstance(item, dict)}
        if "temperature" in statuses_names:
            entities.append(CalypsHomeTemperatureSensor(coordinator, api, obj))
        if "illuminance" in statuses_names:
            entities.append(CalypsHomeIlluminanceSensor(coordinator, api, obj))

    if entities:
        async_add_entities(entities, True)
        LOGGER.info("%d capteurs Calyps'HOME ajoutés", len(sonde_objects))


class CalypsHomeSensorBase(CoordinatorEntity, SensorEntity):
    """Base commune pour les capteurs Calyps'HOME (température, luminosité, ...)"""

    _status_name: str = ""

    def __init__(self, coordinator: CoordinatorEntity, api: CalypsHomeAPI, object: CalypsHomeObject, unique_suffix: str):
        """
        Args:
            coordinator: Coordinateur de mise à jour des données
            api: Instance de `CalypsHomeAPI`
            object: Objet `CalypsHomeObject` représentant la sonde
            unique_suffix: Suffixe pour rendre l'unique_id distinct entre les capteurs d'une même sonde
        """
        super().__init__(coordinator)
        self._api = api
        self._device_id = object.id
        self._device_name = object.name
        self._attr_unique_id = f"{self._device_id}_{unique_suffix}"
        self._attr_native_value = None
        self._attr_available = True

    @property
    def device_info(self):
        """Retourne les informations de l'appareil (regroupe les capteurs sous une même sonde)"""
        return {
            "identifiers": {(DOMAIN, str(self._device_id))},
            "name": self._device_name,
            "manufacturer": "Calyps'HOME",
            "model": "Sensor",
        }

    def _find_status_value(self) -> str | None:
        """Récupère la valeur brute (str) du statut `_status_name` pour cette sonde, ou None"""
        objects = self.coordinator.data
        if not objects:
            return None

        sonde = next((obj for obj in objects if obj is not None and obj.id == self._device_id), None)
        if not sonde:
            return None

        statuses = sonde.statuses or []
        for item in statuses:
            if isinstance(item, dict) and item.get("name") == self._status_name:
                return item.get("value")
        return None

    def _handle_coordinator_update(self) -> None:
        """Met à jour la valeur du capteur à partir des données du coordinateur partagé"""
        try:
            raw_value = self._find_status_value()
            if raw_value is not None:
                self._attr_native_value = float(raw_value)
            self.async_write_ha_state()
        except (ValueError, TypeError) as err:
            LOGGER.error("Erreur lors de la mise à jour du capteur %s (%s): %s", self._device_name, self._status_name, err)

    async def async_added_to_hass(self) -> None:
        """Configure le callback pour les mises à jour du coordinateur"""
        await super().async_added_to_hass()
        self._handle_coordinator_update()


class CalypsHomeTemperatureSensor(CalypsHomeSensorBase):
    """Capteur de température d'une sonde Calyps'HOME"""

    _status_name = "temperature"

    def __init__(self, coordinator: CoordinatorEntity, api: CalypsHomeAPI, object: CalypsHomeObject):
        super().__init__(coordinator, api, object, unique_suffix="temperature")
        self._attr_name = f"{object.name} Température"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS


class CalypsHomeIlluminanceSensor(CalypsHomeSensorBase):
    """Capteur de luminosité d'une sonde Calyps'HOME"""

    _status_name = "illuminance"

    def __init__(self, coordinator: CoordinatorEntity, api: CalypsHomeAPI, object: CalypsHomeObject):
        super().__init__(coordinator, api, object, unique_suffix="illuminance")
        self._attr_name = f"{object.name} Luminosité"
        self._attr_device_class = SensorDeviceClass.ILLUMINANCE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = LIGHT_LUX