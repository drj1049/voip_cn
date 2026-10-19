import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './App.css';

// Entry point: find the <div id="root"> in index.html and draw the whole app inside it
ReactDOM.createRoot(document.getElementById('root')).render(<App />);
