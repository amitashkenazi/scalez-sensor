import subprocess
import time
import logging
import os
from datetime import datetime

# Set absolute paths for logging
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, 'command_execution.log')

# Set up logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

def run_commands():
    try:
        # First command - authentication
        auth_result = subprocess.run(
            ['sudo', '/usr/local/bin/authenticate.py', 
             '--username', 'amitashkenazi@gmail.com', 
             '--password', 'zaq1Xsw2@'],
            capture_output=True,
            text=True,
            env=dict(os.environ, PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        )
        
        logging.info(f"Authentication command executed. Status: {auth_result.returncode}")
        if auth_result.returncode != 0:
            logging.error(f"Authentication error: {auth_result.stderr}")
            return
            
        # Second command - scale reader
        scale_result = subprocess.run(
            ['sudo', '/usr/local/bin/scale_reader.py'],
            capture_output=True,
            text=True,
            env=dict(os.environ, PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        )
        
        logging.info(f"Scale reader command executed. Status: {scale_result.returncode}")
        if scale_result.returncode != 0:
            logging.error(f"Scale reader error: {scale_result.stderr}")
            
    except Exception as e:
        logging.error(f"Error executing commands: {str(e)}")

def main():
    print(f"LOG_FILE: {LOG_FILE}")
    logging.info("Script started")
    
    while True:
        run_commands()
        time.sleep(10)

if __name__ == "__main__":
    main()
