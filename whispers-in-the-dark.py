#!/usr/bin/env python3
"""
Whispers in the Dark — a 2D psychological-horror platformer.

Run:  python whispers-in-the-dark.py
Dependencies: pygame (or pygame-ce on Python 3.14+).

One file.  No external assets — everything is drawn with pygame primitives
so the game is 100 % self-contained.

Style
- Dark, muted palette, deep blacks & heavy silhouettes.
- Flickering fluorescent lights, fog particles, distant machinery.
- A creature that stalks the player: hears, glimpses, then (rarely) chases.

Controls
  WASD / arrows   move
  SPACE / W / ↑   jump
  S / ↓           crouch (slip under low barriers, quieter)
  E               interact / climb ladder / read notes
  SHIFT           walk quietly (reduces creature detection)
  R               restart from last checkpoint
  Esc             quit
"""
from __future__ import annotations
import math
import random
import sys

import pygame

# ────────────────────────────── config ────────────────────────────────────
WIN = WIDTH, HEIGHT = 960, 540
FPS = 60
TITLE = "Whispers in the Dark"

# colours — deep, desaturated, almost monochromatic
BLACK      = (8, 8, 12)
DARK       = (16, 16, 24)
GRAY       = (40, 42, 52)
DIM_GRAY   = (55, 58, 70)
MID_GRAY   = (90, 94, 110)
LT_GRAY    = (160, 165, 180)
WHITE      = (210, 212, 225)
OFF_WHITE  = (190, 192, 205)

# accent colours
FLOOR_LIT  = (120, 110, 140, 60)
SWITCH_ON  = (140, 200, 255)
SWITCH_OFF = (60, 70, 90)
DOOR_COL   = (55, 48, 66)
LOCKED     = (120, 40, 50)
KEY_GOLD   = (220, 190, 80)
BATTERY    = (120, 180, 120)
NOTE_PAPER = (170, 170, 140)
CHASE_RED  = (200, 50, 60)

# player
PLAYER_W, PLAYER_H = 18, 34
PLAYER_SPEED = 170
PLAYER_JUMP = 470
GRAVITY = 1500
MAX_FALL = 700

# creature
CREATURE_W, CREATURE_H = 26, 38
CREATURE_SPEED = 70   # slower stalker

# light
TORCH_RADIUS = 180
TORCH_FALLOFF = 90 + 90  # inner + outer

# ────────────────────────────── helpers ───────────────────────────────────


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def noise(x, y, t):
    """Fast fake-noise for fog / light flicker."""
    return (math.sin(x * 0.13 + t * 0.7) + math.cos(y * 0.17 + t * 0.5)
            + math.sin((x + y) * 0.07 - t * 0.3)) * 0.33 + 0.5


# ─────────────────────────────── entities ──────────────────────────────────


class Entity:
    """Minimal moving-rectangle with AABB collision against tiles."""

    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.vx = 0.0
        self.vy = 0.0

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def move(self, dt, tilemap):
        self.vy = clamp(self.vy + GRAVITY * dt, -MAX_FALL, MAX_FALL)
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        landed = False

        # ── Y collision ──
        if self.vy != 0:
            r = pygame.Rect(nx, ny, self.w, self.h)
            # check tiles that overlap the new Y position
            left = int(nx // tilemap.ts)
            right = int((nx + self.w) // tilemap.ts)
            top = int(min(self.y, ny) // tilemap.ts)
            bottom = int(max(self.y + self.h, ny + self.h) // tilemap.ts)
            for ty in range(top - 1, bottom + 2):
                for tx in range(left - 1, right + 2):
                    if tilemap.solid_at(tx, ty):
                        tile = pygame.Rect(
                            tx * tilemap.ts, ty * tilemap.ts,
                            tilemap.ts, tilemap.ts)
                        if r.colliderect(tile):
                            if self.vy > 0 and self.y + self.h <= tile.top + 2:
                                # landing on top
                                ny = tile.top - self.h
                                self.vy = 0
                                landed = True
                            elif self.vy < 0 and self.y >= tile.bottom - 2:
                                # hit head
                                ny = tile.bottom
                                self.vy = 0
            # low wall head bump (only if not crouching)
            if not getattr(self, 'crouching', False):
                for lw in tilemap.low_walls:
                    if lw.colliderect(r):
                        if self.vy < 0 and self.y >= lw.bottom - 2:
                            # hit the low wall from below
                            ny = lw.bottom
                            self.vy = 0

        # ── X collision (re-check with resolved ny) ──
        if self.vx != 0:
            r = pygame.Rect(nx, ny, self.w, self.h)
            left = int(min(self.x, nx) // tilemap.ts)
            right = int(max(self.x + self.w, nx + self.w) // tilemap.ts)
            top = int(ny // tilemap.ts)
            bottom = int((ny + self.h) // tilemap.ts)
            for ty in range(top - 1, bottom + 2):
                for tx in range(left - 1, right + 2):
                    if tilemap.solid_at(tx, ty):
                        tile = pygame.Rect(
                            tx * tilemap.ts, ty * tilemap.ts,
                            tilemap.ts, tilemap.ts)
                        if r.colliderect(tile):
                            if self.vx > 0:
                                nx = tile.left - self.w
                            elif self.vx < 0:
                                nx = tile.right
                            self.vx = 0
            # low wall horizontal collision (only if not crouching)
            if not getattr(self, 'crouching', False):
                for lw in tilemap.low_walls:
                    if lw.colliderect(r):
                        if self.vx > 0:
                            nx = lw.left - self.w
                        elif self.vx < 0:
                            nx = lw.right
                        self.vx = 0

        self.x = nx
        self.y = ny

        # collect hits for backward compat
        hits = [w for w in tilemap.walls if w.colliderect(self.rect)]
        return hits, landed


class Player(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, PLAYER_W, PLAYER_H)
        self.facing = 1
        self.on_ground = False
        self.battery = 3
        self.invuln = 0.0

        # crouch
        self.crouching = False
        self.crouch_timer = 0.0

    def handle(self, keys, dt, tilemap):
        # safe key check — array may not have scancodes we expect
        def kp(k):
            try:
                return keys[k]
            except IndexError:
                return False
        # crouch detection
        self.crouching = kp(pygame.K_s) or kp(pygame.K_DOWN)
        # crouch: halve height, can't jump, move at 60% speed
        if self.crouching:
            effective_h = PLAYER_H // 2
            effective_speed = PLAYER_SPEED * 0.6
        else:
            effective_h = PLAYER_H
            effective_speed = PLAYER_SPEED * (0.5 if kp(pygame.K_LSHIFT) or
                                              kp(pygame.K_RSHIFT) else 1.0)
        self.vx = 0
        if kp(pygame.K_a) or kp(pygame.K_LEFT):
            self.vx = -effective_speed
            self.facing = -1
        if kp(pygame.K_d) or kp(pygame.K_RIGHT):
            self.vx = effective_speed
            self.facing = 1
        # full air control: can change direction mid-jump (no penalty)
        # jump (normal)
        if (kp(pygame.K_SPACE) or kp(pygame.K_w) or
                kp(pygame.K_UP)) and self.on_ground and not self.crouching:
            self.vy = -PLAYER_JUMP
            self.on_ground = False
        # wall jump: if touching a wall mid-air, jump off it
        if (kp(pygame.K_SPACE) or kp(pygame.K_w) or
                kp(pygame.K_UP)) and not self.on_ground and not self.crouching:
            # check if touching a wall on the side we're moving toward
            for wall in tilemap.walls:
                if self.vx > 0 and abs(self.x + self.w - wall.left) < 6:
                    # wall on the right — jump away left
                    self.vy = -PLAYER_JUMP * 0.85
                    self.vx = -PLAYER_JUMP * 0.6
                    self.facing = -1
                    break
                elif self.vx < 0 and abs(wall.right - self.x) < 6:
                    # wall on the left — jump away right
                    self.vy = -PLAYER_JUMP * 0.85
                    self.vx = PLAYER_JUMP * 0.6
                    self.facing = 1
                    break
        # adjust the player rect height for collision when crouching
        original_h = self.h
        self.h = effective_h
        hits, landed = self.move(dt, tilemap)
        self.h = original_h
        self.on_ground = landed


class Creature:
    """The stalker.  Roams between patrol nodes when idle, dashes when
    alerted.  Visibility is determined by simple LOS ray-marching."""

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.w = CREATURE_W
        self.h = CREATURE_H
        self.state = "hidden"  # hidden / patrol / chase
        self.alert = 0.0
        self.target = (x, y)
        self.phase = 0  # chase intensity 0..1
        self.seen_time = 0.0
        self.speed = CREATURE_SPEED
        self.target_area = None

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def update(self, dt, player_x, player_y, area):
        match self.state:
            case "hidden":
                # invisible, just following the player
                self.x = player_x + 60 * getattr(player_x and 1, 'facing', 1) * 0 - player_x * 0 + player_x  # stays near player
                # simpler: hover behind player
                pass
            case "patrol":
                if self.target_area:
                    tx, ty = self.target
                    dx, dy = tx - self.x, ty - self.y
                    d = math.hypot(dx, dy)
                    if d < 4:
                        if area.spawn_points:
                            self.target = random.choice(area.spawn_points)
                    elif d > 0:
                        self.x += dx / d * self.speed * 0.4 * dt
                        self.y += dy / d * self.speed * 0.4 * dt
            case "chase":
                pass  # handled by game._creature_think
        self.alert = clamp(self.alert, 0, 1)


class Item:
    def __init__(self, x, y, w, h, kind):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.kind = kind  # 'key', 'battery', 'note'

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)


class Door:
    def __init__(self, x, y, w, h, locked=True, key_id=0):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.locked = locked
        self.key_id = key_id
        self.opened = False

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)


class Button:
    def __init__(self, x, y, w=30, h=12):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.pressed = False

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)


# ────────────────────────────── tilemap ────────────────────────────────────


class Tilemap:
    """Holds walls + decorative tiles.  Walls are drawn thick; decor is
    drawn as darker rectangles to suggest pipes, consoles, etc."""

    def __init__(self, ts=32):
        self.ts = ts
        self.walls = []          # list of pygame.Rect
        self.decor = []          # (rect, brightness 0..1)
        self.low_walls = []      # low obstacles (16px tall, crouch under)
        self.grid_w = 0
        self.grid_h = 0
        self.spawn_points = []
        self._solid_flags = {}   # (tx, ty) -> True for solid tiles
        self._low_flags = {}     # (tx, ty) -> True for low obstacles

    def build_from_grid(self, grid):
        """grid: list of strings.  Character meanings:
        '#' = wall
        '~' = low obstacle (crouch under — 16px tall)
        '.' = empty
        'M' = machinery (decorative, not solid)
        'S' = switch tile
        'D' = door (replaced by Door objects by the caller)
        'P' = player start
        Letters other than '#' and '~' produce non-solid decor or spawns."""
        self.grid_h = len(grid)
        self.grid_w = len(grid[0]) if grid else 0
        self.walls.clear()
        self.decor.clear()
        self.low_walls.clear()
        self.spawn_points.clear()
        self._solid_flags.clear()
        self._low_flags.clear()
        for gy, row in enumerate(grid):
            for gx, ch in enumerate(row):
                x, y = gx * self.ts, gy * self.ts
                is_wall = False
                if ch == '#':
                    self.walls.append(pygame.Rect(x, y, self.ts, self.ts))
                    self._solid_flags[(gx, gy)] = True
                    is_wall = True
                elif ch == '~':
                    # low obstacle: 16px tall barrier at top of tile
                    self.low_walls.append(pygame.Rect(x, y, self.ts, 16))
                    self._low_flags[(gx, gy)] = True
                elif ch in 'MmS':
                    # machinery / symbols / structural — non-solid decor
                    self.decor.append((pygame.Rect(
                        x + 4, y + 4, self.ts - 8, self.ts - 8),
                        0.5 + 0.1 * (hash(ch) % 5)))
                elif ch == 'P':
                    self.spawn_points.append((x + self.ts / 2,
                                              y + self.ts / 2))
                # 'D' and '.' are empty (non-solid) for the tilemap;
                # doors are handled by the Area layer.

    def solid_at(self, tx, ty):
        # check full walls
        if self._solid_flags.get((tx, ty), False):
            return True
        # check low walls only if entity is tall enough
        return False

    def low_wall_at(self, rect):
        """Return True if rect intersects a low obstacle (needs crouching)."""
        for lw in self.low_walls:
            if lw.colliderect(rect) and rect.bottom - rect.height / 2 < lw.bottom:
                # player must be crouching (height / 2) to fit under
                pass
        # simpler: check if any low wall intersects the top half of the rect
        for lw in self.low_walls:
            top_rect = pygame.Rect(rect.x, rect.y, rect.w, rect.h // 2)
            if lw.colliderect(top_rect):
                return True
        return False

    def collide_rect(self, rect):
        return [w for w in self.walls if w.colliderect(rect)]

    @property
    def bounds(self):
        return pygame.Rect(0, 0, self.grid_w * self.ts,
                           self.grid_h * self.ts)


# ─────────────────────────────── area ──────────────────────────────────────


class Area:
    """A screen-full of world: tilemap, items, doors, creature, and
    area-specific behaviour (patrol nodes, ambient sounds)."""

    NAMES = ["Abandoned Lab", "Maintenance Tunnels",
             "Flooded Sector", "Power Station",
             "Creature's Nest", "Hidden Facility"]

    def __init__(self, idx, tilemap, player_start):
        self.idx = idx
        self.name = self.NAMES[idx]
        self.tilemap = tilemap
        self.player_start = player_start
        self.items = []
        self.doors = []
        self.buttons = []
        self.creature = None
        self.ambient = []  # list of (sound_label, interval)
        self.fog_density = 0.35
        self.light_flicker = 0.15
        self.chase_nodes = []
        self._last_ambient = 0.0

    def add_item(self, x, y, kind):
        self.items.append(Item(x, y, 14, 14, kind))

    def add_door(self, x, y, w, h, locked=True):
        self.doors.append(Door(x, y, w, h, locked=locked))

    def ambient_tick(self, dt):
        self._last_ambient -= dt
        if self._last_ambient <= 0:
            self._last_ambient = random.uniform(2, 6)
            return True
        return False


# ──────────────────────────────── fog ─────────────────────────────────────


class Fog:
    """A fullscreen noise overlay that drifts, thickening suspense."""

    def __init__(self):
        self.surf = pygame.Surface(WIN, pygame.SRCALPHA)
        self.t = 0.0

    def update(self, dt, density=0.35):
        self.t += dt * 0.3

    def draw(self, screen, density):
        self.surf.fill((0, 0, 0, 0))
        step = 40
        for y in range(0, HEIGHT, step):
            for x in range(0, WIDTH, step):
                n = noise(x, y, self.t) * density * 220
                if n > 20:
                    pygame.draw.rect(self.surf, (0, 0, 0, int(n)),
                                     (x, y, step, step))
        screen.blit(self.surf, (0, 0))


# ─────────────────────── flicker / torch light ────────────────────────────


class Torch:
    """Radial light with noisy edge flicker."""

    def __init__(self):
        self.surf = pygame.Surface(WIN, pygame.SRCALPHA)
        self.t = 0.0

    def update(self, dt):
        self.t += dt * 4

    def draw(self, screen, cx, cy, radius=TORCH_RADIUS):
        self.surf.fill((0, 0, 0, 0))
        # Build layered translucent circles — outer dark, inner bright
        for band in range(8):
            r = int(radius - band * radius / 8)
            inner_a = int(165 - band * 14)
            flicker = noise(cx, cy, self.t + band)
            a = max(0, int(inner_a * (0.9 + 0.1 * flicker)))
            color = (0, 0, 0, a)
            pygame.draw.circle(self.surf, color,
                               (int(cx), int(cy)), r)
        screen.blit(self.surf, (0, 0))


# ─────────────────────────────── game ──────────────────────────────────────


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(WIN)
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 20)
        self.font_big = pygame.font.Font(None, 42)
        self.font_note = pygame.font.Font(None, 26)
        self.fog = Fog()
        self.torch = Torch()
        self.t = 0.0
        self._build_world()
        self._new_game()

    # ───────────────────── world construction ────────────────

    def _build_world(self):
        ts = 32
        self.areas = []

        # ── Area 0: Abandoned Laboratory ──────────────────────
        lab_grid = [
            "################################################",
            "#P        .        .        .        .        #",
            "#  M M M  ~>   M    .   M    .   M    .   M   #",
            "#  # # #   .   #    .   #    .   #    .   #   #",
            "#          .          .          .          #",
            "##########.##########.##########.##########.#",
            "#  .      #.  .       #.  .      #.  .      #",
            "#  . M   . #  M .   M .    M  .   #  M .   M .#",
            "#K .  .   .   .       S     .   .   .   .   .#",
            "#.#####.####.########.####.####.####.####.#.#",
            "#          .          .          .          #",
            "#  M       .          .          .          #",
            "#  #       .    S     .     M    .   M     M.#",
            "#          .          .          .          #",
            "#D######.####.####.#####.####.####.####.######",
            "#     .          .          .          .    #",
            "# M   .   M      .   M      .   M      .    #",
            "################################################",
        ]
        lab_tm = Tilemap(ts)
        lab_tm.build_from_grid(lab_grid)
        a0 = Area(0, lab_tm, (48, 1 * ts))
        a0.add_item(24, 5 * ts + 8, 'key')
        a0.add_item(80, 14 * ts + 8, 'battery')
        a0.add_item(400, 8 * ts + 8, 'note')
        a0.add_item(300, 4 * ts + 8, 'battery')
        a0.add_item(700, 14 * ts + 8, 'key')
        a0.add_door(48, 14 * ts, ts * 2, ts, locked=True)
        a0.add_door(720, 14 * ts, ts * 2, ts, locked=False)

        # ── Area 1: Maintenance Tunnels (darker, more fog) ──
        tun_grid = [
            "#############################################",
            "#P~       .     .       .     .       .    #",
            "#  M M  ~  .     .       .     .       .   M M  #",
            "#  # #     .     .       .     .       .  # #   #",
            "#  . ~    .     .       .     .       .  .      #",
            "#############.#############.#############. #",
            "#          . .          . .          . .   #",
            "#  . M   . M. .   M    . M. .   M    . M   #",
            "#K . .   . .  .  S     . .  .  S    . .   .#",
            "#.######.####.##.#########.##.####.######.#",
            "#       .     .  ~     .     .     ~     . #",
            "###########################################",
        ]
        tun_tm = Tilemap(ts)
        tun_tm.build_from_grid(tun_grid)
        a1 = Area(1, tun_tm, (48, 1 * ts))
        a1.fog_density = 0.55
        a1.add_item(24, 5 * ts + 8, 'key')
        a1.add_item(120, 2 * ts + 8, 'battery')
        a1.add_item(300, 8 * ts + 8, 'note')
        a1.add_door(48, 10 * ts, ts * 2, ts, locked=True)
        a1.add_door(560, 10 * ts, ts * 2, ts, locked=False)

        # ── Area 2: Flooded Sector (water slows movement) ───
        fl_grid = [
            "#############################################",
            "#P      .      .      .      .      .       #",
            "#  M    .  M   .  M    .  M   .  M   .  M    #",
            "#  #    .  #   .  #    .  #   .  #   .  #    #",
            "#  .    .  .   .  .    .  .   .  .   .  .   #",
            "###.####.####.####.####.####.####.####.####.#",
            "#  .       .       .        .      .      . #",
            "#  M M   M M M   M M M   M M M   M M M   M M#",
            "#K       .        .        .       .       #",
            "#.####.####.####.####.####.####.####.####.###",
            "###########################################",
        ]
        fl_tm = Tilemap(ts)
        fl_tm.build_from_grid(fl_grid)
        a2 = Area(2, fl_tm, (48, 1 * ts))
        a2.fog_density = 0.45
        a2.add_item(32, 3 * ts + 8, 'battery')
        a2.add_item(280, 4 * ts + 8, 'key')
        a2.add_item(500, 7 * ts + 8, 'note')
        a2.add_door(48, 9 * ts, ts * 2, ts, locked=True)
        a2.add_door(580, 9 * ts, ts * 2, ts, locked=False)

        # ── Area 3: Power Station (switches + moving platforms) ──
        ps_grid = [
            "#############################################",
            "#P       .      .      .      .      .      #",
            "#  M     .    M .    M .    M .    M .     #",
            "#  #     .    # .    # .    # .    # .     #",
            "#  .     .    . .    . .    . .    . .     #",
            "###.#####.####.####.####.####.####.####.###",
            "#S .     .      .      .      .      .     #",
            "#  M     M      M      M      M      M     #",
            "#K  .    .      .      .      .      .     #",
            "#.###.###.####.###.####.###.####.###.####.#",
            "###########################################",
        ]
        ps_tm = Tilemap(ts)
        ps_tm.build_from_grid(ps_grid)
        a3 = Area(3, ps_tm, (48, 1 * ts))
        a3.add_item(24, 8 * ts + 8, 'switch')
        a3.add_item(60, 4 * ts + 8, 'battery')
        a3.add_item(320, 2 * ts + 8, 'key')
        a3.add_door(48, 10 * ts, ts * 2, ts, locked=True)
        a3.add_door(560, 10 * ts, ts * 2, ts, locked=False)

        # ── Area 4: Creature's Nest (chase arena, heavy fog) ──
        nest_grid = [
            "#############################################",
            "#P           .            .            .    #",
            "#  M         .            .            .    #",
            "#  #         .      M     .            .    #",
            "#  .         .      #     .            .    #",
            "#########.###.####.####.####.####.#########",
            "#       .     .           .     .         #",
            "#  M    .    M .      M   .    M .    M    #",
            "#  #    .    # .      #   .    # .    #    #",
            "#  .    .    . .      .   .    . .    .    #",
            "#K  .  .    .  .    .  .    .    .  .  .  .#",
            "###########################################",
        ]
        nest_tm = Tilemap(ts)
        nest_tm.build_from_grid(nest_grid)
        a4 = Area(4, nest_tm, (48, 1 * ts))
        a4.fog_density = 0.7
        a4.add_item(40, 10 * ts + 8, 'key')
        a4.add_item(120, 5 * ts + 8, 'battery')
        a4.add_door(48, 11 * ts, ts * 2, ts, locked=True)
        a4.add_door(580, 11 * ts, ts * 2, ts, locked=False)

        # ── Area 5: Hidden Facility (final mystery) ────────────
        hf_grid = [
            "#############################################",
            "#P          .          .          .         #",
            "#  M        .          .          .         #",
            "#  #        .          .          .         #",
            "#  .        .          .          .         #",
            "###.####.####.####.####.####.####.####.####.#",
            "#  .    .    .    .    .    .    .    .    #",
            "#  M    M    M    M    M    M    M    M    M#",
            "#K                                        .#",
            "###########################################",
        ]
        hf_tm = Tilemap(ts)
        hf_tm.build_from_grid(hf_grid)
        a5 = Area(5, hf_tm, (48, 1 * ts))
        a5.fog_density = 0.8
        a5.add_item(320, 4 * ts + 8, 'note')
        a5.add_item(480, 2 * ts + 8, 'battery')
        self.areas.extend([a0, a1, a2, a3, a4, a5])

    # ──────────────────── game state ──────────────────────────

    def _new_game(self):
        self.player = Player(*self.areas[0].player_start)
        self.area_idx = 0
        self.keys = 0
        self.batteries = 3
        self.last_checkpoint = (0, self.areas[0].player_start)
        self.state = "exploring"
        self.chase_t = 0.0
        self.message = "Welcome to the facility."
        self.message_t = 4.0
        self.subtitle_lines = []
        self.subtitle_t = 0.0
        self.grace_until = 6.0  # invulnerable for first few seconds
        self.t = 0.0
        self.creature = Creature(600, 400)
        self.areas[0].creature = self.creature
        self.interact_prompt = None

    def _set_checkpoint(self):
        self.last_checkpoint = (self.area_idx,
                                (self.player.x, self.player.y))
        self.message = "Checkpoint set."
        self.message_t = 2.5

    def _restart(self):
        self.area_idx = self.last_checkpoint[0]
        cx, cy = self.last_checkpoint[1]
        self.player = Player(cx, cy)
        self.state = "exploring"
        self.creature.state = "hidden"
        self.creature.x = self.player.x + 500
        self.creature.y = self.player.y + 60
        self.grace_until = 5.0  # grace period after respawn
        self.message = "Returned to checkpoint."
        self.message_t = 3

    # ──────────────────── interaction ────────────────────────

    def _interact(self):
        area = self.areas[self.area_idx]
        pr = self.player.rect
        px, py = self.player.x + self.player.w / 2, self.player.y

        # items
        for it in area.items[:]:
            if pr.colliderect(it.rect):
                if it.kind == 'key':
                    self.keys += 1
                    self.message = "Key acquired."
                    area.items.remove(it)
                elif it.kind == 'battery':
                    if self.batteries < 5:
                        self.batteries += 1
                        self.message = "Battery added."
                        area.items.remove(it)
                    else:
                        self.message = "Charged to full."
                elif it.kind == 'note':
                    self._show_note()
                    area.items.remove(it)
                    self.state = "reading"
                    return
                elif it.kind == 'switch':
                    self.message = "Switch activated."
                    area.items.remove(it)
                    # open all doors in this area
                    for d in area.doors:
                        d.locked = False
                    self.message_t = 3
                    return
                self.message_t = 2
                return

        # doors
        for door in area.doors:
            if pr.colliderect(door.rect):
                if door.locked:
                    if self.keys > 0:
                        door.locked = False
                        self.keys -= 1
                        self.message = "Door unlocked."
                        self.message_t = 2
                        return
                    else:
                        self.message = "Need a key."
                        self.message_t = 2
                        return
                # open door → transition to next area
                self.message = "Through..."
                self.message_t = 1.5
                self._transition_next()
                return

        # nothing
        self.message = "Nothing of interest."
        self.message_t = 2

    def _show_note(self):
        texts = [
            "Facility Log #1\nThe tests were a mistake.\nSubject exhibits...\nuncontrolled regeneration.\nIt learned to mimic voices.",
            "Facility Log #2\nI hear it in the walls now.\nLouder at night.\nIt knows my footsteps.\nMy own.",
            "Facility Log #3\nThe exit sign lied.\nThere was never an exit.\nIt just wanted\nus to stop running.",
            "Facility Log #4\nDay 47: It stopped chasing.\nIt started thinking.\nI'm writing this in blood\nbecause pencil lead won't scratch steel.",
            "Facility Log #5\nThe last thing I remember\nis my own voice,\nwhispering 'come closer.'\nMy mouth moved but my lungs said no.",
            "Final Entry\nYou're not reading this.\nIt already has your voice.\nDon't trust the whisper\nbefore the jump.",
        ]
        note = random.choice(texts)
        self.subtitle_lines = note.split('\n')
        self.subtitle_t = 15

    def _transition_next(self):
        if self.area_idx < len(self.areas) - 1:
            self.area_idx += 1
            cx, cy = self.areas[self.area_idx].player_start
            self.player.x, self.player.y = cx, cy
            self.player.vx = self.player.vy = 0
            self.creature.x = self.player.x + 500
            self.creature.y = self.player.y + 60
            self.creature.state = "hidden"
            self._set_checkpoint()
            self.message = f"— {self.areas[self.area_idx].name} —"
            self.message_t = 3
            self.state = "exploring"
        else:
            self.state = "win"
            self.message = "You escaped? Or did you?"
            self.message_t = 8
            self.subtitle_lines = ["The exit door closes behind you.",
                                   "But you could swear you heard",
                                   "your own footsteps",
                                   "coming from inside."]
            self.subtitle_t = 10

    # ──────────────────── updates ────────────────────────────

    @staticmethod
    def _safe_key(keys, key):
        try:
            return keys[key]
        except IndexError:
            return False

    def update(self, dt):
        self.t += dt
        self.message_t = max(0, self.message_t - dt)
        if self.subtitle_t > 0:
            self.subtitle_t -= dt
        if self.subtitle_t <= 0:
            self.subtitle_lines = []

        if self.state == "reading":
            return
        if self.state == "dead" or self.state == "win":
            return

        keys = pygame.key.get_pressed()
        area = self.areas[self.area_idx]
        self.interact_prompt = None

        # ── ambient / horror cues ────────────
        if area.ambient_tick(dt) and random.random() < 0.45:
            self._ambient_cue(area)

        # ── creature AI ─────────────────────
        self._creature_think(dt, area)

        # ── player ──────────────────────────
        self.player.handle(keys, dt, area.tilemap)

        # ── interactions ───────────────────
        if self._safe_key(keys, pygame.K_e):
            self._interact()

        # ── auto-pickup items ────────────────
        for it in area.items[:]:
            if self.player.rect.colliderect(it.rect) and \
               it.kind in ('key', 'battery', 'switch'):
                if it.kind == 'key':
                    self.keys += 1
                    self.message = "Key acquired."
                elif it.kind == 'battery':
                    if self.batteries < 5:
                        self.batteries += 1
                        self.message = "Battery added."
                elif it.kind == 'switch':
                    for d in area.doors:
                        d.locked = False
                    self.message = "Switch activated."
                self.message_t = 2
                area.items.remove(it)

        # ── door proximity prompt ──────────
        for door in area.doors:
            if door.rect.colliderect(self.player.rect):
                if door.locked:
                    self.interact_prompt = (
                        "E  (key required)" if self.keys == 0 else
                        f"E  (unlock, {self.keys} key(s))")
                else:
                    self.interact_prompt = "E  → next area"
                break

        # ── crouch prompt for low obstacles ──
        if not self.player.crouching:
            tm = area.tilemap
            head_rect = pygame.Rect(
                self.player.x, self.player.y - 8,
                self.player.w, 20)
            if tm.low_wall_at(head_rect):
                self.interact_prompt = "S  crouch"

        # ── fall off map ───────────────────
        bounds = area.tilemap.bounds
        if self.player.y > bounds.bottom + 200:
            self._restart()

        # ── state transitions ──────────────
        if self.state == "chase":
            self.chase_t -= dt
            if self.chase_t <= 0:
                self.state = "exploring"
                self.creature.state = "hidden"

        # ── torch flicker / battery drain ─
        self.torch.update(dt)
        self.fog.update(dt, area.fog_density)

        # battery slowly drains over time — tension
        if self.batteries <= 0:
            self.batteries = 0
            # game over: you were consumed by darkness
            self.state = "dead"
            self.message = "The dark takes you."
            self.message_t = 8
            self.subtitle_lines = ["You should have kept moving.",
                                   "The whispers are inside now."]
            self.subtitle_t = 6

    def _ambient_cue(self, area):
        """Trigger footsteps, whispers, creaks — distant horror."""
        cues = ["distant footsteps", "whispering", "metal banging",
                "electrical buzz", "pipes creaking", "sudden silence",
                "something breathing behind you", "a child laughing"]
        cue = random.choice(cues)
        self.subtitle_lines = [f"[ {cue} ]", ""]
        self.subtitle_t = 3.5

    def _creature_think(self, dt, area):
        """The creature decides: stalk, hide, or chase."""
        px = self.player.x + self.player.w / 2
        py = self.player.y + self.player.h / 2
        dist = math.hypot(self.creature.x - px, self.creature.y - py)

        # chance to initiate a chase
        if (self.state == "exploring" and dist < 340
                and self.t > self.grace_until  # grace period
                and random.random() < 0.015):
            self.state = "chase"
            self.creature.state = "chase"
            self.chase_t = random.uniform(3.5, 6.5)
            self.creature.phase = 1.0
            self._ambient_cue(area)
            self.subtitle_lines = ["[ You feel eyes on you ]",
                                   "[ Don't look back ]"]
            self.subtitle_t = 3.0
            return

        if self.state == "chase":
            # creature slowly advances toward player - more suspense than speed
            offset = random.uniform(-15, 15)
            dx = px - self.creature.x + offset
            dy = (py + 17) - self.creature.y
            dd = math.hypot(dx, dy)
            if dd > 0:
                self.creature.x += dx / dd * self.creature.speed * 1.0 * dt
                self.creature.y += dy / dd * self.creature.speed * 1.4 * dt
        else:
            # hidden: follow player but stay invisible
            self.creature.state = "hidden"
            # stay just behind the player
            self.creature.x = px - 50 * self.player.facing
            self.creature.y = py + 10

        # player caught
        if dist < 24 and self.state == "chase":
            self.state = "dead"
            self.message = "It was never real... was it?"
            self.message_t = 8
            self.subtitle_lines = ["The last whisper\nis your own voice.", ""]
            self.subtitle_t = 6

    # ──────────────────── drawing ─────────────────────────────

    def draw(self):
        screen = self.screen
        screen.fill(BLACK)
        area = self.areas[self.area_idx]
        tm = area.tilemap
        cam_x = clamp(self.player.x - WIDTH / 2, 0,
                      max(0, tm.bounds.right - WIDTH))
        cam_y = clamp(self.player.y - HEIGHT / 2, 0,
                      max(0, tm.bounds.bottom - HEIGHT))

        # ── parallax background / machinery ──
        self._draw_bg(screen, area, self.t, cam_x / 80, cam_y / 80)

        # ── tiles ──
        for wall in tm.walls:
            wx, wy = wall.x - cam_x, wall.y - cam_y
            col = MID_GRAY
            # flickering fluorescent strips on every other row
            if (wall.y // tm.ts) % 2 == 0 and self.t % 0.4 < 0.9:
                flicker = 0.7 + 0.3 * math.sin(
                    self.t * 8 + wall.x * 0.02 + wall.y * 0.03)
                col = tuple(int(c * flicker) for c in DIM_GRAY)
            pygame.draw.rect(screen, col,
                             (wx, wy, tm.ts, tm.ts))
            # highlight edges for depth
            if wall.y > 0 and (wall.y // tm.ts) % 3 == 1:
                edge_col = tuple(int(c * 0.5) for c in col)
                pygame.draw.rect(screen, edge_col,
                                 (wx, wy, tm.ts, tm.ts), 1)

        # ── low obstacles (crouch under) ──
        for lw in tm.low_walls:
            lx, ly = lw.x - cam_x, lw.y - cam_y
            low_col = (70, 68, 78)
            pygame.draw.rect(screen, low_col,
                             (lx, ly, lw.w, lw.h))
            pygame.draw.rect(screen, (50, 48, 58),
                             (lx, ly, lw.w, lw.h), 1)

        # ── decor / machinery ──
        for rect, bright in tm.decor:
            dx, dy = rect.x - cam_x, rect.y - cam_y
            col = tuple(int(c * bright) for c in GRAY)
            pygame.draw.rect(screen, col, (dx, dy, rect.w, rect.h))
            # pipes / wires
            for i in range(3):
                wire_col = tuple(int(c * 0.5 * bright) for c in col)
                pygame.draw.line(
                    screen, wire_col,
                    (dx, dy + i * 4),
                    (dx + rect.w, dy + i * 4), 1)

        # ── doors ──
        for door in area.doors:
            d = door.rect
            col = LOCKED if door.locked else DOOR_COL
            pygame.draw.rect(
                screen, col,
                (d.x - cam_x, d.y - cam_y, d.w, d.h))
            if door.locked:
                # padlock
                lock_col = (120, 50, 60) if self.keys == 0 else (200, 160, 70)
                pygame.draw.circle(
                    screen, lock_col,
                    (int(d.centerx - cam_x), int(d.centery - cam_y)), 5)
                pygame.draw.circle(
                    screen, lock_col,
                    (int(d.centerx - cam_x), int(d.centery - cam_y)), 5, 1)
            else:
                # door outline shows it's passable
                pygame.draw.rect(
                    screen, (90, 85, 100),
                    (d.x - cam_x, d.y - cam_y, d.w, d.h), 2)

        # ── buttons & switches ──
        for btn in area.buttons:
            col = SWITCH_ON if btn.pressed else SWITCH_OFF
            pygame.draw.rect(
                screen, col,
                (btn.x - cam_x, btn.y - cam_y, btn.w, btn.h))

        # ── items ──
        for it in area.items:
            ix, iy = it.x - cam_x, it.y - cam_y
            if it.kind == 'key':
                col = KEY_GOLD
                pygame.draw.polygon(screen, col,
                                    [(ix, iy), (ix + 10, iy - 6),
                                     (ix + it.w, iy + 4),
                                     (ix + it.w - 10, iy + it.h - 6)])
                pygame.draw.polygon(screen, col,
                                    [(ix, iy + 10), (ix + 4, iy + it.h),
                                     (ix + it.w - 4, iy + it.h),
                                     (ix + it.w, iy + 6)])
            elif it.kind == 'battery':
                pygame.draw.rect(screen, BATTERY, (ix, iy, it.w, it.h), 2)
                pygame.draw.line(screen, BATTERY,
                                 (ix, iy), (ix + it.w, iy + it.h), 2)
                pygame.draw.line(screen, BATTERY,
                                 (ix + it.w, iy), (ix, iy + it.h), 2)
            elif it.kind == 'note':
                pygame.draw.rect(screen, NOTE_PAPER,
                                 (ix, iy, it.w, it.h))
                pygame.draw.line(screen, (120, 110, 100),
                                 (ix + 2, iy + 4),
                                 (ix + it.w - 2, iy + 4), 1)
                pygame.draw.line(screen, (120, 110, 100),
                                 (ix + 2, iy + 8),
                                 (ix + it.w - 2, iy + 8), 1)
            elif it.kind == 'switch':
                sw_col = SWITCH_ON if it.kind == 'switch' else GRAY
                pygame.draw.rect(screen, sw_col,
                                 (ix, iy, it.w, it.h))
                pygame.draw.circle(screen, (200, 180, 120),
                                   (ix + it.w // 2, iy + it.h // 2), 3)

        # ── player ──
        self._draw_player(screen, cam_x, cam_y)

        # ── creature (visible during chase, silhouette when nearby) ──
        if self.creature.state == "chase" or self.state == "chase":
            cr = self.creature.rect
            # shadow
            pygame.draw.ellipse(
                screen, (0, 0, 0, 80),
                (cr.x - cam_x, cr.y + cr.h - cam_y + 4,
                 cr.w, 8))
            # body
            pygame.draw.rect(
                screen, (30, 30, 40),
                (cr.x - cam_x, cr.y - cam_y, cr.w, cr.h))
            pygame.draw.rect(
                screen, (20, 20, 30),
                (cr.x - cam_x, cr.y - cam_y, cr.w, cr.h), 1)
            # head
            pygame.draw.ellipse(
                screen, (40, 40, 50),
                (cr.x - cam_x - 2, cr.y - 8 - cam_y, cr.w + 4, 16))
            # eyes glow red
            pygame.draw.circle(
                screen, CHASE_RED,
                (int(cr.centerx - 6 - cam_x),
                 int(cr.centery - 4 - cam_y)), 3)
            pygame.draw.circle(
                screen, CHASE_RED,
                (int(cr.centerx + 6 - cam_x),
                 int(cr.centery - 4 - cam_y)), 3)
            # limbs — spindly silhouette
            pygame.draw.line(
                screen, (20, 20, 30),
                (cr.centerx - 10 - cam_x, cr.centery - cam_y),
                (cr.centerx - 16 - cam_x, cr.centery + 12 - cam_y), 3)
            pygame.draw.line(
                screen, (20, 20, 30),
                (cr.centerx + 10 - cam_x, cr.centery - cam_y),
                (cr.centerx + 16 - cam_x, cr.centery + 12 - cam_y), 3)
            pygame.draw.line(
                screen, (20, 20, 30),
                (cr.centerx - 10 - cam_x, cr.centery + 12 - cam_y),
                (cr.centerx - 14 - cam_x, cr.centery + 24 - cam_y), 3)
            pygame.draw.line(
                screen, (20, 20, 30),
                (cr.centerx + 10 - cam_x, cr.centery + 12 - cam_y),
                (cr.centerx + 14 - cam_x, cr.centery + 24 - cam_y), 3)
        # brief glimpse when hidden but close
        elif self.creature.state == "hidden":
            dist = math.hypot(
                self.creature.x - (self.player.x + 9),
                self.creature.y - (self.player.y + 17))
            if dist < 120 and random.random() < 0.02:
                # very brief silhouette flash
                alpha_t = self.t * 30
                if int(alpha_t) % 2 == 0:
                    cr = self.creature.rect
                    pygame.draw.rect(
                        screen, (20, 20, 30, 60),
                        (cr.x - cam_x, cr.y - cam_y, cr.w, cr.h))

        # ── torch light overlay ──
        torch_x = self.player.x + self.player.w / 2 - cam_x
        torch_y = self.player.y + self.player.h / 2 - cam_y
        self.torch.draw(screen, torch_x, torch_y)

        # ── fog overlay ──
        self.fog.draw(screen, area.fog_density * 0.7)

        # ── UI ──
        self._draw_ui(screen, area)

        # ── messages ──
        if self.message and self.message_t > 0:
            alpha = min(255, int(self.message_t / 3 * 255))
            msg = self.font_big.render(self.message, True, WHITE)
            msg.set_alpha(alpha)
            screen.blit(msg, (WIDTH / 2 - msg.get_width() / 2, 60))

        if self.subtitle_t > 0 and self.subtitle_lines:
            for i, line in enumerate(self.subtitle_lines):
                sub = self.font_note.render(line, True, LT_GRAY)
                sub.set_alpha(min(200, int(self.subtitle_t / 5 * 200)))
                screen.blit(sub, (WIDTH / 2 - sub.get_width() / 2,
                                  HEIGHT - 120 + i * 20))

        # ── interact prompt ──
        if self.interact_prompt and self.state == "exploring":
            prompt = self.font.render(self.interact_prompt, True, OFF_WHITE)
            prompt.set_alpha(200)
            screen.blit(prompt, (WIDTH / 2 - prompt.get_width() / 2,
                                 HEIGHT - 36))

        # ── chase warning ──
        if self.state == "chase":
            w = int(200 + 55 * math.sin(self.t * 12))
            warn = self.font_big.render("RUN!", True,
                                        (w, 30, 50))
            screen.blit(warn, (WIDTH / 2 - warn.get_width() / 2, 100))

        pygame.display.flip()

    def _draw_bg(self, screen, area, t, ox, oy):
        # distant machinery silhouettes
        for i in range(8):
            bx = -120 + i * 140 + ox * 3
            by = 60 + math.sin(t * 0.3 + i) * 2 + oy * 2
            pygame.draw.rect(screen, GRAY, (bx, by, 30, 110), 1)
            # rotating fan
            pygame.draw.circle(screen, MID_GRAY,
                               (int(bx + 15), int(by + 25)), 6)
            # fan blade
            blade_a = t * 3 + i
            pygame.draw.line(
                screen, MID_GRAY,
                (int(bx + 15), int(by + 25)),
                (int(bx + 15 + math.cos(blade_a) * 10),
                 int(by + 25 + math.sin(blade_a) * 10)), 1)
        # ceiling pipes
        for y in range(0, HEIGHT, 40):
            bx = (math.sin(t * 0.2 + y * 0.01) * 12 + ox * 4) % 60
            pygame.draw.line(screen, MID_GRAY, (bx, y), (bx + 40, y), 1)

    def _draw_player(self, screen, cam_x, cam_y):
        x = self.player.x - cam_x
        y = self.player.y - cam_y
        col = LT_GRAY
        if self.player.invuln > 0 and self.t % 0.1 < 0.05:
            return  # flicker when hurt
        # when crouching, draw a shorter body
        draw_h = self.player.h // 2 if self.player.crouching else self.player.h
        # body
        pygame.draw.ellipse(screen, col,
                            (x, y + 4, self.player.w, draw_h - 4))
        # face (higher when crouching)
        face_y = y + 6 if self.player.crouching else y + 10
        eye_x = x + (6 if self.player.facing < 0 else self.player.w - 6)
        pygame.draw.circle(screen, WHITE, (int(eye_x), int(face_y)), 3)
        # arms — tucked in when crouching
        if self.player.crouching:
            pygame.draw.line(screen, col, (x, y + 10),
                             (x - self.player.facing * 6, y + 12), 3)
        else:
            arm_y = y + 12
            if self.player.vx:
                swing = math.sin(self.t * 12) * 2
                pygame.draw.line(screen, col, (x, arm_y),
                                 (x - self.player.facing * 12,
                                  arm_y + swing), 3)
            else:
                pygame.draw.line(screen, col, (x, arm_y),
                                 (x - self.player.facing * 8, arm_y), 3)
        # legs
        leg_swing = (math.sin(self.t * 12) * 1.5
                     if self.player.on_ground else 0)
        if not self.player.crouching:
            pygame.draw.line(screen, col,
                             (x + 4, y + self.player.h),
                             (x + 4 + leg_swing, y + self.player.h + 12), 3)
            pygame.draw.line(screen, col,
                             (x + self.player.w - 4, y + self.player.h),
                             (x + self.player.w - 4 - leg_swing,
                              y + self.player.h + 12), 3)

    def _draw_ui(self, screen, area):
        # battery indicator
        for i in range(self.batteries):
            pygame.draw.rect(screen, BATTERY,
                             (16 + i * 18, 16, 14, 14))
        # keys
        for i in range(self.keys):
            col = KEY_GOLD
            kx, ky = 160 + i * 18, 16
            pygame.draw.polygon(
                screen, col, [(kx, ky), (kx + 6, ky - 4),
                              (kx + 10, ky + 2), (kx + 10, ky + 10),
                              (kx + 6, ky + 14), (kx - 6, ky + 8)])
        # area name
        name = self.font.render(
            f"{area.name}  [{self.area_idx + 1}/6]", True, WHITE)
        screen.blit(name, (WIDTH / 2 - name.get_width() / 2, 12))
        # state indicator
        if self.state == "chase":
            chase_txt = self.font_big.render("CHASE!", True, CHASE_RED)
            screen.blit(chase_txt, (WIDTH / 2 - chase_txt.get_width() / 2, 20))

    # ──────────────────── loop ──────────────────────────────

    def run(self):
        running = True
        while running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        self._restart()
                    elif (event.key == pygame.K_SPACE and
                          self.state == "reading"):
                        self.state = "exploring"
                        self.subtitle_t = 0
            self.update(dt)
            self.draw()
        pygame.quit()
        sys.exit()


# ───────────────────────────────── go ──────────────────────────────────────

if __name__ == "__main__":
    Game().run()