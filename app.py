from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify
from flask_mysqldb import MySQL
from MySQLdb.cursors import DictCursor
import config
from functools import wraps
from collections import defaultdict
from datetime import time, timedelta, date, datetime
import requests

ESP32_IP = "192.168.1.200"  # Use your assigned static IP

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# MySQL config
app.config['MYSQL_HOST'] = config.MYSQL_HOST
app.config['MYSQL_USER'] = config.MYSQL_USER
app.config['MYSQL_PASSWORD'] = config.MYSQL_PASSWORD
app.config['MYSQL_DB'] = config.MYSQL_DB
mysql = MySQL(app)

def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'role' not in session:
                flash("Please log in first.")
                return redirect('/login')
            if session['role'] != role:
                flash("Unauthorized access.")
                return redirect('/login')
            return f(*args, **kwargs)
        return wrapped
    return decorator

def timedelta_to_str(td):
    total_seconds = int(td.total_seconds())
    total_seconds = total_seconds % (24 * 3600)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def get_student_time_in(student_id, subject_id):
    cur = mysql.connection.cursor()
    today = date.today()  # Get today's date in Python
    cur.execute("""
        SELECT time_in
        FROM student_attendance
        WHERE student_id = %s AND subject_id = %s AND date = %s
        LIMIT 1
    """, (student_id, subject_id, today))
    result = cur.fetchone()
    return result[0] if result else None

@app.route('/')
@role_required('instructor')
def subject_for_attendance():
    print('>>>>> subject_for_attendance')
    instructor_id = session['user']
    instructor_email = session.get('email')

    cur = mysql.connection.cursor(DictCursor)

    # Get all subjects assigned to this instructor
    cur.execute("""
        SELECT 
            s.id,
            s.subject_code,
            s.course_level,
            s.section,
            s.class_start_time,
            s.class_end_time,
            s.class_duration_time,
            (
                SELECT COUNT(*) 
                FROM student_subject_requests ssr 
                WHERE ssr.subject_id = s.id AND ssr.status = 'accepted'
            ) AS student_count,
            (
                SELECT COUNT(*) 
                FROM student_subject_requests ssr 
                WHERE ssr.subject_id = s.id AND ssr.status = 'pending'
            ) AS pending_count
        FROM subjects s
        WHERE s.instructor_id = %s
    """, (instructor_id,))

    subjects = cur.fetchall()

    now = datetime.now().time()

    for subject in subjects:
        # Convert to strings for display
        subject['start_time'] = timedelta_to_str(subject['class_start_time'])
        subject['end_time'] = timedelta_to_str(subject['class_end_time'])

        # Calculate readable duration
        duration = subject.get('class_duration_time')
        if duration is not None:
            hours = int(duration)
            minutes = int(round((duration - hours) * 60))
            subject['duration_time'] = f"{hours}:{minutes:02d}"
        else:
            subject['duration_time'] = 'N/A'

        # Check if now is between class_start_time and class_end_time
        start = (datetime.min + subject['class_start_time']).time()
        end = (datetime.min + subject['class_end_time']).time()
        subject['is_active_now'] = start <= now <= end

    return render_template('instructor/subject_list_for_attendance.html', subjects=subjects, instructor_email=instructor_email)

@app.route('/attendance/<int:subject_id>')
@role_required('instructor')
def subject_attendance_board(subject_id):
    try:        
        esp32_ip = f"http://{ESP32_IP}:5000/set_subject"
        payload = {'subject_id': subject_id, 'status': 'start'}
        response = requests.post(esp32_ip, json=payload)
        if response.status_code != 200:
            print(f"ERROR: ESP32 responded with an error {response.text}")
    except Exception as e:
        print(f"Failed to contact ESP32: {e}")

    print('>>>>> subject_attendance_board')
    cur = mysql.connection.cursor(DictCursor)

    # Get subject info
    cur.execute("SELECT * FROM subjects WHERE id = %s", (subject_id,))
    subject = cur.fetchone()

    subject['start_time_str'] = timedelta_to_str(subject['class_start_time'])
    subject['end_time_str'] = timedelta_to_str(subject['class_end_time'])

    # Get enrolled students
    cur.execute("""
            SELECT s.last_name, s.first_name, s.middle_name, s.id
            FROM students s
            JOIN student_subject_requests r ON s.id = r.student_id
            WHERE r.subject_id = %s AND r.status = 'accepted'
        """, (subject_id,))
    students = cur.fetchall()

    now = datetime.now().time()
    today = date.today()
    attendance_list = []
    class_start = subject['class_start_time']

    for student in students:
        mark = 'absent'
        student_id = student['id']
        student_time_in = get_student_time_in(student_id, subject_id)  # this is timedelta

        if not student_time_in:
            # this must only initialize and must execute once
            cur.execute("""
                    INSERT INTO student_attendance (student_id, subject_id, time_in, date, mark)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE time_in = VALUES(time_in), mark = VALUES(mark)
                """, (student_id, subject_id, student_time_in, today, mark))

            mysql.connection.commit()
        else:
              # timedelta
            student_time = student_time_in  # timedelta

            # check if student arrived within 15 minutes of class start
            if student_time <= class_start + timedelta(minutes=15):
                mark = 'check'
            else:
                mark = 'late'

        # Convert time_in to string safely
        if isinstance(student_time_in, timedelta):
            total_seconds = int(student_time_in.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            time_in_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        elif isinstance(student_time_in, time):
            time_in_str = student_time_in.strftime('%H:%M:%S')
        elif isinstance(student_time_in, datetime):
            time_in_str = student_time_in.time().strftime('%H:%M:%S')
        else:
            time_in_str = 'N/A'

        attendance_list.append({
            'last_name': student['last_name'],
            'first_name': student['first_name'],
            'middle_name': student['middle_name'],
            'time_in': time_in_str,
            'mark': mark
        })

    return render_template(
            'instructor/subject_attendance_board.html', 
            subject=subject, 
            attendance_list=attendance_list,
            end_time=subject['class_end_time']
        )

@app.route('/finalize_attendance/<int:subject_id>', methods=['POST'])
@role_required('instructor')
def finalize_attendance(subject_id):
    cur = mysql.connection.cursor(DictCursor)

    # Get subject start time
    cur.execute("SELECT class_start_time FROM subjects WHERE id = %s", (subject_id,))
    subject = cur.fetchone()
    class_start = subject['class_start_time']

    # Recalculate attendance marks
    cur.execute("""
        SELECT id, student_id, time_in
        FROM student_attendance
        WHERE subject_id = %s AND DATE(date) = CURDATE()
    """, (subject_id,))
    records = cur.fetchall()

    for record in records:
        attendance_id = record['id']
        student_time = record['time_in']

        if student_time is None:
            mark = 'absent'
        else:
            # Convert time_in to timedelta if stored as time
            if isinstance(student_time, time):
                student_time = timedelta(
                    hours=student_time.hour, minutes=student_time.minute, seconds=student_time.second
                )
            if student_time <= class_start + timedelta(minutes=15):
                mark = 'check'
            else:
                mark = 'late'

        cur.execute("""
            UPDATE student_attendance
            SET mark = %s
            WHERE id = %s
        """, (mark, attendance_id))

    mysql.connection.commit()
    
    try:        
        esp32_ip = "http://<ESP32_IP>:5000/set_subject"
        payload = {'subject_id': subject_id, 'status': 'stop'}
        response = requests.post(esp32_ip, json=payload)
        if response.status_code != 200:
            return jsonify({'error': 'ESP32 responded with an error', 'details': response.text}), 500

    except Exception as e:
        print("ESP32 stop command failed:", e)
        return jsonify({'error': 'Failed to contact ESP32', 'details': str(e)}), 500
    
    return jsonify({'message': 'Attendance finalized'}), 200


@app.route('/api/fingerprint_log', methods=['POST'])
def fingerprint_log():
    data = request.get_json()
    fingerprint_id = data.get('fingerprint_id')
    subject_id = data.get('subject_id')
    today = date.today()

    cur = mysql.connection.cursor(DictCursor)

    # Match student
    cur.execute("""
        SELECT id FROM students WHERE 
            %s IN (registered_fingerprint_1, registered_fingerprint_2, 
                   registered_fingerprint_3, registered_fingerprint_4, 
                   registered_fingerprint_5)
    """, (fingerprint_id,))
    student = cur.fetchone()

    if not student:
        return jsonify({'message': 'Unknown fingerprint'}), 404

    student_id = student['id']

    # Check if already recorded
    cur.execute("""
        SELECT * FROM student_attendance
        WHERE student_id = %s AND subject_id = %s AND date = %s
    """, (student_id, subject_id, today))
    existing = cur.fetchone()

    if existing:
        return jsonify({'message': 'Already recorded'}), 200

    # Record time_in
    now = datetime.now().time()
    mark = None  # Let your /finalize_attendance decide the mark

    cur.execute("""
        INSERT INTO student_attendance (student_id, subject_id, time_in, date, mark)
        VALUES (%s, %s, %s, %s, %s)
    """, (student_id, subject_id, now, today, mark))
    mysql.connection.commit()

    return jsonify({'message': 'Attendance recorded'}), 200







@app.route('/login', methods=['GET', 'POST'])
def login():
    role = request.args.get('role', 'instructor')  # Default to instructor
    
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        table = 'instructors' if role == 'instructor' else 'students'

        cur = mysql.connection.cursor(DictCursor)  # Use DictCursor for dictionary results
        cur.execute(f"SELECT * FROM {table} WHERE email = %s", (email,))
        user = cur.fetchone()

        print(f"Password MySQL: {user['password'] if user else None}")  # Optional debugging
        print(f"Password HTML: {password}")  # Optional debugging

        if user is None:
            flash("Invalid email or password (user not found)")
            return redirect(f'/login?role={role}')

        if user['password'] == password or True:  # Replace 'or True' with actual password check in prod
            # Store identifiers and email in session
            if role == 'instructor':
                session['user'] = user['employee_ID']  # Use employee_ID for instructors
            else:
                session['user'] = user['id']  # Use id for students

            session['role'] = role
            session['email'] = user['email']  # Store email for greeting

            return redirect('/' if role == 'instructor' else '/student_profile')
        else:
            flash("Invalid email or password (incorrect password)")
            return redirect(f'/login?role={role}')

    return render_template('auth/login.html', role=role)


@app.route('/register', methods=['GET', 'POST'])
def register():
    role = request.args.get('role', 'instructor')

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        fingerprint_id = request.form.get('registered_fingerprint_ID') or None

        cur = mysql.connection.cursor()

        if role == 'instructor':
            employee_id = request.form['employee_id']
            cur.execute("""
                INSERT INTO instructors (employee_id, email, password, registered_fingerprint_ID)
                VALUES (%s, %s, %s, %s)
            """, (employee_id, email, password, fingerprint_id))
            mysql.connection.commit()
            return redirect('/login?role=instructor')

        elif role == 'student':
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            school_id = request.form['school_id']
            section = request.form['section']
            course_level = request.form['course_level']
            cor_link = request.form['cor_link']
            middle_name = request.form['middle_name'].strip() or None

            cur.execute("""
                INSERT INTO students (
                    first_name, middle_name, last_name, school_ID,
                    section, course_level, email, password, COR_link,
                    registered_fingerprint_ID
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                first_name, middle_name, last_name, school_id,
                section, course_level, email, password, cor_link,
                fingerprint_id
            ))

            mysql.connection.commit()
            return redirect('/login?role=student')

    return render_template('auth/register.html', role=role)

@app.route('/edit-or-add-subject')
@role_required('instructor')
def edit_or_add_subjects():
    instructor_id = session.get('user')
    instructor_email = session.get('email') 

    cur = mysql.connection.cursor(DictCursor)

    cur.execute(
        """
            SELECT s.id, s.subject_code, s.course_level, s.section,
                s.class_start_time, s.class_end_time, s.class_duration_time,
                COUNT(ss.student_id) AS enrolled_count
            FROM subjects s
            LEFT JOIN student_subjects ss ON s.id = ss.subject_id
            WHERE s.instructor_id = %s
            GROUP BY s.id, s.subject_code, s.course_level, s.section,
                    s.class_start_time, s.class_end_time, s.class_duration_time
        """, 
        (instructor_id,)
    )

    subjects = cur.fetchall()
    subject_count = len(subjects)

    for subject in subjects:
        start = subject['class_start_time']
        end = subject['class_end_time']

        subject['class_start_time'] = timedelta_to_str(start)
        subject['class_end_time'] = timedelta_to_str(end)

        # Duration formatting as before
        duration = subject.get('class_duration_time')
        if duration is not None:
            hours = int(duration)
            minutes = int(round((duration - hours) * 60))
            subject['class_duration_time_display'] = f"{hours}:{minutes:02d}"
        else:
            subject['class_duration_time_display'] = 'N/A'
    # Get pending request counts per subject
    subject_ids = [subject['id'] for subject in subjects]
    if subject_ids:
        format_strings = ','.join(['%s'] * len(subject_ids))
        cur.execute(
            f"""
                SELECT subject_id, COUNT(*) as pending_count
                FROM student_subject_requests
                WHERE subject_id IN ({format_strings}) AND status = 'pending'
                GROUP BY subject_id
            """, tuple(subject_ids))
        pending_counts = {row['subject_id']: row['pending_count'] for row in cur.fetchall()}
    else:
        pending_counts = {}

    for subject in subjects:
        subject['pending_count'] = pending_counts.get(subject['id'], 0)

    # Group by course level
    grouped_subjects = {}
    for subject in subjects:
        level = subject['course_level']
        grouped_subjects.setdefault(level, []).append(subject)

    return render_template(
        'instructor/edit_add_subjects.html',
        grouped_subjects=grouped_subjects,
        instructor_email=instructor_email,
        subject_count=subject_count
    )

@app.route('/edit_instructor_profile', methods=['GET', 'POST'])
@role_required('instructor')
def instructor_profile():
    employee_id = session['user']  # make sure this matches your session key
    cur = mysql.connection.cursor(DictCursor)  # Use DictCursor for dict results

    if request.method == 'POST':
        fingerprint_id = request.form.get('registered_fingerprint_ID') or None

        # Update only the fingerprint ID; email is NOT changed here
        cur.execute("""
            UPDATE instructors
            SET registered_fingerprint_ID = %s
            WHERE employee_id = %s
        """, (fingerprint_id, employee_id))
        mysql.connection.commit()

        flash("Profile updated successfully!")
        return redirect('/edit-or-add-subject')

    cur.execute("SELECT email, registered_fingerprint_ID FROM instructors WHERE employee_id = %s", (employee_id,))
    instructor = cur.fetchone()
    return render_template('instructor/profile.html', instructor=instructor)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/delete_subject/<int:subject_id>')
@role_required('instructor')
def delete_subject(subject_id):
    instructor_id = session.get('user')

    cur = mysql.connection.cursor()
    # Verify subject ownership
    cur.execute("SELECT id FROM subjects WHERE id = %s AND instructor_id = %s", (subject_id, instructor_id))
    subject = cur.fetchone()

    if subject:
        # Delete dependent rows in student_subject_requests
        cur.execute("DELETE FROM student_subject_requests WHERE subject_id = %s", (subject_id,))
        # Delete dependent rows in student_subjects
        cur.execute("DELETE FROM student_subjects WHERE subject_id = %s", (subject_id,))
        # Now delete the subject itself
        cur.execute("DELETE FROM subjects WHERE id = %s", (subject_id,))
        mysql.connection.commit()
        flash('Subject deleted successfully', 'success')
    else:
        flash('Subject not found or unauthorized', 'error')

    return redirect('/edit-or-add-subject')

@app.route('/add_subject', methods=['POST'])
@role_required('instructor')
def add_subject():
    subject = request.form['subject']
    course_level = request.form['course_level']
    section = request.form['section']
    class_start_time = request.form['class_start_time']
    class_end_time = request.form['class_end_time']
    class_duration_time = request.form.get('class_duration_time')
    instructor_id = session['user']

    if not class_duration_time:
        flash("Duration is required")
        return redirect('/edit-or-add-subject')

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO subjects (
            instructor_id, subject_code, course_level, section,
            class_start_time, class_end_time, class_duration_time
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        instructor_id, subject, course_level, section,
        class_start_time, class_end_time, class_duration_time
    ))
    mysql.connection.commit()
    flash('Subject added successfully!')
    return redirect('/edit-or-add-subject')

@app.route('/subject/<int:subject_id>')
def subject_students(subject_id):
    if session.get('role') != 'instructor':
        return redirect('/login')

    # Fetch the subject info (optional, to display title)
    cur = mysql.connection.cursor()
    cur.execute("SELECT subject_code, course_level, section FROM subjects WHERE id = %s", (subject_id,))
    subject = cur.fetchone()

    # Fetch students enrolled in this subject
    # Assuming you have a table that links students to subjects, e.g., student_subjects(student_id, subject_id)
    cur.execute("""
        SELECT s.first_name, s.last_name, s.school_ID, s.COR_link, s.middle_name, s.id
        FROM students s
        JOIN student_subjects ss ON s.id = ss.student_id
        WHERE ss.subject_id = %s
        ORDER BY s.last_name ASC
    """, (subject_id,))
    students = cur.fetchall()
# 🔥 Get pending request count for this subject
    cur.execute("""
        SELECT COUNT(*) 
        FROM student_subject_requests 
        WHERE subject_id = %s AND status = 'pending'
    """, (subject_id,))
    pending_count = cur.fetchone()[0]

    return render_template('instructor/subject_students.html',
                           subject=subject,
                           students=students,
                           subject_id=subject_id,
                           pending_count=pending_count)

@app.route('/unenroll_student/<int:subject_id>/<int:student_id>')
def unenroll_student(subject_id, student_id):
    if session.get('role') != 'instructor':
        return redirect('/login')

    cur = mysql.connection.cursor()
    # Remove from enrolled list
    cur.execute("DELETE FROM student_subjects WHERE subject_id = %s AND student_id = %s", (subject_id, student_id))
    # Reset request status
    cur.execute("""
        UPDATE student_subject_requests
        SET status = 'rejected'
        WHERE subject_id = %s AND student_id = %s
    """, (subject_id, student_id))
    mysql.connection.commit()

    flash('Student has been unenrolled successfully.', 'success')
    return redirect(url_for('subject_students', subject_id=subject_id))

@app.route('/request_subject', methods=['POST'])
@role_required('student')
def request_subject():
    student_id = session['user']
    subject_id = request.form['subject_id']

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, status FROM student_subject_requests 
        WHERE student_id = %s AND subject_id = %s
    """, (student_id, subject_id))

    existing = cur.fetchone()

    if not existing:
        cur.execute("""
            INSERT INTO student_subject_requests (student_id, subject_id, status)
            VALUES (%s, %s, 'pending')
        """, (student_id, subject_id))
        mysql.connection.commit()
        request_id = cur.lastrowid
    elif existing[1] == 'rejected':
        cur.execute("""
            UPDATE student_subject_requests SET status = 'pending' 
            WHERE id = %s
        """, (existing[0],))
        mysql.connection.commit()
        request_id = existing[0]
    else:
        request_id = existing[0]

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'pending', 'request_id': request_id})

    return redirect('/student_profile')

@app.route('/subject_requests/<int:subject_id>')
@role_required('instructor')
def subject_requests(subject_id):
    cur = mysql.connection.cursor()
    # Get pending requests for this subject
    cur.execute("""
        SELECT r.id, s.last_name, s.first_name, s.middle_name, s.school_ID, s.COR_link
        FROM student_subject_requests r
        JOIN students s ON r.student_id = s.id
        WHERE r.subject_id = %s AND r.status = 'pending'
    """, (subject_id,))
    requests = cur.fetchall()


    # Get subject info (optional)
    cur.execute("SELECT subject_code, course_level, section FROM subjects WHERE id = %s", (subject_id,))
    subject = cur.fetchone()
    if not subject:
        return "Subject not found", 404


    return render_template('instructor/subject_requests.html', requests=requests, subject=subject, subject_id=subject_id)

@app.route('/update_request/<int:request_id>/<action>')
def update_request(request_id, action):
    if session.get('role') != 'instructor' or action not in ['accept', 'reject']:
        return redirect('/login')

    status = 'accepted' if action == 'accept' else 'rejected'

    cur = mysql.connection.cursor()

    # Update request status
    cur.execute("UPDATE student_subject_requests SET status = %s WHERE id = %s", (status, request_id))
    mysql.connection.commit()

    # If accepted, insert into student_subjects
    if status == 'accepted':
        # Get student_id and subject_id
        cur.execute("SELECT student_id, subject_id FROM student_subject_requests WHERE id = %s", (request_id,))
        student_id, subject_id = cur.fetchone()
        
        # Avoid duplicate enrollments
        cur.execute("SELECT id FROM student_subjects WHERE student_id = %s AND subject_id = %s", (student_id, subject_id))
        existing = cur.fetchone()
        if not existing:
            cur.execute("INSERT INTO student_subjects (student_id, subject_id) VALUES (%s, %s)", (student_id, subject_id))
            mysql.connection.commit()

    # Redirect back to request list
    cur.execute("SELECT subject_id FROM student_subject_requests WHERE id = %s", (request_id,))
    subject_id = cur.fetchone()[0]

    return redirect(f'/subject_requests/{subject_id}')

@app.route('/student_profile')
@role_required('student')
def student_profile():
    student_id = session['user']
    cur = mysql.connection.cursor(DictCursor)

    # Fetch all subjects
    cur.execute("""
        SELECT s.id, s.subject_code, s.course_level, s.section, 
            i.email AS instructor_email,
            s.class_start_time, s.class_end_time, s.class_duration_time
        FROM subjects s
        JOIN instructors i ON s.instructor_id = i.employee_ID
    """)

    subjects = cur.fetchall()

    for subject in subjects:
        start = subject['class_start_time']
        end = subject['class_end_time']

        subject['class_start_time'] = timedelta_to_str(start)
        subject['class_end_time'] = timedelta_to_str(end)

        # Duration formatting as before
        duration = subject.get('class_duration_time')
        if duration is not None:
            hours = int(duration)
            minutes = int(round((duration - hours) * 60))
            subject['class_duration_time_display'] = f"{hours}:{minutes:02d}"
        else:
            subject['class_duration_time_display'] = 'N/A'

    cur.execute("SELECT first_name, middle_name, last_name, course_level, section FROM students WHERE id = %s", (student_id,))
    student_info = cur.fetchone()

    # Fetch subject requests made by this student (including request id)
    cur.execute("""
        SELECT id, subject_id, status FROM student_subject_requests
        WHERE student_id = %s
    """, (student_id,))
    requests = cur.fetchall()

    # Build a dict: subject_id -> list of statuses
    requested_subjects = defaultdict(list)
    for r in requests:
        requested_subjects[r['subject_id']].append(r['status'])

    return render_template('student/profile.html', 
                            subjects=subjects, 
                            requested_subjects=requested_subjects, 
                            requests=requests, 
                            student_info=student_info)

@app.route('/cancel_request/<int:request_id>', methods=['POST'])
@role_required('student')
def cancel_request(request_id):
    student_id = session['user']
    cur = mysql.connection.cursor()
    # Only allow cancel if request belongs to logged-in student and is pending
    cur.execute("""
        DELETE FROM student_subject_requests
        WHERE id = %s AND student_id = %s AND status = 'pending'
    """, (request_id, student_id))
    mysql.connection.commit()
    flash("Request cancelled.")
    return redirect('/student_profile')

@app.route('/edit_student_profile', methods=['GET', 'POST'])
@role_required('student')
def edit_student_profile():
    student_id = session['user']
    cur = mysql.connection.cursor(DictCursor)

    if request.method == 'POST':
        first_name = request.form['first_name']
        middle_name = request.form['middle_name']
        last_name = request.form['last_name']
        school_id = request.form['school_id']
        section = request.form['section']
        course_level = request.form['course_level']
        cor_link = request.form['cor_link']

        # Update student info
        cur.execute("""
            UPDATE students
            SET first_name = %s,
                middle_name = %s,
                last_name = %s,
                school_ID = %s,
                section = %s,
                course_level = %s,
                COR_link = %s
            WHERE id = %s
        """, (first_name, middle_name, last_name, school_id, section, course_level, cor_link, student_id))
        mysql.connection.commit()

        flash("Profile updated successfully!")
        return redirect('/student_profile')

    # GET method - fetch current student info
    cur.execute("SELECT first_name, middle_name, last_name, school_ID, section, course_level, COR_link, email FROM students WHERE id = %s", (student_id,))
    student = cur.fetchone()

    return render_template('student/edit_profile.html', student=student)

if __name__ == '__main__':
    app.run(debug=True)