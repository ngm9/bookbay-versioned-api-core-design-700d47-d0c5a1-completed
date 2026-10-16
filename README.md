# Bookbay Versioned Api Core Design

The main.py module constructs the FastAPI application and includes routers from routes_v1.py and routes_misc.py. The first route module contains 24 user and order handlers, while the second contains 19 listing, search, cancellation, and refund handlers.

This repository is the Python implementation of that system.

## Helpful Tips

- Read `docs/DESIGN.md` — the design document — for the full background on this task.
- Review the source code below to see exactly how the current system works.
- On the Utkrusht whiteboard for this task, the current system is already drawn and locked for reference — draw your redesigned architecture in the same Low-Level Design area.
- You're welcome to update `docs/DESIGN.md` or add your own files to this repository to capture your design notes as you work.

## Objectives
Please commit an updated DESIGN.md capturing your rationale, decisions and assumptions. Also update the excalidraw diagram to show the changes you propose. You are tasked with the following changes:
- Redesign the Bookbay API core so new clients receive stable, testable contracts.
- Keep the existing mobile app working unchanged throughout the six-month migration.
- Ensure retrying one checkout action can never create a second order.
- Unify collection and error behavior so partner clients can integrate predictably.
- Justify versioning, action modeling, idempotency, and dependency-boundary trade-offs.

## What's in this repository

- `docs/DESIGN.md` — the design document
- The current implementation, organized as a standard Python project:
  - main.py — `app/__init__.py`, `app/main.py`
  - db.py — `app/db.py`
  - models.py — `app/models.py`
  - schemas.py — `app/schemas.py`
  - auth.py — `app/auth.py`
  - errors.py — `app/errors.py`
  - notifications.py — `app/notifications.py`
  - routes_v1.py — `app/routes_v1.py`
  - routes_misc.py — `app/routes_misc.py`
