# Whispers in the Dark

A 2D psychological-horror platformer built with Python + Pygame.

## Run

```bash
pip install pygame-ce   # or: pip install pygame
python whispers-in-the-dark.py
```

## Controls

| Input              | Action                                  |
| ------------------ | --------------------------------------- |
| WASD / arrows      | Move                                    |
| SPACE / W / ↑      | Jump                                    |
| S / ↓              | Crouch (slip under low barriers)        |
| E                  | Interact (doors, items, notes)          |
| SHIFT              | Walk quietly (reduces creature hearing) |
| R                  | Restart from checkpoint                 |
| ESC                | Quit                                    |

## Areas

1. Abandoned Laboratory — learn movement + crouch
2. Maintenance Tunnels — dark, foggy, low barriers
3. Flooded Sector — murky passages, reduced visibility
4. Power Station — switches, machinery
5. Creature's Nest — heart of the facility, heavy fog
6. Hidden Facility — final mystery

## Game Design Document

### Overview

**Whispers in the Dark** is a 2D psychological-horror platformer. The player
controls a small character trapped inside an abandoned underground facility,
combining classic platforming with psychological horror.

### Gameplay

- Run, jump, climb, and interact with objects
- Levels contain platforms, gaps, moving platforms, locked doors, switches,
  and hidden paths
- Solve simple puzzles to progress
- Player is relatively defenseless — escaping and hiding are more important
  than fighting
- Checkpoints prevent frustration on death

### Horror Elements

- Dark, abandoned, unsettling atmosphere
- Flickering lights, shadows, distant footsteps, strange noises
- Environmental changes and sudden silence
- A mysterious creature that stalks the player:
  - Not always visible — suspense built through sounds and brief glimpses
  - Chase sequences requiring quick platforming to escape
  - Fair scares over cheap jumpscares

### Visual Style

- Dark, atmospheric art with deep blacks and muted colors
- Fog and particle overlays
- Flickering fluorescent lights
- Detailed abandoned machinery
- Strange symbols and clues hidden throughout
- Strong silhouettes and shadows

### Story

The player discovers why the facility was abandoned through environmental
clues, notes, recordings, and strange events. Mysteries make the player
question what is real. Each area reveals another piece of the story.

### Level Design

Six interconnected areas, each introducing a new mechanic or horror element:

1. **Abandoned Laboratory** — basic platforming + crouch mechanic
2. **Maintenance Tunnels** — lower visibility, more fog, low barriers
3. **Flooded Underground Sector** — water physics concept
4. **Power Station** — switches that unlock doors, machinery
5. **Creature's Nest** — chase sequences, densest fog
6. **Hidden Facility** — final revelation

### Sound

- Atmospheric design: distant metal banging, electrical buzzing,
  footsteps, whispering voices, pipe creaking
- Sudden silence before important events
- Intense music during chase sequences

### Technical

- Single-file Python + Pygame implementation
- No external assets — all drawing via pygame primitives
- AABB tile-based collision system
- State machine for creature AI (hidden → chase → dead)
- Radial torch light with noise-based flicker
- Layered fog density per area
- Procedural background with parallax machinery
