# CRM Manual — JH Skills Development and Consultancy (Pty) Ltd

This repository contains the actionable CRM implementation artefacts based on the provided CRM System Development Manual.

This CRM_MANUAL.md is a concise, developer-friendly version of the full manual with links to implementation artefacts in this repo.

Contents
- Purpose & objectives
- Roles & permissions
- Core modules
- Workflows
- Database design
- Technical stack & recommendation
- Development plan & milestones

Purpose & Objectives
The goal is to implement a centralized CRM supporting training project management, learner administration, client management, SETA/QCTO compliance, finance, communication, and reporting.

Recommended stack (per manual)
- Backend: VB.NET (ASP.NET) on .NET (per developer execution plan) with SQL Server
- Frontend: React (or server-side Razor views in ASP.NET for faster VB integration)
- DB: SQL Server (matches VB.NET and corporate Windows hosting)

User roles (short)
- SuperAdmin, ProjectManager, TrainingCoordinator, Facilitator, FinanceOfficer, ClientUser, LearnerUser

Core modules (short)
- Clients, Learners, Projects, Training Delivery, Assessment & Moderation, Compliance, Finance, Communication, Reporting

Workflows (short)
- Learner enrollment, Training delivery, Assessment lifecycle, Project lifecycle (lead → proposal → contract → implementation → reporting)

Database & Artifacts
- SQL Server CREATE scripts: database/sql_server_schema.sql
- ER diagram (Mermaid): docs/erd.mmd
- OpenAPI skeleton: openapi/OPENAPI.yaml

Development plan (high level)
Phase 1 — Foundation (6–8 weeks)
- Authentication & RBAC, Dashboard, Clients, Learners, Projects
Phase 2 — Training & Assessment (6–8 weeks)
Phase 3 — Assessment & Compliance (4–6 weeks)
Phase 4 — Finance & Automation (4–6 weeks)
Phase 5 — Mobile and AI (future)

Repository layout (this branch)
- CRM_MANUAL.md
- database/sql_server_schema.sql
- docs/erd.mmd
- openapi/OPENAPI.yaml
- .github/

How to use these artefacts
1. Review database/sql_server_schema.sql and run it against a fresh SQL Server instance (adjust file paths, filestream settings, and usernames as required).
2. Use the ER diagram to confirm table relationships.
3. Use OPENAPI.yaml to generate server stubs or client SDKs.
4. After DB is provisioned, scaffold the VB.NET solution and implement the Data Access Layer using the schema.

Next steps I will take if you want me to continue
- Scaffold an ASP.NET VB.NET solution with Entity Framework models and initial controllers for authentication, clients, learners and projects.
- Create seed data and sample database migrations.

