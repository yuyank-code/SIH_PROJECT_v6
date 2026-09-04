"""Recovery Playbook — the standard, phased checklist a community works through
to recover from a confirmed landslide.

This is *guidance*, not fabricated operational data. The steps are a checklist
template aligned with India's NDMA landslide-management guidance and the Sphere
humanitarian standards, adapted for the North Eastern Region. When a plan is
generated for an incident, these template steps are copied into `recovery_steps`
rows (each tagged source='TEMPLATE'); authorities/field officers then work them,
and can add their own steps (source='MANUAL'). Nothing here claims to be a
measurement of a real event — it is a recommended course of action.

Four phases, in the order recovery actually unfolds:
  RELIEF          immediate life-saving relief          (0-72 hours)
  EARLY_RECOVERY  stabilise and assess                  (first weeks)
  RESTORATION     rebuild services and livelihoods      (weeks-months)
  RESILIENCE      mitigate so it does not recur         (months onward)

Some steps only apply above a severity threshold (e.g. calling in NDRF/SDRF for a
CRITICAL event). `severity_min` gates those; steps with no gate apply to every
confirmed incident.

Every step carries two guidance fields, so the checklist tells an officer WHAT
to do AND when it is actually possible:
  requires_assessment  True = cannot honestly be marked DONE from a desk; it
                       needs on-ground confirmation (a survey, a site visit,
                       a verified count). Shown in the UI as "needs on-ground
                       assessment" and never auto-completed.
  manageable_when      Human-readable gate — the condition that must hold
                       before this step is realistically actionable ("" = the
                       step is actionable immediately after the event).
"""
from __future__ import annotations

from typing import Any, Dict, List

FRAMEWORK = "NDMA/Sphere-aligned landslide recovery checklist (adapted for NER)"

PHASES: List[Dict[str, str]] = [
    {"key": "RELIEF",         "label": "Immediate relief",            "window": "0-72 hours"},
    {"key": "EARLY_RECOVERY", "label": "Early recovery",              "window": "First weeks"},
    {"key": "RESTORATION",    "label": "Restoration",                 "window": "Weeks to months"},
    {"key": "RESILIENCE",     "label": "Rehabilitation & resilience", "window": "Months onward"},
]

_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

# code: stable identifier (kept if the template is re-generated so progress is
# never lost). severity_min: only include when incident severity is at/above it.
# requires_assessment / manageable_when: see module docstring.
STEPS: List[Dict[str, Any]] = [
    # ---- RELIEF (0-72h) ----------------------------------------------------
    {"code": "REL-EOC",     "phase": "RELIEF", "title": "Activate the Emergency Operations Centre and set incident command",
     "detail": "Name an incident commander and open a single point of coordination for the event.",
     "requires_assessment": False, "manageable_when": "Immediately after confirmation"},
    {"code": "REL-SAR",     "phase": "RELIEF", "title": "Launch search & rescue at the slide site",
     "detail": "Sweep the debris and run-out path for trapped and missing people.",
     "requires_assessment": True, "manageable_when": "As soon as the site is reachable"},
    {"code": "REL-NDRF",    "phase": "RELIEF", "title": "Request NDRF/SDRF deployment", "severity_min": "HIGH",
     "detail": "Call in specialised rescue teams for a large or deep failure.",
     "requires_assessment": True, "manageable_when": "Once the slide site is confirmed"},
    {"code": "REL-TRIAGE",  "phase": "RELIEF", "title": "Triage and treat the injured; set up a medical post",
     "detail": "Stabilise casualties on site and arrange evacuation of the seriously hurt.",
     "requires_assessment": True, "manageable_when": "Once casualties reach the gathering point"},
    {"code": "REL-MASSCAS", "phase": "RELIEF", "title": "Stand up mass-casualty triage and mortuary arrangements", "severity_min": "CRITICAL",
     "detail": "Scale medical response and dignified handling of the deceased for a major loss of life.",
     "requires_assessment": True, "manageable_when": "Once casualty numbers are confirmed"},
    {"code": "REL-EVAC",    "phase": "RELIEF", "title": "Evacuate people from the unstable slope and run-out zone",
     "detail": "Move households out of the danger area before any secondary slide.",
     "requires_assessment": True, "manageable_when": "As soon as the danger zone is mapped"},
    {"code": "REL-SHELTER", "phase": "RELIEF", "title": "Open relief camps / temporary shelter for displaced families",
     "detail": "Provide a safe, dry place to sleep away from the hazard.",
     "requires_assessment": True, "manageable_when": "After evacuation begins"},
    {"code": "REL-WATFOOD", "phase": "RELIEF", "title": "Distribute emergency drinking water, food and blankets",
     "detail": "Meet basic survival needs for everyone displaced or cut off.",
     "requires_assessment": True, "manageable_when": "After camps are stood up"},
    {"code": "REL-COMMS",   "phase": "RELIEF", "title": "Restore contact with cut-off villages",
     "detail": "Reach isolated settlements by satellite phone, radio or runner and log their status.",
     "requires_assessment": True, "manageable_when": "As soon as routes or comms permit"},
    {"code": "REL-MISSING", "phase": "RELIEF", "title": "Account for missing persons and maintain a verified casualty list",
     "detail": "Keep one authoritative, updated list — never an estimate presented as fact.",
     "requires_assessment": True, "manageable_when": "As search & rescue proceeds"},

    # ---- EARLY RECOVERY (first weeks) --------------------------------------
    {"code": "ER-ASSESS",   "phase": "EARLY_RECOVERY", "title": "Complete rapid damage & needs assessment, village by village",
     "detail": "Record homes, people and lifelines affected in each settlement (blank = not yet assessed).",
     "requires_assessment": True, "manageable_when": "Once access routes are open"},
    {"code": "ER-ACCESS",   "phase": "EARLY_RECOVERY", "title": "Clear debris and reopen one access route to each cut-off village",
     "detail": "Restore at least a single lifeline road so relief and medical help can reach people.",
     "requires_assessment": True, "manageable_when": "After search & rescue winds down"},
    {"code": "ER-UTIL",     "phase": "EARLY_RECOVERY", "title": "Restore electricity and safe water supply",
     "detail": "Bring back power and clean water to camps and affected homes.",
     "requires_assessment": True, "manageable_when": "After debris clearance reaches the site"},
    {"code": "ER-SANIT",    "phase": "EARLY_RECOVERY", "title": "Set up sanitation and disease surveillance in relief camps",
     "detail": "Prevent a secondary health crisis — latrines, hygiene, and watch for outbreaks.",
     "requires_assessment": True, "manageable_when": "Once camps are occupied"},
    {"code": "ER-CASH",     "phase": "EARLY_RECOVERY", "title": "Provide interim cash relief / ex-gratia to affected families",
     "detail": "Release immediate assistance so families can meet urgent needs.",
     "requires_assessment": False, "manageable_when": "Once the family list is verified"},
    {"code": "ER-TAG",      "phase": "EARLY_RECOVERY", "title": "Inspect and safety-tag damaged buildings (red / green)",
     "detail": "Mark which structures are safe to re-enter and which must stay closed.",
     "requires_assessment": True, "manageable_when": "After the damage assessment is complete"},
    {"code": "ER-SECURE",   "phase": "EARLY_RECOVERY", "title": "Secure the slope against an immediate secondary slide",
     "detail": "Sheet the scar with tarpaulin and divert surface runoff away from the failure.",
     "requires_assessment": True, "manageable_when": "After the site is declared safe to work"},

    # ---- RESTORATION (weeks-months) ----------------------------------------
    {"code": "RES-ROADS",   "phase": "RESTORATION", "title": "Repair or rebuild damaged roads, bridges and culverts",
     "detail": "Return the transport network to normal, permanent service.",
     "requires_assessment": True, "manageable_when": "Once permanent resources are available"},
    {"code": "RES-HOMES",   "phase": "RESTORATION", "title": "Reconstruct damaged homes to safe standards",
     "detail": "Rebuild — relocating off the run-out zone where the site is no longer safe.",
     "requires_assessment": True, "manageable_when": "After the risk area is finalised"},
    {"code": "RES-PUBLIC",  "phase": "RESTORATION", "title": "Restore schools, health centres and public buildings",
     "detail": "Reopen the services a community depends on day to day.",
     "requires_assessment": True, "manageable_when": "After the damage assessment is complete"},
    {"code": "RES-LIVE",    "phase": "RESTORATION", "title": "Support livelihood recovery",
     "detail": "Help farms, shops and daily-wage workers get back to earning.",
     "requires_assessment": True, "manageable_when": "Once affected households are back"},
    {"code": "RES-CLAIMS",  "phase": "RESTORATION", "title": "Process compensation, insurance and assistance claims",
     "detail": "See that affected families actually receive what they are entitled to.",
     "requires_assessment": True, "manageable_when": "After the official loss record is finalised"},
    {"code": "RES-DEBRIS",  "phase": "RESTORATION", "title": "Environmental clean-up and safe disposal of debris",
     "detail": "Remove slide material without choking rivers or destabilising other slopes.",
     "requires_assessment": True, "manageable_when": "After road access is restored"},

    # ---- RESILIENCE (months onward) ----------------------------------------
    {"code": "RSL-SLOPE",   "phase": "RESILIENCE", "title": "Engineer slope stabilisation",
     "detail": "Retaining walls, soil nailing or rock bolting to hold the slope.",
     "requires_assessment": True, "manageable_when": "After funding and design are approved"},
    {"code": "RSL-BIO",     "phase": "RESILIENCE", "title": "Bioengineering — replant deep-rooted vegetation",
     "detail": "Bind the soil naturally to reduce future failures.",
     "requires_assessment": True, "manageable_when": "In the next planting season"},
    {"code": "RSL-DRAIN",   "phase": "RESILIENCE", "title": "Build or upgrade slope drainage",
     "detail": "Control surface and subsurface water — the usual trigger on these hills.",
     "requires_assessment": True, "manageable_when": "According to the engineering design"},
    {"code": "RSL-LANDUSE", "phase": "RESILIENCE", "title": "Decide land use — relocate the most exposed households",
     "detail": "Move people off land that cannot be made safe, with their consent and support.",
     "requires_assessment": True, "manageable_when": "After the hazard zone is declared"},
    {"code": "RSL-MONITOR", "phase": "RESILIENCE", "title": "Install / upgrade monitoring and early-warning links",
     "detail": "Add rain gauges and sensors, and wire them to the alerting system.",
     "requires_assessment": True, "manageable_when": "After site access is restored"},
    {"code": "RSL-PLAN",    "phase": "RESILIENCE", "title": "Update the local disaster-management and evacuation plan",
     "detail": "Fold the lessons of this event into the written plan and routes.",
     "requires_assessment": False, "manageable_when": "After the response is debriefed"},
    {"code": "RSL-DRILL",   "phase": "RESILIENCE", "title": "Run community awareness and evacuation drills",
     "detail": "Make sure people know the warning and where to go before the next monsoon.",
     "requires_assessment": True, "manageable_when": "Before the next monsoon season"},
    {"code": "RSL-FEEDBACK","phase": "RESILIENCE", "title": "Feed the confirmed outcome back into the risk model",
     "detail": "Log the event as ground truth so future predictions improve.",
     "requires_assessment": False, "manageable_when": "Once the event record is verified"},
]


def phases() -> List[Dict[str, str]]:
    """Ordered phase metadata (key, label, window)."""
    return [dict(p) for p in PHASES]


def build_steps(severity: str | None) -> List[Dict[str, Any]]:
    """Return the ordered template steps that apply to an incident of this
    severity. Steps gated by `severity_min` are dropped for milder events; an
    unknown/None severity is treated as the most inclusive (everything applies)."""
    rank = _SEVERITY_RANK.get((severity or "").upper(), max(_SEVERITY_RANK.values()))
    phase_order = {p["key"]: i for i, p in enumerate(PHASES)}
    out: List[Dict[str, Any]] = []
    for idx, s in enumerate(STEPS):
        gate = s.get("severity_min")
        if gate and rank < _SEVERITY_RANK.get(gate, 0):
            continue
        out.append({
            "code": s["code"],
            "phase": s["phase"],
            "title": s["title"],
            "detail": s.get("detail", ""),
            "requires_assessment": bool(s.get("requires_assessment", False)),
            "manageable_when": s.get("manageable_when", ""),
            "phase_order": phase_order.get(s["phase"], 99),
            "step_order": idx,
        })
    return out
