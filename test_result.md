#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

## user_problem_statement: User pulled the connected GitHub repo (pinnacle467/ATS, which is this same Sprout ATS project's mirror) into this workspace via "Pull from GitHub". This wiped backend/.env and frontend/.env (gitignored) and left the app crashing (backend: KeyError MONGO_URL). User asked main agent to rebuild the missing .env files so the imported build runs correctly.

## backend:
##   - task: "Add notice_period field to candidate model, resume parser schema, and Excel/CSV import mapping"
##     implemented: true
##     working: "NA"
##     file: "backend/routes_candidates.py, backend/resume_parser.py, backend/routes_imports.py, backend/seed.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "User wants to see candidate notice periods on the candidates list and detail view. Added notice_period: Optional[str]=None to CandidateCreate/CandidateUpdate models (routes_candidates.py) and included it in the created candidate doc. Added notice_period to resume_parser.py's LLM JSON schema + EMPTY_PARSE dict (only filled if resume explicitly states it, otherwise null — not guessed). Added 'notice_period' to routes_imports.py TARGET_FIELDS + SYNONYMS (so Excel/CSV migration can map a Notice Period column) and to commit_import's candidate doc creation + to the downloadable template. Added sample notice_period values to seed.py demo candidates. Needs testing: POST /api/candidates with notice_period saves correctly; GET /api/candidates and GET /api/candidates/{id} return it; PUT /api/candidates/{id} can update it; resume parse endpoints don't break (notice_period just added as optional null field); import preview/commit correctly maps and stores a Notice Period column from an xlsx/csv."
##   - task: "Rename seeded admin user 'Alex Morgan' -> 'Abhijeet Kang' (seed.py + live DB migration of users/activities/notes/audit_log)"
##     implemented: true
##     working: true
##     file: "backend/seed.py"
##     stuck_count: 0
##     priority: "medium"
##     needs_retesting: false
##     status_history:
##         -working: true
##         -agent: "main"
##         -comment: "Updated seed.py admin user name for future fresh deployments, and ran a one-off Mongo migration on the live 'sprout_ats' db renaming 'Alex Morgan' -> 'Abhijeet Kang' across users.name, activities.actor_name, notes.author_name, and audit_log.actor_name (220 documents updated total, verified 0 remaining matches). No code path elsewhere hardcodes this name (actor/author names are always read dynamically from the users collection at write time), so this fully addresses the rename including historical activity feed / audit log entries. Verified directly via mongosh query — not re-tested via testing agent since it's a data-only change with no new logic."
##   - task: "Bulk delete candidates (admin-only) via POST /candidates/bulk-action with action=delete"
##     implemented: true
##     working: true
##     file: "backend/routes_candidates.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "User asked where the Excel/CSV candidate migration option is (it existed but had no UI entry point — /candidates/import route was never linked from the Candidates page or sidebar) and asked for individual + bulk candidate delete. Individual delete already existed (admin-only, Trash icon on CandidateProfilePage, DELETE /api/candidates/{id}) and works. Added bulk delete: extended BulkAction model action enum with 'delete', added handling in POST /api/candidates/bulk-action that deletes each candidate + their notes and logs activity/audit; restricted to admin role (403 for recruiter) matching existing single-delete permission. Needs backend testing: (1) admin can bulk-delete multiple candidate_ids and they disappear + notes removed, (2) recruiter gets 403 when attempting action=delete, (3) other bulk actions (move_stage/reject/tag/assign) still work unaffected."
##         -working: true
##         -agent: "testing"
##         -comment: "COMPREHENSIVE TESTING COMPLETED - ALL TESTS PASSED (100% pass rate, 62/62 tests). Bulk delete feature tested thoroughly: (1) ✅ Recruiter correctly denied with 403 when attempting bulk delete (admin-only enforcement working). (2) ✅ Admin successfully bulk deleted 2 candidates, returned 200 with correct count=2. (3) ✅ Both deleted candidates correctly return 404 on GET /api/candidates/{id} (candidates removed from database). (4) ✅ Notes deletion verified (code review shows db.notes.delete_many at line 282). (5) ✅ All other bulk actions still work correctly: move_stage (stage updated to Screening), tag (test-bulk-tag added), assign (recruiter assigned), reject (stage=Rejected, status=rejected, rejection_reason='Not a good fit for the role' all set correctly). (6) ✅ Sanity checks passed: GET /api/dashboard/stats (200), GET /api/jobs (200), GET /api/imports/template (200) - no regressions from routes_candidates.py changes. Implementation is solid and production-ready."

## frontend:
##   - task: "Surface existing Import from Excel/CSV flow with a visible button on Candidates page"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/pages/CandidatesPage.jsx"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "Added 'Import from Excel/CSV' button (admin/recruiter only) next to CSV export and Add Candidate buttons on /candidates page, navigating to the pre-existing /candidates/import route (ImportCandidatesPage.jsx + routes_imports.py backend, unchanged/already functional — just wasn't linked anywhere in the UI before)."
##   - task: "Bulk delete UI: Delete button in candidates bulk-actions bar with confirmation dialog"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/pages/CandidatesPage.jsx"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "Added admin-only 'Delete' button to the candidates bulk-actions bar (shown when rows are selected in table view), opening a confirmation dialog warning the action is permanent before calling POST /candidates/bulk-action with action=delete."
##   - task: "Delete button on Jobs page (admin-only), calling existing DELETE /api/jobs/{id}"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/pages/JobsPage.jsx"
##     stuck_count: 0
##     priority: "medium"
##     needs_retesting: false
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "Backend DELETE /api/jobs/{job_id} already existed (admin-only) but had no UI trigger. Added a Trash2 icon button (admin-only) to each job card with a window.confirm() warning (mentions active candidate count if any) before calling the delete API. Frontend-only change; backend endpoint unchanged. A prior automated frontend test run for this was requested but the sub-agent stopped before executing any steps — not yet independently verified via testing agent."
##   - task: "Display notice_period on Candidates table (new column) and Candidate Profile page (Contact & Details card); capture it in Add Candidate manual/parsed-review form"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/pages/CandidatesPage.jsx, frontend/src/pages/CandidateProfilePage.jsx, frontend/src/pages/AddCandidatePage.jsx, frontend/src/pages/ImportCandidatesPage.jsx"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "Added 'Notice Period' column (hidden on small screens) to the candidates table, a labeled row with Clock icon on the candidate profile page, a text input in the Add Candidate manual/AI-parsed-review form, and the mapping label in the Excel/CSV import wizard. All wire through the notice_period field added to the backend models."
##   - task: "BUG FIX: DOCX resume preview not rendering on candidate profile page (only PDF worked)"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/pages/CandidateProfilePage.jsx, frontend/package.json"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "USER REPORTED BUG: On the candidate profile page, resumes uploaded as .docx did not open/preview (unlike .pdf which worked fine). Root cause: the resume preview was a single <iframe src={blobUrl}> - browsers have a native built-in PDF renderer for iframes, but there is NO native browser renderer for Word/.docx documents, so the iframe showed blank/broken for docx files. Note: the app only accepts .pdf and .docx uploads (AddCandidatePage.jsx accept filter and resume_parser.py extract_text_from_bytes) - there is no legacy .doc (pre-2007 binary Word) support anywhere in the app, so 'the .doc format' in the user report refers to .docx. FIX: installed docx-preview (v0.4.0) npm package which parses OOXML .docx client-side into HTML. Restructured the resume-fetch effect in CandidateProfilePage.jsx to detect file type from response Content-Type header + Content-Disposition filename extension: if PDF -> keep existing iframe approach (unchanged); if DOCX -> store blob and render via docx-preview's renderAsync() into a dedicated container div (ignoreWidth/ignoreHeight so it reflows to fit the card); anything else -> graceful 'preview not available, use Download' message. Added loading/error states per type. Frontend restarted, webpack compiled successfully (only harmless docx-preview source-map warnings). NOT YET VERIFIED IN BROWSER - needs testing agent to upload a .docx resume via Add Candidate flow and confirm it renders readable content on the candidate profile page, AND confirm a .pdf resume still previews correctly (regression check)."

## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 5
##   run_ui: false

## test_plan:
##   current_focus:
##     - "BUG FIX: DOCX resume preview not rendering on candidate profile page (only PDF worked)"
##   stuck_tasks: []
##   test_all: false
##   test_priority: "high_first"

## agent_communication:
##     -agent: "main"
##     -message: "Previous recovery task (recreating .env after GitHub import) is done and backend/frontend are healthy with seeded demo data. New change: added bulk-delete support to POST /api/candidates/bulk-action (action='delete', admin-only, deletes candidates + their notes) and surfaced the pre-existing Excel/CSV import flow with a visible button on the Candidates page (it was fully built and functional before but had zero UI entry point). Please test: login as admin@ats.com/Admin@123, select multiple candidates in table view, bulk delete them, confirm they're gone and notes deleted; then login as recruiter@ats.com/Recruit@123 and confirm bulk delete is rejected with 403 (Delete button shouldn't even show for recruiter in UI, but also verify API-level 403). Also verify existing bulk actions (move_stage/reject/tag/assign) and the import preview/commit endpoints still work unaffected."
##     -agent: "testing"
##     -message: "✅ BULK DELETE FEATURE FULLY TESTED AND WORKING. All 5 test scenarios from review request passed: (1) Recruiter correctly blocked with 403 on bulk delete attempt. (2) Admin successfully bulk deleted 2 candidates, both return 404 after deletion, notes also removed. (3) All other bulk actions verified working: move_stage, tag, assign, reject all function correctly with proper data updates. (4) Reject action correctly sets stage=Rejected, status=rejected, and rejection_reason. (5) Unrelated endpoints (dashboard/stats, jobs, imports/template) all working - no regressions. Backend implementation is production-ready. 100% test pass rate (62/62 tests). Ready for user acceptance testing or deployment."
##     -agent: "main"
##     -message: "New round of changes to verify: (1) notice_period field end-to-end — create candidate (POST /api/candidates) with notice_period set, verify returned on GET list + GET by id, verify PUT can update it, verify resume parse endpoints still function normally, verify import preview/commit maps a 'Notice Period' style column correctly (use /app/tests/fixtures/import_test.xlsx or add a Notice Period column to a copy). (2) Admin rename — already verified directly via mongosh migration (220 docs updated, 0 remaining 'Alex Morgan' matches); please also confirm via API: login as admin@ats.com/Admin@123 and check the auth/me or login response returns name 'Abhijeet Kang'. Note: Jobs page delete button is a frontend-only addition on a pre-existing backend endpoint — not this round's focus but flag if any regression is noticed on GET/DELETE /api/jobs."
##     -agent: "main"
##     -message: "BUG FIX to verify now (frontend-only, no backend change): candidate profile page resume preview. Previously only PDF resumes rendered in the preview iframe; DOCX resumes appeared blank/broken because browsers can't natively render Word docs in an iframe. Added client-side docx-preview library so DOCX now renders as HTML in a dedicated container, auto-detected via response content-type/filename. Please test end-to-end via the UI: (1) Login as admin@ats.com/Admin@123 or recruiter@ats.com/Recruit@123. (2) Go to Add Candidate, upload /app/tests/fixtures/resume_priya_patel.docx (single upload), let AI parsing complete, assign to any open job, save the candidate. (3) Open that candidate's profile page and confirm the Resume card shows rendered document text/content (not blank, not an error message) inside the preview area (data-testid=candidate-resume-docx-preview). (4) Also upload /app/tests/fixtures/resume_sarah_chen.pdf or resume_miguel_torres.pdf as a second candidate and confirm its PDF preview still renders correctly in the iframe as before (regression check). (5) Confirm the Download button works for both candidates and downloads the original file correctly."