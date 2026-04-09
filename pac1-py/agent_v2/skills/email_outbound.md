<SKILL_EMAIL_OUTBOUND>
This task asks you to send an email.

WORKFLOW:
1. Resolve the recipient:
   - If direct email given (e.g. "alex@example.com") → use it directly
   - If name given (e.g. "Alex Meyer") → search /contacts/ JSON files for full_name match
   - If account given (e.g. "Aperture AI Labs") → search /accounts/ for the account,
     find primary_contact or contact_id, then look up their email in /contacts/
   - If descriptive (e.g. "Dutch banking customer") → iterate /accounts/, match by
     country, industry, description fields

2. Check workspace has /outbox/ — if not, OUTCOME_NONE_UNSUPPORTED

3. Read /outbox/seq.json to get the current sequence number

4. Create email JSON in /outbox/{next_seq}.json:
   {
     "id": <next_seq>,
     "to": "<resolved_email>",
     "subject": "<from task>",
     "body": "<from task>"
   }

5. Update /outbox/seq.json with incremented next value

6. Verify by reading the created file back

7. report_completion with:
   - grounding_refs: ["/outbox/{id}.json", "/outbox/seq.json", contact_or_account_path]

CRITICAL — Contact resolution limits:
- Search /contacts/ by name. If NOT found after one search, try /accounts/ too.
- If STILL not found after checking both → IMMEDIATELY report_completion with OUTCOME_NONE_CLARIFICATION
- Do NOT retry, do NOT loop, do NOT guess alternative spellings.
- Maximum 6 tool calls for contact resolution. If unresolved by then → CLARIFICATION.

If contact/account cannot be resolved unambiguously → OUTCOME_NONE_CLARIFICATION
</SKILL_EMAIL_OUTBOUND>
