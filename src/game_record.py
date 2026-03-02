"""game_record.py — move format, serialization, and game record for Cube Roller."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, asdict
from typing import Optional


@dataclass
class Move:
    turn: int           # sequential action counter (1-based)
    player: int         # 1 or 2
    move_type: str      # 'build' | 'add_side' | 'deploy' | 'roll' | 'end_turn'

    # build / add_side / deploy
    cube_index: Optional[int] = None    # index in player.cubes

    # add_side only
    face: Optional[str] = None          # logic face: u/d/f/b/l/r
    effect: Optional[str] = None        # effect name
    rotation: int = 0                   # 0 / 90 / 180 / 270

    # deploy / roll
    pos_x: Optional[int] = None         # board column
    pos_y: Optional[int] = None         # board row

    # roll only
    direction: Optional[str] = None     # up / down / left / right
    trigger_ability: bool = False
    action_dir: Optional[tuple] = None  # (dx, dy) for slide s2 / grapple s2
    rotate_dir: Optional[str] = None    # cw / ccw for rotate effect

    def to_dict(self) -> dict:
        """Serialise to a compact dict, omitting None / False / 0 defaults."""
        result = {}
        for f in fields(self):
            val = getattr(self, f.name)
            # Always keep the three required fields
            if f.name in ('turn', 'player', 'move_type'):
                result[f.name] = val
                continue
            # Omit None
            if val is None:
                continue
            # Omit False
            if isinstance(val, bool) and not val:
                continue
            # Omit 0 for rotation (the default)
            if f.name == 'rotation' and val == 0:
                continue
            # Convert tuple to list for JSON compatibility
            if isinstance(val, tuple):
                val = list(val)
            result[f.name] = val
        return result

    @classmethod
    def from_dict(cls, data: dict) -> 'Move':
        """Deserialise from dict, restoring defaults for missing fields."""
        kwargs = dict(data)
        # Restore action_dir as tuple if present
        if 'action_dir' in kwargs and kwargs['action_dir'] is not None:
            kwargs['action_dir'] = tuple(kwargs['action_dir'])
        return cls(**kwargs)


class GameRecord:
    FORMAT_VERSION = '1.0'

    def __init__(self, p1_factories: list, p2_factories: list):
        # Store as lists of lists for JSON compatibility
        self.p1_factories = [list(f) for f in p1_factories]
        self.p2_factories = [list(f) for f in p2_factories]
        self.moves: list[Move] = []
        self._turn = 0

    def record(self, player: int, move_type: str, **kwargs) -> Move:
        """Increment turn counter, build Move, append and return it."""
        self._turn += 1
        move = Move(turn=self._turn, player=player, move_type=move_type, **kwargs)
        self.moves.append(move)
        return move

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            'format_version': self.FORMAT_VERSION,
            'p1_factories': self.p1_factories,
            'p2_factories': self.p2_factories,
            'moves': [m.to_dict() for m in self.moves],
        }

    def to_json(self, indent: int = 2) -> str:
        """Return formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str):
        """Write JSON to file."""
        with open(path, 'w') as fh:
            fh.write(self.to_json())

    @classmethod
    def from_dict(cls, data: dict) -> 'GameRecord':
        """Deserialise from dict."""
        record = cls(
            p1_factories=data['p1_factories'],
            p2_factories=data['p2_factories'],
        )
        for move_data in data.get('moves', []):
            move = Move.from_dict(move_data)
            record.moves.append(move)
            record._turn = move.turn
        return record

    @classmethod
    def load(cls, path: str) -> 'GameRecord':
        """Load from JSON file."""
        with open(path) as fh:
            data = json.load(fh)
        return cls.from_dict(data)
