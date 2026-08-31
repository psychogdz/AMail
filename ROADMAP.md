# AMail — Roadmap

## Phase 1: Project Foundation & Authentication ✅
- Django project skeleton
- Settings (base/dev/prod)
- User authentication (login/logout/password change)
- Admin-only user creation
- Base templates and responsive CSS
- Dashboard placeholder

## Phase 2: Categories & Email Addresses ✅
- Category model (CRUD)
- Email address model
- Custom email address creation with validation
- Email address management (enable/disable/delete)
- Category assignment

## Phase 3: Random Email Generation ✅
- Random address generator (short, standard, human-like)
- Preview before save
- Generate Again functionality
- Uniqueness validation

## Phase 4: Mail Receiving Integration ⬅️ Next
- Postfix configuration
- Lightweight ingest script (ingest_mail.py)
- SQLite virtual mailbox maps
- SMTP-level recipient rejection
- Email parsing and storage

## Phase 5: Inbox & Email Viewer
- Inbox interface
- Email list with pagination
- Email content viewer
- HTML email safe rendering
- Read/unread status
- Search functionality
- Bulk actions

## Phase 6: Security & Optimization
- Rate limiting
- Input sanitization hardening
- Resource optimization
- Email cleanup management command
- systemd timer for cleanup
- Storage monitoring

## Phase 7: Deployment & Production Hardening
- Nginx configuration
- Gunicorn systemd service
- SSL/TLS setup
- Postfix TLS
- Production security settings
- Deployment documentation
- Install script
