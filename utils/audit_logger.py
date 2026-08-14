from models import AuditLog, db
from datetime import datetime

def log_action(user_type, user_id, action):
    log = AuditLog(user_type=user_type, user_id=user_id, action=action, timestamp=datetime.utcnow())
    db.session.add(log)
    db.session.commit()
