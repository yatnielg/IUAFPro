# Copilot Instructions for campusiuaf

## Project Overview
This is a Django-based web application for managing student records and campus operations. The codebase includes custom management commands, templates for various user flows, and static assets for frontend presentation.

## Architecture & Key Components
- **Django App Structure:**
  - `alumnos/`: Main app for student management. Contains models, views, admin, migrations, and custom management commands.
  - `campusiuaf/`: Project settings, URLs, and WSGI/ASGI entry points.
  - `templates/`: Organized by feature (account, alumnos, panel, base) for HTML rendering.
  - `static/` and `staticfiles/`: Static assets (JS, CSS, images) for both admin and user-facing interfaces.
- **Database:** Uses SQLite (`db.sqlite3`) for local development.
- **Excel Integration:** Several `.xlsm` files suggest import/export workflows with Excel for bulk data operations.

## Developer Workflows
- **Run Server:**
  - `python manage.py runserver`
- **Custom Management Commands:**
  - Located in `alumnos/management/commands/` (e.g., `import_alumnos.py`, `cargar_programas.py`).
  - Run via: `python manage.py <command_name>`
- **Migrations:**
  - Standard Django migrations in `alumnos/migrations/`.
  - Apply with: `python manage.py migrate`
- **Testing:**
  - Tests in `alumnos/tests.py`. Run with: `python manage.py test alumnos`

## Project-Specific Patterns & Conventions
- **Template Organization:**
  - Templates are grouped by feature, not just app. E.g., `panel/`, `account/`, `alumnos/`.
- **Static Files:**
  - Custom static assets are under both `static/` and `staticfiles/`. Admin assets are separated from user assets.
- **Excel Workflows:**
  - Likely use of management commands for importing/exporting student data from `.xlsm` files. Check command scripts for details.
- **User Management:**
  - Custom user creation and authentication flows in `templates/account/` and `templates/alumnos/crear_usuario.html`.

## Integration Points
- **Excel:** Bulk data import/export via management commands and `.xlsm` files.
- **Custom Commands:** Extend Django admin functionality for campus-specific workflows.

## Examples
- To import students: `python manage.py import_alumnos`
- To load programs: `python manage.py cargar_programas`

## Key Files & Directories
- `alumnos/models.py`: Student data model definitions
- `alumnos/management/commands/`: Custom admin/automation scripts
- `templates/`: All HTML templates for rendering views
- `static/`: JS, CSS, and image assets
- `campusiuaf/settings.py`: Project configuration

## Recommendations for AI Agents
- Always check for custom management commands before scripting data operations.
- Respect template and static file organization when adding new features.
- Use Django conventions unless a project-specific pattern is evident.
- Reference existing templates and static assets for UI consistency.

---
_If any section is unclear or missing important project-specific details, please provide feedback to improve these instructions._
