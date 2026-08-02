import re

def parse_diff(diff_content: str) -> dict:
    """
    Parses a unified diff string and returns a dictionary mapping
    filename -> list of dicts with keys 'line_number' and 'content' for added lines.
    """
    files = {}
    current_file = None
    new_line_num = 0
    
    lines = diff_content.splitlines()
    for line in lines:
        # Detect new file header
        if line.startswith('+++ '):
            # Extract filename, strip 'b/' prefix if present
            match = re.match(r'^\+\+\+\s+b/(.*)$', line)
            if not match:
                match = re.match(r'^\+\+\+\s+(.*)$', line)
            
            if match:
                current_file = match.group(1)
                files[current_file] = []
                new_line_num = 0
            continue
        
        # Detect hunk header: @@ -old_start,old_count +new_start,new_count @@
        if line.startswith('@@ '):
            hunk_match = re.match(r'^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@', line)
            if hunk_match:
                new_line_num = int(hunk_match.group(1))
            continue
        
        # Parse hunk contents
        if current_file is not None:
            if line.startswith('+') and not line.startswith('+++'):
                files[current_file].append({
                    'line_number': new_line_num,
                    'content': line[1:]
                })
                new_line_num += 1
            elif line.startswith('-') and not line.startswith('---'):
                # Deleted lines don't exist in the new file, so we skip them
                pass
            elif line.startswith(' ') or line == '':
                # Context lines increment line counter in the new file
                new_line_num += 1
                
    # Filter out empty files or deletions (/dev/null)
    return {k: v for k, v in files.items() if v and k != "/dev/null"}

if __name__ == "__main__":
    # Small self-test
    import sys
    test_diff = """diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def hello():
-    print("old")
+    print("new")
+    return True
"""
    result = parse_diff(test_diff)
    print("Parsed test diff:", result)
