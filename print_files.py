import os
import pyperclip
def print_file_contents(directory, file_extension, output, exclude_files=[], exclude_directories=[]):
    for root, dirs, files in os.walk(directory):
        # Exclude directories like __pycache__, .serverless, venv, etc.
        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.serverless', 'venv', 'node_modules', '.venv']]
        for directory in exclude_directories:
            if directory in dirs:
                dirs.remove(directory)
        


        for file in files:
            if file in exclude_files:
                print(f"excluding file: {file}")
                continue
        
            if file.endswith(file_extension) or file == 'serverless.yml':
                print(f"file: {file}")
                file_path = os.path.join(root, file)
                output += f"<{file_path}>:"
                output += "File Content:"
                with open(file_path, 'r') as f:
                    content = f.read()
                    output += content
                output += "\n"
    return output

# Specify the directory to search (current directory)
output = ""
project_directory = '.'
output += "here is my files' content:"
# Print the contents of all Python files and the serverless.yml file
output = print_file_contents(project_directory, '.py', output, exclude_files=['.DS_Store'], exclude_directories=['node_modules', '__pycache__','.venv'])
output = print_file_contents(project_directory, '.sh', output, exclude_files=['.DS_Store'], exclude_directories=['node_modules', '__pycache__','.venv'])
pyperclip.copy(output)