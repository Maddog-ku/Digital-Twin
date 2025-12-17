import React from 'react';
import { DigitalTwinProvider } from './context/DigitalTwinContext';
import HomePage from './pages/HomePage';

function App() {
  return (
    <DigitalTwinProvider>
      <HomePage />
    </DigitalTwinProvider>
  );
}

export default App;

