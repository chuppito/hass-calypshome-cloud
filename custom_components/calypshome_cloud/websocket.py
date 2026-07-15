import re
import base64
import asyncio
import logging
import websockets
from typing import TYPE_CHECKING
from collections.abc import Awaitable, Callable

from homeassistant.util.ssl import client_context

if TYPE_CHECKING:
    from .api import CalypsHomeAPI

LOGGER = logging.getLogger(__name__)

class CalypsHomeWebSocket:
    
    WS_EVENT_RE = re.compile(r"^event/io/ezsp/(?P<real_name>.+)/(?P<field>[^/]+)$")
    
    @property
    def on_update(self) -> Callable[[dict | None], Awaitable[None]] | None:
        """Getter pour le callback de mise à jour"""
        return self._on_update
    
    @on_update.setter
    def on_update(self, value: Callable[[dict | None], Awaitable[None]] | None):
        """Setter pour le callback de mise à jour"""
        self._on_update = value
    
    
    def __init__(self, api: CalypsHomeAPI, on_update: Callable[[dict | None], Awaitable[None]] | None = None):
        """        
        Args:
            api: Instance de `CalypsHomeAPI` pour accéder aux données et au token
            on_update: Callback asynchrone appelé lorsqu'une mise à jour est reçue
        """
        self._api = api
        self._on_update = on_update
        self._ws_task = None
        self._ws_connected = False
        
    
    def _decode_ws_event_path(self, encoded_path: str) -> str | None:
        """Décode un chemin d'événement websocket encodé en base64
        
        Args:
            encoded_path: Chemin d'événement encodé en base64
            
        Returns:
            Chemin d'événement décodé ou `None` en cas d'erreur
        """
        try:
            payload = encoded_path[1:] if encoded_path.startswith("@") else encoded_path
            payload += "=" * (-len(payload) % 4)
            return base64.b64decode(payload).decode("utf-8")
        except Exception as e:
            LOGGER.debug("Impossible de décoder le chemin websocket '%s': %s", encoded_path, e)
            return None
    
    
    def _parse_ws_message(self, message: str) -> dict | None:
        """Parse un message websocket et extrait les mises à jour de niveau
        
        Args:
            message: Message websocket brut
        
        Returns:
            Dictionnaire avec les données si succès, sinon `None`
        """
        # Extrait le chemin d'événement encodé en b64 et la valeur
        parts = message.split()
        encoded_index = next((i for i, token in enumerate(parts) if token.startswith("@")), -1)
        if encoded_index == -1 or encoded_index + 1 >= len(parts):
            return None

        # Décode le chemin d'événement
        event_path = self._decode_ws_event_path(parts[encoded_index])
        if not event_path:
            return None

        # Extrait le nom réel et le champ à partir du chemin d'événement
        match = self.WS_EVENT_RE.match(event_path)
        if not match:
            return None

        # Extrait la valeur, en la décodant si elle est elle aussi encodée en base64 (préfixe @)
        raw_value = parts[encoded_index + 1]
        value = self._decode_ws_event_path(raw_value) if raw_value.startswith("@") else raw_value
        if value is None:
            return None

        return {
            "real_name": match.group("real_name"),
            "field": match.group("field"),
            "value": value
        }


    async def _ws_listen_loop(self) -> None:
        """Écoute le websocket et déclenche les mises à jour sur les messages"""
        ws_url = self._api.base_url.replace("https://", "wss://") + "/ws"

        while True:
            try:
                # Connexion au websocket
                LOGGER.debug("Connexion au websocket: %s", ws_url)
                
                async with websockets.connect(
                    ws_url, 
                    ping_interval=30, 
                    subprotocols=["lws-mirror-protocol"],
                    ssl=client_context()
                ) as ws:
                    self._ws_connected = True
                    LOGGER.info("Websocket connecté")
                    
                    # Envoie immédiatement le login websocket avec le token encodé
                    if not self._api.token and not self._api.login():
                        LOGGER.warning("Impossible d'authentifier le websocket, reconnexion...")
                        self._ws_connected = False
                        await asyncio.sleep(5)
                        continue

                    await ws.send(f"p1 1 _web / login @{base64.b64encode(self._api.token.encode()).decode()}")
                    LOGGER.debug("Message de connexion websocket envoyé")

                    # Boucle d'écoute des messages websocket
                    async for message in ws:
                        ws_update = self._parse_ws_message(message)

                        # Notifie uniquement les messages de niveau reconnus
                        if ws_update and self._on_update:
                            try:
                                await self._on_update(ws_update)
                            except Exception as e:
                                LOGGER.error("Erreur dans le callback de mise à jour: %s", e)

            except Exception as e:
                self._ws_connected = False
                LOGGER.warning("Erreur websocket, reconnexion dans 5s: %s", e)
                await asyncio.sleep(5)


    async def start_websocket(self) -> None:
        """Commence à écouter le websocket pour les mises à jour en temps réel"""
        if self._ws_task and not self._ws_task.done():
            return

        # Lancer la boucle d'écoute websocket
        self._ws_task = asyncio.create_task(self._ws_listen_loop())


    def stop_websocket(self) -> None:
        """Arrête l'écoute du websocket"""
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
        self._ws_connected = False