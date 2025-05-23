from django.shortcuts import render


def is_admin(user):
    return user.is_authenticated and (
        getattr(user, "is_admin", False) or user.is_superuser
    )


def cgu_view(request):
    return render(request, "common/cgu.html")


def confidentiality_view(request):
    return render(request, "common/confidentiality.html")


def cgv_view(request):
    return render(request, "common/cgv.html")
