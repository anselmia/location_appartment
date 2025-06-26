from django.db.models import Count

def get_conciergerie_system_messages(user):
    """
    Retourne les messages système pour le tableau de bord du conciergerie.
    """
    from logement.models import Logement

    if not user.is_authenticated:
        return []

    messages_system = []

    # Vérifie la présence d'un compte conciergerie
    if not user.has_conciergerie:
        messages_system.append(
            "Vous n'avez pas encore de compte conciergerie. Veuillez en créer un pour accéder à votre tableau de bord."
        )
    elif not user.has_valid_conciergerie:
        messages_system.append(
            "Votre compte conciergerie est en attente de validation. Veuillez patienter pour accéder à votre tableau de bord."
        )

    # Vérifie la présence d'un compte Stripe
    if not user.has_stripe_account:
        messages_system.append(
            "Vous n'avez pas encore de compte Stripe. Veuillez en créer un pour recevoir vos paiements."
        )

    # Vérifie la présence de logements
    if not user.has_logements:
        messages_system.append(
            "Vous n'avez pas encore de logements. Veuillez attendre qu'un propriétaire vous ajoute."
        )
    else:
        # Récupère les logements de l'utilisateur
        logements = Logement.objects.filter(admin=user)

        # Logement fermés
        closed = logements.filter(statut="close")
        if closed.exists():
            messages_system.append(
                f"{closed.count()} logement(s) fermé(s). Ils ne sont pas encore visibles par les voyageurs."
            )

        # Logements sans photo
        no_photo = logements.annotate(photo_count=Count("photos")).filter(photo_count=0)
        if no_photo.exists():
            messages_system.append(
                f"{no_photo.count()} logement(s) n'ont pas de photo. Ajoutez des photos pour attirer plus de voyageurs."
            )


        # Logements incomplets (ajoute d'autres critères si besoin)
        incomplete = logements.filter(description__isnull=True) | logements.filter(description="")
        incomplete = incomplete.distinct()
        if incomplete.exists():
            messages_system.append(
                f"{incomplete.count()} logement(s) n'ont pas de description. Complétez-les pour améliorer leur attractivité."
            )

    return messages_system
