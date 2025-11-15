import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './Slots.css';

function Slots() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await axios.get('http://localhost:5000/api/slots');
        setData(res.data);
        setLoading(false);
      } catch (err) {
        setError('Failed to fetch slots details');
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="container">
      <h2>Slots Details</h2>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Slot ID</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.map((slot) => (
              <tr key={slot._id}>
                <td>{slot.slot_id}</td>
                <td>
                  <span className={`status-badge ${slot.status}`}>
                    {slot.status.charAt(0).toUpperCase() + slot.status.slice(1)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Slots;