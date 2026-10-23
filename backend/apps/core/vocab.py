"""
Controlled vocabularies from the SRS. Seed data and every API must use these
exact values, so filters, dashboards and status badges stay consistent.
"""

# SRS 4.5 - in workflow order; the last four are terminal or decision states.
APPLICATION_STATUSES = (
    "Planned", "Shortlisted", "Documents Pending", "Submitted", "Under Review",
    "Offer Received", "Rejected", "Withdrawn", "Completed",
)

# SRS 4.6
DOCUMENT_TYPES = (
    "Transcript", "Degree Certificate", "Passport", "SOP", "LOR", "Resume/CV", "Test Score", "Other",
)
DOCUMENT_STATUSES = ("Required", "Uploaded", "Under Review", "Verified", "Rejected", "Expired")

# SRS 4.7
SESSION_STATUSES = ("Scheduled", "Completed", "Cancelled")
SESSION_MODES = ("In person", "Video call", "Phone")
FOLLOW_UP_STATUSES = ("Pending", "Done")

# SRS 4.8
RECOMMENDATION_STATUSES = ("Suggested", "Accepted", "Rejected")
RECOMMENDATION_TIERS = ("Reach", "Target", "Safe")

# SRS 4.10 ("writing": SOP drafts shared, comments, AI-consent requests, referee letters)
NOTIFICATION_CATEGORIES = ("status_change", "missing_document", "deadline", "follow_up", "assignment", "writing")

# SOP / LOR writing (apps/writing): a statement is an SOP draft, a referee brief or a referee's starting draft
STATEMENT_KINDS = ("sop", "lor_brief", "lor_draft")
STATEMENT_STATUSES = ("Draft", "Shared", "Final")
# A referee's stored status; "Received" and "Verified" are read from the linked LOR document
REFERENCE_STATUSES = ("Planned", "Requested", "Cancelled")
REFERENCE_STAGES = ("Planned", "Requested", "Received", "Verified", "Cancelled")

# SRS 4.8 - outcome of the hard eligibility rules for one course (apps/recommendations/engine.py)
RECOMMENDATION_ELIGIBILITY = ("eligible", "insufficient_data", "ineligible")
RECOMMENDATION_ORIGINS = ("engine", "counsellor")

# SRS 4.4 - course master data (same levels a student can target in their preferences)
COURSE_LEVELS = ("Diploma", "Bachelors", "Masters", "MBA", "PhD", "Certificate")
ENGLISH_TESTS = ("IELTS", "TOEFL", "PTE", "Duolingo", "Cambridge")
