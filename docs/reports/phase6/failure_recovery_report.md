# Failure Recovery Probe Report

- generated_at: 2026-02-07T09:39:10.369946+00:00
- scenario_passed: 4/4
- pass_rate: 100.0%
- total_duration_ms: 1102.25

| Scenario | Result | Duration(ms) | Detail |
| --- | --- | ---: | --- |
| timeout_backoff | PASS | 324.18 | {"first_status": "succeeded", "resumed_run_ids": [1], "final_status": "succeeded"} |
| transient_retry | PASS | 272.19 | {"first_status": "succeeded", "resumed_count": 1, "final_status": "succeeded"} |
| duplicate_request_idempotency | PASS | 237.29 | {"run_id": 1, "second_status": "succeeded", "llm_invocations": 1} |
| restart_recovery | PASS | 268.59 | {"interrupted_run_ids": [1], "resumed_run_ids": [2]} |
