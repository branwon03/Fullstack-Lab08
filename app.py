from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///enrollment.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False) 
    
    enrollments = db.relationship('Enrollment', backref='student', lazy=True, foreign_keys='Enrollment.student_id')
    courses_taught = db.relationship('Course', backref='teacher', lazy=True)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    time = db.Column(db.String(100), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    enrollments = db.relationship('Enrollment', backref='course', lazy=True, cascade='all, delete-orphan')

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    grade = db.Column(db.Float, nullable=True)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)

from flask_admin import AdminIndexView, expose

class SecureAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not self.is_accessible():
            return self.inaccessible_callback(name='index')
        return super(SecureAdminIndexView, self).index()
    
    def is_accessible(self):
        return session.get('role') == 'admin'
    
    def inaccessible_callback(self, name, **kwargs):
        flash('You must be an admin to access this page.', 'danger')
        return redirect(url_for('login'))

admin = Admin(app, name='UC Merced Dashboard', template_mode='bootstrap3', index_view=SecureAdminIndexView())

class SecureModelView(ModelView):
    def is_accessible(self):
        return session.get('role') == 'admin'
    
    def inaccessible_callback(self, name, **kwargs):
        flash('You must be an admin to access this page.', 'danger')
        return redirect(url_for('login'))

class EnrollmentAdminView(SecureModelView):
    # Show basic columns in list view
    column_list = ['id', 'student_id', 'course_id', 'grade', 'enrolled_at']
    column_labels = {
        'id': 'ID',
        'student_id': 'Student ID',
        'course_id': 'Course ID',
        'grade': 'Grade',
        'enrolled_at': 'Enrolled At'
    }
    column_default_sort = ('enrolled_at', True)

class CourseAdminView(SecureModelView):
    # Show columns in list view
    column_list = ['name', 'time', 'capacity', 'teacher_id']
    column_labels = {
        'name': 'Course Name',
        'time': 'Time',
        'capacity': 'Capacity',
        'teacher_id': 'Teacher ID'
    }
    column_searchable_list = ['name']
    # Explicitly include teacher_id in the create/edit form
    form_columns = ['name', 'time', 'capacity', 'teacher_id']

admin.add_view(SecureModelView(User, db.session))
admin.add_view(CourseAdminView(Course, db.session))
admin.add_view(EnrollmentAdminView(Enrollment, db.session))

@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'student':
            return redirect(url_for('student_dashboard'))
        elif role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        elif role == 'admin':
            return redirect(url_for('admin.index'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        # DEVELOPMENT ONLY: Using plain text password comparison
        # WARNING: Never use this in production!
        if user and user.password == password:
            session['user_id'] = user.id
            session['username'] = user.username
            session['full_name'] = user.full_name
            session['role'] = user.role
            
            flash(f'Welcome {user.full_name}!', 'success')
            
            if user.role == 'student':
                return redirect(url_for('student_dashboard'))
            elif user.role == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            elif user.role == 'admin':
                return redirect(url_for('admin.index'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/student/dashboard')
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please log in as a student.', 'warning')
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    enrollments = Enrollment.query.filter_by(student_id=student_id).all()
    
    return render_template('student_dashboard.html', enrollments=enrollments)

@app.route('/student/add_courses')
def add_courses():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please log in as a student.', 'warning')
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    
    all_courses = Course.query.all()
    
    enrolled_course_ids = [e.course_id for e in Enrollment.query.filter_by(student_id=student_id).all()]
    
    available_courses = []
    for course in all_courses:
        if course.id not in enrolled_course_ids:
            enrolled_count = Enrollment.query.filter_by(course_id=course.id).count()
            teacher = User.query.get(course.teacher_id)
            available_courses.append({
                'course': course,
                'enrolled_count': enrolled_count,
                'spots_left': course.capacity - enrolled_count,
                'is_full': enrolled_count >= course.capacity,
                'teacher_name': teacher.full_name if teacher else 'Unknown'
            })
    
    return render_template('add_courses.html', courses=available_courses)

@app.route('/student/enroll/<int:course_id>', methods=['POST'])
def enroll_course(course_id):
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please log in as a student.', 'warning')
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    course = Course.query.get_or_404(course_id)
    
    existing = Enrollment.query.filter_by(student_id=student_id, course_id=course_id).first()
    if existing:
        flash('You are already enrolled in this course.', 'warning')
        return redirect(url_for('add_courses'))
    
    enrolled_count = Enrollment.query.filter_by(course_id=course_id).count()
    if enrolled_count >= course.capacity:
        flash('This course is full.', 'danger')
        return redirect(url_for('add_courses'))
    
    enrollment = Enrollment(student_id=student_id, course_id=course_id)
    db.session.add(enrollment)
    db.session.commit()
    
    flash(f'Successfully enrolled in {course.name}!', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/student/drop/<int:enrollment_id>', methods=['POST'])
def drop_course(enrollment_id):
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please log in as a student.', 'warning')
        return redirect(url_for('login'))
    
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    
    if enrollment.student_id != session['user_id']:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('student_dashboard'))
    
    course_name = enrollment.course.name
    db.session.delete(enrollment)
    db.session.commit()
    
    flash(f'Successfully dropped {course_name}.', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/teacher/dashboard')
def teacher_dashboard():
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('Please log in as a teacher.', 'warning')
        return redirect(url_for('login'))
    
    teacher_id = session['user_id']
    courses = Course.query.filter_by(teacher_id=teacher_id).all()
    
    return render_template('teacher_dashboard.html', courses=courses)

@app.route('/teacher/course/<int:course_id>')
def view_course(course_id):
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('Please log in as a teacher.', 'warning')
        return redirect(url_for('login'))
    
    course = Course.query.get_or_404(course_id)
    
    if course.teacher_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    enrollments = Enrollment.query.filter_by(course_id=course_id).all()
    
    return render_template('view_course.html', course=course, enrollments=enrollments)

@app.route('/teacher/update_grade/<int:enrollment_id>', methods=['POST'])
def update_grade(enrollment_id):
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('Please log in as a teacher.', 'warning')
        return redirect(url_for('login'))
    
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    course = enrollment.course
    
    if course.teacher_id != session['user_id']:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    grade = request.form.get('grade')
    
    if grade:
        try:
            enrollment.grade = float(grade)
            db.session.commit()
            flash('Grade updated successfully!', 'success')
        except ValueError:
            flash('Invalid grade value.', 'danger')
    
    return redirect(url_for('view_course', course_id=course.id))

def init_db():
    with app.app_context():
        db.create_all()
        
        if User.query.count() > 0:
            print("Database already initialized.")
            return
        
        # DEVELOPMENT ONLY: Storing plain text passwords
        # WARNING: Never use this in production!
        students = [
            User(username='jsantos', password='password', full_name='Jose Santos', role='student'),
            User(username='bbrown', password='password', full_name='Betty Brown', role='student'),
            User(username='jstuart', password='password', full_name='John Stuart', role='student'),
            User(username='lcheng', password='password', full_name='Li Cheng', role='student'),
            User(username='nlittle', password='password', full_name='Nancy Little', role='student'),
            User(username='mnorris', password='password', full_name='Mindy Norris', role='student'),
            User(username='aranganath', password='password', full_name='Aditya Ranganath', role='student'),
            User(username='ychen', password='password', full_name='Yi Wen Chen', role='student'),
            User(username='cnorris', password='password', full_name='Chuck Norris', role='student'),
            User(username='kmalik', password='password', full_name='Kabir Malik', role='student'),
            User(username='aghosh', password='password', full_name='Aditya Ghosh', role='student'),
            User(username='bwong', password='password', full_name='Brandon Wong', role='student'),

        ]
        
        teachers = [
            User(username='rjenkins', password='password', full_name='Ralph Jenkins', role='teacher'),
            User(username='swalker', password='password', full_name='Susan Walker', role='teacher'),
            User(username='ahepworth', password='password', full_name='Ammon Hepworth', role='teacher'),
            User(username='scarpin', password='password', full_name='Stefano Carpin', role='teacher'),
            User(username='acerpa', password='password', full_name='Alberto Cerpa', role='teacher'),

        ]
        
        admin = [
            User(username='jsmuñoz',password='password',full_name='Juan Sánchez Muñoz', role='admin'),
            User(username='admin',password='password',full_name='Administrator', role='admin'),
        ]

        for user in students + teachers + admin:
            db.session.add(user)
        
        db.session.commit()
        
        courses = [
            Course(name='Math 101', time='MWF 10:00-10:50 AM', capacity=8, teacher_id=teachers[0].id),
            Course(name='Physics 121', time='TR 11:00-11:50 AM', capacity=10, teacher_id=teachers[1].id),
            Course(name='CS 106', time='MWF 2:00-2:50 PM', capacity=10, teacher_id=teachers[2].id),
            Course(name='CSE 162', time='TR 3:00-3:50 PM', capacity=4, teacher_id=teachers[2].id),
            Course(name='CSE 108', time='TR 5:00-7:00 PM', capacity=120, teacher_id=teachers[2].id),
            Course(name='CSE 160', time='MW 3:00-5:00 PM', capacity=120, teacher_id=teachers[4].id),
            Course(name='CSE 180', time='TUTR 10:30-11:45 AM', capacity=120, teacher_id=teachers[3].id),

        ]
        
        for course in courses:
            db.session.add(course)
        
        db.session.commit()
        
        enrollments_data = [
            (students[0].id, courses[0].id, 92.0),  
            (students[1].id, courses[0].id, 65.0),  
            (students[2].id, courses[0].id, 86.0),  
            (students[3].id, courses[0].id, 77.0),
            
            (students[4].id, courses[1].id, 53.0),   
            (students[3].id, courses[1].id, 85.0),
            (students[5].id, courses[1].id, 94.0),   
            (students[2].id, courses[1].id, 91.0),  
            (students[1].id, courses[1].id, 88.0),  
            
            (students[6].id, courses[2].id, 93.0),  
            (students[7].id, courses[2].id, 85.0),  
            (students[4].id, courses[2].id, 57.0),   
            (students[5].id, courses[2].id, 68.0),   
            
            (students[6].id, courses[3].id, 99.0),  
            (students[4].id, courses[3].id, 87.0),   
            (students[7].id, courses[3].id, 92.0),  
            (students[2].id, courses[3].id, 67.0),  

            (students[9].id, courses[4].id, 100.0),  
            (students[10].id, courses[4].id, 100.0),  
            (students[11].id, courses[4].id, 100.0),

            (students[9].id, courses[5].id, 87.0),  
            (students[10].id, courses[5].id, 83.0),  

            (students[9].id, courses[6].id, 88.0),  
            (students[10].id, courses[6].id, 95.0),  

        ]
        
        for student_id, course_id, grade in enrollments_data:
            enrollment = Enrollment(student_id=student_id, course_id=course_id, grade=grade)
            db.session.add(enrollment)
        
        db.session.commit()
        print("Database initialized with sample data!")

if __name__ == '__main__':
    init_db()
    app.run(debug=True)