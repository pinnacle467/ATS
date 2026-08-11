#!/usr/bin/env python3
"""
Password Reset & Change Password Flow Testing
Tests the newly added password reset & change password endpoints in /app/backend/routes_auth.py
"""
import hashlib
import requests
import sys
import time
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

# Configuration
BASE_URL = "https://candidate-sync-4.preview.emergentagent.com/api"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "sprout_ats"

# Test credentials
ADMIN_EMAIL = "admin@ats.com"
ADMIN_PASSWORD = "Admin@123"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'

class PasswordResetTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.critical_failures = []
        self.mongo_client = MongoClient(MONGO_URL)
        self.db = self.mongo_client[DB_NAME]
        
    def log(self, msg, color=Colors.BLUE):
        print(f"{color}{msg}{Colors.END}")
        
    def test(self, name, method, endpoint, expected_status, data=None, token=None, params=None):
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        self.tests_run += 1
        print(f"\n🔍 Test #{self.tests_run}: {name}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASS - Status: {response.status_code}", Colors.GREEN)
                try:
                    return True, response.json()
                except Exception:
                    return True, response.text
            else:
                self.tests_failed += 1
                self.log(f"❌ FAIL - Expected {expected_status}, got {response.status_code}", Colors.RED)
                try:
                    error_detail = response.json()
                    self.log(f"   Response: {error_detail}", Colors.YELLOW)
                    return False, error_detail
                except Exception:
                    self.log(f"   Response: {response.text[:200]}", Colors.YELLOW)
                    return False, {}
                
        except Exception as e:
            self.tests_failed += 1
            self.log(f"❌ FAIL - Error: {str(e)}", Colors.RED)
            return False, {}
    
    def get_admin_user_id(self):
        """Get admin user ID from database"""
        user = self.db.users.find_one({'email': ADMIN_EMAIL})
        if user:
            return user['id']
        return None
    
    def insert_synthetic_token(self, user_id, email, raw_token):
        """Insert a synthetic password reset token into the database"""
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        now_dt = datetime.now(timezone.utc)
        expires_at = now_dt + timedelta(hours=1)
        
        reset_doc = {
            'id': f'test_{int(time.time())}',
            'user_id': user_id,
            'email': email,
            'token_hash': token_hash,
            'created_at': now_dt.isoformat(),
            'expires_at': expires_at.isoformat(),
            'used_at': None,
            'ip': '127.0.0.1',
        }
        
        result = self.db.password_resets.insert_one(reset_doc)
        self.log(f"   Inserted synthetic token for {email}", Colors.CYAN)
        return raw_token
    
    def count_password_resets(self, email):
        """Count password reset requests for an email in the last hour"""
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        count = self.db.password_resets.count_documents({
            'email': email,
            'created_at': {'$gte': since.isoformat()},
        })
        return count
    
    def run_all_tests(self):
        """Run all password reset and change password tests"""
        self.log("\n" + "="*80, Colors.BLUE)
        self.log("PASSWORD RESET & CHANGE PASSWORD FLOW TESTING", Colors.BLUE)
        self.log("="*80, Colors.BLUE)
        
        # Get admin user ID
        admin_user_id = self.get_admin_user_id()
        if not admin_user_id:
            self.log("❌ CRITICAL: Cannot find admin user in database", Colors.RED)
            self.critical_failures.append("Admin user not found in database")
            return
        
        self.log(f"\n✓ Admin user ID: {admin_user_id}", Colors.GREEN)
        
        # ===================================================================
        # TEST CASE 1: Forgot password with non-existent email
        # ===================================================================
        self.log("\n" + "-"*80, Colors.CYAN)
        self.log("TEST CASE 1: Forgot password with non-existent email", Colors.CYAN)
        self.log("-"*80, Colors.CYAN)
        
        success, response = self.test(
            "POST /api/auth/forgot-password with non-existent email",
            "POST",
            "/auth/forgot-password",
            200,
            data={'email': 'nobody@example.com'}
        )
        
        if success:
            if response.get('ok') == True:
                self.log("   ✓ Returns 200 with ok:true (no user enumeration)", Colors.GREEN)
            else:
                self.critical_failures.append("Test 1: Expected ok:true in response")
                self.log("   ❌ Response does not contain ok:true", Colors.RED)
        
        # ===================================================================
        # TEST CASE 2: Forgot password with admin email + synthetic token
        # ===================================================================
        self.log("\n" + "-"*80, Colors.CYAN)
        self.log("TEST CASE 2: Forgot password with admin email + synthetic token", Colors.CYAN)
        self.log("-"*80, Colors.CYAN)
        
        success, response = self.test(
            "POST /api/auth/forgot-password with admin@ats.com",
            "POST",
            "/auth/forgot-password",
            200,
            data={'email': ADMIN_EMAIL}
        )
        
        if success:
            if response.get('ok') == True:
                self.log("   ✓ Returns 200 with ok:true", Colors.GREEN)
            else:
                self.critical_failures.append("Test 2: Expected ok:true in response")
                self.log("   ❌ Response does not contain ok:true", Colors.RED)
        
        # Insert synthetic token for testing
        synthetic_token = "TESTTOKEN_ADMIN_reset_flow_1234567890abcdef"
        self.insert_synthetic_token(admin_user_id, ADMIN_EMAIL, synthetic_token)
        
        # ===================================================================
        # TEST CASE 3: Verify valid reset token
        # ===================================================================
        self.log("\n" + "-"*80, Colors.CYAN)
        self.log("TEST CASE 3: Verify valid reset token", Colors.CYAN)
        self.log("-"*80, Colors.CYAN)
        
        success, response = self.test(
            "GET /api/auth/reset-password/verify with valid token",
            "GET",
            "/auth/reset-password/verify",
            200,
            params={'token': synthetic_token}
        )
        
        if success:
            if response.get('ok') == True and response.get('email') == ADMIN_EMAIL:
                self.log(f"   ✓ Returns ok:true with email: {response.get('email')}", Colors.GREEN)
            else:
                self.critical_failures.append("Test 3: Expected ok:true and correct email")
                self.log(f"   ❌ Response: {response}", Colors.RED)
        
        # ===================================================================
        # TEST CASE 4: Verify invalid reset token
        # ===================================================================
        self.log("\n" + "-"*80, Colors.CYAN)
        self.log("TEST CASE 4: Verify invalid reset token", Colors.CYAN)
        self.log("-"*80, Colors.CYAN)
        
        success, response = self.test(
            "GET /api/auth/reset-password/verify with invalid token",
            "GET",
            "/auth/reset-password/verify",
            400,
            params={'token': 'WRONGTOKEN'}
        )
        
        if success:
            if 'Invalid or expired reset link' in str(response.get('detail', '')):
                self.log("   ✓ Returns 400 with 'Invalid or expired reset link'", Colors.GREEN)
            else:
                self.log(f"   ⚠️  Expected 'Invalid or expired reset link', got: {response.get('detail')}", Colors.YELLOW)
        
        # ===================================================================
        # TEST CASE 5: Reset password with valid token
        # ===================================================================
        self.log("\n" + "-"*80, Colors.CYAN)
        self.log("TEST CASE 5: Reset password with valid token", Colors.CYAN)
        self.log("-"*80, Colors.CYAN)
        
        success, response = self.test(
            "POST /api/auth/reset-password with valid token and new password",
            "POST",
            "/auth/reset-password",
            200,
            data={'token': synthetic_token, 'new_password': 'TempPass@1'}
        )
        
        if success:
            if response.get('ok') == True:
                self.log("   ✓ Password reset successful", Colors.GREEN)
                
                # Verify login with new password
                time.sleep(1)  # Brief pause
                success2, login_response = self.test(
                    "POST /api/auth/login with new password (TempPass@1)",
                    "POST",
                    "/auth/login",
                    200,
                    data={'email': ADMIN_EMAIL, 'password': 'TempPass@1'}
                )
                
                if success2 and 'token' in login_response:
                    self.log("   ✓ Login successful with new password", Colors.GREEN)
                    admin_token = login_response['token']
                else:
                    self.critical_failures.append("Test 5: Cannot login with new password")
                    self.log("   ❌ Login failed with new password", Colors.RED)
                    admin_token = None
            else:
                self.critical_failures.append("Test 5: Password reset failed")
                self.log("   ❌ Password reset failed", Colors.RED)
                admin_token = None
        else:
            admin_token = None
        
        # ===================================================================
        # TEST CASE 6: Reuse same token (should fail)
        # ===================================================================
        self.log("\n" + "-"*80, Colors.CYAN)
        self.log("TEST CASE 6: Reuse same token (should fail)", Colors.CYAN)
        self.log("-"*80, Colors.CYAN)
        
        success, response = self.test(
            "POST /api/auth/reset-password with already-used token",
            "POST",
            "/auth/reset-password",
            400,
            data={'token': synthetic_token, 'new_password': 'AnotherPass@1'}
        )
        
        if success:
            if 'already been used' in str(response.get('detail', '')):
                self.log("   ✓ Returns 400 with 'already been used'", Colors.GREEN)
            else:
                self.log(f"   ⚠️  Expected 'already been used', got: {response.get('detail')}", Colors.YELLOW)
        
        # ===================================================================
        # TEST CASE 7: Weak password validation
        # ===================================================================
        self.log("\n" + "-"*80, Colors.CYAN)
        self.log("TEST CASE 7: Weak password validation", Colors.CYAN)
        self.log("-"*80, Colors.CYAN)
        
        # Create another synthetic token for weak password tests
        synthetic_token2 = f"TESTTOKEN_ADMIN_weak_pass_{int(time.time())}"
        self.insert_synthetic_token(admin_user_id, ADMIN_EMAIL, synthetic_token2)
        
        # Test 7a: Too short
        success, response = self.test(
            "POST /api/auth/reset-password with password 'short' (too short)",
            "POST",
            "/auth/reset-password",
            400,
            data={'token': synthetic_token2, 'new_password': 'short'}
        )
        
        if success:
            if '8 characters' in str(response.get('detail', '')):
                self.log("   ✓ Rejects password < 8 chars", Colors.GREEN)
            else:
                self.log(f"   ⚠️  Expected '8 characters' error, got: {response.get('detail')}", Colors.YELLOW)
        
        # Test 7b: No uppercase
        success, response = self.test(
            "POST /api/auth/reset-password with 'alllowercase1' (no uppercase)",
            "POST",
            "/auth/reset-password",
            400,
            data={'token': synthetic_token2, 'new_password': 'alllowercase1'}
        )
        
        if success:
            if 'upper and lower case' in str(response.get('detail', '')):
                self.log("   ✓ Rejects password without uppercase", Colors.GREEN)
            else:
                self.log(f"   ⚠️  Expected 'upper and lower case' error, got: {response.get('detail')}", Colors.YELLOW)
        
        # Test 7c: No numbers
        success, response = self.test(
            "POST /api/auth/reset-password with 'NoNumbers' (no digits)",
            "POST",
            "/auth/reset-password",
            400,
            data={'token': synthetic_token2, 'new_password': 'NoNumbers'}
        )
        
        if success:
            if 'at least one number' in str(response.get('detail', '')):
                self.log("   ✓ Rejects password without numbers", Colors.GREEN)
            else:
                self.log(f"   ⚠️  Expected 'at least one number' error, got: {response.get('detail')}", Colors.YELLOW)
        
        # ===================================================================
        # TEST CASE 8: Change password (logged-in user)
        # ===================================================================
        self.log("\n" + "-"*80, Colors.CYAN)
        self.log("TEST CASE 8: Change password (logged-in user)", Colors.CYAN)
        self.log("-"*80, Colors.CYAN)
        
        if not admin_token:
            self.log("   ⚠️  Skipping - no admin token from test 5", Colors.YELLOW)
        else:
            # Test 8a: Wrong current password
            success, response = self.test(
                "POST /api/auth/change-password with wrong current password",
                "POST",
                "/auth/change-password",
                400,
                data={'current_password': 'WrongPass@1', 'new_password': 'AnotherPass@1'},
                token=admin_token
            )
            
            if success:
                if 'Current password is incorrect' in str(response.get('detail', '')):
                    self.log("   ✓ Rejects wrong current password", Colors.GREEN)
                else:
                    self.log(f"   ⚠️  Expected 'Current password is incorrect', got: {response.get('detail')}", Colors.YELLOW)
            
            # Test 8b: Same password
            success, response = self.test(
                "POST /api/auth/change-password with same password",
                "POST",
                "/auth/change-password",
                400,
                data={'current_password': 'TempPass@1', 'new_password': 'TempPass@1'},
                token=admin_token
            )
            
            if success:
                if 'must be different' in str(response.get('detail', '')):
                    self.log("   ✓ Rejects same password", Colors.GREEN)
                else:
                    self.log(f"   ⚠️  Expected 'must be different', got: {response.get('detail')}", Colors.YELLOW)
            
            # Test 8c: Change back to Admin@123 (restore original password)
            success, response = self.test(
                "POST /api/auth/change-password to restore Admin@123",
                "POST",
                "/auth/change-password",
                200,
                data={'current_password': 'TempPass@1', 'new_password': ADMIN_PASSWORD},
                token=admin_token
            )
            
            if success:
                if response.get('ok') == True:
                    self.log("   ✓ Password changed back to Admin@123", Colors.GREEN)
                    
                    # Verify old password no longer works
                    time.sleep(1)
                    success2, _ = self.test(
                        "POST /api/auth/login with old password TempPass@1 (should fail)",
                        "POST",
                        "/auth/login",
                        401,
                        data={'email': ADMIN_EMAIL, 'password': 'TempPass@1'}
                    )
                    
                    if success2:
                        self.log("   ✓ Old password TempPass@1 no longer works", Colors.GREEN)
                    
                    # Verify new password works
                    success3, _ = self.test(
                        "POST /api/auth/login with restored password Admin@123",
                        "POST",
                        "/auth/login",
                        200,
                        data={'email': ADMIN_EMAIL, 'password': ADMIN_PASSWORD}
                    )
                    
                    if success3:
                        self.log("   ✓ Restored password Admin@123 works", Colors.GREEN)
                    else:
                        self.critical_failures.append("Test 8: Cannot login with restored password")
                        self.log("   ❌ CRITICAL: Cannot login with Admin@123", Colors.RED)
                else:
                    self.critical_failures.append("Test 8: Failed to restore password")
                    self.log("   ❌ Failed to restore password", Colors.RED)
        
        # ===================================================================
        # TEST CASE 9: Rate limiting (5 requests per hour per email)
        # ===================================================================
        self.log("\n" + "-"*80, Colors.CYAN)
        self.log("TEST CASE 9: Rate limiting (5 requests per hour per email)", Colors.CYAN)
        self.log("-"*80, Colors.CYAN)
        
        test_email = "ratelimit@example.com"
        
        # Count existing requests
        initial_count = self.count_password_resets(test_email)
        self.log(f"   Initial password_resets count for {test_email}: {initial_count}", Colors.CYAN)
        
        # Send 6 requests
        for i in range(1, 7):
            success, response = self.test(
                f"POST /api/auth/forgot-password attempt {i}/6",
                "POST",
                "/auth/forgot-password",
                200,
                data={'email': test_email}
            )
            
            if success and response.get('ok') == True:
                self.log(f"   ✓ Attempt {i}: Returns 200 ok (generic response)", Colors.GREEN)
            
            time.sleep(0.5)  # Brief pause between requests
        
        # Count final requests
        final_count = self.count_password_resets(test_email)
        self.log(f"   Final password_resets count for {test_email}: {final_count}", Colors.CYAN)
        
        new_rows = final_count - initial_count
        self.log(f"   New password_resets rows created: {new_rows}", Colors.CYAN)
        
        if new_rows <= 5:
            self.log(f"   ✓ Rate limiting working: only {new_rows} rows created (max 5)", Colors.GREEN)
        else:
            self.log(f"   ❌ Rate limiting NOT working: {new_rows} rows created (expected max 5)", Colors.RED)
            self.critical_failures.append(f"Test 9: Rate limiting failed - {new_rows} rows created")
        
        # ===================================================================
        # SUMMARY
        # ===================================================================
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*80, Colors.BLUE)
        self.log("TEST SUMMARY", Colors.BLUE)
        self.log("="*80, Colors.BLUE)
        
        total = self.tests_run
        passed = self.tests_passed
        failed = self.tests_failed
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        self.log(f"\nTotal Tests: {total}", Colors.BLUE)
        self.log(f"Passed: {passed}", Colors.GREEN)
        self.log(f"Failed: {failed}", Colors.RED if failed > 0 else Colors.GREEN)
        self.log(f"Pass Rate: {pass_rate:.1f}%", Colors.GREEN if pass_rate >= 90 else Colors.YELLOW)
        
        if self.critical_failures:
            self.log(f"\n❌ CRITICAL FAILURES ({len(self.critical_failures)}):", Colors.RED)
            for i, failure in enumerate(self.critical_failures, 1):
                self.log(f"   {i}. {failure}", Colors.RED)
        else:
            self.log("\n✅ NO CRITICAL FAILURES", Colors.GREEN)
        
        self.log("\n" + "="*80, Colors.BLUE)
        
        # Close MongoDB connection
        self.mongo_client.close()
        
        # Exit with appropriate code
        sys.exit(0 if failed == 0 else 1)

if __name__ == '__main__':
    tester = PasswordResetTester()
    tester.run_all_tests()
