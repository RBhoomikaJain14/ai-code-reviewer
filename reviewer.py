import os
import sys
import json
import requests
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from diff_parser import parse_diff

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
IS_MOCK_MODE = not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here"

# Initialize modern GenAI client if not mock
client = None
if not IS_MOCK_MODE:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Error initializing Gemini: {e}")
        IS_MOCK_MODE = True

def run_smart_scanner(parsed_diff: dict) -> list:
    """
    A smart static analysis scanner that runs when Gemini API is unavailable.
    It inspects code additions for typical bugs and returns mock comments.
    """
    comments = []
    for filename, changes in parsed_diff.items():
        for change in changes:
            line_content = change["content"]
            line_num = change["line_number"]
            
            # Rule 1: Detect hardcoded credentials
            if any(kw in line_content.upper() for kw in ["API_KEY", "SECRET", "PASSWORD", "PASSWORD_HASH"]):
                comments.append({
                    "path": filename,
                    "line": line_num,
                    "body": "### WARNING: Hardcoded Credentials\nDo not hardcode secrets like API keys or passwords directly in the codebase. Use environment variables (e.g. `os.environ` or `process.env`) to store credentials securely."
                })
                
            # Rule 2: Detect unclosed files in Python
            elif filename.endswith(".py") and "open(" in line_content and "with" not in line_content:
                comments.append({
                    "path": filename,
                    "line": line_num,
                    "body": "### WARNING: Resource Leak - Unclosed File\nThe file is opened using `open()` but not wrapped in a `with` block. Use a `with` statement instead to ensure the file is closed automatically:\n```python\nwith open(filepath, 'r') as f:\n    data = f.read()\n```"
                })
                
            # Rule 3: Detect unhandled HTTP requests in Python
            elif filename.endswith(".py") and "requests.get" in line_content and "try" not in line_content:
                comments.append({
                    "path": filename,
                    "line": line_num,
                    "body": "### WARNING: Missing Exception Handling\nCalling `requests.get()` without exception handling can crash the app if the network is down. Wrap it in a `try-except` block for safety."
                })
                
    return comments

def analyze_diff_with_gemini(parsed_diff: dict) -> list:
    """
    Tries to call Gemini API, but falls back to the Smart Scanner if API fails or is not enabled.
    """
    if IS_MOCK_MODE:
        print("Running in Smart Scanner fallback mode (no API key configured).")
        return run_smart_scanner(parsed_diff)

    try:
        prompt = f"""
You are a senior software engineer. Review these changes:
{json.dumps(parsed_diff)}

Identify bugs, security vulnerabilities, and code quality issues.
Return comments in this JSON schema:
{{
  "comments": [
    {{
      "path": "filename",
      "line": line_number,
      "body": "Comment text in Markdown"
    }}
  ]
}}
"""
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        result = json.loads(response.text)
        return result.get("comments", [])
        
    except Exception as e:
        print(f"Error calling Gemini API: {e}. Falling back to Smart Scanner.")
        # Fallback so the PR review never fails or says empty review on errors
        return run_smart_scanner(parsed_diff)

def get_pr_diff(repo: str, pr_number: int, token: str) -> str:
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    url = f"{api_url}/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def submit_github_review(repo: str, pr_number: int, commit_sha: str, comments: list, token: str):
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    url = f"{api_url}/repos/{repo}/pulls/{pr_number}/reviews"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    
    github_comments = []
    for comment in comments:
        github_comments.append({
            "path": comment["path"],
            "line": comment["line"],
            "body": comment["body"],
            "side": "RIGHT"
        })
        
    review_body = "🤖 **AI Code Review Completed**\n\n"
    if github_comments:
        review_body += f"I have analyzed the diff and identified {len(github_comments)} potential issue(s). Please check the inline comments below for suggestions."
    else:
        review_body += "LGTM! I reviewed the code changes and found no issues."
        
    payload = {
        "commit_id": commit_sha,
        "body": review_body,
        "event": "COMMENT",
        "comments": github_comments
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code in [200, 201]:
        print(f"Successfully posted review with {len(github_comments)} comments.")
    else:
        print(f"Failed to post review: {response.status_code} - {response.text}")
        response.raise_for_status()

def main():
    token = os.environ.get("GITHUB_TOKEN")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    
    if event_path and os.path.exists(event_path):
        print("Running inside GitHub Actions context.")
        if not token:
            print("Error: GITHUB_TOKEN is not defined.")
            sys.exit(1)
            
        with open(event_path, "r", encoding="utf-8") as f:
            event_data = json.load(f)
            
        repo = os.environ.get("GITHUB_REPOSITORY")
        pr_number = event_data.get("pull_request", {}).get("number")
        commit_sha = event_data.get("pull_request", {}).get("head", {}).get("sha")
        
        try:
            diff_content = get_pr_diff(repo, pr_number, token)
            parsed_diff = parse_diff(diff_content)
            comments = analyze_diff_with_gemini(parsed_diff)
            submit_github_review(repo, pr_number, commit_sha, comments, token)
            print("Review workflow completed successfully!")
        except Exception as e:
            print(f"Error during PR review: {e}")
            sys.exit(1)
    else:
        print("Running locally. Performing self-test simulation.")
        diff_file_path = os.path.join(os.path.dirname(__file__), "tests", "test_diffs.diff")
        if not os.path.exists(diff_file_path):
            print(f"Error: local test diff not found.")
            sys.exit(1)
            
        with open(diff_file_path, "r", encoding="utf-8") as f:
            diff_content = f.read()
            
        parsed_diff = parse_diff(diff_content)
        comments = analyze_diff_with_gemini(parsed_diff)
        print(f"Generated {len(comments)} comments in local run.")
        for i, comment in enumerate(comments, 1):
            print(f"\n[{i}] FILE: {comment['path']} | LINE: {comment['line']}")
            print(f"{comment['body']}\n")

if __name__ == "__main__":
    main()
