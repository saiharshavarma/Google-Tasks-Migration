# Google Tasks Migration (Account 1 work -> Account 2 personal)

This script copies Google Tasks from one Google account to another.

It copies:

- Task lists (example: "My Tasks")
- Tasks inside each list
- Completed tasks (included)
- Due dates (including all-day style due dates)
- Notes

It does NOT delete anything in the source account. It only reads from Account 1 and writes new copies into Account 2.

## What you need

- Python 3.9+ installed
- Access to both Google accounts (Account 1 work and Account 2 personal)
- A Google Cloud project with:
  - Google Tasks API enabled
  - OAuth configured (Desktop app client)
  - Test users added (both accounts), if you are in Testing mode
- The OAuth client file downloaded as `credentials.json`

## Folder layout

Put these files in one folder:

- `transfer_tasks.py`
- `credentials.json`

The script will create these files automatically when it runs:

- `token_source.json` (OAuth token for Account 1)
- `token_dest.json` (OAuth token for Account 2)
- `checkpoint_copied_task_ids.json` (progress checkpoint so you can resume safely)

## Step 1: Google Cloud setup (quick checklist)

In Google Cloud Console (same project throughout):

1. Enable API
   - APIs & Services -> Library -> enable Google Tasks API

2. Configure OAuth (Google Auth Platform)
   - Branding: fill app name + emails
   - Audience: External, keep it in Testing if you want minimal setup
   - Test users: add Account 1 email and Account 2 email
   - Data Access: add scope `https://www.googleapis.com/auth/tasks`

3. Create OAuth client
   - Clients -> Create OAuth client -> Desktop app
   - Download JSON and rename to `credentials.json`

## Step 2: Install dependencies

Run in your script folder:

```bash
pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

## Step 3: Run the script

```bash
python transfer_tasks.py
```

You will authorize twice:

1. SOURCE login: sign in with Account 1 (work) and allow access
2. DEST login: sign in with Account 2 (personal) and allow access

After it finishes, verify in:

- Google Tasks (tasks.google.com) while signed into Account 2
- Google Calendar with the Tasks calendar enabled (optional)

## Important notes

_It will not delete tasks in Account 1_

The script only lists task lists and tasks from Account 1. It does not call any delete or update methods on the source.

_Avoid duplicates_

If you run the script twice from scratch, you can create duplicates in Account 2.
To reduce this risk, the script uses a checkpoint file:

- checkpoint_copied_task_ids.json

_If you need to rerun:_

- Do not delete the checkpoint file if you want resume behavior.
- If you delete the checkpoint file, it will re-copy everything.

If you previously ran a version that failed mid-way

If you already have a partially copied list in Account 2 and you want a clean run:

1. In Account 2 (tasks.google.com), delete the partial list (example: [From Work] My Tasks)
2. In your script folder, delete:
   - checkpoint_copied_task_ids.json (if present)
3. Run the script again.
