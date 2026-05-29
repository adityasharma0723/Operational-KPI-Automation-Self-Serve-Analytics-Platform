# 📊 Operational KPI Automation & Self-Serve Analytics Platform

Welcome to the workspace for the **Operational KPI Automation & Self-Serve Analytics Platform**! 

This repository has been prepared and configured with the core programming tools required for the project. Below is the status of your development environment, along with easy instructions for launching your workspace and completing the final manual tool installations.

---

## 🛠️ Environment Status & Setup Checklist

Here is the status of the environment components that have been verified or installed:

| Component | Status | Details | Action Required |
| :--- | :---: | :--- | :--- |
| **Python** | ✅ Installed | Python `3.14.0` | None (Ready to use) |
| **Jupyter Notebook** | ✅ Installed | `notebook` package successfully configured | None (Ready to use) |
| **Data Libraries** | ✅ Installed | `pandas`, `matplotlib`, `seaborn`, `scipy`, `openpyxl` | None (Ready to use) |
| **Git Version Control** | ✅ Installed | `git version 2.53.0.windows.1` | None (Ready to use) |
| **DB Browser for SQLite** | ⏳ Manual Step | Visual SQL editor | Download & install |
| **Power BI Desktop** | ⏳ Manual Step | BI & Dashboarding tool | Download & install |
| **GitHub Account** | ⏳ Manual Step | Code hosting & portfolio sharing | Sign up & log in |

---

## 🚀 Quick Start: Launching Jupyter Notebook

To start writing Python code in blocks and running interactive analyses, you can launch Jupyter Notebook directly from this directory:

1. Open **PowerShell** or **Command Prompt** in this directory:
   `c:\Users\addis\OneDrive\Desktop\ML Projects\Operational KPI Automation & Self-Serve Analytics Platform`
2. Run the following command:
   ```bash
   jupyter notebook
   ```
3. A browser tab will open automatically, allowing you to create new `.ipynb` notebooks and execute code interactively.

---

## 📥 Guide for Manual Installations

Since some of the tools are desktop graphical interfaces, you will need to perform the following short installations:

### 1. 🗄️ DB Browser for SQLite
* **What it does**: A lightweight, visual tool to browse SQLite database files, run SQL queries, and edit tables without setting up a database server.
* **Download Link**: [sqlitebrowser.org/dl/](https://sqlitebrowser.org/dl/)
* **Recommended Version**: Download the **Standard Installer** for 64-bit Windows.

### 2. 📊 Power BI Desktop
* **What it does**: Microsoft's business intelligence and dashboarding tool where you will create your interactive visuals, KPIs, and reports.
* **Download Link**: [microsoft.com/power-bi](https://powerbi.microsoft.com/desktop/)
* **Recommended Version**: Click **Download Free** or download it from the **Microsoft Store** on Windows for automatic background updates.

### 3. 🐱 GitHub Account
* **What it does**: A cloud-based platform to store, version-control, and showcase your codebase and projects.
* **Action**:
  1. Visit [github.com](https://github.com/) and click **Sign Up** to create a free account.
  2. To link your local Git with your GitHub account, run these commands in your terminal:
     ```bash
     git config --global user.name "Your Name"
     git config --global user.email "your.email@example.com"
     ```

---

## 🧪 Verification Script
We have added a simple verification script `verify_setup.py` in this workspace. You can run it anytime to confirm that all Python libraries are correctly loaded and working:
```bash
python verify_setup.py
```
