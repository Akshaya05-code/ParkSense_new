import React from 'react';
import { Link } from 'react-router-dom';
import './Dashboard.css';

function Dashboard() {
  return (
    <div className="dashboard-container">
      <header className="header">
        <h1>ParkSense Dashboard</h1>
        <p>Manage your parking system with ease</p>
      </header>
      <section className="hero">
        <div className="hero-content">
          <h2>Welcome to ParkSense</h2>
          <p>Access real-time parking data, review logs, and manage slots efficiently.</p>
          <div className="hero-actions">
            <Link to="/current-logs" className="action-button current-logs">Current Logs</Link>
            <Link to="/previous-logs" className="action-button previous-logs">Previous Logs</Link>
            <Link to="/slot-details" className="action-button slot-details">Slot Details</Link>
            <Link to="/rover-details" className="action-button rover-details">Rover Details</Link>
          </div>
        </div>
      </section>
      <section className="features">
        <h2>Features</h2>
        <div className="features-grid">
          <div className="feature-card">
            <h3>Real-Time Monitoring</h3>
            <p>Track parking slot status as it happens.</p>
          </div>
          <div className="feature-card">
            <h3>Historical Data</h3>
            <p>Review past parking logs for insights.</p>
          </div>
          <div className="feature-card">
            <h3>Slot Management</h3>
            <p>Manage and view slot details efficiently.</p>
          </div>
        </div>
      </section>
      <footer className="footer">
        <p>© 2025 ParkSense. All rights reserved.</p>
      </footer>
    </div>
  );
}

export default Dashboard;