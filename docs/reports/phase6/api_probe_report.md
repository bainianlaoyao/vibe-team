# API Probe Report

- generated_at: 2026-02-07T09:32:13.639872+00:00
- scenario_passed: 5/5
- step_passed: 31/31
- pass_rate: 100.0%
- total_duration_ms: 262.13

## health_ready [PASS]

- duration_ms: 4.69

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| healthz | PASS | 200 | 3.22 | service healthy |
| readyz | PASS | 200 | 1.43 | service ready |

## agents_tasks_crud [PASS]

- duration_ms: 65.36

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe CRUD Agent | PASS | 201 | 10.08 | agent_id=1 |
| list_agents | PASS | 200 | 3.16 | agent visible in list |
| get_agent | PASS | 200 | 2.79 | agent fetched |
| update_agent | PASS | 200 | 8.03 | agent updated |
| create_task:Probe CRUD Task | PASS | 201 | 10.33 | task_id=1 |
| list_tasks | PASS | 200 | 3.36 | task visible in list |
| update_task | PASS | 200 | 9.67 | task updated |
| get_task | PASS | 200 | 2.44 | task fetched |
| delete_task | PASS | 204 | 8.24 | task deleted |
| delete_agent | PASS | 204 | 7.04 | agent deleted |

## run_and_commands [PASS]

- duration_ms: 126.05

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe Runtime Agent | PASS | 201 | 6.46 | agent_id=1 |
| create_task:Probe Command Task | PASS | 201 | 7.74 | task_id=1 |
| task_start | PASS | 200 | 7.65 | task status=running |
| task_pause | PASS | 200 | 8.5 | task status=blocked |
| task_resume | PASS | 200 | 8.62 | task status=running |
| task_cancel | PASS | 200 | 7.91 | task status=cancelled |
| task_retry | PASS | 200 | 7.66 | task status=todo |
| create_task:Probe Run Task | PASS | 201 | 7.49 | task_id=2 |
| task_run | PASS | 200 | 55.34 | run_id=1 |
| task_run_idempotent_replay | PASS | 200 | 8.4 | idempotent replay confirmed |

## inbox_close_with_user_input [PASS]

- duration_ms: 42.61

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe Inbox Agent | PASS | 201 | 7.38 | agent_id=2 |
| create_task:Probe Inbox Task | PASS | 201 | 8.12 | task_id=3 |
| tool_request_input | PASS | 200 | 12.73 | inbox_item_id=1 |
| inbox_close | PASS | 200 | 10.85 | inbox item closed |
| inbox_query_closed | PASS | 200 | 3.39 | closed item query success |

## events_query_and_stream [PASS]

- duration_ms: 23.42

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| events_create_first | PASS | 201 | 9.03 | event_id=31 |
| events_stream_replay_last | PASS | 200 | 3.24 | replayed_event_id=31 |
| events_create_second | PASS | 201 | 8.26 | event_id=32 |
| events_stream_resume | PASS | 200 | 2.6 | streamed_event_id=32 |
