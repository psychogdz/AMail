#!/usr/bin/env bash
# ==============================================================================
# AMail — Production System Health Check Script
# Verifies Django, Gunicorn, Nginx, Postfix, SQLite, and Mail Ingestion.
# ==============================================================================

set -uo pipefail

APP_DIR="/var/www/amail"
APP_USER="amail"
DOMAIN="${EMAIL_DOMAIN:-viomet.online}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

pass() { echo -e "  [${GREEN}PASS${NC}] $1"; }
warn() { echo -e "  [${YELLOW}WARN${NC}] $1"; ((WARNINGS++)); }
fail() { echo -e "  [${RED}FAIL${NC}] $1"; ((ERRORS++)); }

echo -e "\n${BLUE}==============================================================${NC}"
echo -e "${BLUE}  AMail Production System Health Check${NC}"
echo -e "${BLUE}==============================================================${NC}\n"

# 1. System Services Status
echo -e "${BLUE}1. Checking Core Services Status...${NC}"
for svc in amail nginx postfix; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        pass "Service '${svc}' is running (active)."
    else
        fail "Service '${svc}' is NOT running."
    fi
done

# Check systemd cleanup timer
if systemctl is-active --quiet amail-cleanup.timer 2>/dev/null; then
    pass "Systemd timer 'amail-cleanup.timer' is active."
else
    warn "Systemd timer 'amail-cleanup.timer' is not active."
fi

# 2. Port Checks
echo -e "\n${BLUE}2. Checking Network Ports...${NC}"
if ss -tuln 2>/dev/null | grep -q ':25 ' || netstat -tuln 2>/dev/null | grep -q ':25 '; then
    pass "Port 25 (SMTP) is listening."
else
    fail "Port 25 (SMTP) is NOT listening. Postfix cannot receive inbound email."
fi

if ss -tuln 2>/dev/null | grep -q ':80 ' || netstat -tuln 2>/dev/null | grep -q ':80 '; then
    pass "Port 80 (HTTP) is listening."
else
    warn "Port 80 (HTTP) is not listening."
fi

# 3. Nginx Configuration Check
echo -e "\n${BLUE}3. Validating Nginx Configuration...${NC}"
if nginx -t 2>/dev/null; then
    pass "Nginx configuration syntax is valid."
else
    fail "Nginx configuration syntax check failed."
fi

# 4. Postfix Configuration & Maps Check
echo -e "\n${BLUE}4. Validating Postfix Configuration & Lookup Maps...${NC}"
if postfix check 2>/dev/null; then
    pass "Postfix configuration check (postfix check) passed."
else
    fail "Postfix configuration check reported errors."
fi

if [[ -f "/etc/postfix/virtual_mailboxes.db" || -f "/etc/postfix/virtual_mailboxes" ]]; then
    pass "Postfix virtual mailboxes map file exists (/etc/postfix/virtual_mailboxes)."
else
    fail "Postfix virtual mailboxes map file (/etc/postfix/virtual_mailboxes) is missing."
fi

if grep -q "amail_pipe" /etc/postfix/master.cf 2>/dev/null; then
    pass "Postfix master.cf contains 'amail_pipe' service."
else
    fail "Postfix master.cf is missing 'amail_pipe' service."
fi

# 5. Database & Schema Check
echo -e "\n${BLUE}5. Checking SQLite Database & Schema...${NC}"
DB_PATH="${APP_DIR}/db.sqlite3"
if [[ -f "${DB_PATH}" ]]; then
    pass "Database file exists at '${DB_PATH}'."
    
    # Check SQLite readability and tables
    TABLE_COUNT=$(sqlite3 "${DB_PATH}" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name LIKE 'mailboxes_%';" 2>/dev/null || echo "0")
    if [[ "$TABLE_COUNT" -ge 2 ]]; then
        pass "AMail database tables exist (found ${TABLE_COUNT} mailboxes tables)."
    else
        fail "Required AMail database tables are missing or database is inaccessible."
    fi
    
    # Check WAL mode
    JOURNAL_MODE=$(sqlite3 "${DB_PATH}" "PRAGMA journal_mode;" 2>/dev/null || echo "unknown")
    if [[ "${JOURNAL_MODE,,}" == "wal" ]]; then
        pass "SQLite journal mode is WAL."
    else
        warn "SQLite journal mode is '${JOURNAL_MODE}' (WAL mode recommended)."
    fi
else
    fail "Database file '${DB_PATH}' does not exist."
fi

# 6. Mail Ingestion Script Check
echo -e "\n${BLUE}6. Checking Ingestion Pipeline...${NC}"
INGEST_SCRIPT="${APP_DIR}/scripts/ingest_mail.py"
if [[ -f "${INGEST_SCRIPT}" ]]; then
    if [[ -x "${INGEST_SCRIPT}" || -f "${INGEST_SCRIPT}" ]]; then
        pass "Mail ingestion script exists at '${INGEST_SCRIPT}'."
    fi
else
    fail "Mail ingestion script missing at '${INGEST_SCRIPT}'."
fi

PYTHON_BIN="${APP_DIR}/venv/bin/python"
if [[ -x "${PYTHON_BIN}" ]]; then
    pass "Virtualenv Python binary executable at '${PYTHON_BIN}'."
else
    fail "Virtualenv Python binary missing at '${PYTHON_BIN}'."
fi

# 7. Django Deployment Check
echo -e "\n${BLUE}7. Running Django System Checks...${NC}"
if [[ -x "${PYTHON_BIN}" && -f "${APP_DIR}/manage.py" ]]; then
    cd "${APP_DIR}"
    if sudo -u "${APP_USER}" "${PYTHON_BIN}" manage.py check --deploy 2>&1 | grep -q "System check identified no issues"; then
        pass "Django deployment check (check --deploy) passed with 0 issues."
    else
        DEPLOY_CHECK_OUT=$(sudo -u "${APP_USER}" "${PYTHON_BIN}" manage.py check 2>&1 || true)
        if echo "${DEPLOY_CHECK_OUT}" | grep -q "System check identified no issues"; then
            pass "Django system check passed."
        else
            warn "Django check output: ${DEPLOY_CHECK_OUT}"
        fi
    fi
else
    fail "Cannot execute Django manage.py checks."
fi

# 8. Web App HTTP Response Check
echo -e "\n${BLUE}8. Checking HTTP Local Endpoint Response...${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: amail.${DOMAIN}" http://127.0.0.1/accounts/login/ 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "301" || "$HTTP_CODE" == "302" ]]; then
    pass "Web application responds locally (HTTP ${HTTP_CODE})."
else
    warn "Web application returned HTTP status ${HTTP_CODE} on local check."
fi

# Summary
echo -e "\n${BLUE}==============================================================${NC}"
if [[ $ERRORS -eq 0 ]]; then
    echo -e "${GREEN}  ALL HEALTH CHECKS PASSED! (0 errors, ${WARNINGS} warnings)${NC}"
    echo -e "${BLUE}==============================================================${NC}\n"
    exit 0
else
    echo -e "${RED}  HEALTH CHECK FAILED WITH ${ERRORS} ERROR(S) (${WARNINGS} warnings).${NC}"
    echo -e "${BLUE}==============================================================${NC}\n"
    exit 1
fi
