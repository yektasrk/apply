"""
fit.py — Shortlist career-page roles: strong fits, borderline ones, and the rest.

The career-page watcher (`job_finder.career_pages`) should only add the roles
most worth applying to. This module sorts each role that already passed the
watcher's title and location filters into one of three levels:

- `STRONG`: a core SRE/platform/DevOps title, a description that overlaps the
  resume's demonstrated skills broadly, and nothing that needs a closer look.
  Written as ⭐ Ultra Suitable, skipping triage.
- `BORDERLINE`: plausible, but something needs a human read — a peripheral
  title, thin overlap, a heavy AWS/Azure/GCP focus, 8-9 years required, or no
  description at all. Written with a blank status, so triage decides it by
  reading the full description as its rubric requires.
- `WEAK`: a hard blocker (required Dutch, no visa sponsorship, a security
  clearance, 10+ years) or almost no overlap with the resume. Not written.

This is a rules-based shortlist, not a suitability judgment: anything it is not
sure about goes to triage rather than being starred or dropped.
"""

import re
from dataclasses import dataclass, field

STRONG = "strong"
BORDERLINE = "borderline"
WEAK = "weak"

# The resume's demonstrated skills (resume.md), as label -> pattern. A role's
# overlap is the number of distinct labels its description mentions.
RESUME_SKILLS: dict[str, str] = {
    "Kubernetes": r"kubernetes|k8s|helm|kubernetes operators?",
    "Docker": r"docker|containers?|containeri[sz]ation",
    "Nomad": r"nomad",
    "Linux": r"linux|unix",
    "Kafka": r"kafka",
    "Hadoop": r"hadoop|hdfs|yarn|zookeeper",
    "Elasticsearch": r"elasticsearch|elastic stack|elk|opensearch",
    "PostgreSQL": r"postgres(?:ql)?",
    "Redis": r"redis",
    "Prometheus": r"prometheus",
    "Observability": r"observability|monitoring|alerting|slos?|slis?|grafana",
    "Identity": r"keycloak|active directory|kerberos|ldap|sso|single sign-on",
    "Ansible": r"ansible",
    "Argo CD": r"argo ?cd|gitops",
    "CI/CD": r"ci/cd|ci cd|ci system|continuous (?:integration|delivery|deployment)|github actions|gitlab(?: ci)?|jenkins|teamcity",
    "Object storage": r"s3|minio|object storage",
    "Go": r"golang|go(?= (?:developer|engineer|programming|language|services?|code))|\(go\)|in go\b",
    # "Go" in a list of languages ("Java/Kotlin, Go, Python") is matched
    # separately and case-sensitively in resume_skills: lowercase "go" is a verb.
    "Python": r"python",
    "Bash": r"bash|shell scripting",
    "On-call": r"on-?call|incident (?:response|management)|post-?mortems?",
    "Distributed systems": r"distributed systems?|high availability|scalab(?:le|ility)",
}
_SKILL_PATTERNS = {
    label: re.compile(rf"(?<![\w/]){pattern}(?![\w/])", re.IGNORECASE)
    for label, pattern in RESUME_SKILLS.items()
}

STRONG_MIN_SKILLS = 5
WEAK_MAX_SKILLS = 2  # this many or fewer distinct resume skills is too little overlap

# Titles whose central work is what the resume shows. Anything else that got
# past the watcher's broader title filter (storage, network, HPC, sysadmin,
# cloud engineer, data platform...) is a borderline title.
CORE_TITLE = re.compile(
    r"(?<!\w)(?:site reliability|sre|reliability engineer|platform engineer(?:ing)?|"
    r"dev ?(?:sec)?ops|infrastructure (?:engineer|developer)|kubernetes|linux|"
    r"production engineer|cloud native|cloud operations)(?!\w)",
    re.IGNORECASE,
)
# A core title that is really about something else ("Data Platform", "SAP").
OFF_CORE_TITLE = re.compile(
    r"(?<!\w)(?:data platform|data engineer|sap|salesforce|windows|dba|scada|iam)(?!\w)", re.IGNORECASE
)

_SENTENCE = re.compile(r"[^.!?\n]*")
_SOFTENERS = re.compile(
    r"plus|nice to have|not (?:a )?(?:requirement|required|necessary|mandatory)|preferred|"
    r"bonus|advantage|pr[eé]f[eé]rable|helpful|welcome|is not needed|geen vereiste",
    re.IGNORECASE,
)
DUTCH_REQUIRED = re.compile(
    r"(?:fluent|native|proficien\w*|professional|excellent|strong|good|full)\s+(?:command\s+of\s+(?:the\s+)?)?"
    r"(?:(?:written|spoken|verbal)\s+(?:and\s+(?:written|spoken|verbal)\s+)?)?dutch|"
    r"dutch\s*(?:language\s*)?(?:\(|is\s+|at\s+)?(?:required|mandatory|essential|a must|c1|b2|native)|"
    r"(?:vloeiend|uitstekend|goed)e?\s+(?:beheersing\s+van\s+(?:de\s+)?)?nederlands|"
    r"nederlands\w*\s+(?:is\s+)?(?:vereist|verplicht|een must)|"
    r"beheersing\s+van\s+de\s+nederlandse\s+taal",
    re.IGNORECASE,
)
NO_SPONSORSHIP = re.compile(
    r"(?:not|unable to|cannot|can't|do not|don't|won't)\s+(?:offer|provide|support)?\s*(?:visa\s+)?sponsor|"
    r"no\s+(?:visa\s+)?sponsorship|sponsorship\s+is\s+not\s+(?:available|offered|possible)|"
    r"must\s+(?:already\s+)?(?:have|hold)\s+(?:a\s+valid\s+|the\s+)?(?:eu\s+)?(?:work\s+permit|right\s+to\s+work)|"
    r"(?:eu|eea|dutch)\s+(?:citizenship|nationality|passport)\s+(?:is\s+)?(?:required|mandatory)|"
    r"geen\s+(?:visum|sponsoring)",
    re.IGNORECASE,
)
CLEARANCE = re.compile(
    r"security\s+clearance|(?<!\w)[abc]-screening|aivd|mivd|nato\s+secret|staatsgeheim",
    re.IGNORECASE,
)
YEARS = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:\+|or\s+more|plus)?\s*(?:years?|yrs|jaar)(?=[^.\n]{0,60}(?:experience|ervaring))",
    re.IGNORECASE,
)
CLOUD = re.compile(r"(?<!\w)(?:azure|aws|amazon web services|gcp|google cloud)(?!\w)", re.IGNORECASE)
CLOUD_HEAVY_MENTIONS = 5


@dataclass
class Fit:
    level: str
    reason: str
    skills: list[str] = field(default_factory=list)


GO_IN_LIST = re.compile(r"(?<![A-Za-z])Go(?=\s*[,/)]|\s+(?:and|or)\s)|(?<=[,/(]\s)Go(?![A-Za-z])")


def resume_skills(description: str) -> list[str]:
    """Resume skill labels the description mentions, in RESUME_SKILLS order."""
    found = {label for label, pattern in _SKILL_PATTERNS.items() if pattern.search(description)}
    if GO_IN_LIST.search(description):
        found.add("Go")
    return [label for label in RESUME_SKILLS if label in found]


def _unsoftened(pattern: re.Pattern, text: str) -> str:
    """The first match of `pattern` whose sentence does not call it optional."""
    for match in pattern.finditer(text):
        start = text.rfind(".", 0, match.start()) + 1
        end_match = _SENTENCE.match(text, match.end())
        sentence = text[start : end_match.end() if end_match else match.end()]
        if not _SOFTENERS.search(sentence):
            return match.group(0)
    return ""


def required_years(description: str) -> int:
    """The highest 'N+ years ... experience' the description asks for (0 if none)."""
    values = [int(m.group(1)) for m in YEARS.finditer(description)]
    return max((v for v in values if v <= 25), default=0)


def assess_fit(title: str, description: str) -> Fit:
    title = str(title or "")
    text = str(description or "")

    if found := _unsoftened(DUTCH_REQUIRED, text):
        return Fit(WEAK, f'Requires Dutch ("{found}"); the resume shows no Dutch proficiency.')
    if found := _unsoftened(NO_SPONSORSHIP, text):
        return Fit(WEAK, f'No visa sponsorship ("{found}"); the user needs a sponsored permit.')
    if found := CLEARANCE.search(text):
        return Fit(WEAK, f'Requires a security clearance ("{found.group(0)}").')
    years = required_years(text)
    if years >= 10:
        return Fit(WEAK, f"Requires {years}+ years of experience; the resume shows about 6.")

    if not text.strip():
        return Fit(BORDERLINE, "No description could be read; check the posting.")

    skills = resume_skills(text)
    core = bool(CORE_TITLE.search(title)) and not OFF_CORE_TITLE.search(title)
    # A core title with a tool-light description still goes to triage: some
    # SRE postings describe the work without naming a single technology.
    if len(skills) <= WEAK_MAX_SKILLS and not core:
        shown = ", ".join(skills) or "none"
        return Fit(WEAK, f"Little overlap with the resume (only: {shown}).", skills)
    # A peripheral title (storage, network, HPC, cloud engineer...) earns a
    # triage read only when the work itself overlaps the resume broadly.
    if not core and len(skills) < STRONG_MIN_SKILLS:
        return Fit(WEAK, f"Peripheral title with thin overlap ({', '.join(skills)}).", skills)

    concerns = []
    if not core:
        concerns.append("title is outside the core SRE/platform/DevOps family")
    if len(skills) < STRONG_MIN_SKILLS:
        concerns.append(f"overlap is thin ({', '.join(skills)})")
    if 8 <= years < 10:
        concerns.append(f"asks for {years}+ years")
    cloud = len(CLOUD.findall(text))
    if cloud >= CLOUD_HEAVY_MENTIONS:
        concerns.append(f"heavy AWS/Azure/GCP focus ({cloud} mentions)")

    if concerns:
        summary = "; ".join(concerns)
        return Fit(BORDERLINE, summary[0].upper() + summary[1:] + ".", skills)
    return Fit(STRONG, f"Core role; the description matches the resume on {', '.join(skills)}.", skills)
