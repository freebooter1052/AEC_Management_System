# Abroad Education Counselling and Student Application Management System

[![Version](https://img.shields.io/badge/Version-1.0-blue.svg)](#)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.x-092E20.svg)](https://www.djangoproject.com/)
[![Django REST Framework](https://img.shields.io/badge/DRF-3.x-red.svg)](https://www.django-rest-framework.org/)
[![Database](https://img.shields.io/badge/Database-Apache%20CouchDB-e42528.svg)](https://couchdb.apache.org/)

---

## 📌 Project Overview

The **Abroad Education Counselling and Student Application Management System** is a centralized web platform designed for overseas education counselling agencies. It streamlines and replaces traditional fragmented spreadsheets, physical paperwork, and disconnected records with a document-oriented NoSQL database.

The system supports the entire **counselling-to-application workflow**, allowing students to manage their profiles and track applications, counsellors to mentor students and verify documents, and administrators to oversee master data, staff workload, and system operations.

### 👥 Project Contributors
- **Christin Jose Biju** (26MAI0055)
- **Ridhin Jayan** (26MAI0059)
- **Lakshay S** (26MAI0064)

---

## 🏗️ Architecture & Technology Stack

| Layer | Technology / Component | Key Responsibilities |
| :--- | :--- | :--- |
| **Presentation Layer** | HTML5, CSS3, JavaScript, Bootstrap / React JS | Responsive web interface, forms, and role-specific dashboards |
| **API & Backend Layer**| Python, Django, Django REST Framework (DRF) | Business logic, authentication/authorization (RBAC), validation, RESTful endpoints |
| **Database Layer** | Apache CouchDB (Document-Oriented NoSQL) | JSON document storage, revisions, views, and attachments |
| **Version Control** | Git & GitHub | Source code management and team collaboration |

---

## 👥 User Roles & Access Control

The system implements strict **Role-Based Access Control (RBAC)** across three primary user classes:

```
                  ┌──────────────────────┐
                  │    Authentication    │
                  │   & Role Management  │
                  └──────────┬───────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
  ┌─────────────┐     ┌──────────────┐    ┌───────────────┐
  │   Student   │     │  Counsellor  │    │ Administrator │
  └──────┬──────┘     └──────┬───────┘    └───────┬───────┘
         │                   │                    │
         ├─ Personal Profile ├─ Assigned Students ├─ User Management
         ├─ Search Unis      ├─ Counselling Logs  ├─ Uni & Course Master
         ├─ Applications     ├─ Review & Verify   ├─ Workload Overview
         └─ Track Documents  └─ Recommendations   └─ System Analytics
```

1. **Student**:
   - Maintain personal, academic, and preference profiles.
   - Search universities and programs.
   - Submit and track applications and upload required documents (SOP, LOR, transcripts).
   - View counsellor recommendations, notes, and notifications.

2. **Counsellor**:
   - Manage assigned students and track individual student pipelines.
   - Schedule sessions, record discussion notes, and set follow-up tasks.
   - Review and verify student documents.
   - Provide rule-based course/university recommendations.

3. **Administrator**:
   - Manage user accounts, role delegations, and counsellor student assignments.
   - Manage master data: Universities, courses, countries, and intake deadlines.
   - Access global analytics, reports, and system audit logs.

---

## 🌟 Core System Modules & Features

- **🔐 Authentication & Role Management**: Secure token/session-based authentication with strict role authorization at API level.
- **🎓 Student Management**: Profiles, academic background (GPA, degree, graduation year), preferred intake/countries, and budget range.
- **🤝 Counsellor Management**: Counsellor profiles, student allocations, workload overview, and session scheduling.
- **🏫 University & Course Management**: Database of universities, courses, eligibility criteria, tuition fees, and intake seasons.
- **📝 Application Management**: Application lifecycle tracking across statuses:
  `Planned` ➔ `Shortlisted` ➔ `Documents Pending` ➔ `Submitted` ➔ `Under Review` ➔ `Offer Received` / `Rejected` / `Withdrawn` / `Completed`
- **📁 Document Management**: Manage metadata and file uploads for Transcripts, Degree Certificates, Passports, SOPs, LORs, and Test Scores with status flags (`Required`, `Uploaded`, `Under Review`, `Verified`, `Rejected`, `Expired`).
- **💡 Recommendation & Matching Engine**: Rule-based matching that scores university programs against student budget, target country, academic GPA, and preferred intake.
- **📊 Dashboards & Reporting**: Tailored analytics views for students, counsellors, and administrators.
- **🔔 Notifications & Reminders**: Real-time alerts for application deadlines, missing documents, and follow-ups.

---

## 🗄️ Apache CouchDB Data Model

Data is stored as JSON documents within Apache CouchDB using the `doc_type` attribute for logical categorization.

```mermaid
erDiagram
    STUDENT ||--o{ APPLICATION : submits
    STUDENT }o--|| COUNSELLOR : "advised by"
    STUDENT ||--o{ DOCUMENT : uploads
    STUDENT ||--o{ COUNSELLING_SESSION : attends
    STUDENT ||--o{ RECOMMENDATION : receives
    COUNSELLOR ||--o{ COUNSELLING_SESSION : conducts
    COUNSELLOR ||--o{ RECOMMENDATION : generates
    UNIVERSITY ||--o{ COURSE : offers
    COURSE ||--o{ APPLICATION : receives
    APPLICATION ||--o{ APPLICATION_HISTORY : tracks
    APPLICATION ||--o{ DOCUMENT : requires
```

### Document Types Summary

| Document Type | Purpose | Key Attributes |
| :--- | :--- | :--- |
| `user` | Account & authentication | `user_id`, `username`, `email`, `role`, `password_hash`, `is_active` |
| `student` | Student master profile | `student_id`, `user_id`, `personal`, `academic`, `preferences`, `counsellor_id` |
| `counsellor` | Counsellor profile | `counsellor_id`, `user_id`, `name`, `specialization`, `assigned_student_ids` |
| `university` | University records | `university_id`, `name`, `country_id`, `location`, `website`, `ranking` |
| `course` | Programs offered | `course_id`, `university_id`, `name`, `level`, `duration`, `tuition`, `eligibility` |
| `application` | University application | `application_id`, `student_id`, `university_id`, `course_id`, `intake_id`, `status`, `deadline` |
| `document` | Document metadata | `document_id`, `student_id`, `application_id`, `document_type`, `filename`, `status` |
| `counselling_session`| Session records | `session_id`, `student_id`, `counsellor_id`, `date_time`, `summary`, `follow_up` |
| `recommendation` | University suggestion | `recommendation_id`, `student_id`, `university_id`, `course_id`, `match_factors` |
| `application_history`| Status audit trail | `history_id`, `application_id`, `old_status`, `new_status`, `changed_by`, `timestamp` |

---

### Example JSON Document Structures

#### 1. Student Document (`doc_type: "student"`)
```json
{
  "_id": "student_001",
  "doc_type": "student",
  "user_id": "user_001",
  "personal": {
    "name": "Alex Mercer",
    "email": "alex.mercer@example.com",
    "phone": "+1234567890"
  },
  "academic": {
    "degree": "B.E. Computer Science",
    "cgpa": 8.5,
    "graduation_year": 2026
  },
  "preferences": {
    "countries": ["Germany", "Canada"],
    "course_area": ["Computer Science", "AI/ML"],
    "intake": "Fall 2027",
    "budget": {
      "amount": 25000,
      "currency": "EUR"
    }
  },
  "counsellor_id": "counsellor_001",
  "created_at": "2026-03-01T10:00:00Z",
  "updated_at": "2026-03-05T14:30:00Z"
}
```

#### 2. Application Document (`doc_type: "application"`)
```json
{
  "_id": "application_001",
  "doc_type": "application",
  "student_id": "student_001",
  "university_id": "university_014",
  "course_id": "course_014_02",
  "intake_id": "intake_fall_2027",
  "status": "Documents Pending",
  "deadline": "2027-01-15",
  "history_ids": ["history_001", "history_002"],
  "created_at": "2026-03-10T09:00:00Z",
  "updated_at": "2026-03-12T11:20:00Z"
}
```

---

## ⚡ Non-Functional & Quality Requirements

- **Performance**: API responses within ~2 seconds; dashboard loads within ~3 seconds under local development conditions. Pagination supported across collections.
- **Reliability & Recovery**: Graceful degradation during CouchDB connectivity interruptions and structured error logging without exposing secrets.
- **Security**: Passwords hashed securely, API-level RBAC validation, input sanitization, and environment-based secret configuration.

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.10+**
- **Apache CouchDB 3.x+** running locally or accessible over network (default: `http://127.0.0.1:5984/`)
- **Git**

### Installation Steps

1. **Clone the Repository**
   ```bash
   git clone https://github.com/freebooter1052/AEC_Management_System.git
   cd AEC_Management_System
   ```

2. **Set Up Python Virtual Environment**
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install django djangorestframework couchdb python-dotenv requests
   ```

4. **Configure Environment Variables**
   Create a `.env` file in the root directory:
   ```env
   DJANGO_SECRET_KEY=your-secret-key-here
   DEBUG=True
   COUCHDB_URL=http://admin:password@127.0.0.1:5984/
   COUCHDB_DATABASE=aec_management_db
   ```

5. **Run Migrations & Initialize CouchDB**
   ```bash
   python manage.py migrate
   ```

6. **Start the Development Server**
   ```bash
   python manage.py runserver
   ```
   Access the application in your browser at `http://127.0.0.1:8000/`.

---

## 📖 References & Documentation
- IEEE Recommended Practice for Software Requirements Specifications (IEEE 830-1998)
- [Django Documentation](https://docs.djangoproject.com/)
- [Django REST Framework Documentation](https://www.django-rest-framework.org/)
- [Apache CouchDB Documentation](https://docs.couchdb.org/)
