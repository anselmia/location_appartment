from django.contrib.auth.decorators import user_passes_test, login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from logement.models import Logement, Room, Photo
from .forms import LogementForm


def is_admin(user):
    return user.is_authenticated and user.is_admin  # or use a custom flag


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    logements = Logement.objects.all()
    return render(request, "administration/dashboard.html", {"logements": logements})


@login_required
@user_passes_test(is_admin)
def add_logement(request):
    if request.method == "POST":
        form = LogementForm(request.POST)
        if form.is_valid():
            logement = form.save()
            return redirect("administration:edit_logement", logement.id)
    else:
        form = LogementForm()
    return render(request, "administration/add_logement.html", {"form": form})


@login_required
@user_passes_test(is_admin)
def edit_logement(request, logement_id):
    logement = Logement.objects.prefetch_related("photos").first()
    rooms = logement.rooms.all()
    photos = logement.photos.all()

    if request.method == "POST":
        form = LogementForm(request.POST, instance=logement)
        if form.is_valid():
            form.save()
            return redirect("administration:dashboard")
    else:
        form = LogementForm(instance=logement)

    return render(
        request,
        "administration/edit_logement.html",
        {"form": form, "logement": logement, "rooms": rooms, "photos": photos},
    )


@login_required
@user_passes_test(is_admin)
def add_room(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)
    Room.objects.create(name=request.POST["name"], logement=logement)
    return redirect("administration:edit_logement", logement_id)


@login_required
@user_passes_test(is_admin)
@require_POST
def delete_room(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    logement_id = room.logement.id
    room.delete()
    return redirect("administration:edit_logement", logement_id)


@login_required
@user_passes_test(is_admin)
@require_POST
def upload_photos(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)
    room_id = request.POST.get("room_id")
    room = (
        Room.objects.filter(id=room_id, logement=logement).first() if room_id else None
    )

    for uploaded_file in request.FILES.getlist("photo"):
        Photo.objects.create(logement=logement, room=room, image=uploaded_file)
    return redirect("administration:edit_logement", logement_id)


# Change the room of a photo
@login_required
@user_passes_test(is_admin)
def change_photo_room(request, photo_id):
    if request.method == "POST":
        photo = get_object_or_404(Photo, id=photo_id)
        room_id = request.POST.get("room_id")
        room = get_object_or_404(Room, id=room_id)
        photo.room = room
        photo.save()
        return JsonResponse({"success": True})


# Move photo up or down
@login_required
@user_passes_test(is_admin)
def move_photo(request, photo_id, direction):
    if request.method == "POST":
        photo = get_object_or_404(Photo, id=photo_id)
        if direction == "up":
            previous_photo = Photo.objects.filter(order__lt=photo.order).last()
            if previous_photo:
                photo.order, previous_photo.order = previous_photo.order, photo.order
                photo.save()
                previous_photo.save()
        elif direction == "down":
            next_photo = Photo.objects.filter(order__gt=photo.order).first()
            if next_photo:
                photo.order, next_photo.order = next_photo.order, photo.order
                photo.save()
                next_photo.save()
        return JsonResponse({"success": True})


# Delete photo
@login_required
@user_passes_test(is_admin)
def delete_photo(request, photo_id):
    if request.method == "DELETE":
        photo = get_object_or_404(Photo, id=photo_id)
        photo.delete()
        return JsonResponse({"success": True})
