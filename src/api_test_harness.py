#!/usr/bin/env python3

import time
import json
import sqlite3
import requests
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
import argparse
from dataclasses import dataclass, asdict
import base64

@dataclass
class TestQuestion:
    id: str
    question: str
    category: str
    expected_topics: Optional[List[str]] = None
    complexity: str = "basic"
    user_persona: str = "general"

@dataclass
class TestResult:
    id: str
    test_id: str
    question_id: str
    question: str
    category: str
    response: str
    response_time_ms: int
    timestamp: str
    status: str
    error: Optional[str] = None
    conversation_id: str = ""
    request_payload: Optional[Dict] = None
    response_metadata: Optional[Dict] = None

class DatabaseManager:
    
    def __init__(self):
        self.setup_sqlite()
    
    def setup_sqlite(self):
        os.makedirs('data', exist_ok=True)
        self.db_path = 'data/api_test_results.db'
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS test_sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                api_endpoint TEXT NOT NULL,
                total_questions INTEGER NOT NULL,
                successful_questions INTEGER DEFAULT 0,
                failed_questions INTEGER DEFAULT 0,
                avg_response_time_ms REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS test_results (
                id TEXT PRIMARY KEY,
                test_session_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                question TEXT NOT NULL,
                category TEXT NOT NULL,
                response TEXT NOT NULL,
                response_time_ms INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                conversation_id TEXT,
                request_payload TEXT,
                response_metadata TEXT,
                FOREIGN KEY (test_session_id) REFERENCES test_sessions (id)
            )
        ''')
        
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_test_results_session ON test_results(test_session_id)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_test_results_category ON test_results(category)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_test_results_status ON test_results(status)')
        
        self.conn.commit()
        print("✓ SQLite database initialized")
    
    def create_test_session(self, name: str, description: str, api_endpoint: str, total_questions: int) -> str:
        session_id = str(uuid.uuid4())
        
        self.conn.execute('''
            INSERT INTO test_sessions (id, name, description, api_endpoint, total_questions)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_id, name, description, api_endpoint, total_questions))
        self.conn.commit()
        
        return session_id
    
    def save_result(self, result: TestResult):
        self.conn.execute('''
            INSERT INTO test_results (
                id, test_session_id, question_id, question, category, response,
                response_time_ms, timestamp, status, error, conversation_id,
                request_payload, response_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result.id, result.test_id, result.question_id, result.question,
            result.category, result.response, result.response_time_ms,
            result.timestamp, result.status, result.error, result.conversation_id,
            json.dumps(result.request_payload) if result.request_payload else None,
            json.dumps(result.response_metadata) if result.response_metadata else None
        ))
        self.conn.commit()
    
    def update_session_stats(self, session_id: str, successful: int, failed: int, avg_response_time: float):
        self.conn.execute('''
            UPDATE test_sessions 
            SET successful_questions = ?, failed_questions = ?, avg_response_time_ms = ?, completed_at = ?
            WHERE id = ?
        ''', (successful, failed, avg_response_time, datetime.now().isoformat(), session_id))
        self.conn.commit()
    
    def get_results_for_dashboard(self, session_id: str) -> List[Dict]:
        cursor = self.conn.execute('''
            SELECT * FROM test_results WHERE test_session_id = ? ORDER BY timestamp
        ''', (session_id,))
        columns = [description[0] for description in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        dashboard_results = []
        for result in results:
            dashboard_result = {
                "id": result['question_id'],
                "name": "api_question",
                "input": {
                    "question": result['question'],
                    "question_num": len(dashboard_results) + 1,
                    "total_questions": len(results)
                },
                "output": {
                    "question_id": len(dashboard_results) + 1,
                    "question": result['question'],
                    "response": result['response'],
                    "response_time_ms": result['response_time_ms'],
                    "timestamp": result['timestamp'],
                    "status": result['status'],
                    "complexity": "basic"
                },
                "duration": result['response_time_ms'] / 1000.0,
                "comments": result['error'] or "",
                "feedback_scores.Correctness": 5 if result['status'] == 'success' else 1,
                "feedback_scores.Correctness_reason": "Automated API test"
            }
            dashboard_results.append(dashboard_result)
        
        return dashboard_results

class APITester:
    
    def __init__(self, api_endpoint: str, auth_header: str, database_manager: DatabaseManager):
        self.api_endpoint = api_endpoint
        self.auth_header = auth_header
        self.db = database_manager
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': auth_header
        })
    
    def test_api_connection(self) -> bool:
        try:
            test_payload = {
                "followUpText": json.dumps([{"question": "Hello", "response": ""}]),
                "conversationId": "CONNECTION_TEST"
            }
            
            response = self.session.post(self.api_endpoint, json=test_payload, timeout=10)
            if response.status_code == 200:
                print("✓ API connection successful")
                return True
            else:
                print(f"✗ API connection failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ API connection error: {e}")
            return False
    
    def ask_question(self, question: TestQuestion, conversation_id: str = None) -> TestResult:
        conversation_id = conversation_id or f"TEST_{int(time.time())}"
        result_id = str(uuid.uuid4())
        
        payload = {
            "followUpText": json.dumps([{"question": question.question, "response": ""}]),
            "conversationId": conversation_id
        }
        
        start_time = time.time()
        
        try:
            response = self.session.post(self.api_endpoint, json=payload, timeout=60)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                response_data = response.json()
                api_response = response_data.get('response', '')
                
                return TestResult(
                    id=result_id,
                    test_id="",
                    question_id=question.id,
                    question=question.question,
                    category=question.category,
                    response=api_response,
                    response_time_ms=response_time_ms,
                    timestamp=datetime.now().isoformat(),
                    status='success',
                    conversation_id=conversation_id,
                    request_payload=payload,
                    response_metadata={'status_code': response.status_code, 'headers': dict(response.headers)}
                )
            else:
                return TestResult(
                    id=result_id,
                    test_id="",
                    question_id=question.id,
                    question=question.question,
                    category=question.category,
                    response="",
                    response_time_ms=response_time_ms,
                    timestamp=datetime.now().isoformat(),
                    status='error',
                    error=f"HTTP {response.status_code}: {response.text}",
                    conversation_id=conversation_id,
                    request_payload=payload
                )
                
        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return TestResult(
                id=result_id,
                test_id="",
                question_id=question.id,
                question=question.question,
                category=question.category,
                response="",
                response_time_ms=response_time_ms,
                timestamp=datetime.now().isoformat(),
                status='error',
                error=str(e),
                conversation_id=conversation_id,
                request_payload=payload
            )
    
    def run_test_suite(self, questions: List[TestQuestion], test_name: str, 
                      description: str = "", delay_between_questions: float = 1.0,
                      use_single_conversation: bool = False) -> str:
        
        print(f"🚀 Starting API Test: {test_name}")
        print(f"📊 Questions: {len(questions)}")
        print(f"🔗 Endpoint: {self.api_endpoint}")
        print(f"⏱️  Delay: {delay_between_questions}s between questions")
        print(f"💬 Conversation mode: {'Single' if use_single_conversation else 'Individual'}")
        print("=" * 60)
        
        session_id = self.db.create_test_session(test_name, description, self.api_endpoint, len(questions))
        if not session_id:
            print("✗ Failed to create test session")
            return None
        
        if use_single_conversation:
            conversation_id = f"TEST_SESSION_{session_id}"
        
        results = []
        successful = 0
        failed = 0
        total_response_time = 0
        
        for i, question in enumerate(questions, 1):
            print(f"\n[{i}/{len(questions)}] {question.id}: {question.question[:80]}...")
            
            conv_id = conversation_id if use_single_conversation else f"TEST_{question.id}_{int(time.time())}"
            
            result = self.ask_question(question, conv_id)
            result.test_id = session_id
            
            self.db.save_result(result)
            results.append(result)
            
            if result.status == 'success':
                successful += 1
                print(f"✓ Success ({result.response_time_ms}ms)")
                print(f"  Response: {result.response[:150]}...")
            else:
                failed += 1
                print(f"✗ Failed: {result.error}")
            
            total_response_time += result.response_time_ms
            
            if i < len(questions) and delay_between_questions > 0:
                time.sleep(delay_between_questions)
        
        avg_response_time = total_response_time / len(questions) if questions else 0
        self.db.update_session_stats(session_id, successful, failed, avg_response_time)
        
        print("\n" + "=" * 60)
        print(f"📋 TEST SUMMARY: {test_name}")
        print("=" * 60)
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"📊 Success Rate: {(successful/len(questions)*100):.1f}%" if questions else "0%")
        print(f"⏱️  Average Response Time: {avg_response_time:.0f}ms")
        print(f"💾 Session ID: {session_id}")
        
        return session_id
    
    def export_for_dashboard(self, session_id: str, output_file: str = None) -> str:
        results = self.db.get_results_for_dashboard(session_id)
        
        if not output_file:
            output_file = f"api_test_results_{session_id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"📄 Dashboard-compatible results exported to: {output_file}")
        return output_file

def get_sample_questions() -> List[TestQuestion]:
    return [
        TestQuestion("Q001", "What is the state of the state address for 2025?", "government", complexity="basic"),
        TestQuestion("Q002", "How do I register to vote in South Carolina?", "civic", complexity="basic"),
        TestQuestion("Q003", "What are the requirements for a South Carolina driver's license?", "transportation", complexity="basic"),
        TestQuestion("Q004", "How can I start a small business in South Carolina?", "business", complexity="complex"),
        TestQuestion("Q005", "What assistance is available for first-time homebuyers?", "housing", complexity="complex"),
        TestQuestion("Q006", "How do I apply for unemployment benefits?", "employment", complexity="basic"),
        TestQuestion("Q007", "What are the hunting and fishing license requirements?", "recreation", complexity="basic"),
        TestQuestion("Q008", "How can I get help with my property taxes?", "taxation", complexity="basic"),
        TestQuestion("Q009", "What services are available for seniors in South Carolina?", "seniors", complexity="complex"),
        TestQuestion("Q010", "How do I report a pothole or road maintenance issue?", "infrastructure", complexity="basic"),
    ]

def load_questions_from_file(file_path: str) -> List[TestQuestion]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        questions = []
        for item in data:
            questions.append(TestQuestion(
                id=item.get('id', f"Q{len(questions)+1:03d}"),
                question=item['question'],
                category=item.get('category', 'general'),
                expected_topics=item.get('expected_topics'),
                complexity=item.get('complexity', 'basic')
            ))
        
        return questions
    except Exception as e:
        print(f"✗ Error loading questions from {file_path}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='AI API Test Harness')
    parser.add_argument('--endpoint', required=True, help='API endpoint URL')
    parser.add_argument('--auth', required=True, help='Authorization header (e.g., "Basic xyz123")')
    parser.add_argument('--questions', help='JSON file with questions (uses samples if not provided)')
    parser.add_argument('--name', default='API Test', help='Test session name')
    parser.add_argument('--description', default='', help='Test description')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between questions (seconds)')
    parser.add_argument('--single-conversation', action='store_true', help='Use single conversation ID for all questions')
    parser.add_argument('--export', help='Export results for dashboard to specified file')
    parser.add_argument('--test-connection', action='store_true', help='Test API connection and exit')
    
    args = parser.parse_args()
    
    db = DatabaseManager()
    
    tester = APITester(args.endpoint, args.auth, db)
    
    if args.test_connection:
        success = tester.test_api_connection()
        return 0 if success else 1
    
    if args.questions:
        questions = load_questions_from_file(args.questions)
        if not questions:
            return 1
    else:
        print("📝 Using sample questions (use --questions to load from file)")
        questions = get_sample_questions()
    
    session_id = tester.run_test_suite(
        questions=questions,
        test_name=args.name,
        description=args.description,
        delay_between_questions=args.delay,
        use_single_conversation=args.single_conversation
    )
    
    if not session_id:
        return 1
    
    if args.export:
        tester.export_for_dashboard(session_id, args.export)
    else:
        output_file = tester.export_for_dashboard(session_id)
        print(f"\n💡 Upload {output_file} to your dashboard to visualize results!")
    
    return 0

if __name__ == "__main__":
    exit(main())
