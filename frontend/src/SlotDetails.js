import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './SlotDetails.css';

function SlotDetails() {
  const [slots, setSlots] = useState([]);
  const [visitors, setVisitors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [slotsRes, visitorsRes] = await Promise.all([
          axios.get('http://localhost:5000/api/slots'),
          axios.get('http://localhost:5000/api/previous-logs')
        ]);

        console.log('Slots Data:', slotsRes.data);
        console.log('Visitors Data:', visitorsRes.data);

        const expectedSlots = Array.from({ length: 10 }, (_, i) => `A${i + 1}`);
        const slotsData = slotsRes.data;
        const paddedSlots = expectedSlots.map(slotId => {
          const slot = slotsData.find(s => s.slot_id === slotId) || { slot_id: slotId, status: 'empty' };
          return slot;
        });

        const activeVisitors = visitorsRes.data.filter(v => !v.exit_time);
        console.log('Active Visitors:', activeVisitors);

        const updatedSlots = paddedSlots.map(slot => {
          const visitor = activeVisitors.find(v => v.assigned_slot === slot.slot_id);
          const displayStatus = (slot.status === 'occupied' && visitor) ? 'occupied' : 'empty';
          return {
            slot_id: slot.slot_id,
            status: displayStatus,
            visitor: visitor || null
          };
        });

        setSlots(updatedSlots);
        setVisitors(visitorsRes.data);
        setLoading(false);
      } catch (err) {
        setError('Failed to fetch slot details: ' + err.message);
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const formatEntryTime = (entryTime) => {
    if (!entryTime) return 'Unknown';
    const date = new Date(entryTime);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  if (loading) return <div className="loading-container">Loading...</div>;
  if (error) return <div className="error-container">{error}</div>;

  return (
    <div className="slot-details-container">
      <div className="header">
        <h2>Slot Details</h2>
      </div>
      <div className="content-box">
        <div className="legend">
          <div className="legend-item">
            <span className="legend-dot occupied"></span>
            <span className="legend-label">Occupied</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot empty"></span>
            <span className="legend-label">Empty</span>
          </div>
        </div>
        <div className="slots-grid">
          {slots.map((slot) => {
            console.log(`Slot ${slot.slot_id}:`, { status: slot.status, visitor: slot.visitor });

            return (
              <div key={slot.slot_id} className="slot-wrapper">
                <button
                  className={`slot-button ${slot.status === 'occupied' ? 'occupied' : 'empty'}`}
                  title={slot.visitor ? 
                    `Car Number: ${slot.visitor.car_number || 'Unknown'}\nMobile: ${slot.visitor.mobile || 'Unknown'}\nEntry Time: ${formatEntryTime(slot.visitor.entry_time)}` : 
                    'None'}
                >
                  Slot {slot.slot_id}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default SlotDetails;