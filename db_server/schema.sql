-- SQLite Database Schema for Dental Clinic Voice Assistant

-- Table to store patient details and medical context/anxieties
CREATE TABLE IF NOT EXISTS patients (
    phone_number TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    anxieties TEXT,
    history TEXT,
    last_called TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table to store scheduled appointments
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    requested_date TEXT NOT NULL, -- Format: YYYY-MM-DD
    requested_time TEXT NOT NULL, -- Format: HH:MM
    status TEXT DEFAULT 'scheduled', -- 'scheduled', 'cancelled', 'completed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(phone_number) REFERENCES patients(phone_number)
);

-- Prevent concurrent double-booking for active scheduled slots.
CREATE UNIQUE INDEX IF NOT EXISTS uq_appointments_scheduled_slot
ON appointments (requested_date, requested_time)
WHERE status = 'scheduled';

-- Table to store call logs and operational metrics for the dashboard
CREATE TABLE IF NOT EXISTS call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_phone TEXT,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    transcript TEXT,
    sentiment TEXT,
    duration_seconds INTEGER
);
