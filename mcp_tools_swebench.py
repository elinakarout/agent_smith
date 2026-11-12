import glob

def read_file(filepath, start_line, end_line):
    if start_line > end_line:
        return ""
    if start_line < 0:
        return ""
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
            result=""
            for i in range(start_line - 1, min(len(lines), end_line)):
                result = result + (f"{i + 1}:" + lines[i])
        return result
    except FileNotFoundError:
        return "File Not Found"


def edit_file(filepath, old_str, new_str):
    if old_str == "":
        return "Error: String to replace is \"\"\n"
    if old_str == new_str:
        return "Error: String and Replacement Are Equal\n"
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            occurences = content.count(old_str)
            if occurences > 1:
                return f"Error: {occurences} Occurences Found\n"
            if occurences == 0:
                return "Error: Couldn't Find String\n"
        with open(filepath, 'w') as f:
            content = content.replace(old_str, new_str)
            f.write(content)
            return "String Replaced Successfully\n"
        
    except FileNotFoundError:
        return "Error: File Not Found\n"
    except PermissionError:
        return "Error: Permission Denied\n"


def list_files(directory, pattern):
    return "\n".join(glob.glob(f"{directory}/{pattern}"))


# print(read_file("agent_mbpp/__main__.py", 10, 20), end='')

# print(edit_file("test.py", "# Should we", "#hhhhhhhhhh"), end="")

# print(list_files("**", "*.py"))