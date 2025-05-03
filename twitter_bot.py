import time
import json
import csv
import random
import requests
import os
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse, parse_qs

# ================== CONFIG ==================
GDRIVE_SESSION_FOLDER_URL = 'https://drive.google.com/drive/folders/1eKBQlJJ_s61YHetghooCb1ntmKKiUBou?usp=sharing'
GDRIVE_ACCOUNT_FILE_URL = 'https://drive.google.com/file/d/1weymXfnDh4opZrA_xmTT4QkAjScdWGaf/view?usp=sharing'
GDRIVE_USER_FILE_URL = 'https://drive.google.com/file/d/1Fa-rkZZceInx8vvLu_DcPQKNpZz0iGNM/view?usp=sharing'
LOCAL_DOWNLOAD_DIR = "/tmp/twitter_automation_downloads"
# ============================================

# Helper to extract file ID from Google Drive URL
def get_gdrive_file_id(gdrive_url):
    if "id=" in gdrive_url:
        return parse_qs(urlparse(gdrive_url).query).get('id', [None])[0]
    elif "file/d/" in gdrive_url:
        return gdrive_url.split("file/d/")[1].split("/")[0]
    elif "folders/" in gdrive_url:
        return gdrive_url.split("folders/")[1].split("?")[0]
    else:
        raise ValueError(f"Could not parse Google Drive file ID from URL: {gdrive_url}")

# Download a single file from Google Drive
def download_file_from_gdrive(gdrive_url, dest_path):
    file_id = get_gdrive_file_id(gdrive_url)
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    print(f"Downloading from: {download_url}")
    with requests.get(download_url, stream=True) as response:
        if response.status_code == 200:
            with open(dest_path, 'wb') as f:
                shutil.copyfileobj(response.raw, f)
            print(f"Downloaded to {dest_path}")
        else:
            raise Exception(f"Failed to download file: HTTP {response.status_code}")

# Download all files from a shared Google Drive folder (requires gdown)
def download_folder_from_gdrive(gdrive_url, dest_dir):
    try:
        import gdown
    except ImportError:
        raise ImportError("You must install gdown for folder downloading: pip install gdown")

    folder_id = get_gdrive_file_id(gdrive_url)
    gdown.download_folder(f"https://drive.google.com/drive/folders/{folder_id}", output=dest_dir, quiet=False, use_cookies=False)

# Setup: download necessary files and define paths
def setup():
    os.makedirs(LOCAL_DOWNLOAD_DIR, exist_ok=True)

    # Download files
    account_file_path = os.path.join(LOCAL_DOWNLOAD_DIR, "accounts.csv")
    user_file_path = os.path.join(LOCAL_DOWNLOAD_DIR, "users.txt")
    session_folder_path = os.path.join(LOCAL_DOWNLOAD_DIR, "sessions")
    
    download_file_from_gdrive(GDRIVE_ACCOUNT_FILE_URL, account_file_path)
    download_file_from_gdrive(GDRIVE_USER_FILE_URL, user_file_path)
    download_folder_from_gdrive(GDRIVE_SESSION_FOLDER_URL, session_folder_path)

    return account_file_path, user_file_path, session_folder_path

# Load account data from CSV file
def load_accounts(file_path):
    accounts = []
    with open(file_path, 'r') as file:
        reader = csv.reader(file)
        for line in reader:
            if line:
                try:
                    email, twitter_password, email_password, proxy, cookies = line
                    accounts.append({
                        'email': email,
                        'twitter_password': twitter_password,
                        'email_password': email_password,
                        'proxy': proxy
                    })
                except ValueError:
                    print(f"Skipping malformed line: {line}")
    return accounts

# Wait helper
def wait_for_element(page, selector, element_name, timeout=10000):
    print(f"Waiting for {element_name} element with selector: {selector}")
    element = page.wait_for_selector(selector, timeout=timeout)
    print(f"{element_name} found with selector: {selector}")
    return element

def extract_proxy_details(proxy_url):
    parsed_url = urlparse(proxy_url)
    return parsed_url.username, parsed_url.password, parsed_url.hostname, parsed_url.port

# Save session (cookies) to a file
def save_session(page, session_file):
    print(f"Saving session to {session_file}...")
    cookies = page.context.cookies()
    with open(session_file, 'w') as f:
        json.dump(cookies, f)
    print(f"Session saved with {len(cookies)} cookies.")

# Load session (cookies) from a file
def load_session(page, session_file):
    if Path(session_file).exists():
        print(f"Session file {session_file} found. Attempting to load cookies...")
        with open(session_file, 'r') as f:
            cookies = json.load(f)
        if cookies:
            page.context.add_cookies(cookies)
            print(f"Loaded {len(cookies)} cookies from session file.")
            return True
        else:
            print(f"Session file found but no cookies were found. A fresh login is required.")
            return False
    else:
        print(f"No session file found at {session_file}. A fresh login will be required.")
        return False

# Login to X (Twitter) using email and password
def login(page, account, session_file):
    print(f"Navigating to login page for {account['email']}...")
    page.goto('https://x.com/login')
    time.sleep(5)

    # Step 1: Check if session already exists
    cookies_loaded = load_session(page, session_file)

    # Step 2: If no cookies were loaded (fresh login), proceed with login
    if not cookies_loaded:
        print(f"No valid session found for {account['email']}. Proceeding with login...")

        # Step 3: Enter email/username
        try:
            email_input = wait_for_element(page, 'xpath=//*[@id="layers"]/div/div/div/div/div/div/div[2]/div[2]/div/div/div[2]/div[2]/div/div/div/div[4]/label/div/div[2]/div/input', "Email input field")
            email_input.type(account['email'])
            print("Email entered")
            time.sleep(2)
        except Exception as e:
            print(f"Error entering email: {str(e)}")
            raise

        # Step 4: Click Next button
        try:
            next_button = wait_for_element(page, 'xpath=//*[@id="layers"]/div/div/div/div/div/div/div[2]/div[2]/div/div/div[2]/div[2]/div/div/div/button[2]', "Next button")
            next_button.click()
            print("Clicked Next button")
            time.sleep(5)
        except Exception as e:
            print(f"Error clicking Next button: {str(e)}")
            raise

        # Step 5: Enter password
        try:
            password_input = wait_for_element(page, 'xpath=//*[@id="layers"]/div/div/div/div/div/div/div[2]/div[2]/div/div/div[2]/div[2]/div[1]/div/div/div[3]/div/label/div/div[2]/div[1]/input', "Password input field")
            password_input.type(account['twitter_password'])
            print("Password entered")
            time.sleep(3)
        except Exception as e:
            print(f"Error entering password: {str(e)}")
            raise

        # Step 6: Click Log in button
        try:
            login_button = wait_for_element(page, 'xpath=//*[@id="layers"]/div/div/div/div/div/div/div[2]/div[2]/div/div/div[2]/div[2]/div[2]/div/div[1]/div/div/button', "Log in button")
            login_button.click()
            print("Clicked Log in button")
            time.sleep(5)
        except Exception as e:
            print(f"Error clicking Log in button: {str(e)}")
            raise

        # Step 7: After logging in, save the session (cookies)
        save_session(page, session_file)
    else:
        print(f"Session already active for {account['email']}. Skipping login.")
        # Here we should load the homepage if session exists
        page.goto('https://x.com/home')
        time.sleep(5)

    # Save session after the page has loaded, to ensure up-to-date session
    save_session(page, session_file)

# Function to follow users from the list in the file
def follow_users_from_file(page, user_file):
    with open(user_file, 'r') as file:
        users_lines = file.readlines()

    for i, users_line in enumerate(users_lines):
        users_to_follow = users_line.split(",")
        users_to_follow = [user.strip() for user in users_to_follow]  # Clean up extra spaces

        print(f"Account {i + 1} will follow users: {', '.join(users_to_follow)}")
        
        for user in users_to_follow:
            try:
                print(f"Following user: {user}")
                page.goto(f'https://x.com/{user}')
                time.sleep(5)

                try:
                    follow_button = wait_for_element(page, (
                        'xpath',
                        '//*[@id="react-root"]/div/div/div[2]/main/div/div/div/div[1]/div/div[3]/div/div/div[1]/div[2]/div[1]/div[2]/div/div[1]/button'
                    ), "Follow button", timeout=15)
                    follow_button.click()
                    time.sleep(random.randint(0.3, 0.6))
                    print(f"Followed {user}")
                except Exception as e:
                    print(f"Error following {user}: {str(e)}")
                    continue  # Skip to next user if error occurs

            except Exception as e:
                print(f"Error visiting user profile {user}: {str(e)}")
                continue  # Skip to next user if error occurs

        # Wait for a while after following users
        time.sleep(5)

def main():
    account_file_path, user_file_path, session_folder_path = setup()
    accounts = load_accounts(account_file_path)

    with sync_playwright() as p:
        for account in accounts:
            proxy = account['proxy']
            username, password, host, port = extract_proxy_details(proxy)
            proxy_address = f"http://{host}:{port}"
            session_file = os.path.join(session_folder_path, f"{account['email']}_session.json")

            try:
                browser = p.chromium.launch(
                    headless=False,
                    proxy={"server": proxy_address, "username": username, "password": password},
                    timeout=60000
                )
                context = browser.new_context(ignore_https_errors=True)
                page = context.new_page()

                cookies_loaded = load_session(page, session_file)
                if not cookies_loaded:
                    login(page, account, session_file)

                follow_users_from_file(page, user_file_path)

                input("Press Enter to close the browser...")

            except Exception as e:
                print(f"Error for {account['email']}: {e}")
            finally:
                if 'browser' in locals():
                    browser.close()

if __name__ == "__main__":
    main()
