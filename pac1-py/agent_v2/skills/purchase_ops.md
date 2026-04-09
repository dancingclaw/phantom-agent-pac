<SKILL_PURCHASE_OPS>
This task asks you to fix a purchase processing issue (ID prefix regression).

WORKFLOW:
1. Read /docs/purchase-id-workflow.md to understand the processing pipeline
2. List /processing/ to find active lanes
3. Read the active lane configuration
4. Identify the prefix regression (wrong prefix on downstream processing)
5. Fix the prefix in the active lane
6. Verify by reading the file back
7. report_completion with grounding_refs including docs, processing, and purchase paths

Key concept: purchases flow through processing lanes. Each lane has an ID prefix
format. A "regression" means the prefix was changed incorrectly and needs to be reverted
or fixed to match the documented format.
</SKILL_PURCHASE_OPS>
