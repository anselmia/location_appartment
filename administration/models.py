from django.db import models


class Entreprise(models.Model):
    contact_address = models.CharField(max_length=255, blank=True, null=True)
    contact_phone = models.CharField(max_length=30, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    linkedin = models.URLField(blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)
    logo = models.ImageField(
        upload_to="administration/", blank=True, null=True
    )


class SiteVisit(models.Model):
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    path = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)


class HomePageConfig(models.Model):
    nom = models.CharField(max_length=100, default="Votre Nom de Conciergerie")
    devise = models.CharField(max_length=255, default="Votre slogan ici")
    banner_image = models.ImageField(
        upload_to="administration/", blank=True, null=True
    )
    description = models.TextField(default="")
    primary_color = models.CharField(max_length=7, default="#ff385c")
    font_family = models.CharField(max_length=100, default="'Poppins', sans-serif")
    cta_text = models.CharField(max_length=100, default="Découvrir nos logements")
    contact_title = models.CharField(max_length=100, default="Contactez-nous")

    def __str__(self):
        return "Configuration de la page d’accueil"


class Service(models.Model):
    config = models.ForeignKey(
        HomePageConfig, on_delete=models.CASCADE, related_name="services"
    )
    icon_class = models.CharField(max_length=50, default="fas fa-star")
    description = models.TextField(blank=True, null=True)
    title = models.CharField(max_length=100)
    background_image = models.ImageField(
        upload_to="administration/", blank=True, null=True
    )

    def __str__(self):
        return self.title


class Testimonial(models.Model):
    config = models.ForeignKey(
        HomePageConfig, on_delete=models.CASCADE, related_name="testimonials"
    )
    content = models.TextField()

    def __str__(self):
        return f"Avis: {self.content[:40]}..."


class Commitment(models.Model):
    config = models.ForeignKey(
        HomePageConfig, on_delete=models.CASCADE, related_name="commitments"
    )
    title = models.CharField(max_length=100, default="")
    text = models.CharField(max_length=255)
    background_image = models.ImageField(
        upload_to="administration/", blank=True, null=True
    )

    def __str__(self):
        return f"Engagement: {self.text[:40]}..."
