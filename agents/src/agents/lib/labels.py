# Centralized GitHub label names used across agents.
# Renaming a label = changing one constant.

BUG = "bug"
AUTOTRIAGE = "autotriage"
REGRESSION = "regression"

SEVERITY_CRITICAL = "severity:critical"
SEVERITY_IMPORTANT = "severity:important"
SEVERITY_MINOR = "severity:minor"

HEALTHCHECK = "healthcheck"

AGENT_BUILD = "agent:build"

AREA_API = "area:api"
AREA_WEB = "area:web"
AREA_AGENTS = "area:agents"
AREA_CI = "area:ci"
AREA_DOCS = "area:docs"
PRIORITY_HIGH = "priority:high"
PRIORITY_LOW = "priority:low"

SEVERITY_ALL = frozenset({SEVERITY_CRITICAL, SEVERITY_IMPORTANT, SEVERITY_MINOR})
AREA_ALL = frozenset({AREA_API, AREA_WEB, AREA_AGENTS, AREA_CI, AREA_DOCS})
PRIORITY_ALL = frozenset({PRIORITY_HIGH, PRIORITY_LOW})
ALL_MANAGED = SEVERITY_ALL | AREA_ALL | PRIORITY_ALL | frozenset({BUG, AUTOTRIAGE, REGRESSION, HEALTHCHECK, AGENT_BUILD})
