import React, { useState, useEffect, useRef } from 'react';

const InstallationManager = () => {
  const [logs, setLogs] = useState([]);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [config, setConfig] = useState({
    device_id: '',
    serial_port: '/dev/ttyUSB0',
    baud_rate: 1200,
    bluetooth_mac: '',
    connection_type: 'rs232' // 'rs232' or 'bluetooth'
  });
  const [certStatus, setCertStatus] = useState({
    checked: false,
    complete: false,
    found: [],
    missing: []
  });
  const [btDevices, setBtDevices] = useState([]);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const logEndRef = useRef(null);
  const pollInterval = useRef(null);


  // Fetch initial configuration and certificate status
  useEffect(() => {
    checkCertificates();
    fetchConfig();
  }, []);

  // Auto-scroll logs
  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollInterval.current) {
        clearInterval(pollInterval.current);
      }
    };
  }, [])

  const fetchConfig = async () => {
    try {
      const response = await fetch('/api/config');
      const data = await response.json();
      if (data.device_id) {
        setConfig(prev => ({
          ...prev,
          device_id: data.device_id,
          bluetooth_mac: data.bluetooth_mac || ''
        }));
      }
    } catch (error) {
      console.error('Error fetching config:', error);
      setError("Failed to load configuration");
    }
  };

  const checkCertificates = async () => {
    try {
      const response = await fetch('/api/check-certificates');
      const data = await response.json();
      if (data.success) {
        setCertStatus({
          checked: true,
          complete: data.complete,
          found: data.found,
          missing: data.missing
        });
        setUploadSuccess(data.complete);
      }
    } catch (error) {
      console.error('Error checking certificates:', error);
      setError("Failed to check certificates status");
    }
  };

  const scanBluetoothDevices = async () => {
    setScanning(true);
    try {
      const response = await fetch('/api/scan-bluetooth');
      const data = await response.json();
      if (data.success) {
        // Filter for SH2492 devices
        const relevantDevices = data.devices.filter(device =>
          device.name && device.name.includes('SH2492'));
        setBtDevices(relevantDevices);
      } else {
        setError(data.message);
      }
    } catch (error) {
      setError("Failed to scan Bluetooth devices");
    } finally {
      setScanning(false);
    }
  };

  const handleDeviceSelect = (device) => {
    setConfig(prev => ({
      ...prev,
      bluetooth_mac: device.address,
      connection_type: 'bluetooth'
    }));
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
      if (data.success) {
        setUploadSuccess(true);
        await checkCertificates();
      } else {
        setError(data.message);
      }
    } catch (error) {
      setError('Failed to upload certificates');
    }
  };


  const startLogPolling = () => {
    pollInterval.current = setInterval(fetchLogs, 1000);
  };

  const stopLogPolling = () => {
    if (pollInterval.current) {
      clearInterval(pollInterval.current);
      pollInterval.current = null;
    }
  };

  const fetchLogs = async () => {
    try {
      const response = await fetch('/api/installation-logs');
      const data = await response.json();
      if (data.logs && data.logs.length > 0) {
        setLogs(prevLogs => [...prevLogs, ...data.logs]);
      }
    } catch (error) {
      console.error('Error fetching logs:', error);
    }
  };

  const handleConfigChange = (e) => {
    const { name, value } = e.target;
    setConfig(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const startInstallation = async () => {
    if (!config.device_id) {
      setError('Scale ID is required');
      return;
    }

    setInstalling(true);
    setError(null);
    setLogs([]);
    startLogPolling();

    try {
      const response = await fetch('/api/install-services', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config)
      });

      const data = await response.json();
      if (!data.success) {
        setError(data.message);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setInstalling(false);
      setTimeout(stopLogPolling, 5000);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-6">
      <h2 className="text-2xl font-bold">Scale Installation</h2>

      {/* Certificate Section */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h3 className="text-lg font-semibold mb-4">Certificate Status</h3>

        {!uploadSuccess && (
          <div className="mb-6">
            {certStatus.missing.length > 0 && (
              <div className="mb-4 p-4 bg-red-50 rounded-lg">
                <div className="text-red-600 font-medium mb-2">Missing certificates:</div>
                <ul className="list-disc list-inside space-y-1">
                  {certStatus.missing.map(cert => (
                    <li key={cert} className="text-red-600">{cert}</li>
                  ))}
                </ul>
              </div>
            )}

            <div
              onDragOver={(e) => {
                e.preventDefault();
                e.currentTarget.classList.add('border-blue-500', 'bg-blue-50');
              }}
              onDragLeave={(e) => {
                e.preventDefault();
                e.currentTarget.classList.remove('border-blue-500', 'bg-blue-50');
              }}
              onDrop={(e) => {
                e.preventDefault();
                e.currentTarget.classList.remove('border-blue-500', 'bg-blue-50');
                handleCertificateUpload(e.dataTransfer.files);
              }}
              className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center cursor-pointer hover:border-blue-500 hover:bg-blue-50 transition-all duration-200"
            >
              <div className="flex flex-col items-center">
                <svg className="w-12 h-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-lg text-gray-700 font-medium mb-2">Drop certificate files here</p>
                <p className="text-sm text-gray-500 mb-4">or</p>
                
                <input
                  type="file"
                  multiple
                  onChange={(e) => handleCertificateUpload(e.target.files)}
                  className="hidden"
                  id="certificate-upload"
                  accept=".pem,.crt,.key,.json"
                />
                <label
                  htmlFor="certificate-upload"
                  className="px-6 py-3 bg-blue-500 text-white rounded-lg cursor-pointer hover:bg-blue-600 transition-colors duration-200"
                >
                  Select Files
                </label>
                
                <p className="mt-4 text-sm text-gray-500">
                  Supported files: .pem, .crt, .key, .json
                </p>
              </div>
            </div>
          </div>
        )}

        {uploadSuccess && (
          <div className="border-2 border-green-500 rounded-lg p-4 text-center text-green-600">
            <svg className="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
            </svg>
            <p className="text-lg">All certificates uploaded successfully!</p>
          </div>
        )}
      </div>

      {/* Configuration Section */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Scale ID *</label>
            <input
              type="text"
              name="device_id"
              value={config.device_id}
              onChange={handleConfigChange}
              className="w-full p-2 border rounded bg-gray-100"
              placeholder="Loading from config..."
              disabled
            />
          </div>

          <div className="space-y-2">
            <label className="block text-sm font-medium mb-1">Connection Type</label>
            <div className="flex gap-4">
              <button
                onClick={() => setConfig(prev => ({ ...prev, connection_type: 'rs232' }))}
                className={`px-4 py-2 rounded ${
                  config.connection_type === 'rs232'
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-200 text-gray-700'
                }`}
              >
                RS232
              </button>
              <button
                onClick={() => setConfig(prev => ({ ...prev, connection_type: 'bluetooth' }))}
                className={`px-4 py-2 rounded ${
                  config.connection_type === 'bluetooth'
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-200 text-gray-700'
                }`}
              >
                Bluetooth
              </button>
            </div>
          </div>

          {config.connection_type === 'rs232' ? (
            <>
              <div>
                <label className="block text-sm font-medium mb-1">Serial Port</label>
                <input
                  type="text"
                  name="serial_port"
                  value={config.serial_port}
                  onChange={handleConfigChange}
                  className="w-full p-2 border rounded"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Baud Rate</label>
                <input
                  type="number"
                  name="baud_rate"
                  value={config.baud_rate}
                  onChange={handleConfigChange}
                  className="w-full p-2 border rounded"
                />
              </div>
            </>
          ) : (
            <div className="space-y-4">
              <button
                onClick={scanBluetoothDevices}
                disabled={scanning}
                className="w-full p-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-400"
              >
                {scanning ? (
                  <span className="flex items-center justify-center">
                    <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Scanning...
                  </span>
                ) : 'Scan for Scales'}
              </button>

              {btDevices.length > 0 && (
                <div className="border rounded p-2 space-y-2">
                  {btDevices.map(device => (
                    <div
                      key={device.address}
                      onClick={() => handleDeviceSelect(device)}
                      className={`p-2 rounded cursor-pointer ${
                        config.bluetooth_mac === device.address
                          ? 'bg-blue-100 border-blue-500'
                          : 'hover:bg-gray-100'
                      }`}
                    >
                      <div className="font-medium">{device.name}</div>
                      <div className="text-sm text-gray-600">{device.address}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <button
            onClick={startInstallation}
            disabled={installing || !certStatus.complete}
            className={`w-full p-2 text-white rounded ${
              installing || !certStatus.complete
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-blue-500 hover:bg-blue-600'
            }`}
          >
            {installing ? 'Installing...' : 'Start Installation'}
          </button>

          {!certStatus.complete && (
            <p className="text-sm text-red-600">
              Please upload required certificates before installation
            </p>
          )}
        </div>

        {/* Logs Section */}
        <div className="space-y-4">
          {error && (
            <div className="p-4 bg-red-100 border border-red-400 text-red-700 rounded">
              {error}
            </div>
          )}

          <div className="border rounded h-[400px] overflow-y-auto bg-gray-900 text-gray-100 font-mono p-4">
            {logs.length === 0 ? (
              <div className="text-gray-500">Installation logs will appear here...</div>
            ) : (
              logs.map((log, index) => (
                <div
                  key={index}
                  className={`py-1 ${
                    log.level === 'ERROR' ? 'text-red-400' : 'text-green-400'
                  }`}
                >
                  <span className="text-gray-500">[{log.timestamp}]</span>{' '}
                  {log.message}
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      </div>
    </div>
  );


};

export default InstallationManager;