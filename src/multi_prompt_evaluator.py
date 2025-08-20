import os
import sys
import json
import time
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid
from dataclasses import dataclass, asdict

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from api_test_harness import APITester, DatabaseManager, TestQuestion
from enhanced_link_validation import EnhancedLinkValidator, ComprehensiveTester

@dataclass
class PromptVersion:
    id: str
    name: str
    description: str
    version: str
    timestamp: str

@dataclass
class EvaluationSession:
    id: str
    name: str
    description: str
    created_at: str
    test_questions: List[TestQuestion]
    prompt_versions: List[PromptVersion]
    results: Dict[str, Any] = None

class MultiPromptEvaluator:
    
    def __init__(self, api_endpoint: str, auth_header: str, database_manager: DatabaseManager):
        self.api_endpoint = api_endpoint
        self.auth_header = auth_header
        self.db = database_manager
        
        self.api_tester = APITester(api_endpoint, auth_header, database_manager)
        self.link_validator = EnhancedLinkValidator()
        
        self.current_session: Optional[EvaluationSession] = None
        self.results_by_prompt: Dict[str, Any] = {}
    
    def create_evaluation_session(self, name: str, description: str, 
                                test_questions: List[TestQuestion]) -> EvaluationSession:
        session = EvaluationSession(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            created_at=datetime.now().isoformat(),
            test_questions=test_questions,
            prompt_versions=[],
            results={}
        )
        
        self.current_session = session
        print(f"📋 Created evaluation session: {name}")
        print(f"   Session ID: {session.id}")
        print(f"   Test questions: {len(test_questions)}")
        
        return session
    
    def test_api_connection(self) -> bool:
        print("🔌 Testing API connection...")
        success = self.api_tester.test_api_connection()
        if success:
            print("✅ API connection successful")
        else:
            print("❌ API connection failed - please check endpoint and auth")
        return success
    
    def wait_for_prompt_change(self, prompt_version: PromptVersion, is_first: bool = False) -> bool:
        print("\n" + "="*80)
        if is_first:
            print(f"🎯 PROMPT SETUP: {prompt_version.name}")
            print("   Please set up the initial prompt in your GUI")
        else:
            print(f"🔄 PROMPT CHANGE REQUIRED: {prompt_version.name}")
            print("   Please update the prompt in your GUI to the next version")
        
        print(f"   Version: {prompt_version.version}")
        print(f"   Description: {prompt_version.description}")
        print("\n   Instructions:")
        print("   1. Go to your Resident Assistant GUI")
        print("   2. Update the system prompt as needed")
        print("   3. Save/apply the changes")
        print("   4. Return here and press ENTER to continue")
        print("   5. Or type 'skip' to skip this prompt version")
        print("   6. Or type 'quit' to stop the evaluation")
        print("="*80)
        
        while True:
            user_input = input("\nPress ENTER when prompt is updated (or 'skip'/'quit'): ").strip().lower()
            
            if user_input == '':
                print("✅ Continuing with updated prompt...")
                return True
            elif user_input == 'skip':
                print("⏭️  Skipping this prompt version...")
                return False
            elif user_input == 'quit':
                print("🛑 Stopping evaluation...")
                sys.exit(0)
            else:
                print("⚠️  Please press ENTER to continue, or type 'skip' or 'quit'")
    
    def run_single_prompt_evaluation(self, prompt_version: PromptVersion, 
                                   questions: List[TestQuestion],
                                   delay_between_questions: float = 2.0) -> Dict[str, Any]:
        
        print(f"\n🚀 Starting evaluation for: {prompt_version.name}")
        print(f"   Questions: {len(questions)}")
        print(f"   Delay between questions: {delay_between_questions}s")
        print("-" * 60)
        
        test_name = f"{self.current_session.name} - {prompt_version.name}"
        
        session_id = self.api_tester.run_test_suite(
            questions=questions,
            test_name=test_name,
            description=f"Evaluation of {prompt_version.name} (v{prompt_version.version})",
            delay_between_questions=delay_between_questions,
            use_single_conversation=False
        )
        
        if not session_id:
            print(f"❌ Failed to run tests for {prompt_version.name}")
            return None
        
        api_responses = self.db.get_results_for_dashboard(session_id)
        
        print(f"\n🔍 Running link validation for {len(api_responses)} responses...")
        
        detailed_results = []
        link_validation_summary = {
            "total_links": 0,
            "valid_links": 0,
            "warning_links": 0,
            "invalid_links": 0,
            "questions_with_invalid_links": 0
        }
        
        for i, response in enumerate(api_responses, 1):
            question_id = response.get("id", f"Q{i:03d}")
            question_text = response.get("input", {}).get("question", "")
            response_text = response.get("output", {}).get("response", "")
            response_time_ms = response.get("output", {}).get("response_time_ms", 0)
            
            print(f"  [{i}/{len(api_responses)}] Validating links in {question_id}...")
            
            extracted_links = self.link_validator.extract_links(response_text)
            link_results = []
            
            if extracted_links:
                link_results = self.link_validator.validate_links(extracted_links, show_progress=False)
            
            valid_links = [link for link in link_results if link["status"] == "valid"]
            warning_links = [link for link in link_results if link["status"] == "warning"]
            invalid_links = [link for link in link_results if link["status"] == "invalid"]
            
            link_validation_summary["total_links"] += len(extracted_links)
            link_validation_summary["valid_links"] += len(valid_links)
            link_validation_summary["warning_links"] += len(warning_links)
            link_validation_summary["invalid_links"] += len(invalid_links)
            if len(invalid_links) > 0:
                link_validation_summary["questions_with_invalid_links"] += 1
            
            result = {
                "question_id": question_id,
                "question": question_text,
                "response": response_text,
                "response_time_ms": response_time_ms,
                "links_found": len(extracted_links),
                "links_valid": len(valid_links),
                "links_warning": len(warning_links),
                "links_invalid": len(invalid_links),
                "link_validation_results": link_results,
                "extracted_links": extracted_links,
                "category": next((q.category for q in questions if q.id == question_id), "unknown"),
                "complexity": next((q.complexity for q in questions if q.id == question_id), "basic"),
                "user_persona": next((q.user_persona for q in questions if q.id == question_id), "general")
            }
            
            detailed_results.append(result)
        
        evaluation_result = {
            "prompt_version": asdict(prompt_version),
            "session_id": session_id,
            "test_name": test_name,
            "timestamp": datetime.now().isoformat(),
            "total_questions": len(questions),
            "api_results": api_responses,
            "detailed_results": detailed_results,
            "link_validation_summary": link_validation_summary,
            "performance_metrics": {
                "avg_response_time_ms": sum(r["response_time_ms"] for r in detailed_results) / len(detailed_results) if detailed_results else 0,
                "successful_responses": len([r for r in api_responses if r.get("output", {}).get("status") == "success"]),
                "failed_responses": len([r for r in api_responses if r.get("output", {}).get("status") != "success"])
            }
        }
        
        print(f"\n📊 Summary for {prompt_version.name}:")
        print(f"   ✅ Successful API calls: {evaluation_result['performance_metrics']['successful_responses']}")
        print(f"   ❌ Failed API calls: {evaluation_result['performance_metrics']['failed_responses']}")
        print(f"   🔗 Total links found: {link_validation_summary['total_links']}")
        print(f"   ✅ Valid links: {link_validation_summary['valid_links']}")
        print(f"   ⚠️  Warning links: {link_validation_summary['warning_links']}")
        print(f"   ❌ Invalid links: {link_validation_summary['invalid_links']}")
        if link_validation_summary['total_links'] > 0:
            success_rate = ((link_validation_summary['valid_links'] + link_validation_summary['warning_links']) / link_validation_summary['total_links']) * 100
            print(f"   🎯 Link success rate: {success_rate:.1f}%")
        
        return evaluation_result
    
    def run_multi_prompt_evaluation(self, prompt_versions: List[PromptVersion],
                                  questions: List[TestQuestion] = None,
                                  delay_between_questions: float = 2.0,
                                  delay_between_prompts: float = 5.0) -> Dict[str, Any]:
        
        if not self.current_session:
            raise ValueError("No evaluation session created. Call create_evaluation_session first.")
        
        if questions is None:
            questions = self.current_session.test_questions
        
        print(f"\n🎯 MULTI-PROMPT EVALUATION: {self.current_session.name}")
        print(f"📋 Session ID: {self.current_session.id}")
        print(f"📊 Prompt versions: {len(prompt_versions)}")
        print(f"❓ Test questions: {len(questions)}")
        print(f"⏱️  Delay between questions: {delay_between_questions}s")
        print(f"🔄 Delay between prompts: {delay_between_prompts}s")
        print("="*80)
        
        if not self.test_api_connection():
            return None
        
        all_results = {}
        
        for i, prompt_version in enumerate(prompt_versions, 1):
            print(f"\n🔄 PROMPT VERSION {i}/{len(prompt_versions)}")
            
            is_first = (i == 1)
            should_continue = self.wait_for_prompt_change(prompt_version, is_first)
            
            if not should_continue:
                print(f"⏭️  Skipped {prompt_version.name}")
                continue
            
            self.current_session.prompt_versions.append(prompt_version)
            
            result = self.run_single_prompt_evaluation(
                prompt_version, 
                questions, 
                delay_between_questions
            )
            
            if result:
                all_results[prompt_version.id] = result
                print(f"✅ Completed evaluation for {prompt_version.name}")
            else:
                print(f"❌ Failed evaluation for {prompt_version.name}")
            
            if i < len(prompt_versions) and delay_between_prompts > 0:
                print(f"\n⏳ Waiting {delay_between_prompts}s before next prompt...")
                time.sleep(delay_between_prompts)
        
        self.current_session.results = all_results
        self.results_by_prompt = all_results
        
        return all_results
    
    def save_evaluation_results(self, filename: str = None) -> str:
        if not self.current_session or not self.current_session.results:
            raise ValueError("No evaluation results to save")
        
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = self.current_session.name.replace(' ', '_').replace('/', '_')
            filename = f"multi_prompt_evaluation_{safe_name}_{timestamp}.json"
        
        complete_results = {
            "evaluation_session": asdict(self.current_session),
            "summary": self.generate_comparison_summary(),
            "detailed_results": self.current_session.results,
            "metadata": {
                "api_endpoint": self.api_endpoint,
                "total_prompts_tested": len(self.current_session.prompt_versions),
                "total_questions": len(self.current_session.test_questions),
                "evaluation_completed_at": datetime.now().isoformat()
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(complete_results, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Evaluation results saved to: {filename}")
        return filename
    
    def generate_comparison_summary(self) -> Dict[str, Any]:
        if not self.current_session or not self.current_session.results:
            return {}
        
        summary = {
            "prompt_comparison": {},
            "overall_metrics": {
                "total_prompts": len(self.current_session.results),
                "total_questions_per_prompt": len(self.current_session.test_questions),
                "best_prompt_for_links": None,
                "best_prompt_for_response_time": None
            }
        }
        
        best_link_score = -1
        best_response_time = float('inf')
        
        for prompt_id, result in self.current_session.results.items():
            prompt_name = result["prompt_version"]["name"]
            link_summary = result["link_validation_summary"]
            perf_metrics = result["performance_metrics"]
            
            total_links = link_summary["total_links"]
            if total_links > 0:
                link_success_rate = ((link_summary["valid_links"] + link_summary["warning_links"]) / total_links) * 100
            else:
                link_success_rate = 100
            
            if link_success_rate > best_link_score:
                best_link_score = link_success_rate
                summary["overall_metrics"]["best_prompt_for_links"] = prompt_name
            
            avg_response_time = perf_metrics["avg_response_time_ms"]
            if avg_response_time < best_response_time:
                best_response_time = avg_response_time
                summary["overall_metrics"]["best_prompt_for_response_time"] = prompt_name
            
            summary["prompt_comparison"][prompt_name] = {
                "link_success_rate": round(link_success_rate, 1),
                "total_links": total_links,
                "valid_links": link_summary["valid_links"],
                "invalid_links": link_summary["invalid_links"],
                "avg_response_time_ms": round(avg_response_time, 0),
                "successful_api_calls": perf_metrics["successful_responses"],
                "failed_api_calls": perf_metrics["failed_responses"],
                "questions_with_invalid_links": link_summary["questions_with_invalid_links"]
            }
        
        return summary
    
    def print_final_summary(self):
        if not self.current_session or not self.current_session.results:
            print("❌ No results to summarize")
            return
        
        summary = self.generate_comparison_summary()
        
        print("\n" + "="*80)
        print(f"📊 FINAL EVALUATION SUMMARY: {self.current_session.name}")
        print("="*80)
        
        print(f"🎯 Tested {summary['overall_metrics']['total_prompts']} prompt versions")
        print(f"❓ {summary['overall_metrics']['total_questions_per_prompt']} questions per prompt")
        
        print(f"\n🏆 BEST PERFORMERS:")
        print(f"   🔗 Best for links: {summary['overall_metrics']['best_prompt_for_links']}")
        print(f"   ⚡ Fastest response: {summary['overall_metrics']['best_prompt_for_response_time']}")
        
        print(f"\n📋 PROMPT COMPARISON:")
        for prompt_name, metrics in summary["prompt_comparison"].items():
            print(f"\n   {prompt_name}:")
            print(f"      🔗 Link success rate: {metrics['link_success_rate']}%")
            print(f"      📊 Links found: {metrics['total_links']} (✅{metrics['valid_links']} ❌{metrics['invalid_links']})")
            print(f"      ⚡ Avg response time: {metrics['avg_response_time_ms']}ms")
            print(f"      📞 API calls: ✅{metrics['successful_api_calls']} ❌{metrics['failed_api_calls']}")
            print(f"      ⚠️  Questions with invalid links: {metrics['questions_with_invalid_links']}")
        
        print("="*80)

def main():
    parser = argparse.ArgumentParser(description='Multi-Prompt Evaluation Pipeline for Resident Assistant')
    parser.add_argument('--endpoint', required=True, help='API endpoint URL')
    parser.add_argument('--auth', required=True, help='Authorization header')
    parser.add_argument('--questions', help='JSON file with test questions (generates if not provided)')
    parser.add_argument('--num-questions', type=int, default=25, help='Number of questions to generate if no file provided')
    parser.add_argument('--question-type', default='comprehensive', 
                       choices=['comprehensive', 'link_validation_focused', 'basic_services', 'complex_scenarios'],
                       help='Type of questions to generate')
    parser.add_argument('--name', default='Multi-Prompt Evaluation', help='Evaluation session name')
    parser.add_argument('--description', default='Comparative evaluation of multiple prompt versions', help='Session description')
    parser.add_argument('--delay-questions', type=float, default=2.0, help='Delay between questions (seconds)')
    parser.add_argument('--delay-prompts', type=float, default=5.0, help='Delay between prompt versions (seconds)')
    parser.add_argument('--output', help='Output filename (auto-generated if not provided)')
    parser.add_argument('--prompt1-name', default='Baseline Prompt (Current)', help='Name for first prompt version')
    parser.add_argument('--prompt1-desc', default='Current production prompt', help='Description for first prompt version')
    parser.add_argument('--prompt2-name', default='Enhanced Prompt (Test)', help='Name for second prompt version')
    parser.add_argument('--prompt2-desc', default='Modified prompt with improvements', help='Description for second prompt version')
    
    args = parser.parse_args()
    
    db = DatabaseManager()
    evaluator = MultiPromptEvaluator(args.endpoint, args.auth, db)
    
    if args.questions and os.path.exists(args.questions):
        print(f"📝 Loading questions from {args.questions}")
        with open(args.questions, 'r', encoding='utf-8') as f:
            questions_data = json.load(f)
        
        questions = []
        for q in questions_data:
            questions.append(TestQuestion(
                id=q['id'],
                question=q['question'],
                category=q.get('category', 'general'),
                complexity=q.get('complexity', 'basic'),
                user_persona=q.get('user_persona', 'general')
            ))
    else:
        print("❌ No questions file provided. Please provide a questions JSON file using --questions parameter.")
        print("Example format:")
        print('[{"id": "Q001", "question": "Your question?", "category": "general", "complexity": "basic"}]')
        return 1
    
    session = evaluator.create_evaluation_session(args.name, args.description, questions)
    
    prompt_versions = [
        PromptVersion(
            id="prompt_v1",
            name=args.prompt1_name,
            description=args.prompt1_desc,
            version="1.0",
            timestamp=datetime.now().isoformat()
        ),
        PromptVersion(
            id="prompt_v2", 
            name=args.prompt2_name,
            description=args.prompt2_desc,
            version="2.0",
            timestamp=datetime.now().isoformat()
        )
    ]
    
    print(f"\n🎯 This evaluation will test {len(prompt_versions)} prompt versions:")
    for i, pv in enumerate(prompt_versions, 1):
        print(f"   {i}. {pv.name} - {pv.description}")
    
    try:
        results = evaluator.run_multi_prompt_evaluation(
            prompt_versions=prompt_versions,
            questions=questions,
            delay_between_questions=args.delay_questions,
            delay_between_prompts=args.delay_prompts
        )
        
        if results:
            output_file = evaluator.save_evaluation_results(args.output)
            
            evaluator.print_final_summary()
            
            print(f"\n🎉 Multi-prompt evaluation completed successfully!")
            print(f"📄 Results saved to: {output_file}")
            print(f"🚀 Ready for LLM-based grading analysis!")
            
        else:
            print("❌ Evaluation failed")
            return 1
            
    except KeyboardInterrupt:
        print("\n🛑 Evaluation interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Evaluation failed with error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
