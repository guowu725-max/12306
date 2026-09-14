# WeCom Ticket Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add daily scheduled 12306 monitoring that sends an enterprise WeChat smart-bot confirmation card and only submits an order after the user confirms and availability is re-checked.

**Architecture:** Keep the existing one-off `TicketScheduler` unchanged as much as possible. Add a separate confirmation runner that owns daily cron registration, periodic availability scans, pending confirmation records, WeCom card interaction, fresh re-query, and final order submission; it reuses the existing `QueryService`, `OrderService`, SQLAlchemy session factory, and app lifecycle.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, SQLite, APScheduler 3, existing QueryService/OrderService, official `wecom-aibot-python-sdk`, Vue 3 + Element Plus.

**Spec:** `docs/superpowers/specs/2026-09-14-wecom-ticket-confirmation-design.md`

## Global Constraints

- Preserve the existing one-off task behavior and Docker deployment.
- Do not automate payment, bypass CAPTCHA, bypass rate limits, or bypass 12306 access controls.
- A WeCom confirmation must never submit using stale availability; re-query immediately before ordering.
- A confirmation can cause at most one order attempt.
- Default confirmation expiry is 60 seconds; accepted range is 15–300 seconds.
- Daily scheduling uses the configured project timezone, default `Asia/Shanghai`.
- Existing SQLite databases must upgrade idempotently without requiring recreation.

---

### Task 1: Scheduling domain and database model

**Files:**
- Create: `backend/app/models/confirmation.py`
- Create: `backend/app/services/confirmation_domain.py`
- Create: `backend/app/core/migrations.py`
- Modify: `backend/app/models/task.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py`
- Test: `backend/tests/test_confirmation_domain.py`

**Interfaces:**
- Produces: `resolve_train_date(train_date, date_strategy, date_offset_days, now=None) -> str`
- Produces: `parse_daily_start_time(value: str) -> tuple[int, int]`
- Produces: `TicketConfirmation` ORM model and confirmation status enum.

- [ ] Write tests for fixed/offset date resolution, HH:MM validation, and expiry boundaries.
- [ ] Implement domain helpers and model fields.
- [ ] Add idempotent SQLite column upgrades for task schedule fields.
- [ ] Ensure new confirmation table is registered before `create_all`.

### Task 2: WeCom card adapter

**Files:**
- Create: `backend/app/services/wecom_confirmation.py`
- Create: `backend/tests/test_wecom_confirmation.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces: `WeComConfirmationBot.start()`, `stop()`, `send_confirmation(...)`, `send_text(...)`.
- Produces: event parser returning `(action, confirmation_id, token, actor_id)`.

- [ ] Test card payload, token/task-id parsing, actor extraction, and invalid events.
- [ ] Wrap the official WeCom Python SDK behind a small adapter so tests do not require a live bot.
- [ ] Add Bot ID/Secret/chat/allowed-user/expiry settings.

### Task 3: Confirmation service and safe order execution

**Files:**
- Create: `backend/app/services/ticket_confirmation_service.py`
- Create: `backend/tests/test_ticket_confirmation_service.py`

**Interfaces:**
- Produces: `create_pending_confirmation(...)` with duplicate suppression.
- Produces: `handle_action(action, confirmation_id, raw_token, actor_id)`.
- Consumes: existing `QueryService.query` and `OrderService.buy_ticket`.

- [ ] Test pending de-duplication and token verification.
- [ ] Test expiry and allowed-user rejection.
- [ ] Test that confirm always re-queries and refuses an unavailable seat.
- [ ] Test that duplicate confirm cannot call `buy_ticket` twice.
- [ ] Implement passenger refresh/matching before `buy_ticket`.
- [ ] Mark consumed only after acquiring the confirmation for a single execution path.

### Task 4: Daily confirmation runner

**Files:**
- Create: `backend/app/tasks/confirmation_runner.py`
- Create: `backend/tests/test_confirmation_runner.py`

**Interfaces:**
- Produces: singleton `get_confirmation_runner()` with `start()`, `shutdown()`, `reload_tasks()`, `run_daily_task(task_id)`, `scan_task(task_id, effective_date)`.

- [ ] Test cron registration from `daily_start_time`.
- [ ] Test offset date resolution at daily trigger.
- [ ] Test availability scan filters configured train codes and seat priority.
- [ ] Implement a housekeeping reload job so task edits take effect without service restart.
- [ ] Stop the day's scan after a successful submitted order; leave the next-day cron intact.

### Task 5: API/schema/lifecycle integration

**Files:**
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/app/api/tasks.py`
- Modify: `backend/main.py`
- Create: `backend/app/api/confirmations.py`
- Create: `backend/app/schemas/confirmation.py`

**Interfaces:**
- Task API accepts `schedule_mode`, `daily_start_time`, `date_strategy`, `date_offset_days`, `confirmation_required`.
- Read-only confirmation endpoint exposes current confirmation status to the authenticated task owner.

- [ ] Validate daily tasks require `daily_start_time` and confirmation tasks require WeCom configuration at runtime.
- [ ] Persist new task fields in create/update/response.
- [ ] Start/stop WeCom bot and confirmation runner in FastAPI lifespan.
- [ ] Keep existing `/tasks/{id}/start` behavior for legacy one-off tasks.

### Task 6: Minimal frontend and deployment documentation

**Files:**
- Modify: `frontend/src/views/CreateTask.vue`
- Modify: `frontend/src/views/TaskDetail.vue`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] Add daily/one-off mode, daily time, fixed/offset date strategy, and WeCom-confirm toggle to the task form.
- [ ] Display schedule and confirmation mode on task detail.
- [ ] Document enterprise WeChat smart-bot setup and required environment variables.
- [ ] Document that payment remains in official 12306.

### Task 7: Verification and PR

**Files:**
- Test: all backend tests
- Check: frontend build

- [ ] Run/trigger backend tests if a runnable environment or CI is available.
- [ ] Run/trigger frontend build if a runnable environment or CI is available.
- [ ] Review branch diff for secrets, stale-order paths, and duplicate-submit paths.
- [ ] Open a PR from `feature/wecom-confirmation` to `main` with deployment/configuration notes and explicitly state any verification that could not be executed.
