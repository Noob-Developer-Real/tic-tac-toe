from django.contrib import admin
from .models import *
# Register your models here.
@admin.register(Game)
class Games(admin.ModelAdmin):
    list_display = ('room_code', 'game_creator', 'game_opponent')
    search_fields = ('room_code', 'game_creator', 'game_opponent')
