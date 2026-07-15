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
##   - task: "Recreate backend/.env after GitHub import wiped it (MONGO_URL, DB_NAME, JWT_SECRET, EMERGENT_LLM_KEY, CORS_ORIGINS)"
##     implemented: true
##     working: true
##     file: "backend/.env"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         -working: true
##         -agent: "main"
##         -comment: "backend/.env and frontend/.env were missing after 'Pull from GitHub' (both are gitignored at repo root .gitignore, so never pushed). Backend was crash-looping with KeyError: 'MONGO_URL'. Recreated backend/.env with MONGO_URL=mongodb://localhost:27017, DB_NAME=sprout_ats, CORS_ORIGINS=*, freshly generated JWT_SECRET, and EMERGENT_LLM_KEY fetched via emergent_integrations_manager. Recreated frontend/.env with REACT_APP_BACKEND_URL pulled from the environment's actual preview_endpoint (https://b2b011a2-c28e-4722-ace2-04a2a0b400ea.preview.emergentagent.com). Restarted backend+frontend via supervisor. Backend now starts cleanly, auto-seeds demo data (seed_if_empty), Mongo now shows populated 'sprout_ats' db. Also recreated /app/memory/test_credentials.md (also gitignored, was missing) with the 5 seeded demo accounts (admin/recruiter/interviewer roles) sourced from seed.py. Login page screenshot confirms UI renders correctly with demo one-click login buttons. Requesting backend testing agent to run full regression (auth, resumes, jobs, candidates, interviews, dashboard, admin, imports) since this is effectively validating the freshly-seeded/restored environment end-to-end, not new code changes."

## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 1
##   run_ui: false

## test_plan:
##   current_focus:
##     - "Recreate backend/.env after GitHub import wiped it (MONGO_URL, DB_NAME, JWT_SECRET, EMERGENT_LLM_KEY, CORS_ORIGINS)"
##   stuck_tasks: []
##   test_all: true
##   test_priority: "high_first"

## agent_communication:
##     -agent: "main"
##     -message: "Restored missing .env files (backend + frontend) after user pulled the connected GitHub repo, which wiped gitignored env files and crashed the backend. App now boots clean and auto-seeded demo data into a fresh 'sprout_ats' Mongo db. No application code was changed — this is a pure environment/config recovery. Please run a full backend regression pass to confirm auth (all 5 demo roles), resumes parsing, jobs, candidates, interviews, dashboard, admin, and imports endpoints all work against the freshly seeded DB. Demo credentials are in /app/memory/test_credentials.md."