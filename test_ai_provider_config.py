#!/usr/bin/env python3
"""
Test script for per-tenant AI provider configuration feature.
Tests all 11 scenarios from the review request.
"""
import requests
import json
import sys
from typing import Dict, Any, Optional

# Configuration
BASE_URL = "https://294719e8-6e6a-4485-9f72-fb115de1349a.preview.emergentagent.com/api"
PLATFORM_OWNER_EMAIL = "owner@context66.com"
PLATFORM_OWNER_PASSWORD = "Owner@1234"

# Tenant IDs
CONTEXT66_ID = "0d6ff40c-178b-4ccf-90b5-f1114cfccb0e"
ACME_ID = "309e4847-9d32-4f69-9254-32fc0ab0362b"

# Test results
test_results = []

def log_test(test_num: int, description: str, passed: bool, details: str = ""):
    """Log a test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    result = {
        "test": test_num,
        "description": description,
        "status": status,
        "passed": passed,
        "details": details
    }
    test_results.append(result)
    print(f"\nTest {test_num}: {description}")
    print(f"{status}")
    if details:
        print(f"Details: {details}")

def get_platform_token() -> Optional[str]:
    """Test 1: Login as platform owner and get token."""
    url = f"{BASE_URL}/platform/login"
    payload = {
        "email": PLATFORM_OWNER_EMAIL,
        "password": PLATFORM_OWNER_PASSWORD
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "token" in data:
                log_test(1, "POST /api/platform/login owner@context66.com/Owner@1234 -> 200 with token", 
                        True, f"Token received: {data['token'][:20]}...")
                return data["token"]
            else:
                log_test(1, "POST /api/platform/login owner@context66.com/Owner@1234 -> 200 with token", 
                        False, f"Response missing 'token' field: {data}")
                return None
        else:
            log_test(1, "POST /api/platform/login owner@context66.com/Owner@1234 -> 200 with token", 
                    False, f"Status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        log_test(1, "POST /api/platform/login owner@context66.com/Owner@1234 -> 200 with token", 
                False, f"Exception: {str(e)}")
        return None

def test_get_providers(token: str):
    """Test 2: GET /api/platform/ai/providers -> 200, exactly 6 providers."""
    url = f"{BASE_URL}/platform/ai/providers"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            log_test(2, "GET /api/platform/ai/providers -> 200, exactly 6 providers", 
                    False, f"Status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        # Check if it's a list
        if not isinstance(data, list):
            log_test(2, "GET /api/platform/ai/providers -> 200, exactly 6 providers", 
                    False, f"Response is not a list: {type(data)}")
            return
        
        # Check count
        if len(data) != 6:
            log_test(2, "GET /api/platform/ai/providers -> 200, exactly 6 providers", 
                    False, f"Expected 6 providers, got {len(data)}")
            return
        
        # Check provider IDs
        expected_ids = {"grok", "claude", "openai", "deepseek", "gemini", "kimi"}
        actual_ids = {p.get("id") for p in data}
        
        if actual_ids != expected_ids:
            log_test(2, "GET /api/platform/ai/providers -> 200, exactly 6 providers", 
                    False, f"Expected IDs {expected_ids}, got {actual_ids}")
            return
        
        # Check each provider has required fields
        for provider in data:
            if not all(k in provider for k in ["id", "label", "default_model"]):
                log_test(2, "GET /api/platform/ai/providers -> 200, exactly 6 providers", 
                        False, f"Provider missing required fields: {provider}")
                return
        
        log_test(2, "GET /api/platform/ai/providers -> 200, exactly 6 providers", 
                True, f"All 6 providers present with correct structure: {actual_ids}")
        
    except Exception as e:
        log_test(2, "GET /api/platform/ai/providers -> 200, exactly 6 providers", 
                False, f"Exception: {str(e)}")

def test_get_tenants(token: str):
    """Test 3: GET /api/platform/tenants -> 200; verify ai object structure."""
    url = f"{BASE_URL}/platform/tenants"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"Status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        if not isinstance(data, list):
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"Response is not a list: {type(data)}")
            return
        
        # Find context66 and acme tenants
        context66 = next((t for t in data if t.get("id") == CONTEXT66_ID), None)
        acme = next((t for t in data if t.get("id") == ACME_ID), None)
        
        if not context66:
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"context66 tenant not found in response")
            return
        
        if not acme:
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"acme tenant not found in response")
            return
        
        # Check context66 ai object
        context66_ai = context66.get("ai", {})
        if not isinstance(context66_ai, dict):
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"context66 ai is not a dict: {type(context66_ai)}")
            return
        
        # Verify context66 configuration
        if context66_ai.get("configured") != True:
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"context66 configured should be true, got {context66_ai.get('configured')}")
            return
        
        if context66_ai.get("provider") != "grok":
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"context66 provider should be 'grok', got {context66_ai.get('provider')}")
            return
        
        if context66_ai.get("model") != "grok-4":
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"context66 model should be 'grok-4', got {context66_ai.get('model')}")
            return
        
        # Check key masking
        key_masked = context66_ai.get("key_masked", "")
        if not key_masked.startswith("xai-") or not key_masked.endswith("Y5XH"):
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"context66 key_masked should look like 'xai-••••Y5XH', got '{key_masked}'")
            return
        
        if "••••" not in key_masked and "****" not in key_masked:
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"context66 key_masked should contain masking characters, got '{key_masked}'")
            return
        
        # Check acme ai object
        acme_ai = acme.get("ai", {})
        if not isinstance(acme_ai, dict):
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"acme ai is not a dict: {type(acme_ai)}")
            return
        
        if acme_ai.get("configured") != False:
            log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                    False, f"acme configured should be false, got {acme_ai.get('configured')}")
            return
        
        log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                True, f"context66: configured=true, provider=grok, model=grok-4, key_masked={key_masked}; acme: configured=false")
        
    except Exception as e:
        log_test(3, "GET /api/platform/tenants -> 200; each tenant has ai object", 
                False, f"Exception: {str(e)}")

def test_get_tenant_ai_detail(token: str):
    """Test 4: GET /api/platform/tenants/{context66_id}/ai -> 200, no raw key."""
    url = f"{BASE_URL}/platform/tenants/{CONTEXT66_ID}/ai"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            log_test(4, "GET /api/platform/tenants/{context66_id}/ai -> 200, no raw key", 
                    False, f"Status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        if data.get("configured") != True:
            log_test(4, "GET /api/platform/tenants/{context66_id}/ai -> 200, no raw key", 
                    False, f"configured should be true, got {data.get('configured')}")
            return
        
        # Check that raw API key is NOT present
        response_str = json.dumps(data)
        
        # The real key starts with xai-rPkg1ArHu8MSHM9JR4w4kCSu7beGLYxPOz94OQeYNLLXp9PrUWVJ15klnGwRCu8OwqnZsEZTRG70Y5XH
        # Check for the middle part that should NOT be visible
        if "rPkg1ArHu8MSHM9JR4w4kCSu7beGLYxPOz94OQeYNLLXp9PrUWVJ15klnGwRCu8OwqnZsEZTRG70" in response_str:
            log_test(4, "GET /api/platform/tenants/{context66_id}/ai -> 200, no raw key", 
                    False, f"Raw API key found in response! Response: {response_str}")
            return
        
        # Check that api_key field is not present
        if "api_key" in data:
            log_test(4, "GET /api/platform/tenants/{context66_id}/ai -> 200, no raw key", 
                    False, f"'api_key' field should not be present in response, got: {data}")
            return
        
        # Check that key_masked is present
        if "key_masked" not in data:
            log_test(4, "GET /api/platform/tenants/{context66_id}/ai -> 200, no raw key", 
                    False, f"'key_masked' field should be present in response, got: {data}")
            return
        
        log_test(4, "GET /api/platform/tenants/{context66_id}/ai -> 200, no raw key", 
                True, f"configured=true, key_masked present, raw key NOT in response")
        
    except Exception as e:
        log_test(4, "GET /api/platform/tenants/{context66_id}/ai -> 200, no raw key", 
                False, f"Exception: {str(e)}")

def test_crud_on_acme(token: str):
    """Test 5: CRUD on acme tenant."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Step 1: PUT with new config
    url = f"{BASE_URL}/platform/tenants/{ACME_ID}/ai"
    payload = {
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "sk-fake-123"
    }
    
    try:
        response = requests.put(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code != 200:
            log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                    False, f"PUT step 1 failed with status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        if data.get("configured") != True:
            log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                    False, f"PUT step 1: configured should be true, got {data.get('configured')}")
            return
        
        # Step 2: GET to verify
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                    False, f"GET step 2 failed with status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        if data.get("provider") != "openai":
            log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                    False, f"GET step 2: provider should be 'openai', got {data.get('provider')}")
            return
        
        if data.get("model") != "gpt-4o":
            log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                    False, f"GET step 2: model should be 'gpt-4o', got {data.get('model')}")
            return
        
        # Check masked key
        key_masked_1 = data.get("key_masked", "")
        if not key_masked_1 or "sk-" not in key_masked_1:
            log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                    False, f"GET step 2: key_masked should be present and masked, got '{key_masked_1}'")
            return
        
        # Step 3: PUT with empty api_key (should preserve key, update model)
        payload2 = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": ""
        }
        
        response = requests.put(url, json=payload2, headers=headers, timeout=10)
        
        if response.status_code != 200:
            log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                    False, f"PUT step 3 failed with status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        if data.get("configured") != True:
            log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                    False, f"PUT step 3: configured should still be true, got {data.get('configured')}")
            return
        
        if data.get("model") != "gpt-4o-mini":
            log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                    False, f"PUT step 3: model should be 'gpt-4o-mini', got {data.get('model')}")
            return
        
        # Check that key is still masked (preserved)
        key_masked_2 = data.get("key_masked", "")
        if not key_masked_2 or "sk-" not in key_masked_2:
            log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                    False, f"PUT step 3: key_masked should still be present and masked, got '{key_masked_2}'")
            return
        
        log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                True, f"PUT openai/gpt-4o/sk-fake-123 -> configured=true; GET -> provider=openai, model=gpt-4o, key_masked={key_masked_1}; PUT openai/gpt-4o-mini/'' -> model updated to gpt-4o-mini, key preserved")
        
    except Exception as e:
        log_test(5, "CRUD on acme: PUT with config, GET verify, PUT with empty key preserves key, model updates", 
                False, f"Exception: {str(e)}")

def test_delete_acme_ai(token: str):
    """Test 6: DELETE /api/platform/tenants/{acme_id}/ai -> 200, subsequent GET shows unconfigured."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/platform/tenants/{ACME_ID}/ai"
    
    try:
        # DELETE
        response = requests.delete(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            log_test(6, "DELETE /api/platform/tenants/{acme_id}/ai -> 200, subsequent GET shows unconfigured", 
                    False, f"DELETE failed with status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        if data.get("ok") != True:
            log_test(6, "DELETE /api/platform/tenants/{acme_id}/ai -> 200, subsequent GET shows unconfigured", 
                    False, f"DELETE response should have ok=true, got {data}")
            return
        
        # GET to verify
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            log_test(6, "DELETE /api/platform/tenants/{acme_id}/ai -> 200, subsequent GET shows unconfigured", 
                    False, f"GET after DELETE failed with status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        if data.get("configured") != False:
            log_test(6, "DELETE /api/platform/tenants/{acme_id}/ai -> 200, subsequent GET shows unconfigured", 
                    False, f"GET after DELETE: configured should be false, got {data.get('configured')}")
            return
        
        if data.get("provider") is not None:
            log_test(6, "DELETE /api/platform/tenants/{acme_id}/ai -> 200, subsequent GET shows unconfigured", 
                    False, f"GET after DELETE: provider should be null, got {data.get('provider')}")
            return
        
        log_test(6, "DELETE /api/platform/tenants/{acme_id}/ai -> 200, subsequent GET shows unconfigured", 
                True, f"DELETE returned ok=true; subsequent GET shows configured=false, provider=null")
        
    except Exception as e:
        log_test(6, "DELETE /api/platform/tenants/{acme_id}/ai -> 200, subsequent GET shows unconfigured", 
                False, f"Exception: {str(e)}")

def test_auth_enforcement(token: str):
    """Test 7: Auth enforcement - calls without token should return 401 or 403."""
    
    # Test GET /api/platform/ai/providers without token
    url1 = f"{BASE_URL}/platform/ai/providers"
    
    try:
        response = requests.get(url1, timeout=10)
        
        if response.status_code in [401, 403]:
            pass_1 = True
            details_1 = f"GET /api/platform/ai/providers without token -> {response.status_code} (correct)"
        else:
            pass_1 = False
            details_1 = f"GET /api/platform/ai/providers without token -> {response.status_code} (expected 401/403)"
        
    except Exception as e:
        pass_1 = False
        details_1 = f"GET /api/platform/ai/providers without token -> Exception: {str(e)}"
    
    # Test GET /api/platform/tenants/{context66_id}/ai without token
    url2 = f"{BASE_URL}/platform/tenants/{CONTEXT66_ID}/ai"
    
    try:
        response = requests.get(url2, timeout=10)
        
        if response.status_code in [401, 403]:
            pass_2 = True
            details_2 = f"GET /api/platform/tenants/{{context66_id}}/ai without token -> {response.status_code} (correct)"
        else:
            pass_2 = False
            details_2 = f"GET /api/platform/tenants/{{context66_id}}/ai without token -> {response.status_code} (expected 401/403)"
        
    except Exception as e:
        pass_2 = False
        details_2 = f"GET /api/platform/tenants/{{context66_id}}/ai without token -> Exception: {str(e)}"
    
    # Test PUT .../ai without token
    url3 = f"{BASE_URL}/platform/tenants/{CONTEXT66_ID}/ai"
    payload = {"provider": "openai", "model": "gpt-4o", "api_key": "sk-test"}
    
    try:
        response = requests.put(url3, json=payload, timeout=10)
        
        if response.status_code in [401, 403]:
            pass_3 = True
            details_3 = f"PUT /api/platform/tenants/{{context66_id}}/ai without token -> {response.status_code} (correct)"
        else:
            pass_3 = False
            details_3 = f"PUT /api/platform/tenants/{{context66_id}}/ai without token -> {response.status_code} (expected 401/403)"
        
    except Exception as e:
        pass_3 = False
        details_3 = f"PUT /api/platform/tenants/{{context66_id}}/ai without token -> Exception: {str(e)}"
    
    overall_pass = pass_1 and pass_2 and pass_3
    details = f"{details_1}; {details_2}; {details_3}"
    
    log_test(7, "AUTH enforcement: calls without token -> 401 or 403", 
            overall_pass, details)

def test_ai_test_endpoint_with_stored_key(token: str):
    """Test 8: POST /api/platform/tenants/{context66_id}/ai/test with empty key (uses stored real key)."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/platform/tenants/{CONTEXT66_ID}/ai/test"
    payload = {
        "provider": "grok",
        "model": "grok-4",
        "api_key": ""
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200:
            log_test(8, "POST /api/platform/tenants/{context66_id}/ai/test with stored key -> ok:true (or 429)", 
                    False, f"Status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        # Check if ok=true (success)
        if data.get("ok") == True:
            log_test(8, "POST /api/platform/tenants/{context66_id}/ai/test with stored key -> ok:true (or 429)", 
                    True, f"ok=true, real xAI call succeeded")
            return
        
        # Check if ok=false due to rate limit (acceptable)
        if data.get("ok") == False:
            message = data.get("message", "").lower()
            if "429" in message or "rate" in message or "limit" in message:
                log_test(8, "POST /api/platform/tenants/{context66_id}/ai/test with stored key -> ok:true (or 429)", 
                        True, f"ok=false due to rate limit (acceptable): {data.get('message')}")
                return
            
            # Check if it's an auth rejection (FAIL)
            if "401" in message or "403" in message or "auth" in message or "unauthorized" in message or "forbidden" in message:
                log_test(8, "POST /api/platform/tenants/{context66_id}/ai/test with stored key -> ok:true (or 429)", 
                        False, f"ok=false with auth rejection (FAIL): {data.get('message')}")
                return
            
            # Other error
            log_test(8, "POST /api/platform/tenants/{context66_id}/ai/test with stored key -> ok:true (or 429)", 
                    False, f"ok=false with unexpected error: {data}")
            return
        
        log_test(8, "POST /api/platform/tenants/{context66_id}/ai/test with stored key -> ok:true (or 429)", 
                False, f"Unexpected response: {data}")
        
    except Exception as e:
        log_test(8, "POST /api/platform/tenants/{context66_id}/ai/test with stored key -> ok:true (or 429)", 
                False, f"Exception: {str(e)}")

def test_ai_test_endpoint_with_bad_key(token: str):
    """Test 9: POST /api/platform/tenants/{context66_id}/ai/test with bad key -> ok:false with rejection message."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/platform/tenants/{CONTEXT66_ID}/ai/test"
    payload = {
        "provider": "grok",
        "model": "grok-4",
        "api_key": "bad-key-123"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200:
            log_test(9, "POST /api/platform/tenants/{context66_id}/ai/test with bad key -> ok:false with rejection", 
                    False, f"Status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        if data.get("ok") != False:
            log_test(9, "POST /api/platform/tenants/{context66_id}/ai/test with bad key -> ok:false with rejection", 
                    False, f"Expected ok=false, got {data.get('ok')}")
            return
        
        # Check that message indicates key rejection
        message = data.get("message", "").lower()
        if "401" in message or "403" in message or "auth" in message or "unauthorized" in message or "invalid" in message or "rejected" in message:
            log_test(9, "POST /api/platform/tenants/{context66_id}/ai/test with bad key -> ok:false with rejection", 
                    True, f"ok=false with rejection message: {data.get('message')}")
            return
        
        log_test(9, "POST /api/platform/tenants/{context66_id}/ai/test with bad key -> ok:false with rejection", 
                False, f"ok=false but message doesn't indicate key rejection: {data.get('message')}")
        
    except Exception as e:
        log_test(9, "POST /api/platform/tenants/{context66_id}/ai/test with bad key -> ok:false with rejection", 
                False, f"Exception: {str(e)}")

def test_validation(token: str):
    """Test 10: Validation - invalid provider -> 422, nonexistent tenant -> 404."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test invalid provider
    url1 = f"{BASE_URL}/platform/tenants/{ACME_ID}/ai"
    payload1 = {
        "provider": "notaprovider",
        "model": "some-model",
        "api_key": "sk-test"
    }
    
    try:
        response = requests.put(url1, json=payload1, headers=headers, timeout=10)
        
        if response.status_code == 422:
            pass_1 = True
            details_1 = f"PUT with invalid provider 'notaprovider' -> 422 (correct)"
        else:
            pass_1 = False
            details_1 = f"PUT with invalid provider 'notaprovider' -> {response.status_code} (expected 422)"
        
    except Exception as e:
        pass_1 = False
        details_1 = f"PUT with invalid provider -> Exception: {str(e)}"
    
    # Test nonexistent tenant
    nonexistent_id = "00000000-0000-0000-0000-000000000000"
    url2 = f"{BASE_URL}/platform/tenants/{nonexistent_id}/ai"
    
    try:
        response = requests.get(url2, headers=headers, timeout=10)
        
        if response.status_code == 404:
            pass_2 = True
            details_2 = f"GET nonexistent tenant -> 404 (correct)"
        else:
            pass_2 = False
            details_2 = f"GET nonexistent tenant -> {response.status_code} (expected 404)"
        
    except Exception as e:
        pass_2 = False
        details_2 = f"GET nonexistent tenant -> Exception: {str(e)}"
    
    # Test PUT nonexistent tenant
    payload3 = {
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "sk-test"
    }
    
    try:
        response = requests.put(url2, json=payload3, headers=headers, timeout=10)
        
        if response.status_code == 404:
            pass_3 = True
            details_3 = f"PUT nonexistent tenant -> 404 (correct)"
        else:
            pass_3 = False
            details_3 = f"PUT nonexistent tenant -> {response.status_code} (expected 404)"
        
    except Exception as e:
        pass_3 = False
        details_3 = f"PUT nonexistent tenant -> Exception: {str(e)}"
    
    # Test DELETE nonexistent tenant
    try:
        response = requests.delete(url2, headers=headers, timeout=10)
        
        if response.status_code == 404:
            pass_4 = True
            details_4 = f"DELETE nonexistent tenant -> 404 (correct)"
        else:
            pass_4 = False
            details_4 = f"DELETE nonexistent tenant -> {response.status_code} (expected 404)"
        
    except Exception as e:
        pass_4 = False
        details_4 = f"DELETE nonexistent tenant -> Exception: {str(e)}"
    
    overall_pass = pass_1 and pass_2 and pass_3 and pass_4
    details = f"{details_1}; {details_2}; {details_3}; {details_4}"
    
    log_test(10, "Validation: invalid provider -> 422, nonexistent tenant -> 404", 
            overall_pass, details)

def test_regression(token: str):
    """Test 11: Regression - platform stats, tenants list, normal workspace login still work."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/platform/stats
    url1 = f"{BASE_URL}/platform/stats"
    
    try:
        response = requests.get(url1, headers=headers, timeout=10)
        
        if response.status_code == 200:
            pass_1 = True
            details_1 = f"GET /api/platform/stats -> 200 (correct)"
        else:
            pass_1 = False
            details_1 = f"GET /api/platform/stats -> {response.status_code} (expected 200)"
        
    except Exception as e:
        pass_1 = False
        details_1 = f"GET /api/platform/stats -> Exception: {str(e)}"
    
    # Test GET /api/platform/tenants
    url2 = f"{BASE_URL}/platform/tenants"
    
    try:
        response = requests.get(url2, headers=headers, timeout=10)
        
        if response.status_code == 200:
            pass_2 = True
            details_2 = f"GET /api/platform/tenants -> 200 (correct)"
        else:
            pass_2 = False
            details_2 = f"GET /api/platform/tenants -> {response.status_code} (expected 200)"
        
    except Exception as e:
        pass_2 = False
        details_2 = f"GET /api/platform/tenants -> Exception: {str(e)}"
    
    # Test normal workspace login
    url3 = f"{BASE_URL}/auth/login"
    payload3 = {
        "email": "admin@ats.com",
        "password": "Admin@123",
        "tenant_slug": "context66"
    }
    
    try:
        response = requests.post(url3, json=payload3, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "token" in data:
                pass_3 = True
                details_3 = f"POST /api/auth/login (workspace) -> 200 with token (correct)"
            else:
                pass_3 = False
                details_3 = f"POST /api/auth/login (workspace) -> 200 but no token"
        else:
            pass_3 = False
            details_3 = f"POST /api/auth/login (workspace) -> {response.status_code} (expected 200)"
        
    except Exception as e:
        pass_3 = False
        details_3 = f"POST /api/auth/login (workspace) -> Exception: {str(e)}"
    
    overall_pass = pass_1 and pass_2 and pass_3
    details = f"{details_1}; {details_2}; {details_3}"
    
    log_test(11, "Regression: platform stats, tenants list, workspace login still work", 
            overall_pass, details)

def verify_cleanup(token: str):
    """Verify cleanup: acme has NO ai config, context66 still has grok config."""
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n" + "="*80)
    print("CLEANUP VERIFICATION")
    print("="*80)
    
    # Check acme
    url_acme = f"{BASE_URL}/platform/tenants/{ACME_ID}/ai"
    try:
        response = requests.get(url_acme, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("configured") == False:
                print(f"✅ acme tenant: configured=false (clean)")
            else:
                print(f"⚠️  acme tenant: configured={data.get('configured')} (expected false)")
        else:
            print(f"⚠️  acme tenant: GET failed with {response.status_code}")
    except Exception as e:
        print(f"⚠️  acme tenant: Exception: {str(e)}")
    
    # Check context66
    url_context66 = f"{BASE_URL}/platform/tenants/{CONTEXT66_ID}/ai"
    try:
        response = requests.get(url_context66, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("configured") == True and data.get("provider") == "grok" and data.get("model") == "grok-4":
                print(f"✅ context66 tenant: configured=true, provider=grok, model=grok-4 (unchanged)")
            else:
                print(f"⚠️  context66 tenant: configured={data.get('configured')}, provider={data.get('provider')}, model={data.get('model')}")
        else:
            print(f"⚠️  context66 tenant: GET failed with {response.status_code}")
    except Exception as e:
        print(f"⚠️  context66 tenant: Exception: {str(e)}")

def print_summary():
    """Print test summary."""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    
    print(f"\nTotal: {passed}/{total} tests passed ({100*passed//total}% pass rate)\n")
    
    for result in test_results:
        print(f"{result['status']} Test {result['test']}: {result['description']}")
    
    print("\n" + "="*80)
    
    if passed == total:
        print("✅ ALL TESTS PASSED")
    else:
        print(f"❌ {total - passed} TEST(S) FAILED")
    
    print("="*80)

def main():
    """Run all tests."""
    print("="*80)
    print("TESTING: Per-Tenant AI Provider Configuration")
    print("="*80)
    
    # Get platform token
    token = get_platform_token()
    if not token:
        print("\n❌ CRITICAL: Failed to get platform token. Cannot proceed with tests.")
        sys.exit(1)
    
    # Run all tests
    test_get_providers(token)
    test_get_tenants(token)
    test_get_tenant_ai_detail(token)
    test_crud_on_acme(token)
    test_delete_acme_ai(token)
    test_auth_enforcement(token)
    test_ai_test_endpoint_with_stored_key(token)
    test_ai_test_endpoint_with_bad_key(token)
    test_validation(token)
    test_regression(token)
    
    # Verify cleanup
    verify_cleanup(token)
    
    # Print summary
    print_summary()
    
    # Exit with appropriate code
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    main()
