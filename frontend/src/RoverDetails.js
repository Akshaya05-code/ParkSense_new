import React, { useEffect, useState } from 'react';
import './RoverDetails.css';

function RoverDetails() {
  const [roverLogs, setRoverLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:5000/api/rover-details')
      .then(res => res.json())
      .then(data => {
        setRoverLogs(data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching rover data:', err);
        setLoading(false);
      });
  }, []);

  return (
    <div className="rover-details-container">
      <h1 className="rover-title">Rover Activity Logs</h1>
      {loading ? (
        <p>Loading rover data...</p>
      ) : roverLogs.length === 0 ? (
        <p>No rover data available.</p>
      ) : (
        <div className="rover-cards">
          {roverLogs.map((log, index) => (
            <div key={index} className="rover-card">
              <h2>{log.rover_id || 'Rover-1'}</h2>
              <p><strong>Timestamp:</strong> {new Date(log.timestamp).toLocaleString()}</p>

              <div className="rover-subsection">
                <h3>GPS</h3>
                <p>Lat: {log.gps?.latitude ?? 'N/A'}, Lng: {log.gps?.longitude ?? 'N/A'}, Alt: {log.gps?.altitude ?? 'N/A'}</p>
              </div>

              <div className="rover-subsection">
                 <h3>Battery</h3>
                <p>Voltage: {log.battery?.voltage ?? 'N/A'}V, Current: {log.battery?.current ?? 'N/A'}A, Level: {log.battery?.level ?? 'N/A'}%</p>
              </div>

              <div className="rover-subsection">
                <h3>Status</h3>
                <p>Mode: {log.mode}, Armed: {log.armed ? 'Yes' : 'No'}, Heading: {log.heading}, System: {log.system_status}</p>
              </div>

              <div className="rover-subsection">
                <h3>Velocity</h3>
                <p>X: {log.velocity?.x ?? 0}, Y: {log.velocity?.y ?? 0}, Z: {log.velocity?.z ?? 0}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default RoverDetails;
