import os
from functools import wraps
from datetime import datetime
from collections import defaultdict

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_file
)
from werkzeug.utils import secure_filename

from config import Config

# Initialize app
app = Flask(__name__)
app.config.from_object(Config)

# import db and models
from models import db, Admin, Student, Partylist, Position, Candidate, Vote, AuditLog
db.init_app(app)

# Migrations
from flask_migrate import Migrate
migrate = Migrate(app, db)

# utils
from utils.audit_logger import log_action
from utils.csv_importer import import_students, import_candidates

# helpers
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]

def ensure_ballot_session():
    if "ballot" not in session:
        session["ballot"] = {}
    if "position_index" not in session:
        session["position_index"] = 0

def get_positions_for_student(student):
    q = Position.query.order_by(Position.sort_order.asc(), Position.id.asc())
    positions = q.all()
    filtered = []
    for p in positions:
        if p.eligible_year is None or p.eligible_year == student.year_level:
            filtered.append(p)
    return filtered

def count_progress(student, positions):
    ensure_ballot_session()
    ballot = session["ballot"]
    filled = 0
    total_pages = len(positions)
    for p in positions:
        if str(p.id) in ballot and len(ballot[str(p.id)]) >= p.max_selection:
            filled += 1
    if total_pages == 0:
        return 0
    return int((filled / total_pages) * 100)

# ----------------------
# Admin auth decorator
# ----------------------
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("admin_login", next=request.url))
        return f(*args, **kwargs)
    return decorated

# ---------- Student Routes ----------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        sn = request.form.get("student_number", "").strip()
        try:
            year_level = int(request.form.get("year_level", 0))
        except:
            year_level = 0
        section = request.form.get("section", "").strip()
        major = request.form.get("major", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        if not (sn and year_level and section and major and first_name and last_name):
            flash("Please complete all fields.", "error")
            return redirect(url_for("index"))

        student = Student.query.filter_by(student_number=sn).first()
        if student and student.has_voted:
            flash("You have already cast your vote. Thank you!", "error")
            return redirect(url_for("index"))

        if not student:
            student = Student(
                student_number=sn,
                year_level=year_level,
                section=section,
                major=major,
                first_name=first_name,
                last_name=last_name
            )
            db.session.add(student)
            db.session.commit()
            log_action('student', student.id, "Registered for voting")

        session["student_id"] = student.id
        session["ballot"] = {}
        session["position_index"] = 0
        return redirect(url_for("ballot"))
    return render_template("index.html")

@app.route("/ballot", methods=["GET", "POST"])
def ballot():
    student_id = session.get("student_id")
    if not student_id:
        return redirect(url_for("index"))
    student = Student.query.get_or_404(student_id)
    positions = get_positions_for_student(student)
    ensure_ballot_session()
    position_index = session["position_index"]

    if not positions:
        return redirect(url_for("verify"))

    position_index = max(0, min(position_index, len(positions)-1))
    position = positions[position_index]
    candidates = Candidate.query.filter_by(position_id=position.id).order_by(Candidate.last_name.asc()).all()

    if request.method == "POST":
        selected_ids = request.form.getlist("candidates")
        if len(selected_ids) != position.max_selection:
            flash(f"You must select exactly {position.max_selection} for {position.name}.", "error")
            return render_template("student/ballot.html", student=student, position=position, candidates=candidates, progress=count_progress(student, positions), position_index=position_index, total_positions=len(positions), selected=set(session["ballot"].get(str(position.id), [])))

        session["ballot"][str(position.id)] = [int(x) for x in selected_ids]
        session.modified = True

        if "prev" in request.form:
            session["position_index"] = max(0, position_index - 1)
            return redirect(url_for("ballot"))
        else:
            session["position_index"] = position_index + 1
            if session["position_index"] >= len(positions):
                return redirect(url_for("verify"))
            return redirect(url_for("ballot"))

    selected_set = set(session["ballot"].get(str(position.id), []))
    return render_template("student/ballot.html", student=student, position=position, candidates=candidates, progress=count_progress(student, positions), position_index=position_index, total_positions=len(positions), selected=selected_set)

@app.route("/verify", methods=["GET", "POST"])
def verify():
    student_id = session.get("student_id")
    if not student_id:
        return redirect(url_for("index"))
    student = Student.query.get_or_404(student_id)
    positions = get_positions_for_student(student)
    ensure_ballot_session()

    ballot_display = []
    for p in positions:
        sel_ids = session["ballot"].get(str(p.id), [])
        sel_candidates = Candidate.query.filter(Candidate.id.in_(sel_ids)).all() if sel_ids else []
        ballot_display.append((p, sel_candidates))

    incomplete = [p.name for p in positions if len(session["ballot"].get(str(p.id), [])) != p.max_selection]
    if incomplete:
        flash("Please complete all positions before verification.", "error")
        for idx, p in enumerate(positions):
            if len(session["ballot"].get(str(p.id), [])) != p.max_selection:
                session["position_index"] = idx
                break
        return redirect(url_for("ballot"))

    if request.method == "POST":
        if student.has_voted:
            flash("You have already voted.", "error")
            return redirect(url_for("index"))
        for p, _ in ballot_display:
            for cid in session["ballot"].get(str(p.id), []):
                db.session.add(Vote(student_id=student.id, candidate_id=int(cid)))
        student.has_voted = True
        db.session.commit()
        log_action('student', student.id, "Submitted ballot")
        session.pop("ballot", None)
        session.pop("position_index", None)
        session.pop("student_id", None)
        flash("Your ballot has been submitted. Thank you!", "success")
        return redirect(url_for("index"))

    return render_template("student/verify.html", student=student, ballot_display=ballot_display)

# ---------- Admin Auth ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            session["admin_id"] = admin.id
            log_action('admin', admin.id, "Logged in")
            flash("Welcome back.", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid username or password.", "error")
    return render_template("admin/login.html")

@app.route("/admin/logout")
@admin_required
def admin_logout():
    aid = session.pop("admin_id", None)
    if aid:
        log_action('admin', aid, "Logged out")
    flash("Logged out.", "success")
    return redirect(url_for("admin_login"))

# Seed admin (protected)
@app.route("/admin/seed_admin")
@admin_required
def seed_admin():
    existing = Admin.query.filter_by(username="admin").first()
    if existing:
        return "admin already exists"
    a = Admin(username="admin")
    a.set_password("password")
    db.session.add(a)
    db.session.commit()
    return "Seeded admin user: admin/password"

# Seed positions (protected)
@app.route("/admin/seed_positions")
@admin_required
def seed_positions():
    spec = [
        ("President", 1, None, "Executive", 1),
        ("VP For Social Unit", 1, None, "Executive", 2),
        ("VP For Graphics Unit", 1, None, "Executive", 3),
        ("VP for Coding Unit", 1, None, "Executive", 4),
        ("Secretary", 1, None, "Executive", 5),
        ("Sub Secretary", 1, None, "Executive", 6),
        ("Treasurer", 1, None, "Executive", 7),
        ("Sub Treasurer", 1, None, "Executive", 8),
        ("Auditors", 2, None, "Executive", 9),
        ("Business Manager", 2, None, "Executive", 10),
        ("PIO", 2, None, "Executive", 11),
        ("1st Year Social Unit Representative", 3, 1, "Representatives", 12),
        ("2nd Year Social Unit Representative", 3, 2, "Representatives", 13),
        ("3rd Year Social Unit Representative", 3, 3, "Representatives", 14),
        ("4th Year Social Unit Representative", 3, 4, "Representatives", 15),
        ("1st Year Graphic Unit Representative", 2, 1, "Representatives", 16),
        ("2nd Year Graphic Unit Representative", 2, 2, "Representatives", 17),
        ("3rd Year Graphic Unit Representative", 2, 3, "Representatives", 18),
        ("4th Year Graphic Unit Representative", 2, 4, "Representatives", 19),
        ("1st Year Coding Unit Representative", 2, 1, "Representatives", 20),
        ("2nd Year Coding Unit Representative", 2, 2, "Representatives", 21),
        ("3rd Year Coding Unit Representative", 2, 3, "Representatives", 22),
        ("4th Year Coding Unit Representative", 2, 4, "Representatives", 23),
    ]

    added = 0
    for name, max_sel, year, cat, sort in spec:
        exists = Position.query.filter_by(name=name).first()
        if not exists:
            db.session.add(Position(name=name, max_selection=max_sel, eligible_year=year, category=cat, sort_order=sort))
            added += 1
    if added:
        db.session.commit()
    return f"Seed complete. Added {added} new positions."

# ---------- Admin Dashboard & CRUD ----------
@app.route("/admin")
@admin_required
def admin_dashboard():
    total_students = Student.query.count()
    total_voted = Student.query.filter_by(has_voted=True).count()
    total_candidates = Candidate.query.count()
    total_votes = Vote.query.count()
    return render_template("admin/dashboard.html", total_students=total_students, total_voted=total_voted, total_candidates=total_candidates, total_votes=total_votes)

@app.route("/admin/positions", methods=["GET", "POST"])
@admin_required
def manage_positions():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        max_selection = int(request.form.get("max_selection", 1))
        eligible_year = request.form.get("eligible_year") or None
        category = request.form.get("category", "").strip() or None
        sort_order = int(request.form.get("sort_order", 0))
        pos = Position(name=name, max_selection=max_selection, eligible_year=int(eligible_year) if eligible_year else None, category=category, sort_order=sort_order)
        db.session.add(pos)
        db.session.commit()
        log_action('admin', session.get('admin_id'), f"Added position {name}")
        flash("Position added.", "success")
        return redirect(url_for("manage_positions"))
    positions = Position.query.order_by(Position.sort_order.asc(), Position.id.asc()).all()
    return render_template("admin/manage_positions.html", positions=positions)

@app.route("/admin/positions/<int:pid>/delete", methods=["POST"])
@admin_required
def delete_position(pid):
    pos = Position.query.get_or_404(pid)
    if pos.candidates:
        flash("Cannot delete: position has candidates.", "error")
        return redirect(url_for("manage_positions"))
    db.session.delete(pos)
    db.session.commit()
    log_action('admin', session.get('admin_id'), f"Deleted position {pos.name}")
    flash("Position deleted.", "success")
    return redirect(url_for("manage_positions"))

@app.route("/admin/partylists", methods=["GET", "POST"])
@admin_required
def manage_partylists():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            pl = Partylist(name=name)
            db.session.add(pl)
            db.session.commit()
            log_action('admin', session.get('admin_id'), f"Added partylist {name}")
            flash("Partylist added.", "success")
        return redirect(url_for("manage_partylists"))
    partylists = Partylist.query.order_by(Partylist.name.asc()).all()
    return render_template("admin/manage_partylist.html", partylists=partylists)

@app.route("/admin/partylists/<int:plid>/delete", methods=["POST"])
@admin_required
def delete_partylist(plid):
    pl = Partylist.query.get_or_404(plid)
    if pl.candidates:
        flash("Cannot delete: partylist has candidates.", "error")
        return redirect(url_for("manage_partylists"))
    db.session.delete(pl)
    db.session.commit()
    log_action('admin', session.get('admin_id'), f"Deleted partylist {pl.name}")
    flash("Partylist deleted.", "success")
    return redirect(url_for("manage_partylists"))

@app.route("/admin/candidates", methods=["GET", "POST"])
@admin_required
def manage_candidates():
    positions = Position.query.order_by(Position.sort_order.asc(), Position.name.asc()).all()
    partylists = Partylist.query.order_by(Partylist.name.asc()).all()
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        tagline = request.form.get("tagline", "").strip()
        position_id = int(request.form.get("position_id"))
        partylist_id = request.form.get("partylist_id")
        partylist_id = int(partylist_id) if partylist_id else None

        image_filename = None
        file = request.files.get("image")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            file.save(image_path)
            image_filename = filename

        cand = Candidate(first_name=first_name, last_name=last_name, tagline=tagline, position_id=position_id, partylist_id=partylist_id, image=image_filename)
        db.session.add(cand)
        db.session.commit()
        log_action('admin', session.get('admin_id'), f"Added candidate {cand.full_name} for position_id {position_id}")
        flash("Candidate added.", "success")
        return redirect(url_for("manage_candidates"))

    candidates = Candidate.query.order_by(Candidate.last_name.asc(), Candidate.first_name.asc()).all()
    return render_template("admin/manage_candidates.html", positions=positions, partylists=partylists, candidates=candidates)

@app.route("/admin/candidates/<int:cid>/delete", methods=["POST"])
@admin_required
def delete_candidate(cid):
    cand = Candidate.query.get_or_404(cid)
    if cand.votes:
        flash("Cannot delete: candidate already has votes.", "error")
        return redirect(url_for("manage_candidates"))
    db.session.delete(cand)
    db.session.commit()
    log_action('admin', session.get('admin_id'), f"Deleted candidate {cand.full_name}")
    flash("Candidate deleted.", "success")
    return redirect(url_for("manage_candidates"))

@app.route("/admin/students", methods=["GET"])
@admin_required
def manage_students():
    students = Student.query.order_by(Student.has_voted.desc(), Student.last_name.asc()).all()
    return render_template("admin/manage_students.html", students=students)

# Import CSV
@app.route("/admin/import", methods=["GET", "POST"])
@admin_required
def admin_import():
    if request.method == "POST":
        dtype = request.form.get("data_type")
        file = request.files.get("file")
        admin_id = session.get("admin_id")
        if not file:
            flash("No file uploaded.", "error")
            return redirect(url_for("admin_import"))

        if dtype == "students":
            summary = import_students(file, admin_id=admin_id)
            flash(f"Imported {summary['created']} students; skipped {len(summary['skipped'])}.", "success")
        elif dtype == "candidates":
            summary = import_candidates(file, admin_id=admin_id)
            flash(f"Imported {summary['created']} candidates; skipped {len(summary['skipped'])}.", "success")
        else:
            flash("Unknown import type.", "error")
        return redirect(url_for("admin_import"))

    return render_template("admin/import_data.html")

@app.route("/admin/results")
@admin_required
def admin_results():
    positions = Position.query.order_by(Position.sort_order.asc()).all()
    results_data = []
    for p in positions:
        candidates = Candidate.query.filter_by(position_id=p.id).all()
        counts = []
        total_votes_for_position = 0
        for c in candidates:
            vcount = Vote.query.filter_by(candidate_id=c.id).count()
            total_votes_for_position += vcount
            counts.append((c, vcount))
        results_data.append((p, counts, total_votes_for_position))

    from sqlalchemy import func
    partylist_names = []
    partylist_votes = []
    pls = Partylist.query.order_by(Partylist.name.asc()).all()
    for pl in pls:
        total = db.session.query(func.count(Vote.id)).join(Candidate).filter(Candidate.partylist_id == pl.id).scalar() or 0
        partylist_names.append(pl.name)
        partylist_votes.append(total)
    indep_total = db.session.query(func.count(Vote.id)).join(Candidate).filter(Candidate.partylist_id == None).scalar() or 0
    partylist_names.append("Independent")
    partylist_votes.append(indep_total)

    return render_template("admin/results.html", results=results_data, partylist_names=partylist_names, partylist_votes=partylist_votes)

@app.route("/admin/export_excel")
@admin_required
def export_excel():
    import pandas as pd
    positions = Position.query.order_by(Position.sort_order.asc()).all()
    rows = []
    for p in positions:
        candidates = Candidate.query.filter_by(position_id=p.id).all()
        for c in candidates:
            vcount = Vote.query.filter_by(candidate_id=c.id).count()
            rows.append({"Position": p.name, "Candidate": f"{c.first_name} {c.last_name}", "Partylist": (c.partylist.name if c.partylist_id else "Independent"), "Votes": vcount})
    df = pd.DataFrame(rows, columns=["Position", "Candidate", "Partylist", "Votes"])
    export_path = os.path.join(os.path.dirname(__file__), "itso_results.xlsx")
    df.to_excel(export_path, index=False)
    return send_file(export_path, as_attachment=True, download_name="itso_results.xlsx")

@app.route("/admin/logs")
@admin_required
def admin_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(500).all()
    return render_template("admin/audit_logs.html", logs=logs)

# ----------------------
# Run App
# ----------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
