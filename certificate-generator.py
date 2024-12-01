#!/usr/bin/env python3

import boto3
import json
import os
import argparse
from botocore.exceptions import ClientError

def provision_device(device_id: str, output_dir: str, policy_name: str, stage: str):
    """Provision a new device in AWS IoT"""
    iot = boto3.client('iot')
    
    try:
        # Create thing
        thing_name = f"device-{device_id}"
        print(f"Creating thing: {thing_name}")
        iot.create_thing(
            thingName=thing_name,
            attributePayload={
                'attributes': {
                    'type': 'scale',
                    'device_id': device_id
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
            'device_id': device_id,
            'serial_port': '/dev/ttyUSB0',
            'baud_rate': 1200,
            'iot_endpoint': iot.describe_endpoint(endpointType='iot:Data-ATS')['endpointAddress'],
            'stage': stage

        }
        print(f"config: {config}")
        
        with open(f"{output_dir}/config.json", 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"\n✅ Device {device_id} provisioned successfully!")
        print(f"Certificates saved in: {output_dir}")
        print(f"Configuration saved as: {output_dir}/config.json")
        
    except ClientError as e:
        print(f"❌ Error provisioning device: {e}")
        raise

def main():
    parser = argparse.ArgumentParser(description='Provision a new device in AWS IoT')
    parser.add_argument('--device-id', required=True, help='Scale ID (UUID)')
    parser.add_argument('--output-dir', default='./certs',
                       help='Directory to store certificates')
    parser.add_argument('--policy-name', default='scale-management-system-scale-policy-dev',
                       help='IoT policy name to attach')
    parser.add_argument('--stage', default='dev',
                       help='Deployment stage')
    
    args = parser.parse_args()
    provision_device(args.device_id, args.output_dir, args.policy_name, args.stage)

if __name__ == '__main__':
    main()
