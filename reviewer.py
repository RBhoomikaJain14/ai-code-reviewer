import os
import sys
import json
import requests
import google.generativeai as genai
from dotenv import load_dotenv

# Load local environment variables (if any)
load_dotenv()

# Add directory of this script to path to import diff_parser
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from diff_parser import parse_diff

# Configure Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
IS_MOCK_MODE = not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here"

if not IS_MOCK_MODE:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("\n[Info] Running in MOCK MODE because GEMINI_API_KEY is not set or is placeholder.")
    print("Replace the key in '.env' to run real API calls.\n")

def get_mock_comments() -> list:
    """Returns static mock comments that match tests/test_diffs.diff for testing."""
    return [
        {
            "path": "src/auth.js",
            "line": 16,
            "body": "### WARNING: Hardcoded Credentials\nDo not hardcode secrets like JWT keys directly in the codebase. Use environment variables (e.g., `process.env.JWT_SECRET`) to store credentials securely."
        },
        {
            "path": "app.py",
            "line": 5,
            "body": "### WARNING: Missing Exception Handling\nCalling `requests.get()` without wrapping it in a `try-except` block can cause the application to crash if the network is down or the server returns an invalid status. Add error handling for `requests.exceptions.RequestException`."
        },
        {
            "path": "app.py",
            "line": 11,
            "body": "### WARNING: Resource Leak - Unclosed File\nThe file is opened using `open()` but never explicitly closed. Use a `with` statement instead to ensure the file is closed automatically after reading:\n```python\nwith open(image_path, 'rb') as f:\n    data = f.read()\n```"
        }
    ]

def analyze_diff_with_gemini(parsed_diff: dict) -> list:
    """
    Sends the parsed diff to the Gemini API to analyze for bugs, security risks,
    and code quality issues, returning a list of PR comments.
    """
    if IS_MOCK_MODE:
        mock_comments = get_mock_comments()
        validated_comments = []
        for comment in mock_comments:
            path = comment["path"]
            line = comment["line"]
            if path in parsed_diff:
                valid_lines = [c['line_number'] for c in parsed_diff[path]]
                if line in valid_lines:
                    validated_comments.append(comment)
        return validated_comments

    # Format the changes as a readable text block for the LLM
    diff_text = ""
    for filename, changes in parsed_diff.items():
        diff_text += f"\nFile: {filename}\n"
        for change in changes:
            diff_text += f"  Line {change['line_number']}: {change['content']}\n"
            
    if not diff_text.strip():
        return []

    # Prompt instructing the LLM on code review guidelines
    prompt = f"""
You are a senior, pragmatic software engineer conducting a code review on a pull request.
Review the following code additions and changes:

{diff_text}

Instructions:
1. Identify actual bugs, logic errors, resource leaks, security vulnerabilities (like hardcoded keys, SQL injections), and critical code quality issues.
2. Do not leave styling nits, spacing complaints, or trivial comments. Be positive, direct, and constructive.
3. CRITICAL: You can ONLY review and comment on the lines listed in the diff text above. Do not comment on line numbers that are not in the list for that file.
4. Response Format: You must respond ONLY with a JSON object containing a list of comments, matching this schema:
{{
  "comments": [
    {{
      "path": "filename",
      "line": line_number,
      "body": "Your review comment here in Markdown. Explain the problem, why it matters, and provide a code snippet suggesting how to fix it."
    }}
  ]
}}
If the code looks perfect and there are no issues, return:
{{
  "comments": []
}}
"""

    model = genai.GenerativeModel('gemini-1.5-flash')
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        result = json.loads(response.text)
        comments = result.get("comments", [])
        
        # Post-validation: Ensure comments are actually on lines that exist in the diff
        validated_comments = []
        for comment in comments:
            path = comment.get("path")
            line = comment.get("line")
            body = comment.get("body")
            
            if not path or not line or not body:
                continue
                
            if path in parsed_diff:
                valid_lines = [c['line_number'] for c in parsed_diff[path]]
                if line in valid_lines:
                    validated_comments.append(comment)
                else:
                    print(f"Skipping hallucinated comment on {path}:{line} (line not in diff additions)")
            else:
                print(f"Skipping hallucinated comment on non-existent file {path}")
                
        return validated_comments
        
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return []

def get_pr_diff(repo: str, pr_number: int, token: str) -> str:
    """Fetches the raw diff content of the pull request using GitHub API."""
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
    """Submits the AI code review comments back to the GitHub PR."""
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
        event = "COMMENT"
    else:
        review_body += "LGTM! I reviewed the code changes and found no issues."
        event = "COMMENT"
        
    payload = {
        "commit_id": commit_sha,
        "body": review_body,
        "event": event,
        "comments": github_comments
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 201:
        print(f"Successfully posted review with {len(github_comments)} comments.")
    else:
        print(f"Failed to post review: {response.status_code} - {response.text}")
        response.raise_for_status()

def main():
    token = os.environ.get("GITHUB_TOKEN")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    
    # Check if we are running in GitHub Actions context
    if event_path and os.path.exists(event_path):
        print("Running inside GitHub Actions context.")
        if not token:
            print("Error: GITHUB_TOKEN is not defined. Cannot interact with GitHub.")
            sys.exit(1)
            
        with open(event_path, "r", encoding="utf-8") as f:
            event_data = json.load(f)
            
        repo = os.environ.get("GITHUB_REPOSITORY")
        pr_number = event_data.get("pull_request", {}).get("number")
        commit_sha = event_data.get("pull_request", {}).get("head", {}).get("sha")
        
        if not repo or not pr_number or not commit_sha:
            print(f"Error: Missing required event parameters (repo: {repo}, pr: {pr_number}, commit: {commit_sha})")
            sys.exit(1)
            
        print(f"Processing PR #{pr_number} on {repo} (commit: {commit_sha[:7]})...")
        
        try:
            print("Fetching PR diff...")
            diff_content = get_pr_diff(repo, pr_number, token)
            
            print("Parsing diff...")
            parsed_diff = parse_diff(diff_content)
            
            print("Running Gemini code analysis...")
            comments = analyze_diff_with_gemini(parsed_diff)
            
            print("Submitting review to GitHub...")
            submit_github_review(repo, pr_number, commit_sha, comments, token)
            
            print("Review workflow completed successfully!")
            
        except Exception as e:
            print(f"Error during PR review: {e}")
            sys.exit(1)
    else:
        print("Running locally. Performing self-test simulation.")
        # Local run fallback simulation
        diff_file_path = os.path.join(os.path.dirname(__file__), "tests", "test_diffs.diff")
        if not os.path.exists(diff_file_path):
            print(f"Error: local test diff not found at {diff_file_path}")
            sys.exit(1)
            
        with open(diff_file_path, "r", encoding="utf-8") as f:
            diff_content = f.read()
            
        parsed_diff = parse_diff(diff_content)
        print(f"Parsed files: {list(parsed_diff.keys())}")
        comments = analyze_diff_with_gemini(parsed_diff)
        print(f"Generated {len(comments)} comments in local run.")
        for i, comment in enumerate(comments, 1):
            print(f"\n[{i}] FILE: {comment['path']} | LINE: {comment['line']}")
            print(f"{comment['body']}\n")

if __name__ == "__main__":
    main()
API_KEY = "12345-secret-key-abcdef"
