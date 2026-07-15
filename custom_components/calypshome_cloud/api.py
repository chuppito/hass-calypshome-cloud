import logging
import urllib3
import requests
import threading
from collections.abc import Awaitable, Callable

from .const import DEFAULT_CLOUD_URL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOGGER = logging.getLogger(__name__)

class CalypsHomeObject:
    """Représentation d'un objet Calyps'HOME"""
    
    def __init__(self, id: int, name: str, class_name: str, real_name: str, statuses: list):
        """       
        Args:
            id (int): Identifiant unique de l'objet
            name (str): Nom convivial de l'objet
            class_name (str): Nom de la classe de l'objet
            real_name (str): Nom réel de l'objet utilisé par le cloud
            statuses (list | None, optional): Liste des statuts de l'objet. Defaults to None.
        """
        self.id = id
        self.name = name
        self.class_name = class_name
        self.real_name = real_name
        self.statuses = statuses


class CalypsHomeAPI:
    """Client API pour Calyps'HOME cloud"""

    @property
    def token(self):
        return self._token

    @token.setter
    def token(self, value: str):
        self._token = value
        if value:
            self.session.headers["Authorization"] = f"Bearer {value}"
        else:
            self.session.headers.pop("Authorization", None)


    def __init__(self, email: str, password: str):
        """
        Args:
            email: Email de connexion
            password: Mot de passe
        """
        self.base_url = DEFAULT_CLOUD_URL
        self.email = email
        self.password = password
        self._token = None
        self._request_lock = threading.RLock()
        self.on_update: Callable[[dict | None], Awaitable[None]] | None = None
        self._ws_client = None

        # Session standard, sans pool persistant forcé
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"


    def _extract_object_from_response(self, response: dict) -> dict | None:
        """Extrait les informations d'un objet depuis la réponse de l'API
        
        Args:
            response: Dictionnaire JSON de la réponse de l'API
            
        Returns:
            Dictionnaire avec les informations de l'objet ou `None` en cas d'erreur
        """
        try:
            objectData = response["resource"]
            return CalypsHomeObject(
                id=objectData["id"],
                name=objectData["name"],
                class_name=objectData["className"],
                real_name=objectData["realName"],
                statuses=objectData.get("statuses", [])
            )
        except (ValueError, KeyError) as e:
            LOGGER.error("Erreur lors de l'extraction de l'objet depuis la réponse: %s", e)
            return None


    def _send_calypshome_request(self, method: str, url: str, **kwargs) -> requests.Response | None:
        """Envoie une requête Calyps'HOME avec reprise d'authentification automatique
        
        Args:
            method: Méthode HTTP
            url: URL relative de la requête
            kwargs: Arguments supplémentaires pour `requests.request()`
        
        Returns:
            La réponse de la requête si succès, sinon `None`
        """
        url = f"{self.base_url}{url}"

        # Vérifie si le token est présent, sinon tente de s'authentifier
        if not self.token and not self.login():
            return None

        try:
            # Envoie la requête avec verrouillage pour éviter les conflits de session
            with self._request_lock:
                response = self.session.request(method, url, timeout=10, **kwargs)
        except requests.exceptions.RequestException as e:
            LOGGER.error("Erreur réseau lors de la requête HTTP : %s", e)
            return None

        # Si le token est expiré ou invalide, réessaye après réauthentification
        if response.status_code in (400, 401, 403):
            LOGGER.warning("Token expiré ou invalide (HTTP %s), réauthentification...", response.status_code)
            self.token = None
            if not self.login():
                return None

            try:
                with self._request_lock:
                    response = self.session.request(method, url, timeout=10, **kwargs)
            except requests.exceptions.RequestException as e:
                LOGGER.error("Erreur HTTP lors de la tentative après réauthentification : %s", e)
                return None

        return response


    def _send_action(self, device_id: str, action: str, args: dict = None) -> bool:
        """Envoie une action à un appareil

        Args:
            device_id: ID de l'objet
            action: Nom de l'action à effectuer
            args: Dictionnaire optionnel avec les arguments

        Returns:
            `True` si succès, sinon `False`
        """
        try:
            cloud_action = {"name": action}

            # Ajoute les arguments si fournis
            if args:
                cloud_action["mArgs"] = [
                    {"name": key, "value": str(value)}
                    for key, value in args.items()
                ]

            payload = {"actions": [cloud_action]}

            # Envoie la requête pour lancer l'action
            response = self._send_calypshome_request("PUT", f"/services/durin/my/objects/{device_id}", json=payload)
            if response is None:
                return False

            if 200 <= response.status_code < 300:
                LOGGER.debug("Action %s envoyée à %s", action, device_id)
                return True

            LOGGER.error("Erreur lors de l'envoi de l'action %s: HTTP %s", action, response.status_code)
            return False

        except requests.exceptions.RequestException as e:
            LOGGER.error("Erreur lors de l'envoi de l'action: %s", e)
            return False


    def login(self) -> bool:
        """S'authentifie auprès de l'API cloud
            
        Returns:
            `True` si l'authentification est réussie, sinon `False`
        """
        # On verrouille pour qu'un seul thread à la fois puisse tenter de se connecter
        with self._request_lock:
            if self.token:
                return True

            try:
                response = self.session.post(
                    url=f"{self.base_url}/services/dain/login", 
                    json={"login": self.email, "password": self.password}, 
                    timeout=10
                )
                response.raise_for_status()
                token = response.json().get("token")

                if token:
                    self.token = token
                    LOGGER.debug("Authentification cloud réussie pour %s", self.email)
                    return True

                LOGGER.error("Connexion cloud réussie mais aucun token retourné")
                return False
            except requests.exceptions.RequestException as e:
                LOGGER.error("Erreur lors de l'authentification auprès de l'API cloud: %s", e)
                return False


    def get_objects(self) -> list | None:
        """Récupère la liste de tous les objets
       
        Returns:
            Liste des objets si succès, sinon `None` 
        """
        # Récupération des objets depuis l'API cloud
        try:
            response = self._send_calypshome_request("GET", "/services/durin/my/objects?all")
            if response is None:
                return None

            # Lecture de la réponse et mise en cache
            response.raise_for_status()
            data = response.json()["content"]
            cover_data = [self._extract_object_from_response(obj) for obj in data]
            return [obj for obj in cover_data if obj is not None]
        except requests.exceptions.RequestException as e:
            LOGGER.error("Erreur lors de la récupération des objets: %s", e)
            return None


    def open_shutter(self, device_id: str) -> bool:
        """Ouvre un volet"""
        return self._send_action(device_id, "OPEN")

    def close_shutter(self, device_id: str) -> bool:
        """Ferme un volet"""
        return self._send_action(device_id, "CLOSE")

    def stop_shutter(self, device_id: str) -> bool:
        """Arrête un volet"""
        return self._send_action(device_id, "STOP")

    def set_level(self, device_id: str, level: int) -> bool:
        """Définit le niveau d'ouverture du volet"""
        return self._send_action(device_id, "LEVEL", {"level": level})


    async def start_websocket(self) -> None:
        """Démarre l'écoute websocket pour les mises à jour en temps réel"""
        if self._ws_client is None:
            # Import local pour éviter les imports circulaires au chargement du module
            from .websocket import CalypsHomeWebSocket
            self._ws_client = CalypsHomeWebSocket(self, self.on_update)
        else:
            self._ws_client.on_update = self.on_update

        await self._ws_client.start_websocket()


    def stop_websocket(self) -> None:
        """Arrête l'écoute websocket si elle est en cours"""
        if self._ws_client is not None:
            self._ws_client.stop_websocket()