# GitHub Actions Pages Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace branch-based Pages publishing and automated `main` writes with an explicit, validated GitHub Pages artifact deployment.

**Architecture:** The scheduled workflow generates data in its ephemeral runner, executes the full test suite and deployment validation, assembles `_site/`, uploads a Pages artifact, and deploys it with the minimum Pages permissions. `main` remains the code/configuration branch and is no longer mutated every 30 minutes.

**Tech Stack:** GitHub Actions, GitHub Pages, Python 3.11, pytest, Node.js built-in test runner.

## Global Constraints

- Keep the 30-minute schedule and manual dispatch.
- Do not use the public example OPML in production.
- Do not commit generated snapshots from the scheduled workflow.
- Refuse to replace production when required files are missing, JSON is invalid, data is stale, counts are inconsistent, or all source groups fail.
- Preserve optional DeepSeek Persona enhancement.

---

### Task 1: Add deployment contract tests and validator

**Files:**
- Create: `scripts/validate_deployment.py`
- Create: `tests/test_validate_deployment.py`
- Create: `tests/test_deployment_workflow.py`

- [ ] Define required static and JSON files.
- [ ] Test missing files, stale data, item-count mismatch, and zero successful source groups.
- [ ] Implement `validate_site()` and its CLI.
- [ ] Verify `python -m pytest -q tests/test_validate_deployment.py tests/test_deployment_workflow.py` passes.

### Task 2: Replace branch publishing with Pages artifacts

**Files:**
- Modify: `.github/workflows/update-news.yml`
- Create: `.github/workflows/ci.yml`

- [ ] Remove `contents: write`, `git commit`, and `git push`.
- [ ] Disable OPML unless `FOLLOW_OPML_B64` is configured.
- [ ] Wire DeepSeek Secret/Variables into the data generation step.
- [ ] Run tests and deployment validation before artifact upload.
- [ ] Deploy `_site/` with `actions/upload-pages-artifact` and `actions/deploy-pages`.
- [ ] Add pull-request and `main` CI with read-only permissions.

### Task 3: Update deployment documentation

**Files:**
- Modify: `README.md`

- [ ] Explain the ephemeral build and Pages artifact flow.
- [ ] Instruct maintainers to choose “GitHub Actions” as the Pages source.
- [ ] Document that the example OPML is local-only and DeepSeek uses repository Variables plus a Secret.
- [ ] Explain that scheduled runs no longer create snapshot commits on `main`.
