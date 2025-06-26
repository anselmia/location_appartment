from django.db.models import Count


def get_partner_system_messages(user):
    """
    Retourne les messages système pour le tableau de bord du partenaire.
    """
    from activity.models import Activity

    if not user.is_authenticated:
        return []

    messages_system = []

    # Vérifie la présence d'un compte partenaire
    if not user.has_partners:
        messages_system.append(
            "Vous n'avez pas encore de compte partenaire. Veuillez en créer un pour accéder à votre tableau de bord."
        )
    elif not user.has_valid_partners:
        messages_system.append(
            "Votre compte partenaire est en attente de validation. Veuillez patienter pour accéder à votre tableau de bord."
        )

    # Vérifie la présence d'un compte Stripe
    if not user.has_stripe_account:
        messages_system.append(
            "Vous n'avez pas encore de compte Stripe. Veuillez en créer un pour recevoir vos paiements."
        )

    # Vérifie la présence d'activités
    if not user.has_activities:
        messages_system.append(
            "Vous n'avez pas encore d'activités. Veuillez en créer pour commencer à recevoir des réservations."
        )
    else:
        # Récupère les activités du partenaire
        activities = Activity.objects.filter(owner=user)

        # Activités non validées
        not_validated = activities.filter(validated=False)
        if not_validated.exists():
            messages_system.append(
                f"{not_validated.count()} activité(s) en attente de validation. Elles ne sont pas encore visibles par les voyageurs."
            )

        # Activités sans photo
        no_photo = activities.annotate(photo_count=Count("photos")).filter(photo_count=0)
        if no_photo.exists():
            messages_system.append(
                f"{no_photo.count()} activité(s) n'ont pas de photo. Ajoutez des photos pour attirer plus de voyageurs."
            )

        # Activités incomplètes (ajoute d'autres critères si besoin)
        incomplete = activities.filter(description__isnull=True) | activities.filter(description="")
        incomplete = incomplete.distinct()
        if incomplete.exists():
            messages_system.append(
                f"{incomplete.count()} activité(s) n'ont pas de description. Complétez-les pour améliorer leur attractivité."
            )

        # Activités désactivées
        disabled = activities.filter(active=False)
        if disabled.exists():
            messages_system.append(
                f"{disabled.count()} activité(s) sont désactivées et ne peuvent pas recevoir de réservations."
            )

    return messages_system
