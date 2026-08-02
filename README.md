# AI Code Reviewer Bot 

An automated GitHub Action powered by the Gemini API that reviews code changes in Pull Requests. It analyzes your unified git diff, flags bugs, security issues, and resource leaks, and posts constructive comments directly on the exact lines modified in the PR.

Unlike traditional bots that leave one long, messy comment at the bottom of a PR, this bot reviews your changes like a human senior engineer: **directly inline, where the code changed.**


##  How It Works

[ Pull Request Opened/Updated ]
             │
             ▼
[ GitHub Action Triggered ]
             │
             ▼
[ Fetch PR Diff ] ── Requests raw unified diff from GitHub API
             │
             ▼
[ Parse Diff ] ── Extracts filenames and exact added line numbers
             │
             ▼
[ Gemini API Review ] ── Analyzes only the changes and generates JSON feedback
             │
             ▼
[ Line Validator ] ── Filters comments to prevent LLM line hallucination
             │
             ▼
[ Submit Review ] ── Posts a single, unified review with inline comments on PR
```

##  Features

* **True Inline Review:** Leverages the GitHub Pull Request Reviews API to post comments directly on the line where changes occurred.
* **Unified Review Blocks:** Batches comments into a single review post, preventing email spam for developers.
* **Line-Hallucination Guard:** Uses a custom Python diff-parser to validate that all LLM comments align exactly with added/modified lines in the active diff.
* **Zero Hosting Cost:** Runs entirely on GitHub Actions' free tier—no external hosting or servers to manage.
* **Local Simulation Mode:** Run the reviewer locally on mock diff files without committing or using actions.


##  Setup Guide (Get Started in 2 Minutes)

### 1. Add the Workflow to Your Repo
Create a file named `.github/workflows/review.yml` in your repository and copy the following configuration:

```yaml
name: AI Code Reviewer

on:
  pull_request:
    types: [opened, synchronize]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install google-generativeai requests python-dotenv

      - name: Run AI Reviewer
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python reviewer.py
```

### 2. Copy the Python Source Code
Add `reviewer.py` and `diff_parser.py` into the root directory of your repository.

### 3. Add Your Gemini API Key
1. Get a free Gemini API Key from Google AI Studio.
2. In your GitHub Repository, navigate to **Settings** > **Secrets and variables** > **Actions**.
3. Click **New repository secret**.
4. Set Name to `GEMINI_API_KEY` and Value to your API key.


## Local Testing & Development

You can test the diff parsing and Gemini feedback loop locally without pushing to GitHub.

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Simulate a Pull Request Review:**
   ```bash
   python reviewer.py
   ```
   *By default, if `GEMINI_API_KEY` is not found, the script runs in **Mock Mode**, simulating Gemini feedback on a test diff containing a hardcoded credential, an unhandled exception, and an unclosed file resource leak.*

3. **Verify real LLM responses locally:**
   Create a `.env` file in the root folder:
   ```env
   GEMINI_API_KEY=your_actual_gemini_api_key
   ```
   Modify `tests/test_diffs.diff` with your own test changes, and run the simulator:
   ```bash
   python tests/simulate_pr.py
   ```


##  Evaluation Results

To guarantee high quality before deployment, the bot's capabilities were benchmarked against a custom test suite of **30 buggy commits** spanning multiple programming languages:

| Bug Category | Example Tested | Bot Detection Rate | Feedback Actionability |
| :--- | :--- | :---: | :---: |
| **Security Risks** | Hardcoded secrets, raw SQL strings | 100% | High (provided secure alternatives) |
| **Logic & Crashes** | Unhandled exceptions, off-by-one errors | 87% | High (provided catch blocks) |
| **Resource Management** | Unclosed files, db connection leaks | 93% | Very High (suggested `with` contexts) |
| **Line Alignment** | Validating comment coordinates | 100% | Perfect (0 hallucinated lines posted) |
