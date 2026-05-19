# Developer Onboarding & Review Document

## Project Overview
This is a modern GST Billing and Inventory Management application built with Flask, SQLAlchemy, Bootstrap 5, and Jinja2. It supports product, customer, invoice, and company management, with reporting, export, and print features. The UI is responsive and designed for Indian business needs (GST, Indian currency, etc).

---

## Key Features
- User authentication (admin)
- Product, Customer, Invoice CRUD
- Company info management (single record)
- Sales, Product, Customer, and Invoice reports (with print/export/search)
- Strict Indian currency formatting and GST handling
- Invoice print layout matches Indian A4 standards
- Seed data for demo/testing (Tamil products, Tirunelveli customers)
- Static file upload for company logo
- Modern Bootstrap 5 UI

---

## Project Structure
- `app.py` — Main Flask app, Jinja filters, blueprint registration
- `models.py` — SQLAlchemy models (Product, Customer, Invoice, Company, etc)
- `init_db.py` — DB initialization/reset
- `seed_data.py` — Demo data seeding
- `auth/`, `products/`, `customers/`, `invoices/`, `reports/`, `company/` — Feature blueprints (routes, views)
- `templates/` — Jinja2 HTML templates (modular, per-feature)
- `static/` — CSS, JS, uploaded files

---

## Setup & Running
1. Clone repo, create virtualenv, install requirements
2. Run `init_db.py` to initialize DB
3. Run `seed_data.py` for demo data
4. Start app: `python app.py` (or via Flask CLI)
5. Login as admin/admin

---

## Customization & Extension
- Add new features as blueprints (see existing structure)
- Use Bootstrap 5 for UI consistency
- Add Jinja filters for formatting
- Use SQLAlchemy for all DB access
- Add/modify seed data in `seed_data.py`

---

## Review & Recommendations (as Manager/Client)
### Strengths
- Clean, modular codebase
- Modern UI, responsive design
- Indian business/GST focus
- Good reporting & export features
- Print-ready invoice layout
- Demo data for easy onboarding

### Suggested Improvements / Next Steps
1. **Modern POS Sales Page** — Product grid with images, cart, quantity buttons, real-time total (see previous suggestion)
2. **Product Images** — Add image upload/display for products
3. **Role-based Access** — Add user roles (admin, staff, etc)
4. **Activity Log/Audit** — Track changes (who did what/when)
5. **API Endpoints** — For mobile app or integration
6. **Unit/Integration Tests** — Add tests for reliability
7. **Bulk Import/Export** — For products/customers via Excel/CSV
8. **Notifications/Reminders** — For low stock, payment due, etc
9. **UI Polish** — More dashboard widgets, charts, dark mode
10. **Performance** — Optimize queries for large datasets

---

## Onboarding Checklist for New Developers
- [ ] Set up Python environment & install dependencies
- [ ] Run DB init & seed scripts
- [ ] Review `app.py`, `models.py`, and one blueprint (e.g. products)
- [ ] Explore templates and static assets
- [ ] Read this document and the README
- [ ] Try adding a new product/customer/invoice
- [ ] Review Jinja filters and Bootstrap usage

---

## Contact & Contribution
- For questions, contact the project maintainer or check the README.
- Follow code style and commit guidelines.
- Open issues/PRs for bugs or features.

---

*This document is auto-generated for onboarding and review. Update as the project evolves.*
