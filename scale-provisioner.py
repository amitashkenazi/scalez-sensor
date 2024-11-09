#!/usr/bin/env python3

import boto3
import json
import os
import argparse
from botocore.exceptions import ClientError

def provision_scale(scale_id: str, output_dir: str):
    """Provision a new scale in AWS IoT"""
    iot = boto3.client('iot')
    
    try:
        # Create thing
        iot.create_thing(
            thingName=f"scale-{scale_id}",
            attributePayload={
                'attributes': {
                    'type': 'scale',
                    'scale_id': scale_id
                }
            }
        )
        
        # Create certificate
        cert_response = iot.create_keys_and_certificate(setAsActive=True)
        
        # Save certificate and keys
        os.makedirs(output_dir, exist_ok=True)
        
        with open(f"{output_dir}/{scale_id}.cert.pem", 'w') as f:
            f.write(cert_response['certificatePem'])
            
        with open(f"{output_dir}/{scale_id}.private.key", 'w') as f:
            f.write(cert_response['keyPair']['PrivateKey'])
            
        # Download root CA
        os.system(f"curl https://www.amazontrust.com/repository/AmazonRootCA1.pem -o {output_dir}/root-CA.crt")
        
        # Attach policy
        iot.attach_policy(
            policyName='scale-management-system-scale-policy-dev',  # Update with your policy name
            target=cert_response['certificateArn']
        )
        
        # Attach certificate to thing
        iot.attach_thing_principal(
            thingName=f"scale-{scale_id}",
            principal=cert_response['certificateArn']
        )
        
        print(f"✅ Scale {scale_id} provisioned successfully!")
        print(f"Certificates saved to: {output_dir}")
        
    except ClientError as e:
        print(f"❌ Error provisioning scale: {e}")
        raise

def main():
    parser = argparse.ArgumentParser(description='Provision a new scale in AWS IoT')
    parser.add_argument('--scale-id', required=True, help='Scale ID')
    parser.add_argument('--output-dir', default='/etc/scale-reader/certs',
                       help='Directory to store certificates')
    
    args = parser.parse_args()
    provision_scale(args.scale_id, args.output_dir)

if __name__ == '__main__':
    main()
