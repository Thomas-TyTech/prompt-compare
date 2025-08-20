#!/usr/bin/env python3
"""
Question-by-Question Comparison Dashboard
Creates an expandable HTML dashboard showing side-by-side responses for each question.
"""

import json
import os
import argparse
from datetime import datetime
from typing import Dict, Any, List
import html as html_module


class QuestionComparisonDashboard:
    
    def __init__(self):
        pass
    
    def generate_dashboard(self, results_file: str, output_html: str = None) -> str:
        """Generate a question-by-question comparison dashboard."""
        
        print(f"📊 Loading evaluation results from {results_file}...")
        
        with open(results_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Generate output filename if not specified
        if output_html is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_name = os.path.splitext(os.path.basename(results_file))[0]
            output_html = f"{base_name}_questions_{timestamp}.html"
        
        # Generate HTML content
        html_content = self._generate_html(data)
        
        # Write HTML file
        with open(output_html, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ Question comparison dashboard generated: {output_html}")
        
        return output_html
    
    def _generate_html(self, data: Dict[str, Any]) -> str:
        """Generate the HTML content for the dashboard."""
        
        session = data.get('evaluation_session', {})
        detailed_results = data.get('detailed_results', {})
        
        # Extract questions and responses
        questions_data = {}
        prompt_names = {}
        
        for prompt_key, prompt_data in detailed_results.items():
            if isinstance(prompt_data, dict) and 'detailed_results' in prompt_data:
                prompt_info = prompt_data.get('prompt_version', {})
                prompt_name = prompt_info.get('name', prompt_key)
                prompt_names[prompt_key] = prompt_name
                
                for result in prompt_data['detailed_results']:
                    question_id = result.get('question_id', 'Unknown')
                    question_text = result.get('question', 'No question text')
                    response = result.get('response', 'No response')
                    response_time = result.get('response_time_ms', 0)
                    links_found = result.get('links_found', 0)
                    links_valid = result.get('links_valid', 0)
                    category = result.get('category', 'general')
                    complexity = result.get('complexity', 'basic')
                    
                    if question_id not in questions_data:
                        questions_data[question_id] = {
                            'question': question_text,
                            'category': category,
                            'complexity': complexity,
                            'responses': {}
                        }
                    
                    questions_data[question_id]['responses'][prompt_key] = {
                        'response': response,
                        'response_time_ms': response_time,
                        'links_found': links_found,
                        'links_valid': links_valid,
                        'prompt_name': prompt_name
                    }
        
        # Sort questions by ID
        sorted_questions = sorted(questions_data.items(), key=lambda x: x[0])
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Question Comparison - {session.get('name', 'Evaluation')}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f8fafc;
            color: #1a202c;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }}
        
        .header {{
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
            text-align: center;
        }}
        
        .header h1 {{
            color: #2d3748;
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }}
        
        .header p {{
            color: #718096;
            font-size: 1.1rem;
        }}
        
        .summary-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 1.5rem 0;
        }}
        
        .stat-card {{
            background: #f7fafc;
            padding: 1rem;
            border-radius: 8px;
            text-align: center;
            border-left: 4px solid #4299e1;
        }}
        
        .stat-number {{
            font-size: 2rem;
            font-weight: bold;
            color: #2d3748;
        }}
        
        .stat-label {{
            color: #718096;
            font-size: 0.9rem;
        }}
        
        .question-list {{
            space-y: 1rem;
        }}
        
        .question-item {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 1rem;
            overflow: hidden;
        }}
        
        .question-header {{
            padding: 1.5rem;
            cursor: pointer;
            border-left: 4px solid #4299e1;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #f8fafc;
            transition: background 0.2s;
        }}
        
        .question-header:hover {{
            background: #f1f5f9;
        }}
        
        .question-header.active {{
            background: #e6fffa;
            border-left-color: #38a169;
        }}
        
        .question-info {{
            flex: 1;
        }}
        
        .question-id {{
            font-weight: bold;
            color: #4299e1;
            font-size: 0.9rem;
            margin-bottom: 0.25rem;
        }}
        
        .question-text {{
            color: #2d3748;
            font-size: 1.1rem;
            margin-bottom: 0.5rem;
        }}
        
        .question-meta {{
            display: flex;
            gap: 1rem;
            font-size: 0.8rem;
            color: #718096;
        }}
        
        .expand-icon {{
            color: #718096;
            font-size: 1.2rem;
            transition: transform 0.3s;
        }}
        
        .expand-icon.rotated {{
            transform: rotate(180deg);
        }}
        
        .question-content {{
            display: none;
            padding: 0;
        }}
        
        .question-content.show {{
            display: block;
        }}
        
        .responses-container {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0;
        }}
        
        .response-panel {{
            padding: 1.5rem;
            border-right: 1px solid #e2e8f0;
        }}
        
        .response-panel:last-child {{
            border-right: none;
        }}
        
        .response-panel.prompt-a {{
            background: #f0f9ff;
            border-top: 3px solid #4299e1;
        }}
        
        .response-panel.prompt-b {{
            background: #f0fff4;
            border-top: 3px solid #48bb78;
        }}
        
        .response-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #e2e8f0;
        }}
        
        .prompt-name {{
            font-weight: bold;
            font-size: 1.1rem;
        }}
        
        .prompt-name.prompt-a {{
            color: #2b6cb0;
        }}
        
        .prompt-name.prompt-b {{
            color: #2f855a;
        }}
        
        .response-stats {{
            display: flex;
            gap: 1rem;
            font-size: 0.85rem;
            color: #718096;
        }}
        
        .response-text {{
            background: white;
            padding: 1rem;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            white-space: pre-wrap;
            font-size: 0.95rem;
            line-height: 1.5;
            max-height: 400px;
            overflow-y: auto;
        }}
        
        .no-response {{
            color: #e53e3e;
            font-style: italic;
            background: #fed7d7;
            border-color: #feb2b2;
        }}
        
        @media (max-width: 768px) {{
            .container {{
                padding: 1rem;
            }}
            
            .responses-container {{
                grid-template-columns: 1fr;
            }}
            
            .response-panel {{
                border-right: none;
                border-bottom: 1px solid #e2e8f0;
            }}
            
            .response-panel:last-child {{
                border-bottom: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{session.get('name', 'Question-by-Question Comparison')}</h1>
            <p>{session.get('description', 'Side-by-side comparison of prompt responses')}</p>
            
            <div class="summary-stats">
                <div class="stat-card">
                    <div class="stat-number">{len(sorted_questions)}</div>
                    <div class="stat-label">Total Questions</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{len(prompt_names)}</div>
                    <div class="stat-label">Prompt Versions</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{datetime.now().strftime('%Y-%m-%d')}</div>
                    <div class="stat-label">Generated</div>
                </div>
            </div>
        </div>
        
        <div class="question-list">"""
        
        # Generate question items
        for question_id, question_data in sorted_questions:
            html += f"""
            <div class="question-item">
                <div class="question-header" onclick="toggleQuestion('{question_id}')">
                    <div class="question-info">
                        <div class="question-id">{question_id}</div>
                        <div class="question-text">{html_module.escape(question_data['question'])}</div>
                        <div class="question-meta">
                            <span>Category: {question_data['category']}</span>
                            <span>Complexity: {question_data['complexity']}</span>
                        </div>
                    </div>
                    <div class="expand-icon" id="icon-{question_id}">▼</div>
                </div>
                
                <div class="question-content" id="content-{question_id}">
                    <div class="responses-container">"""
            
            # Generate response panels
            for i, (prompt_key, prompt_name) in enumerate(prompt_names.items()):
                panel_class = "prompt-a" if i == 0 else "prompt-b"
                name_class = "prompt-a" if i == 0 else "prompt-b"
                
                response_data = question_data['responses'].get(prompt_key, {})
                response = response_data.get('response', 'No response available')
                response_time = response_data.get('response_time_ms', 0)
                links_found = response_data.get('links_found', 0)
                links_valid = response_data.get('links_valid', 0)
                
                response_class = "no-response" if not response or response == 'No response available' else ""
                
                html += f"""
                        <div class="response-panel {panel_class}">
                            <div class="response-header">
                                <div class="prompt-name {name_class}">{html_module.escape(prompt_name)}</div>
                                <div class="response-stats">
                                    <span>{response_time}ms</span>
                                    <span>{links_found} links</span>
                                    <span>{links_valid} valid</span>
                                </div>
                            </div>
                            <div class="response-text {response_class}">{html_module.escape(response)}</div>
                        </div>"""
            
            html += """
                    </div>
                </div>
            </div>"""
        
        html += f"""
        </div>
    </div>
    
    <script>
        function toggleQuestion(questionId) {{
            const content = document.getElementById('content-' + questionId);
            const icon = document.getElementById('icon-' + questionId);
            const header = content.previousElementSibling;
            
            if (content.classList.contains('show')) {{
                content.classList.remove('show');
                icon.classList.remove('rotated');
                header.classList.remove('active');
            }} else {{
                content.classList.add('show');
                icon.classList.add('rotated');
                header.classList.add('active');
            }}
        }}
        
        // Optional: Expand first question by default
        // toggleQuestion('{sorted_questions[0][0] if sorted_questions else 'Q001'}');
    </script>
</body>
</html>"""
        
        return html


def main():
    parser = argparse.ArgumentParser(description='Generate Question-by-Question Comparison Dashboard')
    parser.add_argument('--input', required=True, help='Multi-prompt evaluation JSON results file')
    parser.add_argument('--output', help='Output HTML filename (auto-generated if not specified)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"❌ Input file not found: {args.input}")
        return 1
    
    dashboard = QuestionComparisonDashboard()
    
    try:
        output_file = dashboard.generate_dashboard(args.input, args.output)
        print(f"🎉 Question comparison dashboard generated successfully!")
        print(f"📊 Open in browser: file://{os.path.abspath(output_file)}")
        return 0
        
    except Exception as e:
        print(f"❌ Error generating dashboard: {e}")
        return 1


if __name__ == "__main__":
    exit(main())