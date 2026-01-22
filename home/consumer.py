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
        (0,1,2),(3,4,5),(6,7,8),
        (0,3,6),(1,4,7),(2,5,8),
        (0,4,8),(2,4,6),
    ]
    for a, b, c in wins:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "DRAW"
    return None


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

        # 🔹 INITIAL GAME STATE
        state = GAME_STATE.setdefault(self.room_code, {
            "players": {},
            "board": [None] * 9,
            "turn": None,              
            "winner": None,
            "started": False,
            "finished_at": None,
            "scores": {"X": 0, "O": 0},
            "winning_cells": [],
        })

        # 🔹 PLAYER ASSIGNMENT
        if "X" not in state["players"]:
            self.symbol = "X"
            state["players"]["X"] = self.username

        elif "O" not in state["players"]:
            self.symbol = "O"
            state["players"]["O"] = self.username

            # ✅ GAME STARTS HERE
            state["started"] = True
            state["turn"] = random.choice(["X", "O"])  # 🎲 RANDOM FIRST TURN

        else:
            self.close()
            return

        async_to_sync(self.channel_layer.group_add)(
            self.room_group,
            self.channel_name,
        )

        self.accept()

        # 🔹 SEND PLAYER SYMBOL
        self.send(json.dumps({
            "type": "init",
            "symbol": self.symbol,
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

        state["players"].pop(self.symbol, None)

        if not state["players"]:
            GAME_STATE.pop(self.room_code, None)
            Game.objects.filter(room_code=self.room_code).delete()

    def receive(self, text_data):
        from home.models import Game

        data = json.loads(text_data)
        state = GAME_STATE.get(self.room_code)
        if not state:
            return

        # 🔄 RESET GAME
        if data.get("action") == "reset":
            if state["winner"] is None:
                return

            state.update({
                "board": [None] * 9,
                "winner": None,
                "turn": random.choice(["X", "O"]),  # 🎲 RANDOM AGAIN
                "started": len(state["players"]) == 2,
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
        if self.symbol != state["turn"]:
            return
        if state["board"][index] is not None:
            return

        state["board"][index] = self.symbol
        state["turn"] = "O" if self.symbol == "X" else "X"

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
