import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.cover import ATTR_POSITION, CoverDeviceClass, CoverEntity, CoverEntityFeature

from .api import CalypsHomeAPI, CalypsHomeObject
from .const import DOMAIN

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Configure les volets Calyps'HOME à partir d'une entrée config
    
    Args:
        hass: Instance de Home Assistant
        entry: Entrée de configuration
        async_add_entities: Callback pour ajouter des entités à Home Assistant
    """
    # Récupère l'API et le coordinateur à partir des données de l'entrée
    entry_data = hass.data[DOMAIN][entry.entry_id]
    api = entry_data["api"]
    coordinator = entry_data["coordinator"]
    objects = coordinator.data

    if objects is None:
        LOGGER.error("Impossible de récupérer les objets de Calyps'HOME")
        return

    # Crée les entités de volet pour chaque objet de type "shutter"
    entities = [CalypsHomeCover(coordinator, api, obj) for obj in objects if isinstance(obj, CalypsHomeObject) and obj.class_name == "Shutter"]

    # Ajoute les entités à Home Assistant
    if entities:
        async_add_entities(entities, True)
        LOGGER.info("%d volets Calyps'HOME ajoutés", len(entities))


class CalypsHomeCover(CoordinatorEntity, CoverEntity):
    """Représentation d'un volet Calyps'HOME"""

    def __init__(self, coordinator: CoordinatorEntity, api: CalypsHomeAPI, object: CalypsHomeObject):
        """
        Args:
            coordinator: Coordinateur de mise à jour des données
            api: Instance de `CalypsHomeAPI` pour accéder aux données et au token
            object: Objet `CalypsHomeObject` représentant l'objet de type "shutter"
        """
        super().__init__(coordinator)
        self._api = api
        self._device_id = object.id
        self._attr_name = object.name
        self._attr_unique_id = str(self._device_id)
        self._attr_device_class = CoverDeviceClass.SHUTTER

        # Fonctionnalités supportées
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

        self._reset_motion_state()
        self._target_position: int | None = None
        self._motion_start_position: int | None = None

    @property
    def device_info(self):
        """Retourne les informations de l'appareil"""
        return {
            "identifiers": {(DOMAIN, str(self._device_id))},
            "name": self._attr_name,
            "manufacturer": "Calyps'HOME",
            "model": "Rolling Shutter",
        }

    @property
    def current_cover_position(self):
        """Retourne la position actuelle du volet (0-100)"""
        return self._attr_current_cover_position

    @property
    def is_closed(self):
        """Retourne si le volet est fermé"""
        if self._attr_current_cover_position is not None:
            return self._attr_current_cover_position == 0
        return self._attr_is_closed

    @property
    def is_opening(self):
        """Retourne si le volet est en cours d'ouverture"""
        return self._attr_is_opening

    @property
    def is_closing(self):
        """Retourne si le volet est en cours de fermeture"""
        return self._attr_is_closing


    def _handle_coordinator_update(self) -> None:
        """Met à jour l'état de l'entité à partir des données du coordinateur partagé"""
        try:
            # Récupère les données des objets à partir du coordinateur
            objects = self.coordinator.data
            if not objects:
                return

            # Trouve l'objet correspondant à ce volet
            shutter: CalypsHomeObject = next((obj for obj in objects if obj is not None and obj.id == self._device_id), None)     
            if shutter:
                
                # Extrait les statuts du volet pour déterminer la position et l'état
                statuses = shutter.statuses or []
                status_name = None
                for item in statuses:
                    if not isinstance(item, dict):
                        continue
                    
                    # Extrait la valeur du niveau
                    if item.get("name") == "level":
                        level_value = item.get("value")
                        if level_value is not None:
                            self._attr_current_cover_position = max(0, min(100, int(float(level_value))))
                            self._attr_is_closed = self._attr_current_cover_position == 0
                            # Le websocket envoie le niveau quand le volet est arrêté
                            self._reset_motion_state()
                    elif item.get("name") == "status":
                        status_name = str(item.get("value", "")).lower()

                # Si le niveau n'est pas disponible, utilise le statut pour déterminer l'état
                if self._attr_current_cover_position is None and status_name:
                    if status_name == "up":
                        self._attr_current_cover_position = 100
                        self._attr_is_closed = False
                    elif status_name == "down":
                        self._attr_current_cover_position = 0
                        self._attr_is_closed = True
                    elif status_name == "middle":
                        self._attr_is_closed = False

                # Le statut (up/down/middle) signifie arrêt; le mouvement est piloté localement.
                if status_name in ("up", "down", "middle") and self._target_position is None:
                    self._attr_is_opening = False
                    self._attr_is_closing = False

                # Fin de mouvement: à la réception du level final après une commande.
                if self._target_position is not None and self._attr_current_cover_position is not None:
                    reached_target = self._attr_current_cover_position == self._target_position
                    moved_since_command = (
                        self._motion_start_position is not None
                        and self._attr_current_cover_position != self._motion_start_position
                    )

                    if reached_target or moved_since_command or self._motion_start_position is None:
                        self._reset_motion_state()
                    elif self._attr_current_cover_position < self._target_position:
                        self._attr_is_opening = True
                        self._attr_is_closing = False
                    else:
                        self._attr_is_opening = False
                        self._attr_is_closing = True
            
            self.async_write_ha_state()
        except Exception as err:
            LOGGER.error("Erreur lors de la mise à jour du volet %s: %s", self._attr_name, err)


    def _reset_motion_state(self) -> None:
        """Réinitialise l'état de mouvement (volet arrêté)"""
        self._attr_is_opening = False
        self._attr_is_closing = False
        self._target_position = None
        self._motion_start_position = None


    def _start_motion(self, target: int) -> None:
        """Démarre localement le suivi d'un mouvement vers `target`
        
        Args:
            target: Position cible (0-100) vers laquelle le volet se déplace
        """
        self._target_position = target
        self._motion_start_position = self._attr_current_cover_position
        if self._attr_current_cover_position is not None:
            self._attr_is_opening = self._attr_current_cover_position < target
            self._attr_is_closing = self._attr_current_cover_position > target
        else:
            self._attr_is_opening = target > 0
            self._attr_is_closing = target == 0
        self.async_write_ha_state()


    async def async_added_to_hass(self) -> None:
        """Configure le callback pour les mises à jour du coordinateur"""
        await super().async_added_to_hass()
        self._handle_coordinator_update()


    async def async_open_cover(self, **kwargs: Any) -> None:
        """Ouvre le volet"""
        if await self.hass.async_add_executor_job(self._api.open_shutter, self._device_id):
            self._start_motion(100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Ferme le volet"""
        if await self.hass.async_add_executor_job(self._api.close_shutter, self._device_id):
            self._start_motion(0)
            
    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Arrête le volet"""
        success = await self.hass.async_add_executor_job(self._api.stop_shutter, self._device_id)
        if success:
            self._target_position = None
            self._motion_start_position = None
            self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Déplace le volet à une position spécifique"""
        position = kwargs.get(ATTR_POSITION)
        if position is None:
            return
        target = max(0, min(100, int(position)))
        if await self.hass.async_add_executor_job(self._api.set_level, self._device_id, target):
            self._start_motion(target)