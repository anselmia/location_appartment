from icalendar import Calendar, Event
from datetime import datetime
from django.utils.timezone import make_aware
from logement.models import Reservation
import logging

logger = logging.getLogger(__name__)


def generate_ical():
    try:
        cal = Calendar()
        cal.add("prodid", "-//valrose.home-arnaud.ovh//iCal export//FR")
        cal.add("version", "2.0")

        reservations = Reservation.objects.filter(statut="confirmee")
        logger.info(f"{reservations.count()} réservations exportées vers iCal")

        for res in reservations:
            event = Event()
            event.add("summary", "Reserved")
            event.add(
                "dtstart", make_aware(datetime.combine(res.start, datetime.min.time()))
            )
            event.add(
                "dtend", make_aware(datetime.combine(res.end, datetime.min.time()))
            )
            event.add("dtstamp", datetime.now())
            event["uid"] = f"{res.code}"
            cal.add_component(event)

        return cal.to_ical()

    except Exception as e:
        logger.exception("Erreur lors de la génération du fichier iCal")
        raise e
