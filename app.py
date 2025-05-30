from flask import Flask, render_template, request, redirect, session, flash, url_for
from flask_mysqldb import MySQL
from MySQLdb.cursors import DictCursor
import config
from functools import wraps

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



app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# MySQL config
app.config['MYSQL_HOST'] = config.MYSQL_HOST
app.config['MYSQL_USER'] = config.MYSQL_USER
app.config['MYSQL_PASSWORD'] = config.MYSQL_PASSWORD
app.config['MYSQL_DB'] = config.MYSQL_DB
mysql = MySQL(app)

@app.route('/')
def home():
    return redirect('/login')


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

            return redirect('/instructor_profile' if role == 'instructor' else '/student_profile')
        else:
            flash("Invalid email or password (incorrect password)")
            return redirect(f'/login?role={role}')

    return render_template('login.html', role=role)





@app.route('/register', methods=['GET', 'POST'])
def register():
    role = request.args.get('role', 'instructor')

    if request.method == 'POST':
        email = request.form['email']
        # password = generate_password_hash(request.form['password'])
        password = request.form['password']

        cur = mysql.connection.cursor()

        if role == 'instructor':
            employee_id = request.form['employee_id']
            cur.execute("""
                INSERT INTO instructors (employee_id, email, password)
                VALUES (%s, %s, %s)
            """, (employee_id, email, password))
            mysql.connection.commit()
            return redirect('/login?role=instructor')

        elif role == 'student':
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            school_id = request.form['school_id']
            section = request.form['section']
            course_level = request.form['course_level']  # map to DB column name
            cor_link = request.form['cor_link']
            middle_name = request.form['middle_name'].strip() or None

            cur.execute("""
                INSERT INTO students (
                    first_name, middle_name, last_name, school_ID,
                    section, course_level, email, password, COR_link
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                first_name, middle_name, last_name, school_id,
                section, course_level, email, password, cor_link
            ))

            mysql.connection.commit()
            return redirect('/login?role=student')

    return render_template('register.html', role=role)




@app.route('/instructor_profile')
def instructor_profile():
    if session.get('role') != 'instructor':
        return redirect('/login')

    instructor_id = session.get('user')
    instructor_email = session.get('email') 

    print(f"✅instructor_email: {instructor_email}")

    cur = mysql.connection.cursor(DictCursor)

    # Get subjects and count
    cur.execute("""
        SELECT s.id, s.subject_code, s.course_level, s.section,
            COUNT(ss.student_id) AS enrolled_count
        FROM subjects s
        LEFT JOIN student_subjects ss ON s.id = ss.subject_id
        WHERE s.instructor_id = %s
        GROUP BY s.id, s.subject_code, s.course_level, s.section
    """, (instructor_id,))
    
    subjects = cur.fetchall()
    subject_count = len(subjects)

    # Get pending request counts per subject
    subject_ids = [subject['id'] for subject in subjects]
    if subject_ids:
        format_strings = ','.join(['%s'] * len(subject_ids))
        cur.execute(f"""
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
        'instructor_profile.html',
        grouped_subjects=grouped_subjects,
        instructor_email=instructor_email,
        subject_count=subject_count
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/delete_subject/<int:subject_id>')
def delete_subject(subject_id):
    if session.get('role') != 'instructor':
        return redirect('/login')

    instructor_id = session.get('user')

    cur = mysql.connection.cursor()
    # Verify the subject belongs to this instructor before deleting
    cur.execute("SELECT id FROM subjects WHERE id = %s AND instructor_id = %s", (subject_id, instructor_id))
    subject = cur.fetchone()
    if subject:
        cur.execute("DELETE FROM subjects WHERE id = %s", (subject_id,))
        mysql.connection.commit()
        flash('Subject deleted successfully', 'success')
    else:
        flash('Subject not found or unauthorized', 'error')

    return redirect('/instructor_profile')



@app.route('/add_subject', methods=['POST'])
def add_subject():
    if session.get('role') != 'instructor':
        return redirect('/login')

    subject = request.form['subject']
    course_level = request.form['course_level']
    section = request.form['section']
    instructor_id = session['user']

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO subjects (instructor_id, subject_code, course_level, section)
        VALUES (%s, %s, %s, %s)
    """, (instructor_id, subject, course_level, section))
    mysql.connection.commit()
    flash('Subject added successfully!')
    return redirect('/instructor_profile')


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

    return render_template('subject_students.html',
                           subject=subject,
                           students=students,
                           subject_id=subject_id,
                           pending_count=pending_count)

@app.route('/unenroll_student/<int:subject_id>/<int:student_id>')
def unenroll_student(subject_id, student_id):
    if session.get('role') != 'instructor':
        return redirect('/login')

    cur = mysql.connection.cursor()
    # Delete the record linking this student and subject
    cur.execute("DELETE FROM student_subjects WHERE subject_id = %s AND student_id = %s", (subject_id, student_id))
    mysql.connection.commit()

    flash('Student has been unenrolled successfully.', 'success')
    return redirect(url_for('subject_students', subject_id=subject_id))

@app.route('/request_subject', methods=['POST'])
def request_subject():
    if session.get('role') != 'student':
        return redirect('/login')

    student_id = session['user']
    subject_id = request.form['subject_id']

    cur = mysql.connection.cursor()
    # Check if request already exists to avoid duplicates
    cur.execute("""
        SELECT id FROM student_subject_requests 
        WHERE student_id = %s AND subject_id = %s
    """, (student_id, subject_id))
    
    existing = cur.fetchone()

    if not existing:
        cur.execute("""
            INSERT INTO student_subject_requests (student_id, subject_id) VALUES (%s, %s)
        """, (student_id, subject_id))
        mysql.connection.commit()

    cur.execute("""
        INSERT INTO student_subject_requests (student_id, subject_id, status)
        VALUES (%s, %s, 'pending')
    """, (student_id, subject_id))
    mysql.connection.commit()

    return redirect('/student_profile')  # or wherever appropriate

@app.route('/subject_requests/<int:subject_id>')
def subject_requests(subject_id):
    if session.get('role') != 'instructor':
        return redirect('/login')

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


    return render_template('subject_requests.html', requests=requests, subject=subject, subject_id=subject_id)

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
def student_profile():
    if session.get('role') != 'student':
        return redirect('/login')

    student_id = session['user']

    cur = mysql.connection.cursor(DictCursor)

    # Fetch all subjects
    cur.execute("""
        SELECT s.id, s.subject_code, s.course_level, s.section, i.email as instructor_email
        FROM subjects s
        JOIN instructors i ON s.instructor_id = i.employee_ID
    """)

    subjects = cur.fetchall()

    cur.execute("SELECT first_name, middle_name, last_name, course_level, section FROM students WHERE id = %s", (student_id,))
    student_info = cur.fetchone()

    # Fetch subject requests made by this student (including request id)
    cur.execute("""
        SELECT id, subject_id, status FROM student_subject_requests
        WHERE student_id = %s
    """, (student_id,))
    requests = cur.fetchall()
    requested_subjects = {r['subject_id']: r['status'] for r in requests}

    return render_template('student_profile.html', subjects=subjects, requested_subjects=requested_subjects, requests=requests, student_info=student_info)


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

    return render_template('edit_student_profile.html', student=student)


if __name__ == '__main__':
    app.run(debug=True)
