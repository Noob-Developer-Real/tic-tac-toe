from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
import json
import time
import re
import random

GAME_STATE = {}
ROOM_TTL = 60


def safe_group_name(room_code: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", room_code)
    return f"room_{cleaned}"[:99]


def check_winner(board):
    wins = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    ]
    for a, b, c in wins:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "DRAW"
    return None


def reshuffle_players(state):
    """
    Randomly assign X and O.
    Runs ONLY when exactly two connections exist.
    """
    if len(state["connections"]) != 2:
        return

    usernames = list(state["connections"].values())
    random.shuffle(usernames)

    state["players"] = {
        "X": usernames[0],
        "O": usernames[1],
    }
    state["turn"] = random.choice(["X", "O"])


class Gameroom(WebsocketConsumer):

    def connect(self):
        from home.models import Game

        self.room_code = self.scope["url_route"]["kwargs"]["room_code"]
        self.room_group = safe_group_name(self.room_code)

        query = self.scope["query_string"].decode()
        if "username=" not in query:
            self.close()
            return

        self.username = query.split("username=")[-1]

        game = Game.objects.filter(room_code=self.room_code).first()
        if not game:
            self.close()
            return

        state = GAME_STATE.setdefault(self.room_code, {
            "connections": {},          # channel_name -> username
            "players": {},              # {"X": username, "O": username}
            "board": [None] * 9,
            "turn": None,
            "winner": None,
            "started": False,
            "finished_at": None,
            "scores": {"X": 0, "O": 0},
            "winning_cells": [],
        })

        # Only 2 players allowed
        if len(state["connections"]) >= 2:
            self.close()
            return

        state["connections"][self.channel_name] = self.username

        # Start game when second player joins
        if len(state["connections"]) == 2:
            reshuffle_players(state)
            state["started"] = True

        async_to_sync(self.channel_layer.group_add)(
            self.room_group,
            self.channel_name,
        )

        self.accept()

        self.send(json.dumps({
            "type": "init",
            "username": self.username,
        }))

        self.broadcast_state()

    def disconnect(self, close_code):
        from home.models import Game

        async_to_sync(self.channel_layer.group_discard)(
            self.room_group,
            self.channel_name,
        )

        state = GAME_STATE.get(self.room_code)
        if not state:
            Game.objects.filter(room_code=self.room_code).delete()
            return

        state["connections"].pop(self.channel_name, None)

        # Reset game if a player leaves
        state["players"] = {}
        state["started"] = False
        state["turn"] = None

        if not state["connections"]:
            GAME_STATE.pop(self.room_code, None)
            Game.objects.filter(room_code=self.room_code).delete()

    def receive(self, text_data):
        from home.models import Game

        data = json.loads(text_data)
        state = GAME_STATE.get(self.room_code)
        if not state:
            return

        # 🔄 RESET ROUND
        if data.get("action") == "reset":
            if state["winner"] is None:
                return

            if len(state["connections"]) == 2:
                reshuffle_players(state)
                state["started"] = True
            else:
                state["started"] = False

            state.update({
                "board": [None] * 9,
                "winner": None,
                "winning_cells": [],
                "finished_at": None,
            })

            self.broadcast_state()
            return

        # 🎯 PLAYER MOVE
        index = data.get("move")
        if index is None or not (0 <= index <= 8):
            return
        if not state["started"] or state["winner"]:
            return
        if state["board"][index] is not None:
            return

        # Resolve symbol dynamically
        player_symbol = None
        for symbol, username in state["players"].items():
            if username == self.username:
                player_symbol = symbol
                break

        if player_symbol != state["turn"]:
            return

        state["board"][index] = player_symbol
        state["turn"] = "O" if player_symbol == "X" else "X"

        winner = check_winner(state["board"])
        if winner:
            state["winner"] = winner
            state["finished_at"] = time.time()

            if winner != "DRAW":
                state["scores"][winner] += 1

            Game.objects.filter(room_code=self.room_code).delete()

        self.broadcast_state()

    def broadcast_state(self):
        state = GAME_STATE.get(self.room_code)
        if not state:
            return

        async_to_sync(self.channel_layer.group_send)(
            self.room_group,
            {
                "type": "game_update",
                "state": state,
            }
        )

        if state["winner"] and state["finished_at"]:
            if time.time() - state["finished_at"] > ROOM_TTL:
                GAME_STATE.pop(self.room_code, None)

    def game_update(self, event):
        self.send(json.dumps({
            "type": "state",
            "state": event["state"],
        }))
