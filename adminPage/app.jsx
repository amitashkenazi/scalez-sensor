import React, { useState, useEffect } from 'react';
import InstallationManager from '../components/InstallationManager';

const App = () => {
  const [activeTab, setActiveTab] = useState('wifi');
  const [wifiStatus, setWifiStatus] = useState({ connected: false, ssid: '', ip: '' });
  const [networks, setNetworks] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState(null);
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    checkStatus();
    fetchLogs();
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, []);

  const checkStatus = async () => {
    try {
      const response = await fetch('/api/status');
      const data = await response.json();
      setWifiStatus(data);
    } catch (error) {
      console.error('Error checking status:', error);
    }
  };

  const scanNetworks = async () => {
    setScanning(true);
    try {
      const response = await fetch('/api/scan');
      const data = await response.json();
      setNetworks(data.networks || []);
    } catch (error) {
      console.error('Error scanning networks:', error);
    } finally {
      setScanning(false);
    }
  };

  const connectToNetwork = async (ssid, password) => {
    setConnecting(true);
    setError(null);
    try {
      const response = await fetch('/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ssid, password })
      });
      const data = await response.json();
      if (!data.success) {
        setError(data.error);
      } else {
        await checkStatus();
      }
    } catch (error) {
      setError('Failed to connect to network');
    } finally {
      setConnecting(false);
    }
  };

  const disconnectWifi = async () => {
    try {
      await fetch('/api/disconnect');
      await checkStatus();
    } catch (error) {
      console.error('Error disconnecting:', error);
    }
  };

  const fetchLogs = async () => {
    try {
      const response = await fetch('/api/logs');
      const data = await response.json();
      if (data.success) {
        setLogs(data.logs);
      }
    } catch (error) {
      console.error('Error fetching logs:', error);
    }
  };

  const handleCertificateUpload = async (files) => {
    const formData = new FormData();
    for (const file of files) {
      formData.append('certificates', file);
    }

    try {
      const response = await fetch('/api/upload-certificates', {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      if (!data.success) {
        setError(data.message);
      }
    } catch (error) {
      setError('Failed to upload certificates');
    }
  };

  const renderWiFiTab = () => (
    <div className="space-y-6">
      <div className="bg-white p-6 rounded-lg shadow">
        <h3 className="text-lg font-semibold mb-4">WiFi Status</h3>
        {wifiStatus.connected ? (
          <div className="space-y-2">
            <p>Connected to: {wifiStatus.ssid}</p>
            <p>IP Address: {wifiStatus.ip}</p>
            <button
              onClick={disconnectWifi}
              className="mt-2 px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600"
            >
              Disconnect
            </button>
          </div>
        ) : (
          <p>Not connected to any network</p>
        )}
      </div>

      <div className="bg-white p-6 rounded-lg shadow">
        <h3 className="text-lg font-semibold mb-4">Available Networks</h3>
        <button
          onClick={scanNetworks}
          disabled={scanning}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-400"
        >
          {scanning ? 'Scanning...' : 'Scan Networks'}
        </button>
        
        <div className="mt-4 space-y-2">
          {networks.map((network) => (
            <div key={network.ssid} className="flex items-center justify-between p-2 border rounded">
              <div>
                <span className="font-medium">{network.ssid}</span>
                <span className="ml-2 text-sm text-gray-500">
                  Signal: {network.signal_strength}%
                </span>
              </div>
              <button
                onClick={() => {
                  const password = prompt(`Enter password for ${network.ssid}`);
                  if (password) {
                    connectToNetwork(network.ssid, password);
                  }
                }}
                disabled={connecting}
                className="px-3 py-1 bg-green-500 text-white rounded hover:bg-green-600 disabled:bg-gray-400"
              >
                Connect
              </button>
            </div>
          ))}
        </div>
        
        {error && (
          <div className="mt-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}
      </div>
    </div>
  );

  const renderCertificatesTab = () => (
    <div className="bg-white p-6 rounded-lg shadow space-y-6">
      <h3 className="text-lg font-semibold">Upload Certificates</h3>
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handleCertificateUpload(e.dataTransfer.files);
        }}
        className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center"
      >
        <p>Drag and drop certificate files here</p>
        <p className="text-sm text-gray-500 mt-2">Required: device.cert.pem, device.private.key, root-CA.crt</p>
      </div>
      
      <div className="mt-4">
        <input
          type="file"
          multiple
          onChange={(e) => handleCertificateUpload(e.target.files)}
          className="hidden"
          id="certificate-upload"
        />
        <label
          htmlFor="certificate-upload"
          className="inline-block px-4 py-2 bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600"
        >
          Select Files
        </label>
      </div>
    </div>
  );

  const renderLogsTab = () => (
    <div className="bg-white p-6 rounded-lg shadow">
      <h3 className="text-lg font-semibold mb-4">System Logs</h3>
      <div className="h-96 overflow-y-auto bg-gray-900 text-gray-100 font-mono p-4 rounded">
        {logs.map((log, index) => (
          <div key={index} className="py-1">
            <span className="text-gray-500">[{log.timestamp}]</span>{' '}
            <span className="text-gray-300">{log.source}:</span>{' '}
            {log.message}
          </div>
        ))}
      </div>
    </div>
  );

  const renderInstallTab = () => (
    <InstallationManager />
  );

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <h1 className="text-xl font-bold text-gray-800">Scale Setup</h1>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto py-6 px-4">
        <div className="border-b border-gray-200 mb-6">
          <nav className="-mb-px flex space-x-8">
            {[
              { id: 'wifi', name: 'WiFi Setup' },
              { id: 'certs', name: 'Certificates' },
              { id: 'install', name: 'Installation' },
              { id: 'logs', name: 'System Logs' }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab.name}
              </button>
            ))}
          </nav>
        </div>

        {activeTab === 'wifi' && renderWiFiTab()}
        {activeTab === 'certs' && renderCertificatesTab()}
        {activeTab === 'install' && renderInstallTab()}
        {activeTab === 'logs' && renderLogsTab()}
      </div>
    </div>
  );
};

export default App;