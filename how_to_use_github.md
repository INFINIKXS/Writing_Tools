# How to Use GitHub: The Essential Guide

Git is the local version control system running on your computer, while GitHub is the cloud platform where you host and collaborate on your Git repositories. This guide covers the most common operations you'll need for everyday development.

## 1. Getting Started (One-Time Setup)

Before using Git for the first time, you need to tell it who you are. These details will be attached to every commit you make.

```bash
# Set your name and email
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# Verify your settings
git config --list
```

> [!TIP]
> Setting up SSH keys with GitHub is highly recommended so you don't have to enter your password every time you push code.

## 2. Starting a Project

There are two main ways to start a project: creating a new one locally, or downloading an existing one from GitHub.

### Option A: Clone an Existing Repository
Downloads a project from GitHub to your local machine.

```bash
# Clone a repository using HTTPS
git clone https://github.com/username/repository.git

# Move into the project directory
cd repository
```

### Option B: Initialize a New Local Repository
Starts a brand new Git project in an existing folder.

```bash
# Initialize git in the current directory
git init

# Link it to an empty repository you created on GitHub
git remote add origin https://github.com/username/repository.git
```

## 3. The Daily Workflow (Save & Upload)

This is the loop you will use 90% of the time: **Modify -> Stage -> Commit -> Push**.

### Step 1: See What Changed
Always check the status of your files before staging.

```bash
# Show modified, staged, and untracked files
git status

# See exactly what lines of code changed
git diff
```

### Step 2: Stage Your Changes
Staging tells Git which modified files you want to include in your next commit.

```bash
# Stage a specific file
git add filename.js

# Stage ALL changed and new files in the current directory
git add .
```

### Step 3: Commit Your Changes
A commit takes a "snapshot" of your staged files and saves it locally.

```bash
# Commit with a descriptive message
git commit -m "Add login validation logic"
```

### Step 4: Push to GitHub
Upload your local commits to the remote repository on GitHub.

```bash
# Push to the current branch (if it already exists on GitHub)
git push

# Push a NEW branch to GitHub for the first time
git push -u origin branch-name
```

## 4. Working with Branches

Branches allow you to work on features or fixes in isolation without affecting the stable `main` branch.

### Creating and Switching Branches
```bash
# See all local branches (the current one has a *)
git branch

# Create a new branch and switch to it immediately
git checkout -b feature/new-login

# Switch back to an existing branch
git checkout main
```

### Merging Branches
Once your feature is done, you merge it back into the main branch.

```bash
# 1. First, make sure you are on the branch you want to merge INTO
git checkout main

# 2. Merge the feature branch into main
git merge feature/new-login

# 3. (Optional) Delete the feature branch locally if you're done with it
git branch -d feature/new-login
```

> [!NOTE]
> In most team environments, instead of merging locally via terminal, you will push your branch to GitHub and open a **Pull Request (PR)** so others can review your code before it merges into main.

## 5. Staying Up to Date

If you are working with others (or from multiple computers), you need to download their changes.

```bash
# Download changes from GitHub AND merge them into your current branch
git pull

# Download latest information about branches/commits without merging yet
git fetch
```

## 6. Undoing Mistakes

We all make mistakes. Here is how to fix the most common Git accidents.

### "I modified a file, but I want to discard my changes and go back to the last commit."
```bash
# Discard changes in a specific file
git restore filename.js

# Discard ALL uncommitted changes in the repository
git restore .
```

### "I accidentally staged a file with `git add`, but I don't want to commit it yet."
```bash
# Unstage a file (keeps your modifications intact)
git restore --staged filename.js
```

### "I want to change the message of the very last commit I made."
```bash
# Opens your default terminal editor to change the last commit message
git commit --amend

# Or supply the new message directly inline
git commit --amend -m "Corrected commit message"
```

### "I committed something, but I want to undo that commit entirely."
```bash
# UNDO the last commit, but KEEP all your changed files unstaged on your machine
git reset HEAD~1

# WARNING: UNDO the last commit and DESTROY ALL CHANGES you made
git reset --hard HEAD~1
```

## 7. Useful Diagnostic Commands

```bash
# View the history of commits
git log

# View a more compact list of commits (one line per commit)
git log --oneline

# Find out who wrote a specific line in a file
git blame filename.js
```

> [!CAUTION]
> Never run `git push --force` unless you are absolutely certain of what you are doing. It forcibly overwrites the remote repository with your local state, which can permanently delete your teammates' work.
