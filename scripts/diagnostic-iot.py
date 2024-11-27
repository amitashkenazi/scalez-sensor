#!/usr/bin/env python3

import os
import sys
import json
import socket
import ssl
import subprocess
from urllib.parse import urlparse
import boto3

def run_diagnostics(endpoint, cert_dir="/etc/scale-reader/certs", scale_id=None):
    """Run comprehensive AWS IoT connection diagnostics"""
    results = []
    
    def add_result(test, status, message):
        results.append({"test": test, "status": status, "message": message})
        print(f"\n{test}:")
        print(f"Status: {'✅ PASS' if status else '❌ FAIL'}")
        print(f"Message: {message}")

    # 1. Check network connectivity
    try:
        hostname = urlparse(f"https://{endpoint}").netloc
        socket.create_connection((hostname, 443), timeout=5)
        add_result("Network Connectivity", True, f"Can connect to {hostname}:443")
    except Exception as e:
        add_result("Network Connectivity", False, f"Cannot connect to {hostname}:443: {str(e)}")

    # 2. Verify certificate files
    cert_files = {
        'cert': 'device.cert.pem',
        'key': 'device.private.key',
        'root': 'root-CA.crt'
    }
    
    for name, filename in cert_files.items():
        path = os.path.join(cert_dir, filename)
        try:
            with open(path, 'r') as f:
                content = f.read().strip()
                if content.startswith('-----BEGIN'):
                    add_result(f"Certificate File ({name})", True, f"Valid certificate format in {path}")
                else:
                    add_result(f"Certificate File ({name})", False, f"Invalid certificate format in {path}")
        except Exception as e:
            add_result(f"Certificate File ({name})", False, f"Error reading {path}: {str(e)}")

    # 3. Verify SSL handshake
    try:
        context = ssl.create_default_context(cafile=os.path.join(cert_dir, 'root-CA.crt'))
        context.load_cert_chain(
            os.path.join(cert_dir, 'device.cert.pem'),
            os.path.join(cert_dir, 'device.private.key')
        )
        
        with socket.create_connection((hostname, 443)) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                add_result("SSL Handshake", True, "Successfully completed SSL handshake")
    except Exception as e:
        add_result("SSL Handshake", False, f"SSL handshake failed: {str(e)}")

    # 4. Check AWS IoT thing status if scale_id is provided
    if scale_id:
        try:
            iot = boto3.client('iot')
            thing_name = f"scale-{scale_id}"
            thing = iot.describe_thing(thingName=thing_name)
            
            # Check attached certificates
            principals = iot.list_thing_principals(thingName=thing_name)
            if principals['principals']:
                add_result("AWS IoT Thing", True, 
                          f"Thing exists and has {len(principals['principals'])} certificate(s) attached")
            else:
                add_result("AWS IoT Thing", False, 
                          "Thing exists but has no certificates attached")
        except Exception as e:
            add_result("AWS IoT Thing", False, f"Error checking thing status: {str(e)}")

    # 5. Test MQTT port
    try:
        socket.create_connection((hostname, 8883), timeout=5)
        add_result("MQTT Port", True, "Port 8883 is accessible")
    except Exception as e:
        add_result("MQTT Port", False, f"Cannot connect to port 8883: {str(e)}")

    return results

def main():
    # Load config
    try:
        with open("certs/config.json") as f:
            config = json.load(f)
            endpoint = config.get("iot_endpoint")
            scale_id = config.get("scale_id")
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    if not endpoint:
        print("Error: No IoT endpoint found in config")
        sys.exit(1)

    print("\nAWS IoT Connection Diagnostics")
    print("=" * 50)
    
    results = run_diagnostics(endpoint, cert_dir='./certs', scale_id=scale_id)
    
    # Summary
    print("\nDiagnostic Summary")
    print("=" * 50)
    failed_tests = [r for r in results if not r['status']]
    
    if failed_tests:
        print("\nThe following issues were found:")
        for test in failed_tests:
            print(f"\n❌ {test['test']}:")
            print(f"   {test['message']}")
        print("\nRecommended actions:")
        print("1. Verify your AWS IoT policy allows connect, publish, and subscribe")
        print("2. Ensure certificates are properly attached to the thing in AWS IoT")
        print("3. Check network firewall rules for ports 443 and 8883")
        print("4. Verify the endpoint matches your AWS IoT configuration")
    else:
        print("\n✅ All diagnostic tests passed!")

if __name__ == '__main__':
    main()