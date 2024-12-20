import React, { useState, useCallback, useEffect } from 'react';

function ScaleSetup() {
  const [activeTab, setActiveTab] = useState('wifi');
  const [networks, setNetworks] = useState([]);
  const [status, setStatus] = useState({});
  const [config, setConfig] = useState({});
  const [selectedNetwork, setSelectedNetwork] = useState(null);
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [certUploadStatus, setCertUploadStatus] = useState({ success: false, message: '' });
  const [installStatus, setInstallStatus] = useState({ success: false, message: '' });

  useEffect(() => {
    updateStatus();
    updateConfig();
    refreshNetworks();
  }, []);

  useEffect(() => {
    const interval = setInterval(updateStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const updateStatus = async () => {
    try {
      const response = await fetch('/api/status');
      const data = await response.json();
      setStatus(data);
    } catch (error) {
      console.error('Error updating status:', error);
    }
  };

  const updateConfig = async () => {
    try {
      const response = await fetch('/api/config');
      const data = await response.json();
      setConfig(data);
    } catch (error) {
      console.error('Error updating config:', error);
    }
  };

  const refreshNetworks = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/scan');
      const data = await response.json();
      setNetworks(data.networks);
    } catch (error) {
      console.error('Error scanning networks:', error);
    }
    setLoading(false);
  };

  const connectToNetwork = async (event) => {
    event.preventDefault();
    setLoading(true);
    
    try {
      const response = await fetch('/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ssid: selectedNetwork,
          password: password
        })
      });
      
      const data = await response.json();
      if (data.success) {
        alert('Successfully connected to network');
        updateStatus();
      } else {
        alert(`Failed to connect: ${data.error}`);
      }
    } catch (error) {
      alert('Error connecting to network');
    }
    
    setLoading(false);
    setSelectedNetwork(null);
    setPassword('');
  };

  const disconnectWifi = async () => {
    if (!confirm('Are you sure you want to disconnect from WiFi?')) {
      return;
    }
    
    try {
      const response = await fetch('/api/disconnect');
      const data = await response.json();
      if (data.success) {
        alert('Successfully disconnected from WiFi');
        updateStatus();
      } else {
        alert(`Failed to disconnect: ${data.error}`);
      }
    } catch (error) {
      alert('Error disconnecting from WiFi');
    }
  };

  const onDrop = useCallback(async (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    
    const formData = new FormData();
    files.forEach(file => formData.append('certificates', file));

    try {
      const response = await fetch('/api/upload-certificates', {
        method: 'POST',
        body: formData
      });
      
      const result = await response.json();
      setCertUploadStatus({
        success: result.success,
        message: result.message
      });
    } catch (error) {
      setCertUploadStatus({
        success: false,
        message: `Upload failed: ${error.message}`
      });
    }
  }, []);

  const handleInstallServices = async () => {
    try {
      setInstallStatus({ success: false, message: 'Installing services...' });
      
      const response = await fetch('/api/install-services', {
        method: 'POST'
      });
      
      const result = await response.json();
      setInstallStatus({
        success: result.success,
        message: result.message
      });
    } catch (error) {
      setInstallStatus({
        success: false,
        message: `Installation failed: ${error.message}`
      });
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="flex border-b">
          <button
            className={`px-4 py-2 ${activeTab === 'wifi' ? 'border-b-2 border-blue-500' : ''}`}
            onClick={() => setActiveTab('wifi')}
          >
            WiFi Setup
          </button>
          <button
            className={`px-4 py-2 ${activeTab === 'certificates' ? 'border-b-2 border-blue-500' : ''}`}
            onClick={() => setActiveTab('certificates')}
          >
            Certificates
          </button>
          <button
            className={`px-4 py-2 ${activeTab === 'services' ? 'border-b-2 border-blue-500' : ''}`}
            onClick={() => setActiveTab('services')}
          >
            Services
          </button>
        </div>
      </div>

      {/* WiFi Tab */}
      {activeTab === 'wifi' && (
        <div>
          <div className={`mb-6 p-4 rounded ${status.connected ? 'bg-green-100' : 'bg-red-100'}`}>
            {status.connected ? (
              <div>
                <p>Connected to: {status.ssid}</p>
                <p>IP Address: {status.ip}</p>
              </div>
            ) : (
              <p>Not connected to any network</p>
            )}
          </div>

          <button
            onClick={refreshNetworks}
            className="mb-4 px-4 py-2 bg-blue-500 text-white rounded"
            disabled={loading}
          >
            {loading ? 'Scanning...' : 'Scan Networks'}
          </button>

          {status.connected && (
            <button
              onClick={disconnectWifi}
              className="ml-2 px-4 py-2 bg-red-500 text-white rounded"
            >
              Disconnect
            </button>
          )}

          <div className="mt-4">
            <h2 className="text-lg font-semibold mb-2">Available Networks</h2>
            <ul>
              {networks.map((network) => (
                <li
                  key={network.ssid}
                  className="p-2 border-b cursor-pointer hover:bg-gray-100"
                  onClick={() => setSelectedNetwork(network.ssid)}
                >
                  {network.ssid}
                  <span className="float-right">{network.signal_strength}%</span>
                </li>
              ))}
            </ul>
          </div>

          {selectedNetwork && (
            <div className="mt-4 p-4 border rounded">
              <h3 className="text-lg mb-2">Connect to {selectedNetwork}</h3>
              <form onSubmit={connectToNetwork}>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password"
                  className="w-full p-2 border rounded mb-2"
                  required
                />
                <button
                  type="submit"
                  className="px-4 py-2 bg-blue-500 text-white rounded"
                  disabled={loading}
                >
                  Connect
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedNetwork(null)}
                  className="ml-2 px-4 py-2 bg-gray-500 text-white rounded"
                >
                  Cancel
                </button>
              </form>
            </div>
          )}
        </div>
      )}

      {/* Certificates Tab */}
      {activeTab === 'certificates' && (
        <div>
          <div
            onDrop={onDrop}
            onDragOver={(e) => e.preventDefault()}
            className="border-2 border-dashed rounded p-8 text-center"
          >
            <p className="mb-4">Drag and drop certificate files here</p>
            <p className="text-sm text-gray-500">
              Required files: device.cert.pem, device.private.key, root-CA.crt
            </p>
          </div>

          {certUploadStatus.message && (
            <div className={`mt-4 p-4 rounded ${certUploadStatus.success ? 'bg-green-100' : 'bg-red-100'}`}>
              {certUploadStatus.message}
            </div>
          )}
        </div>
      )}

      {/* Services Tab */}
      {activeTab === 'services' && (
        <div>
          <div className="mb-4">
            <h2 className="text-lg font-semibold mb-2">Install Services</h2>
            <p className="text-gray-600 mb-4">
              This will install and configure all required services for the scale:
            </p>
            <ul className="list-disc ml-6 mb-4">
              <li>Scale Reader Service</li>
              <li>Cloud Control Service</li>
              <li>System Monitoring</li>
              <li>Log Rotation</li>
            </ul>
            <button
              onClick={handleInstallServices}
              className="px-4 py-2 bg-blue-500 text-white rounded"
            >
              Install Services
            </button>
          </div>

          {installStatus.message && (
            <div className={`mt-4 p-4 rounded ${installStatus.success ? 'bg-green-100' : 'bg-red-100'}`}>
              {installStatus.message}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ScaleSetup;