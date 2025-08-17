#KnK HOSTEL Management System

A comprehensive hostel management system that allows administrators to manage rooms, beds, and students with a beautiful user interface and complete audit logging.

## Features

- **User Authentication**: Secure login system for administrators
- **Dashboard**: Overview of hostel statistics and occupancy
- **Beds Management**: Track and manage bed availability across rooms
- **Student Management**: Add and remove students with room assignments
- **Audit Logging**: Complete history of all system activities
- **Modern UI**: Responsive design with animations and icons

## Database Implementation

This system implements full CRUD operations:
- **Create**: Add new rooms and students
- **Read**: View dashboard statistics, room status, and student information
- **Update**: Modify room capacity and occupancy
- **Delete**: Remove students from the system

## Setup Instructions

1. Install Python (3.8 or higher)
2. Install dependencies:
```
pip install -r requirements.txt
```

3. Run the application:
```
python app.py
```

4. Access the system at: http://localhost:5000

## Default Login

- Username: `admin`
- Password: `admin123`

## Project Structure

- `app.py`: Main application file (contains all code)
- `requirements.txt`: Python dependencies
- Templates are generated automatically when the application runs

## Technical Details

- **Framework**: Flask
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: Bootstrap, Font Awesome, Animate.css
- **Fonts**: Raleway and Roboto

## Project Information

- **Created for**: Database Management Course Project
- **Submission Date**: 10/03/2025
