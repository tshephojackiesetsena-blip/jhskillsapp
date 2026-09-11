# JH Skills CRM — Repository

This repository contains starter artifacts for the JH Skills Development CRM described in the project manual.

What's included in this commit:

- CRM_MANUAL.md — concise, actionable version of the CRM manual and implementation notes.
- database/sql_server_schema.sql — CREATE TABLE scripts for SQL Server (VB.NET execution plan).
- docs/erd.mmd — Mermaid-format ER diagram describing core tables and relations.
- openapi/OPENAPI.yaml — Basic OpenAPI (3.0.0) spec skeleton for core endpoints.
- .github/ISSUE_TEMPLATE/bug_report.md — bug report template.
- CONTRIBUTING.md — contribution guidelines and branch/PR rules.

Next steps:
- Review the SQL schema and adjust data types/lengths for local needs.
- Run the SQL script against a fresh database to provision schema.
- Expand OpenAPI with authentication and all models.
- Start scaffolding server-side code (VB.NET / ASP.NET) using the schema and API spec.

If you want, I can now scaffold an ASP.NET VB.NET solution and initial controllers, or generate the full, unabridged manual file in the repo.
