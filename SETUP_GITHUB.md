# GitHub Setup Guide

This guide explains how to upload this project to your GitHub repository.

## Prerequisites

- A GitHub account
- Git installed on your system

## Step-by-Step Instructions

### 1. Create a New Repository on GitHub

1. Go to [GitHub](https://github.com)
2. Log in to your account
3. Click the **+** button in the top-right corner
4. Select **New repository**
5. Enter repository details:
   - **Repository name**: `DAZ` (or your preferred name)
   - **Description**: GameServer Web Interface - Self-hosted game server management
   - **Visibility**: Public (so users can download the install script)
   - **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click **Create repository**

### 2. Initialize Git in Your Project

```bash
cd /home/tim/DAYZ/gameserver-webinterface

# Initialize git repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: GameServer Web Interface v1.0"
```

### 3. Link to GitHub Repository

Replace `YOUR_USERNAME` with your actual GitHub username:

```bash
# Add remote repository
git remote add origin https://github.com/timvida/DAZ.git

# Verify remote
git remote -v
```

### 4. Push to GitHub

```bash
# Push to main branch
git branch -M main
git push -u origin main
```

### 5. Verify Upload

1. Go to your repository: `https://github.com/timvida/DAZ`
2. Verify all files are uploaded
3. Check that the README displays correctly

## Important Files for Users

After uploading to GitHub, users can install using:

```bash
wget https://raw.githubusercontent.com/timvida/DAZ/main/install.sh
chmod +x install.sh
./install.sh
```

The install script will automatically:
- Clone the repository
- Install all dependencies
- Set up the web interface

## GitHub Repository Structure

```
DAZ/
├── .gitignore              # Ignores venv, databases, etc.
├── LICENSE                 # MIT License
├── README.md               # Main documentation
├── SETUP_GITHUB.md         # This file
├── install.sh              # Main installation script
├── requirements.txt        # Python dependencies
├── config.py               # Configuration
├── database.py             # Database models
├── app.py                  # Flask application
├── steam_utils.py          # SteamCMD utilities
├── server_manager.py       # Server management
├── static/
│   ├── css/style.css       # Dark theme styles
│   └── js/main.js          # Frontend JavaScript
└── templates/
    ├── base.html           # Base template
    ├── install.html        # Installation wizard
    ├── login.html          # Login page
    └── dashboard.html      # Dashboard
```

## Update Repository

When you make changes to the code:

```bash
# Check what changed
git status

# Add modified files
git add .

# Commit changes
git commit -m "Description of changes"

# Push to GitHub
git push
```

## Creating a Release

To create a version release:

1. Go to your repository on GitHub
2. Click **Releases** on the right sidebar
3. Click **Create a new release**
4. Create a tag (e.g., `v1.0.0`)
5. Fill in release details
6. Click **Publish release**

## Making the Project Public

Ensure your repository is set to **Public** so users can:
- Download the install script directly
- Clone the repository
- View the source code

Go to Settings → General → Danger Zone → Change repository visibility

## Support and Issues

Enable GitHub Issues so users can report problems:
1. Go to repository **Settings**
2. Scroll to **Features**
3. Check **Issues**

## Done!

Your GameServer Web Interface is now available on GitHub!

Users can install it with just one command:
```bash
wget https://raw.githubusercontent.com/timvida/DAZ/main/install.sh && chmod +x install.sh && ./install.sh
```
