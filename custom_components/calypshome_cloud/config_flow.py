import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_LOGIN, CONF_PASSWORD, LOGGER

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOGIN): str,
        vol.Required(CONF_PASSWORD): str
    }
)


async def validate_input(hass: HomeAssistant, data: dict) -> dict[str, str]:
    """Valide que l'entrée utilisateur permet de se connecter"""
    from .api import CalypsHomeAPI

    api = CalypsHomeAPI(data[CONF_LOGIN], data[CONF_PASSWORD])

    try:
        authenticated = await hass.async_add_executor_job(api.login)
        if not authenticated:
            raise Exception("Authentification échouée")

        objects = await hass.async_add_executor_job(api.get_objects)
        if objects is None:
            raise Exception("Impossible de récupérer les objets")
    except Exception as err:
        LOGGER.error("Erreur lors de la connexion à Calyps'HOME: %s", err)
        raise

    return {"title": f"Calyps'HOME"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gère un flux de configuration pour Calyps'HOME"""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, str] | None = None) -> FlowResult:
        """Gère l'étape initiale"""
        
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Valider la configuration
                info = await validate_input(self.hass, user_input)
            except Exception:
                LOGGER.exception("Exception inattendue")
                errors["base"] = "cannot_connect"
            else:
                # Créer l'entrée de configuration
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)