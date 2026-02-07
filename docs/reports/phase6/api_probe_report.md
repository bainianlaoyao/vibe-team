# API Probe Report

- generated_at: 2026-02-07T10:19:25.128745+00:00
- scenario_passed: 5/5
- step_passed: 31/31
- pass_rate: 100.0%
- total_duration_ms: 316.91

## health_ready [PASS]

- duration_ms: 6.64

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| healthz | PASS | 200 | 4.39 | service healthy |
| readyz | PASS | 200 | 2.17 | service ready |

## agents_tasks_crud [PASS]

- duration_ms: 80.43

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe CRUD Agent | PASS | 201 | 11.07 | agent_id=1 |
| list_agents | PASS | 200 | 5.19 | agent visible in list |
| get_agent | PASS | 200 | 3.64 | agent fetched |
| update_agent | PASS | 200 | 9.71 | agent updated |
| create_task:Probe CRUD Task | PASS | 201 | 12.57 | task_id=1 |
| list_tasks | PASS | 200 | 4.33 | task visible in list |
| update_task | PASS | 200 | 12.26 | task updated |
| get_task | PASS | 200 | 3.59 | task fetched |
| delete_task | PASS | 204 | 9.2 | task deleted |
| delete_agent | PASS | 204 | 8.57 | agent deleted |

## run_and_commands [PASS]

- duration_ms: 148.21

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe Runtime Agent | PASS | 201 | 9.68 | agent_id=1 |
| create_task:Probe Command Task | PASS | 201 | 14.34 | task_id=1 |
| task_start | PASS | 200 | 8.84 | task status=running |
| task_pause | PASS | 200 | 9.11 | task status=blocked |
| task_resume | PASS | 200 | 11.27 | task status=running |
| task_cancel | PASS | 200 | 8.85 | task status=cancelled |
| task_retry | PASS | 200 | 8.09 | task status=todo |
| create_task:Probe Run Task | PASS | 201 | 12.69 | task_id=2 |
| task_run | PASS | 200 | 56.05 | run_id=1 |
| task_run_idempotent_replay | PASS | 200 | 8.91 | idempotent replay confirmed |

## inbox_close_with_user_input [PASS]

- duration_ms: 51.99

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe Inbox Agent | PASS | 201 | 6.52 | agent_id=2 |
| create_task:Probe Inbox Task | PASS | 201 | 8.74 | task_id=3 |
| tool_request_input | PASS | 200 | 15.43 | inbox_item_id=1 |
| inbox_close | PASS | 200 | 15.6 | inbox item closed |
| inbox_query_closed | PASS | 200 | 5.51 | closed item query success |

## events_query_and_stream [PASS]

- duration_ms: 29.64

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| events_create_first | PASS | 201 | 12.25 | event_id=31 |
| events_stream_replay_last | PASS | 200 | 4.79 | replayed_event_id=31 |
| events_create_second | PASS | 201 | 7.9 | event_id=32 |
| events_stream_resume | PASS | 200 | 4.32 | streamed_event_id=32 |
