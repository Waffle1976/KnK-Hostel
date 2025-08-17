from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import os
import json

# Create the application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hostel.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Define models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(10), unique=True, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    occupied = db.Column(db.Integer, default=0)
    
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'))
    check_in_date = db.Column(db.DateTime, nullable=False)
    room = db.relationship('Room', backref=db.backref('students', lazy=True))

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship('User', backref=db.backref('audit_logs', lazy=True))
    
    @classmethod
    def log(cls, action, entity_type, entity_id=None, details=None):
        log_entry = cls(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            user_id=current_user.id if not current_user.is_anonymous else None
        )
        db.session.add(log_entry)
        db.session.commit()
        return log_entry

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/audit_logs')
@login_required
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    return render_template('audit_logs.html', logs=logs)

@app.route('/api/audit_logs')
@login_required
def api_audit_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    logs_data = [{
        'id': log.id,
        'action': log.action,
        'entity_type': log.entity_type,
        'entity_id': log.entity_id,
        'details': log.details,
        'user': log.user.username if log.user else 'System',
        'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for log in logs]
    return jsonify(logs_data)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:  # In production, use proper password hashing
            login_user(user)
            flash('Login successful')
            # Log the login action
            with app.app_context():
                AuditLog.log('login', 'user', user.id, f'User {username} logged in')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    username = current_user.username
    user_id = current_user.id
    logout_user()
    flash('You have been logged out')
    # Log the logout action
    with app.app_context():
        AuditLog.log('logout', 'user', user_id, f'User {username} logged out')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    rooms = Room.query.all()
    students = Student.query.all()
    
    # Calculate bed statistics
    total_beds = sum(room.capacity for room in rooms)
    occupied_beds = sum(room.occupied for room in rooms)
    available_beds = total_beds - occupied_beds
    
    return render_template('dashboard.html', 
                           rooms=rooms, 
                           students=students, 
                           total_beds=total_beds,
                           occupied_beds=occupied_beds,
                           available_beds=available_beds)
@app.route('/add_student', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        name = request.form.get('name')
        student_id = request.form.get('student_id')
        room_id = request.form.get('room_id')

        # 🔹 Check if student_id already exists
        existing_student = Student.query.filter_by(student_id=student_id).first()
        if existing_student:
            flash('This Student ID is already registered!', 'danger')
            return redirect(url_for('add_student'))

        room = Room.query.get(room_id)
        if room and room.occupied < room.capacity:
            student = Student(
                name=name,
                student_id=student_id,
                room_id=room_id,
                check_in_date=datetime.now()
            )
            room.occupied += 1
            db.session.add(student)
            db.session.commit()

            # Log the student addition
            AuditLog.log(
                'add',
                'student',
                student.id,
                f'Student {name} (ID: {student_id}) added to room {room.room_number}'
            )

            flash('Student added successfully', 'success')
            return redirect(url_for('dashboard'))

        flash('Room is full or invalid', 'danger')

    # Only show rooms with free space
    rooms = Room.query.filter(Room.capacity > Room.occupied).all()
    return render_template('add_student.html', rooms=rooms)


@app.route('/add_room', methods=['GET', 'POST'])
@login_required
def add_room():
    if request.method == 'POST':
        room_number = request.form.get('room_number')
        capacity = request.form.get('capacity')
        
        if Room.query.filter_by(room_number=room_number).first():
            flash('Room number already exists')
        else:
            room = Room(
                room_number=room_number,
                capacity=int(capacity),
                occupied=0
            )
            db.session.add(room)
            db.session.commit()
            
            # Log the room addition
            AuditLog.log('add', 'room', room.id, 
                        f'Room {room_number} with capacity {capacity} added')
            
            flash('Room added successfully')
            return redirect(url_for('beds'))
    return render_template('add_room.html')

@app.route('/beds')
@login_required
def beds():
    rooms = Room.query.all()
    
    # Calculate bed statistics
    total_beds = sum(room.capacity for room in rooms)
    occupied_beds = sum(room.occupied for room in rooms)
    available_beds = total_beds - occupied_beds
    
    return render_template('beds.html', 
                           rooms=rooms, 
                           total_beds=total_beds,
                           occupied_beds=occupied_beds,
                           available_beds=available_beds)

@app.route('/edit_room/<int:room_id>', methods=['GET', 'POST'])
@login_required
def edit_room(room_id):
    room = Room.query.get_or_404(room_id)
    
    if request.method == 'POST':
        new_capacity = int(request.form.get('capacity'))
        old_capacity = room.capacity
        
        # Ensure new capacity is not less than current occupancy
        if new_capacity < room.occupied:
            flash('New capacity cannot be less than current occupancy')
            return redirect(url_for('edit_room', room_id=room_id))
        
        room.capacity = new_capacity
        db.session.commit()
        
        # Log the room update
        AuditLog.log('update', 'room', room.id, 
                    f'Room {room.room_number} capacity changed from {old_capacity} to {new_capacity}')
        
        flash('Room capacity updated successfully')
        return redirect(url_for('beds'))
        
    return render_template('edit_room.html', room=room)

@app.route('/remove_student/<int:student_id>', methods=['POST'])
@login_required
def remove_student(student_id):
    student = Student.query.get_or_404(student_id)
    student_name = student.name
    student_id_num = student.student_id
    room = Room.query.get(student.room_id)
    room_number = room.room_number if room else 'Unknown'
    
    if room:
        room.occupied -= 1
    db.session.delete(student)
    db.session.commit()
    
    # Log the student removal
    AuditLog.log('remove', 'student', student_id, 
                f'Student {student_name} (ID: {student_id_num}) removed from room {room_number}')
    
    flash('Student removed successfully')
    return redirect(url_for('dashboard'))

# Initialize the database and add sample data
def initialize_db():
    with app.app_context():
        db.create_all()
        
        # Check if admin user exists
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin = User(username='admin', password='admin123', role='admin')
            db.session.add(admin)
            db.session.commit()
            print('Admin user created successfully')
            
            # Add sample rooms
            rooms = [
                Room(room_number='101', capacity=4, occupied=0),
                Room(room_number='102', capacity=2, occupied=0),
                Room(room_number='103', capacity=3, occupied=0),
                Room(room_number='201', capacity=2, occupied=0)
            ]
            db.session.add_all(rooms)
            db.session.commit()
            print('Sample rooms added successfully')

# Create HTML templates directory if it doesn't exist
def create_templates():
    if not os.path.exists('templates'):
        os.makedirs('templates')
        
    # Beds Management template
    with open('templates/beds.html', 'w') as f:
        f.write('''{% extends "base.html" %}
{% block content %}
<div class="row mb-4">
    <div class="col-md-12">
        <h2 class="text-center mb-4 animate__animated animate__fadeIn"><i class="fas fa-bed me-2"></i> Beds Management</h2>
    </div>
</div>

<!-- Stats Cards -->
<div class="row mb-4">
    <div class="col-md-4">
        <div class="card stat-card animate__animated animate__fadeInUp">
            <div class="card-body">
                <i class="fas fa-bed icon-stat"></i>
                <div class="stat-value">{{ total_beds }}</div>
                <div class="stat-label">Total Beds</div>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card stat-card animate__animated animate__fadeInUp" style="animation-delay: 0.1s;">
            <div class="card-body">
                <i class="fas fa-user-check icon-stat"></i>
                <div class="stat-value">{{ occupied_beds }}</div>
                <div class="stat-label">Occupied Beds</div>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card stat-card animate__animated animate__fadeInUp" style="animation-delay: 0.2s;">
            <div class="card-body">
                <i class="fas fa-check-circle icon-stat"></i>
                <div class="stat-value">{{ available_beds }}</div>
                <div class="stat-label">Available Beds</div>
            </div>
        </div>
    </div>
</div>

<div class="card mb-4 animate__animated animate__fadeInUp">
    <div class="card-header d-flex justify-content-between align-items-center">
        <h3><i class="fas fa-door-open me-2"></i>Rooms and Beds</h3>
        <a href="{{ url_for('add_room') }}" class="btn btn-primary">
            <i class="fas fa-plus-circle me-1"></i> Add New Room
        </a>
    </div>
    <div class="card-body">
        <div class="table-responsive">
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>Room Number</th>
                        <th>Total Beds</th>
                        <th>Occupied Beds</th>
                        <th>Available Beds</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for room in rooms %}
                    <tr>
                        <td><i class="fas fa-door-closed me-1"></i> {{ room.room_number }}</td>
                        <td><i class="fas fa-bed me-1"></i> {{ room.capacity }}</td>
                        <td><i class="fas fa-user me-1"></i> {{ room.occupied }}</td>
                        <td><i class="fas fa-check-circle me-1"></i> {{ room.capacity - room.occupied }}</td>
                        <td>
                            {% if room.capacity == room.occupied %}
                                <span class="badge bg-danger">Full</span>
                            {% elif room.occupied == 0 %}
                                <span class="badge bg-success">Empty</span>
                            {% else %}
                                <span class="badge bg-warning">Partial</span>
                            {% endif %}
                        </td>
                        <td>
                            <a href="{{ url_for('edit_room', room_id=room.id) }}" class="btn btn-sm btn-primary">
                                <i class="fas fa-edit"></i> Edit Capacity
                            </a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}''')
        
    # Edit Room template
    with open('templates/edit_room.html', 'w') as f:
        f.write('''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card animate__animated animate__fadeInUp">
            <div class="card-header">
                <h3 class="text-center"><i class="fas fa-edit me-2"></i>Edit Room Capacity</h3>
            </div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label for="room_number" class="form-label">Room Number</label>
                        <input type="text" class="form-control" id="room_number" value="{{ room.room_number }}" disabled>
                    </div>
                    <div class="mb-3">
                        <label for="current_capacity" class="form-label">Current Capacity</label>
                        <input type="text" class="form-control" id="current_capacity" value="{{ room.capacity }}" disabled>
                    </div>
                    <div class="mb-3">
                        <label for="current_occupied" class="form-label">Current Occupied</label>
                        <input type="text" class="form-control" id="current_occupied" value="{{ room.occupied }}" disabled>
                    </div>
                    <div class="mb-3">
                        <label for="capacity" class="form-label">New Capacity</label>
                        <input type="number" class="form-control" id="capacity" name="capacity" min="{{ room.occupied }}" value="{{ room.capacity }}" required>
                        <small class="text-muted">New capacity cannot be less than current occupancy ({{ room.occupied }}).</small>
                    </div>
                    <div class="text-center">
                        <button type="submit" class="btn btn-primary">
                            <i class="fas fa-save me-1"></i> Update Capacity
                        </button>
                        <a href="{{ url_for('beds') }}" class="btn btn-secondary">
                            <i class="fas fa-times me-1"></i> Cancel
                        </a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}''')
        
    # Audit Logs template
    with open('templates/audit_logs.html', 'w') as f:
        f.write('''{% extends "base.html" %}
{% block content %}
<div class="row mb-4">
    <div class="col-md-12">
        <h2 class="text-center mb-4 animate__animated animate__fadeIn"><i class="fas fa-history me-2"></i> Audit Logs</h2>
    </div>
</div>

<div class="card animate__animated animate__fadeInUp">
    <div class="card-header">
        <h3><i class="fas fa-list me-2"></i>System Activity Logs</h3>
    </div>
    <div class="card-body">
        <div class="table-responsive">
            <table class="table table-striped" id="auditTable">
                <thead>
                    <tr>
                        <th><i class="fas fa-hashtag me-1"></i> ID</th>
                        <th><i class="fas fa-tasks me-1"></i> Action</th>
                        <th><i class="fas fa-tag me-1"></i> Entity Type</th>
                        <th><i class="fas fa-info-circle me-1"></i> Details</th>
                        <th><i class="fas fa-user me-1"></i> User</th>
                        <th><i class="fas fa-clock me-1"></i> Timestamp</th>
                    </tr>
                </thead>
                <tbody>
                    {% for log in logs %}
                    <tr class="animate__animated animate__fadeIn" style="animation-delay: {{ loop.index * 0.05 }}s;">
                        <td>{{ log.id }}</td>
                        <td>
                            {% if log.action == 'add' %}
                                <span class="badge bg-success">ADD</span>
                            {% elif log.action == 'remove' %}
                                <span class="badge bg-danger">REMOVE</span>
                            {% elif log.action == 'login' %}
                                <span class="badge bg-primary">LOGIN</span>
                            {% elif log.action == 'logout' %}
                                <span class="badge bg-warning">LOGOUT</span>
                            {% else %}
                                <span class="badge bg-secondary">{{ log.action|upper }}</span>
                            {% endif %}
                        </td>
                        <td>{{ log.entity_type|capitalize }}</td>
                        <td>{{ log.details }}</td>
                        <td>{{ log.user.username if log.user else 'System' }}</td>
                        <td>{{ log.timestamp.strftime('%Y-%m-%d %H:%M:%S') }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>

<script>
    // Add animation to new logs
    document.addEventListener('DOMContentLoaded', function() {
        // Highlight newest logs
        const rows = document.querySelectorAll('#auditTable tbody tr');
        if (rows.length > 0) {
            rows[0].classList.add('table-primary');
        }
        
        // Refresh logs every 30 seconds
        setInterval(function() {
            fetch('/api/audit_logs')
                .then(response => response.json())
                .then(data => {
                    const tbody = document.querySelector('#auditTable tbody');
                    // Check if we have new logs
                    if (tbody.children.length > 0) {
                        const firstLogId = parseInt(tbody.children[0].children[0].textContent);
                        const newLogs = data.filter(log => log.id > firstLogId);
                        
                        if (newLogs.length > 0) {
                            // Add new logs at the top
                            newLogs.reverse().forEach(log => {
                                const tr = document.createElement('tr');
                                tr.className = 'animate__animated animate__fadeIn table-primary';
                                
                                // ID cell
                                let td = document.createElement('td');
                                td.textContent = log.id;
                                tr.appendChild(td);
                                
                                // Action cell
                                td = document.createElement('td');
                                const badge = document.createElement('span');
                                badge.className = 'badge';
                                
                                if (log.action === 'add') {
                                    badge.className += ' bg-success';
                                    badge.textContent = 'ADD';
                                } else if (log.action === 'remove') {
                                    badge.className += ' bg-danger';
                                    badge.textContent = 'REMOVE';
                                } else if (log.action === 'login') {
                                    badge.className += ' bg-primary';
                                    badge.textContent = 'LOGIN';
                                } else if (log.action === 'logout') {
                                    badge.className += ' bg-warning';
                                    badge.textContent = 'LOGOUT';
                                } else {
                                    badge.className += ' bg-secondary';
                                    badge.textContent = log.action.toUpperCase();
                                }
                                
                                td.appendChild(badge);
                                tr.appendChild(td);
                                
                                // Entity type cell
                                td = document.createElement('td');
                                td.textContent = log.entity_type.charAt(0).toUpperCase() + log.entity_type.slice(1);
                                tr.appendChild(td);
                                
                                // Details cell
                                td = document.createElement('td');
                                td.textContent = log.details;
                                tr.appendChild(td);
                                
                                // User cell
                                td = document.createElement('td');
                                td.textContent = log.user;
                                tr.appendChild(td);
                                
                                // Timestamp cell
                                td = document.createElement('td');
                                td.textContent = log.timestamp;
                                tr.appendChild(td);
                                
                                tbody.insertBefore(tr, tbody.firstChild);
                                
                                // Remove highlight from previous new logs
                                setTimeout(() => {
                                    const highlightedRows = document.querySelectorAll('.table-primary');
                                    highlightedRows.forEach(row => {
                                        if (row !== tr) {
                                            row.classList.remove('table-primary');
                                        }
                                    });
                                }, 5000);
                            });
                        }
                    }
                });
        }, 30000);
    });
</script>
{% endblock %}''')
    
    # Base template
    with open('templates/base.html', 'w') as f:
        f.write('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hostel Management System</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Raleway:wght@300;400;500;600;700;800&family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-color: #3498db;
            --secondary-color: #2c3e50;
            --accent-color: #e74c3c;
            --light-color: #ecf0f1;
            --dark-color: #2c3e50;
        }
        
        body {
            font-family: 'Roboto', sans-serif;
            background-color: #f8f9fa;
            color: var(--dark-color);
        }
        
        h1, h2, h3, h4, h5, h6, .navbar-brand, .nav-link, .btn {
            font-family: 'Raleway', sans-serif;
            font-weight: 700;
        }
        
        .navbar {
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color)) !important;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .navbar-brand {
            font-weight: 700;
            letter-spacing: 1px;
        }
        
        .card {
            border: none;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.15);
        }
        
        .card-header {
            background: linear-gradient(135deg, var(--primary-color), #2980b9);
            color: white;
            border-radius: 10px 10px 0 0 !important;
            padding: 15px 20px;
        }
        
        .btn-primary {
            background-color: var(--primary-color);
            border-color: var(--primary-color);
            transition: all 0.3s ease;
        }
        
        .btn-primary:hover {
            background-color: #2980b9;
            border-color: #2980b9;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        
        .table {
            border-collapse: separate;
            border-spacing: 0;
        }
        
        .table th {
            background-color: var(--primary-color);
            color: white;
            border: none;
        }
        
        .table tr:nth-child(even) {
            background-color: rgba(52, 152, 219, 0.05);
        }
        
        .table tr:hover {
            background-color: rgba(52, 152, 219, 0.1);
        }
        
        .alert {
            border-radius: 8px;
            animation: fadeInDown 0.5s ease;
        }
        
        @keyframes fadeInDown {
            from {
                opacity: 0;
                transform: translateY(-20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .nav-link {
            position: relative;
            margin: 0 5px;
            transition: color 0.3s ease;
        }
        
        .nav-link:after {
            content: '';
            position: absolute;
            width: 0;
            height: 2px;
            bottom: 0;
            left: 0;
            background-color: white;
            transition: width 0.3s ease;
        }
        
        .nav-link:hover:after {
            width: 100%;
        }
        
        .icon-stat {
            font-size: 2.5rem;
            margin-bottom: 15px;
            color: var(--primary-color);
        }
        
        .stat-card {
            text-align: center;
            padding: 20px;
        }
        
        .stat-value {
            font-size: 1.8rem;
            font-weight: bold;
            margin: 10px 0;
            color: var(--dark-color);
        }
        
        .stat-label {
            font-size: 1rem;
            color: #7f8c8d;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand animate__animated animate__fadeIn" href="{{ url_for('index') }}">
                <i class="fas fa-hotel me-2"></i> KnK HOSTEL Management
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    {% if current_user.is_authenticated %}
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('dashboard') }}">
                                <i class="fas fa-tachometer-alt me-1"></i> Dashboard
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('beds') }}">
                                <i class="fas fa-bed me-1"></i> Beds Management
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('add_student') }}">
                                <i class="fas fa-user-plus me-1"></i> Add Student
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('add_room') }}">
                                <i class="fas fa-door-open me-1"></i> Add Room
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('audit_logs') }}">
                                <i class="fas fa-history me-1"></i> Audit Logs
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('logout') }}">
                                <i class="fas fa-sign-out-alt me-1"></i> Logout
                            </a>
                        </li>
                    {% else %}
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('login') }}">
                                <i class="fas fa-sign-in-alt me-1"></i> Login
                            </a>
                        </li>
                    {% endif %}
                </ul>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="alert alert-info animate__animated animate__fadeInDown">
                        <i class="fas fa-info-circle me-2"></i> {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>

    <footer class="bg-dark text-white mt-5 py-3">
        <div class="container text-center">
            <p class="mb-0">(c) 2025 KnK HOSTEL Management System</p>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
        // Add animation to cards when they come into view
        $(document).ready(function() {
            // Animate elements when they come into view
            function animateOnScroll() {
                $('.card').each(function() {
                    var bottom_of_object = $(this).offset().top + $(this).outerHeight();
                    var bottom_of_window = $(window).scrollTop() + $(window).height();
                    if (bottom_of_window > bottom_of_object) {
                        $(this).addClass('animate__animated animate__fadeInUp');
                    }
                });
            }
            
            // Run on page load
            animateOnScroll();
            
            // Run on scroll
            $(window).scroll(function() {
                animateOnScroll();
            });
        });
    </script>
</body>
</html>''')
    
    # Index template
    with open('templates/index.html', 'w') as f:
        f.write('''{% extends "base.html" %}
{% block content %}
<style>
    .hero-section {
        position: relative;
        height: 500px;
        overflow: hidden;
        border-radius: 15px;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    
    .hero-image {
        width: 100%;
        height: 100%;
        object-fit: cover;
        filter: brightness(0.7);
        transition: transform 10s ease;
    }
    
    .hero-section:hover .hero-image {
        transform: scale(1.05);
    }
    
    .hero-content {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        color: white;
        text-align: center;
        padding: 2rem;
        z-index: 1;
    }
    
    .hero-content h1 {
        font-size: 3.5rem;
        font-weight: 700;
        margin-bottom: 1rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        animation: fadeInDown 1s ease;
    }
    
    .hero-content p {
        font-size: 1.2rem;
        max-width: 700px;
        margin-bottom: 2rem;
        text-shadow: 1px 1px 3px rgba(0,0,0,0.5);
        animation: fadeInUp 1s ease;
    }
    
    .about-section {
        background-color: white;
        border-radius: 15px;
        padding: 2rem;
        margin-bottom: 2rem;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        animation: fadeIn 1s ease;
    }
    
    .about-card {
        height: 100%;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .about-card:hover {
        transform: translateY(-10px);
        box-shadow: 0 15px 30px rgba(0,0,0,0.15);
    }
    
    .about-icon {
        font-size: 3rem;
        color: var(--primary-color);
        margin-bottom: 1rem;
    }
    
    @keyframes fadeInDown {
        from {
            opacity: 0;
            transform: translateY(-30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes fadeIn {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }
</style>

<!-- Hero Section with Building Image -->
<div class="hero-section animate__animated animate__fadeIn">
    <img src="https://images.unsplash.com/photo-1555854877-bab0e564b8d5?ixlib=rb-4.0.3&ixid=MnwxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8&auto=format&fit=crop&w=1740&q=80" alt="Hostel Building" class="hero-image">
    <div class="hero-content">
        <h1 class="display-4">Welcome to NK HOSTEL</h1>
        <p class="lead">Your premier hostel management solution for comfortable and affordable student accommodation</p>
        {% if not current_user.is_authenticated %}
            <a href="{{ url_for('login') }}" class="btn btn-primary btn-lg animate__animated animate__pulse animate__infinite animate__slower">
                <i class="fas fa-sign-in-alt me-2"></i> Login to System
            </a>
        {% else %}
            <a href="{{ url_for('dashboard') }}" class="btn btn-primary btn-lg">
                <i class="fas fa-tachometer-alt me-2"></i> Go to Dashboard
            </a>
        {% endif %}
    </div>
</div>

<!-- About Us Section -->
<div class="about-section">
    <h2 class="text-center mb-4"><i class="fas fa-info-circle me-2"></i>About Us</h2>
    <div class="row">
        <div class="col-md-4 mb-4">
            <div class="card about-card">
                <div class="card-body text-center">
                    <i class="fas fa-building about-icon"></i>
                    <h3>Our Facilities</h3>
                    <p>KnK HOSTEL offers modern, well-maintained accommodation with all the amenities students need for a comfortable stay. Our facilities include high-speed internet, study areas, and common rooms for socializing.</p>
                </div>
            </div>
        </div>
        <div class="col-md-4 mb-4">
            <div class="card about-card">
                <div class="card-body text-center">
                    <i class="fas fa-users about-icon"></i>
                    <h3>Our Mission</h3>
                    <p>We are committed to providing safe, affordable, and comfortable housing for students. Our mission is to create a supportive community where students can thrive academically and personally.</p>
                </div>
            </div>
        </div>
        <div class="col-md-4 mb-4">
            <div class="card about-card">
                <div class="card-body text-center">
                    <i class="fas fa-shield-alt about-icon"></i>
                    <h3>Our Values</h3>
                    <p>We prioritize safety, respect, and inclusivity. Our management system ensures efficient operations, transparent communication, and responsive service to meet the needs of our residents.</p>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Features Section -->
<div class="row mb-4">
    <div class="col-md-12">
        <div class="card">
            <div class="card-header text-white">
                <h3 class="mb-0"><i class="fas fa-star me-2"></i>Why Choose Our Hostel Management System?</h3>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <ul class="list-group list-group-flush">
                            <li class="list-group-item"><i class="fas fa-check-circle text-success me-2"></i> Efficient room and bed allocation</li>
                            <li class="list-group-item"><i class="fas fa-check-circle text-success me-2"></i> Real-time occupancy tracking</li>
                            <li class="list-group-item"><i class="fas fa-check-circle text-success me-2"></i> Comprehensive student management</li>
                        </ul>
                    </div>
                    <div class="col-md-6">
                        <ul class="list-group list-group-flush">
                            <li class="list-group-item"><i class="fas fa-check-circle text-success me-2"></i> Detailed audit logging for all activities</li>
                            <li class="list-group-item"><i class="fas fa-check-circle text-success me-2"></i> User-friendly interface for administrators</li>
                            <li class="list-group-item"><i class="fas fa-check-circle text-success me-2"></i> Secure authentication system</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}''')
    
    # Login template
    with open('templates/login.html', 'w') as f:
        f.write('''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h3 class="text-center">Login</h3>
            </div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label for="username" class="form-label">Username</label>
                        <input type="text" class="form-control" id="username" name="username" required>
                    </div>
                    <div class="mb-3">
                        <label for="password" class="form-label">Password</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                    </div>
                    <div class="text-center">
                        <button type="submit" class="btn btn-primary">Login</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}''')
    
    # Dashboard template
    with open('templates/dashboard.html', 'w') as f:
        f.write('''{% extends "base.html" %}
{% block content %}
<div class="row mb-4">
    <div class="col-md-12">
        <h2 class="text-center mb-4 animate__animated animate__fadeIn"><i class="fas fa-tachometer-alt me-2"></i> Hostel Dashboard</h2>
    </div>
</div>

<!-- Stats Cards -->
<div class="row mb-4">
    <div class="col-md-3">
        <div class="card stat-card animate__animated animate__fadeInUp">
            <div class="card-body">
                <i class="fas fa-door-open icon-stat"></i>
                <div class="stat-value">{{ rooms|length }}</div>
                <div class="stat-label">Total Rooms</div>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card animate__animated animate__fadeInUp" style="animation-delay: 0.1s;">
            <div class="card-body">
                <i class="fas fa-users icon-stat"></i>
                <div class="stat-value">{{ students|length }}</div>
                <div class="stat-label">Total Students</div>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card animate__animated animate__fadeInUp" style="animation-delay: 0.2s;">
            <div class="card-body">
                <i class="fas fa-bed icon-stat"></i>
                <div class="stat-value">{{ occupied_beds }}</div>
                <div class="stat-label">Beds Occupied</div>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card animate__animated animate__fadeInUp" style="animation-delay: 0.3s;">
            <div class="card-body">
                <i class="fas fa-bed icon-stat"></i>
                <div class="stat-value">{{ available_beds }}</div>
                <div class="stat-label">Beds Available</div>
            </div>
        </div>
    </div>
</div>

<div class="row">
    <div class="col-md-6">
        <div class="card mb-4 animate__animated animate__fadeInLeft">
            <div class="card-header">
                <h3><i class="fas fa-door-open me-2"></i>Rooms Status</h3>
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>Room Number</th>
                                <th>Capacity</th>
                                <th>Occupied</th>
                                <th>Available</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for room in rooms %}
                            <tr>
                                <td><i class="fas fa-door-closed me-1"></i> {{ room.room_number }}</td>
                                <td><i class="fas fa-bed me-1"></i> {{ room.capacity }}</td>
                                <td><i class="fas fa-user me-1"></i> {{ room.occupied }}</td>
                                <td><i class="fas fa-check-circle me-1"></i> {{ room.capacity - room.occupied }}</td>
                                <td>
                                    {% if room.capacity == room.occupied %}
                                        <span class="badge bg-danger">Full</span>
                                    {% elif room.occupied == 0 %}
                                        <span class="badge bg-success">Empty</span>
                                    {% else %}
                                        <span class="badge bg-warning">Partial</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                <div class="mt-3">
                    <a href="{{ url_for('add_room') }}" class="btn btn-primary">
                        <i class="fas fa-plus-circle me-1"></i> Add New Room
                    </a>
                </div>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card mb-4 animate__animated animate__fadeInRight">
            <div class="card-header">
                <h3><i class="fas fa-users me-2"></i>Students List</h3>
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Student ID</th>
                                <th>Room</th>
                                <th>Check-in Date</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for student in students %}
                            <tr>
                                <td><i class="fas fa-user-graduate me-1"></i> {{ student.name }}</td>
                                <td><i class="fas fa-id-card me-1"></i> {{ student.student_id }}</td>
                                <td><i class="fas fa-door-open me-1"></i> {{ student.room.room_number }}</td>
                                <td><i class="fas fa-calendar-alt me-1"></i> {{ student.check_in_date.strftime('%Y-%m-%d') }}</td>
                                <td>
                                    <form method="POST" action="{{ url_for('remove_student', student_id=student.id) }}" onsubmit="return confirm('Are you sure you want to remove this student?');">
                                        <button type="submit" class="btn btn-sm btn-danger">
                                            <i class="fas fa-user-minus"></i>
                                        </button>
                                    </form>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                <div class="mt-3">
                    <a href="{{ url_for('add_student') }}" class="btn btn-primary">
                        <i class="fas fa-user-plus me-1"></i> Add New Student
                    </a>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}''')
    
    # Add Student template
    with open('templates/add_student.html', 'w') as f:
        f.write('''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h3 class="text-center">Add New Student</h3>
            </div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label for="name" class="form-label">Full Name</label>
                        <input type="text" class="form-control" id="name" name="name" required>
                    </div>
                    <div class="mb-3">
                        <label for="student_id" class="form-label">Student ID</label>
                        <input type="text" class="form-control" id="student_id" name="student_id" required>
                    </div>
                    <div class="mb-3">
                        <label for="room_id" class="form-label">Room</label>
                        <select class="form-control" id="room_id" name="room_id" required>
                            <option value="">Select a room</option>
                            {% for room in rooms %}
                                {% if room.occupied < room.capacity %}
                                    <option value="{{ room.id }}">Room {{ room.room_number }} ({{ room.capacity - room.occupied }} available)</option>
                                {% endif %}
                            {% endfor %}
                        </select>
                    </div>
                    <div class="text-center">
                        <button type="submit" class="btn btn-primary">Add Student</button>
                        <a href="{{ url_for('dashboard') }}" class="btn btn-secondary">Cancel</a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}''')
    
    # Add Room template
    with open('templates/add_room.html', 'w') as f:
        f.write('''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h3 class="text-center">Add New Room</h3>
            </div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label for="room_number" class="form-label">Room Number</label>
                        <input type="text" class="form-control" id="room_number" name="room_number" required>
                    </div>
                    <div class="mb-3">
                        <label for="capacity" class="form-label">Capacity</label>
                        <input type="number" class="form-control" id="capacity" name="capacity" min="1" max="10" required>
                    </div>
                    <div class="text-center">
                        <button type="submit" class="btn btn-primary">Add Room</button>
                        <a href="{{ url_for('dashboard') }}" class="btn btn-secondary">Cancel</a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}''')

if __name__ == '__main__':
    # Create templates and initialize database
    create_templates()
    initialize_db()
    
    # Run the application
    app.run(debug=True)
