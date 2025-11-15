import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './CurrentLog.css';

function CurrentLog() {
  const [data, setData] = useState([]);
  const [filteredData, setFilteredData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [entryDateFilter, setEntryDateFilter] = useState('');

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api/current-logs';

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
      setError(err.response?.data?.message || err.message || 'Failed to fetch current logs');
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
        log.timestamp && new Date(log.timestamp).toDateString() === selectedDate
      );
    }

    setFilteredData(filtered);
  }, [entryDateFilter, data]);

  const handleRefetch = () => {
    fetchData();
  };

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
        <h2>Current Logs</h2>
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
                <th>Number Plate</th>
                <th>Timestamp</th>
                <th>Slots</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredData.map((log, index) => (
                <tr key={log._id || index}>
                  <td>{log.number_plate || 'N/A'}</td>
                  <td>{log.timestamp ? new Date(log.timestamp).toLocaleString() : 'N/A'}</td>
                  <td>{log.slots ? `${log.slots} ` : 'N/A'}</td>
                  <td>
                    <span className={
                      log.status?.toLowerCase() === 'authorized' ? 'status-authorized' :
                      log.status?.toLowerCase() === 'unauthorized' ? 'status-unauthorized' : ''
                    }>
                      {log.status || 'Unauthozired'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default CurrentLog;