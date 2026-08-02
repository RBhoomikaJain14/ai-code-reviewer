import os
import sys

# Add parent directory to path so we can import diff_parser and reviewer
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from diff_parser import parse_diff
from reviewer import analyze_diff_with_gemini

def main():
    diff_file_path = os.path.join(os.path.dirname(__file__), "test_diffs.diff")
    if not os.path.exists(diff_file_path):
        print(f"Error: test diff file not found at {diff_file_path}")
        return
    
    with open(diff_file_path, "r", encoding="utf-8") as f:
        diff_content = f.read()
    
    print("Parsing diff...")
    parsed_diff = parse_diff(diff_content)
    
    print("\n--- Review Process Started ---")
    comments = analyze_diff_with_gemini(parsed_diff)
    print(f"Review completed. Generated {len(comments)} comments:\n")
    
    for i, comment in enumerate(comments, 1):
        print(f"[{i}] FILE: {comment['path']} | LINE: {comment['line']}")
        print(f"--- Comment Content ---\n{comment['body']}\n-----------------------\n")

if __name__ == "__main__":
    main()
