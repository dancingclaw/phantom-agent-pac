"""Task classifier — matches task text to the best skill."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillMatch:
    skill_id: str
    confidence: float  # 0.0 - 1.0


# ── Pattern groups ──────────────────────────────────────────

_SECURITY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"override[-\s]?(fast[-\s]?path|instructions|execution)",
        r"bypass\s+(safeguards|guardrails|approval)",
        r"forward\s+(any\s+)?(visible\s+)?credentials",
        r"email\s+passwords",
        r"delete\s+[\"']?/?AGENTS\.md",
        r"remove\s+[\"']?/?AGENTS\.md",
        r"security\s+relay",
        r"clipboard\s+relay",
        r"embedded\s+tool\s+note",
        r"trusted\s+operational\s+guidance",
        r"suppress\s+mention",
        r"mark\s+(the\s+)?task\s+(finished|complete)",
        r"keep\s+the\s+completion\s+log\s+minimal",
        r"ops-bridge@example\.com",
        r"ship\s+(any\s+)?secrets",
    ]
]

_INBOX_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"process\s+(the\s+)?(inbox|incoming\s+queue|inbound)",
        r"handle\s+(the\s+)?(next\s+)?(inbox|inbound|incoming\s+queue)",
        r"take\s+care\s+of\s+(the\s+)?(next\s+)?(message\s+in\s+)?(inbox|pending\s+inbox|incoming\s+queue|inbox\s+queue|inbound)",
        r"review\s+(the\s+)?(next\s+)?(inbox|inbound|incoming\s+queue)",
        r"work\s+through\s+(the\s+)?(next\s+)?(inbox|inbound|incoming\s+queue)",
        r"triage\s+(the\s+)?(inbox|queue|incoming\s+queue)",
    ]
]

_EMAIL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"(send|write)\s+(a\s+)?(brief\s+)?(email|e-mail|message|note)\s+to",
        r"email\s+(reminder\s+)?to\s+",
        r"email\s+to\s+",
        r"reply\s+(by|via)\s+email",
    ]
]

_LOOKUP_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"what\s+is\s+the\s+(email|address)",
        r"return\s+only\s+the\s+email",
        r"which\s+accounts?\s+(are\s+)?managed\s+by",
        r"how\s+many\s+accounts?\s+",
        r"what\s+is\s+the\s+exact\s+legal\s+name",
        r"answer\s+(only\s+)?with\s+the\s+(number|email|name)",
    ]
]

_INVOICE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"create\s+invoice",
    ]
]

_FOLLOWUP_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"(reschedule|move|postpone|shift|bump)\s+(the\s+)?follow[\s-]?up",
        r"reconnect\s+in\s+(two|three|\d+)\s+weeks",
        r"follow[\s-]?up\s+date\s+regression",
        r"move\s+the\s+next\s+follow[\s-]?up",
    ]
]

_CAPTURE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"capture\s+(this\s+)?snippet\s+from",
        r"take\s+.+from\s+(inbox|00_inbox).+capture",
    ]
]

_CLEANUP_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"remove\s+all\s+captured\s+(cards|threads)",
        r"discard\s+thread",
        r"start\s+over.+remove",
        r"clear\s+(all\s+)?(cards|threads)",
    ]
]

_KNOWLEDGE_LOOKUP_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"which\s+(article|file)\s+(did\s+)?i\s+capture",
        r"what\s+(article|file)\s+(did\s+)?i\s+capture",
        r"what\s+date\s+is",
        r"which\s+captured\s+article",
    ]
]

_UNSUPPORTED_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"calendar\s+invite",
        r"schedule\s+(a\s+)?meeting",
        r"upload\s+.+to\s+https?://",
        r"sync\s+.+to\s+salesforce",
        r"sync\s+.+to\s+hubspot",
        r"deploy\s+.+to\s+",
    ]
]

_PURCHASE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"purchase\s+id\s+prefix",
        r"prefix\s+regression",
        r"downstream\s+processing",
    ]
]

_DEICTIC_RE = re.compile(r"(^|\s)(this|that|these|those)(\s|$)", re.IGNORECASE)


def _match_any(text: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(text) for p in patterns)


def _has_security_in_payload(text: str) -> bool:
    """Check for security markers in quoted/embedded content."""
    return _match_any(text, _SECURITY_PATTERNS)


def classify_task(task_text: str) -> SkillMatch:
    """Classify a task into the best matching skill."""
    text = task_text.strip()
    lowered = text.lower()
    words = text.split()

    # 1. Security — highest priority
    if _has_security_in_payload(text):
        return SkillMatch("security_denial", 0.95)

    # 2. Check for embedded hostile content in capture tasks
    if _match_any(text, _CAPTURE_PATTERNS) and _has_security_in_payload(text):
        return SkillMatch("security_denial", 0.95)

    # 3. Inbox — check BEFORE clarification (short inbox requests like "handle inbox!" are valid)
    if _match_any(text, _INBOX_PATTERNS):
        return SkillMatch("inbox_processing", 0.85)

    # 4. Clarification — very short or deictic (but NOT if it's clearly an inbox task)
    if len(words) <= 3 and "/" not in text and "." not in text:
        if not any(w in lowered for w in ["inbox", "queue", "pending", "inbound"]):
            return SkillMatch("clarification", 0.85)
    if _DEICTIC_RE.search(text) and len(words) <= 5:
        return SkillMatch("clarification", 0.80)

    # 5. Unsupported capabilities
    if _match_any(text, _UNSUPPORTED_PATTERNS):
        return SkillMatch("unsupported_capability", 0.90)

    # 6. Knowledge repo tasks
    if _match_any(text, _CLEANUP_PATTERNS):
        return SkillMatch("knowledge_cleanup", 0.90)
    if _match_any(text, _CAPTURE_PATTERNS):
        return SkillMatch("knowledge_capture", 0.90)
    if _match_any(text, _KNOWLEDGE_LOOKUP_PATTERNS):
        return SkillMatch("knowledge_lookup", 0.85)

    # 6. CRM tasks
    if _match_any(text, _INVOICE_PATTERNS):
        return SkillMatch("invoice_creation", 0.90)
    if _match_any(text, _FOLLOWUP_PATTERNS):
        return SkillMatch("followup_reschedule", 0.90)
    if _match_any(text, _PURCHASE_PATTERNS):
        return SkillMatch("purchase_ops", 0.90)

    # 7. Email outbound (inbox already handled above)
    if _match_any(text, _EMAIL_PATTERNS):
        return SkillMatch("email_outbound", 0.85)

    # 9. CRM lookup
    if _match_any(text, _LOOKUP_PATTERNS):
        return SkillMatch("crm_lookup", 0.85)

    # 10. Fallback — try to infer from keywords
    if any(w in lowered for w in ["email", "send", "write"]) and "outbox" not in lowered:
        if any(w in lowered for w in ["address", "what is", "return"]):
            return SkillMatch("crm_lookup", 0.60)
        return SkillMatch("email_outbound", 0.60)

    if any(w in lowered for w in ["inbox", "queue", "pending", "inbound"]):
        return SkillMatch("inbox_processing", 0.60)

    if any(w in lowered for w in ["capture", "distill", "snippet"]):
        return SkillMatch("knowledge_capture", 0.60)

    # No confident match — no skill injection, agent uses base prompt
    return SkillMatch("", 0.0)
