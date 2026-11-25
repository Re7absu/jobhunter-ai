from enum import StrEnum


class ApplicationStatus(StrEnum):
    DISCOVERED = "Discovered"
    ANALYZED = "Analyzed"
    AWAITING_APPROVAL = "Awaiting Approval"
    APPROVED = "Approved"
    READY_TO_APPLY = "Ready to Apply"
    APPLIED = "Applied"
    FOLLOW_UP_REQUIRED = "Follow-up Required"
    RESPONSE_RECEIVED = "Response Received"
    INTERVIEW_SCHEDULED = "Interview Scheduled"
    REJECTED = "Rejected"
    CLOSED = "Closed"


# Statuses meaning "the application has actually been submitted"
SUBMITTED_STATUSES = {
    ApplicationStatus.APPLIED,
    ApplicationStatus.FOLLOW_UP_REQUIRED,
    ApplicationStatus.RESPONSE_RECEIVED,
    ApplicationStatus.INTERVIEW_SCHEDULED,
    ApplicationStatus.REJECTED,
}
PENDING_STATUSES = {
    ApplicationStatus.AWAITING_APPROVAL,
    ApplicationStatus.APPROVED,
    ApplicationStatus.READY_TO_APPLY,
}


class ApplicationMethod(StrEnum):
    EMAIL = "email"
    ONLINE = "online"


class EmailStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    FAILED = "failed"


class FollowUpStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DISMISSED = "dismissed"


class JobCategory(StrEnum):
    TECHNOLOGY = "technology"
    PRODUCT_MANAGEMENT = "product_management"


class MatchCategory(StrEnum):
    EXCELLENT = "Excellent Match"
    GOOD = "Good Match"
    POTENTIAL = "Potential Match"
    LOW = "Low Match"


def match_category(score: int) -> MatchCategory:
    if score >= 80:
        return MatchCategory.EXCELLENT
    if score >= 65:
        return MatchCategory.GOOD
    if score >= 50:
        return MatchCategory.POTENTIAL
    return MatchCategory.LOW


EXPERIENCE_LEVELS = ["internship", "coop", "graduate", "entry", "junior", "mid", "senior"]
