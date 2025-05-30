from twilio.rest import Client
import logging
import re
import requests

from django.conf import settings

logger = logging.getLogger(__name__)

SMSAPIAUTH_TOKEN = settings.SMSAPIAUTH_TOKEN


def normalize_french_phone(phone: str) -> str:
    """
    Convertit un numéro français local (06..., 07...) en format international +33
    """
    phone = phone.strip().replace(" ", "").replace(".", "").replace("-", "")
    if phone.startswith("0") and len(phone) == 10:
        return "+33" + phone[1:]
    elif phone.startswith("+33") and len(phone) == 12:
        return phone
    else:
        return None  # Format non reconnu


def is_valid_number(phone: str) -> bool:
    phone = normalize_french_phone(phone)
    if not phone:
        return False
    return re.match(r"^\+33\d{9}$", phone) is not None


def send_sms(to_number: str, message: str) -> bool:
    phone = normalize_french_phone(to_number)
    if not is_valid_number(phone):
        logger.warning(f"Numéro invalide : {to_number}")
        return False

    url = "https://api.smsapi.com/sms.do"
    headers = {"Authorization": f"Bearer {SMSAPIAUTH_TOKEN}"}
    payload = {
        "to": phone,
        "message": message,
        "sender": "SMSAPI",  # ⚠️ ce champ doit être validé dans ton compte SMSAPI
        "format": "json",
    }

    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        result = response.json()

        error = result.get("error")
        if error not in [None, 0]:
            logger.error(f"Erreur SMSAPI ({error}) lors de l’envoi à {phone} : {result.get('message')}")
            return False

        logger.info(f"SMS envoyé à {phone} : {result}")
        return True

    except requests.exceptions.RequestException as e:
        logger.error(f"[HTTP] Erreur de requête SMSAPI vers {phone} : {e}")
    except ValueError as e:
        logger.error(f"[JSON] Réponse invalide de SMSAPI lors de l’envoi à {phone} : {e}")
    except Exception as e:
        logger.error(f"[GENERIC] Erreur inattendue lors de l’envoi SMS à {phone} : {e}")

    return False
