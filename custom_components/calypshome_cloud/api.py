import urllib3
import requests
import threading
from requests.adapters import HTTPAdapter
from collections.abc import Awaitable, Callable

from .const import DEFAULT_CLOUD_URL, LOGGER

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        self._request_lock = threading.Lock()
        self.on_update: Callable[[dict | None], Awaitable[None]] | None = None
        self._ws_client = None

        # Initialisation de la session HTTP avec un pool de connexions
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.headers["Accept"] = "application/json"


    def _extract_object_from_response(self, response: dict) -> dict | None:
        """Extrait les informations d'un objet depuis la réponse de l'API
        
        Args:
            response: Dictionnaire JSON de la réponse de l'API
            
        Returns:
            Dictionnaire avec les informations de l'objet ou `None` en cas d'erreur
        """
        try:
            object = response["resource"]
            return {
                "id": object["id"],
                "name": object["name"],
                "className": object["className"],
                "realName": object["realName"],
                "statuses": object.get("statuses", [])
            }
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

        # Envoie la requête avec verrouillage pour éviter les conflits de session
        with self._request_lock:
            response = self.session.request(method, url, **kwargs)

        # Si le token est expiré ou invalide, réessaye après réauthentification
        if response.status_code in (400, 401, 403):
            LOGGER.warning("Token expiré ou invalide (HTTP %s), réauthentification...", response.status_code)
            self.token = None
            if not self.login():
                return None

            with self._request_lock:
                response = self.session.request(method, url, **kwargs)

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
        if self.token:
            return True
        
        try:
            # Requête d'authentification pour obtenir un token
            response = self.session.post(url=f"{self.base_url}/services/dain/login", json={"login": self.email, "password": self.password})
            response.raise_for_status()
            token = response.json()["token"]

            # Récupération du token dans la réponse
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
            return cover_data
        except requests.exceptions.RequestException as e:
            LOGGER.error("Erreur lors de la récupération des objets: %s", e)
            return None


    def get_object(self, device_id: str) -> dict | None:
        """Récupère l'état actuel d'un objet unique
        
        Args:
            device_id: ID de l'objet
        
        Returns:
            L'objet si succès, sinon `None`
        """
        # Envoie la requête pour récupérer l'objet
        try:
            response = self._send_calypshome_request("GET", f"/services/durin/my/objects/{device_id}")
            if response is None:
                return None

            response.raise_for_status()
            object = self._extract_object_from_response(response.json())
            return object
        except requests.exceptions.RequestException as e:
            LOGGER.error("Erreur lors de la récupération de l'objet %s: %s", device_id, e)
            return None


    def open_shutter(self, device_id: str) -> bool:
        """Ouvre un volet
        
        Args:
            device_id: ID de l'objet
            
        Returns:
            `True` si succès, sinon `False`
        """
        return self._send_action(device_id, "OPEN")

    def close_shutter(self, device_id: str) -> bool:
        """Ferme un volet
            
        Args:
            device_id: ID de l'objet
            
        Returns:
            `True` si succès, sinon `False`
        """
        return self._send_action(device_id, "CLOSE")

    def stop_shutter(self, device_id: str) -> bool:
        """Arrête un volet
            
        Args:
            device_id: ID de l'objet
            
        Returns:
            `True` si succès, sinon `False`
        """
        return self._send_action(device_id, "STOP")

    def set_level(self, device_id: str, level: int) -> bool:
        """Définit le niveau d'ouverture du volet (0-100)
            
        Args:
            device_id: ID de l'objet
            level: Niveau d'ouverture (0-100)
            
        Returns:
            `True` si succès, sinon `False`
        """
        return self._send_action(device_id, "LEVEL", {"level": level})


    async def start_websocket(self) -> None:
        """Démarre l'écoute websocket pour les mises à jour en temps réel"""
        if self._ws_client is None:
            # Import local pour éviter les imports circulaires au chargement du module.
            from .websocket import CalypsHomeWebSocket

            self._ws_client = CalypsHomeWebSocket(self, self.on_update)
        else:
            self._ws_client.set_on_update(self.on_update)

        await self._ws_client.start_websocket()


    def stop_websocket(self) -> None:
        """Arrête l'écoute websocket si elle est en cours"""
        if self._ws_client is not None:
            self._ws_client.stop_websocket()