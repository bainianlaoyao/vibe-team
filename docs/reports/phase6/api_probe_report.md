# API Probe Report

- generated_at: 2026-02-07T09:39:07.908656+00:00
- scenario_passed: 5/5
- step_passed: 31/31
- pass_rate: 100.0%
- total_duration_ms: 299.9

## health_ready [PASS]

- duration_ms: 5.31

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| healthz | PASS | 200 | 3.61 | service healthy |
| readyz | PASS | 200 | 1.65 | service ready |

## agents_tasks_crud [PASS]

- duration_ms: 68.96

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe CRUD Agent | PASS | 201 | 10.95 | agent_id=1 |
| list_agents | PASS | 200 | 3.4 | agent visible in list |
| get_agent | PASS | 200 | 2.89 | agent fetched |
| update_agent | PASS | 200 | 7.63 | agent updated |
| create_task:Probe CRUD Task | PASS | 201 | 11.36 | task_id=1 |
| list_tasks | PASS | 200 | 4.18 | task visible in list |
| update_task | PASS | 200 | 10.69 | task updated |
| get_task | PASS | 200 | 2.53 | task fetched |
| delete_task | PASS | 204 | 7.7 | task deleted |
| delete_agent | PASS | 204 | 7.38 | agent deleted |

## run_and_commands [PASS]

- duration_ms: 150.66

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe Runtime Agent | PASS | 201 | 7.66 | agent_id=1 |
| create_task:Probe Command Task | PASS | 201 | 10.45 | task_id=1 |
| task_start | PASS | 200 | 11.29 | task status=running |
| task_pause | PASS | 200 | 8.9 | task status=blocked |
| task_resume | PASS | 200 | 8.86 | task status=running |
| task_cancel | PASS | 200 | 9.34 | task status=cancelled |
| task_retry | PASS | 200 | 8.45 | task status=todo |
| create_task:Probe Run Task | PASS | 201 | 8.07 | task_id=2 |
| task_run | PASS | 200 | 68.92 | run_id=1 |
| task_run_idempotent_replay | PASS | 200 | 8.4 | idempotent replay confirmed |

## inbox_close_with_user_input [PASS]

- duration_ms: 51.03

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| create_agent:Probe Inbox Agent | PASS | 201 | 8.6 | agent_id=2 |
| create_task:Probe Inbox Task | PASS | 201 | 9.47 | task_id=3 |
| tool_request_input | PASS | 200 | 16.35 | inbox_item_id=1 |
| inbox_close | PASS | 200 | 13.1 | inbox item closed |
| inbox_query_closed | PASS | 200 | 3.34 | closed item query success |

## events_query_and_stream [PASS]

- duration_ms: 23.94

| Step | Result | HTTP | Latency(ms) | Detail |
| --- | --- | --- | ---: | --- |
| events_create_first | PASS | 201 | 8.82 | event_id=31 |
| events_stream_replay_last | PASS | 200 | 3.27 | replayed_event_id=31 |
| events_create_second | PASS | 201 | 8.79 | event_id=32 |
| events_stream_resume | PASS | 200 | 2.77 | streamed_event_id=32 |
