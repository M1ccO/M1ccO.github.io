# NTX Setup Manager - Git How To (Windows)

This file gives you copy-paste commands for the most common Git tasks.

## 1) First-time setup (only once per PC)

Run in PowerShell:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## 2) Start from zero on a new machine (recommended)

Use this when the repository already exists on GitHub.

```powershell
git clone https://github.com/<your-user>/<your-repo>.git
cd "NTX Setup Manager"
git pull origin master
```

Notes:
- `git clone` downloads the full project.
- `git pull` gets latest updates.

## 3) Daily workflow (edit, save, upload)

Run inside your project folder:

```powershell
git status
git add .
git commit -m "Describe what changed"
git push origin master
```

## 4) Get latest changes before you start working

```powershell
git pull origin master
```

## 5) If this folder is local only and not on GitHub yet

This project already has a local Git repo. To publish it the first time:

```powershell
git remote add origin https://github.com/<your-user>/<your-repo>.git
git branch -M master
git push -u origin master
```

After that, normal daily use is:

```powershell
git add .
git commit -m "Your message"
git push
```

## 6) Quick meaning of the key commands

- `git clone`: download a repo to your PC
- `git pull`: update your local repo from GitHub
- `git add`: stage changed files for the next commit
- `git commit`: save a snapshot in your local repo
- `git push`: upload your commits to GitHub

## 7) Useful checks

```powershell
git status
git log --oneline -10
git remote -v
```
