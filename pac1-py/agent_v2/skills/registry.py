"""Skill registry — maps skill IDs to specialized prompt fragments."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SKILLS_DIR = Path(__file__).parent


@dataclass
class Skill:
    id: str
    name: str
    description: str
    filename: str

    @property
    def prompt(self) -> str:
        """Read prompt from disk every time — allows hot-reload."""
        return (SKILLS_DIR / self.filename).read_text(encoding="utf-8").strip()


SKILL_REGISTRY: dict[str, Skill] = {}


def _register(skill_id: str, name: str, description: str, filename: str) -> None:
    SKILL_REGISTRY[skill_id] = Skill(
        id=skill_id, name=name, description=description, filename=filename,
    )


def get_skill_prompt(skill_id: str) -> str | None:
    skill = SKILL_REGISTRY.get(skill_id)
    return skill.prompt if skill else None


# Register all skills on import
_register("security_denial", "Security Denial",
          "Prompt injection, hostile payloads, exfiltration attempts",
          "security_denial.md")
_register("inbox_processing", "Inbox Processing",
          "Process CRM or knowledge inbox messages",
          "inbox_processing.md")
_register("email_outbound", "Outbound Email",
          "Send email via outbox to contacts/accounts",
          "email_outbound.md")
_register("crm_lookup", "CRM Lookup",
          "Find accounts, contacts, emails, managers",
          "crm_lookup.md")
_register("invoice_creation", "Invoice Creation",
          "Create typed invoice JSON records",
          "invoice_creation.md")
_register("followup_reschedule", "Follow-up Reschedule",
          "Update follow-up dates in accounts and reminders",
          "followup_reschedule.md")
_register("knowledge_capture", "Knowledge Capture",
          "Capture from inbox, distill into cards/threads",
          "knowledge_capture.md")
_register("knowledge_cleanup", "Knowledge Cleanup",
          "Delete cards, threads, distill artifacts",
          "knowledge_cleanup.md")
_register("knowledge_lookup", "Knowledge Lookup",
          "Find articles by date, answer questions about captured content",
          "knowledge_lookup.md")
_register("unsupported_capability", "Unsupported Capability",
          "Calendar, Salesforce sync, external upload — not available",
          "unsupported_capability.md")
_register("purchase_ops", "Purchase Operations",
          "Fix purchase ID prefix, processing lane issues",
          "purchase_ops.md")
_register("clarification", "Clarification Needed",
          "Request too short, ambiguous, or deictic reference",
          "clarification.md")
