import React, { useState, useEffect, useRef } from 'react';

const InstallationManager = () => {
  const [logs, setLogs] = useState([]);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState(null);
  const [config, setConfig] = useState({
    scale_id: '',
    serial_port: '/dev/ttyUSB0',
    baud_rate: 1200
  });
  const logEndRef = useRef(null);
  const pollInterval = useRef(null);

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  useEffect(() => {
    return () => {
      if (pollInterval.current) {
        clearInterval(pollInterval.current);
      }
    };
  }, []);

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
    if (!config.scale_id) {
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
      <h2 className="text-2xl font-bold mb-4">Scale Installation</h2>
      
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Scale ID *</label>
            <input
              type="text"
              name="scale_id"
              value={config.scale_id}
              onChange={handleConfigChange}
              className="w-full p-2 border rounded"
              placeholder="Enter Scale ID"
            />
          </div>
          
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
          
          <button
            onClick={startInstallation}
            disabled={installing}
            className="w-full p-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-400"
          >
            {installing ? 'Installing...' : 'Start Installation'}
          </button>
        </div>
        
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