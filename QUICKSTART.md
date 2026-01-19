# Quick Start - Claude Code Agents

## Project Location
Robot: `ssh spot@microspot`
Code: `/home/spot/microspot/src/`

## Agent Execution Order

```
Agent 1 (balance.py)     ─┐
                          ├──► Agent 3 (gait.py) ──► Agent 4 (integration)
Agent 2 (ik_interface.py) ─┘
```

Agent 1 and 2 can run in parallel. Agent 3 needs both. Agent 4 needs all.

## Files Overview

| File | Agent | Action | Description |
|------|-------|--------|-------------|
| `balance.py` | 1 | REWRITE | Return height adjustments (meters) |
| `ik_interface.py` | 2 | CREATE | Bridge IK library to servos |
| `gait.py` | 3 | REWRITE | Use IK for foot positioning |
| `microspot_app.py` | 4 | MODIFY | Update API endpoints |
| `ps4_controller.py` | 4 | MODIFY | Add tuning controls |

## Briefing Documents

1. `MASTER_BRIEFING.md` - Full context, all problems explained
2. `AGENT_1_BALANCE.md` - Balance controller rewrite spec
3. `AGENT_2_IK_INTERFACE.md` - IK integration layer spec
4. `AGENT_3_GAIT.md` - Gait controller rewrite spec
5. `AGENT_4_INTEGRATION.md` - Wiring everything together

## Critical Points

### DON'T
- Don't modify `kinematics/` folder - it's a working library
- Don't change `calibration.json` - it's correct
- Don't use `set_servo(ch, angle, True)` after IK - IK already calibrates

### DO
- Auto-enable balance when gait starts
- Use conservative parameters (slow, small steps)
- Test incrementally (stand → single step → walking)

## Test Commands

```bash
# SSH to robot
ssh spot@microspot

# Run backend
cd ~/microspot && ./start.sh

# API tests (from another terminal)
curl http://microspot:8000/api/balance/status
curl http://microspot:8000/api/gait/status

# Python test
cd ~/microspot/src
python3 -c "from gait import GaitController; from microspot_app import set_servo; gc=GaitController(set_servo); gc.single_step()"
```

## The Core Problem (TL;DR)

Current code applies balance as **angle offsets**. Should apply as **height adjustments**. Current code uses **magic angle constants**. Should use **inverse kinematics** with XYZ foot positions.

That's it. Fix those two things and walking will be stable.
