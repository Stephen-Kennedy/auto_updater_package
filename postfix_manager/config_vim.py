import os
import shutil
from datetime import datetime
from pkgutil import get_data

# Define paths
PACKAGE_NAME = 'auto_updater_package.config_files'
VIMRC_PATH = '/etc/vim/vimrc'

# Backup function
def backup_vimrc():
    """ Create a backup of the existing /etc/vim/vimrc file. """
    if os.path.isfile(VIMRC_PATH):
        backup_path = f"{VIMRC_PATH}.bak_{datetime.now().strftime('%y%m%d')}"
        shutil.copy2(VIMRC_PATH, backup_path)
        print(f"Backup created: {backup_path}")
    else:
        print("No existing /etc/vim/vimrc file to back up.")

# Update function
def update_vimrc():
    """ Update /etc/vim/vimrc with the content of vim_utils.txt from the package. """
    try:
        # Load vim_utils.txt content from within the package
        vim_utils_content = get_data(PACKAGE_NAME, 'vim_utils.txt').decode('utf-8')
        
        with open(VIMRC_PATH, 'a') as vimrc:
            vimrc.write("\n" + vim_utils_content)
        print("/etc/vim/vimrc has been updated successfully.")
    except PermissionError:
        print("Permission denied. Please run this script with elevated privileges.")
    except FileNotFoundError:
        print("vim_utils.txt not found in the package. Ensure it exists and the package is installed correctly.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    backup_vimrc()
    update_vimrc()

