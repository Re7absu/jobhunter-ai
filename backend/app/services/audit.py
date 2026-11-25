import logging

from sqlalchemy.orm import Session

from app.models import AuditLog

log = logging.getLogger("audit")


def audit(db: Session, user_id: int | None, action: str, entity_type: str | None = None,
          entity_id: int | None = None, details: dict | None = None, ip: str | None = None,
          commit: bool = False) -> None:
    db.add(AuditLog(user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id,
                    details=details, ip_address=ip))
    log.info("user=%s action=%s %s#%s", user_id, action, entity_type, entity_id)
    if commit:
        db.commit()
