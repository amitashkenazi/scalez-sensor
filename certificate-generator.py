#!/usr/bin/env python3

import boto3
import json
import os
import argparse
from botocore.exceptions import ClientError

def provision_device(scale_id: str, output_dir: str, policy_name: str):
    """Provision a new device in AWS IoT"""
    iot = boto3.client('iot')
    
    try:
        # Create thing
        thing_name = f"scale-{scale_id}"
        print(f"Creating thing: {thing_name}")
        iot.create_thing(
            thingName=thing_name,
            attributePayload={
                'attributes': {
                    'type': 'scale',
                    'scale_id': scale_id
                }
            }
        )
        
        # Create certificate
        print("Creating certificates...")
        cert_response = iot.create_keys_and_certificate(setAsActive=True)
        
        # Save certificate and keys with generic names
        os.makedirs(output_dir, exist_ok=True)
        
        # Save with generic names
        with open(f"{output_dir}/device.cert.pem", 'w') as f:
            f.write(cert_response['certificatePem'])
            
        with open(f"{output_dir}/device.private.key", 'w') as f:
            f.write(cert_response['keyPair']['PrivateKey'])
            
        # Download root CA
        print("Downloading root CA certificate...")
        os.system(f"curl https://www.amazontrust.com/repository/AmazonRootCA1.pem -o {output_dir}/root-CA.crt")
        
        # Attach policy
        print(f"Attaching policy: {policy_name}")
        iot.attach_policy(
            policyName=policy_name,
            target=cert_response['certificateArn']
        )
        
        # Attach certificate to thing
        print("Attaching certificate to thing...")
        iot.attach_thing_principal(
            thingName=thing_name,
            principal=cert_response['certificateArn']
        )
        
        # Save configuration
        config = {
            'scale_id': scale_id,
            'serial_port': '/dev/ttyUSB0',
            'baud_rate': 1200,
            'iot_endpoint': iot.describe_endpoint(endpointType='iot:Data-ATS')['endpointAddress']
        }
        
        with open(f"{output_dir}/config.json", 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"\n✅ Device {scale_id} provisioned successfully!")
        print(f"Certificates saved in: {output_dir}")
        print(f"Configuration saved as: {output_dir}/config.json")
        
    except ClientError as e:
        print(f"❌ Error provisioning device: {e}")
        raise

def main():
    parser = argparse.ArgumentParser(description='Provision a new device in AWS IoT')
    parser.add_argument('--scale-id', required=True, help='Scale ID (UUID)')
    parser.add_argument('--output-dir', default='./certs',
                       help='Directory to store certificates')
    parser.add_argument('--policy-name', default='scale-management-system-scale-policy-dev',
                       help='IoT policy name to attach')
    
    args = parser.parse_args()
    provision_device(args.scale_id, args.output_dir, args.policy_name)

if __name__ == '__main__':
    main()