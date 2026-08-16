"""ASCII banner — the Scedly sun. Shown on bare invocation."""

# ─── CHANGE THIS with your actual logo ───
# ANSI colors (degrade gracefully on terminals without color support).
_Y = "\033[93m"  # bright yellow (sun disc)
_O = "\033[33m"  # amber (rays)
_G = "\033[92m"  # phosphor green (wordmark)
_R = "\033[0m"  # reset

LOGO = rf"""
{_O}          \   |   /{_R}
{_O}       '-. {_Y}.-~-.{_O} .-'{_R}
{_O}     ---  {_Y}( o o ){_O}  ---     {_G}scedly_{_R}
{_O}       .-' {_Y}'-_-'{_O} '-.{_R}      {_O}schedule, automated.{_R}
{_O}          /   |   \{_R}
"""
# ───────────────────────────────────────────


def print_logo():
    print(LOGO)
