# MSU Vision 2020 - Exhaustive QA Testing Manual

This manual provides the **exact data** to copy and paste to test the complete lifecycle of the application. It explicitly uses **all 13 PDF files** your friend created in the `Test_data` folder to ensure full coverage across every single department!

---

## Phase 0: Bulk User Setup (Do This First)

To make testing easy, I have prepared a `bulk_users_test.csv` file inside `D:\MSU VISION 2020\MSU2020\test_data\`.

### Step 1: Upload the CSV
1. **Log in as:** `demo` (Foundation Admin)
2. **Navigate to:** Click on **Governance** in the left sidebar menu.
3. Scroll down until you see the **CSV Upload** or Bulk Profile Form section.
4. Click "Choose File", select `D:\MSU VISION 2020\MSU2020\test_data\bulk_users_test.csv`, and upload/confirm it.

### Step 2: Set Test Passwords
Because bulk-imported users are created with "unusable passwords" (for security), you need to give them a manual password for testing. 

*After you successfully upload the CSV in Step 1*, open your terminal in `D:\MSU VISION 2020\MSU2020\` and run this command to set their passwords to `Tester@123`:
```bash
.\.venv\Scripts\python.exe manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); users = User.objects.filter(username__endswith='_test'); [u.set_password('Tester@123') or u.save() for u in users]; print(f'Passwords set for {users.count()} test users!')"
```

**Your Test Accounts are now ready!** You can log into any of these accounts with the password `Tester@123`:
- `hod_test` (HOD)
- `gov_test` (Governance)
- `lead_test` (Project Lead)
- `finance_test` (Finance)
- `donor_test` (Donor)

---

## Phase 1: Creating Department Needs (HOD)

We will test the platform by creating **8 separate Needs**—one for each department—to utilize every single `Final_...` PDF.

1. **Log in as:** `hod_test` (Password: `Tester@123`)
2. **Navigate to:** **Needs** > **New Need**

**Repeat the process to create all 8 Needs using the data below:**

| Department | Title to Copy | Target Amount (₹) | PDF to Upload | Note |
|------------|---------------|-------------------|---------------|------|
| **Computer Eng.** | `Computer Engineering Lab Upgrade` | `1500000` | `Final_Computer_Engineering.pdf` | Over threshold (Goes to Governance) |
| **Mechanical Eng.** | `Mechanical Workshop Tools` | `800000` | `Final_Mechanical_Engineering.pdf` | Standard Admin Approval |
| **Applied Math** | `Mathematics Computing Cluster` | `500000` | `Final_Applied_Mathematics.pdf` | Standard Admin Approval |
| **Chemical Eng.** | `Chemical Process Simulators` | `1200000` | `Final_Chemical_Engineering.pdf` | Over threshold (Goes to Governance) |
| **Civil Eng.** | `Civil Structural Testing Rigs` | `900000` | `Final_Civil_Engineering.pdf` | Standard Admin Approval |
| **Electrical Eng.** | `Electrical Grid Simulators` | `750000` | `Final_Electrical_Engineering.pdf` | Standard Admin Approval |
| **Electronics (ECE)** | `Electronics & Comm Analyzers` | `1400000` | `Final_Electronics_&_Communication.pdf` | Over threshold (Goes to Governance) |
| **Info. Tech (IT)** | `IT Networking Infrastructure` | `600000` | `Final_Information_Technology.pdf` | Standard Admin Approval |

*(Note: For all of them, you can also upload the generic `Detailed_Needs.pdf` file as a secondary attachment if the form allows multiple uploads, or just use the department-specific one).*

---

## Phase 2: Cataloging & Approvals (Admin & Gov)

1. **Log in as:** `demo` (Foundation Admin)
2. **Navigate to:** **Needs** 
3. **Action:** Click **Catalog Need** on all 8 Needs. 
   - *3 Needs (Computer, Chemical, Electronics) become `Pending Governance`.*
   - *5 Needs become `Cataloged` (Standard).*
4. **Log in as:** `gov_test` (Governance Team)
5. **Navigate to:** **Governance** (Left Sidebar)
6. **Action:** Approve the 3 high-value Needs. 

---

## Phase 3: Project Creation (Admin)

1. **Log in as:** `demo` (Foundation Admin)
2. **Navigate to:** **Needs** > Open any approved Need.
3. **Action:** Click **Convert to Project**.
4. **Copy & Paste Data:**
   - **Project Lead:** Assign `lead_test`
   - **Budget:** Match the Target Amount (e.g., `1500000`)
   - **Project Documentation Upload:** Select `D:\MSU VISION 2020\Test_data\Expenses_Donors_Projects_Needs_Funding\Detailed_Projects.pdf`
5. **Action:** Click **Create Project**. (Repeat for as many Needs as you want to test).

---

## Phase 4: Donors & Finance (Finance Controller)

1. **Log in as:** `finance_test` (Finance Controller)
2. **Navigate to:** **Funding** > **Contributions** > **Add Contribution**
3. **Copy & Paste Data:**
   - **Donor:** Select `donor_test`
   - **Amount:** `25000`
   - **Currency:** `USD`
   - **Project Allocation:** Link it to a newly created project.
   - **Upload Receipt:** Select `D:\MSU VISION 2020\Test_data\Expenses_Donors_Projects_Needs_Funding\Detailed_Funding.pdf`
4. **Action:** Click **Save**.

---

## Phase 5: Expenses (Project Lead)

1. **Log in as:** `lead_test` (Project Lead)
2. **Navigate to:** **My Projects** > Open a Project.
3. **Action:** Go to the **Expenses** tab and click **Request Expense**.
4. **Copy & Paste Data:**
   - **Amount:** `50000`
   - **Upload Expense Report:** Select `D:\MSU VISION 2020\Test_data\Expenses_Donors_Projects_Needs_Funding\Detailed_Expenses.pdf`
5. **Action:** Click **Submit Request**. The Finance Controller can now approve it.

---

## Phase 6: Events (Admin)

1. **Log in as:** `demo` (Foundation Admin)
2. **Navigate to:** **Events** > **New Event**
3. **Copy & Paste Data:**
   - **Title:** `Cross-Departmental Alumni Networking`
   - **Upload Event Details:** Select `D:\MSU VISION 2020\Test_data\Expenses_Donors_Projects_Needs_Funding\Detailed_Events.pdf`
4. **Action:** Save and publish the event.
