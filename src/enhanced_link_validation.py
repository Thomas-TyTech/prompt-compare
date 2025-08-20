import sys
import os
import argparse
import requests
import re
import json
from datetime import datetime
import time
import uuid
from typing import List, Dict, Optional
from urllib.parse import urlparse
import concurrent.futures
from threading import Lock
import warnings
from urllib3.exceptions import InsecureRequestWarning

warnings.filterwarnings('ignore', category=InsecureRequestWarning)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from api_test_harness import APITester, DatabaseManager, TestQuestion
except ImportError:
    print("Error: Could not import API test harness. Make sure api_test_harness.py is in the same directory.")
    sys.exit(1)

class EnhancedLinkValidator:
    
    def __init__(self, timeout=15, max_workers=3, max_retries=2):
        self.timeout = timeout
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.session = requests.Session()
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        self.session.max_redirects = 10
        
        self.validation_lock = Lock()
        
    def extract_links(self, text):
        patterns = [
            r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w%!./?=&+#]*)*',
            r'www\.(?:[-\w.])+(?:/[-\w%!./?=&+#]*)*',
        ]
        
        all_links = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            all_links.extend(matches)
        
        cleaned_links = []
        for link in all_links:
            if link.startswith('www.'):
                link = 'https://' + link
            
            while link and link[-1] in '.,:;!?)]}>"\'':
                link = link[:-1]
            
            if link and len(link) > 10 and '.' in link:
                cleaned_links.append(link)
        
        seen = set()
        unique_links = []
        for link in cleaned_links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)
        
        return unique_links
    
    def validate_single_link_attempt(self, url, attempt=1):
        start_time = time.time()
        
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return {
                    "url": url,
                    "status": "invalid",
                    "status_code": None,
                    "error": "Invalid URL format",
                    "response_time_ms": 0,
                    "final_url": url,
                    "redirects": 0,
                    "attempt": attempt
                }
            
            methods_to_try = [
                ("HEAD", lambda: self.session.head(url, timeout=self.timeout, allow_redirects=True, verify=False)),
                ("GET", lambda: self.session.get(url, timeout=self.timeout, allow_redirects=True, verify=False, stream=True))
            ]
            
            last_exception = None
            
            for method_name, method_func in methods_to_try:
                try:
                    response = method_func()
                    response_time = int((time.time() - start_time) * 1000)
                    
                    if response.status_code < 400:
                        status = "valid"
                        error = None
                    elif response.status_code == 404:
                        if method_name == "HEAD":
                            continue
                        status = "invalid"
                        error = "Page not found (404)"
                    elif response.status_code == 403:
                        if method_name == "HEAD":
                            continue
                        status = "warning"
                        error = "Access forbidden (403) - may be bot protection"
                    elif response.status_code == 429:
                        status = "warning"
                        error = "Rate limited (429) - try again later"
                    elif response.status_code >= 500:
                        status = "warning"
                        error = f"Server error ({response.status_code}) - temporary issue"
                    else:
                        status = "invalid"
                        error = f"HTTP error ({response.status_code})"
                    
                    redirects = len(response.history) if hasattr(response, 'history') else 0
                    
                    return {
                        "url": url,
                        "status": status,
                        "status_code": response.status_code,
                        "error": error,
                        "response_time_ms": response_time,
                        "final_url": response.url,
                        "redirects": redirects,
                        "method_used": method_name,
                        "attempt": attempt
                    }
                    
                except (requests.exceptions.ConnectionError, 
                        requests.exceptions.Timeout,
                        requests.exceptions.TooManyRedirects) as e:
                    last_exception = e
                    continue
                except Exception as e:
                    last_exception = e
                    continue
            
            response_time = int((time.time() - start_time) * 1000)
            return {
                "url": url,
                "status": "invalid",
                "status_code": None,
                "error": f"Connection failed: {str(last_exception)}",
                "response_time_ms": response_time,
                "final_url": url,
                "redirects": 0,
                "attempt": attempt
            }
            
        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            return {
                "url": url,
                "status": "invalid",
                "status_code": None,
                "error": f"Validation error: {str(e)}",
                "response_time_ms": response_time,
                "final_url": url,
                "redirects": 0,
                "attempt": attempt
            }
    
    def validate_single_link(self, url):
        best_result = None
        
        for attempt in range(1, self.max_retries + 1):
            result = self.validate_single_link_attempt(url, attempt)
            
            if result["status"] == "valid":
                return result
            
            if best_result is None or (
                result["status"] == "warning" and best_result["status"] == "invalid"
            ):
                best_result = result
            
            if attempt < self.max_retries and result["status"] == "invalid":
                time.sleep(1)
        
        return best_result
    
    def validate_links(self, urls, show_progress=True):
        if not urls:
            return []
        
        results = []
        
        if show_progress:
            print(f"    Validating {len(urls)} links with enhanced validation...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_url = {executor.submit(self.validate_single_link, url): url for url in urls}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    if show_progress:
                        if result["status"] == "valid":
                            status_symbol = "✅"
                        elif result["status"] == "warning":
                            status_symbol = "⚠️"
                        else:
                            status_symbol = "❌"
                        
                        print(f"      {status_symbol} {url} ({result.get('status_code', 'N/A')}) - {result.get('method_used', 'N/A')}")
                        
                except Exception as e:
                    results.append({
                        "url": url,
                        "status": "invalid",
                        "status_code": None,
                        "error": f"Validation failed: {str(e)}",
                        "response_time_ms": 0,
                        "final_url": url,
                        "redirects": 0,
                        "attempt": 1
                    })
                    
                    if show_progress:
                        print(f"      ❌ {url} (Validation failed)")
        
        return results

class ComprehensiveTester:
    
    def __init__(self, api_endpoint, auth_header, database_manager):
        self.api_tester = APITester(api_endpoint, auth_header, database_manager)
        self.link_validator = EnhancedLinkValidator()
        self.db = database_manager
    
    def load_questions(self, questions_file):
        try:
            with open(questions_file, 'r', encoding='utf-8') as f:
                questions_data = json.load(f)
            
            test_questions = []
            for q in questions_data:
                test_questions.append(TestQuestion(
                    id=q['id'],
                    question=q['question'],
                    category=q.get('category', 'general'),
                    complexity=q.get('complexity', 'basic')
                ))
            
            return test_questions
            
        except Exception as e:
            print(f"❌ Error loading questions from {questions_file}: {e}")
            return []
    
    def run_comprehensive_test(self, questions, test_name, description="", delay=2.0):
        
        print(f"🚀 Starting Enhanced Comprehensive Link Validation Test: {test_name}")
        print(f"📊 Questions: {len(questions)}")
        print(f"🔗 API Endpoint: {self.api_tester.api_endpoint}")
        print(f"⏱️  Delay: {delay}s between questions")
        print(f"🔄 Enhanced validation with {self.link_validator.max_retries} retries per link")
        print("=" * 80)
        
        session_id = self.api_tester.run_test_suite(
            questions=questions,
            test_name=test_name,
            description=description,
            delay_between_questions=delay,
            use_single_conversation=False
        )
        
        if not session_id:
            print("❌ Failed to run API test suite")
            return None
        
        api_responses = self.db.get_results_for_dashboard(session_id)
        
        print(f"\n🔍 Starting enhanced link validation for {len(api_responses)} responses...")
        print("=" * 80)
        
        comprehensive_results = []
        
        for i, response in enumerate(api_responses, 1):
            question_id = response.get("id", f"Q{i:03d}")
            question_text = response.get("input", {}).get("question", "")
            response_text = response.get("output", {}).get("response", "")
            response_time_ms = response.get("output", {}).get("response_time_ms", 0)
            timestamp = response.get("output", {}).get("timestamp", "")
            status = response.get("output", {}).get("status", "unknown")
            
            print(f"\n[{i}/{len(api_responses)}] Processing {question_id}...")
            print(f"  Question: {question_text[:100]}...")
            
            extracted_links = self.link_validator.extract_links(response_text)
            print(f"  Found {len(extracted_links)} links to validate")
            
            link_validation_results = []
            if extracted_links:
                link_validation_results = self.link_validator.validate_links(
                    extracted_links, 
                    show_progress=True
                )
            
            valid_links = [link for link in link_validation_results if link["status"] == "valid"]
            warning_links = [link for link in link_validation_results if link["status"] == "warning"]
            invalid_links = [link for link in link_validation_results if link["status"] == "invalid"]
            
            result = {
                "question_id": question_id,
                "question": question_text,
                "response": response_text,
                "api_response_time_ms": response_time_ms,
                "api_status": status,
                "timestamp": timestamp,
                "links_found": len(extracted_links),
                "links_valid": len(valid_links),
                "links_warning": len(warning_links),
                "links_invalid": len(invalid_links),
                "link_validation_results": link_validation_results,
                "valid_links": valid_links,
                "warning_links": warning_links,
                "invalid_links": invalid_links,
                "category": next((q.category for q in questions if q.id == question_id), "unknown"),
                "complexity": next((q.complexity for q in questions if q.id == question_id), "basic")
            }
            
            comprehensive_results.append(result)
            
            print(f"  ✅ Valid links: {len(valid_links)}")
            print(f"  ⚠️  Warning links: {len(warning_links)}")
            print(f"  ❌ Invalid links: {len(invalid_links)}")
            
            if delay > 0 and i < len(api_responses):
                time.sleep(delay)
        
        return {
            "session_id": session_id,
            "test_name": test_name,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "total_questions": len(questions),
            "results": comprehensive_results
        }

def main():
    parser = argparse.ArgumentParser(description='Enhanced Comprehensive API and Link Validation Test')
    parser.add_argument('--endpoint', required=True, help='API endpoint URL')
    parser.add_argument('--auth', required=True, help='Authorization header')
    parser.add_argument('--questions', default='comprehensive_invalid_links_test_100.json', 
                        help='JSON file containing test questions')
    parser.add_argument('--name', default='Enhanced Comprehensive Link Validation Test', help='Test name')
    parser.add_argument('--description', default='Enhanced comprehensive test with improved link validation', 
                        help='Test description')
    parser.add_argument('--delay', type=float, default=2.0, help='Delay between questions (seconds)')
    parser.add_argument('--output', help='Output file name (auto-generated if not specified)')
    
    args = parser.parse_args()
    
    db = DatabaseManager()
    tester = ComprehensiveTester(args.endpoint, args.auth, db)
    
    questions = tester.load_questions(args.questions)
    if not questions:
        print("❌ No questions loaded. Exiting.")
        return 1
    
    print(f"📝 Loaded {len(questions)} questions from {args.questions}")
    
    results = tester.run_comprehensive_test(
        questions=questions,
        test_name=args.name,
        description=args.description,
        delay=args.delay
    )
    
    if not results:
        print("❌ Test failed")
        return 1
    
    if not args.output:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        args.output = f"enhanced_test_results_{timestamp}.json"
    
    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n📄 Results saved to: {args.output}")
    except Exception as e:
        print(f"❌ Error saving results: {e}")
        return 1
    
    total_links = sum(r["links_found"] for r in results["results"])
    total_valid = sum(r["links_valid"] for r in results["results"])
    total_warning = sum(r["links_warning"] for r in results["results"])
    total_invalid = sum(r["links_invalid"] for r in results["results"])
    
    print("\n" + "=" * 80)
    print(f"📊 ENHANCED COMPREHENSIVE TEST SUMMARY: {args.name}")
    print("=" * 80)
    print(f"✅ Questions processed: {results['total_questions']}")
    print(f"🔗 Total links found: {total_links}")
    if total_links > 0:
        print(f"✅ Valid links: {total_valid} ({(total_valid/total_links*100):.1f}%)")
        print(f"⚠️  Warning links: {total_warning} ({(total_warning/total_links*100):.1f}%)")
        print(f"❌ Invalid links: {total_invalid} ({(total_invalid/total_links*100):.1f}%)")
        print(f"🎯 Success rate (Valid + Warning): {((total_valid + total_warning)/total_links*100):.1f}%")
    else:
        print("✅ Valid links: 0")
        print("⚠️  Warning links: 0") 
        print("❌ Invalid links: 0")
    
    if total_invalid > 0:
        print(f"\n❌ Questions with most invalid links:")
        sorted_results = sorted(results["results"], key=lambda x: x["links_invalid"], reverse=True)
        for result in sorted_results[:5]:
            if result["links_invalid"] > 0:
                print(f"  {result['question_id']}: {result['links_invalid']} invalid links")
    
    print(f"\n✅ Enhanced comprehensive test completed successfully!")
    print(f"📄 Upload {args.output} to your dashboard for detailed analysis")
    
    return 0

if __name__ == "__main__":
    exit(main())
