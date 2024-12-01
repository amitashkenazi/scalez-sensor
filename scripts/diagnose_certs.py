#!/usr/bin/env python3

import os
import json
import OpenSSL
import datetime
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

def diagnose_certificates(cert_dir="./certs", endpoint=None):
    """Diagnose common issues with AWS IoT certificates"""
    issues = []
    warnings = []
    
    # Certificate paths
    cert_files = {
        'cert': f"{cert_dir}/device.cert.pem",
        'key': f"{cert_dir}/device.private.key",
        'root': f"{cert_dir}/root-CA.crt"
    }
    
    # Check certificate existence and permissions
    for name, path in cert_files.items():
        if not os.path.exists(path):
            issues.append(f"Missing {name} file: {path}")
            continue
            
        perms = oct(os.stat(path).st_mode)[-3:]
        if name == 'key' and perms != '600':
            issues.append(f"Private key has incorrect permissions: {perms}. Should be 600.")
    
    if issues:
        return issues, warnings
    
    # Load and verify certificate
    try:
        with open(cert_files['cert'], 'rb') as f:
            cert_data = f.read()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            
        # Check expiration
        now = datetime.datetime.now()
        if cert.not_valid_after < now:
            issues.append(f"Certificate has expired on {cert.not_valid_after}")
        elif cert.not_valid_after < now + datetime.timedelta(days=30):
            warnings.append(f"Certificate will expire soon: {cert.not_valid_after}")
            
        # Extract and verify certificate details
        if endpoint:
            san_dns_names = []
            try:
                for ext in cert.extensions:
                    if ext.oid.dotted_string == '2.5.29.17':  # Subject Alternative Name
                        san_dns_names = [name.value for name in ext.value if isinstance(name, x509.DNSName)]
                
                endpoint_base = endpoint.split('.')[0]
                matching_sans = [san for san in san_dns_names if endpoint_base in san]
                
                if not matching_sans:
                    issues.append(f"Certificate SANs {san_dns_names} don't match endpoint {endpoint}")
            except Exception as e:
                warnings.append(f"Could not verify SAN names: {str(e)}")
        
        # Verify private key matches certificate
        try:
            with open(cert_files['key'], 'rb') as f:
                key_data = f.read()
                private_key = serialization.load_pem_private_key(
                    key_data,
                    password=None,
                    backend=default_backend()
                )
                
            # Get public keys
            cert_public_key = cert.public_key().public_numbers()
            private_key_public = private_key.public_key().public_numbers()
            
            if cert_public_key != private_key_public:
                issues.append("Private key does not match certificate")
                
        except Exception as e:
            issues.append(f"Error verifying private key: {str(e)}")
            
    except Exception as e:
        issues.append(f"Error loading certificate: {str(e)}")
    
    return issues, warnings

if __name__ == "__main__":
    print("\nAWS IoT Certificate Diagnostics")
    print("=" * 50)
    
    endpoint = None
    try:
        with open("./certs/config.json") as f:
            config = json.load(f)
            endpoint = config.get("iot_endpoint")
    except Exception:
        pass
    
    issues, warnings = diagnose_certificates(endpoint=endpoint)
    
    if issues:
        print("\nIssues Found:")
        for issue in issues:
            print(f"❌ {issue}")
    
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"⚠️ {warning}")
    
    if not issues and not warnings:
        print("\n✅ No issues found with certificates")
        