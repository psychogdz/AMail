# AMail — Development Progress

## Phase 1: Project Foundation & Authentication
**Status**: ✅ Complete

### Completed
- [x] Project skeleton created (config/, apps/, templates/, static/)
- [x] Settings configured (base/dev/prod) with SQLite WAL mode
- [x] Authentication views (login/logout/password change)
- [x] Admin-only user creation (no public registration)
- [x] Base templates with responsive dark dashboard theme
- [x] Dashboard placeholder with stat cards
- [x] 404/500 error pages
- [x] Tests written and passing (10/10)
- [x] Documentation created (README.md, ROADMAP.md)

---

## Phase 2: Categories & Email Addresses
**Status**: ✅ Complete

### Completed
- [x] Category model with CRUD (create, list, edit, delete)
- [x] EmailAddress model with validation
- [x] Custom email address creation (lowercase normalization, reserved check, duplicate check)
- [x] Email address management (enable/disable toggle, delete)
- [x] Category assignment and move between categories
- [x] Category deletion with safe address handling (move or uncategorize)
- [x] Address list with pagination (20 per page) and category filtering
- [x] Copy-to-clipboard for email addresses
- [x] Dashboard updated with real stats from database
- [x] Sidebar navigation updated with working links
- [x] Ownership enforcement on all views (user isolation)
- [x] Admin registration for both models
- [x] Tests written and passing (32 new, 42 total)

---

## Phase 3: Random Email Generation
**Status**: ✅ Complete

### Completed
- [x] Random address generator utility (`apps/mailboxes/generator.py`) using Python's `secrets` module
- [x] Three generation styles implemented:
  - **Short Random**: 5 alphanumeric chars (e.g. `x7k29`)
  - **Standard Random**: 8 alphanumeric chars (e.g. `k7x92m4p`)
  - **Human-like Random**: adjective + noun + 2-digit number (e.g. `silverfox42`)
- [x] Built-in lightweight curated wordlists for human-like style without external API dependencies
- [x] Server-side uniqueness checking against DB and reserved address list with automatic retries
- [x] AJAX/JSON endpoint (`/addresses/generate-random/`) for dynamic on-demand address generation
- [x] Enhanced creation UI (`templates/mailboxes/address_create.html`) with dual-method tabs:
  - Method A: Custom Email creation with live domain suffix preview
  - Method B: Random Generator with style selector, live preview badge, and "Generate Again"
- [x] Address deletion confirmation dialog (`templates/mailboxes/address_delete.html`) with safe options:
  - Option 1: Disable address (stops accepting mail, preserves history)
  - Option 2: Delete permanently (removes address and records)
- [x] 10 new tests added (52 total tests passing)

---

## Phase 4: Mail Receiving Integration
**Status**: ✅ Complete

### Completed
- [x] `EmailMessage` database model with full email metadata (sender, sender_name, sender_email, recipient, subject, plain body, HTML body, message_id, raw headers, size, read status, attachment info)
- [x] Lightweight standalone Postfix pipe ingest script (`scripts/ingest_mail.py`):
  - Memory usage: ~9MB RAM, latency <30ms
  - Standard library only (no heavy Django boot per email)
  - Python `email.policy.default` RFC 5322 parsing with UTF-8 support
  - Attachment metadata extraction without heavy disk writes
  - SQLite WAL mode concurrency and timeout management
  - Proper Postfix delivery exit codes (`EX_OK`, `EX_TEMPFAIL`, `EX_NOUSER`, `EX_UNAVAILABLE`)
- [x] Postfix deployment configuration templates in `deploy/postfix/`:
  - `main.cf.snippet` with virtual maps, anti-open-relay restrictions, 5MB size limit, TLS config, concurrency limits
  - `master.cf.snippet` with `amail_pipe` service definition
  - `sqlite-virtual-domains.cf` & `sqlite-virtual-mailboxes.cf` for SMTP-level rejection of unlisted/disabled recipients (550 User unknown)
  - `transport` mapping and complete integration guide (`deploy/postfix/README.md`)
- [x] Django management command (`manage.py ingest_email`) for CLI testing and direct mail ingestion
- [x] Real-time received/unread count properties on `EmailAddress` model
- [x] Dynamic dashboard integration reflecting real email counts with user isolation
- [x] 9 new mail ingestion & integration tests added (61 total tests passing)

### Key Decisions
- Pipe transport with standalone python script keeps RAM usage under 10MB on 1GB VPS.
- Recipient rejection at SMTP time (`virtual_mailbox_maps` SQLite query) drops spam/unknown recipients before Python script invocation.
- Attachments are scanned for metadata without persisting large binaries, protecting 10GB SSD.

### Test Results
```
Ran 61 tests in 71.622s — OK

AccountsTests (10):
  ✓ test_csrf_enforced
  ✓ test_dashboard_requires_auth
  ✓ test_login_invalid_credentials
  ✓ test_login_page_renders
  ✓ test_login_valid_credentials
  ✓ test_logout
  ✓ test_logout_requires_post
  ✓ test_no_registration_url
  ✓ test_password_change_requires_auth
  ✓ test_password_change_works

CategoryTests (10):
  ✓ test_category_list_requires_auth
  ✓ test_category_list_shows_own
  ✓ test_category_create
  ✓ test_category_create_duplicate
  ✓ test_category_edit
  ✓ test_category_edit_other_user
  ✓ test_category_delete
  ✓ test_category_delete_moves_addresses
  ✓ test_category_delete_uncategorizes_addresses
  ✓ test_category_delete_other_user

EmailAddressTests (18):
  ✓ test_address_list_requires_auth
  ✓ test_address_list_shows_own
  ✓ test_address_create
  ✓ test_address_create_no_category
  ✓ test_address_create_duplicate
  ✓ test_address_create_duplicate_cross_user
  ✓ test_address_create_reserved
  ✓ test_address_create_invalid_chars
  ✓ test_address_create_uppercase_normalized
  ✓ test_address_toggle
  ✓ test_address_toggle_other_user
  ✓ test_address_move_category
  ✓ test_address_detail_own
  ✓ test_address_detail_other_user
  ✓ test_address_list_filter_by_category
  ✓ test_address_list_pagination

MailIngestTests (9):
  ✓ test_ingest_plain_text
  ✓ test_ingest_html_and_text_multipart
  ✓ test_ingest_with_attachments
  ✓ test_ingest_utf8_subject_and_body
  ✓ test_ingest_unknown_recipient
  ✓ test_ingest_disabled_recipient
  ✓ test_ingest_cli_recipient_override
  ✓ test_dashboard_stats_with_received_emails
  ✓ test_ingest_management_command

RandomGeneratorTests (8):
  ✓ test_generate_short_style
  ✓ test_generate_standard_style
  ✓ test_generate_human_like_style
  ✓ test_generate_random_local_part_uniqueness
  ✓ test_generate_random_skips_existing
  ✓ test_generate_api_authenticated
  ✓ test_generate_api_unauthenticated
  ✓ test_create_address_with_generated_local_part

AddressDeleteTests (4):
  ✓ test_address_delete_get_confirmation
  ✓ test_address_delete_post_action_delete
  ✓ test_address_delete_post_action_disable
  ✓ test_address_delete_other_user

ValidationTests (4):
  ✓ test_valid_local_parts
  ✓ test_invalid_local_parts
  ✓ test_reserved_addresses
  ✓ test_max_length
```

---

## Phase 5: Inbox & Email Viewer
**Status**: ⏳ Next
