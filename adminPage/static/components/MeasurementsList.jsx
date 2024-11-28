import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

const MeasurementsList = () => {
  const [measurements, setMeasurements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchMeasurements = async () => {
      try {
        const response = await fetch('/api/measurements');
        const data = await response.json();
        
        if (data.success) {
          setMeasurements(data.measurements);
        } else {
          setError(data.error || 'Failed to fetch measurements');
        }
      } catch (err) {
        setError('Failed to fetch measurements');
      } finally {
        setLoading(false);
      }
    };

    fetchMeasurements();
    const interval = setInterval(fetchMeasurements, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <div className="text-center p-4">Loading measurements...</div>;
  }

  if (error) {
    return (
      <div className="text-red-500 p-4 text-center">
        Error: {error}
      </div>
    );
  }

  return (
    <Card className="w-full max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle>Recent Measurements</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="divide-y">
          {measurements.length > 0 ? (
            measurements.map((measurement, index) => (
              <div key={index} className="py-3 flex justify-between items-center">
                <div>
                  <div className="text-lg font-medium">
                    {measurement.weight} {measurement.unit}
                  </div>
                  <div className="text-sm text-gray-500">
                    {new Date(measurement.timestamp).toLocaleString()}
                  </div>
                </div>
                <div className="text-sm">
                  {measurement.uploaded ? (
                    <span className="text-green-500">Uploaded</span>
                  ) : (
                    <span className="text-yellow-500">Pending</span>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="text-center py-4 text-gray-500">
              No measurements found
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default MeasurementsList;