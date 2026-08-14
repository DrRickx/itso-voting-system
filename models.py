from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_type = db.Column(db.String(20))   # 'admin' or 'student'
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_number = db.Column(db.String(32), unique=True, nullable=False)
    year_level = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(32), nullable=False)
    major = db.Column(db.String(64), nullable=False)
    first_name = db.Column(db.String(64), nullable=False)
    last_name = db.Column(db.String(64), nullable=False)
    has_voted = db.Column(db.Boolean, default=False)
    votes = db.relationship("Vote", backref="student", lazy=True)

class Partylist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    candidates = db.relationship("Candidate", backref="partylist", lazy=True)

class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    max_selection = db.Column(db.Integer, default=1)
    eligible_year = db.Column(db.Integer, nullable=True)
    category = db.Column(db.String(64), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    candidates = db.relationship("Candidate", backref="position", lazy=True)

class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(64), nullable=False)
    last_name = db.Column(db.String(64), nullable=False)
    tagline = db.Column(db.String(255), nullable=True)
    image = db.Column(db.String(255), nullable=True)
    position_id = db.Column(db.Integer, db.ForeignKey("position.id"), nullable=False)
    partylist_id = db.Column(db.Integer, db.ForeignKey("partylist.id"), nullable=True)
    votes = db.relationship("Vote", backref="candidate", lazy=True)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
