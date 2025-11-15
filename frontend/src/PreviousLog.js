import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './PreviousLog.css';

function PreviousLog() {
  const [data, setData] = useState([]);
  const [filteredData, setFilteredData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [entryDateFilter, setEntryDateFilter] = useState('');
  const [exitDateFilter, setExitDateFilter] = useState('');
  const [slotFilter, setSlotFilter] = useState('');

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api/previous-logs';

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(API_URL);
      if (!Array.isArray(res.data)) {
        throw new Error('Invalid data format: Expected an array');
      }
      setData(res.data);
      setFilteredData(res.data);
      setLoading(false);
    } catch (err) {
      setError(err.response?.data?.message || err.message || 'Failed to fetch previous logs');
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    let filtered = data;

    if (entryDateFilter) {
      const selectedDate = new Date(entryDateFilter).toDateString();
      filtered = filtered.filter(log =>
        log.entry_time && new Date(log.entry_time).toDateString() === selectedDate
      );
    }

    if (exitDateFilter) {
      const selectedDate = new Date(exitDateFilter).toDateString();
      filtered = filtered.filter(log =>
        log.exit_time && new Date(log.exit_time).toDateString() === selectedDate
      );
    }

    if (slotFilter) {
      filtered = filtered.filter(log => log.assigned_slot === slotFilter);
    }

    setFilteredData(filtered);
  }, [entryDateFilter, exitDateFilter, slotFilter, data]);

  const handleRefetch = () => {
    fetchData();
  };

  const uniqueSlots = [...new Set(data.map(log => log.assigned_slot).filter(slot => slot))];

  if (loading) {
    return (
      <div className="loading-container">
        <div className="spinner"></div>
        <span>Loading...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-container">
        <p>{error}</p>
        <button onClick={handleRefetch} className="retry-button">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="logs-container">
      <div className="header">
        <h2>Previous Parking Logs</h2>
        <div className="filter-container">
          <div className="filter-group">
            <label htmlFor="entryDateFilter">Entry Date:</label>
            <input
              type="date"
              id="entryDateFilter"
              value={entryDateFilter}
              onChange={(e) => setEntryDateFilter(e.target.value)}
              className="filter-input"
            />
          </div>
          <div className="filter-group">
            <label htmlFor="exitDateFilter">Exit Date:</label>
            <input
              type="date"
              id="exitDateFilter"
              value={exitDateFilter}
              onChange={(e) => setExitDateFilter(e.target.value)}
              className="filter-input"
            />
          </div>
          <div className="filter-group">
            <label htmlFor="slotFilter">Slot:</label>
            <select
              id="slotFilter"
              value={slotFilter}
              onChange={(e) => setSlotFilter(e.target.value)}
              className="filter-select"
            >
              <option value="">All Slots</option>
              {uniqueSlots.map(slot => (
                <option key={slot} value={slot}>{slot}</option>
              ))}
            </select>
          </div>
          <button onClick={handleRefetch} className="refresh-button">
            Refresh Logs
          </button>
        </div>
      </div>
      {filteredData.length === 0 ? (
        <p className="no-logs">No logs available.</p>
      ) : (
        <div className="table-container">
          <table className="logs-table">
            <thead>
              <tr>
                <th>Car Number</th>
                <th>Mobile</th>
                <th>Slot</th>
                <th>Entry Time</th>
                <th>Exit Time</th>
                <th>Status</th>
                <th>Cost (₹)</th>
              </tr>
            </thead>
            <tbody>
              {filteredData.map((log, index) => (
                <tr key={log._id || index}>
                  <td>{log.car_number || 'N/A'}</td>
                  <td>{log.mobile || 'N/A'}</td>
                  <td>{log.assigned_slot || 'N/A'}</td>
                  <td>{log.entry_time ? new Date(log.entry_time).toLocaleString() : 'N/A'}</td>
                  <td>{log.exit_time ? new Date(log.exit_time).toLocaleString() : 'N/A'}</td>
                  <td>
                    <span className={`status ${log.confirmed ? 'confirmed' : 'pending'}`}>
                      {log.confirmed ? 'Confirmed' : 'Pending'}
                    </span>
                  </td>
                  <td>{log.total_cost ? `₹${log.total_cost}` : 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default PreviousLog;