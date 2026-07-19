-- PostgreSQL Database Schema for Dental Clinic Voice Assistant

-- Table to store patient details and medical context/anxieties
CREATE TABLE IF NOT EXISTS patients (
    phone_number VARCHAR(32) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    anxieties TEXT,
    history TEXT,
    last_called TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table to store scheduled appointments
CREATE TABLE IF NOT EXISTS appointments (
    id BIGSERIAL PRIMARY KEY,
    patient_name VARCHAR(255) NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    requested_date DATE NOT NULL,
    requested_time TIME NOT NULL,
    status VARCHAR(32) DEFAULT 'scheduled', -- 'scheduled', 'cancelled', 'completed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(phone_number) REFERENCES patients(phone_number)
);

-- Prevent concurrent double-booking for active scheduled slots.
CREATE UNIQUE INDEX IF NOT EXISTS uq_appointments_scheduled_slot
ON appointments (requested_date, requested_time)
WHERE status = 'scheduled';

-- Table to store call logs and operational metrics for the dashboard
CREATE TABLE IF NOT EXISTS call_logs (
    id BIGSERIAL PRIMARY KEY,
    caller_phone VARCHAR(32),
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    transcript TEXT,
    sentiment VARCHAR(64),
    duration_seconds INTEGER
);
