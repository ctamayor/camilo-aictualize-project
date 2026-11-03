# Request: compact every WeaponX file automatically each night

*Email, drafted for opportunity 5: Weekly manual compaction of WeaponX Access databases, $368 a month.*

**For:** IT (or whoever owns the WeaponX database and its daily import), from the person who sent book admins the weekly compaction procedure

---

Subject: Request: nightly automatic compaction of every WeaponX file

Hi,

**What I need:** a job that compacts every WeaponX Access file each night. You can set it up either way:
1. A scheduled overnight task for each file that runs Access with the /compact switch, e.g. `msaccess.exe "<path to WeaponX file>" /compact`, or
2. A compact step added to the end of the daily WeaponX import.

**Why:** At the moment, book admins in six managers' groups compact their own files by hand at least once a week, and one admin does it every day. This takes about 4.3 hours of admin time a month (about $368). It also means a file keeps growing whenever someone forgets. Once the job runs every night, admins can stop doing this by hand and every file stays small. You only have to set it up once.

**What I need back from you:**
- Which option you'll use and roughly when it can go live.
- Anything you need from us. I'll collect the location of each group's WeaponX file from its book admin and send you the list.

Once you confirm the job is running, I'll tell the book admins they can stop the weekly manual compact.

Thanks,
[Name / role]

---

**Background, for whoever sets this up**

*Why the files grow:* WeaponX imports and deletes a lot of data every day, and Access doesn't free that space until the file is compacted. Compacting makes a big difference. The Texas file went from 520 MB to 30 MB, and a West file went from 400 MB to 12 MB.

*What admins do by hand now (what the job replaces):*
1. Open the WeaponX file while holding down Shift, so the main form doesn't open by itself.
2. Choose Tools / Database Utilities / Compact Database from the menus.
3. Wait for it to finish. On files of several hundred MB this can take a while.
4. Open the file again and use it as normal.

*Points to check when setting it up:*
- Access usually needs exclusive use of a file to compact it, so run the job when nobody has the file open and after the daily import has finished.
- Make sure the job compacts the file without the main form opening and stopping it. The manual steps avoid this by holding Shift.
- Set up one job, or one import step, for each WeaponX file in all six managers' groups. Please check that every file on the list is covered.
- For the first few nights, compare each file's size with its previous size to confirm the compact is working before the admins stop doing it by hand.

*Until the job is live:* book admins should keep compacting by hand at least once a week, as they do now.
