import re

# Heuristic only - see docs/superpowers/specs/2026-07-25-mobile-reels-homepage-design.md
# for why a User-Agent check was chosen over a real viewport check.
_MOBILE_USER_AGENT_PATTERN = re.compile(
    r"Mobi|Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini",
    re.IGNORECASE,
)


def is_mobile_user_agent(user_agent: str) -> bool:
    return bool(_MOBILE_USER_AGENT_PATTERN.search(user_agent))
