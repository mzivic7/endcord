import curses
import logging
import shutil
import subprocess
import sys

if sys.platform == "win32":
    import pywintypes
    import win32cred
    BACKSPACE = 8
else:
    BACKSPACE = curses.KEY_BACKSPACE

APP_NAME = "endcord"
TOKEN_MANAGER_TEXT = """ Token is required to access Discord through your account without logging-in.
 If token is provided here, it will be encrypted and saved in local systems keyring.
 Alternatively token can be provided in config and as command argument.
 To delete it run 'endcord --remove-token'; to update: 'endcord --update-token'.

 Obtaining your token:
 1. Open Discord in browser.
 2. Open developer tools ('F12' or 'Ctrl+Shift+I' on Chrome and Firefox).
 3. Go to the 'Network' tab then refresh the page.
 4. In the 'Filter URLs' text box, search 'discord.com/api'.
 5. Click on any filtered entry. On the right side, switch to 'Header' tab, look for 'Authorization'.
 6. Copy value of 'Authorization: ...' found under 'Request Headers' (right click -> Copy Value)
 7. This is your discord token. DO NOT SHARE IT!

 Token can be pasted here (with Ctrl+Shift+V on most terminals):



 Enter to confirm, Esc to cancel.
 """
logger = logging.getLogger(__name__)


def load_token():
    """Try to load token from system keyring"""
    if sys.platform == "linux":
        try:
            result = subprocess.run([
                "secret-tool", "lookup",
                "service", APP_NAME,
                ], capture_output=True, text=True, check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    if sys.platform == "win32":
        try:
            cred = win32cred.CredRead(
                f"{APP_NAME} token",
                win32cred.CRED_TYPE_GENERIC,
            )
            return cred["CredentialBlob"].decode("utf-16")
        except pywintypes.error:
            return None

    if sys.platform == "darwin":
        try:
            result = subprocess.run([
                "security", "find-generic-password",
                "-s", APP_NAME,
                "-w",
                ], capture_output=True, text=True, check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None


def save_token(token):
    """Save token to sustem keyring"""
    if sys.platform == "linux":
        subprocess.run([
            "secret-tool", "store",
            "--label=" + f"{APP_NAME} token",
            "service", APP_NAME,
            ], input=token.encode(), check=True,
        )

    elif sys.platform == "win32":
        try:
            win32cred.CredWrite({
                "Type": win32cred.CRED_TYPE_GENERIC,
                "TargetName": f"{APP_NAME} token",
                "CredentialBlob": token.encode("utf-16"),
                "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
            }, 0)
        except pywintypes.error as e:
            sys.exit(e)


    elif sys.platform == "darwin":
        subprocess.run([
            "security", "add-generic-password",
            "-s", APP_NAME,
            "-a", "token",
            "-w", token,
            "-U",
            ], check=True,
        )


def remove_token():
    """Remove token from system keyring"""
    if sys.platform == "linux":
        try:
            subprocess.run([
                "secret-tool", "clear",
                "service", APP_NAME,
                ], check=True,
            )
        except subprocess.CalledProcessError:
            pass

    elif sys.platform == "win32":
        try:
            win32cred.CredDelete(
                f"{APP_NAME} token",
                win32cred.CRED_TYPE_GENERIC,
                0,
            )
        except pywintypes.error:
            pass

    elif sys.platform == "darwin":
        subprocess.run([
            "security", "delete-generic-password",
            "-s", APP_NAME,
            ], check=True,
        )


def get_prompt_y(width):
    """Get prompt y position from length of TOKEN_MANAGER_TEXT and terminal width"""
    lines = TOKEN_MANAGER_TEXT.split("\n")
    used_lines = len(lines)
    for line in lines:
        used_lines += len(line) // width
    return used_lines - 3


def token_prompt(screen):
    """Keybinding picker, prints last pressed key combination"""
    curses.use_default_colors()
    curses.curs_set(0)
    curses.init_pair(1, -1, -1)
    screen.bkgd(" ", curses.color_pair(1))
    screen.addstr(1, 0, TOKEN_MANAGER_TEXT, curses.color_pair(1))
    _, w = screen.getmaxyx()
    prompt_y = get_prompt_y(w)
    screen.addstr(prompt_y, 1, "TOKEN: " + " " * (w - 9), curses.color_pair(1) | curses.A_STANDOUT)
    run = True
    enter = False
    text = ""
    while run:
        key = screen.getch()

        if key == 27:
            screen.nodelay(True)
            key = screen.getch()
            if key == -1:
                # escape key
                screen.nodelay(False)
                break
            sequence = [27, key]
            while key != -1:
                key = screen.getch()
                sequence.append(key)
                if key == 126:
                    break
                if key == 27:   # holding escape key
                    sequence.append(-1)
                    break
            screen.nodelay(False)
            if sequence[-1] == -1 and sequence[-2] == 27:
                break

        if key == 10:
            enter = True
            break

        if isinstance(key, int) and 32 <= key <= 126:
            text += chr(key)

        if key == BACKSPACE:
            text = text[:-1]

        _, w = screen.getmaxyx()
        screen.addstr(prompt_y, 1, "TOKEN: " + text[:w-9] + " " * (w - len(text)-9), curses.color_pair(1) | curses.A_STANDOUT)
        screen.refresh()

    screen.clear()
    screen.refresh()

    if enter:
        return text
    return None


def get_token(force=False):
    """
    Try to get token from keyring, if unavailable, show UI prompt to save it.
    If secret-tool command is not installed, return None.
    """
    token = load_token()
    if token and not force:
        return token

    if sys.platform == "linux" and not shutil.which("secret-tool"):
        sys.exit("secret-tool command not found on system, probably because 'libsecret' is not installed. Token can be provided with argument -t or in config.")

    try:
        token = curses.wrapper(token_prompt)
    except curses.error as e:
        if str(e) != "endwin() returned ERR":
            logger.error(e)
            sys.exit("Curses error, see log for more info")

    if token:
        save_token(token)
        return token
    sys.exit("No token provided")
