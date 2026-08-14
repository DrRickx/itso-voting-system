import io, csv
from models import db, Student, Partylist, Position, Candidate
from utils.audit_logger import log_action

def import_students(file_storage, admin_id=None):
    """
    CSV columns:
    student_number,year_level,section,major,first_name,last_name
    """
    text = file_storage.stream.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    created = 0
    skipped = []
    for i, row in enumerate(reader, start=2):
        sn = (row.get('student_number') or '').strip()
        try:
            year = int((row.get('year_level') or '').strip())
        except:
            year = None
        section = (row.get('section') or '').strip()
        major = (row.get('major') or '').strip()
        fn = (row.get('first_name') or '').strip()
        ln = (row.get('last_name') or '').strip()

        if not (sn and year and section and major and fn and ln):
            skipped.append((i, "Missing required fields"))
            continue

        existing = Student.query.filter_by(student_number=sn).first()
        if existing:
            skipped.append((i, "Student number already exists"))
            continue

        s = Student(
            student_number=sn,
            year_level=year,
            section=section,
            major=major,
            first_name=fn,
            last_name=ln
        )
        db.session.add(s)
        created += 1

    db.session.commit()
    if admin_id:
        log_action('admin', admin_id, f"Imported students CSV: created={created}, skipped={len(skipped)}")
    return {"created": created, "skipped": skipped}

def import_candidates(file_storage, admin_id=None):
    """
    CSV columns:
    first_name,last_name,position,partylist,tagline,image_filename(optional)
    """
    text = file_storage.stream.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    created = 0
    skipped = []
    for i, row in enumerate(reader, start=2):
        fn = (row.get('first_name') or '').strip()
        ln = (row.get('last_name') or '').strip()
        position_name = (row.get('position') or '').strip()
        party_name = (row.get('partylist') or '').strip()
        tagline = (row.get('tagline') or '').strip()
        image = (row.get('image_filename') or '').strip() or None

        if not (fn and ln and position_name):
            skipped.append((i, "Missing required fields"))
            continue

        pos = Position.query.filter_by(name=position_name).first()
        if not pos:
            skipped.append((i, f"Position '{position_name}' not found"))
            continue

        party = None
        if party_name:
            party = Partylist.query.filter_by(name=party_name).first()
            if not party:
                party = Partylist(name=party_name)
                db.session.add(party)
                db.session.flush()

        cand = Candidate(
            first_name=fn,
            last_name=ln,
            tagline=tagline,
            image=image,
            position_id=pos.id,
            partylist_id=(party.id if party else None)
        )
        db.session.add(cand)
        created += 1

    db.session.commit()
    if admin_id:
        log_action('admin', admin_id, f"Imported candidates CSV: created={created}, skipped={len(skipped)}")
    return {"created": created, "skipped": skipped}
