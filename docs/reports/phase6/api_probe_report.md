# API Probe Report

- generated_at: 2026-02-07T09:50:22.889332+00:00
- scenario_passed: 5/5
- step_passed: 31/31
- pass_rate: 100.0%
- total_duration_ms: 370.62

## health_ready [PASS]

- duration_ms: 5.17

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| healthz | PASS | 200 | 3.46 | service healthy |
| readyz | PASS | 200 | 1.67 | service ready |

## agents_tasks_crud [PASS]

- duration_ms: 103.49

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe CRUD Agent | PASS | 201 | 12.24 | agent_id=1 |
| list_agents | PASS | 200 | 4.77 | agent visible in list |
| get_agent | PASS | 200 | 3.46 | agent fetched |
| update_agent | PASS | 200 | 9.45 | agent updated |
| create_task:Probe CRUD Task | PASS | 201 | 13.45 | task_id=1 |
| list_tasks | PASS | 200 | 3.78 | task visible in list |
| update_task | PASS | 200 | 11.8 | task updated |
| get_task | PASS | 200 | 3.57 | task fetched |
| delete_task | PASS | 204 | 13.43 | task deleted |
| delete_agent | PASS | 204 | 27.23 | agent deleted |

## run_and_commands [PASS]

- duration_ms: 175.01

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe Runtime Agent | PASS | 201 | 30.77 | agent_id=1 |
| create_task:Probe Command Task | PASS | 201 | 10.58 | task_id=1 |
| task_start | PASS | 200 | 10.12 | task status=running |
| task_pause | PASS | 200 | 10.97 | task status=blocked |
| task_resume | PASS | 200 | 10.28 | task status=running |
| task_cancel | PASS | 200 | 9.09 | task status=cancelled |
| task_retry | PASS | 200 | 9.15 | task status=todo |
| create_task:Probe Run Task | PASS | 201 | 16.21 | task_id=2 |
| task_run | PASS | 200 | 57.96 | run_id=1 |
| task_run_idempotent_replay | PASS | 200 | 9.56 | idempotent replay confirmed |

## inbox_close_with_user_input [PASS]

- duration_ms: 59.63

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe Inbox Agent | PASS | 201 | 9.22 | agent_id=2 |
| create_task:Probe Inbox Task | PASS | 201 | 12.17 | task_id=3 |
| tool_request_input | PASS | 200 | 17.06 | inbox_item_id=1 |
| inbox_close | PASS | 200 | 15.1 | inbox item closed |
| inbox_query_closed | PASS | 200 | 5.89 | closed item query success |

## events_query_and_stream [PASS]

- duration_ms: 27.32

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| events_create_first | PASS | 201 | 10.66 | event_id=31 |
| events_stream_replay_last | PASS | 200 | 3.86 | replayed_event_id=31 |
| events_create_second | PASS | 201 | 8.48 | event_id=32 |
| events_stream_resume | PASS | 200 | 3.91 | streamed_event_id=32 |
