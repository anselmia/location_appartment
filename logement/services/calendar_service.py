from icalendar import Calendar, Event
from datetime import datetime
from django.utils.timezone import make_aware
from django.shortcuts import get_object_or_404
from logement.models import Reservation, Logement
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def generate_ical(code):
    try:
        logement = get_object_or_404(Logement, code=code)

        cal = Calendar()
        cal.add("prodid", f"-//{settings.DOMAIN}//iCal export//FR")
        cal.add("version", "2.0")

        reservations = Reservation.objects.filter(logement=logement, statut="confirmee")
        logger.info(f"{reservations.count()} réservations exportées vers iCal")

        for res in reservations:
            event = Event()
            event.add("summary", "Reserved")
            event.add("dtstart", make_aware(datetime.combine(res.start, datetime.min.time())))
            event.add("dtend", make_aware(datetime.combine(res.end, datetime.min.time())))
            event.add("dtstamp", datetime.now())
            event["uid"] = f"{res.code}"
            cal.add_component(event)

        return cal.to_ical()

    except Exception as e:
        logger.exception("Erreur lors de la génération du fichier iCal")
        raise e
