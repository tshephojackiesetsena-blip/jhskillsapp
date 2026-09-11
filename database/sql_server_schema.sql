-- SQL Server schema for JH Skills CRM (VB.NET execution plan)
-- Run on SQL Server 2016+ (or Azure SQL). Adjust filegroups, file locations and sizes as needed.
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;

IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'crm')
BEGIN
    EXEC('CREATE SCHEMA crm');
END
GO

-- Roles
CREATE TABLE crm.Roles (
    RoleId INT IDENTITY(1,1) PRIMARY KEY,
    Name NVARCHAR(100) NOT NULL UNIQUE,
    Description NVARCHAR(400) NULL,
    CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME(),
    ModifiedAt DATETIME2 NULL
);

-- Users
CREATE TABLE crm.Users (
    UserId INT IDENTITY(1,1) PRIMARY KEY,
    FullName NVARCHAR(250) NOT NULL,
    Email NVARCHAR(320) NOT NULL UNIQUE,
    Phone NVARCHAR(50) NULL,
    PasswordHash NVARCHAR(512) NOT NULL,
    RoleId INT NOT NULL REFERENCES crm.Roles(RoleId),
    IsActive BIT DEFAULT 1,
    CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME(),
    ModifiedAt DATETIME2 NULL
);

CREATE INDEX IX_Users_Email ON crm.Users(Email);

-- Clients
CREATE TABLE crm.Clients (
    ClientId INT IDENTITY(1,1) PRIMARY KEY,
    CompanyName NVARCHAR(250) NOT NULL,
    RegistrationNumber NVARCHAR(100) NULL,
    IndustrySector NVARCHAR(150) NULL,
    Address NVARCHAR(500) NULL,
    ContactPerson NVARCHAR(250) NULL,
    ContactEmail NVARCHAR(320) NULL,
    ContactPhone NVARCHAR(50) NULL,
    SetaAlignment NVARCHAR(200) NULL,
    Notes NVARCHAR(MAX) NULL,
    CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME(),
    ModifiedAt DATETIME2 NULL
);

-- Client Contacts (multiple contacts per client)
CREATE TABLE crm.ClientContacts (
    ContactId INT IDENTITY(1,1) PRIMARY KEY,
    ClientId INT NOT NULL REFERENCES crm.Clients(ClientId) ON DELETE CASCADE,
    FullName NVARCHAR(250) NOT NULL,
    Role NVARCHAR(150) NULL,
    Email NVARCHAR(320) NULL,
    Phone NVARCHAR(50) NULL,
    CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME()
);

-- Projects
CREATE TABLE crm.Projects (
    ProjectId INT IDENTITY(1,1) PRIMARY KEY,
    ProjectName NVARCHAR(250) NOT NULL,
    ClientId INT NOT NULL REFERENCES crm.Clients(ClientId),
    FundingSource NVARCHAR(100) NULL,
    Qualification NVARCHAR(250) NULL,
    StartDate DATE NULL,
    EndDate DATE NULL,
    Budget DECIMAL(18,2) DEFAULT 0,
    Status NVARCHAR(50) DEFAULT 'Draft',
    CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME(),
    ModifiedAt DATETIME2 NULL
);

CREATE INDEX IX_Projects_ClientId ON crm.Projects(ClientId);

-- Learners
CREATE TABLE crm.Learners (
    LearnerId INT IDENTITY(1,1) PRIMARY KEY,
    FullName NVARCHAR(250) NOT NULL,
    IDNumber NVARCHAR(50) NULL,
    Gender NVARCHAR(20) NULL,
    DisabilityStatus NVARCHAR(100) NULL,
    Email NVARCHAR(320) NULL,
    Phone NVARCHAR(50) NULL,
    Address NVARCHAR(500) NULL,
    EmploymentStatus NVARCHAR(100) NULL,
    QualificationEnrolled NVARCHAR(250) NULL,
    ProjectId INT NULL REFERENCES crm.Projects(ProjectId),
    DocumentsStatus NVARCHAR(100) NULL,
    CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME(),
    ModifiedAt DATETIME2 NULL
);

CREATE INDEX IX_Learners_ProjectId ON crm.Learners(ProjectId);

-- Enrollments (historical, a learner may be enrolled in many projects)
CREATE TABLE crm.Enrollments (
    EnrollmentId INT IDENTITY(1,1) PRIMARY KEY,
    LearnerId INT NOT NULL REFERENCES crm.Learners(LearnerId),
    ProjectId INT NOT NULL REFERENCES crm.Projects(ProjectId),
    EnrollmentDate DATETIME2 DEFAULT SYSUTCDATETIME(),
    Status NVARCHAR(50) DEFAULT 'Active'
);

-- Training Sessions
CREATE TABLE crm.TrainingSessions (
    SessionId INT IDENTITY(1,1) PRIMARY KEY,
    ProjectId INT NOT NULL REFERENCES crm.Projects(ProjectId),
    Title NVARCHAR(250) NULL,
    SessionDate DATE NOT NULL,
    Venue NVARCHAR(250) NULL,
    FacilitatorId INT NULL REFERENCES crm.Users(UserId),
    CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME()
);

-- Attendance
CREATE TABLE crm.Attendance (
    AttendanceId INT IDENTITY(1,1) PRIMARY KEY,
    LearnerId INT NOT NULL REFERENCES crm.Learners(LearnerId),
    SessionId INT NOT NULL REFERENCES crm.TrainingSessions(SessionId) ON DELETE CASCADE,
    Status NVARCHAR(50) DEFAULT 'Present',
    FacilitatorId INT NULL REFERENCES crm.Users(UserId),
    RecordedAt DATETIME2 DEFAULT SYSUTCDATETIME()
);

-- Assessments
CREATE TABLE crm.Assessments (
    AssessmentId INT IDENTITY(1,1) PRIMARY KEY,
    LearnerId INT NOT NULL REFERENCES crm.Learners(LearnerId),
    UnitStandard NVARCHAR(250) NULL,
    AssessorId INT NULL REFERENCES crm.Users(UserId),
    Result NVARCHAR(50) NULL,
    AssessmentDate DATE NULL,
    ModerationStatus NVARCHAR(50) DEFAULT 'Not Started',
    CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME()
);

-- Documents (generic repository)
CREATE TABLE crm.Documents (
    DocumentId INT IDENTITY(1,1) PRIMARY KEY,
    OwnerType NVARCHAR(50) NOT NULL, -- 'Learner','Client','Project','Assessment'
    OwnerId INT NOT NULL,
    FileName NVARCHAR(500) NOT NULL,
    ContentType NVARCHAR(200) NULL,
    FilePath NVARCHAR(1000) NULL, -- stored path or blob reference
    UploadedBy INT NULL REFERENCES crm.Users(UserId),
    UploadedAt DATETIME2 DEFAULT SYSUTCDATETIME(),
    IsPublic BIT DEFAULT 0
);

-- Invoices / Finance
CREATE TABLE crm.Invoices (
    InvoiceId INT IDENTITY(1,1) PRIMARY KEY,
    ClientId INT NOT NULL REFERENCES crm.Clients(ClientId),
    ProjectId INT NULL REFERENCES crm.Projects(ProjectId),
    InvoiceNumber NVARCHAR(100) NOT NULL UNIQUE,
    Amount DECIMAL(18,2) NOT NULL,
    VAT DECIMAL(18,2) DEFAULT 0,
    Status NVARCHAR(50) DEFAULT 'Pending',
    IssueDate DATE DEFAULT CAST(SYSUTCDATETIME() AS DATE),
    DueDate DATE NULL,
    PaymentDate DATE NULL,
    CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME()
);

CREATE INDEX IX_Invoices_ClientId ON crm.Invoices(ClientId);

-- Payments
CREATE TABLE crm.Payments (
    PaymentId INT IDENTITY(1,1) PRIMARY KEY,
    InvoiceId INT NOT NULL REFERENCES crm.Invoices(InvoiceId),
    Amount DECIMAL(18,2) NOT NULL,
    PaymentDate DATETIME2 DEFAULT SYSUTCDATETIME(),
    Method NVARCHAR(100) NULL,
    TransactionReference NVARCHAR(250) NULL
);

-- Expenses (project-level)
CREATE TABLE crm.Expenses (
    ExpenseId INT IDENTITY(1,1) PRIMARY KEY,
    ProjectId INT NULL REFERENCES crm.Projects(ProjectId),
    Description NVARCHAR(500) NULL,
    Amount DECIMAL(18,2) NOT NULL,
    IncurredAt DATE NULL,
    CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME()
);

-- Notifications
CREATE TABLE crm.Notifications (
    NotificationId INT IDENTITY(1,1) PRIMARY KEY,
    UserId INT NULL REFERENCES crm.Users(UserId),
    Message NVARCHAR(1000) NOT NULL,
    Channel NVARCHAR(50) DEFAULT 'InApp', -- Email,SMS
    IsRead BIT DEFAULT 0,
    TriggeredAt DATETIME2 DEFAULT SYSUTCDATETIME()
);

-- Audit Log
CREATE TABLE crm.AuditLogs (
    AuditId BIGINT IDENTITY(1,1) PRIMARY KEY,
    Entity NVARCHAR(200) NOT NULL,
    EntityId NVARCHAR(200) NULL,
    Action NVARCHAR(100) NOT NULL,
    PerformedBy INT NULL REFERENCES crm.Users(UserId),
    PerformedAt DATETIME2 DEFAULT SYSUTCDATETIME(),
    Details NVARCHAR(MAX) NULL
);

-- Seed roles and an admin user (password hash placeholder)
INSERT INTO crm.Roles (Name, Description) VALUES
('SuperAdministrator','Full system access'),
('ProjectManager','Manage projects and teams'),
('TrainingCoordinator','Manage learners and training'),
('Facilitator','Deliver training and assessments'),
('FinanceOfficer','Handle invoicing and payments');

INSERT INTO crm.Users (FullName, Email, PasswordHash, RoleId, IsActive)
VALUES ('System Administrator','admin@jhskills.local','REPLACE_WITH_SECURE_HASH', 1, 1);

-- End of schema
GO
