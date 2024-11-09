import React, { useState, useCallback } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { CircleCheck, AlertCircle, Upload, Wifi, Settings } from 'lucide-react';

export default function ScaleSetup() {
  const [certUploadStatus, setCertUploadStatus] = useState({ success: false, message: '' });
  const [installStatus, setInstallStatus] = useState({ success: false, message: '' });

  const onDrop = useCallback(async (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    
    // Check if all required certificates are present
    const requiredCerts = ['device.cert.pem', 'device.private.key', 'root-CA.crt'];
    const uploadedCerts = files.map(f => f.name);
    const missingCerts = requiredCerts.filter(cert => !uploadedCerts.includes(cert));
    
    if (missingCerts.length > 0) {
      setCertUploadStatus({
        success: false,
        message: `Missing required certificates: ${missingCerts.join(', ')}`
      });
      return;
    }

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
    <div className="w-full max-w-4xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-6">Scale Setup</h1>
      
      <Tabs defaultValue="wifi" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="wifi" className="flex items-center gap-2">
            <Wifi className="w-4 h-4" />
            WiFi Setup
          </TabsTrigger>
          <TabsTrigger value="certificates" className="flex items-center gap-2">
            <Upload className="w-4 h-4" />
            Certificates
          </TabsTrigger>
          <TabsTrigger value="services" className="flex items-center gap-2">
            <Settings className="w-4 h-4" />
            Services
          </TabsTrigger>
        </TabsList>

        <TabsContent value="wifi">
          <div id="wifi-content" />
        </TabsContent>

        <TabsContent value="certificates">
          <div className="p-6 border rounded-lg">
            <h2 className="text-xl font-semibold mb-4">Upload Certificates</h2>
            
            <div 
              onDrop={onDrop}
              onDragOver={(e) => e.preventDefault()}
              className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-gray-400 transition-colors"
            >
              <Upload className="w-12 h-12 mx-auto mb-4 text-gray-400" />
              <p className="mb-2">Drag and drop certificate files here</p>
              <p className="text-sm text-gray-500">Required files: device.cert.pem, device.private.key, root-CA.crt</p>
            </div>

            {certUploadStatus.message && (
              <Alert className={`mt-4 ${certUploadStatus.success ? 'bg-green-50' : 'bg-red-50'}`}>
                {certUploadStatus.success ? (
                  <CircleCheck className="w-4 h-4 text-green-600" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-red-600" />
                )}
                <AlertDescription>{certUploadStatus.message}</AlertDescription>
              </Alert>
            )}
          </div>
        </TabsContent>

        <TabsContent value="services">
          <div className="p-6 border rounded-lg">
            <h2 className="text-xl font-semibold mb-4">Install Services</h2>
            
            <div className="mb-4">
              <p className="text-gray-600 mb-4">
                This will install and configure all required services for the scale:
              </p>
              <ul className="list-disc ml-6 text-gray-600">
                <li>Scale Reader Service</li>
                <li>Cloud Control Service</li>
                <li>System Monitoring</li>
                <li>Log Rotation</li>
              </ul>
            </div>

            <button
              onClick={handleInstallServices}
              className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition-colors"
            >
              Install Services
            </button>

            {installStatus.message && (
              <Alert className={`mt-4 ${installStatus.success ? 'bg-green-50' : 'bg-red-50'}`}>
                {installStatus.success ? (
                  <CircleCheck className="w-4 h-4 text-green-600" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-red-600" />
                )}
                <AlertDescription>{installStatus.message}</AlertDescription>
              </Alert>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
