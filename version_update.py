import os
import sys

extensions_white = [".py", ".ini"]
extensions_black = [".pyc"]


def get_version_number():
    """Get version number from VersionNumber file"""
    if os.path.exists("VersionNumber"):
        with open("VersionNumber") as f:
            version = f.readline()
        return version.replace("\n", "")
    print("VersionNumber file not found,")
    sys.exit()


def get_file_list():
    """Get list of all files with extensions from extensions_white"""
    file_list = []
    for path, subdirs, files in os.walk(os.getcwd()):
        for name in files:
            file_path = os.path.join(path, name)
            if any(x in file_path for x in extensions_white):
                if not any(x in file_path for x in extensions_black):
                    file_list.append(file_path)
    return file_list


def main():
    """Update versions in all files"""
    print("Running version update script.")
    version = get_version_number()
    file_list = get_file_list()
    any_updated = False
    for filename in file_list:
        if "version_update.py" not in filename:
            update = False
            with open(filename, "r") as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith("VERSION = "):
                        if line.split("VERSION = ")[-1] != f'"{version}"\n':
                            update = True
            if update:
                any_updated = True
                with open(filename, "w") as f:
                    for line in lines:
                        if "VERSION = " in line:
                            f.write(f'VERSION = "{version}"\n')
                        else:
                            f.write(line)
                print(f"Version number updated in: {filename}")
    if any_updated:
        print(f"New version: {version}")
    else:
        print("Version in all files is already the latest.")
    sys.exit()

if __name__ == "__main__":
    main()
