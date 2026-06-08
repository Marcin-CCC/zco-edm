# EDM ZCO Project - Audit Report: Bugs & Improvements

**Date:** 2026-06-07
**Scope:** Full codebase audit (backend, frontend, deployment, documentation)

---

## Critical Bugs (Must Fix)

### 1. [CRITICAL] Webhook Router References Non-Existent Model Columns
**File:** [`backend/app/webhooks/router.py:97-102`](backend/app/webhooks/router.py:97)
**Issue:** The `StatusUpdate` model and endpoint reference `file_obj.ocr_result` and `file_obj.metadata`, but the `File` SQLAlchemy model ([`backend/app/models.py:85`](backend/app/models.py:85)) does not define these columns. The `seed.sql` table definition also lacks these columns.
**Impact:** Webhook status updates will crash with `AttributeError`.
**Fix:** Add `ocr_result` (Text) and `metadata` (JSON) columns to the `File` model and `seed.sql`.

```python
# In models.py File class:
ocr_result = Column(Text, nullable=True)
metadata = Column(Text, nullable=True)  # or JSON if using PostgreSQL JSONB
```

### 2. [CRITICAL] DocumentStatus Enum Mismatch
**File:** [`backend/app/webhooks/router.py:50`](backend/app/webhooks/router.py:50)
**Issue:** References `DocumentStatus.PROCESSED` but the enum ([`backend/app/models.py:24`](backend/app/models.py:24)) defines `READY = "Przetworzono"`, not `PROCESSED`.
**Impact:** Webhook processing will fail with `AttributeError`.
**Fix:** Change to `DocumentStatus.READY` or add `PROCESSED` as an alias.

### 3. [CRITICAL] Hardcoded API URL in Frontend (Bypasses Proxy)
**File:** [`frontend/src/app/dashboard/file-queue/page.tsx:38`](frontend/src/app/dashboard/file-queue/page.tsx:38)
**Issue:** Uses `http://127.0.0.1:8000` directly instead of going through the Next.js proxy (`/api/...`).
**Impact:** Breaks in Docker/production - the file queue page will not work outside local development.
**Fix:** Use the `api.ts` helper or proxy through `/api/processing-queue/`.

### 4. [HIGH] Legacy Duplicate main.py
**File:** [`backend/main.py`](backend/main.py), [`backend/app/main.py`](backend/app/main.py)
**Issue:** Two separate FastAPI application files exist. `backend/main.py` contains old, simplified endpoints while `backend/app/main.py` contains the proper modular app. The Dockerfile CMD runs `uvicorn app.main:app` which loads `backend/app/main.py` - but `backend/main.py` is dead code causing confusion.
**Impact:** Maintenance confusion; old endpoints in `backend/main.py` (e.g., `/api/upload`) may cause conflicts.
**Fix:** Remove `backend/main.py` or consolidate into `backend/app/main.py`.

### 5. [HIGH] Type Mismatch: File Size Column
**File:** [`backend/app/models.py:93`](backend/app/models.py:93) vs [`backend/seed.sql:44`](backend/seed.sql:44)
**Issue:** SQLAlchemy model defines `size = Column(Float)` but seed.sql uses `size BIGINT`.
**Impact:** Potential data type inconsistency when running seed.sql manually.
**Fix:** Align both to use `BIGINT` (integers for byte counts).

---

## Medium Priority Issues

### 6. [MEDIUM] Registration Requires Authentication (Chicken-and-Egg)
**File:** [`backend/app/auth/auth.py:13`](backend/app/auth/auth.py:13)
**Issue:** The `/api/auth/register` endpoint uses `current_user: User = Depends(get_current_user)` as a required dependency, meaning you must be logged in as admin to register new users. There's no mechanism for initial admin creation.
**Impact:** First admin account must be created via `seed.sql` or direct database access.
**Fix:** Add a `FORCE_AUTH_REGISTER` environment variable or separate registration endpoint for initial setup.

### 7. [MEDIUM] React/Type Types Version Mismatch
**File:** [`frontend/package.json:38-40`](frontend/package.json:38)
**Issue:** Uses React 19 runtime (`react: ^19.2.6`, `react-dom: ^19.2.6`) but `@types/react: ^18.2.48` and `@types/react-dom: ^18.2.18`.
**Impact:** TypeScript type errors, potential runtime issues with React 19 features.
**Fix:** Update to `@types/react: ^19.0.0` and `@types/react-dom: ^19.0.0`.

### 8. [MEDIUM] Next.js Version Anomaly
**File:** [`frontend/package.json:28`](frontend/package.json:28)
**Issue:** Specifies `next: ^16.2.6` but Next.js v16 does not exist yet (current stable is v14.x).
**Impact:** Could cause npm resolution issues or refer to a pre-release version.
**Fix:** Verify and correct the Next.js version number.

### 9. [MEDIUM] Unused Dependencies
**File:** [`backend/requirements.txt:17`](backend/requirements.txt:17)
**Issue:** `python-http-client` is listed but never imported or used in the codebase.
**Impact:** Unnecessary dependency bloat.
**Fix:** Remove from requirements.txt.

### 10. [MEDIUM] Inconsistent DOCLING_API_URL Default
**File:** [`backend/app/config.py:37`](backend/app/config.py:37) vs [`docker-compose.yaml:52`](docker-compose.yaml:52)
**Issue:** `config.py` defaults to `http://127.0.0.1:8002` but docker-compose sets `http://docling:8002`.
**Impact:** If env var is not set, container won't connect to Docling.
**Fix:** Align defaults or ensure docker-compose always sets it.

---

## Low Priority / Code Quality Issues

### 11. [LOW] Missing ONDELETE Cascade for Files
**File:** [`backend/seed.sql:45`](backend/seed.sql:45)
**Issue:** `folder_id INTEGER REFERENCES folders(id)` lacks `ON DELETE CASCADE` or `SET NULL`.
**Impact:** Deleting a folder will fail if it contains files due to foreign key constraint.
**Fix:** Add `ON DELETE SET NULL` to allow files to exist without folders.

### 12. [LOW] Unnecessary Exception Handling
**File:** [`backend/app/folders/router.py:81-82`](backend/app/folders/router.py:81)
**Issue:** Try/catch block that catches all exceptions and re-wraps them in a 500 error.
**Impact:** Loses original error context; FastAPI already handles exceptions properly.
**Fix:** Remove unnecessary try/catch.

### 13. [LOW] Comment Typos in Dockerfile
**File:** [`backend/Dockerfile:5`](backend/Dockerfile:5)
**Issue:** Comment says "Instalaza zaleZNOSCI" - multiple typos.
**Impact:** Cosmetic only, but indicates lack of polish.
**Fix:** Correct to "Instalacja zależności".

### 14. [LOW] Missing Database Relation in seed.sql
**File:** [`backend/seed.sql`](backend/seed.sql)
**Issue:** The `seed.sql` creates tables like `documents`, `document_pages`, `processing_queue`, `embeddings`, `events`, `audit_log` that are NOT defined in the SQLAlchemy models ([`backend/app/models.py`](backend/app/models.py)).
**Impact:** These tables are created by seed.sql but the application code never uses them - dead schema.
**Fix:** Either add corresponding SQLAlchemy models or remove unused tables from seed.sql.

### 15. [LOW] No Refresh Token Implementation
**File:** [`frontend/src/lib/store.ts`](frontend/src/lib/store.ts)
**Issue:** JWT tokens stored in localStorage with no expiration handling or refresh mechanism.
**Impact:** When tokens expire (default 480 minutes), user is abruptly logged out.
**Fix:** Implement token refresh logic or add refresh tokens.

### 16. [LOW] Access Packages Page Exists But No Backend Support
**File:** [`frontend/src/app/dashboard/access-packages/page.tsx`](frontend/src/app/dashboard/access-packages/page.tsx)
**Issue:** UI page exists but references no corresponding backend endpoints or API functions.
**Impact:** Page will show errors or empty data.
**Fix:** Either implement backend support or remove/hide the page.

---

## Security Considerations

| Issue | Severity | Description |
|-------|----------|-------------|
| Default SECRET_KEY | High | Default is `zco-edm-secret-key-change-in-production` - must be changed in production |
| CORS allow_origins=["*"] | Medium | In `backend/main.py:58` (legacy file) |
| JWT in localStorage | Medium | Vulnerable to XSS; consider httpOnly cookies |
| No rate limiting | Medium | Login endpoint has no rate limiting |
| Password truncation at 72 bytes | Low | bcrypt limitation, documented and handled |

---

## Improvements & Suggestions

### 17. Add Health Check to All Services
- Frontend has no health endpoint
- Consider adding `/api/health/frontend` for monitoring

### 18. Database Connection Pooling
- Current setup uses basic SQLAlchemy engine
- Consider `QueuePool` with proper size settings for production

### 19. Structured Logging
- No logging configuration exists
- Add Python `logging` with JSON format for container log parsing

### 20. API Documentation Enhancement
- FastAPI `/docs` is exposed publicly
- Consider authentication for Swagger UI in production

### 21. Frontend Error Boundaries
- No React error boundaries configured
- Add error boundaries for graceful error handling

---

## Summary

| Category | Count |
|----------|-------|
| Critical Bugs | 4 |
| High Priority | 1 |
| Medium Priority | 5 |
| Low Priority | 6 |
| Security | 4 |
| Improvements | 5 |
| **Total** | **25** |

---

## Recommended Priority Order

1. **Fix Critical Bugs** (#1-#5) - These will cause runtime failures
2. **Address Security** - Change SECRET_KEY, consider token storage
3. **Medium Issues** (#6-#10) - Type mismatches, dead code
4. **Code Quality** (#11-#16) - Database constraints, unused code
5. **Improvements** (#17-#21) - Logging, monitoring, documentation
