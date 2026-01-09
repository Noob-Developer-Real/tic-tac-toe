from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Game


def home(request):
    if request.method == "POST":
        username = request.POST.get("username")
        option = request.POST.get("option")
        room_code = request.POST.get("room_code")

        if not username or not room_code:
            messages.error(request, "Invalid input")
            return redirect("/")

        # JOIN ROOM
        if option == "1":
            game = Game.objects.filter(room_code=room_code).first()

            if game is None:
                messages.error(request, "Room not found")
                return redirect("/")

            # ❌ NO is_over checks anymore
            game.game_opponent = username
            game.save()

            return redirect(f"/game/{room_code}?username={username}")

        # CREATE ROOM
        if option == "2":
            Game.objects.get_or_create(
                room_code=room_code,
                defaults={"game_creator": username}
            )

            return redirect(f"/game/{room_code}?username={username}")

    return render(request, "home/home.html")


def play(request, room_code):
    username = request.GET.get("username")

    if not username:
        return redirect(f"/?room={room_code}")

    return render(
        request,
        "home/play.html",
        {
            "room_code": room_code,
            "username": username,
        },
    )
