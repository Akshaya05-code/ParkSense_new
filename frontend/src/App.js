import React, { Component } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Dashboard from './Dashboard';
import CurrentLog from './CurrentLog';
import PreviousLog from './PreviousLog';
import Slots from './Slots';
import SlotDetails from './SlotDetails';
import RoverDetails from './RoverDetails';

class ErrorBoundary extends Component {
  state = { error: null, errorInfo: null };
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
    this.setState({ errorInfo });
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ textAlign: 'center', marginTop: '2rem', color: 'red' }}>
          <h1>Error: {this.state.error.message}</h1>
          <p>Check the console for details.</p>
          {this.state.errorInfo && (
            <pre style={{ textAlign: 'left', margin: '1rem', color: 'black' }}>
              {this.state.errorInfo.componentStack}
            </pre>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  console.log('App component rendered');
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <div style={{ minHeight: '100vh' }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/current-logs" element={<CurrentLog />} />
            <Route path="/previous-logs" element={<PreviousLog />} />
            <Route path="/slots" element={<Slots />} />
            <Route path="/slot-details" element={<SlotDetails />} />
            <Route path="/rover-details" element={<RoverDetails />} />
            <Route path="*" element={<div style={{ textAlign: 'center', marginTop: '2rem', color: 'red' }}>404: Page Not Found</div>} />
          </Routes>
        </div>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;