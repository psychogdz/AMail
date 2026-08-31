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

### Key Decisions
- EmailAddress uses `local_part` + `domain` with unique_together constraint
- Domain defaults to settings.EMAIL_DOMAIN (viomet.online)
- CategoryForm validates unique_together (user + name) in clean_name
- Address validation: ^[a-z0-9][a-z0-9._-]*[a-z0-9]$ (or single alphanumeric)
- 16 reserved addresses blocked (postmaster, abuse, admin, etc.)
- Cross-user duplicate addresses rejected (same local_part+domain)

### Test Results
```
Ran 42 tests in 49.159s — OK

CategoryTests (10):
  ✓ category_list_requires_auth
  ✓ category_list_shows_own
  ✓ category_create
  ✓ category_create_duplicate
  ✓ category_edit
  ✓ category_edit_other_user → 404
  ✓ category_delete
  ✓ category_delete_moves_addresses
  ✓ category_delete_uncategorizes_addresses
  ✓ category_delete_other_user → 404

EmailAddressTests (18):
  ✓ address_list_requires_auth
  ✓ address_list_shows_own
  ✓ address_create
  ✓ address_create_no_category
  ✓ address_create_duplicate
  ✓ address_create_duplicate_cross_user
  ✓ address_create_reserved
  ✓ address_create_invalid_chars
  ✓ address_create_uppercase_normalized
  ✓ address_toggle
  ✓ address_toggle_other_user → 404
  ✓ address_delete
  ✓ address_delete_other_user → 404
  ✓ address_move_category
  ✓ address_detail_own
  ✓ address_detail_other_user → 404
  ✓ address_list_filter_by_category
  ✓ address_list_pagination

ValidationTests (4):
  ✓ valid_local_parts
  ✓ invalid_local_parts
  ✓ reserved_addresses
  ✓ max_length
```

---

## Phase 3: Random Email Generation
**Status**: ⏳ Next
