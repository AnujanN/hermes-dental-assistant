import React, { useState, useEffect, useRef } from "react";

// API Base URL (assumes FastAPI is running on port 8000)
const API_BASE = "http://localhost:8000";

function App() {
  // Metrics and appointments state
  const [metrics, setMetrics] = useState({
    total_calls: 0,
    active_appointments: 0,
    avg_duration_seconds: 0,
    latest_calls: [],
  });
  const [appointments, setAppointments] = useState([]);
  const [loadingMetrics, setLoadingMetrics] = useState(true);

  // Call simulator state
  const [isCallActive, setIsCallActive] = useState(false);
  const [callerPhone, setCallerPhone] = useState("+1 (555) 902-1324");
  const [callerName, setCallerName] = useState("Jane Doe");
  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [sessionSid, setSessionSid] = useState("");
  const [isSendingMessage, setIsSendingMessage] = useState(false);

  // Manual booking form state
  const [bookingForm, setBookingForm] = useState({
    patient_name: "",
    phone_number: "",
    date: "",
    time: "09:00",
  });
  const [bookingStatus, setBookingStatus] = useState("");

  // UI Popups/Modals
  const [selectedCall, setSelectedCall] = useState(null);

  const chatEndRef = useRef(null);

  // Fetch metrics & appointments
  const fetchData = async () => {
    try {
      const resMetrics = await fetch(`${API_BASE}/api/metrics`);
      if (resMetrics.ok) {
        const data = await resMetrics.json();
        setMetrics(data);
      }

      const resApps = await fetch(`${API_BASE}/api/appointments`);
      if (resApps.ok) {
        const data = await resApps.json();
        setAppointments(data);
      }
    } catch (err) {
      console.error("Error fetching data from backend:", err);
    } finally {
      setLoadingMetrics(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Poll updates every 4 seconds
    const interval = setInterval(fetchData, 4000);
    return () => clearInterval(interval);
  }, []);

  // Scroll chat history to bottom
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatHistory]);

  // Simulator: Toggle Call Connection
  const handleToggleCall = () => {
    if (isCallActive) {
      // Hang up
      setIsCallActive(false);
      setChatHistory((prev) => [
        ...prev,
        { role: "system", text: "--- Call Ended ---" },
      ]);
      fetchData(); // Refresh logs immediately
    } else {
      // Dial
      const sid = "sim-" + Math.random().toString(36).substr(2, 9);
      setSessionSid(sid);
      setIsCallActive(true);
      setChatHistory([
        { role: "system", text: `Incoming call started from ${callerPhone}...` },
        { role: "agent", text: `Hello, this is Alex from Radiant Smile Dental. How can I help you today?` },
      ]);
    }
  };

  // Simulator: Send Text Message
  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatInput.trim() || !isCallActive || isSendingMessage) return;

    const userText = chatInput.trim();
    setChatInput("");
    setChatHistory((prev) => [...prev, { role: "user", text: userText }]);
    setIsSendingMessage(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: userText,
          phone_number: callerPhone,
          session_id: sessionSid,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setChatHistory((prev) => [
          ...prev,
          { role: "agent", text: data.response },
        ]);
      } else {
        setChatHistory((prev) => [
          ...prev,
          { role: "system", text: "Error: Failed to fetch reply from gateway." },
        ]);
      }
    } catch (err) {
      setChatHistory((prev) => [
        ...prev,
        { role: "system", text: "Connection error. Ensure backend is running." },
      ]);
    } finally {
      setIsSendingMessage(false);
    }
  };

  // Admin: Submit Manual Booking
  const handleManualBooking = async (e) => {
    e.preventDefault();
    if (!bookingForm.patient_name || !bookingForm.phone_number || !bookingForm.date) {
      setBookingStatus("Please fill in all fields.");
      return;
    }

    setBookingStatus("Submitting...");
    try {
      const response = await fetch(`${API_BASE}/api/appointments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bookingForm),
      });
      const data = await response.json();

      if (data.success) {
        setBookingStatus("Success! Appointment saved.");
        setBookingForm({ patient_name: "", phone_number: "", date: "", time: "09:00" });
        fetchData();
      } else {
        setBookingStatus(data.message || "Failed to book slot.");
      }
    } catch (err) {
      setBookingStatus("Error contacting database.");
    }
  };

  return (
    <div className="app-container">
      {/* Header Bar */}
      <header>
        <div className="logo-section">
          <h1>Radiant Smile Assistant</h1>
          <p>Hermes-3 Voice Receptionist Administrative Console</p>
        </div>
        <div className="system-status">
          <div className="status-indicator"></div>
          <span>ALEX BOT: ONLINE</span>
        </div>
      </header>

      {/* Analytics Cards Row */}
      <div className="metrics-row">
        <div className="metric-card">
          <div className="metric-icon">📞</div>
          <div className="metric-info">
            <h3>Total Phone Calls</h3>
            <p>{metrics.total_calls}</p>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-icon">📅</div>
          <div className="metric-info">
            <h3>Booked Appointments</h3>
            <p>{metrics.active_appointments}</p>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-icon">⏳</div>
          <div className="metric-info">
            <h3>Avg Conversation</h3>
            <p>{metrics.avg_duration_seconds}s</p>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-icon">🤖</div>
          <div className="metric-info">
            <h3>Hermes Inference</h3>
            <p>Nous 8B (OpenRouter)</p>
          </div>
        </div>
      </div>

      {/* Main Grid */}
      <div className="dashboard-grid">
        
        {/* Column 1: Call Logging Feed */}
        <div className="panel">
          <div className="panel-title">
            <span>Call Analytics logs</span>
            <span style={{ fontSize: "0.8rem", color: "var(--accent)" }}>Recent activity</span>
          </div>
          <div className="logs-list">
            {metrics.latest_calls.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>No call history records found.</p>
            ) : (
              metrics.latest_calls.map((log) => (
                <div key={log.id} className="log-item" onClick={() => setSelectedCall(log)}>
                  <div className="log-header">
                    <span className="log-phone">{log.caller_phone}</span>
                    <span className="log-time">
                      {log.start_time ? log.start_time.split(" ")[1] || log.start_time : "Just now"}
                    </span>
                  </div>
                  <div className="log-snippet">
                    {log.transcript ? log.transcript.substring(0, 70) + "..." : "Call connected..."}
                  </div>
                  <div className="log-footer">
                    <span className="log-duration">Duration: {log.duration_seconds || 0}s</span>
                    <span className="log-sentiment">{log.sentiment || "Neutral"}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Column 2: Digital Calendar View & Admin Booking Form */}
        <div className="panel">
          <div className="panel-title">
            <span>Clinic Booking Ledger</span>
            <span style={{ fontSize: "0.8rem", color: "var(--accent)" }}>SQLite Database</span>
          </div>
          
          <div className="calendar-list">
            {appointments.length === 0 ? (
              <p style={{ padding: "16px", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                No active appointments booked in the system.
              </p>
            ) : (
              <table className="calendar-table">
                <thead>
                  <tr>
                    <th>Patient Name</th>
                    <th>Date</th>
                    <th>Time</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {appointments.map((app) => (
                    <tr key={app.id}>
                      <td><strong>{app.patient_name}</strong></td>
                      <td>{app.requested_date}</td>
                      <td>{app.requested_time}</td>
                      <td>
                        <span className="status-badge status-scheduled">
                          {app.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <form className="manual-booking-form" onSubmit={handleManualBooking}>
            <div className="form-title">Manual Schedule Override</div>
            <div className="form-row">
              <input
                type="text"
                className="form-input"
                placeholder="Patient Name"
                value={bookingForm.patient_name}
                onChange={(e) => setBookingForm({ ...bookingForm, patient_name: e.target.value })}
              />
              <input
                type="text"
                className="form-input"
                placeholder="Phone Number"
                value={bookingForm.phone_number}
                onChange={(e) => setBookingForm({ ...bookingForm, phone_number: e.target.value })}
              />
            </div>
            <div className="form-row">
              <input
                type="date"
                className="form-input"
                value={bookingForm.date}
                onChange={(e) => setBookingForm({ ...bookingForm, date: e.target.value })}
              />
              <select
                className="form-input"
                value={bookingForm.time}
                onChange={(e) => setBookingForm({ ...bookingForm, time: e.target.value })}
              >
                <option value="08:00">08:00 AM</option>
                <option value="09:00">09:00 AM</option>
                <option value="10:00">10:00 AM</option>
                <option value="11:00">11:00 AM</option>
                <option value="12:00">12:00 PM</option>
                <option value="13:00">01:00 PM</option>
                <option value="14:00">02:00 PM</option>
                <option value="15:00">03:00 PM</option>
                <option value="16:00">04:00 PM</option>
              </select>
            </div>
            <button type="submit" className="form-btn">Schedule Appointment</button>
            {bookingStatus && (
              <div style={{ fontSize: "0.8rem", textAlign: "center", color: bookingStatus.includes("Success") ? "var(--accent-light)" : "var(--warning)" }}>
                {bookingStatus}
              </div>
            )}
          </form>
        </div>

        {/* Column 3: Interactive Sandbox Voice/Text Simulator */}
        <div className="panel simulator-panel">
          <div className="panel-title">
            <span>Live Agent Simulator</span>
            {isCallActive && <span className="status-indicator"></span>}
          </div>

          <div className="call-config">
            <div className="config-row">
              <span className="config-label">Caller Phone:</span>
              <input
                type="text"
                className="config-input"
                value={callerPhone}
                disabled={isCallActive}
                onChange={(e) => setCallerPhone(e.target.value)}
              />
            </div>
            <button
              onClick={handleToggleCall}
              className={`call-btn ${isCallActive ? "active-call" : ""}`}
            >
              {isCallActive ? "Hang Up Connection" : "Initiate Test Call"}
            </button>
          </div>

          <div className="chat-history">
            {chatHistory.length === 0 ? (
              <div style={{ textAlign: "center", padding: "40px 10px", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                Configure Caller Phone above and click "Initiate Test Call" to start chatting with Alex.
              </div>
            ) : (
              chatHistory.map((msg, index) => (
                <div
                  key={index}
                  className={`chat-message ${
                    msg.role === "user"
                      ? "message-user"
                      : msg.role === "agent"
                      ? "message-agent"
                      : "message-system"
                  }`}
                >
                  {msg.text}
                </div>
              ))
            )}
            {isSendingMessage && (
              <div className="chat-message message-agent" style={{ opacity: 0.6 }}>
                Alex is thinking...
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form className="chat-input-form" onSubmit={handleSendMessage}>
            <input
              type="text"
              className="chat-input"
              placeholder={isCallActive ? "Type what caller says..." : "Dial call to speak..."}
              disabled={!isCallActive || isSendingMessage}
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
            />
            <button
              type="submit"
              className="chat-submit-btn"
              disabled={!isCallActive || isSendingMessage || !chatInput.trim()}
            >
              Send
            </button>
          </form>
        </div>

      </div>

      {/* Detailed Transcript View Modal */}
      {selectedCall && (
        <div style={{
          position: "fixed",
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: "rgba(0,0,0,0.8)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 1000,
          padding: "20px"
        }} onClick={() => setSelectedCall(null)}>
          <div style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            borderRadius: "20px",
            width: "100%",
            maxWidth: "600px",
            padding: "24px",
            maxHeight: "80vh",
            display: "flex",
            flexDirection: "column"
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px", borderBottom: "1px solid var(--border)", paddingBottom: "12px" }}>
              <h3 style={{ color: "#fff" }}>Call Record Details</h3>
              <button style={{ background: "none", border: "none", color: "#fff", cursor: "pointer", fontSize: "1.2rem" }} onClick={() => setSelectedCall(null)}>×</button>
            </div>
            <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "16px" }}>
              <div><strong>Caller Number:</strong> {selectedCall.caller_phone}</div>
              <div><strong>Call Start Time:</strong> {selectedCall.start_time}</div>
              <div><strong>Duration:</strong> {selectedCall.duration_seconds || 0} seconds</div>
              <div><strong>Sentiment:</strong> {selectedCall.sentiment}</div>
            </div>
            <div style={{
              flexGrow: 1,
              overflowY: "auto",
              backgroundColor: "rgba(0,0,0,0.2)",
              padding: "16px",
              borderRadius: "12px",
              fontFamily: "monospace",
              fontSize: "0.9rem",
              lineHeight: "1.5",
              whiteSpace: "pre-wrap",
              color: "var(--text-main)"
            }}>
              {selectedCall.transcript || "No transcription generated for this session."}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
